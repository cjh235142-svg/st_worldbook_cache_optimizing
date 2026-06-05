import re
from copy import deepcopy
from pathlib import Path

from . import world_book_utils as wu

_XML_TAG_RE = re.compile(r"<([\u4e00-\u9fff\w]+)>")
_XML_CLOSE_RE = re.compile(r"</([\u4e00-\u9fff\w]+)>")
_MD_BOUNDARY_RE = re.compile(r"^(#{1,2})\s+(.+?)(开始|结束|start|end|begin|close)\s*$")


class BoundaryPair:
    """存储一对边界条目的信息，用于创建边界副本。

    Attributes:
        open_entry: 开边界条目（如 <暗部>）。
        close_entry: 闭边界条目（如 </暗部>）。
        open_copy_content: 开副本的 content（仅保留标签/标题行）。
        close_copy_content: 闭副本的 content。
    """
    def __init__(self, open_entry, close_entry, open_copy_content, close_copy_content):
        """初始化边界配对。

        Args:
            open_entry: 开边界条目。
            close_entry: 闭边界条目。
            open_copy_content: 开副本的 content 文本（仅标签/标题行）。
            close_copy_content: 闭副本的 content 文本。
        """
        self.open_entry = open_entry
        self.close_entry = close_entry
        self.open_copy_content = open_copy_content
        self.close_copy_content = close_copy_content


def run(input_path: str, output_path: str | None = None,
        wrapper_name: str = "补充内容") -> str:
    """执行重排序、字段重映射、边界检测与复制、补充包裹注入。

    处理流程：
    1. 注入临时字段（_original_order, _is_static）
    2. 检测边界条目对，创建边界副本
    3. 创建补充包裹条目
    4. 6 键排序
    5. 去空（删除无动态的副本和包裹）
    6. 重分配 order/uid
    7. 应用字段修改规则
    8. 清理临时字段并保存

    Args:
        input_path: 拆分后世界书 JSON 路径。
        output_path: 输出路径，None 时自动生成。
        wrapper_name: 补充包裹的内容名称（默认"补充内容"）。

    Returns:
        重排后世界书 JSON 的路径。

    Notes:
        幂等：已处理过的条目（key=["/.*/"] 等）会被跳过。
        不修改输入文件。
    """
    assert Path(input_path).exists()
    ip = str(Path(input_path).resolve())
    src = Path(ip)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_reordered.json")
    output_path = str(Path(output_path).resolve())

    wb = wu.load_world_book(ip)
    entries_data = wb.get("entries", {})
    entries = list(entries_data.values())

    for e in entries:
        e["_original_order"] = e.get("order", 100)
        e["_is_static"] = wu.determine_static(e.get("content", ""))
        e["_is_boundary_copy"] = False
        e["_is_supplement"] = False

    pairs = _pair_boundaries(entries)
    boundary_copies = _create_boundary_copies(entries, pairs)

    supplements = _create_supplement_wrapper(entries, wrapper_name)

    all_entries = list(entries) + boundary_copies + supplements
    all_entries = wu.sort_entries(all_entries)
    all_entries = _prune_empty(all_entries)
    all_entries = wu.reassign_orders(all_entries)
    all_entries = wu.reassign_uids(all_entries)

    for e in all_entries:
        _apply_rules(e)

    for e in all_entries:
        e.pop("_original_order", None)
        e.pop("_pair_id", None)

    wu.save_world_book(all_entries, output_path)
    return output_path


def is_boundary_entry(content: str) -> tuple | None:
    """判断条目是否为边界条目（开/闭标记）。

    边界条目需同时满足：
    1. 无动态标记（determine_static 为 True）
    2. content 存在未闭合的 XML 标签，或以 #/## 开头且以 开始/结束 结尾

    Args:
        content: 条目的 content 文本。

    Returns:
        (type, name, copy_content) 元组，或 None。
        type: "xml_open" | "xml_close" | "md_open" | "md_close"
        name: 标签名或标题基名
        copy_content: 副本使用的纯标签/标题文本

    Notes:
        含动态标记的条目不会被识别为边界（即使有未闭合标签）。
    """
    assert isinstance(content, str)
    if wu.detect_markers(content):
        return None

    xml_result = _detect_xml_boundary_simple(content)
    if xml_result:
        return xml_result

    md_result = _detect_md_boundary(content)
    if md_result:
        return md_result

    return None


