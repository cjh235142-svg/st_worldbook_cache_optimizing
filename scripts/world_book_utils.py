"""
Common utilities for World Book processing scripts.
"""

import json
import os
import re
import copy
import sys
import logging

logger = logging.getLogger("wb")

# ---- Position/Role enumerations ----

POSITION = {
    "before": 0,
    "after": 1,
    "ANTop": 2,
    "ANBottom": 3,
    "atDepth": 4,
    "EMTop": 5,
    "EMBottom": 6,
    "outlet": 7,
}

ROLE = {
    "SYSTEM": 0,
    "USER": 1,
    "ASSISTANT": 2,
}

# ---- ST -> originalData field mapping (from SillyTavern source) ----

ST_TO_ORIGINAL_KEY_MAP = {
    "displayIndex": "extensions.display_index",
    "excludeRecursion": "extensions.exclude_recursion",
    "preventRecursion": "extensions.prevent_recursion",
    "delayUntilRecursion": "extensions.delay_until_recursion",
    "selectiveLogic": "extensions.selectiveLogic",
    "comment": "comment",
    "constant": "constant",
    "order": "insertion_order",
    "depth": "extensions.depth",
    "probability": "extensions.probability",
    "useProbability": "extensions.useProbability",
    "position": "extensions.position",
    "role": "extensions.role",
    "content": "content",
    "key": "keys",
    "keysecondary": "secondary_keys",
    "selective": "selective",
    "matchWholeWords": "extensions.match_whole_words",
    "useGroupScoring": "extensions.use_group_scoring",
    "caseSensitive": "extensions.case_sensitive",
    "matchPersonaDescription": "extensions.match_persona_description",
    "matchCharacterDescription": "extensions.match_character_description",
    "matchCharacterPersonality": "extensions.match_character_personality",
    "matchCharacterDepthPrompt": "extensions.match_character_depth_prompt",
    "matchScenario": "extensions.match_scenario",
    "matchCreatorNotes": "extensions.match_creator_notes",
    "scanDepth": "extensions.scan_depth",
    "automationId": "extensions.automation_id",
    "vectorized": "extensions.vectorized",
    "groupOverride": "extensions.group_override",
    "groupWeight": "extensions.group_weight",
    "sticky": "extensions.sticky",
    "cooldown": "extensions.cooldown",
    "delay": "extensions.delay",
    "triggers": "extensions.triggers",
    "ignoreBudget": "extensions.ignore_budget",
    "outletName": "extensions.outlet_name",
}

# Fields that need inversion between ST and originalData
INVERT_MAP = {"disable": "enabled"}

# Global warning counter
WARNING_COUNT = 0


# ---- File I/O ----

