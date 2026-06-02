import json
import re
from datetime import datetime
from pathlib import Path

from . import world_book_utils as wu


def run(input_path: str, output_path: str | None = None) -> str:
    input_path = str(Path(input_path).resolve())
    src = Path(input_path)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_analysis.json")
    output_path = str(Path(output_path).resolve())

    wb = wu.load_world_book(input_path)
    ref_path = str(Path(input_path).resolve())
    src = Path(ref_path)
    is_pipeline_product = any(
        src.stem.endswith(suffix)
        for suffix in ("_analysis", "_split", "_reordered", "_merged")
    )
    if not is_pipeline_product:
        wu.backup_file(input_path)

    entries_data = wb.get("entries", {})
    if isinstance(entries_data, list):
        entries_data = {str(i): e for i, e in enumerate(entries_data)}
    entry_list = list(entries_data.items())

    analysis_entries = []
    static_count = 0
    dynamic_count = 0
    mixed_count = 0

    for key, entry in entry_list:
        uid = entry.get("uid", int(key) if key.isdigit() else 0)
        comment = entry.get("comment", "")
        content = entry.get("content", "")
        is_outlet = entry.get("position") == 7
        has_plugin = wu.has_special_plugin(content, comment)

        is_static, is_mixed = wu.classify_entry(content)
        markers = wu.detect_markers(content)

        if is_outlet or has_plugin:
            suggested_split = False
            is_mixed = False
        else:
            suggested_split = is_mixed

        if is_static and not is_mixed:
            static_count += 1
        elif not is_static and not is_mixed:
            dynamic_count += 1
        else:
            mixed_count += 1

        ejs_ranges = wu.find_ejs_compound_ranges(content) if is_mixed else None
        boundaries = None
        if is_mixed and suggested_split:
            boundaries = _detect_split_boundaries(content, ejs_ranges)

        analysis_entries.append({
            "uid": uid,
            "comment": comment,
            "is_static": is_static,
            "is_mixed": is_mixed,
            "detected_markers": markers,
            "suggested_split": suggested_split,
            "ejs_compound_ranges": ejs_ranges if ejs_ranges else None,
            "split_boundaries": boundaries,
        })

    result = {
        "source": src.name,
        "generated_at": datetime.now().isoformat(),
        "entries": analysis_entries,
        "summary": {
            "total": len(entry_list),
            "static": static_count,
            "dynamic": dynamic_count,
            "mixed": mixed_count,
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return output_path


def _detect_split_boundaries(content: str, compound_ranges: list | None) -> list[dict] | None:
    lines = content.splitlines(keepends=True)
    headings = wu.split_by_headings(content)
    compound_ranges = compound_ranges or []
    all_ranges = list(compound_ranges)

    outermost_tag = wu.find_outermost_xml_tag(content)
    close_lines = _find_all_close_lines(content)

    boundaries = []
    for seg in headings:
        sl = seg["start_line"]
        el = seg["end_line"]
        if wu._is_line_in_ranges(sl, all_ranges) or wu._is_line_in_ranges(el, all_ranges):
            if sl == el and all(wu._is_line_in_ranges(sl, all_ranges) for _ in [sl]):
                seg_text = "".join(lines[sl:el+1])
                is_dyn = len(wu.detect_markers(seg_text)) > 0
                boundaries.append({
                    "type": "heading",
                    "heading_level": seg.get("heading_level"),
                    "heading_text": seg.get("heading_text", ""),
                    "start_line": sl,
                    "end_line": el,
                    "is_dynamic": is_dyn,
                })
            else:
                boundaries.append({
                    "type": "heading",
                    "heading_level": seg.get("heading_level"),
                    "heading_text": seg.get("heading_text", ""),
                    "start_line": sl,
                    "end_line": el,
                    "is_dynamic": True,
                })
        else:
            seg_text = "".join(lines[sl:el+1])
            is_dyn = len(wu.detect_markers(seg_text)) > 0
            boundaries.append({
                "type": "heading",
                "heading_level": seg.get("heading_level"),
                "heading_text": seg.get("heading_text", ""),
                "start_line": sl,
                "end_line": el,
                "is_dynamic": is_dyn,
            })

    if close_lines:
        boundaries = _split_at_close_lines(boundaries, close_lines)
    _assign_wrap_tags(boundaries, outermost_tag, close_lines[-1] if close_lines else None)

    is_dynamic_values = {b["is_dynamic"] for b in boundaries}
    if not boundaries or len(is_dynamic_values) <= 1:
        return None

    return boundaries


def _find_all_close_lines(content: str) -> list[int]:
    all_tags = wu.find_xml_tags(content)
    if not all_tags:
        return []
    close_re = re.compile(r"^\s*</([\u4e00-\u9fff\w]+)>\s*$")
    result = []
    seen = set()
    for i, line in enumerate(content.splitlines(keepends=True)):
        m = close_re.match(line)
        if m and m.group(1) in {t["tag"] for t in all_tags} and i not in seen:
            result.append(i)
            seen.add(i)
    return sorted(result)


def _split_at_close_lines(boundaries: list[dict], close_lines: list[int]) -> list[dict]:
    for line_no in close_lines:
        new_boundaries = []
        for b in boundaries:
            sl, el = b["start_line"], b["end_line"]
            if sl <= line_no < el:
                new_boundaries.append({
                    **{k: v for k, v in b.items()},
                    "end_line": line_no,
                })
                new_boundaries.append({
                    **{k: v for k, v in b.items()},
                    "start_line": line_no + 1,
                })
            else:
                new_boundaries.append(b)
        boundaries = new_boundaries
    return boundaries


def _assign_wrap_tags(boundaries: list[dict], tag: str | None, close_line: int | None) -> None:
    for b in boundaries:
        if tag and close_line is not None and b["start_line"] > close_line:
            b["wrap_tag"] = None
        else:
            b["wrap_tag"] = tag


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    out = run(args.input, args.output)
    print(f"Analysis written to: {out}")
