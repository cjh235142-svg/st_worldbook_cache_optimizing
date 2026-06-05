from pathlib import Path
from collections import defaultdict

from . import world_book_utils as wu


def run(input_path: str, output_path: str | None = None) -> str:
    """合并同一 (position, constant, depth) 的静态条目。

    处理流程：
    1. 加载重排后世界书
    2. 分类：可合并静态 vs 不可合并（动态/边界副本/补充包裹/outlet/disabled）
    3. 可合并静态按 (pos, constant, depth) 分组，组内 >=2 条则合并
    4. 合并后的条目与不可合并条目统一排序，重分配 order/uid
    5. 清理临时字段并保存

    Args:
        input_path: 重排后世界书 JSON 路径。
        output_path: 输出路径，None 时自动生成。

    Returns:
        合并后世界书 JSON 的路径。

    Notes:
        幂等：已合并的条目（每组只剩 1 条）不会再次合并。
        不修改输入文件。
    """
    assert Path(input_path).exists()
    ip = str(Path(input_path).resolve())
    src = Path(ip)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_merged.json")
    output_path = str(Path(output_path).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    wb = wu.load_world_book(ip)
    entries_data = wb.get("entries", {})
    entries = list(entries_data.values())

    mergeable = []
    non_mergeable = []
    for e in entries:
        if _is_mergeable_static(e):
            mergeable.append(e)
        else:
            non_mergeable.append(e)

    groups = defaultdict(list)
    for e in mergeable:
        pos = e.get("position", 0)
        const = e.get("constant", False)
        depth = e.get("depth")
        groups[(pos, const, depth)].append(e)

    merged = []
    for group in groups.values():
        group.sort(key=lambda x: x.get("order", 100))
        if len(group) == 1:
            merged.append(dict(group[0]))
        else:
            merged.append(_merge_one_group(group))

    all_entries = merged + [dict(e) for e in non_mergeable]
    all_entries.sort(key=lambda x: x.get("order", 100))
    all_entries = wu.reassign_orders(all_entries)
    all_entries = wu.reassign_uids(all_entries)

    for e in all_entries:
        e.pop("_is_static", None)
        e.pop("_original_order", None)
        e.pop("_is_boundary_copy", None)
        e.pop("_is_supplement", None)

    wu.save_world_book(all_entries, output_path)
    return output_path


def _is_mergeable_static(entry: dict) -> bool:
    """判断条目是否为"可合并的静态"条目。

    排除以下类型：
    - outlet（position=7）
    - disabled（disable=true）
    - 边界副本（comment 含 [boundary-copy-）
    - 补充包裹（comment 含 [supplement-）
    - 动态条目（含动态标记）

    Args:
        entry: 世界书条目 dict。

    Returns:
        True = 可参与静态合并。
    """
    assert isinstance(entry, dict)
    content = entry.get("content", "")
    comment = entry.get("comment", "")
    if entry.get("position") == 7:
        return False
    if entry.get("disable", False):
        return False
    if "[boundary-copy-" in comment:
        return False
    if "[supplement-" in comment:
        return False
    if not wu.determine_static(content):
        return False
    return True


def _merge_one_group(group: list[dict]) -> dict:
    """将同一 (pos, constant, depth) 组内多条静态条目合并为一条。

    content 按 order 升序用 \n\n 拼接。
    大部分字段取默认值，仅保留分组字段（pos/const/depth）和 role。

    Args:
        group: 同一分组的静态条目列表（已按 order 排序），len >= 2。

    Returns:
        合并后的单一条目 dict。key 已被清空，comment 格式为 "合并:min-max"。

    Notes:
        displayIndex 由调用方 reassign_uids 重新分配。
        key/keysecondary 清空（蓝灯条目无需关键词匹配）。
    """
    assert isinstance(group, list) and len(group) >= 2
    contents = [e["content"] for e in group]
    merged_content = "\n\n".join(contents)
    min_order = group[0].get("order", 0)
    max_order = group[-1].get("order", 0)
    base = group[0]

    defaults = wu.get_default_entry_fields()
    defaults["position"] = base.get("position", 0)
    defaults["constant"] = base.get("constant", False)
    defaults["depth"] = base.get("depth")
    defaults["content"] = merged_content
    defaults["order"] = min_order
    defaults["comment"] = f"合并:{min_order}-{max_order}"
    defaults["key"] = []
    defaults["keysecondary"] = []
    defaults["role"] = base.get("role")
    defaults["useProbability"] = False
    return defaults


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args()
    out = run(args.input, args.output)
    print(f"Merged world book written to: {out}")
