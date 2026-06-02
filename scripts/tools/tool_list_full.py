import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, sort_entries, override_entry_dynamic_status


def run(
    input_path: str,
    output_path: str | None = None,
    max_len: int = 500,
    no_truncate: bool = False,
    filter_type: str | None = None,
    uid: int | None = None,
    search: str | None = None,
) -> str:
    wb = load_world_book(input_path)
    raw_entries = list(wb.get("entries", {}).values())

    for e in raw_entries:
        e["_is_static"] = determine_static(e.get("content", ""))
        override_entry_dynamic_status(e)

    if uid is not None:
        raw_entries = [e for e in raw_entries if e.get("uid") == uid]
        if not raw_entries:
            return f"[NOT FOUND] No entry with uid={uid}"
    elif search is not None:
        search_lower = search.lower()
        raw_entries = [
            e for e in raw_entries
            if search_lower in e.get("comment", "").lower()
            or search_lower in e.get("content", "").lower()
        ]
        if not raw_entries:
            return f"[NOT FOUND] No entry matching \"{search}\""

    if filter_type == "static":
        raw_entries = [e for e in raw_entries if e["_is_static"]]
    elif filter_type == "static-content":
        raw_entries = [e for e in raw_entries if e["_is_static"]]
    elif filter_type == "dynamic":
        raw_entries = [e for e in raw_entries if not e["_is_static"]]

    entries = sort_entries(raw_entries)

    lines = []
    for idx, e in enumerate(entries):
        is_s = "✓" if e.get("_is_static") else "✗"
        is_c = "✓" if e.get("constant") else "✗"
        keys_str = ", ".join(e.get("key", [])) if e.get("key") else "--"

        lines.append("═" * 70)
        lines.append(
            f"[{idx}] UID={e.get('uid')}  Order={e.get('order',0)}  "
            f"Pos={e.get('position',0)}  Depth={e.get('depth','')}  "
            f"Static={is_s}  Constant={is_c}"
        )
        lines.append(f"    Comment: {e.get('comment','')}")
        lines.append(f"    Keys: {keys_str}")

        content = e.get("content", "")
        if no_truncate:
            label = "Content:"
        elif len(content) <= max_len:
            label = f"Content ({len(content)} chars):"
        else:
            label = f"Content preview ({max_len}/{len(content)} chars):"
            content = content[:max_len] + "...(truncated)"

        lines.append(f"    {label}")
        lines.append("─" * 70)
        lines.append(content)
        lines.append("")

    result = "\n".join(lines)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="List world book entries with full content")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--max-len", type=int, default=500)
    p.add_argument("--no-truncate", action="store_true")
    p.add_argument("--filter", default=None, choices=["static", "static-content", "dynamic"])
    p.add_argument("-u", "--uid", type=int, default=None, help="Show entry with given UID only")
    p.add_argument("-s", "--search", default=None, help="Search entries by comment or content")
    args = p.parse_args()
    print(run(args.input, args.output, args.max_len, args.no_truncate,
              args.filter, args.uid, args.search))
