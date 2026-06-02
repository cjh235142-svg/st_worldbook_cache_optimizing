import re
from copy import deepcopy
from pathlib import Path

from . import world_book_utils as wu

_XML_TAG_RE = re.compile(r"<([\u4e00-\u9fff\w]+)>")
_XML_CLOSE_RE = re.compile(r"</([\u4e00-\u9fff\w]+)>")
_MD_BOUNDARY_RE = re.compile(r"^(#{1,2})\s+(.+?)(开始|结束|start|end|begin|close)\s*$")


class BoundaryPair:
    def __init__(self, open_entry, close_entry, open_copy_content, close_copy_content):
        self.open_entry = open_entry
        self.close_entry = close_entry
        self.open_copy_content = open_copy_content
        self.close_copy_content = close_copy_content


def run(input_path: str, output_path: str | None = None,
        wrapper_name: str = "补充内容") -> str:
    ip = str(Path(input_path).resolve())
    src = Path(ip)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_reordered.json")
    output_path = str(Path(output_path).resolve())

    wb = wu.load_world_book(ip)
    entries_data = wb.get("entries", {})
    entries = list(entries_data.values())

    for e in entries:
        e["_original_order"] = e.get("order", 100)
        e["_is_static"] = wu.determine_static(e.get("content", ""))
        e["_is_boundary_copy"] = False
        e["_is_supplement"] = False

    pairs = _pair_boundaries(entries)
    boundary_copies = _create_boundary_copies(entries, pairs)
    for bc in boundary_copies:
        bc.setdefault("_is_static", wu.determine_static(bc.get("content", "")))
        bc.setdefault("_original_order", bc.get("order", 100))

    supplements = _create_supplement_wrapper(entries, wrapper_name)
    for s in supplements:
        s.setdefault("_is_static", False)
        s.setdefault("_original_order", s.get("order", 0))

    all_entries = list(entries) + boundary_copies + supplements
    all_entries = wu.sort_entries(all_entries)
    all_entries = _prune_empty(all_entries)
    all_entries = wu.reassign_orders(all_entries)
    all_entries = wu.reassign_uids(all_entries)

    for e in all_entries:
        _apply_rules(e)

    for e in all_entries:
        e.pop("_original_order", None)

    wu.save_world_book(all_entries, output_path)
    return output_path


def is_boundary_entry(content: str) -> tuple | None:
    if wu.detect_markers(content):
        return None

    xml_result = _detect_xml_boundary_simple(content)
    if xml_result:
        return xml_result

    md_result = _detect_md_boundary(content)
    if md_result:
        return md_result

    return None


def _is_boundary_copy_content(content: str) -> bool:
    stripped = content.strip()
    if re.match(r"^<[\u4e00-\u9fff\w]+>\s*$", stripped):
        return True
    if re.match(r"^</[\u4e00-\u9fff\w]+>\s*$", stripped):
        return True
    if _MD_BOUNDARY_RE.match(stripped):
        return True
    return False


def _detect_xml_boundary_simple(content: str) -> tuple | None:
    stripped = content.strip()
    m = _XML_TAG_RE.search(stripped)
    if m:
        tag = m.group(1)
        if f"</{tag}>" not in stripped:
            return ("xml_open", tag, f"<{tag}>")
    m = _XML_CLOSE_RE.search(stripped)
    if m:
        tag = m.group(1)
        if f"<{tag}>" not in stripped:
            return ("xml_close", tag, f"</{tag}>")
    return None


def _detect_md_boundary(content: str) -> tuple | None:
    stripped = content.strip()
    for line in stripped.splitlines():
        m = _MD_BOUNDARY_RE.match(line.strip())
        if m:
            heading = m.group(1)
            base = m.group(2).strip()
            suffix = m.group(3)
            btype = "md_open" if suffix in ("开始", "start", "begin") else "md_close"
            return (btype, base, f"{heading} {base}{suffix}")
    return None