def _is_boundary_copy_content(content: str) -> bool:
    """判断 content 是否仅含单个边界标签/标题行（即副本内容形式）。

    用于幂等性检查：若条目的 content 仅为 `<暗部>`、`</暗部>`、
    `# 暗部开始` 等形式，且 key=["/.*/"]，说明它已经是管线生成的副本，
    应跳过二次处理。

    Args:
        content: 条目的 content 文本。

    Returns:
        True = content 仅含单个标签或标题行。

    Notes:
        不与 key=["/.*/"] 联动使用（调用方负责检查 key）。
    """
    assert isinstance(content, str)
    stripped = content.strip()
    if re.match(r"^<[\u4e00-\u9fff\w]+>\s*$", stripped):
        return True
    if re.match(r"^</[\u4e00-\u9fff\w]+>\s*$", stripped):
        return True
    if _MD_BOUNDARY_RE.match(stripped):
        return True
    return False


def _detect_xml_boundary_simple(content: str) -> tuple | None:
    """检测 XML 边界条目：content 开头是否有未闭合的 XML 标签。

    使用 re.match（从头匹配），strip 后标签必须在 content 开头。
    开标签：`<暗部>` 存在且 `</暗部>` 不存在 → xml_open
    闭标签：`</暗部>` 存在且 `<暗部>` 不存在 → xml_close

    Args:
        content: 条目的 content 文本。

    Returns:
        (type, name, copy_content) 或 None。

    Notes:
        使用 re.match 而非 re.search，避免正文中偶然出现的
        `<tag>` 被误判为边界。
    """
    assert isinstance(content, str)
    stripped = content.strip()
    m = _XML_TAG_RE.match(stripped)
    if m:
        tag = m.group(1)
        if f"</{tag}>" not in stripped:
            return ("xml_open", tag, f"<{tag}>")
    m = _XML_CLOSE_RE.match(stripped)
    if m:
        tag = m.group(1)
        if f"<{tag}>" not in stripped:
            return ("xml_close", tag, f"</{tag}>")
    return None


def _detect_md_boundary(content: str) -> tuple | None:
    """检测 Markdown 标题边界条目。

    匹配以 #/## 开头、以 "开始"/"结束"/"start"/"end"/"begin"/"close" 结尾的行。

    Args:
        content: 条目的 content 文本。

    Returns:
        (type, name, copy_content) 或 None。
        type: "md_open" | "md_close"
    """
    assert isinstance(content, str)
    stripped = content.strip()
    for line in stripped.splitlines():
        m = _MD_BOUNDARY_RE.match(line.strip())
        if m:
            heading = m.group(1)
            base = m.group(2).strip()
            suffix = m.group(3)
            btype = "md_open" if suffix in ("开始", "start", "begin") else "md_close"
            return (btype, base, f"{heading} {base}{suffix}")
    return None


