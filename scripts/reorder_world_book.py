"""
Script 2: Reorder and reconfigure World Book entries for DeepSeek cache optimization.

Goal: immutable (non-EJS) entries first for cache hit, mutable (EJS) entries last.

Steps:
  1. Dense numbering: all entries sorted by (depth DESC, order ASC) -> order=0..T-1
  2. OFFSET = T
  3. Classify: EJS (comment ends with -EJS), non-EJS, bracket markers
  4. Apply field adjustments (constant, cooldown, position, depth, role)
  5. Identify bracket pairs, mark sectioned EJS entries
  6. non-EJS: keep order; EJS: order += OFFSET
  7. Create supplementary start/end entries for sections with EJS entries
  8. Final sort by (depth DESC, order ASC)
  9. Sync extensions sub-fields
"""

import sys
import os
import copy
import logging
from world_book_utils import (
    load_world_book,
    save_world_book,
    get_entries_sorted,
    set_entries_from_list,
    find_bracket_pairs,
    sync_extensions,
    log_info,
    log_warning,
    WARNING_COUNT,
    extract_heading_only,
    atdepth_sort_key,
    dense_sort_key,
    configure_logging,
    add_log_level_arg,
    default_output_path,
    POSITION,
    ROLE,
)

_log = logging.getLogger("reorder")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reorder World Book")
    parser.add_argument("input", help="Input JSON path")
    parser.add_argument("output", nargs="?", help="Output JSON path")
    add_log_level_arg(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    input_path = args.input
    output_path = args.output if args.output else default_output_path(input_path, "_reordered")

    log_info(f"加载文件: {input_path}")
    data = load_world_book(input_path)
    entries = get_entries_sorted(data)

    log_info(f"原始条目数: {len(entries)}")

    # === 未定义行为检查 (在密集编号前，检查原始数据) ===
    _check_order_collisions(entries)

    # === S1: 密集编号 ===
    entries.sort(key=dense_sort_key)
    for seq, entry in enumerate(entries):
        entry["order"] = seq
        entry["_seq"] = seq
    T = len(entries)
    log_info(f"密集编号: order=0..{T - 1}")

    # === S2: OFFSET ===
    OFFSET = T
    log_info(f"offset={OFFSET}")

    # === 分类 ===
    non_ejs = [e for e in entries if not e.get("comment", "").endswith("-EJS")]
    ejs_list = [e for e in entries if e.get("comment", "").endswith("-EJS")]

    log_info(f"Non-EJS: {len(non_ejs)}, EJS: {len(ejs_list)}")

    bracket_pairs = find_bracket_pairs(entries)
    log_info(f"识别到 {len(bracket_pairs)} 对 bracket 配对")

    # === S3: 字段调整 ===
    _apply_field_adjustments(non_ejs, ejs_list)
    log_info(f"字段调整: {len(non_ejs)} non-EJS, {len(ejs_list)} EJS")

    # === S4: order分配 ===
    for entry in ejs_list:
        entry["order"] += OFFSET

    # === S5: 补充条目 ===
    max_uid = max((e["uid"] for e in entries), default=0)
    supplements = _create_supplement_entries(entries, ejs_list, bracket_pairs, OFFSET, max_uid)
    log_info(f"补充条目: {len(supplements)} 个")

    all_entries = entries + supplements

    # === S6: 最终排序 (depth>=10→最前, others→中间, depth<10→最后) ===
    all_entries.sort(key=atdepth_sort_key)

    # === S7: 同步extensions ===
    for entry in all_entries:
        sync_extensions(entry)

    log_info(f"最终条目数: {len(all_entries)}")
    log_info(f"最终排序按 (band, pos, -depth(仅atDepth), order)")

    if WARNING_COUNT > 0:
        log_info(f"警告总数: {WARNING_COUNT}")

    # === S8: uid 对齐为 dict key, 清理内部标记, 写入 ===
    for i, entry in enumerate(all_entries):
        entry["uid"] = i

    # 移除内部追踪字段
    for entry in all_entries:
        entry.pop("_orig_uid", None)
        entry.pop("_seq", None)

    set_entries_from_list(data, all_entries)
    save_world_book(output_path, data)
    log_info(f"写入: {output_path}")


def _check_order_collisions(entries: list):
    seen = {}
    for e in entries:
        pos = e.get("position", 0)
        depth = e.get("depth", 0)
        order = e.get("order", 0)
        # For position!=4, depth is irrelevant; same order = collision
        collision_key = (pos, depth if pos == POSITION["atDepth"] else None, order)
        if collision_key in seen:
            prev = seen[collision_key]
            log_warning(
                f"order碰撞: pos={pos}, depth={collision_key[1]}, order={order} | "
                f'uid={prev["uid"]} "{prev.get("comment","")}" vs '
                f'uid={e["uid"]} "{e.get("comment","")}"'
            )
        seen[collision_key] = e


def _apply_field_adjustments(non_ejs: list, ejs_list: list):
    for entry in non_ejs:
        # Skip supplementary entries — they have their own settings
        if "补充开始" in entry.get("comment", "") or "补充结束" in entry.get("comment", ""):
            continue

        entry["constant"] = True
        entry["cooldown"] = 0
        entry["probability"] = 100
        entry["useProbability"] = True
        entry["selective"] = True

        if entry.get("position", 0) == POSITION["atDepth"]:
            orig_depth = entry.get("depth", 0)
            if orig_depth < 10:
                entry["depth"] = 0
            else:
                entry["depth"] = 9999
            entry["role"] = ROLE["USER"]
        else:
            # Non-atDepth: ensure role is not null
            entry["role"] = entry.get("role") or ROLE["SYSTEM"]

    for entry in ejs_list:
        entry["position"] = POSITION["atDepth"]
        entry["depth"] = 0
        entry["role"] = ROLE["USER"]


def _create_supplement_entries(
    entries: list, ejs_list: list, bracket_pairs: list, offset: int, start_uid: int
) -> list:
    supplements = []
    uid = start_uid + 1

    for start_entry, end_entry in bracket_pairs:
        start_order = start_entry.get("order", start_entry.get("_seq", 0))
        end_order = end_entry.get("order", end_entry.get("_seq", 0))

        section_ejs = [
            e
            for e in ejs_list
            if start_order < e.get("_seq", e.get("order", 0)) < end_order
        ]

        section_name = start_entry.get("comment", "").replace("开始", "")

        if not section_ejs:
            log_info(f'Section "{section_name}": 无EJS条目，跳过')
            continue

        min_seq = min(e.get("_seq", e.get("order", 0)) for e in section_ejs)
        max_seq = max(e.get("_seq", e.get("order", 0)) for e in section_ejs)

        if min_seq <= start_order or max_seq >= end_order:
            log_warning(
                f'Section "{section_name}": EJS条目的_seq ({min_seq}-{max_seq}) '
                f"不在bracket范围 ({start_order}-{end_order}) 内，跳过补充条目创建"
            )
            continue

        supp_start = copy.deepcopy(start_entry)
        supp_start["uid"] = uid
        uid += 1
        supp_start["comment"] = f"{section_name}补充开始"
        supp_start["constant"] = False
        supp_start["selective"] = True
        supp_start["key"] = ["/.+/"]
        supp_start["selectiveLogic"] = 0
        supp_start["position"] = POSITION["atDepth"]
        supp_start["depth"] = 0
        supp_start["role"] = ROLE["USER"]
        supp_start["probability"] = 100
        supp_start["useProbability"] = True
        supp_start["order"] = offset + (min_seq - 1)
        supp_start["content"] = extract_heading_only(start_entry.get("content", ""), section_name)
        _log.debug("supp_start content: %s → %s", section_name, repr(supp_start["content"]))
        supplements.append(supp_start)

        supp_end = copy.deepcopy(end_entry)
        supp_end["uid"] = uid
        uid += 1
        supp_end["comment"] = f"{section_name}补充结束"
        supp_end["constant"] = False
        supp_end["selective"] = True
        supp_end["key"] = ["/.+/"]
        supp_end["selectiveLogic"] = 0
        supp_end["position"] = POSITION["atDepth"]
        supp_end["depth"] = 0
        supp_end["role"] = ROLE["USER"]
        supp_end["probability"] = 100
        supp_end["useProbability"] = True
        supp_end["order"] = offset + (max_seq + 1)
        supp_end["content"] = extract_heading_only(end_entry.get("content", ""), section_name)
        supplements.append(supp_end)

        log_info(f'Section "{section_name}": {len(section_ejs)} 个EJS条目 -> 创建补充条目')

    return supplements



if __name__ == "__main__":
    main()
