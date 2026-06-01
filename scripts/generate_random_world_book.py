"""
Generate random SillyTavern World Book JSON for testing.

Usage:
  python generate_random_world_book.py <output.json> [options]
"""

import sys
import os
import re
import json
import logging
import random
import argparse
import copy

logger = logging.getLogger("gen")
_db = lambda msg: logger.debug(msg)

# ---- Template data ----

SECTION_NAMES = [
    "设定", "角色", "剧情", "暗部", "学校", "魔法", "科学", "事件",
    "地标", "国家", "教派", "组织", "武器", "能力", "历史",
]

ENTITY_NAMES = [
    "上条当麻", "御坂美琴", "一方通行", "茵蒂克丝", "白井黑子", "初春饰利",
    "佐天泪子", "食蜂操祈", "麦野沉利", "绢旗最爱", "芙兰达", "泷壶理后",
    "神裂火织", "史提尔", "奥索拉", "后方之水", "右方之火", "左方之地",
    "土御门元春", "结标淡希", "固法美伟", "月咏小萌", "黄泉川爱穗",
    "亚雷斯塔", "木山春生", "婚后光子", "削板军霸", "帆风润子", "蜜蚁爱愉",
]

EJS_VARS = ["天数", "阶段", "好感度", "进度", "等级", "分数", "计数"]

# Entity name generation
_entity_counter = [0]


def gen_entity_name() -> str:
    _entity_counter[0] += 1
    c = _entity_counter[0]
    if c <= len(ENTITY_NAMES):
        return ENTITY_NAMES[c - 1]
    return f"{random.choice(ENTITY_NAMES)}{c}"


def gen_section_name(used: set) -> str:
    available = [n for n in SECTION_NAMES if n not in used]
    if available:
        return random.choice(available)
    return f"分区{len(used) + 1}"

# ---- Entry template ----

NEW_ENTRY_TEMPLATE = {
    "uid": 0,
    "key": [],
    "keysecondary": [],
    "comment": "",
    "content": "",
    "constant": False,
    "vectorized": False,
    "selective": True,
    "selectiveLogic": 0,
    "addMemo": True,
    "order": 0,
    "position": 1,
    "disable": False,
    "ignoreBudget": False,
    "excludeRecursion": False,
    "preventRecursion": False,
    "matchPersonaDescription": False,
    "matchCharacterDescription": False,
    "matchCharacterPersonality": False,
    "matchCharacterDepthPrompt": False,
    "matchScenario": False,
    "matchCreatorNotes": False,
    "delayUntilRecursion": False,
    "probability": 100,
    "useProbability": True,
    "depth": 4,
    "outletName": "",
    "group": "",
    "groupOverride": False,
    "groupWeight": 100,
    "scanDepth": None,
    "caseSensitive": None,
    "matchWholeWords": None,
    "useGroupScoring": False,
    "automationId": "",
    "role": 0,
    "sticky": 0,
    "cooldown": 0,
    "delay": 0,
    "triggers": [],
    "extensions": {
        "position": 1,
        "exclude_recursion": False,
        "display_index": 0,
        "probability": 100,
        "useProbability": True,
        "depth": 4,
        "selectiveLogic": 0,
        "outlet_name": "",
        "group": "",
        "group_override": False,
        "group_weight": 100,
        "prevent_recursion": False,
        "delay_until_recursion": False,
        "scan_depth": None,
        "match_whole_words": None,
        "use_group_scoring": False,
        "case_sensitive": None,
        "automation_id": "",
        "role": 0,
        "vectorized": False,
        "sticky": 0,
        "cooldown": 0,
        "delay": 0,
        "match_persona_description": False,
        "match_character_description": False,
        "match_character_personality": False,
        "match_character_depth_prompt": False,
        "match_scenario": False,
        "match_creator_notes": False,
        "triggers": [],
        "ignore_budget": False,
    },
    "characterFilter": {
        "isExclude": False,
        "names": [],
        "tags": [],
    },
}


