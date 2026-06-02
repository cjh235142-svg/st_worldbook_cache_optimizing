import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, sort_entries


def run(input_path: str, fmt: str = "table", filter_type: str | None = None) -> str:
    wb = load_world_book(input_path)
    entries = list(wb.get("entries", {}).values())

    for e in entries:
        e["_is_static"] = determine_static(e.get("content", ""))

    if filter_type == "static":
        entries = [e for e in entries if e["_is_static"]]
    elif filter_type == "dynamic":
        entries = [e for e in entries if not e["_is_static"]]

    entries = sort_entries(entries)

    if fmt == "csv":
        lines = ["order,pos,depth,static,constant,uid,comment"]
        for e in entries:
            lines.append(
                f"{e.get('order','')},{e.get('position','')},{e.get('depth','')},"
                f"{'✓' if e.get('_is_static') else '✗'},"
                f"{'✓' if e.get('constant') else '✗'},"
                f"{e.get('uid','')},{e.get('comment','')}"
            )
        return "\n".join(lines)

    lines = []
    lines.append(f"{'Order':>5}  {'Pos':>3}  {'Depth':>5}  {'Static':>6}  {'Const':>6}  {'UID':>4}  Comment")
    lines.append("─" * 80)
    for e in entries:
        is_s = "✓" if e.get("_is_static") else "✗"
        is_c = "✓" if e.get("constant") else "✗"
        lines.append(
            f"{e.get('order',0):>5}  {e.get('position',0):>3}  "
            f"{str(e.get('depth','')):>5}  {is_s:>6}  {is_c:>6}  "
            f"{e.get('uid',''):>4}  {e.get('comment','')}"
        )

    static_count = sum(1 for e in entries if e.get("_is_static"))
    dynamic_count = len(entries) - static_count
    lines.append("─" * 80)
    lines.append(f"Summary: {len(entries)} entries ({static_count} static, {dynamic_count} dynamic)")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--csv", action="store_true")
    p.add_argument("--filter", default=None, choices=["static", "dynamic"])
    args = p.parse_args()
    fmt = "csv" if args.csv else "table"
    print(run(args.input, fmt, args.filter))
