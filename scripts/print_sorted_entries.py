"""
Print all World Book entries (name + content) in sort order.

Usage:
  python scripts/print_sorted_entries.py <input.json> [output.txt]
"""

import sys
import os
from world_book_utils import load_world_book, get_entries_sorted, atdepth_sort_key


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <input.json> [output.txt]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    data = load_world_book(input_path)
    entries = get_entries_sorted(data)
    entries.sort(key=atdepth_sort_key)

    SEP = "=" * 70
    lines = []
    for i, entry in enumerate(entries):
        tags = []
        if entry.get("constant"):
            tags.append("蓝")
        else:
            tags.append("绿")
        c = entry.get("comment", "")
        if c.endswith("-EJS"):
            tags.append("EJS")
        if "补充开始" in c or "补充结束" in c:
            tags.append("SUPP")
        elif c.endswith("开始") or c.endswith("结束"):
            tags.append("BRACKET")
        if entry.get("disable"):
            tags.append("禁用")

        tag_str = "[" + "][".join(tags) + "]" if tags else ""

        header = (
            f"{SEP}\n"
            f"#{i:>3}  uid={entry['uid']:>5}  depth={entry.get('depth','?'):>5}  "
            f"order={entry.get('order','?'):>5}  pos={entry.get('position','?'):>2}  "
            f"{tag_str}\n"
            f"  comment: {c}"
        )
        lines.append(header)
        content = entry.get("content", "")
        if content:
            lines.append(f"  content:")
            for cl in content.split("\n"):
                lines.append(f"    | {cl}")
        else:
            lines.append(f"  content: (empty)")

    lines.append(SEP)
    result = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Written to {output_path}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