def _pair_boundaries(entries: list[dict]) -> list[BoundaryPair]:
    groups = {}
    for e in entries:
        pos = e.get("position", 0)
        groups.setdefault(pos, []).append(e)

    pairs = []
    for pos, group in groups.items():
        stack = []
        sorted_group = sorted(group, key=lambda x: x["_original_order"])
        for e in sorted_group:
            content = e.get("content", "")
            comment = e.get("comment", "")
            key = e.get("key", [])

            if key == ["/.*/"] and _is_boundary_copy_content(content):
                continue

            r = _detect_xml_boundary_simple(content)
            if r is None:
                r = _detect_md_boundary(content)
            if r is None:
                continue

            btype, name, copy_content = r
            if btype in ("xml_open", "md_open"):
                stack.append((e, name, copy_content, btype))
            else:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][1] == name:
                        open_e, _, open_copy, open_type = stack.pop(i)
                        pairs.append(BoundaryPair(
                            open_entry=open_e, close_entry=e,
                            open_copy_content=open_copy,
                            close_copy_content=copy_content,
                        ))
                        break
    return pairs


def _create_boundary_copies(entries: list[dict], pairs: list[BoundaryPair]) -> list[dict]:
    copies = []
    for pair in pairs:
        min_order = pair.open_entry["_original_order"]
        max_order = pair.close_entry["_original_order"]
        has_dynamic = any(
            min_order < e["_original_order"] < max_order
            and not wu.determine_static(e.get("content", ""))
            for e in entries
        )
        if not has_dynamic:
            continue

        open_copy = deepcopy(pair.open_entry)
        open_copy["content"] = pair.open_copy_content
        open_copy["_is_boundary_copy"] = True
        open_copy["_original_order"] = min_order
        open_copy["comment"] = (
            f"{pair.open_entry.get('comment','')} [boundary-copy-open]"
        ).strip()
        open_copy["uid"] = None

        close_copy = deepcopy(pair.close_entry)
        close_copy["content"] = pair.close_copy_content
        close_copy["_is_boundary_copy"] = True
        close_copy["_original_order"] = max_order
        close_copy["comment"] = (
            f"{pair.close_entry.get('comment','')} [boundary-copy-close]"
        ).strip()
        close_copy["uid"] = None

        copies.extend([open_copy, close_copy])
    return copies


def _detect_wrapper_style(entries: list[dict]) -> str:
    xml_count = 0
    md_count = 0
    for e in entries:
        content = e.get("content", "")
        xml_count += len(re.findall(r"<[\u4e00-\u9fff\w]+>", content))
        md_count += len(re.findall(r"^#{1,2}\s", content, re.MULTILINE))
    return "xml" if xml_count >= md_count else "markdown"


def _is_existing_supplement(entry: dict, wrapper_name: str) -> bool:
    comment = entry.get("comment", "")
    if "[supplement-" in comment:
        return True
    content = entry.get("content", "").strip()
    key = entry.get("key", [])
    if key == ["/.*/"]:
        open_pattern = f"<{wrapper_name}>"
        close_pattern = f"</{wrapper_name}>"
        md_start = f"# {wrapper_name}开始"
        md_end = f"# {wrapper_name}结束"
        if content in (open_pattern, close_pattern, md_start, md_end):
            return True
    return False


