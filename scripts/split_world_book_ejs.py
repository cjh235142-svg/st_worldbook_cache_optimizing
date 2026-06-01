"""
Script 1: Split World Book entries by EJS script presence.

Splits entries containing <%_ %> EJS tags into two:
- Non-EJS entry (keeps original comment)
- EJS entry (original comment + "-EJS")

Split at Markdown heading boundaries. EJS if/else blocks are kept intact.
All fields except uid/comment/content are inherited from parent.
Entries without EJS scripts remain unchanged.
"""

import sys
import os
import re
import copy
import logging
from world_book_utils import (
    load_world_book,
    save_world_book,
    get_entries_sorted,
    set_entries_from_list,
    parse_ejs_regions,
    find_markdown_headings,
    log_info,
    log_warning,
    WARNING_COUNT,
    configure_logging,
    add_log_level_arg,
    default_output_path,
)

_log = logging.getLogger("split")
_db = lambda msg, *a: _log.debug(msg, *a)


def process_entry(entry: dict, new_entries: list, max_uid: int) -> int:
    content = entry.get("content", "")
    if not content:
        return max_uid

    if "<%_" not in content:
        return max_uid

    comment = entry.get("comment", f"uid={entry['uid']}")
    _db('处理条目 uid=%s "%s": 含EJS', entry["uid"], comment)

    ejs_regions = parse_ejs_regions(content)
    if not ejs_regions:
        log_warning(f'条目 uid={entry["uid"]} "{comment}": 检测到<%_但无有效EJS区域')
        return max_uid

    # Rule: only split if first non-empty line is a heading (XML or Markdown).
    # EJS-start or non-heading → rename only.
    first_line = ""
    for raw_line in content.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        first_line = stripped
        break
    is_xml = bool(re.match(r"^<([\w\u4e00-\u9fff]+)>", first_line))
    is_md = first_line.startswith("#")
    if first_line.startswith("<%_") or (not is_xml and not is_md):
        entry["comment"] = comment + "-EJS"
        _db('  -> 首行非标题/EJS，全EJS: "%s"', entry["comment"])
        return max_uid

    # Step 1: Split content by EJS region boundaries
    # Build a mask: True = inside EJS region, False = non-EJS
    ejs_mask = [False] * len(content)
    for start, end in ejs_regions:
        # Clamp to content length
        clamped_end = min(end, len(content))
        for i in range(start, clamped_end):
            ejs_mask[i] = True

    # Step 2: Find all headings (both inside and outside EJS regions)
    all_headings = find_markdown_headings(content)

    # Step 3: Reconstruct segments respecting both EJS mask AND headings
    non_ejs_parts = []
    ejs_parts = []
    current = 0

    # Collect all split points: heading starts + EJS region transitions
    split_points = set()
    split_points.add(0)
    split_points.add(len(content))
    for h in all_headings:
        split_points.add(h["start"])
    for start, end in ejs_regions:
        split_points.add(start)
        split_points.add(min(end, len(content)))

    sorted_points = sorted(split_points)

    for i in range(len(sorted_points) - 1):
        seg_start = sorted_points[i]
        seg_end = sorted_points[i + 1]
        if seg_start >= seg_end:
            continue

        text = content[seg_start:seg_end]
        if not text.strip():
            # Preserve empty segments that are structural (heading-only)
            continue

        # Determine if this segment is inside EJS
        # Use the first character's mask status
        is_ejs = False
        if seg_start < len(ejs_mask):
            is_ejs = ejs_mask[seg_start]

        if is_ejs:
            ejs_parts.append(text)
        else:
            non_ejs_parts.append(text)

    non_ejs_content = "".join(non_ejs_parts).strip() if non_ejs_parts else ""
    ejs_content = "".join(ejs_parts).strip() if ejs_parts else ""

    # Already an -EJS entry or comment already suffixed — skip
    if comment.endswith("-EJS"):
        _db('  跳过: comment 已以 -EJS 结尾')
        return max_uid

    if not non_ejs_content:
        entry["comment"] = comment + "-EJS"
        xml_tag = _detect_xml_tag(content)
        if xml_tag:
            entry["content"] = _wrap_xml_supplement(xml_tag, content)
        _db('  -> 全EJS，重命名: "%s"', entry["comment"])
        return max_uid

    xml_tag = _detect_xml_tag(content)

    entry["content"] = non_ejs_content

    max_uid += 1
    new_entry = copy.deepcopy(entry)
    new_entry["uid"] = max_uid
    new_entry["comment"] = comment + "-EJS"

    if xml_tag:
        new_entry["content"] = f"<{xml_tag}补充>\n{ejs_content}\n</{xml_tag}补充>"
    else:
        new_entry["content"] = ejs_content

    new_entries.append(new_entry)
    _db('  -> 拆分: non-EJS(uid=%s), EJS(uid=%s)', entry["uid"], max_uid)
    return max_uid


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Split EJS entries")
    parser.add_argument("input", help="Input JSON path")
    parser.add_argument("output", nargs="?", help="Output JSON path")
    add_log_level_arg(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    input_path = args.input
    output_path = args.output if args.output else default_output_path(input_path, "_split")

    log_info(f"加载文件: {input_path}")
    data = load_world_book(input_path)

    entries = get_entries_sorted(data)
    total = len(entries)
    log_info(f"总条目数: {total}")

    max_uid = max((e["uid"] for e in entries), default=0)
    new_entries = []
    renamed = 0

    for entry in entries:
        old_comment = entry.get("comment", "")
        old_has_ejs = "<%_" in entry.get("content", "")
        prev_uid = max_uid
        max_uid = process_entry(entry, new_entries, max_uid)
        if max_uid > prev_uid:
            pass  # 新增了EJS条目
        elif old_has_ejs and entry["comment"].endswith("-EJS"):
            renamed += 1

    entries.extend(new_entries)
    new_count = len(new_entries)

    log_info(f"拆分完成: 新增 {new_count} 个-EJS条目, 重命名 {renamed} 个条目")
    log_info(f"最终条目数: {len(entries)}")

    if WARNING_COUNT > 0:
        log_info(f"警告总数: {WARNING_COUNT}")

    set_entries_from_list(data, entries)
    save_world_book(output_path, data)
    log_info(f"写入: {output_path}")


def _detect_xml_tag(content: str):
    """If content is wrapped in <Tag>...</Tag>, return tag name; else None."""
    lines = content.strip().split("\n")
    if not lines:
        return None
    first = lines[0].strip()
    last = lines[-1].strip()
    m_open = re.match(r"^<([\w\u4e00-\u9fff]+)>", first)
    m_close = re.match(r"^</([\w\u4e00-\u9fff]+)>", last)
    if m_open and m_close and m_open.group(1) == m_close.group(1):
        return m_open.group(1)
    return None


def _wrap_xml_supplement(tag: str, content: str) -> str:
    """Replace <Tag>...</Tag> wrapping with <Tag补充>...</Tag补充>."""
    inner = content.strip()
    # Strip existing tag wrappers
    lines = inner.split("\n")
    if lines:
        first = lines[0].strip()
        last = lines[-1].strip()
        if re.match(r"^<[\w\u4e00-\u9fff]+>", first):
            lines = lines[1:]
        if lines and re.match(r"^</[\w\u4e00-\u9fff]+>", last):
            lines = lines[:-1]
    inner = "\n".join(lines).strip()
    return f"<{tag}补充>\n{inner}\n</{tag}补充>"



if __name__ == "__main__":
    main()