def generate_ejs_content(entity: str, with_headings: bool = True) -> str:
    """Generate EJS-driven content, optionally with intermixed headings.

    Creates content where some headings are outside EJS blocks (will be split
    to non-EJS), and some are INSIDE EJS blocks (will be kept with EJS).
    """
    var = random.choice(EJS_VARS)
    threshold = random.randint(30, 100)

    flavor_topics = [
        ("获得了新的力量", "尚未觉醒"),
        ("变得非常重要", "保持低调"),
        ("开始活跃", "仍然神秘"),
        ("进入关键阶段", "默默无闻"),
        ("实力大增", "等待时机"),
        ("受到关注", "旁观者"),
        ("引发事件", "隐藏实力"),
        ("成为焦点", "不被注意"),
    ]
    flavor_a, flavor_b = random.choice(flavor_topics)

    lines = []

    # --- Section A: Non-EJS heading (outside EJS) ---
    if with_headings and random.random() < 0.6:
        lines.append(f"# {entity}")
        lines.append(f"  - 这是一个重要角色")
        lines.append(f"  - 与许多事件相关")
        lines.append("")

    # --- Section B: EJS block, possibly containing its own heading ---
    heading_inside = with_headings and random.random() < 0.5
    if heading_inside:
        ejs_heading = random.choice(["能力状态", "当前阶段", "剧情分支", "关系进展"])
        lines.append(f"<%_ if (getvar('stat_data.${var}') <= {threshold}) {{ _%>")
        lines.append(f"## {ejs_heading}")
        lines.append(f"  - {flavor_a} — 变量{var} <= {threshold}")
        lines.append(f"<%_ }} else {{ _%>")
        lines.append(f"## {ejs_heading}")
        lines.append(f"  - {flavor_b} — 变量{var} > {threshold}")
        lines.append(f"<%_ }} _%>")
    else:
        lines.append(f"<%_ if (getvar('stat_data.${var}') <= {threshold}) {{ _%>")
        lines.append(f"  - {flavor_a}")
        lines.append(f"<%_ }} else {{ _%>")
        lines.append(f"  - {flavor_b}")
        lines.append(f"<%_ }} _%>")
    lines.append("")

    # --- Section C: Non-EJS heading (outside EJS) ---
    if with_headings and random.random() < 0.5:
        lines.append(f"## 背景信息")
        lines.append(f"  - 这是独立于时间轴的信息")
        lines.append(f"  - 始终适用的设定")
        lines.append("")

    # --- Section D: Second EJS block with nested if/else ---
    if random.random() < 0.4:
        threshold2 = threshold + random.randint(10, 50)
        heading_inside2 = with_headings and random.random() < 0.4
        if heading_inside2:
            ejs_heading2 = random.choice(["关键事件", "转折点", "隐藏线索"])
            lines.append(f"<%_ if (getvar('stat_data.${var}') <= {threshold2}) {{ _%>")
            lines.append(f"## {ejs_heading2}")
            lines.append(f"  - 次要线索浮现")
            lines.append(f"<%_ }} else if (getvar('stat_data.${var}') <= {threshold2 + 30}) {{ _%>")
            lines.append(f"## {ejs_heading2}")
            lines.append(f"  - 关键转折点")
            lines.append(f"<%_ }} else {{ _%>")
            lines.append(f"## {ejs_heading2}")
            lines.append(f"  - 最终阶段")
            lines.append(f"<%_ }} _%>")
        else:
            lines.append(f"<%_ if (getvar('stat_data.${var}') <= {threshold2}) {{ _%>")
            lines.append(f"  - 次要线索浮现")
            lines.append(f"<%_ }} else if (getvar('stat_data.${var}') <= {threshold2 + 30}) {{ _%>")
            lines.append(f"  - 关键转折点")
            lines.append(f"<%_ }} else {{ _%>")
            lines.append(f"  - 最终阶段")
            lines.append(f"<%_ }} _%>")
        lines.append("")

    # --- Section E: Non-EJS trailing content ---
    if with_headings and random.random() < 0.4:
        lines.append(f"## 备注")
        lines.append(f"  - 此信息不随游戏变量改变")
        lines.append(f"  - 始终生效")

    return "\n".join(lines)


