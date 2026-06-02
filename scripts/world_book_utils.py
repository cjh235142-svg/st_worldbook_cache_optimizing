import json
import re
import shutil
from datetime import datetime
from pathlib import Path


DYNAMIC_MARKER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("<% if", re.compile(r"<%[-_]?\s*if\b")),
    ("<%=", re.compile(r"<%=")),
    ("<%-", re.compile(r"<%-")),
    ("<%", re.compile(r"<%(?![-=])\s*")),
    ("{{getvar::", re.compile(r"\{\{getvar::")),
    ("{{setvar::", re.compile(r"\{\{setvar::")),
    ("{{incvar::", re.compile(r"\{\{incvar::")),
    ("{{xbgetvar_yaml_idx::", re.compile(r"\{\{xbgetvar_yaml_idx::")),
    ("{{if", re.compile(r"\{\{if\b")),
    ("{{.", re.compile(r"\{\{\.")),
    ("{{$", re.compile(r"\{\{\$")),
    ("getvar(", re.compile(r"\bgetvar\(")),
    ("setvar(", re.compile(r"\bsetvar\(")),
    ("variables.", re.compile(r"\bvariables\.")),
    ("{{time}}", re.compile(r"\{\{time\}\}")),
    ("{{date}}", re.compile(r"\{\{date\}\}")),
    ("{{idleDuration}}", re.compile(r"\{\{idleDuration\}\}")),
    ("<state>", re.compile(r"<state>")),
]

STATIC_MACRO_NAMES = {"char", "user", "model", "group", "original"}
SPECIAL_PLUGIN_PREFIXES = [
    "[GENERATE:BEFORE]", "[GENERATE:AFTER]",
    "[RENDER:BEFORE]", "[RENDER:AFTER]",
    "[InitialVariables]",
]
SPECIAL_PLUGIN_DECORATORS = [
    "@@activate", "@@dont_activate", "@@generate_before", "@@generate_after",
    "@@render_before", "@@render_after", "@@preprocessing",
    "@@if", "@@private", "@@iframe", "@@message_formatting",
    "@@dont_preload", "@@always_enabled", "@@only_preload",
]

_POSITION_MAP = {0: "before", 1: "after", 2: "ANTop", 3: "ANBottom",
                 4: "atDepth", 5: "EMTop", 6: "EMBottom", 7: "outlet"}

def _strip_string_literals(code: str) -> str:
    result = []
    i = 0
    while i < len(code):
        c = code[i]
        if c in ("'", '"', '`'):
            delim = c
            i += 1
            while i < len(code):
                if code[i] == '\\':
                    i += 2
                elif code[i] == delim:
                    if delim == '`':
                        break
                    i += 1
                    break
                else:
                    i += 1
            result.append(' ')
        elif c == '/' and i + 1 < len(code) and code[i + 1] == '/':
            j = code.find('\n', i)
            if j == -1:
                j = len(code)
            result.append(' ' * (j - i))
            i = j
        elif c == '/' and i + 1 < len(code) and code[i + 1] == '*':
            j = code.find('*/', i + 2)
            if j == -1:
                j = len(code)
            result.append(' ' * (j - i + 2))
            i = j + 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def count_net_braces(ejs_code: str) -> int:
    clean = _strip_string_literals(ejs_code)
    return clean.count("{") - clean.count("}")


def detect_markers(content: str) -> list[str]:
    markers = []
    for name, pat in DYNAMIC_MARKER_PATTERNS:
        if pat.search(content):
            markers.append(name)
    return markers


def determine_static(content: str) -> bool:
    return len(detect_markers(content)) == 0


def has_special_plugin(content: str, comment: str = "") -> bool:
    for prefix in SPECIAL_PLUGIN_PREFIXES:
        if prefix in comment:
            return True
    if comment.startswith("@INJECT"):
        return True
    for dec in SPECIAL_PLUGIN_DECORATORS:
        if dec in content:
            return True
    return False


def _strip_ejs_blocks(content: str) -> str:
    return re.sub(r"<%[-_=]?.*?%>", "", content, flags=re.DOTALL)


def _strip_macros(content: str) -> str:
    return re.sub(r"\{\{.*?\}\}", "", content)


def _strip_ejs_and_macros(content: str) -> str:
    content = _strip_ejs_blocks(content)
    content = _strip_macros(content)
    return content