def _pair_boundaries(entries: list[dict]) -> list[BoundaryPair]:
    """在相同 position 内对边界条目进行栈式配对。

    仅在同 position 组内配对，不跨组。
    使用栈匹配开/闭边界，最近邻配对。
    跳过已有副本特征的条目（key=["/.*/"] + 副本内容）。

    Args:
        entries: 条目列表（含 _original_order 等临时字段）。

    Returns:
        BoundaryPair 列表。每对包含开闭条目的引用和副本 content。
        每对的开闭条目 position 相同。

    Notes:
        同 position 内栈式配对，不跨 position。
        嵌套标签正确处理：最近邻配对。
    """
    assert isinstance(entries, list)
    groups = {}
    for e in entries:
        pos = e.get("position", 0)
        groups.setdefault(pos, []).append(e)

    pairs = []
    for pos, group in groups.items():
        stack = []
        sorted_group = sorted(group, key=lambda x: x["_original_order"])
        for e in sorted_group:
            content = e.get("content", "")
            comment = e.get("comment", "")
            key = e.get("key", [])

            if key == ["/.*/"] and _is_boundary_copy_content(content):
                continue

            r = _detect_xml_boundary_simple(content)
            if r is None:
                r = _detect_md_boundary(content)
            if r is None:
                continue

            btype, name, copy_content = r
            if btype in ("xml_open", "md_open"):
                stack.append((e, name, copy_content, btype))
            else:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][1] == name:
                        open_e, _, open_copy, open_type = stack.pop(i)
                        pairs.append(BoundaryPair(
                            open_entry=open_e, close_entry=e,
                            open_copy_content=open_copy,
                            close_copy_content=copy_content,
                        ))
                        break
    return pairs


def _create_boundary_copies(entries: list[dict], pairs: list[BoundaryPair]) -> list[dict]:
    """根据边界配对结果创建边界副本条目。

    对每对边界，检查其 order 区间内是否有动态条目。
    有则创建开+闭两个副本（仅保留标签/标题行），并绑定 _pair_id。

    Args:
        entries: 全部条目列表（用于检查区间内是否有动态条目）。
        pairs: _pair_boundaries 返回的配对列表。

    Returns:
        新创建的边界副本条目列表。每个 pair 产生 0 或 2 个副本。

    Notes:
        副本使用 deepcopy 避免影响原始条目。
        副本的 _original_order 设为原始边界的 order 值以保证排序正确。
    """
    assert isinstance(entries, list)
    assert isinstance(pairs, list)
    copies = []
    for pair_id, pair in enumerate(pairs):
        min_order = pair.open_entry["_original_order"]
        max_order = pair.close_entry["_original_order"]
        has_dynamic = any(
            min_order < e["_original_order"] < max_order
            and not wu.determine_static(e.get("content", ""))
            for e in entries
        )
        if not has_dynamic:
            continue

        open_copy = deepcopy(pair.open_entry)
        open_copy["content"] = pair.open_copy_content
        open_copy["_is_boundary_copy"] = True
        open_copy["_original_order"] = min_order
        open_copy["_pair_id"] = pair_id
        open_copy["comment"] = (
            f"{pair.open_entry.get('comment','')} [boundary-copy-open]"
        ).strip()
        open_copy["uid"] = None

        close_copy = deepcopy(pair.close_entry)
        close_copy["content"] = pair.close_copy_content
        close_copy["_is_boundary_copy"] = True
        close_copy["_original_order"] = max_order
        close_copy["_pair_id"] = pair_id
        close_copy["comment"] = (
            f"{pair.close_entry.get('comment','')} [boundary-copy-close]"
        ).strip()
        close_copy["uid"] = None

        copies.extend([open_copy, close_copy])
    return copies


def _detect_wrapper_style(entries: list[dict]) -> str:
    """统计所有条目中 XML 标签与 Markdown 标题的使用频率，决定包裹风格。

    统计全书的 XML 标签数（<tag>）和 Markdown 标题行（#/## 开头行）。
    返回出现次数更多的风格。

    Args:
        entries: 条目列表。

    Returns:
        "xml" 或 "markdown"。
    """
    assert isinstance(entries, list)
    xml_count = 0
    md_count = 0
    for e in entries:
        content = e.get("content", "")
        xml_count += len(re.findall(r"<[\u4e00-\u9fff\w]+>", content))
        md_count += len(re.findall(r"^#{1,2}\s", content, re.MULTILINE))
    return "xml" if xml_count >= md_count else "markdown"