def generate_hybrid_content(entity: str) -> str:
    """Generate content designed to test heading/EJS boundary splitting.

    Guarantees at least one heading outside EJS and one heading inside EJS.
    """
    var = random.choice(EJS_VARS)
    t = random.randint(20, 80)

    lines = [
        f"<{entity}>",
        f"# {entity}",
        f"  - 基本信息，始终有效",
        f"",
        f"## 通用设定",
        f"  - 这些信息不随变量改变",
        f"  - 适用于所有阶段",
        f"",
        f"## 状态信息",
        f"<%_ if (getvar('stat_data.${var}') <= {t}) {{ _%>",
        f"  - 当前处于早期阶段",
        f"  - 数据值 {var} <= {t}",
        f"<%_ }} else {{ _%>",
        f"  - 进入后期阶段",
        f"  - 数据值 {var} > {t}",
        f"<%_ }} _%>",
        f"",
        f"## 固定备注",
        f"  - 此信息始终生效",
        f"</{entity}>",
    ]
    return "\n".join(lines)


def generate_heading_in_ejs_only(entity: str) -> str:
    """Generate content where ALL headings are inside EJS blocks.

    This tests the case where after splitting, the non-EJS content is empty
    and the entry should just be renamed to {name}-EJS.
    """
    var = random.choice(EJS_VARS)
    t = random.randint(30, 100)

    lines = [
        f"<%_ if (getvar('stat_data.${var}') <= {t}) {{ _%>",
        f"# {entity}（初期）",
        f"  - 初期设定内容",
        f"  - 仅在被条件选中时显示",
        f"<%_ }} else {{ _%>",
        f"# {entity}（后期）",
        f"  - 后期设定内容",
        f"  - 随着进度解锁",
        f"<%_ }} _%>",
    ]
    return "\n".join(lines)


def generate_plain_content(entity: str) -> str:
    """Generate content without EJS."""
    sections = random.randint(1, 3)
    lines = [f"# {entity}"]
    for _ in range(sections):
        subsection = random.choice(["概要", "背景", "能力", "关系", "事件", "性格"])
        lines.append(f"## {subsection}")
        num_facts = random.randint(1, 4)
        facts = random.sample([
            "这是一个重要的设定要素",
            "与主角有着密切关联",
            "在故事中起到关键作用",
            "拥有独特的能力或属性",
            "背后隐藏着不为人知的秘密",
            "来自古老的传说",
            "在现代社会中以特殊形式存在",
            "是多方势力争夺的焦点",
            "拥有强大的影响力",
            "曾经发生过重大变故",
        ], k=min(num_facts, 10))
        for fact in facts:
            lines.append(f"  - {fact}")
    return "\n".join(lines)


def generate_unclosed_ejs(entity: str) -> str:
    """Generate EJS content with intentionally unbalanced braces.

    Creates one of several error patterns:
    - Missing closing brace (extra { )
    - Missing opening brace (extra } )
    - Unclosed <%_ without matching _%>
    """
    var = random.choice(EJS_VARS)
    t = random.randint(30, 80)
    pattern = random.randint(0, 2)

    if pattern == 0:
        # Extra opening brace — no matching }
        return (
            f"# {entity}\n"
            f"  - 正常内容\n"
            f"<%_ if (getvar('stat_data.${var}') <= {t}) {{ _%>\n"
            f"  - 条件内容（未闭合）\n"
        )
    elif pattern == 1:
        # Extra closing brace — no matching {
        return (
            f"# {entity}\n"
            f"  - 正常内容\n"
            f"  - 多余内容\n"
            f"<%_ }} _%>\n"
        )
    else:
        # Nested brace depth stuck — one extra { inside EJS
        return (
            f"# {entity}\n"
            f"<%_ if (getvar('stat_data.${var}') <= {t}) {{ _%>\n"
            f"  - 嵌套开启 {{\n"
            f"<%_ }} _%>\n"
            f"  - 正常内容\n"
            f"## 关系\n"
            f"  - 始终有效的信息\n"
        )


