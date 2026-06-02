import json
import re
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

        static_boundaries = []
        dynamic_boundaries = []

        for b in boundaries:
            sl, el = b["start_line"], b["end_line"]
            segment = "".join(lines[sl:el+1])
            if wu._is_empty_or_heading_only(segment):
                continue
            if b["is_dynamic"]:
                dynamic_boundaries.append((segment, b))
            else:
                static_boundaries.append((segment, b))

        static_segments = [s for s, _ in static_boundaries]
        dynamic_segments = [s for s, _ in dynamic_boundaries]

        if not static_segments or not dynamic_segments:
            new_entries.append(dict(entry))
            continue

        base = {k: v for k, v in entry.items()
                if k not in ("uid", "content", "comment")}
        base.setdefault("displayIndex", None)

        se = dict(base)
        se["uid"] = None
        se["content"] = _build_content(static_boundaries)
        se["comment"] = f"{entry.get('comment','')} [split-static]".strip()

        de = dict(base)
        de["uid"] = None
        de["content"] = _build_content(dynamic_boundaries)
        de["comment"] = f"{entry.get('comment','')} [split-dynamic]".strip()

        new_entries.extend([se, de])

    new_entries = wu.reassign_uids(new_entries)
    wu.save_world_book(new_entries, output_path)
    return output_path


def _build_content(boundaries: list[tuple[str, dict]]) -> str:
    by_tag = {}   # tag -> list of stripped segments
    unwrapped = []
    for segment, b in boundaries:
        tag = b.get("wrap_tag")
        s = _strip_all_standalone_tag_lines(segment)
        if tag:
            by_tag.setdefault(tag, []).append(s)
        else:
            unwrapped.append(s)
    parts = []
    for tag, segments in by_tag.items():
        parts.append(f"<{tag}>\n" + "\n\n".join(segments) + f"\n</{tag}>")
    if unwrapped:
        parts.append("\n\n".join(unwrapped))
    return "\n\n".join(parts)


_XML_TAG_LINE_RE = re.compile(r"^\s*</?[\u4e00-\u9fff\w]+>\s*$\n?", flags=re.MULTILINE)


def _strip_all_standalone_tag_lines(segment: str) -> str:
    return _XML_TAG_LINE_RE.sub("", segment)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", dest="world_book", required=True)
    p.add_argument("-a", "--analysis", required=True)
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args()
    out = run(args.world_book, args.analysis, args.output)
    print(f"Split world book written to: {out}")
