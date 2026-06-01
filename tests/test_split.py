"""
Test 1: Validate split World Book format and correctness.
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
        print("Usage: python test_split.py <split_output.json>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    log_info(f"Test 1: 验证拆分后世界书 — {path}")

    passed = 0
    failed = 0

    data = load_world_book(path)
    entries = get_entries_sorted(data)

    # 1.1: entries 为合法 dict
    if isinstance(data.get("entries"), dict):
        passed += 1
        log_info("PASS 1.1: entries 为合法 dict")
    else:
        failed += 1
        print("FAIL 1.1: entries 不是 dict", file=sys.stderr)

    # 1.2: originalData 结构完整
    if "originalData" in data:
        od = data["originalData"]
        if isinstance(od, dict) and "name" in od and "entries" in od:
            passed += 1
            log_info("PASS 1.2: originalData 结构完整")
        else:
            failed += 1
            print("FAIL 1.2: originalData 结构不完整", file=sys.stderr)
    else:
        log_info("SKIP 1.2: 无 originalData")
        passed += 1

    # 1.3: 每条目必含 uid, comment, content
    missing = []
    for e in entries:
        for f in ("uid", "comment", "content"):
            if f not in e:
                missing.append(f"uid={e.get('uid','?')} 缺 {f}")
    if not missing:
        passed += 1
        log_info("PASS 1.3: 所有条目录含 uid/comment/content")
    else:
        failed += 1
        for m in missing:
            print(f"FAIL 1.3: {m}", file=sys.stderr)

    # 1.5: -EJS 条目 content 全部含 <%_
    ejs_clean = []
    for e in entries:
        if e.get("comment", "").endswith("-EJS"):
            if "<%_" not in e.get("content", ""):
                ejs_clean.append(f"uid={e['uid']} \"{e.get('comment','')}\" 不含EJS标签")
    if not ejs_clean:
        passed += 1
        log_info("PASS 1.5: -EJS 条目全部含 <%_")
    else:
        failed += 1
        for m in ejs_clean:
            print(f"FAIL 1.5: {m}", file=sys.stderr)

    # 1.6: Non-EJS 条目 content 不含 <%_
    non_ejs_polluted = []
    for e in entries:
        if not e.get("comment", "").endswith("-EJS"):
            if "<%_" in e.get("content", ""):
                non_ejs_polluted.append(f'uid={e["uid"]} "{e.get("comment","")}" 含EJS标签')
    if not non_ejs_polluted:
        passed += 1
        log_info("PASS 1.6: Non-EJS 条目不含 <%_")
    else:
        failed += 1
        for m in non_ejs_polluted:
            print(f"FAIL 1.6: {m}", file=sys.stderr)

    # 1.8: EJS条目 if/else 块 brace 配对
    ejs_entries = [e for e in entries if e.get("comment", "").endswith("-EJS")]
    brace_issues = []
    for e in ejs_entries:
        content = e.get("content", "")
        depth = 0
        for ch in content:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    depth = 0
        if depth != 0:
            brace_issues.append(f'uid={e["uid"]} "{e.get("comment","")}" brace不平衡: {depth}')
    if not brace_issues:
        passed += 1
        log_info("PASS 1.8: EJS brace配对完整")
    else:
        failed += 1
        for m in brace_issues:
            print(f"FAIL 1.8: {m}", file=sys.stderr)

    print(f"\n=== Test 1 结果: {passed} passed, {failed} failed, {WARNING_COUNT} warnings ===", file=sys.stderr)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