def _create_supplement_wrapper(entries: list[dict], wrapper_name: str) -> list[dict]:
    existing = any(_is_existing_supplement(e, wrapper_name) for e in entries)
    if existing:
        return []
    has_dynamic = any(not wu.determine_static(e.get("content", "")) for e in entries)
    if not has_dynamic:
        return []

    style = _detect_wrapper_style(entries)
    if style == "xml":
        open_content = f"<{wrapper_name}>"
        close_content = f"</{wrapper_name}>"
    else:
        open_content = f"# {wrapper_name}开始"
        close_content = f"# {wrapper_name}结束"

    base = {
        "content": "", "comment": "", "constant": False,
        "key": [], "keysecondary": [],
        "position": 4, "depth": 0, "role": 1, "order": 0,
        "disable": False, "selective": True, "selectiveLogic": 0,
        "probability": 100, "useProbability": False,
        "sticky": 0, "cooldown": 0, "delay": 0,
        "scanDepth": None, "caseSensitive": None, "matchWholeWords": None,
        "useGroupScoring": None,
        "matchPersonaDescription": False, "matchCharacterDescription": False,
        "matchCharacterPersonality": False, "matchCharacterDepthPrompt": False,
        "matchScenario": False, "matchCreatorNotes": False,
        "excludeRecursion": False, "preventRecursion": False,
        "delayUntilRecursion": 0, "ignoreBudget": False,
        "group": "", "groupOverride": False, "groupWeight": 100,
        "outletName": "", "automationId": "", "vectorized": False,
        "addMemo": False, "triggers": [],
        "characterFilter": {"names": [], "tags": [], "isExclude": False},
        "displayIndex": None, "uid": None,
    }

    open_entry = dict(base)
    open_entry["content"] = open_content
    open_entry["comment"] = "[supplement-start]"
    open_entry["_is_supplement"] = True
    open_entry["_original_order"] = float("inf")

    close_entry = dict(base)
    close_entry["content"] = close_content
    close_entry["comment"] = "[supplement-end]"
    close_entry["_is_supplement"] = True
    close_entry["_original_order"] = float("inf")

    return [open_entry, close_entry]


def _prune_empty(entries: list[dict]) -> list[dict]:
    all_entries = list(entries)
    to_remove = set()

    boundary_indices = [i for i, e in enumerate(all_entries) if e.get("_is_boundary_copy")]
    # 同 position 内栈式配对保证输出顺序为 开1,闭1,开2,闭2,...
    # 因此 boundary_indices 成对相邻出现
    i = 0
    while i < len(boundary_indices):
        open_idx = boundary_indices[i]
        close_idx = boundary_indices[i + 1] if i + 1 < len(boundary_indices) else None
        if close_idx is None:
            break
        has_dynamic = any(
            not wu.determine_static(all_entries[j].get("content", ""))
            and not all_entries[j].get("_is_boundary_copy")
            and not all_entries[j].get("_is_supplement")
            for j in range(open_idx + 1, close_idx)
        )
        if not has_dynamic:
            to_remove.update([open_idx, close_idx])
        i += 2

    has_any_dynamic = any(
        not wu.determine_static(e.get("content", ""))
        and not e.get("_is_boundary_copy")
        for e in all_entries
    )
    if not has_any_dynamic:
        for idx, e in enumerate(all_entries):
            if e.get("_is_supplement"):
                to_remove.add(idx)

    return [e for idx, e in enumerate(all_entries) if idx not in to_remove]


def _apply_rules(entry: dict) -> None:
    is_static = entry.pop("_is_static", True)
    is_copy = entry.pop("_is_boundary_copy", False)
    is_supplement = entry.pop("_is_supplement", False)

    pos = entry.get("position", 0)

    if pos == 7:
        return

    if is_copy or is_supplement:
        entry["constant"] = False
        entry["position"] = 4
        entry["depth"] = 0
        entry["role"] = 1
        entry["key"] = ["/.*/"]
        entry["useProbability"] = False
        entry["probability"] = 100
        entry["cooldown"] = 0
        entry["sticky"] = 0
        entry["delay"] = 0
        return

    depth = entry.get("depth")

    if is_static:
        entry["constant"] = True
        entry["cooldown"] = 0
        entry["probability"] = 100
        entry["useProbability"] = False
        entry["sticky"] = 0
        entry["delay"] = 0

        if pos == 4 and depth is not None:
            if depth >= 10:
                entry["depth"] = 9999
            else:
                entry["depth"] = 0
            entry["role"] = 1
        elif pos == 4:
            entry["depth"] = 0
            entry["role"] = 1
    else:
        entry["position"] = 4
        entry["depth"] = 0
        entry["role"] = 1


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", default=None)
    p.add_argument("-w", "--wrapper-name", default="补充内容")
    args = p.parse_args()
    out = run(args.input, args.output, args.wrapper_name)
    print(f"Reordered world book written to: {out}")
