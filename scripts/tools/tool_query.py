"""跨产物查询、过滤、验证工具。

支持按条目类型（static/dynamic/boundary/supplement/merged）、
order 范围、文本搜索筛选条目，支持 CSV 输出和产物完整性验证。

Usage:
    python -m scripts.tools.tool_query -i <产物.json> [--filter TYPE] [--order-range N M]
                                         [--search TEXT] [--csv] [--summary-only] [--verify]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import world_book_utils as wu


def _classify_entry_type(entry: dict) -> str:
    """返回条目的类型标签：static / dynamic / boundary / supplement / merged。"""
    comment = entry.get("comment", "")
    if comment.startswith("合并:"):
        return "merged"
    if "[boundary-copy-" in comment:
        return "boundary"
    if "[supplement-" in comment:
        return "supplement"
    if wu.determine_static(entry.get("content", "")):
        return "static"
    return "dynamic"


def run(input_path: str, filter_type: str | None = None,
        order_range: tuple[int, int] | None = None, search: str | None = None,
        fmt: str = "table", summary_only: bool = False,
        verify: bool = False) -> str:
    """执行查询。

    Args:
        input_path: 任意管线产物 JSON 路径。
        filter_type: 筛选类型，None 表示全部。
        order_range: (min, max) order 范围。
        search: 文本搜索关键词。
        fmt: "table" 或 "csv"。
        summary_only: 只输出统计数字。
        verify: 执行产物完整性验证。

    Returns:
        输出文本。
    """
    with open(input_path, "r", encoding="utf-8") as f:
        wb = json.load(f)
    entries_data = wb.get("entries", {})
    if isinstance(entries_data, dict):
        entries = list(entries_data.values())
    elif isinstance(entries_data, list):
        entries = entries_data
    else:
        entries = []

    if verify:
        issues = _verify(entries)
        if issues:
            return "\n".join(issues)
        return "✓ 产物完整性验证通过"

    filtered = []
    for e in entries:
        etype = _classify_entry_type(e)

        if filter_type and etype != filter_type:
            continue

        if order_range:
            o = e.get("order", -1)
            if o < order_range[0] or o > order_range[1]:
                continue

        if search:
            comment = e.get("comment", "")
            content = e.get("content", "")
            if search not in comment and search not in content:
                continue

        filtered.append(e)

    filtered.sort(key=lambda x: x.get("order", 0))

    if summary_only:
        return _build_summary(filtered, entries, filter_type)

    if fmt == "csv":
        return _format_csv(filtered)

    return _format_table(filtered, filter_type)


def _build_summary(filtered: list[dict], all_entries: list[dict], filter_type: str | None) -> str:
    """输出统计摘要。"""
    if filter_type is None:
        counts = {t: 0 for t in ("static", "dynamic", "boundary", "supplement", "merged")}
        for e in all_entries:
            t = _classify_entry_type(e)
            counts[t] = counts.get(t, 0) + 1

        orders = sorted(e.get("order", 0) for e in all_entries)
        uids = sorted(e.get("uid", 0) for e in all_entries)
        total = len(all_entries)

        parts = [f"total={total}"]
        for t in ("static", "dynamic", "boundary", "supplement", "merged"):
            if counts[t]:
                parts.append(f"{t}={counts[t]}")
        if orders:
            o_cont = orders == list(range(len(orders)))
            parts.append(f"order: min={orders[0]} max={orders[-1]} continuous={'yes' if o_cont else 'no'}")
        if uids:
            u_cont = uids == list(range(len(uids)))
            parts.append(f"uid: min={uids[0]} max={uids[-1]} continuous={'yes' if u_cont else 'no'}")

        temp = ['_is_static', '_original_order', '_is_boundary_copy', '_is_supplement']
        found = False
        for e in all_entries:
            if any(f in e for f in temp):
                found = True
                break
        parts.append(f"temp_field_residue: {'found!' if found else 'none'}")

        return "  ".join(parts)

    orders = sorted(e.get("order", 0) for e in filtered)
    total = len(filtered)
    o_cont = orders == list(range(total)) if orders else True
    parts = [f"total={total}"]

    if any('[boundary-copy-' in e.get('comment','') for e in filtered):
        parts.append(f"boundary={sum(1 for e in filtered if '[boundary-copy-' in e.get('comment',''))}")
    if any('[supplement-' in e.get('comment','') for e in filtered):
        parts.append(f"supplement={sum(1 for e in filtered if '[supplement-' in e.get('comment',''))}")
    if orders:
        parts.append(f"order: {orders[0]}..{orders[-1]}")

    return "  ".join(parts)


def _format_csv(entries: list[dict]) -> str:
    """CSV 格式输出。"""
    lines = ["order,pos,depth,type,constant,disable,uid,comment"]
    for e in entries:
        lines.append(
            f"{e.get('order','')},{e.get('position','')},{e.get('depth','')},"
            f"{_classify_entry_type(e)},"
            f"{'✓' if e.get('constant') else '✗'},"
            f"{'✓' if e.get('disable') else '✗'},"
            f"{e.get('uid','')},{e.get('comment','')}"
        )
    return "\n".join(lines)


def _format_table(entries: list[dict], filter_type: str | None) -> str:
    """表格格式输出。"""
    lines = []
    lines.append(f"{'#':>4}  {'Order':>5}  {'Pos':>3}  {'Depth':>5}  {'Type':>10}  {'Const':>6}  {'Dis':>4}  {'UID':>4}  Comment")
    lines.append("─" * 100)
    for idx, e in enumerate(entries):
        etype = _classify_entry_type(e)
        is_c = "✓" if e.get("constant") else "✗"
        is_d = "✓" if e.get("disable") else "✗"
        lines.append(
            f"{idx:>4}  {e.get('order',0):>5}  {e.get('position',0):>3}  "
            f"{str(e.get('depth','')):>5}  {etype:>10}  {is_c:>6}  {is_d:>4}  "
            f"{e.get('uid',''):>4}  {e.get('comment','')}"
        )

    type_counts = {}
    for e in entries:
        t = _classify_entry_type(e)
        type_counts[t] = type_counts.get(t, 0) + 1
    parts = [f"{k}={v}" for k, v in sorted(type_counts.items())]
    lines.append("─" * 100)
    lines.append(f"Total: {len(entries)} entries ({', '.join(parts)})")
    return "\n".join(lines)


def _verify(entries: list[dict]) -> list[str]:
    """产物完整性验证。"""
    issues = []

    if not entries:
        return ["✗ 条目列表为空"]

    orders = sorted(e.get("order", -1) for e in entries)
    if orders[0] != 0 or orders[-1] != len(entries) - 1:
        issues.append(f"✗ order 不连续: 范围 {orders[0]}..{orders[-1]}, 条目数 {len(entries)}")
    elif orders != list(range(len(entries))):
        issues.append(f"✗ order 不连续: {orders[:10]}...")

    uids = sorted(e.get("uid", -1) for e in entries)
    if uids != list(range(len(entries))):
        issues.append(f"✗ uid 不连续")

    temp = ['_is_static', '_original_order', '_is_boundary_copy', '_is_supplement', '_pair_id']
    for e in entries:
        for f in temp:
            if f in e:
                issues.append(f"✗ 临时字段 '{f}' 残留 uid={e.get('uid')}")
                break

    static_max = -1
    dynamic_min = len(entries)
    for e in entries:
        o = e.get("order", 0)
        if _classify_entry_type(e) in ("boundary", "supplement", "dynamic"):
            if o < dynamic_min:
                dynamic_min = o
        else:
            if o > static_max:
                static_max = o
    if static_max >= 0 and dynamic_min < len(entries) and static_max > dynamic_min:
        issues.append(f"✗ 静态条目 (max order={static_max}) 未全部排在动态条目 (min order={dynamic_min}) 之前")

    if not issues:
        issues.append("✓ 产物完整性验证通过")

    return issues


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Cross-artifact world book query tool")
    p.add_argument("-i", "--input", required=True, help="Pipeline product JSON")
    p.add_argument("--filter", default=None,
                   choices=["static", "dynamic", "boundary", "supplement", "merged"],
                   help="Filter by entry type")
    p.add_argument("--order-range", nargs=2, type=int, metavar=("N", "M"),
                   help="Order range filter (inclusive)")
    p.add_argument("--search", default=None, help="Text search in comment/content")
    p.add_argument("--csv", action="store_true", help="CSV output")
    p.add_argument("--summary-only", action="store_true", help="Statistics only")
    p.add_argument("--verify", action="store_true", help="Verify artifact integrity")
    args = p.parse_args()

    fmt = "csv" if args.csv else "table"
    order_range = (args.order_range[0], args.order_range[1]) if args.order_range else None

    print(run(args.input, args.filter, order_range, args.search, fmt,
              args.summary_only, args.verify))
