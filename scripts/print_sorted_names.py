"""
Debug utility: Print sorted entry names for visual comparison.

Outputs entry list sorted by (depth DESC, order ASC) with tags:
  [蓝] = constant entry
  [绿] = selective (non-constant)
  [EJS] = EJS entry
  [BRACKET] = section start/end marker
  [SUPP] = supplementary start/end marker
"""

import sys
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

    lines = []
    for entry in entries:
        tags = []
        if entry.get("constant"):
            tags.append("蓝")
        else:
            tags.append("绿")
        if entry.get("comment", "").endswith("-EJS"):
            tags.append("EJS")
        if "补充开始" in entry.get("comment", "") or "补充结束" in entry.get("comment", ""):
            tags.append("SUPP")
        elif entry.get("comment", "").endswith("开始") or entry.get("comment", "").endswith("结束"):
            tags.append("BRACKET")
        if entry.get("disable"):
            tags.append("禁用")

        tag_str = "[" + "][".join(tags) + "]" if tags else ""
        line = (
            f"uid={entry['uid']:>5} "
            f"depth={entry.get('depth','?'):>5} "
            f"order={entry.get('order','?'):>5} "
            f"pos={entry.get('position','?'):>2} "
            f"{tag_str:<20} "
            f"{entry.get('comment','')}"
        )
        lines.append(line)

    result = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Written to {output_path}", file=sys.stderr)

    print(result)


if __name__ == "__main__":
    main()
