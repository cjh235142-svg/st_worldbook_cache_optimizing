from pathlib import Path
from collections import defaultdict

from . import world_book_utils as wu


def run(input_path: str, output_path: str | None = None) -> str:
    ip = str(Path(input_path).resolve())
    src = Path(ip)
    if output_path is None:
        output_path = str(src.parent / f"{src.stem}_merged.json")
    output_path = str(Path(output_path).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    wb = wu.load_world_book(ip)
    entries_data = wb.get("entries", {})
    entries = list(entries_data.values())

    mergeable = []
    non_mergeable = []
    for e in entries:
        if _is_mergeable_static(e):
            mergeable.append(e)
        else:
            non_mergeable.append(e)

    groups = defaultdict(list)
    for e in mergeable:
        pos = e.get("position", 0)
        const = e.get("constant", False)
        depth = e.get("depth")
        groups[(pos, const, depth)].append(e)

    merged = []
    for group in groups.values():
        group.sort(key=lambda x: x.get("order", 100))
        if len(group) == 1:
            merged.append(dict(group[0]))
        else:
            merged.append(_merge_one_group(group))

    all_entries = merged + [dict(e) for e in non_mergeable]
    all_entries.sort(key=lambda x: x.get("order", 100))
    all_entries = _reassign_orders(all_entries)
    all_entries = wu.reassign_uids(all_entries)

    for e in all_entries:
        e.pop("_is_static", None)
        e.pop("_original_order", None)
        e.pop("_is_boundary_copy", None)
        e.pop("_is_supplement", None)

    wu.save_world_book(all_entries, output_path)
    return output_path


def _reassign_orders(entries: list[dict]) -> list[dict]:
    for i, e in enumerate(entries):
        e["order"] = i
    return entries


def _is_mergeable_static(entry: dict) -> bool:
    content = entry.get("content", "")
    comment = entry.get("comment", "")
    if "[boundary-copy-" in comment:
        return False
    if "[supplement-" in comment:
        return False
    if not wu.determine_static(content):
        return False
    return True


def _merge_one_group(group: list[dict]) -> dict:
    contents = [e["content"] for e in group]
    merged_content = "\n\n".join(contents)
    min_order = group[0].get("order", 0)
    max_order = group[-1].get("order", 0)
    base = group[0]

    return {
        "position": base.get("position", 0),
        "constant": base.get("constant", False),
        "depth": base.get("depth"),
        "content": merged_content,
        "order": min_order,
        "comment": f"合并:{min_order}-{max_order}",
        "key": [],
        "keysecondary": [],
        "role": base.get("role"),
        "useProbability": False,
        "disable": False,
        "selective": True,
        "selectiveLogic": 0,
        "probability": 100,
        "sticky": 0,
        "cooldown": 0,
        "delay": 0,
        "scanDepth": None,
        "caseSensitive": None,
        "matchWholeWords": None,
        "useGroupScoring": None,
        "matchPersonaDescription": False,
        "matchCharacterDescription": False,
        "matchCharacterPersonality": False,
        "matchCharacterDepthPrompt": False,
        "matchScenario": False,
        "matchCreatorNotes": False,
        "excludeRecursion": False,
        "preventRecursion": False,
        "delayUntilRecursion": False,
        "ignoreBudget": False,
        "group": "",
        "groupOverride": False,
        "groupWeight": 100,
        "outletName": "",
        "automationId": "",
        "vectorized": False,
        "addMemo": False,
        "triggers": [],
        "characterFilter": {"names": [], "tags": [], "isExclude": False},
        "displayIndex": None,
        "uid": None,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    out = run(args.input, args.output)
    print(f"Merged world book written to: {out}")
