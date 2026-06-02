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

    entries_data = wb.get("entries", {})
    if not isinstance(entries_data, dict):
        errors.append({"code": "A2", "level": "error", "scope": "file",
                        "uid": None, "message": "entries is not a dict"})
        return _build_result(src.name, errors, warnings)

    entries = [(k, e) for k, e in entries_data.items()]

    for key, entry in entries:
        uid = entry.get("uid")
        if str(uid) != key:
            errors.append({"code": "A3", "level": "error", "scope": "entry",
                            "uid": uid, "key": key,
                            "message": f"uid={uid} != entries key={key}"})
        if "content" not in entry:
            errors.append({"code": "A4", "level": "error", "scope": "entry",
                            "uid": uid, "message": "content field missing"})
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
    scope = "assembled" if uid is None else "entry"
    open_tags = [t for t in re.findall(r"<([\u4e00-\u9fff\w]+)>", content)
                 if t not in _FALSE_POSITIVE_TAGS]
    close_tags = [t for t in re.findall(r"</([\u4e00-\u9fff\w]+)>", content)
                  if t not in _FALSE_POSITIVE_TAGS]

    from collections import Counter
    oc = Counter(open_tags)
    cc = Counter(close_tags)
    for tag in oc:
        if oc[tag] > cc.get(tag, 0):
            errors.append({"code": "C1", "level": "error", "scope": scope,
                            "uid": uid, "message": f"XML tag <{tag}> unclosed"})
    for tag in cc:
        if cc[tag] > oc.get(tag, 0):
            errors.append({"code": "C2", "level": "error", "scope": scope,
                            "uid": uid, "message": f"XML tag </{tag}> has no open"})


def _check_macro_integrity(content, uid, warnings):
    scope = "assembled" if uid is None else "entry"
    opens = content.count("{{")
    closes = content.count("}}")
    if opens != closes:
        warnings.append({"code": "E1", "level": "warning", "scope": scope,
                          "uid": uid, "message": f"Macro brace mismatch: opens={opens}, closes={closes}"})


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
    if entry.get("depth") and entry.get("depth", 0) >= 10 and entry.get("position") != 4:
        warnings.append({"code": "F4", "level": "warning", "scope": "entry",
                          "uid": uid, "message": f"depth>=10 but position={pos} (depth only meaningful at pos=4)"})
    content = entry.get("content", "").strip()
    if not content:
        warnings.append({"code": "F5", "level": "warning", "scope": "entry",
                          "uid": uid, "message": "content is empty"})
    if content.strip() and determine_static(content) and "{{time}}" in content:
        warnings.append({"code": "F7", "level": "warning", "scope": "entry",
                          "uid": uid, "message": "static entry contains {{time}} macro (time-varying)"})

    order = entry.get("order")
    pos = entry.get("position")
    depth = entry.get("depth")
    if order is not None:
        group_key = (pos, depth)
        if not hasattr(_check_cache_rules, "_orders"):
            _check_cache_rules._orders = {}
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


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output-errors", default=None)
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    run(args.input, args.output_errors, args.strict)
