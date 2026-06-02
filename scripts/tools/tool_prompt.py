import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, sort_entries

_PLACEHOLDER = "[{name} Placeholder]"


def run(
    input_path: str,
    system_prompt: str | None = None,
    character_path: str | None = None,
    persona_path: str | None = None,
    scenario: str | None = None,
    chat_history_path: str | None = None,
    output_path: str | None = None,
    no_comments: bool = False,
) -> str:
    wb = load_world_book(input_path)
    entries = list(wb.get("entries", {}).values())

    for e in entries:
        e["_is_static"] = determine_static(e.get("content", ""))
    entries = sort_entries(entries)

    sys_prompt = _load_text(system_prompt) if system_prompt else _PLACEHOLDER.format(name="System Prompt")
    persona = _load_text(persona_path) if persona_path else _PLACEHOLDER.format(name="Persona Description")
    char_desc = _PLACEHOLDER.format(name="Character Description")
    char_personality = _PLACEHOLDER.format(name="Character Personality")
    scn = scenario or _PLACEHOLDER.format(name="Scenario")

    if character_path:
        char_data = _load_json(character_path)
        char_desc = char_data.get("description", char_desc)
        char_personality = char_data.get("personality", char_personality)
        if not scenario:
            scn = char_data.get("scenario", scn)

    pos0_entries = [e for e in entries if e.get("position") == 0]
    pos1_entries = [e for e in entries if e.get("position") == 1]
    pos5_entries = [e for e in entries if e.get("position") == 5]
    pos6_entries = [e for e in entries if e.get("position") == 6]
    pos2_entries = [e for e in entries if e.get("position") == 2]
    pos3_entries = [e for e in entries if e.get("position") == 3]

    pos4_entries = [e for e in entries if e.get("position") == 4]
    pos4_by_depth = {}
    for e in pos4_entries:
        d = e.get("depth", 0)
        pos4_by_depth.setdefault(d, []).append(e)

    chat_messages = _parse_chat_history(chat_history_path) if chat_history_path else [
        {"role": "user", "content": _PLACEHOLDER.format(name="Chat History")},
    ]

    sections = []
    order = ["System Prompt", "pos0", "Persona", "CharDesc", "CharPersonality",
             "Scenario", "pos1", "pos5", "pos6", "ChatHistory", "pos2", "pos3"]

    if not no_comments:
        sections.append(f"<!-- ============ [1/{len(order)}] System Prompt ============ -->")
    sections.append(sys_prompt.strip())

    if not no_comments and pos0_entries:
        sections.append(f"\n<!-- ============ [2/{len(order)}] World Info (before) pos=0 ============ -->")
    if pos0_entries:
        sections.extend(_format_entries(pos0_entries, no_comments))

    if not no_comments:
        sections.append(f"\n<!-- ============ [3/{len(order)}] Persona Description ============ -->")
    sections.append(persona.strip())

    if not no_comments:
        sections.append(f"\n<!-- ============ [4/{len(order)}] Character Description ============ -->")
    sections.append(char_desc.strip())

    if not no_comments:
        sections.append(f"\n<!-- ============ [5/{len(order)}] Character Personality ============ -->")
    sections.append(char_personality.strip())

    if not no_comments:
        sections.append(f"\n<!-- ============ [6/{len(order)}] Scenario ============ -->")
    sections.append(scn.strip())

    if not no_comments and pos1_entries:
        sections.append(f"\n<!-- ============ [7/{len(order)}] World Info (after) pos=1 ============ -->")
    if pos1_entries:
        sections.extend(_format_entries(pos1_entries, no_comments))

    if pos5_entries:
        if not no_comments:
            sections.append(f"\n<!-- ============ [8/{len(order)}] Chat Examples pos=5 [top] ============ -->")
        sections.extend(_format_entries(pos5_entries, no_comments))
    if pos6_entries:
        if not no_comments:
            sections.append(f"\n<!-- Chat Examples pos=6 [bottom] -->")
        sections.extend(_format_entries(pos6_entries, no_comments))

    if not no_comments:
        sections.append(f"\n<!-- ============ [9/{len(order)}] Chat History (with pos=4 atDepth) ============ -->")

    sorted_depths = sorted(pos4_by_depth.keys(), reverse=True)
    for depth in sorted_depths:
        injected = pos4_by_depth[depth]
        depth_idx = max(0, len(chat_messages) - depth - 1)
        if depth_idx < len(chat_messages):
            target_msg = chat_messages[depth_idx]
            if not no_comments:
                for ei in injected:
                    sections.append(
                        f"<!--   injected: Entry uid={ei.get('uid')} "
                        f"order={ei.get('order')} comment=\"{ei.get('comment','')}\" "
                        f"pos=4 depth={ei.get('depth')} -->"
                    )
            sections.extend(_format_entries(injected, no_comments, prefix=""))

    for i, msg in enumerate(chat_messages):
        if not no_comments:
            sections.append(f"\n<!-- Chat Message {i+1}: -->")
        role_label = {"user": "用户", "assistant": "角色", "system": "系统"}.get(msg["role"], msg["role"])
        sections.append(f"{role_label}: {msg['content']}")

    if pos2_entries or pos3_entries:
        if not no_comments:
            sections.append(f"\n<!-- ============ [10/{len(order)}] Author's Note pos=2/3 ============ -->")
        sections.extend(_format_entries(pos2_entries + pos3_entries, no_comments))

    total_sections = sum(1 for s in sections if s.strip()) if no_comments else len(sections)
    if not no_comments:
        sections.append(f"\n<!-- ============================================ -->")
        sections.append(f"<!-- 总计: {len(order)} 段, {sum(1 for s in sections if 'injected' in s)} 个 WI 条目注入 -->")

    result = "\n".join(sections)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
    return result


def _format_entries(entries, no_comments, prefix="") -> list[str]:
    lines = []
    for e in entries:
        if not no_comments:
            is_s = "✓" if e.get("_is_static") else "✗"
            lines.append(
                f"<!-- Entry uid={e.get('uid')}: order={e.get('order')} "
                f"\"{e.get('comment','')}\" static={is_s} "
                f"pos={e.get('position')} depth={e.get('depth')} -->"
            )
        lines.append(prefix + e.get("content", ""))
    return lines


def _load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_chat_history(path: str) -> list[dict]:
    data = _load_json(path)
    messages = data.get("chat", data.get("messages", []))
    return [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
    ]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True)
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--character", default=None)
    p.add_argument("--persona", default=None)
    p.add_argument("--scenario", default=None)
    p.add_argument("--chat-history", default=None)
    p.add_argument("-o", "--output", default=None)
    p.add_argument("-C", "--no-comments", action="store_true")
    args = p.parse_args()
    print(run(
        args.input, args.system_prompt, args.character,
        args.persona, args.scenario, args.chat_history,
        args.output, args.no_comments,
    ))
