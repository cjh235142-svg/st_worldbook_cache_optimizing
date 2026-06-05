import json
import re
from datetime import datetime
from pathlib import Path

from . import world_book_utils as wu


def run(input_path: str, output_path: str | None = None) -> str:
    """执行条目分析：遍历世界书条目，判定三态并检测拆分边界。

    处理流程：
    1. 加载世界书 JSON
    2. 遍历每条 entry，调用 classify_entry 判定 is_static/is_mixed
    3. 对混合条目检测拆分边界（基于 Markdown 标题和 XML 闭标签）
    4. 输出分析 JSON（含 suggested_split、split_boundaries 等）

    Args:
        input_path: 世界书 JSON 文件路径。
        output_path: 输出路径，None 时自动生成为 {原名}_analysis.json。

    Returns:
        分析结果 JSON 文件的路径。

    Notes:
        备份由 run_pipeline.py 在入口统一执行，本函数不自备份。
        不修改原始世界书文件。
    """
    assert input_path is not None
    assert Path(input_path).exists()
    input_path = str(Path(input_path).resolve())
    src = Path(input_path)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_analysis.json")
    output_path = str(Path(output_path).resolve())

    wb = wu.load_world_book(input_path)
    ref_path = str(Path(input_path).resolve())
    src = Path(ref_path)

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
        is_outlet = wu.is_outlet_entry(entry)
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
            if wu.is_ejs_unclosed(content):
                suggested_split = False
            else:
                boundaries = _detect_split_boundaries(content, ejs_ranges)
                if boundaries is None:
                    suggested_split = False

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
    """检测混合条目的拆分边界。

    以 Markdown 标题（#/##）作为候选边界，过滤被 EJS 复合块
    覆盖的段落，再在 XML 闭标签处二次切分，最后分配 wrap_tag。

    Args:
        content: 条目的 content 文本。
        compound_ranges: EJS 复合块的行范围，为 None 时视为空。

    Returns:
        list[dict] 每个段落的信息（type/start_line/end_line/is_dynamic/wrap_tag），
        若无可拆分边界返回 None。

    Notes:
        wrap_tag 根据 outermost_tag 分配，闭标签之后的段落不包裹。
    """
    assert isinstance(content, str)
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
            if sl == el and wu._is_line_in_ranges(sl, all_ranges):
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
    """扫描 content 中所有独立成行的闭标签行号。

    仅匹配整行仅含 </tagname>（前后可有空白）的闭标签。
    用于将已按 heading 切好的段落在此处再次切分。

    Args:
        content: 条目 content 文本。

    Returns:
        闭标签行号列表（0-based，递增排序）。

    Notes:
        仅匹配已在 find_xml_tags 中识别出的标签的闭标签。
    """
    assert isinstance(content, str)
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
    """在闭标签行处切分已有边界段落。

    遍历闭标签行号，对包含该行的段落一分为二。
    支持递归嵌套：多个闭标签行依次处理。

    Args:
        boundaries: _detect_split_boundaries 输出的边界列表。
        close_lines: _find_all_close_lines 输出的闭标签行号。

    Returns:
        切分后的新边界列表。

    Notes:
        不修改输入列表，返回新列表。
    """
    assert isinstance(boundaries, list)
    assert isinstance(close_lines, list)
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
    """为每个边界段落分配 wrap_tag。

    闭标签行之后的段落 wrap_tag=None（不包裹最外层标签），
    之前的段落 wrap_tag=tag（将被包裹在最外层标签内）。

    Args:
        boundaries: 边界列表（就地修改）。
        tag: 最外层标签名，None 表示无标签。
        close_line: 最后一个闭标签行号，None 表示无闭标签。

    Notes:
        就地修改 boundaries。
        若 tag=None 或 close_line=None，所有段落 wrap_tag=tag（即 None）。
    """
    assert isinstance(boundaries, list)
    for b in boundaries:
        if tag and close_line is not None and b["start_line"] > close_line:
            b["wrap_tag"] = None
        else:
            b["wrap_tag"] = tag


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args()
    out = run(args.input, args.output)
    print(f"Analysis written to: {out}")