def _is_existing_supplement(entry: dict, wrapper_name: str) -> bool:
    """判断条目是否为已有的补充包裹条目。

    用于幂等性检查：避免二次运行时重复创建补充包裹。

    Args:
        entry: 条目 dict。
        wrapper_name: 补充包裹的内容名称。

    Returns:
        True = 该条目已是补充包裹。

    Notes:
        精确匹配 comment 值（"[supplement-start]" / "[supplement-end]"）
        而非子串匹配，避免用户条目的 comment 含 "[supplement-" 被误判。
    """
    assert isinstance(entry, dict)
    comment = entry.get("comment", "")
    if comment in ("[supplement-start]", "[supplement-end]"):
        return True
    content = entry.get("content", "").strip()
    key = entry.get("key", [])
    if key == ["/.*/"]:
        open_pattern = f"<{wrapper_name}>"
        close_pattern = f"</{wrapper_name}>"
        md_start = f"# {wrapper_name}开始"
        md_end = f"# {wrapper_name}结束"
        if content in (open_pattern, close_pattern, md_start, md_end):
            return True
    return False


def _create_supplement_wrapper(entries: list[dict], wrapper_name: str) -> list[dict]:
    """若世界书含动态条目，创建补充包裹条目（开+闭）。

    补充包裹用 <补充内容>...</补充内容> 或 # 补充内容开始...# 补充内容结束
    的形式将所有动态内容包裹起来，使缓存前缀不受动态内容影响。

    Args:
        entries: 条目列表。
        wrapper_name: 包裹名称（默认"补充内容"）。

    Returns:
        包含开包裹和闭包裹的条目列表。
        若已存在或全静态则返回空列表。

    Notes:
        幂等：若已有补充包裹条目则跳过创建。
        包裹风格根据全书 XML 标签与 Markdown 标题使用频率自动选择。
    """
    assert isinstance(entries, list)
    assert isinstance(wrapper_name, str) and wrapper_name
    existing = any(_is_existing_supplement(e, wrapper_name) for e in entries)
    if existing:
        return []
    has_dynamic = any(not wu.determine_static(e.get("content", "")) for e in entries)
    if not has_dynamic:
        return []

    style = _detect_wrapper_style(entries)
    if style == "xml":
        open_content = f"<{wrapper_name}>"
        close_content = f"</{wrapper_name}>"
    else:
        open_content = f"# {wrapper_name}开始"
        close_content = f"# {wrapper_name}结束"

    base = {
        "content": "", "comment": "", "constant": False,
        "key": [], "keysecondary": [],
        "position": 4, "depth": 0, "role": 1, "order": 0,
        "disable": False, "selective": True, "selectiveLogic": 0,
        "probability": 100, "useProbability": False,
        "sticky": 0, "cooldown": 0, "delay": 0,
        "scanDepth": None, "caseSensitive": None, "matchWholeWords": None,
        "useGroupScoring": None,
        "matchPersonaDescription": False, "matchCharacterDescription": False,
        "matchCharacterPersonality": False, "matchCharacterDepthPrompt": False,
        "matchScenario": False, "matchCreatorNotes": False,
        "excludeRecursion": False, "preventRecursion": False,
        "delayUntilRecursion": 0, "ignoreBudget": False,
        "group": "", "groupOverride": False, "groupWeight": 100,
        "outletName": "", "automationId": "", "vectorized": False,
        "addMemo": False, "triggers": [],
        "characterFilter": {"names": [], "tags": [], "isExclude": False},
        "displayIndex": None, "uid": None,
    }

    open_entry = dict(base)
    open_entry["content"] = open_content
    open_entry["comment"] = "[supplement-start]"
    open_entry["_is_supplement"] = True
    open_entry["_original_order"] = float("inf")

    close_entry = dict(base)
    close_entry["content"] = close_content
    close_entry["comment"] = "[supplement-end]"
    close_entry["_is_supplement"] = True
    close_entry["_original_order"] = float("inf")

    return [open_entry, close_entry]