def parse_content_blocks(content: str) -> list[dict]:
    lines = content.splitlines(keepends=True)
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        ejs_begin = -1
        for keyword in ("<%_", "<%=", "<%-", "<%#", "<%"):
            idx = line.find(keyword)
            if idx != -1:
                if ejs_begin == -1 or idx < ejs_begin:
                    ejs_begin = idx
        if ejs_begin != -1:
            block_lines = []
            block_lines.append(line)
            if "%>" in line[ejs_begin + 2:]:
                body_start = ejs_begin + 2
                for kw in ("<%_", "<%=", "<%-", "<%#", "<%"):
                    if line[ejs_begin:].startswith(kw):
                        body_start = ejs_begin + len(kw)
                        break
                end_idx = line.rfind("%>", ejs_begin + 2)
                if end_idx != -1:
                    ejs_body = line[body_start:end_idx]
                else:
                    ejs_body = line[body_start:]
                blocks.append({"type": "ejs", "content": ejs_body.strip(),
                               "start_line": i, "end_line": i,
                               "brace_delta": count_net_braces(ejs_body)})
                i += 1
                continue
            else:
                j = i + 1
                while j < len(lines):
                    block_lines.append(lines[j])
                    if "%>" in lines[j]:
                        break
                    j += 1
                raw = "".join(block_lines)
                ejs_start = 0
                for kw in ("<%_", "<%=", "<%-", "<%#", "<%"):
                    idx2 = raw.find(kw)
                    if idx2 != -1:
                        ejs_start = idx2 + len(kw)
                        break
                ejs_end = raw.rfind("%>")
                if ejs_end == -1:
                    ejs_end = len(raw)
                ejs_body = raw[ejs_start:ejs_end]
                blocks.append({"type": "ejs", "content": ejs_body.strip(),
                               "start_line": i, "end_line": j,
                               "brace_delta": count_net_braces(ejs_body)})
                i = j + 1
                continue
        else:
            blocks.append({"type": "text", "content": line,
                           "start_line": i, "end_line": i, "brace_delta": 0})
            i += 1
    return blocks


def find_ejs_compound_ranges(content: str) -> list[tuple[int, int]]:
    lines = content.splitlines(keepends=True)
    blocks = parse_content_blocks(content)
    ranges = []
    depth = 0
    start = None
    for block in blocks:
        if block["type"] == "ejs":
            depth += block["brace_delta"]
            if depth > 0 and start is None:
                start = block["start_line"]
            if depth == 0 and start is not None:
                ranges.append((start, block["end_line"]))
                start = None
    if start is not None:
        ranges.append((start, max(len(lines) - 1, 0)))
    return ranges


def _content_fully_covered(content: str, compound_ranges: list[tuple[int, int]]) -> bool:
    lines = content.splitlines(keepends=True)
    if not lines:
        return True
    total = len(lines)
    covered = [False] * total
    for s, e in compound_ranges:
        for i in range(max(0, s), min(e + 1, total)):
            covered[i] = True
    return all(covered)


def _is_line_in_ranges(line_idx: int, ranges: list[tuple[int, int]]) -> bool:
    for s, e in ranges:
        if s <= line_idx <= e:
            return True
    return False


def classify_entry(content: str) -> tuple[bool, bool]:
    markers = detect_markers(content)
    if not markers:
        return (True, False)
    clean = _strip_ejs_and_macros(content).strip()
    if not clean:
        return (False, False)
    compound_ranges = find_ejs_compound_ranges(content)
    if compound_ranges and _content_fully_covered(content, compound_ranges):
        return (False, False)
    return (False, True)


def find_xml_tags(content: str) -> list[dict]:
    results = []
    tag_re = re.compile(r"<([\u4e00-\u9fff\w]+)>")
    close_re = re.compile(r"</([\u4e00-\u9fff\w]+)>")
    stack = []
    pos = 0
    while pos < len(content):
        m1 = tag_re.search(content, pos)
        m2 = close_re.search(content, pos)
        if m1 and (not m2 or m1.start() <= m2.start()):
            stack.append((m1.group(1), m1.start()))
            pos = m1.end()
        elif m2:
            tag = m2.group(1)
            for j in range(len(stack) - 1, -1, -1):
                if stack[j][0] == tag:
                    results.append({"tag": tag, "open_start": stack[j][1],
                                    "close_end": m2.end()})
                    stack.pop(j)
                    break
            pos = m2.end()
        else:
            break
    return results