def generate_undefined_behavior_content(entity: str) -> str:
    """Generate content that triggers undefined behavior scenarios.

    Edge cases:
    - Empty content
    - <%_ with no EJS tags in valid regions (stray <%_ text)
    - Single <%_ tag with no _%>
    """
    pattern = random.randint(0, 3)
    var = random.choice(EJS_VARS)

    if pattern == 0:
        # Empty / whitespace-only content
        return "  \n\n  "
    elif pattern == 1:
        # Stray <%_ in non-EJS context (not a valid EJS tag but contains <%_)
        return (
            f"# {entity}\n"
            f"  - 这条目含 <%_ 符号但非合法 EJS\n"
            f"  - 这是文本中的特殊标记 <percent_ 可能是误输入\n"
        )
    elif pattern == 2:
        # Single unclosed EJS tag
        return (
            f"# {entity}\n"
            f"  - 前置内容\n"
            f"<%_ if (getvar('stat_data.${var}') <= 50)\n"
            f"  - 后面内容\n"
        )
    else:
        # Normal-looking EJS but missing _%> on one branch
        return (
            f"# {entity}\n"
            f"<%_ if (getvar('stat_data.${var}') <= 50) {{ _%>\n"
            f"  - 条件A\n"
            f"<%_ }} else {{ _%>\n"
            f"  - 条件B（缺少闭合 _%>）\n"
        )


def generate_bracket_content(name: str, is_start: bool) -> str:
    """Generate content for bracket start/end entries."""
    tag = name if is_start else ""
    closing = "" if is_start else "/"
    lines = [f"<{closing}{tag}>"]
    if is_start:
        lines.append(f"# {name}")
        lines.append(f"  - 以下是关于{name}的设定")
    return "\n".join(lines)


def sync_extensions(entry: dict):
    """Sync top-level fields to extensions sub-object."""
    ext = entry["extensions"]
    ext["position"] = entry["position"]
    ext["depth"] = entry["depth"]
    ext["probability"] = entry["probability"]
    ext["useProbability"] = entry["useProbability"]
    ext["selectiveLogic"] = entry["selectiveLogic"]
    ext["role"] = entry["role"]
    ext["sticky"] = entry["sticky"]
    ext["cooldown"] = entry["cooldown"]
    ext["delay"] = entry["delay"]
    ext["vectorized"] = entry["vectorized"]
    ext["display_index"] = entry.get("displayIndex", 0)


