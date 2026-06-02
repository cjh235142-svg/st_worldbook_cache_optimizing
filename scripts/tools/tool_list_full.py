import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, sort_entries


def run(
    input_path: str,
    output_path: str | None = None,
    max_len: int = 500,
    no_truncate: bool = False,
    filter_type: str | None = None,
) -> str:
    wb = load_world_book(input_path)
    entries = list(wb.get("entries", {}).values())

    for e in entries:
        e["_is_static"] = determine_static(e.get("content", ""))
        comment = e.get("comment", "")
        key = e.get("key", [])
        is_boundary_or_supp = "[boundary-copy-" in comment or "[supplement-" in comment
        is_wildcard = key == ["/.*/"]
        if is_boundary_or_supp or is_wildcard:
            e["_is_static"] = False

    if filter_type == "static":
        entries = [e for e in entries if e["_is_static"]]
    elif filter_type == "dynamic":
        entries = [e for e in entries if not e["_is_static"]]

    entries = sort_entries(entries)

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
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default=None)
    p.add_argument("--max-len", type=int, default=500)
    p.add_argument("--no-truncate", action="store_true")
    p.add_argument("--filter", default=None, choices=["static", "static-content", "dynamic"])
    args = p.parse_args()
    print(run(args.input, args.output, args.max_len, args.no_truncate, args.filter))