def _prune_empty(entries: list[dict]) -> list[dict]:
    """删除无动态条目包裹的边界副本和补充包裹。

    分两步：
    1. 按 _pair_id 分组边界副本，检查组内开闭之间是否有动态条目。
       无动态则删除这对副本。
    2. 检查全书中是否有任何动态条目。无动态则删除所有补充包裹。

    Args:
        entries: 已排序的条目列表（含临时字段）。

    Returns:
        过滤后的新列表（不修改输入）。剩余补充包裹仍然成对。

    Notes:
        按 _pair_id 分组配对，不依赖排序后索引相邻。
        嵌套边界场景（如 <A><B>...</B></A>）下相邻索引配对会失效。
    """
    assert isinstance(entries, list)
    all_entries = list(entries)
    to_remove = set()

    from collections import defaultdict
    pair_groups = defaultdict(list)
    for idx, e in enumerate(all_entries):
        if e.get("_is_boundary_copy"):
            pair_groups[e["_pair_id"]].append(idx)

    # Loop invariant: 每组 indices 长度 == 2（开+闭），open_idx < close_idx
    for indices in pair_groups.values():
        if len(indices) != 2:
            continue
        open_idx, close_idx = sorted(indices)
        has_dynamic = any(
            not wu.determine_static(all_entries[j].get("content", ""))
            and not all_entries[j].get("_is_boundary_copy")
            and not all_entries[j].get("_is_supplement")
            for j in range(open_idx + 1, close_idx)
        )
        if not has_dynamic:
            to_remove.update([open_idx, close_idx])

    has_any_dynamic = any(
        not wu.determine_static(e.get("content", ""))
        and not e.get("_is_boundary_copy")
        for e in all_entries
    )
    if not has_any_dynamic:
        for idx, e in enumerate(all_entries):
            if e.get("_is_supplement"):
                to_remove.add(idx)

    return [e for idx, e in enumerate(all_entries) if idx not in to_remove]


def _apply_rules(entry: dict) -> None:
    """对单个条目应用字段修改规则。

    规则：
    - outlet（pos=7）：跳过所有规则，保持原值
    - 边界副本/补充包裹：constant=false, key=["/.*/"], pos=4, depth=0 等
    - 静态条目：constant=true, cooldown=0, useProbability=false 等
    - 动态条目：position=4, depth=0, role=1（其他字段保持原值）

    Args:
        entry: 条目 dict（就地修改）。

    Notes:
        就地修改 entry。
        弹出 _is_static、_is_boundary_copy、_is_supplement 临时字段。
        临时字段的清理由调用方在外部循环完成（_original_order, _pair_id）。
    """
    assert isinstance(entry, dict)
    is_static = entry.pop("_is_static", True)
    is_copy = entry.pop("_is_boundary_copy", False)
    is_supplement = entry.pop("_is_supplement", False)

    pos = entry.get("position", 0)

    if pos == 7:
        return

    if is_copy or is_supplement:
        entry["constant"] = False
        entry["position"] = 4
        entry["depth"] = 0
        entry["role"] = 1
        entry["key"] = ["/.*/"]
        entry["useProbability"] = False
        entry["probability"] = 100
        entry["cooldown"] = 0
        entry["sticky"] = 0
        entry["delay"] = 0
        return

    depth = entry.get("depth")

    if is_static:
        entry["constant"] = True
        entry["cooldown"] = 0
        entry["probability"] = 100
        entry["useProbability"] = False
        entry["sticky"] = 0
        entry["delay"] = 0

        if pos == 4 and depth is not None:
            if depth >= 10:
                entry["depth"] = 9999
            else:
                entry["depth"] = 0
            entry["role"] = 1
        elif pos == 4:
            entry["depth"] = 0
            entry["role"] = 1
    else:
        entry["position"] = 4
        entry["depth"] = 0
        entry["role"] = 1


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default=None)
    p.add_argument("-w", "--wrapper-name", default="补充内容")
    args = p.parse_args()
    out = run(args.input, args.output, args.wrapper_name)
    print(f"Reordered world book written to: {out}")