def find_outermost_xml_tag(content: str) -> str | None:
    all_tags = find_xml_tags(content)
    if not all_tags:
        return None
    best = None
    best_span = -1
    for t in all_tags:
        span = t["close_end"] - t["open_start"]
        if span > best_span:
            best_span = span
            best = t["tag"]
    return best


def split_by_headings(content: str) -> list[dict]:
    lines = content.splitlines(keepends=True)
    segments = []
    current_start = 0
    current_heading = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,2})\s+(.+?)($|\n)", line)
        if m:
            if current_start < i:
                segments.append({
                    "heading_level": current_heading[0] if current_heading else None,
                    "heading_text": current_heading[1] if current_heading else "",
                    "start_line": current_start,
                    "end_line": i - 1,
                })
            lvl = len(m.group(1))
            current_heading = (lvl, m.group(2).strip())
            current_start = i
    if current_start < len(lines):
        segments.append({
            "heading_level": current_heading[0] if current_heading else None,
            "heading_text": current_heading[1] if current_heading else "",
            "start_line": current_start,
            "end_line": len(lines) - 1,
        })
    return segments


def _is_empty_or_heading_only(segment: str) -> bool:
    clean = re.sub(r"<[^>]+>", "", segment)
    clean = re.sub(r"^#{1,2}\s.*$", "", clean, flags=re.MULTILINE)
    clean = clean.strip()
    return clean == ""


def get_default_entry_fields() -> dict:
    return {
        "uid": None, "key": [], "keysecondary": [], "comment": "",
        "content": "", "constant": False, "disable": False,
        "selective": True, "selectiveLogic": 0, "order": 100,
        "position": 0, "depth": 4, "role": None,
        "probability": 100, "useProbability": True, "sticky": 0,
        "cooldown": 0, "delay": 0,
        "scanDepth": None, "caseSensitive": None, "matchWholeWords": None,
        "useGroupScoring": None,
        "matchPersonaDescription": False, "matchCharacterDescription": False,
        "matchCharacterPersonality": False, "matchCharacterDepthPrompt": False,
        "matchScenario": False, "matchCreatorNotes": False,
        "excludeRecursion": False, "preventRecursion": False,
        "delayUntilRecursion": False, "ignoreBudget": False,
        "group": "", "groupOverride": False, "groupWeight": 100,
        "outletName": "", "automationId": "", "vectorized": False,
        "addMemo": False, "triggers": [],
        "characterFilter": {"names": [], "tags": [], "isExclude": False},
        "displayIndex": None,
    }


def load_world_book(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "entries" not in data:
        data["entries"] = {}
    return data


def save_world_book(entries: dict | list, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(entries, list):
        entries_dict = {str(i): e for i, e in enumerate(entries)}
    else:
        entries_dict = entries
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": entries_dict}, f, ensure_ascii=False, indent=2)


def backup_file(path: str | Path) -> str:
    path = Path(path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.parent / f"{path.stem}.backup_{ts}{path.suffix}"
    shutil.copy2(path, backup)
    return str(backup)


def reassign_uids(entries: list[dict]) -> list[dict]:
    for i, e in enumerate(entries):
        e["uid"] = i
        e["displayIndex"] = i
    return entries


def is_outlet_entry(entry: dict) -> bool:
    return entry.get("position") == 7


def sort_entries(entries: list[dict]) -> list[dict]:
    for e in entries:
        e.setdefault("_is_static", determine_static(e.get("content", "")))
        e.setdefault("_original_order", e.get("order", 100))
        e.setdefault("_is_boundary_copy", False)
        e.setdefault("_is_supplement", False)
    return sorted(entries, key=_sort_key)


def _sort_key(entry: dict) -> tuple:
    is_static = entry.get("_is_static", True)
    is_copy_or_supp = entry.get("_is_boundary_copy", False) or entry.get("_is_supplement", False)
    category = 1 if (not is_static or is_copy_or_supp) else 0

    if entry.get("_is_supplement"):
        comment = entry.get("comment", "")
        if "[supplement-start]" in comment:
            sub_order = 0
        else:
            sub_order = 2
    else:
        sub_order = 1

    pos = entry.get("position", 0)
    depth = entry.get("depth")

    if pos == 4 and depth is not None:
        if depth >= 10:
            stability = 0
        else:
            stability = 2
        depth_key = -depth
    else:
        stability = 1
        depth_key = 0

    original_order = entry.get("_original_order", entry.get("order", 100))
    return (category, sub_order, stability, pos, depth_key, original_order)
