"""
Script 3: Synchronize entries back to originalData.

Maps ST internal format fields to originalData (character card) format
using the reverse of convertCharacterBook() + originalWIDataKeyMap.

Drops originalData entries whose uid no longer exists in ST entries.
Creates new originalData entries for ST entries without matches.
"""

import sys
import os
import copy
import logging
from world_book_utils import (
    load_world_book,
    save_world_book,
    get_entries_sorted,
    get_nested_value,
    set_nested_value,
    ST_TO_ORIGINAL_KEY_MAP,
    INVERT_MAP,
    log_info,
    WARNING_COUNT,
    configure_logging,
    add_log_level_arg,
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync originalData")
    parser.add_argument("input", help="Input JSON path")
    add_log_level_arg(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    input_path = args.input
    log_info(f"加载文件: {input_path}")
    data = load_world_book(input_path)

    st_entries = list(data.get("entries", {}).values())

    if "originalData" not in data:
        log_info("无 originalData, 跳过同步")
        return

    orig_data = data["originalData"]
    if "entries" not in orig_data or not isinstance(orig_data["entries"], list):
        log_info("originalData.entries 不存在或非数组, 跳过同步")
        return

    orig_entries = orig_data["entries"]
    log_info(f"ST entries: {len(st_entries)}, originalData entries: {len(orig_entries)}")

    # Build lookup: uid -> originalData index
    orig_by_uid = {}
    for i, oe in enumerate(orig_entries):
        orig_by_uid[oe.get("id")] = i

    st_uids = {e["uid"] for e in st_entries}

    updated = 0
    new_count = 0
    removed = 0

    # Update existing / create new
    for st in st_entries:
        uid = st["uid"]
        if uid in orig_by_uid:
            _st_to_original_update(st, orig_entries[orig_by_uid[uid]])
            updated += 1
        else:
            new_entry = _st_to_original_new(st)
            orig_entries.append(new_entry)
            new_count += 1
            log_info(f"新增 originalData: uid={uid}")

    # Remove deleted
    to_remove = [
        i for i, oe in enumerate(orig_entries) if oe.get("id") not in st_uids
    ]
    for i in reversed(to_remove):
        log_info(f"移除 originalData: id={orig_entries[i].get('id')}")
        del orig_entries[i]
        removed += 1

    log_info(f"同步完成: 更新 {updated} 条, 新增 {new_count} 条, 移除 {removed} 条")

    if WARNING_COUNT > 0:
        log_info(f"警告总数: {WARNING_COUNT}")

    save_world_book(input_path, data)
    log_info(f"覆盖写入: {input_path}")


def _st_to_original_update(st_entry: dict, orig_entry: dict):
    orig_entry["id"] = st_entry["uid"]
    orig_entry["enabled"] = not st_entry.get("disable", False)
    orig_entry["insertion_order"] = st_entry.get("order", 0)

    _simple_map(st_entry, orig_entry, "keys", "key")
    _simple_map(st_entry, orig_entry, "secondary_keys", "keysecondary")
    _simple_map(st_entry, orig_entry, "comment", "comment")
    _simple_map(st_entry, orig_entry, "content", "content")
    _simple_map(st_entry, orig_entry, "constant", "constant")
    _simple_map(st_entry, orig_entry, "selective", "selective")

    # Extensions sub-fields via ST_TO_ORIGINAL_KEY_MAP
    for st_key, orig_path in ST_TO_ORIGINAL_KEY_MAP.items():
        if st_key in st_entry:
            set_nested_value(orig_entry, orig_path, st_entry[st_key])
    for inverted, orig_name in INVERT_MAP.items():
        if inverted in st_entry:
            if orig_name not in ST_TO_ORIGINAL_KEY_MAP.values():
                orig_entry[orig_name] = not st_entry[inverted]

    # characterFilter -> character_filter (only update if already present, don't add to new)
    if "characterFilter" in st_entry:
        if "character_filter" in orig_entry:
            orig_entry["character_filter"] = copy.deepcopy(st_entry["characterFilter"])

    # Ensure extensions dict exists with defaults
    _ensure_extensions(orig_entry)

    # Top-level position string (before_char / after_char) for pos 0/1
    st_pos = st_entry.get("position", 1)
    if st_pos in (0, 1):
        orig_entry["position"] = "before_char" if st_pos == 0 else "after_char"


def _st_to_original_new(st_entry: dict) -> dict:
    orig = {
        "id": st_entry["uid"],
        "keys": st_entry.get("key", []),
        "secondary_keys": st_entry.get("keysecondary", []),
        "comment": st_entry.get("comment", ""),
        "content": st_entry.get("content", ""),
        "constant": st_entry.get("constant", False),
        "selective": st_entry.get("selective", True),
        "insertion_order": st_entry.get("order", 0),
        "enabled": not st_entry.get("disable", False),
        "position": "after_char",
        "use_regex": True,
        "extensions": {},
    }

    _ensure_extensions(orig)

    for st_key, orig_path in ST_TO_ORIGINAL_KEY_MAP.items():
        if st_key in st_entry:
            val = st_entry[st_key]
            # Never write null for role — use 0 instead
            if st_key == "role" and val is None:
                val = 0
            set_nested_value(orig, orig_path, val)

    for inverted, orig_name in INVERT_MAP.items():
        if inverted in st_entry:
            if orig_name not in ST_TO_ORIGINAL_KEY_MAP.values():
                orig[orig_name] = not st_entry[inverted]

    # Only add character_filter if the ST entry has non-empty filter
    cf = st_entry.get("characterFilter")
    if cf and (cf.get("names") or cf.get("tags") or cf.get("isExclude")):
        orig["character_filter"] = copy.deepcopy(cf)

    st_pos = st_entry.get("position", 1)
    if st_pos in (0, 1):
        orig["position"] = "before_char" if st_pos == 0 else "after_char"

    # Sync position into extensions.position too
    if "position" in st_entry:
        orig["extensions"]["position"] = st_entry["position"]

    return orig


def _simple_map(st_entry, orig_entry, orig_key, st_key):
    if st_key in st_entry:
        orig_entry[orig_key] = st_entry[st_key]


def _ensure_extensions(orig_entry: dict):
    if "extensions" not in orig_entry or not isinstance(orig_entry["extensions"], dict):
        orig_entry["extensions"] = {}
    ext = orig_entry["extensions"]
    ext.setdefault("position", orig_entry.get("position", 1) if isinstance(orig_entry.get("position"), int) else 1)
    ext.setdefault("exclude_recursion", False)
    ext.setdefault("display_index", 0)
    ext.setdefault("probability", 100)
    ext.setdefault("useProbability", True)
    ext.setdefault("depth", 4)
    ext.setdefault("selectiveLogic", 0)
    ext.setdefault("group", "")
    ext.setdefault("group_override", False)
    ext.setdefault("group_weight", 100)
    ext.setdefault("prevent_recursion", False)
    ext.setdefault("delay_until_recursion", False)
    ext.setdefault("scan_depth", None)
    ext.setdefault("match_whole_words", None)
    ext.setdefault("use_group_scoring", False)
    ext.setdefault("case_sensitive", None)
    ext.setdefault("automation_id", "")
    ext.setdefault("role", 0)
    ext.setdefault("vectorized", False)
    ext.setdefault("sticky", 0)
    ext.setdefault("cooldown", 0)
    ext.setdefault("delay", 0)
    ext.setdefault("match_persona_description", False)
    ext.setdefault("match_character_description", False)
    ext.setdefault("match_character_personality", False)
    ext.setdefault("match_character_depth_prompt", False)
    ext.setdefault("match_scenario", False)
    ext.setdefault("match_creator_notes", False)
    ext.setdefault("triggers", [])
    ext.setdefault("ignore_budget", False)
    ext.setdefault("outlet_name", "")


if __name__ == "__main__":
    main()
