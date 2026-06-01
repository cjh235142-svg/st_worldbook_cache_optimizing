"""
Test 4: Validate synced originalData correctness and consistency.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from world_book_utils import (
    load_world_book,
    get_entries_sorted,
    log_info,
    WARNING_COUNT,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_sync.py <synced_output.json>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    log_info(f"Test 4: 验证同步后世界书 — {path}")

    passed = 0
    failed = 0

    data = load_world_book(path)

    if "originalData" not in data:
        log_info("SKIP: 无 originalData")
        return

    od = data["originalData"]
    st_entries = list(data.get("entries", {}).values())
    od_entries = od.get("entries", [])

    # 4.1: originalData.entries 数量 == entries 数量
    if len(od_entries) == len(st_entries):
        passed += 1
        log_info(f"PASS 4.1: originalData({len(od_entries)}) == ST({len(st_entries)})")
    else:
        failed += 1
        print(f"FAIL 4.1: originalData({len(od_entries)}) != ST({len(st_entries)})",
              file=sys.stderr)

    # 4.2: 每个 ST entry.uid 在 originalData 中有对应 id
    od_by_id = {}
    for e in od_entries:
        od_by_id[e.get("id")] = e

    missing = []
    for st in st_entries:
        if st["uid"] not in od_by_id:
            missing.append(f'uid={st["uid"]} "{st.get("comment","")}"')
    if not missing:
        passed += 1
        log_info("PASS 4.2: 所有 ST uid 在 originalData 中有对应")
    else:
        failed += 1
        for m in missing:
            print(f"FAIL 4.2: {m}", file=sys.stderr)

    # 4.3: 关键字段映射
    field_errors = []
    for st in st_entries:
        if st["uid"] in od_by_id:
            od_e = od_by_id[st["uid"]]
            # keys
            st_keys = st.get("key", [])
            od_keys = od_e.get("keys", [])
            if st_keys != od_keys:
                field_errors.append(f'uid={st["uid"]} key: ST={st_keys} vs originalData={od_keys}')
            # comment
            st_comment = st.get("comment", "")
            od_comment = od_e.get("comment", "")
            if st_comment != od_comment:
                field_errors.append(
                    f'uid={st["uid"]} comment: ST="{st_comment}" vs originalData="{od_comment}"'
                )
            # content
            st_content = st.get("content", "")
            od_content = od_e.get("content", "")
            if st_content != od_content:
                field_errors.append(f'uid={st["uid"]} content mismatch')
            # constant
            st_const = st.get("constant", False)
            od_const = od_e.get("constant", False)
            if st_const != od_const:
                field_errors.append(f'uid={st["uid"]} constant: ST={st_const} vs originalData={od_const}')

    if not field_errors:
        passed += 1
        log_info("PASS 4.3: 关键字段映射正确")
    else:
        failed += 1
        for m in field_errors[:10]:
            print(f"FAIL 4.3: {m}", file=sys.stderr)
        if len(field_errors) > 10:
            print(f"  ... 共 {len(field_errors)} 个错误", file=sys.stderr)

    # 4.4: enabled == !disable
    enabled_errors = []
    for st in st_entries:
        if st["uid"] in od_by_id:
            od_e = od_by_id[st["uid"]]
            expected = not st.get("disable", False)
            actual = od_e.get("enabled", True)
            if expected != actual:
                enabled_errors.append(
                    f'uid={st["uid"]} enabled: expected={expected} actual={actual}'
                )
    if not enabled_errors:
        passed += 1
        log_info("PASS 4.4: enabled == !disable")
    else:
        failed += 1
        for m in enabled_errors[:5]:
            print(f"FAIL 4.4: {m}", file=sys.stderr)

    # 4.5: originalData.name 未被修改 (无法验证原始值，仅检查存在)
    if "name" in od:
        passed += 1
        log_info(f'PASS 4.5: originalData.name="{od["name"]}"')
    else:
        failed += 1
        print("FAIL 4.5: originalData.name 不存在", file=sys.stderr)

    print(
        f"\n=== Test 4 结果: {passed} passed, {failed} failed, {WARNING_COUNT} warnings ===",
        file=sys.stderr,
    )
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