def load_world_book(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_world_book(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- Entry list <-> dict conversion ----

def get_entries_sorted(data: dict) -> list:
    entries = data.get("entries", {})
    return [entries[k] for k in sorted(entries.keys(), key=int)]


def set_entries_from_list(data: dict, entries: list):
    data["entries"] = {str(i): e for i, e in enumerate(entries)}


# ---- Nested path access (for extensions.position etc.) ----

def get_nested_value(obj, path: str):
    parts = path.split(".")
    for p in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return None
    return obj


def set_nested_value(obj: dict, path: str, value):
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in obj or not isinstance(obj[p], dict):
            obj[p] = {}
        obj = obj[p]
    obj[parts[-1]] = value


# ---- Extensions sync ----

EXTENSIONS_SYNC_FIELDS = [
    "position", "excludeRecursion", "displayIndex", "probability",
    "useProbability", "depth", "selectiveLogic", "outletName",
    "group", "groupOverride", "groupWeight", "preventRecursion",
    "delayUntilRecursion", "scanDepth", "matchWholeWords",
    "useGroupScoring", "caseSensitive", "automationId", "role",
    "vectorized", "sticky", "cooldown", "delay",
    "matchPersonaDescription", "matchCharacterDescription",
    "matchCharacterPersonality", "matchCharacterDepthPrompt",
    "matchScenario", "matchCreatorNotes", "triggers", "ignoreBudget",
]


def sync_extensions(entry: dict):
    ext = entry.get("extensions", {})
    if not isinstance(ext, dict):
        ext = {}
        entry["extensions"] = ext

    _sync_one(entry, ext, "position")
    _sync_one(entry, ext, "excludeRecursion", "exclude_recursion")
    _sync_one(entry, ext, "displayIndex", "display_index")
    _sync_one(entry, ext, "probability")
    _sync_one(entry, ext, "useProbability")
    _sync_one(entry, ext, "depth")
    _sync_one(entry, ext, "selectiveLogic")
    _sync_one(entry, ext, "outletName", "outlet_name")
    _sync_one(entry, ext, "group")
    _sync_one(entry, ext, "groupOverride", "group_override")
    _sync_one(entry, ext, "groupWeight", "group_weight")
    _sync_one(entry, ext, "preventRecursion", "prevent_recursion")
    _sync_one(entry, ext, "excludeRecursion", "exclude_recursion")
    _sync_one(entry, ext, "delayUntilRecursion", "delay_until_recursion")
    _sync_one(entry, ext, "scanDepth", "scan_depth")
    _sync_one(entry, ext, "matchWholeWords", "match_whole_words")
    _sync_one(entry, ext, "useGroupScoring", "use_group_scoring")
    _sync_one(entry, ext, "caseSensitive", "case_sensitive")
    _sync_one(entry, ext, "automationId", "automation_id")
    _sync_one(entry, ext, "role")
    _sync_one(entry, ext, "vectorized")
    _sync_one(entry, ext, "sticky")
    _sync_one(entry, ext, "cooldown")
    _sync_one(entry, ext, "delay")
    _sync_one(entry, ext, "matchPersonaDescription", "match_persona_description")
    _sync_one(entry, ext, "matchCharacterDescription", "match_character_description")
    _sync_one(entry, ext, "matchCharacterPersonality", "match_character_personality")
    _sync_one(entry, ext, "matchCharacterDepthPrompt", "match_character_depth_prompt")
    _sync_one(entry, ext, "matchScenario", "match_scenario")
    _sync_one(entry, ext, "matchCreatorNotes", "match_creator_notes")
    _sync_one(entry, ext, "triggers")
    _sync_one(entry, ext, "ignoreBudget", "ignore_budget")


def _sync_one(entry, ext, st_key, ext_key=None):
    if ext_key is None:
        ext_key = st_key
    if st_key in entry:
        ext[ext_key] = entry[st_key]


# ---- EJS parsing ----

def parse_ejs_regions(content: str) -> list:
    tags = list(re.finditer(r"<%_[^%]*_%>", content))
    if not tags:
        return []

    regions = []
    depth = 0
    region_start = -1

    for tag in tags:
        tag_text = tag.group()
        opens = tag_text.count("{")
        closes = tag_text.count("}")
        old_depth = depth
        depth += opens
        depth -= closes

        if old_depth == 0 and depth > 0:
            region_start = tag.start()
        if old_depth > 0 and depth == 0:
            regions.append((region_start, tag.end()))
            region_start = -1

    if depth > 0 and region_start >= 0:
        regions.append((region_start, len(content)))

    return regions


def is_inside_ejs(pos: int, regions: list) -> bool:
    for start, end in regions:
        if start <= pos < end:
            return True
    return False


def contains_ejs(content: str, regions: list = None) -> bool:
    if regions is None:
        regions = parse_ejs_regions(content)
    if not regions:
        return False
    return any(start < len(content) for start, _ in regions)


# ---- Markdown heading parsing ----

HEADING_PATTERN = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)


def find_markdown_headings(content: str):
    headings = []
    for m in HEADING_PATTERN.finditer(content):
        headings.append({
            "start": m.start(),
            "end": m.end(),
            "level": len(m.group(1)),
            "text": m.group(2).strip(),
        })
    return headings


def split_by_headings(content: str, headings: list):
    sections = []
    if not headings:
        if content.strip():
            sections.append(content)
        return sections

    # prefix before first heading
    if headings[0]["start"] > 0:
        prefix = content[:headings[0]["start"]]
        if prefix.strip():
            sections.append(prefix)

    for i, h in enumerate(headings):
        start = h["start"]
        end = headings[i + 1]["start"] if i + 1 < len(headings) else len(content)
        sections.append(content[start:end])

    return sections


# ---- Bracket pair detection ----

START_PATTERN = re.compile(r"^(.+)开始$")
END_PATTERN = re.compile(r"^(.+)结束$")
# Brackets that contain "补充" are synthetic markers, not original brackets
SUPP_PARENS = "补充"


def find_bracket_pairs(entries: list) -> list:
    starts = {}
    ends = {}

    for e in entries:
        comment = e.get("comment", "")
        if SUPP_PARENS in comment:
            continue
        m = START_PATTERN.match(comment)
        if m:
            starts.setdefault(m.group(1), []).append(e)
        m = END_PATTERN.match(comment)
        if m:
            ends.setdefault(m.group(1), []).append(e)

    pairs = []
    for name in sorted(starts.keys()):
        if name in ends:
            s_list = starts[name]
            e_list = ends[name]
            for s, e in zip(s_list, e_list):
                pairs.append((s, e))
            if len(s_list) != len(e_list):
                log_warning(f"bracket配对数量不一致: '{name}开始'={len(s_list)} vs '{name}结束'={len(e_list)}")
        else:
            for s in starts[name]:
                log_warning(f"bracket未配对: \"{s['comment']}\" (uid={s['uid']}) 无对应结束")

    for name in ends:
        if name not in starts:
            for e in ends[name]:
                log_warning(f"bracket未配对: \"{e['comment']}\" (uid={e['uid']}) 无对应开始")

    return pairs


# ---- Logging ----

def log_info(msg: str):
    logger.info(msg)


def log_warning(msg: str):
    global WARNING_COUNT
    WARNING_COUNT += 1
    logger.warning(msg)


# ---- Deep copy helper ----

def clone_entry(entry: dict, new_uid: int, new_comment: str) -> dict:
    e = copy.deepcopy(entry)
    e["uid"] = new_uid
    e["comment"] = new_comment
    return e


# ---- Heading-only content extraction ----

def extract_heading_only(content: str, heading_text: str) -> str:
    """Generate content for a supplement entry.
    Preserves XML tag format <XX> </XX> → <XX补充> </XX补充>,
    or Markdown heading format # XX → # XX补充.
    heading_text should be the base name (without '补充').
    Only returns FIRST matching line (opening or closing tag).
    """
    lines = content.split("\n")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<%_"):
            continue
        # Match opening tag: <Tag> or <Tag> followed by text
        m = re.match(r"^</?([\w\u4e00-\u9fff]+)>", stripped)
        if m:
            tag = m.group(1)
            is_close = stripped.startswith("</")
            if is_close:
                return f"</{tag}补充>"
            else:
                return f"<{tag}补充>"

    # Fallback: Markdown heading format
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("###"):
            return f"# {heading_text}补充"

    return f"# {heading_text}补充"


# ---- Content assembly ----

def assemble_content(sections: list) -> str:
    return "\n".join(s.strip() for s in sections if s.strip())


# ---- Sort key (atDepth 分档) ----

def atdepth_sort_key(entry: dict, include_position: bool = True):
    """Sort key: (band, pos, -depth, order).
    band=0: (pos=4, depth>=10)  -- first
    band=1: all others          -- middle
    band=2: (pos=4, depth<10)   -- last
    Within atDepth bands: depth DESC, order ASC.
    """
    pos = entry.get("position", 0)
    depth = entry.get("depth", 0)
    order = entry.get("order", 0)
    if pos == POSITION["atDepth"]:
        band = 0 if depth >= 10 else 2
        return (band, pos, -depth, order) if include_position else (band, -depth, order)
    return (1, pos, 0, order) if include_position else (1, 0, order)


def dense_sort_key(entry: dict):
    """Same three-band logic as atdepth_sort_key: (band, pos, -depth, order)."""
    pos = entry.get("position", 0)
    depth = entry.get("depth", 0)
    order = entry.get("order", 0)
    if pos == POSITION["atDepth"]:
        band = 0 if depth >= 10 else 2
        return (band, pos, -depth, order)
    return (1, pos, 0, order)


# ---- Logging bootstrap ----

def configure_logging(level: str = "INFO", fmt: str = "%(levelname)-7s %(message)s"):
    logging.basicConfig(level=getattr(logging, level.upper()), format=fmt, stream=sys.stderr)


def add_log_level_arg(parser, default: str = "INFO"):
    parser.add_argument("--log-level", type=str, default=default,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help=f"Logging level (default: {default})")


# ---- File path helpers ----

def default_output_path(input_path: str, suffix: str = "_out") -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}{suffix}{ext}"