def generate_original_data_entry(st_entry: dict) -> dict:
    """Generate a matching originalData entry."""
    return {
        "id": st_entry["uid"],
        "keys": st_entry["key"],
        "secondary_keys": st_entry["keysecondary"],
        "comment": st_entry["comment"],
        "content": st_entry["content"],
        "constant": st_entry["constant"],
        "selective": st_entry["selective"],
        "insertion_order": st_entry["order"],
        "enabled": not st_entry["disable"],
        "position": "before_char" if st_entry["position"] == 0 else "after_char",
        "use_regex": True,
        "extensions": {
            "position": st_entry["position"],
            "exclude_recursion": st_entry["excludeRecursion"],
            "display_index": st_entry.get("displayIndex", 0),
            "probability": st_entry["probability"],
            "useProbability": st_entry["useProbability"],
            "depth": st_entry["depth"],
            "selectiveLogic": st_entry["selectiveLogic"],
            "outlet_name": st_entry["outletName"],
            "group": st_entry["group"],
            "group_override": st_entry["groupOverride"],
            "group_weight": st_entry["groupWeight"],
            "prevent_recursion": st_entry["preventRecursion"],
            "delay_until_recursion": st_entry["delayUntilRecursion"],
            "scan_depth": st_entry["scanDepth"],
            "match_whole_words": st_entry["matchWholeWords"],
            "use_group_scoring": st_entry["useGroupScoring"],
            "case_sensitive": st_entry["caseSensitive"],
            "automation_id": st_entry["automationId"],
            "role": st_entry["role"],
            "vectorized": st_entry["vectorized"],
            "sticky": st_entry["sticky"],
            "cooldown": st_entry["cooldown"],
            "delay": st_entry["delay"],
            "match_persona_description": st_entry["matchPersonaDescription"],
            "match_character_description": st_entry["matchCharacterDescription"],
            "match_character_personality": st_entry["matchCharacterPersonality"],
            "match_character_depth_prompt": st_entry["matchCharacterDepthPrompt"],
            "match_scenario": st_entry["matchScenario"],
            "match_creator_notes": st_entry["matchCreatorNotes"],
            "triggers": st_entry["triggers"],
            "ignore_budget": st_entry["ignoreBudget"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Generate random World Book JSON")
    parser.add_argument("output", help="Output JSON path")
    parser.add_argument("-n", "--num-entries", type=int, default=60,
                        help="Number of entries (default: 60)")
    parser.add_argument("--ejs-prob", type=float, default=0.4,
                        help="Probability an entry contains EJS (default: 0.4)")
    parser.add_argument("--bracket-prob", type=float, default=0.3,
                        help="Probability of creating a bracketed section (default: 0.3)")
    parser.add_argument("--deep-prob", type=float, default=0.15,
                        help="Probability a position=4 entry has depth >= 10 (default: 0.15)")
    parser.add_argument("--bad-ejs-prob", type=float, default=0.0,
                        help="Probability an EJS entry has unbalanced braces (default: 0.0, opt-in)")
    parser.add_argument("--undefined-prob", type=float, default=0.0,
                        help="Probability an entry triggers undefined behavior (default: 0.0, opt-in)")
    parser.add_argument("--order-collision-prob", type=float, default=0.0,
                        help="Probability adjacent entries share order value (default: 0.0, opt-in)")
    parser.add_argument("--unclosed-bracket-prob", type=float, default=0.0,
                        help="Probability a bracket section lacks a closing bracket (default: 0.0, opt-in)")
    parser.add_argument("--position-weights", type=str, default="0:30,1:40,4:20,6:10",
                        help="Position weights as pos:weight,... (default: 0:30,1:40,4:20,6:10)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--no-original-data", action="store_true",
                        help="Do not generate originalData")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="[%(levelname)s] %(message)s", stream=sys.stderr)

    if args.seed is not None:
        random.seed(args.seed)
        logger.info("Random seed: %s", args.seed)

    # Parse position weights
    pos_weights = {}
    for pw in args.position_weights.split(","):
        p, w = pw.split(":")
        pos_weights[int(p)] = int(w)
    pos_list = list(pos_weights.keys())
    pos_wlist = [pos_weights[p] for p in pos_list]

    num_entries = args.num_entries
    ejs_prob = args.ejs_prob
    bracket_prob = args.bracket_prob
    deep_prob = args.deep_prob
    bad_ejs_prob = args.bad_ejs_prob
    undefined_prob = args.undefined_prob
    order_collision_prob = args.order_collision_prob
    unclosed_bracket_prob = args.unclosed_bracket_prob

    entries = []
    uid = 0
    order = 0

    # Track used names
    used_names = set()

    # Generate bracketed sections
    num_sections = 0
    target_sections = max(1, int(num_entries * bracket_prob / 8))
    while num_sections < target_sections and order < num_entries - 4:
        num_sections += 1
        sec_name = gen_section_name(used_names)
        used_names.add(sec_name)

        # Bracket start
        start_entry = copy.deepcopy(NEW_ENTRY_TEMPLATE)
        start_entry["uid"] = uid; uid += 1
        start_entry["comment"] = f"{sec_name}开始"
        start_entry["content"] = generate_bracket_content(sec_name, True)
        start_entry["constant"] = True
        start_entry["key"] = [sec_name]
        start_entry["order"] = order; order += 1
        start_entry["position"] = random.choice([0, 1])
        start_entry["depth"] = 4
        sync_extensions(start_entry)
        entries.append(start_entry)

        # Section entries
        sec_size = random.randint(2, 6)
        for _ in range(sec_size):
            if order >= num_entries - 1:
                break
            entity = gen_entity_name()

            entry = copy.deepcopy(NEW_ENTRY_TEMPLATE)
            entry["uid"] = uid; uid += 1
            entry["comment"] = f"{sec_name}：{entity}"
            entry["order"] = order; order += 1
            entry["position"] = random.choice([0, 1, 4])
            entry["depth"] = random.choice([1, 4, 10, 20]) if entry["position"] == 4 else 4
            if entry["depth"] >= 10 and random.random() > deep_prob:
                entry["depth"] = random.choice([1, 4])
            entry["key"] = [entity]
            entry["selective"] = random.choice([True, True, False])
            entry["constant"] = random.choice([True, False, False])

            if random.random() < ejs_prob:
                if random.random() < bad_ejs_prob:
                    entry["content"] = generate_unclosed_ejs(entity)
                elif random.random() < undefined_prob:
                    entry["content"] = generate_undefined_behavior_content(entity)
                else:
                    roll = random.random()
                    if roll < 0.25:
                        entry["content"] = generate_ejs_content(entity)
                    elif roll < 0.50:
                        entry["content"] = generate_hybrid_content(entity)
                    elif roll < 0.75:
                        entry["content"] = generate_heading_in_ejs_only(entity)
                    else:
                        entry["content"] = generate_ejs_content(entity, with_headings=False)
            elif random.random() < undefined_prob:
                entry["content"] = generate_undefined_behavior_content(entity)
            else:
                entry["content"] = generate_plain_content(entity)

            sync_extensions(entry)
            entries.append(entry)

        # Bracket end (optionally skipped for unclosed-bracket testing)
        if random.random() < unclosed_bracket_prob:
            logger.debug("跳过 bracket 闭合: %s结束", sec_name)
        else:
            end_entry = copy.deepcopy(NEW_ENTRY_TEMPLATE)
            end_entry["uid"] = uid; uid += 1
            end_entry["comment"] = f"{sec_name}结束"
            end_entry["content"] = f"</{sec_name}>"
            end_entry["constant"] = True
            end_entry["key"] = [sec_name]
            end_entry["order"] = order; order += 1
            end_entry["position"] = start_entry["position"]
            end_entry["depth"] = 4
            sync_extensions(end_entry)
            entries.append(end_entry)

    # Fill remaining entries (unbracketed)
    while order < num_entries:
        entity = gen_entity_name()

        entry = copy.deepcopy(NEW_ENTRY_TEMPLATE)
        entry["uid"] = uid; uid += 1
        entry["comment"] = entity
        entry["order"] = order; order += 1
        entry["position"] = random.choices(pos_list, weights=pos_wlist, k=1)[0]
        entry["depth"] = random.choice([1, 4, 10, 20]) if entry["position"] == 4 else 4
        if entry["depth"] >= 10 and random.random() > deep_prob:
            entry["depth"] = random.choice([1, 4])
        entry["key"] = [entity]
        entry["selective"] = random.choice([True, True, False])
        entry["constant"] = random.choice([True, False, False])

        if random.random() < ejs_prob:
            if random.random() < bad_ejs_prob:
                entry["content"] = generate_unclosed_ejs(entity)
            elif random.random() < undefined_prob:
                entry["content"] = generate_undefined_behavior_content(entity)
            else:
                roll = random.random()
                if roll < 0.25:
                    entry["content"] = generate_ejs_content(entity)
                elif roll < 0.50:
                    entry["content"] = generate_hybrid_content(entity)
                elif roll < 0.75:
                    entry["content"] = generate_heading_in_ejs_only(entity)
                else:
                    entry["content"] = generate_ejs_content(entity, with_headings=False)
        elif random.random() < undefined_prob:
            entry["content"] = generate_undefined_behavior_content(entity)
        else:
            entry["content"] = generate_plain_content(entity)

        sync_extensions(entry)
        entries.append(entry)

    # Ensure consistent order values (with optional collisions)
    for i, entry in enumerate(entries):
        entry["order"] = i

    # Inject order collisions for undefined-behavior testing
    collision_count = 0
    if order_collision_prob > 0:
        i = 1
        while i < len(entries):
            if random.random() < order_collision_prob:
                entries[i]["order"] = entries[i - 1]["order"]
                collision_count += 1
                i += 2  # skip the next to avoid triple collisions
            else:
                i += 1
        if collision_count > 0:
            logger.info("注入 order 碰撞: %s 处", collision_count)

    # Optionally inject an orphan bracket (开始 without 结束 or vice versa)
    orphan_bracket_count = 0
    if unclosed_bracket_prob > 0 and random.random() < unclosed_bracket_prob:
        orphan_bracket_count = 1
        orphan_name = gen_section_name(used_names)
        is_start = random.choice([True, False])
        orphan = copy.deepcopy(NEW_ENTRY_TEMPLATE)
        orphan["uid"] = uid; uid += 1
        if is_start:
            orphan["comment"] = f"{orphan_name}开始"
            orphan["content"] = generate_bracket_content(orphan_name, True)
        else:
            orphan["comment"] = f"{orphan_name}结束"
            orphan["content"] = f"</{orphan_name}>"
        orphan["constant"] = True
        orphan["key"] = [orphan_name]
        orphan["order"] = len(entries); entries.append(orphan)
        orphan["position"] = random.choice([0, 1])
        orphan["depth"] = 4
        sync_extensions(orphan)
        logger.debug("注入孤立 bracket: %s", orphan["comment"])

    # Build output
    result = {
        "entries": {str(i): e for i, e in enumerate(entries)},
    }

    if not args.no_original_data:
        original_name = os.path.basename(args.output).replace(".json", "").replace("_", " ")
        result["originalData"] = {
            "name": original_name,
            "entries": [generate_original_data_entry(e) for e in entries],
        }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Stats
    ejs_count = sum(1 for e in entries if "<%_" in e["content"])
    bracket_count = sum(1 for e in entries if e["comment"].endswith("开始") or e["comment"].endswith("结束"))
    pos4_deep = sum(1 for e in entries if e["position"] == 4 and e["depth"] >= 10)
    bad_brace = sum(1 for e in entries if _has_brace_mismatch(e.get("content", "")))
    undefined = sum(1 for e in entries if _is_undefined_content(e.get("content", "")))
    unclosed = sum(1 for e in entries if
                   (e["comment"].endswith("开始") and not _has_matching_end(e["comment"], entries))
                   or (e["comment"].endswith("结束") and not _has_matching_start(e["comment"], entries)))
    logger.info("生成完成: %s 条目", len(entries))
    logger.info("  EJS条目: %s", ejs_count)
    logger.info("  Bracket标记: %s", bracket_count)
    logger.info("  position=4且depth>=10: %s", pos4_deep)
    logger.info("  brace不对称: %s", bad_brace)
    logger.info("  未定义行为: %s", undefined)
    logger.info("  order碰撞: %s", collision_count)
    logger.info("  bracket不闭合: %s", unclosed + orphan_bracket_count)
    logger.info("  originalData: %s", '有' if not args.no_original_data else '无')
    logger.info("输出: %s", args.output)


def _has_matching_end(start_comment: str, entries: list) -> bool:
    name = start_comment.replace("开始", "")
    target = f"{name}结束"
    return any(e.get("comment") == target for e in entries)


def _has_matching_start(end_comment: str, entries: list) -> bool:
    name = end_comment.replace("结束", "")
    target = f"{name}开始"
    return any(e.get("comment") == target for e in entries)


def _has_brace_mismatch(content: str) -> bool:
    """Check if content has unbalanced brace pairs within EJS blocks."""
    tags = re.findall(r"<%_[^%]*_%>", content)
    depth = 0
    for tag in tags:
        depth += tag.count("{")
        depth -= tag.count("}")
    return depth != 0


def _is_undefined_content(content: str) -> bool:
    """Check if content exhibits undefined behavior patterns."""
    if not content or not content.strip():
        return True
    if "<%_" in content and "_%>" not in content:
        return True
    return False


if __name__ == "__main__":
    main()
