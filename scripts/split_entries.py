import json
from copy import deepcopy
from pathlib import Path

from . import world_book_utils as wu


def run(world_book_path: str, analysis_path: str, output_path: str | None = None) -> str:
    wb_path = str(Path(world_book_path).resolve())
    src = Path(wb_path)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_split.json")
    output_path = str(Path(output_path).resolve())

    wb = wu.load_world_book(wb_path)
    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    uid_map = {a["uid"]: a for a in analysis.get("entries", [])}
    entries_data = wb.get("entries", {})
    original_entries = list(entries_data.items())

    new_entries = []
    for key, entry in original_entries:
        uid = entry.get("uid", int(key) if key.isdigit() else 0)
        ae = uid_map.get(uid)
        if ae is None or not ae.get("suggested_split"):
            new_entries.append(dict(entry))
            continue

        boundaries = ae.get("split_boundaries")
        if not boundaries:
            new_entries.append(dict(entry))
            continue

        is_dynamic_values = {b.get("is_dynamic") for b in boundaries}
        if len(is_dynamic_values) <= 1:
            new_entries.append(dict(entry))
            continue

        content = entry.get("content", "")
        lines = content.splitlines(keepends=True)
        outermost_tag = wu.find_outermost_xml_tag(content)

        static_segments = []
        dynamic_segments = []

        for b in boundaries:
            sl, el = b["start_line"], b["end_line"]
            segment = "".join(lines[sl:el+1])
            if wu._is_empty_or_heading_only(segment):
                continue
            if b["is_dynamic"]:
                dynamic_segments.append(segment)
            else:
                static_segments.append(segment)

        if not static_segments or not dynamic_segments:
            new_entries.append(dict(entry))
            continue

        def _wrap(segments, tag):
            body = "\n\n".join(segments)
            if tag:
                return f"<{tag}>\n{body}\n</{tag}>"
            return body

        base = {k: v for k, v in entry.items()
                if k not in ("uid", "content", "comment")}
        base.setdefault("displayIndex", None)

        se = dict(base)
        se["uid"] = None
        se["content"] = _wrap(static_segments, outermost_tag)
        se["comment"] = f"{entry.get('comment','')} [split-static]".strip()

        de = dict(base)
        de["uid"] = None
        de["content"] = _wrap(dynamic_segments, outermost_tag)
        de["comment"] = f"{entry.get('comment','')} [split-dynamic]".strip()

        new_entries.extend([se, de])

    new_entries = wu.reassign_uids(new_entries)
    wu.save_world_book(new_entries, output_path)
    return output_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--world-book", required=True)
    p.add_argument("--analysis", required=True)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    out = run(args.world_book, args.analysis, args.output)
    print(f"Split world book written to: {out}")
