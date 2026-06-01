"""
Test 2 & 3: Validate reordered World Book format, consistency, and correctness.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from world_book_utils import (
    load_world_book,
    get_entries_sorted,
    log_info,
    log_warning,
    WARNING_COUNT,
    POSITION,
    ROLE,
    atdepth_sort_key,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_reorder.py <reordered_output.json> [original_split.json]",
              file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    original_path = sys.argv[2] if len(sys.argv) > 2 else None

    log_info(f"Test 2&3: 验证重排序后世界书 — {path}")

    passed = 0
    failed = 0

    data = load_world_book(path)
    entries = get_entries_sorted(data)

    # --- Test 3: 合法性 ---

    # 3.1: entries 合法
    if isinstance(data.get("entries"), dict):
        passed += 1
        log_info("PASS 3.1: entries 为合法 dict")
    else:
        failed += 1
        print("FAIL 3.1: entries 不是 dict", file=sys.stderr)

    # 3.2: 所有 non-EJS, non-补充 条目 constant == True
    non_ejs_entries = [
        e for e in entries if not e.get("comment", "").endswith("-EJS")
    ]
    non_ejs_nonsupp = [
        e for e in non_ejs_entries
        if not ("补充开始" in e.get("comment", "") or "补充结束" in e.get("comment", ""))
    ]
    non_constant = [e for e in non_ejs_nonsupp if not e.get("constant")]
    if not non_constant:
        passed += 1
        log_info("PASS 3.2: 所有 non-EJS non-补充 条目 constant=True")
    else:
        failed += 1
        for e in non_constant:
            print(f'FAIL 3.2: uid={e["uid"]} "{e.get("comment","")}" constant=False',
                  file=sys.stderr)

    # 3.3: 所有 non-EJS non-补充 条目 cooldown == 0
    non_zero_cooldown = [e for e in non_ejs_nonsupp if e.get("cooldown", 0) != 0]
    if not non_zero_cooldown:
        passed += 1
        log_info("PASS 3.3: 所有 non-EJS 条目 cooldown=0")
    else:
        failed += 1
        for e in non_zero_cooldown:
            print(f'FAIL 3.3: uid={e["uid"]} "{e.get("comment","")}" cooldown!=0',
                  file=sys.stderr)

    # 3.4: 所有 non-EJS non-补充 条目 probability == 100
    non_100_prob = [e for e in non_ejs_nonsupp if e.get("probability") != 100]
    if not non_100_prob:
        passed += 1
        log_info("PASS 3.4: 所有 non-EJS 条目 probability=100")
    else:
        failed += 1
        for e in non_100_prob:
            print(f'FAIL 3.4: uid={e["uid"]} "{e.get("comment","")}" probability!=100',
                  file=sys.stderr)

    # 3.5: position=4 non-EJS depth 只能是 0 或 9999
    atdepth_non_ejs = [e for e in non_ejs_entries if e.get("position") == POSITION["atDepth"]]
    bad_depth = [e for e in atdepth_non_ejs if e.get("depth") not in (0, 9999)]
    if not bad_depth:
        passed += 1
        log_info("PASS 3.5: position=4 non-EJS depth in {0, 9999}")
    else:
        failed += 1
        for e in bad_depth:
            print(f'FAIL 3.5: uid={e["uid"]} depth={e.get("depth")}', file=sys.stderr)

    # 3.6: EJS 条目 position=4, depth=0, role=1
    ejs_entries = [e for e in entries if e.get("comment", "").endswith("-EJS")]
    bad_ejs = [
        e
        for e in ejs_entries
        if e.get("position") != POSITION["atDepth"]
        or e.get("depth") != 0
        or e.get("role") != ROLE["USER"]
    ]
    if not bad_ejs:
        passed += 1
        log_info("PASS 3.6: EJS 条目 position=4/depth=0/role=1")
    else:
        failed += 1
        for e in bad_ejs:
            print(
                f'FAIL 3.6: uid={e["uid"]} pos={e.get("position")} depth={e.get("depth")} role={e.get("role")}',
                file=sys.stderr,
            )

    # 3.7: 补充条目 constant=False, key 含 /.+/
    supp_entries = [
        e for e in entries if "补充开始" in e.get("comment", "") or "补充结束" in e.get("comment", "")
    ]
    bad_supp = [
        e
        for e in supp_entries
        if e.get("constant")
        or "/.+/" not in str(e.get("key", []))
        or e.get("selectiveLogic") != 0
    ]
    if not bad_supp:
        passed += 1
        log_info("PASS 3.7: 补充条目 constant=False, key含/.+/, selectiveLogic=0")
    else:
        failed += 1
        for e in bad_supp:
            print(f'FAIL 3.7: uid={e["uid"]} "{e.get("comment","")}"', file=sys.stderr)

    # 3.9: extensions 子字段与顶层一致
    ext_mismatch = []
    for e in entries:
        ext = e.get("extensions", {})
        if isinstance(ext, dict):
            for top_key in ("position", "depth", "role", "probability", "cooldown"):
                if top_key in e:
                    ext_key = (
                        "exclude_recursion"
                        if top_key == "excludeRecursion"
                        else top_key
                    )
                    if ext_key in ext and e[top_key] != ext[ext_key]:
                        ext_mismatch.append(
                            f'uid={e["uid"]} {top_key}: entry={e[top_key]} vs extensions={ext[ext_key]}'
                        )
    if not ext_mismatch:
        passed += 1
        log_info("PASS 3.9: extensions 与顶层一致")
    else:
        failed += 1
        for m in ext_mismatch:
            print(f"FAIL 3.9: {m}", file=sys.stderr)

    # 3.10: uid 与 entries dict key 一致
    uid_mismatch = []
    for i, e in enumerate(entries):
        if e.get("uid", -1) != i:
            uid_mismatch.append(
                f'index={i} uid={e.get("uid","?")} "{e.get("comment","")}"'
            )
    if not uid_mismatch:
        passed += 1
        log_info("PASS 3.10: uid 与 entries key 一致")
    else:
        failed += 1
        for m in uid_mismatch[:5]:
            print(f"FAIL 3.10: {m}", file=sys.stderr)
        if len(uid_mismatch) > 5:
            print(f"  ... 共 {len(uid_mismatch)} 条", file=sys.stderr)

    # --- Test 2: 相对顺序一致性 (需要原始文件) ---

    if original_path:
        orig_data = load_world_book(original_path)
        orig_entries = get_entries_sorted(orig_data)

        # 3.5b: 原始 non-EJS position=4 depth>=10 条目映射为 depth=9999
        orig_atdepth = [
            e for e in orig_entries
            if e.get("position") == POSITION["atDepth"]
            and e.get("depth", 0) >= 10
            and not e.get("comment", "").endswith("-EJS")
        ]
        if not orig_atdepth:
            log_info("SKIP 3.5b: 原始无 depth>=10 的 position=4 条目")
        else:
            deep_comments = {e.get("comment") for e in orig_atdepth}
            not_mapped = [
                e for e in entries
                if e.get("comment") in deep_comments and e.get("depth") != 9999
            ]
            if not not_mapped:
                passed += 1
                log_info(f"PASS 3.5b: 所有原始 depth>=10 条目映射为 depth=9999 ({len(deep_comments)} 条)")
            else:
                failed += 1
                for e in not_mapped:
                    print(
                        f'FAIL 3.5b: uid={e["uid"]} "{e.get("comment","")}"'
                        f' depth={e.get("depth")} (expected 9999)',
                        file=sys.stderr,
                    )

        # === 2.1: Non-EJS 条目在相同 (band, pos) 分区内严格顺序校验 ===
        # 规则: 同一分区内条目顺序必须与原始一致;
        #       仅当原始 (pos, depth, order) 完全相同时豁免(未定义行为)

        def _group_key(e):
            pos = e.get("position", 0)
            if pos == POSITION["atDepth"]:
                depth = e.get("depth", 0)
                band = 0 if depth >= 10 else 2
                return (band, pos)
            return (1, pos)

        supp_set = {e.get("comment", "") for e in supp_entries}
        orig_non = [e for e in orig_entries
                    if not e.get("comment", "").endswith("-EJS")
                    and e.get("comment") not in supp_set]
        new_non = [e for e in entries
                   if not e.get("comment", "").endswith("-EJS")
                   and e.get("comment") not in supp_set]

        orig_key_map = {}
        for e in orig_non:
            c = e.get("comment", "")
            orig_key_map[c] = (e.get("position", 0), e.get("depth", 0), e.get("order", 0))

        orig_grouped = {}
        for e in sorted(orig_non, key=lambda x: atdepth_sort_key(x, include_position=False)):
            orig_grouped.setdefault(_group_key(e), []).append(e.get("comment", ""))

        new_grouped = {}
        for e in sorted(new_non, key=lambda x: atdepth_sort_key(x, include_position=False)):
            new_grouped.setdefault(_group_key(e), []).append(e.get("comment", ""))

        group_failures = []
        for key in orig_grouped:
            olist = orig_grouped.get(key, [])
            nlist = new_grouped.get(key, [])
            if olist == nlist:
                continue
            for idx in range(min(len(olist), len(nlist))):
                if olist[idx] != nlist[idx]:
                    ok = orig_key_map.get(olist[idx], ())
                    nk = orig_key_map.get(nlist[idx], ())
                    if ok and nk and ok == nk:
                        log_warning(f"2.1 (undefined): '{olist[idx]}' vs '{nlist[idx]}' (同 key={ok})")
                    else:
                        group_failures.append(
                            f"group={key} idx={idx}: '{olist[idx]}' vs '{nlist[idx]}' orig={ok}!={nk}"
                        )
            if len(olist) > len(nlist):
                group_failures.append(f"group={key}: 缺失 {len(olist)-len(nlist)} 条")
            elif len(nlist) > len(olist):
                group_failures.append(f"group={key}: 多出 {len(nlist)-len(olist)} 条")

        if not group_failures:
            passed += 1
            log_info("PASS 2.1: Non-EJS 分区内顺序一致")
        else:
            failed += 1
            for v in group_failures[:5]:
                print(f"FAIL 2.1: {v}", file=sys.stderr)
            if len(group_failures) > 5:
                print(f"  ... 共 {len(group_failures)} 处", file=sys.stderr)

        # === 2.2: EJS 条目集合与顺序校验 ===
        # EJS 全部收敛到 pos=4/depth=0; 按原始分区比较顺序
        orig_ejs = [e for e in orig_entries if e.get("comment", "").endswith("-EJS")]
        new_ejs = [e for e in entries if e.get("comment", "").endswith("-EJS")]

        if not orig_ejs:
            log_info("SKIP 2.2: 原始文件无 EJS 条目")
        else:
            new_ejs_set = {e.get("comment") for e in new_ejs}
            lost = [e.get("comment") for e in orig_ejs if e.get("comment") not in new_ejs_set]
            if lost:
                failed += 1
                print(f"FAIL 2.2: {len(lost)} 个 EJS 条目丢失: {lost[:5]}", file=sys.stderr)
            else:
                # Group both by original (band, pos), compare comment order
                orig_ejs_key_map = {}
                for e in orig_ejs:
                    c = e.get("comment", "")
                    orig_ejs_key_map[c] = (e.get("position", 0), e.get("depth", 0), e.get("order", 0))

                orig_ejs_grouped = {}
                for e in sorted(orig_ejs, key=lambda x: atdepth_sort_key(x, include_position=False)):
                    orig_ejs_grouped.setdefault(_group_key(e), []).append(e.get("comment", ""))

                new_ejs_grouped = {}
                for e in sorted(new_ejs, key=lambda x: atdepth_sort_key(x, include_position=False)):
                    # All EJS are now pos=4. Use original key from comment lookup for grouping.
                    ok = orig_ejs_key_map.get(e.get("comment", ""), ())
                    if ok:
                        pos, depth, order = ok
                        if pos == POSITION["atDepth"]:
                            band = 0 if depth >= 10 else 2
                        else:
                            band, pos, depth = 1, pos, 0
                        new_ejs_grouped.setdefault((band, pos), []).append(e.get("comment", ""))

                ejs_failures = []
                for key in orig_ejs_grouped:
                    olist = orig_ejs_grouped.get(key, [])
                    nlist = new_ejs_grouped.get(key, [])
                    if olist == nlist:
                        continue
                    for idx in range(min(len(olist), len(nlist))):
                        if olist[idx] != nlist[idx]:
                            ok = orig_ejs_key_map.get(olist[idx], ())
                            nk = orig_ejs_key_map.get(nlist[idx], ())
                            if ok and nk and ok == nk:
                                log_warning(f"2.2 (undefined): '{olist[idx]}' vs '{nlist[idx]}' (同 key={ok})")
                            else:
                                ejs_failures.append(
                                    f"group={key} idx={idx}: '{olist[idx]}' vs '{nlist[idx]}' orig={ok}!={nk}"
                                )
                    if len(olist) > len(nlist):
                        ejs_failures.append(f"group={key}: 缺失 {len(olist)-len(nlist)} 条")
                    elif len(nlist) > len(olist):
                        ejs_failures.append(f"group={key}: 多出 {len(nlist)-len(olist)} 条")

                if not ejs_failures:
                    passed += 1
                    log_info("PASS 2.2: EJS 条目集合与分区顺序一致")
                else:
                    failed += 1
                    for v in ejs_failures[:5]:
                        print(f"FAIL 2.2: {v}", file=sys.stderr)
                    if len(ejs_failures) > 5:
                        print(f"  ... 共 {len(ejs_failures)} 处", file=sys.stderr)

        # 2.5: 所有 non-EJS non-补充 order < 所有 EJS order
        supp_uids = {e["uid"] for e in supp_entries}
        non_ejs_nonsupp_orders = [
            e.get("order", 0) for e in non_ejs_entries if e["uid"] not in supp_uids
        ]
        max_non_ejs_order = max(non_ejs_nonsupp_orders, default=-1)
        if ejs_entries:
            min_ejs_order = min(e.get("order", 0) for e in ejs_entries)
            if min_ejs_order > max_non_ejs_order:
                passed += 1
                log_info("PASS 2.5: non-EJS(sans supp) order < EJS order")
            else:
                failed += 1
                print(
                    f"FAIL 2.5: max(non-EJS order)={max_non_ejs_order}, min(EJS order)={min_ejs_order}",
                    file=sys.stderr,
                )
        else:
            log_info("SKIP 2.5: 无 EJS 条目")
    else:
        log_info("SKIP Test 2: 未提供原始文件，跳过顺序对比")

    print(
        f"\n=== Test 2&3 结果: {passed} passed, {failed} failed, {WARNING_COUNT} warnings ===",
        file=sys.stderr,
    )
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
