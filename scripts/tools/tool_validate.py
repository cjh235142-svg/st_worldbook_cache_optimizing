import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, parse_content_blocks
from tools.tool_prompt import run as assemble_prompt

_FALSE_POSITIVE_TAGS = {
    "user", "char", "model", "group", "original",
    "br", "hr", "img", "input", "link", "meta",
    "span", "div", "p", "b", "i", "a",
    "content", "WritingStyle",
    "Variable_Format", "Update", "Update_Analysis",
    "json_patch", "status_current_variable", "Variable_Rules",
}


def run(input_path: str, output_errors: str | None = None,
        strict: bool = False) -> dict:
    src = Path(input_path)
    errors = []
    warnings = []

    try:
        wb = load_world_book(input_path)
    except FileNotFoundError:
        e = {"code": "A0", "level": "error", "scope": "file",
             "uid": None, "message": f"File not found: {input_path}"}
        errors.append(e)
        return _build_result(src.name, errors, warnings)
    except json.JSONDecodeError as ex:
        e = {"code": "A1", "level": "error", "scope": "file",
             "uid": None, "message": f"Invalid JSON: {ex}"}
        errors.append(e)
        return _build_result(src.name, errors, warnings)

    entries_data = wb.get("entries", {})
    if not isinstance(entries_data, dict):
        errors.append({"code": "A2", "level": "error", "scope": "file",
                        "uid": None, "message": "entries is not a dict"})
        return _build_result(src.name, errors, warnings)

    entries = [(k, e) for k, e in entries_data.items()]

    _check_cache_rules._orders = {}

    for key, entry in entries:
        uid = entry.get("uid")
        if str(uid) != key:
            errors.append({"code": "A3", "level": "error", "scope": "entry",
                            "uid": uid, "key": key,
                            "message": f"uid={uid} != entries key={key}"})
        if "content" not in entry:
            errors.append({"code": "A4", "level": "error", "scope": "entry",
                            "uid": uid, "message": "content field missing"})
        else:
            content = entry.get("content", "")
            clean = re.sub(r"</?[\u4e00-\u9fff\w]+>", "", content)
            clean = re.sub(r"^#{1,2}\s.*$", "", clean, flags=re.MULTILINE)
            if clean.strip() == "" and content.strip():
                warnings.append({"code": "D1", "level": "warning", "scope": "entry",
                                  "uid": uid,
                                  "message": "content only contains heading/tag, no body text"})
        if strict:
            _check_cache_rules(entry, uid, warnings)

    _check_cross_entry_md(entries, warnings)

    try:
        prompt_text = assemble_prompt(input_path, no_comments=True)
    except Exception as e:
        errors.append({"code": "P0", "level": "error", "scope": "file",
                        "uid": None, "message": f"Failed to assemble prompt: {e}"})
        result = _build_result(src.name, errors, warnings)
        if output_errors:
            with open(output_errors, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            _print_result(result)
        return result

    _check_ejs_integrity(prompt_text, None, errors)
    _check_xml_tags(prompt_text, None, errors)
    _check_macro_integrity(prompt_text, None, warnings)

    result = _build_result(src.name, errors, warnings)
    if output_errors:
        with open(output_errors, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        _print_result(result)

    return result


def _check_ejs_integrity(content, uid, errors):
    scope = "assembled" if uid is None else "entry"
    pos = 0
    while pos < len(content):
        idx = content.find("<%", pos)
        if idx == -1:
            break
        close = content.find("%>", idx + 2)
        if close == -1:
            line = content[:idx].count("\n") + 1
            errors.append({"code": "B1", "level": "error", "scope": scope,
                            "uid": uid, "message": f"EJS block not closed near line {line}"})
            break
        pos = close + 2

    blocks = parse_content_blocks(content)
    depth = 0
    for b in blocks:
        if b["type"] == "ejs":
            depth += b["brace_delta"]
    if depth != 0:
        errors.append({"code": "B2", "level": "error", "scope": scope,
                        "uid": uid, "message": f"EJS brace unbalanced: net={depth}"})


def _check_xml_tags(content, uid, errors):
    is_global = uid is None
    scope = "assembled" if is_global else "entry"
    code_unclosed = "C4" if is_global else "C1"
    code_no_open = "C5" if is_global else "C2"
    code_cross = "C3"

    _tag_re = re.compile(r"<(/?)([\u4e00-\u9fff\w]+)>")
    stack = []
    pos = 0
    while pos < len(content):
        m = _tag_re.search(content, pos)
        if not m:
            break
        is_close = bool(m.group(1))
        tag = m.group(2)
        if tag in _FALSE_POSITIVE_TAGS:
            pos = m.end()
            continue
        if not is_close:
            stack.append((tag, m.start()))
        else:
            found = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    found = i
                    break
            if found is not None:
                for j in range(len(stack) - 1, found, -1):
                    line_no = content[:stack[j][1]].count("\n") + 1
                    errors.append({"code": code_cross, "level": "error", "scope": scope,
                                    "uid": uid,
                                    "message": f"XML tag crossing: <{stack[j][0]}> not closed "
                                               f"before </{tag}> near line {line_no}"})
                stack.pop(found)
            else:
                errors.append({"code": code_no_open, "level": "error", "scope": scope,
                                "uid": uid, "message": f"XML tag </{tag}> has no open"})
        pos = m.end()

    for tag, start_pos in stack:
        line_no = content[:start_pos].count("\n") + 1
        errors.append({"code": code_unclosed, "level": "error", "scope": scope,
                        "uid": uid,
                        "message": f"XML tag <{tag}> unclosed near line {line_no}"})


def _check_macro_integrity(content, uid, warnings):
    scope = "assembled" if uid is None else "entry"
    opens = content.count("{{")
    closes = content.count("}}")
    if opens != closes:
        warnings.append({"code": "E1", "level": "warning", "scope": scope,
                          "uid": uid, "message": f"Macro brace mismatch: opens={opens}, closes={closes}"})
    for m in re.finditer(r"<%[-=](.*?)%>", content, re.DOTALL):
        ejs_body = m.group(1)
        if "{{" in ejs_body:
            warnings.append({"code": "E2", "level": "warning", "scope": scope,
                              "uid": uid,
                              "message": f"EJS output block contains nested macro: {m.group(0)[:60]}"})


def _check_cache_rules(entry, uid, warnings):
    if entry.get("constant") and entry.get("key"):
        warnings.append({"code": "F1", "level": "warning", "scope": "entry",
                          "uid": uid, "message": "constant=true but key is not empty"})
    if entry.get("useProbability") and entry.get("probability", 100) < 100:
        if determine_static(entry.get("content", "")):
            warnings.append({"code": "F2", "level": "warning", "scope": "entry",
                              "uid": uid, "message": "static entry with probability < 100"})
    pos = entry.get("position")
    if pos != 4 and determine_static(entry.get("content", "")) is False:
        warnings.append({"code": "F3", "level": "warning", "scope": "entry",
                          "uid": uid, "message": f"dynamic entry with position={pos} (expected 4)"})
    depth = entry.get("depth")
    if depth is not None and depth >= 10 and entry.get("position") != 4:
        warnings.append({"code": "F4", "level": "warning", "scope": "entry",
                          "uid": uid, "message": f"depth>=10 but position={pos} (depth only meaningful at pos=4)"})
    content = entry.get("content", "").strip()
    if not content:
        warnings.append({"code": "F5", "level": "warning", "scope": "entry",
                          "uid": uid, "message": "content is empty"})
    if content.strip() and determine_static(content) and "{{time}}" in content:
        warnings.append({"code": "F7", "level": "warning", "scope": "entry",
                          "uid": uid, "message": "static entry contains {{time}} macro (time-varying)"})

    # F8: self-closing tag (same <tag> at both start and end line)
    lines = entry.get("content", "").splitlines()
    if len(lines) >= 2:
        m1 = re.match(r'^<([\u4e00-\u9fff\w]+)>$', lines[0].strip())
        m2 = re.match(r'^<([\u4e00-\u9fff\w]+)>$', lines[-1].strip())
        if m1 and m2 and m1.group(1) == m2.group(1):
            tag = m1.group(1)
            if tag not in _FALSE_POSITIVE_TAGS:
                warnings.append({"code": "F8", "level": "warning", "scope": "entry",
                                  "uid": uid,
                                  "message": f"possible self-closing tag <{tag}> at both start and end, "
                                             f"should use <{tag}>...</{tag}>"})

    order = entry.get("order")
    pos = entry.get("position")
    depth = entry.get("depth")
    if order is not None:
        group_key = (pos, depth)
        if group_key not in _check_cache_rules._orders:
            _check_cache_rules._orders[group_key] = {}
        if order in _check_cache_rules._orders[group_key]:
            other_uid = _check_cache_rules._orders[group_key][order]
            warnings.append({"code": "F6", "level": "warning", "scope": "entry",
                              "uid": uid,
                              "message": f"order={order} duplicate with uid={other_uid} "
                                         f"in group (pos={pos}, depth={depth})"})
        else:
            _check_cache_rules._orders[group_key][order] = uid


def _check_cross_entry_md(entries, warnings):
    md_re = re.compile(r"^(#{1,2})\s+(.+?)(开始|结束|start|end|begin|close)\s*$")
    open_entries = {}
    close_entries = []
    for key, e in entries:
        content = e.get("content", "").strip()
        m = md_re.match(content)
        if m:
            base = m.group(2).strip()
            suffix = m.group(3)
            uid = e.get("uid")
            if suffix in ("开始", "start", "begin"):
                open_entries[base] = uid
            else:
                close_entries.append(base)
    for base in open_entries:
        if base not in close_entries:
            warnings.append({"code": "D2", "level": "warning", "scope": "cross-entry",
                              "uid": open_entries[base],
                              "message": f"MD boundary #{base}开始 has no matching end"})
    for base in close_entries:
        if base not in open_entries:
            warnings.append({"code": "D2", "level": "warning", "scope": "cross-entry",
                              "uid": None,
                              "message": f"MD boundary #{base}结束 has no matching start"})


def _build_result(source, errors, warnings):
    return {
        "source": source,
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _print_result(result):
    source = result["source"]
    errors = result["errors"]
    warnings = result["warnings"]
    print(f"{'='*60}")
    print(f"  World book validation: {source}")
    print(f"{'='*60}")
    if errors:
        print(f"\n[ERRORS] ({len(errors)}):")
        for e in errors:
            uid_label = "assembled" if e.get("uid") is None else f"uid={e['uid']}"
            print(f"  [{e['code']}] {uid_label}: {e['message']}")
    if warnings:
        print(f"\n[WARNINGS] ({len(warnings)}):")
        for w in warnings:
            uid_label = "assembled" if w.get("uid") is None else f"uid={w['uid']}"
            print(f"  [{w['code']}] {uid_label}: {w['message']}")
    print(f"\n{'─'*60}")
    print(f"  Result: {len(errors)} errors, {len(warnings)} warnings")
    print(f"  {'PASS' if result['pass'] else 'FAIL - not recommended to continue!'}")
    print(f"{'='*60}")


def _pipeline_check_single(entries: list[dict], source: str) -> dict:
    """对单个产物文件执行管线完整性检查。"""
    errors = []
    warnings = []

    if not entries:
        errors.append({"code": "P0", "level": "error", "scope": "file",
                        "uid": None, "message": "entries list is empty"})
        return _build_result(source, errors, warnings)

    orders = sorted(e.get("order", -1) for e in entries)
    if orders[0] != 0 or orders[-1] != len(entries) - 1:
        errors.append({"code": "P1", "level": "error", "scope": "file",
                        "uid": None,
                        "message": f"order not continuous: range {orders[0]}..{orders[-1]}, "
                                   f"expected 0..{len(entries) - 1}"})
    elif orders != list(range(len(entries))):
        errors.append({"code": "P1", "level": "error", "scope": "file",
                        "uid": None, "message": "order not continuous"})

    uids = sorted(e.get("uid", -1) for e in entries)
    if uids != list(range(len(entries))):
        errors.append({"code": "P2", "level": "error", "scope": "file",
                        "uid": None, "message": "uid not continuous"})

    temp_fields = ['_is_static', '_original_order', '_is_boundary_copy', '_is_supplement', '_pair_id']
    for e in entries:
        for f in temp_fields:
            if f in e:
                warnings.append({"code": "P3", "level": "warning", "scope": "entry",
                                  "uid": e.get("uid"),
                                  "message": f"temporary field '{f}' found"})
                break

    static_max = -1
    dynamic_min = len(entries)
    for e in entries:
        o = e.get("order", 0)
        comment = e.get("comment", "")
        if "[boundary-copy-" in comment or "[supplement-" in comment or not determine_static(e.get("content", "")):
            if o < dynamic_min:
                dynamic_min = o
        else:
            if o > static_max:
                static_max = o
    if static_max >= 0 and dynamic_min < len(entries) and static_max > dynamic_min:
        errors.append({"code": "P5", "level": "error", "scope": "file",
                        "uid": None,
                        "message": f"static entries (max order={static_max}) after "
                                   f"dynamic entries (min order={dynamic_min})"})

    return _build_result(source, errors, warnings)


def _pipeline_check_chain(pipeline_dir: str, pipeline_name: str) -> dict:
    """对整套产物链执行完整性检查。"""
    errors = []
    warnings = []

    dir_path = Path(pipeline_dir)
    suffixes = ["_analysis", "_split", "_reordered", "_merged"]
    files = {}
    all_exist = True
    for suf in suffixes:
        f = dir_path / f"{pipeline_name}{suf}.json"
        files[suf] = f
        if not f.exists():
            errors.append({"code": "C1", "level": "error", "scope": "file",
                            "uid": None, "message": f"missing: {f.name}"})
            all_exist = False

    if not all_exist:
        return _build_result(pipeline_name, errors, warnings)

    entry_counts = {}
    for suf in suffixes:
        with open(files[suf]) as f:
            data = json.load(f)
        ed = data.get("entries", {})
        if isinstance(ed, dict):
            entry_counts[suf] = len(ed)
        elif isinstance(ed, list):
            entry_counts[suf] = len(ed)
        else:
            entry_counts[suf] = 0

    if entry_counts["_split"] < entry_counts["_analysis"]:
        warnings.append({"code": "C2", "level": "warning", "scope": "file",
                          "uid": None,
                          "message": f"split ({entry_counts['_split']}) < analysis "
                                     f"({entry_counts['_analysis']})"})
    if entry_counts["_reordered"] < entry_counts["_split"]:
        warnings.append({"code": "C2", "level": "warning", "scope": "file",
                          "uid": None,
                          "message": f"reordered ({entry_counts['_reordered']}) < split "
                                     f"({entry_counts['_split']})"})
    if entry_counts["_merged"] > entry_counts["_reordered"]:
        warnings.append({"code": "C2", "level": "warning", "scope": "file",
                          "uid": None,
                          "message": f"merged ({entry_counts['_merged']}) > reordered "
                                     f"({entry_counts['_reordered']})"})

    backups = list(dir_path.glob(f"{pipeline_name}.backup_*"))
    if not backups:
        warnings.append({"code": "C3", "level": "warning", "scope": "file",
                          "uid": None, "message": "no backup file found"})

    result = _build_result(pipeline_name, errors, warnings)
    result["entry_counts"] = entry_counts
    result["backups"] = [str(b.name) for b in backups]
    return result


def _print_pipeline_result(result: dict) -> None:
    """打印管线检查结果。"""
    source = result["source"]
    entry_counts = result.get("entry_counts", {})
    backups = result.get("backups", [])
    errors = result["errors"]
    warnings = result["warnings"]

    print(f"{'=' * 60}")
    print(f"  Pipeline check: {source}")
    print(f"{'=' * 60}")

    if entry_counts:
        for suf in ["_analysis", "_split", "_reordered", "_merged"]:
            cnt = entry_counts.get(suf, "?")
            print(f"  {suf:15s}: {cnt} entries")
        print()

    if backups:
        for b in backups:
            print(f"  ✓ backup: {b}")
        print()

    if errors:
        for e in errors:
            print(f"  ✗ [{e['code']}] {e['message']}")
    if warnings:
        for w in warnings:
            print(f"  ⚠ [{w['code']}] {w['message']}")

    if not errors and not warnings:
        print(f"  ✓ All checks passed")

    print(f"\n{'─' * 60}")
    print(f"  Result: {len(errors)} errors, {len(warnings)} warnings")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", default=None,
                   help="Single artifact JSON for pipeline-check")
    p.add_argument("--pipeline-check", action="store_true",
                   help="Enable pipeline integrity check for single file")
    p.add_argument("--pipeline-dir", default=None,
                   help="Directory containing pipeline artifacts")
    p.add_argument("--pipeline-name", default=None,
                   help="Pipeline artifact filename prefix")
    p.add_argument("--output-errors", default=None)
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    if args.pipeline_dir and args.pipeline_name:
        result = _pipeline_check_chain(args.pipeline_dir, args.pipeline_name)
        _print_pipeline_result(result)
        if args.output_errors:
            with open(args.output_errors, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
    elif args.input and args.pipeline_check:
        wb = load_world_book(args.input)
        entries_data = wb.get("entries", {})
        entries = list(entries_data.values())
        src = Path(args.input).name
        result = _pipeline_check_single(entries, src)
        if args.output_errors:
            with open(args.output_errors, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            _print_pipeline_result(result)
    else:
        run(args.input, args.output_errors, args.strict)
