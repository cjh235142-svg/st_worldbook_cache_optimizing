import json
import re
import shutil
from datetime import datetime
from pathlib import Path


DYNAMIC_MARKER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("<% if", re.compile(r"<%[-_]?\s*if\b")),
    ("<%=", re.compile(r"<%=")),
    ("<%-", re.compile(r"<%-")),
    # <%# EJS 注释不影响输出，不在动态标记列表中
    ("<%", re.compile(r"<%(?![-=#])\s*")),
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
    ("{{random", re.compile(r"\{\{random\b")),
    ("{{roll", re.compile(r"\{\{roll\b")),
    ("{{format_message_variable", re.compile(r"\{\{format_message_variable\b")),
    ("{{input}}", re.compile(r"\{\{input\}\}")),
    ("{{lastMessage}}", re.compile(r"\{\{lastMessage\}\}")),
    ("{{lastMessageId}}", re.compile(r"\{\{lastMessageId\}\}")),
    ("{{lastUserMessage}}", re.compile(r"\{\{lastUserMessage\}\}")),
    ("{{lastCharMessage}}", re.compile(r"\{\{lastCharMessage\}\}")),
    ("{{bias", re.compile(r"\{\{bias\b")),
    ("{{inject", re.compile(r"\{\{inject")),
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
    """移除 JavaScript 代码中的字符串字面量和注释，只保留代码骨架。

    处理 ' " ` 三种字符串、// 行注释、/* */ 块注释。
    将字符串/注释替换为等长空格以保持行号不变。

    Args:
        code: EJS 代码片段。

    Returns:
        去除了字符串字面量和注释后的纯代码。
        返回值长度等于输入长度（替换为空格以保持行号不变）。

    Notes:
        不处理正则表达式字面量（/pattern/），
        因世界书 EJS 中几乎不出现含 { } 的正则，无实际影响。
    """
    assert isinstance(code, str), f"code must be str, got {type(code)}"
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
    """统计 EJS 代码中 { 数 - } 数的差值。

    用于追踪 EJS 复合块的 brace 深度。
    先剥离字符串字面量以避免误计字符串内的花括号。

    Args:
        ejs_code: EJS 块的主体代码（不含 <% %> 标记）。

    Returns:
        { 数量 - } 数量的差值。
        正数表示开括号多于闭括号（深度增加），
        负数表示闭括号多于开括号（深度减少）。

    Notes:
        差值范围通常不超过 ±10（代码块内 brace 深度）。
    """
    assert isinstance(ejs_code, str), f"ejs_code must be str, got {type(ejs_code)}"
    clean = _strip_string_literals(ejs_code)
    result = clean.count("{") - clean.count("}")
    assert -20 < result < 20, f"brace delta out of range: {result}"
    return result


def detect_markers(content: str) -> list[str]:
    """扫描 content 中所有动态标记，返回匹配的标记名称列表。

    遍历 DYNAMIC_MARKER_PATTERNS 中的 (名称, 正则) 对，
    对每个正则执行 pat.search(content)，若匹配则记录名称。

    Args:
        content: 条目的 content 文本。

    Returns:
        命中的动态标记名称列表。未命中时返回空列表。
        静态宏（{{char}}, {{user}} 等）不在匹配范围内。

    Notes:
        纯函数，无副作用。不修改 content。
        正则匹配默认大小写敏感。
        不区分单行跨行：search 在全文搜索。
    """
    assert isinstance(content, str), f"content must be str, got {type(content)}"
    markers = []
    for name, pat in DYNAMIC_MARKER_PATTERNS:
        if pat.search(content):
            markers.append(name)
    return markers


def determine_static(content: str) -> bool:
    """判断 content 是否为纯静态内容（不含任何动态标记）。

    动态标记定义见 DYNAMIC_MARKER_PATTERNS，包括 EJS、变量宏等。
    {{char}}, {{user}} 等静态宏不影响判定结果。

    Args:
        content: 条目的 content 文本。

    Returns:
        True = 纯静态，False = 包含至少一个动态标记。
    """
    assert isinstance(content, str)
    result = len(detect_markers(content)) == 0
    assert isinstance(result, bool)
    return result


def has_special_plugin(content: str, comment: str = "") -> bool:
    """检测条目是否包含提示词模板插件或小白X插件的特殊标记。

    检查 comment 中的前缀（[GENERATE:BEFORE] 等）和
    content 中的装饰器行（@@preprocessing 等）。

    Args:
        content: 条目的 content 文本。
        comment: 条目的 comment（标题）。

    Returns:
        True = 含特殊插件标记，不应由管线自动处理。

    Notes:
        插件标记条目在分析阶段即标记为 suggested_split=false。
    """
    assert isinstance(content, str)
    assert isinstance(comment, str)
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
    """移除所有 EJS 块标记（<% ... %>）及其内部内容。

    匹配 <% % = - _ # 开头的 EJS 块，用 DOTALL 模式跨行匹配。

    Args:
        content: 原始文本。

    Returns:
        移除了所有 EJS 块后的纯文本。
    """
    assert isinstance(content, str)
    return re.sub(r"<%[-_=#]?.*?%>", "", content, flags=re.DOTALL)


def _strip_macros(content: str) -> str:
    """移除所有酒馆宏（{{ ... }}）。

    使用非贪婪匹配，不检查宏名称合法性。

    Args:
        content: 原始文本。

    Returns:
        移除了所有宏后的纯文本。
    """
    assert isinstance(content, str)
    return re.sub(r"\{\{.*?\}\}", "", content)


def _strip_ejs_and_macros(content: str) -> str:
    """先后移除 EJS 块和宏标记，保留纯文本静态内容。

    用于 classify_entry 中判定混合条目是否有静态残留。
    先 strip EJS 再 strip macro，顺序固定不可交换
    （EJS 块内可能包含宏标记，需先剥外层）。

    Args:
        content: 原始文本。

    Returns:
        同时移除了 EJS 块和宏标记后的纯文本。
    """
    assert isinstance(content, str)
    content = _strip_ejs_blocks(content)
    content = _strip_macros(content)
    return content


_EJS_OPEN_RE = re.compile(r"<%(?:[_=#-])?")


def parse_content_blocks(content: str) -> list[dict]:
    """将 content 按 <% ... %> 边界切分为 text/ejs 交替块序列。

    每行优先检测是否包含 EJS 起始标记（<%），若有则将其及后续
    行合并为单一 EJS 块，直到匹配到 %> 为止。
    无 EJS 标记的行作为纯文本块。
    每个 EJS 块计算 brace_delta（{ 数 - } 数）。

    Args:
        content: 原始 content 文本。

    Returns:
        list[dict]，每项含 type/text 块为 "ejs"/"text"、
        content（不含 <% %> 标记的代码体）、
        start_line/end_line（0-based 行号）、
        brace_delta（仅 ejs 块有效，text 块为 0）。

    Notes:
        交替序列保证：相邻块的 type 不同（text/ejs 交替）。
        行覆盖保证：起止行号从 0 到末尾。
        跨行 EJS 块合并为单一块，行号为起始到结束。
        若 <% 后无 %>，视为块延伸到文件末尾。
    """
    assert isinstance(content, str)
    lines = content.splitlines(keepends=True)
    blocks = []
    i = 0
    # Loop invariant: i < len(lines)，已处理前 i 行
    while i < len(lines):
        line = lines[i]
        m = _EJS_OPEN_RE.search(line)
        if m:
            ejs_begin = m.start()
            body_start = m.end()
            if "%>" in line[ejs_begin + 2:]:
                end_idx = line.rfind("%>", ejs_begin + 2)
                ejs_body = line[body_start:end_idx]
                blocks.append({"type": "ejs", "content": ejs_body.strip(),
                               "start_line": i, "end_line": i,
                               "brace_delta": count_net_braces(ejs_body)})
                i += 1
                continue
            else:
                j = i + 1
                while j < len(lines):
                    if "%>" in lines[j]:
                        break
                    j += 1
                raw = "".join(lines[i:j + 1]) if j < len(lines) else "".join(lines[i:])
                m2 = _EJS_OPEN_RE.search(raw)
                ejs_start = m2.end() if m2 else len(raw)
                ejs_end = raw.rfind("%>")
                if ejs_end == -1:
                    ejs_end = len(raw)
                ejs_body = raw[ejs_start:ejs_end]
                blocks.append({"type": "ejs", "content": ejs_body.strip(),
                               "start_line": i, "end_line": j if j < len(lines) else len(lines) - 1,
                               "brace_delta": count_net_braces(ejs_body)})
                i = j + 1
                continue
        else:
            blocks.append({"type": "text", "content": line,
                           "start_line": i, "end_line": i, "brace_delta": 0})
            i += 1
    return blocks


def find_ejs_compound_ranges(content: str) -> list[tuple[int, int]]:
    """追踪 EJS brace 深度，返回复合块的行范围列表。

    从深度 > 0 开始，到深度 == 0 结束，形成一个复合块。
    复合块涵盖了一个完整的 EJS 控制结构（如 if/else/for）的
    所有行，包括其间的静态输出文本。

    Args:
        content: 原始 content 文本。

    Returns:
        [(start_line, end_line), ...] 每个复合块的行范围。
        若无复合块（所有 EJS 深度为 0），返回 []。
        范围按 start_line 递增、不重叠。

    Notes:
        若 brace 最终未归零（未闭合），最后一个范围延伸到末尾。
        不清理/修改 content。
    """
    assert isinstance(content, str)
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
    """判断 content 的所有行是否都被 EJS 复合块覆盖。

    用于 classify_entry：若全部行都在复合块内，
    则该条目不可拆分（复合块全覆盖=纯动态）。

    Args:
        content: 原始 content 文本。
        compound_ranges: find_ejs_compound_ranges 的输出。

    Returns:
        True = 每一行都落在至少一个复合块范围内。
    """
    assert isinstance(content, str)
    assert isinstance(compound_ranges, list)
    lines = content.splitlines(keepends=True)
    if not lines:
        return True
    total = len(lines)
    covered = [False] * total
    for s, e in compound_ranges:
        for i in range(max(0, s), min(e + 1, total)):
            covered[i] = True
    return all(covered)


def is_ejs_unclosed(content: str) -> bool:
    """检查 EJS brace 深度在内容末尾是否未归零（即未闭合）。

    用于 analyze_entries 的拆分守卫：
    若 EJS 未闭合，混合条目不应被拆分（拆分会产生破碎 EJS）。

    Args:
        content: 原始 content 文本。

    Returns:
        True = EJS brace 深度未归零（有未闭合的 if/for/while 等）。
        False = 深度归零或无 EJS 内容。

    Notes:
        即使 EJS 块未闭合，只要无标记残留（纯动态），
        classify_entry 已能正确判定为纯动态。
        此函数针对混合条目中的未闭合情况做二次保护。
    """
    assert isinstance(content, str)
    blocks = parse_content_blocks(content)
    depth = 0
    # Loop invariant: depth = 已处理 EJS 块的累计 brace delta
    for block in blocks:
        if block["type"] == "ejs":
            depth += block["brace_delta"]
    result = depth != 0
    assert isinstance(result, bool)
    return result


def _is_line_in_ranges(line_idx: int, ranges: list[tuple[int, int]]) -> bool:
    """判断行号是否落在任一 [start, end] 区间内。

    用于 analyze_entries 的边界检测：判断标题行是否在 EJS 复合块范围内。

    Args:
        line_idx: 0-based 行号。
        ranges: [(start, end), ...] 区间列表。

    Returns:
        True = 行号在任一区间内。
    """
    for s, e in ranges:
        if s <= line_idx <= e:
            return True
    return False


def classify_entry(content: str) -> tuple[bool, bool]:
    """对条目 content 进行三态判定：纯静态 / 纯动态 / 混合。

    判定过程：
    1. 无动态标记 → 纯静态 (True, False)
    2. 剥离 EJS+宏后无残留 → 纯动态 (False, False)
    3. 有残留但被 EJS 复合块完全覆盖 → 纯动态（不可拆分）
    4. 有残留且未被完全覆盖 → 混合可拆分 (False, True)

    Args:
        content: 条目的 content 文本。

    Returns:
        (is_static, is_mixed): 两者不可同时为 True。
        (True, False) = 纯静态，(False, False) = 纯动态，
        (False, True) = 混合（可能可拆分）。

    Notes:
        不判断是否可拆分（由调用方基于 suggested_split 决定）。
        不检查 EJS 是否闭合（由 is_ejs_unclosed 补充）。
    """
    assert isinstance(content, str)
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
    """识别 content 中所有成对的 XML 包裹标签。

    使用栈匹配，处理嵌套标签。仅匹配含中文或英文的标签名。
    自闭合标签（<X/>）和未闭合标签不在结果中。

    Args:
        content: 搜索文本。

    Returns:
        [{"tag": str, "open_start": int, "close_end": int}, ...]
        按 open_start 递增排序。

    Notes:
        不处理 <!DOCTYPE>、<?xml?>、<!-- comment --> 等非标签语法。
        自闭合标签（<br/>、<hr/>）不匹配。
    """
    assert isinstance(content, str)
    results = []
    tag_re = re.compile(r"<([\u4e00-\u9fff\w]+)>")
    close_re = re.compile(r"</([\u4e00-\u9fff\w]+)>")
    stack = []
    pos = 0
    # Loop invariant: stack 中始终保存未闭合的开标签（标签名, 位置）
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
    """返回 content 中最外层成对 XML 标签名（跨度最大者）。

    用于 split_boundaries 的 wrap_tag 分配：确定包裹整个条目的
    最外层标签。选择标准为 close_end - open_start 最大的标签。

    Args:
        content: 搜索文本。

    Returns:
        最外层标签名，若无可配对标签则返回 None。

    Notes:
        当有多个并列外层标签时，选择跨度最大者。
        仅含一层标签时等价于该标签名。
    """
    assert isinstance(content, str)
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
    """按 # / ## 标题边界将 content 切分为段落。

    每个标题行（# 或 ##）开始一个新段落，前一段落在
    新标题前结束。首个标题前的文本作为无标题段落。

    Args:
        content: 原始 content 文本。

    Returns:
        [{"heading_level": int|None, "heading_text": str,
          "start_line": int, "end_line": int}, ...]
        按 start_line 递增排列。
        段落覆盖全部行且不重叠：下一段 start_line = 前一段 end_line + 1。

    Notes:
        不处理 ### 三级标题（仅 H1/H2 作为拆分边界）。
        空内容返回一个覆盖行 0~0 的段落。
    """
    assert isinstance(content, str)
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
    """判断段落是否无实质内容（仅含空白、标题行、空 XML 标签）。

    用于拆分过程中的空段落过滤：先剥离 XML 标签和 Markdown 标题，
    再 strip 空白，剩余为空则视为无意义段落。

    Args:
        segment: 段落文本。

    Returns:
        True = 无实质内容应丢弃，False = 有实质文本保留。

    Notes:
        正则只匹配含中英文的 XML 标签（<御坂美琴>、</角色>），
        不匹配 HTML 注释、EJS 块、比较表达式中的 <...>。
    """
    assert isinstance(segment, str)
    clean = re.sub(r"</?[\u4e00-\u9fff\w]+>", "", segment)
    clean = re.sub(r"^#{1,2}\s.*$", "", clean, flags=re.MULTILINE)
    clean = clean.strip()
    return clean == ""


def get_default_entry_fields() -> dict:
    """返回世界书条目的默认字段字典。

    默认值来自 SillyTavern 源码 world-info.js 的
    newWorldInfoEntryDefinition。
    用于 merge_entries 中 _merge_one_group 构建合并后的条目，
    覆盖部分字段保留合并前的属性。

    Returns:
        dict，包含酒馆世界书条目的全部标准字段及默认值。
    """
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
        "delayUntilRecursion": 0, "ignoreBudget": False,
        "group": "", "groupOverride": False, "groupWeight": 100,
        "outletName": "", "automationId": "", "vectorized": False,
        "addMemo": False, "triggers": [],
        "characterFilter": {"names": [], "tags": [], "isExclude": False},
        "displayIndex": None,
    }


def load_world_book(path: str | Path) -> dict:
    """从 JSON 文件加载世界书数据。

    读取指定路径的 JSON，返回包含 entries 字段的 dict。
    若 JSON 中无 entries，初始化为空字典。

    Args:
        path: JSON 文件路径。

    Returns:
        {"entries": {str: dict}}，entries 为 uid_str → entry 的映射。

    Raises:
        FileNotFoundError: 文件不存在。
        JSONDecodeError: JSON 格式非法（由 json.load 抛出）。

    Notes:
        不修改文件系统，只读。
    """
    assert path is not None
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "entries" not in data:
        data["entries"] = {}
    return data


def save_world_book(entries: dict | list, path: str | Path) -> None:
    """将世界书条目写入 JSON 文件。

    若 entries 为 list，自动转为 {str(i): entry} 字典格式。
    输出格式为 {"entries": {uid_str: entry, ...}}，indent=2。

    Args:
        entries: 条目列表（list[dict]）或已格式化的 dict。
        path: 输出 JSON 文件路径。

    Notes:
        自动创建父目录（若不存在）。
        只写入 entries 字段，丢弃所有其他顶层元数据。
    """
    assert isinstance(entries, (dict, list))
    assert path is not None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(entries, list):
        entries_dict = {str(i): e for i, e in enumerate(entries)}
    else:
        entries_dict = entries
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": entries_dict}, f, ensure_ascii=False, indent=2)


def backup_file(path: str | Path) -> str:
    """创建世界书 JSON 文件的备份副本。

    备份文件名为 {原名}.backup_{时间戳}{后缀}，
    与源文件位于同一目录。

    Args:
        path: 源文件路径。

    Returns:
        备份文件的绝对路径字符串。

    Notes:
        使用 shutil.copy2 保留文件元数据（mtime 等）。
    """
    assert Path(path).exists()
    path = Path(path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.parent / f"{path.stem}.backup_{ts}{path.suffix}"
    shutil.copy2(path, backup)
    return str(backup)


def reassign_uids(entries: list[dict]) -> list[dict]:
    """从 0 起连续重分配所有条目的 uid 和 displayIndex。

    保留原有顺序，将 uid 和 displayIndex 设为条目在列表中的索引。

    Args:
        entries: 条目列表，按需排序后可传入。

    Returns:
        修改后的 entries（就地修改，返回引用）。

    Notes:
        就地修改 entries，返回同一引用。
        此前若有 uid/displayIndex 值会被覆盖。
    """
    assert isinstance(entries, list)
    for i, e in enumerate(entries):
        e["uid"] = i
        e["displayIndex"] = i
    return entries


def reassign_orders(entries: list[dict]) -> list[dict]:
    """从 0 起连续重分配所有条目的 order。

    保留原有顺序，将 order 设为条目在列表中的索引。
    确保最终输出的 order 值连续无空洞。

    Args:
        entries: 条目列表，按需排序后可传入。

    Returns:
        修改后的 entries（就地修改，返回引用）。

    Notes:
        就地修改 entries，返回同一引用。
        之前设置的 order 值被覆盖。
    """
    assert isinstance(entries, list)
    for i, e in enumerate(entries):
        e["order"] = i
    return entries


def is_outlet_entry(entry: dict) -> bool:
    """判断条目是否为 outlet 类型（position=7）。

    outlet 条目通过 {{outlet::Name}} 宏显式引用，
    不参与自动注入，管线不对其做拆分或重排。

    Args:
        entry: 世界书条目 dict。

    Returns:
        True = outlet 条目。
    """
    assert isinstance(entry, dict)
    return entry.get("position") == 7


def override_entry_dynamic_status(entry: dict) -> None:
    """对边界副本和补充包裹条目强制将 _is_static 置为 False。

    这些条目虽然 content 纯静态（仅有标签/标题行），
    但在排序逻辑中应归入动态区（category=1）。

    Args:
        entry: 世界书条目 dict。

    Notes:
        就地修改 entry。
        被 tool_list.py 和 tool_list_full.py 调用，
        用于调试工具中正确归类条目。
    """
    assert isinstance(entry, dict)
    comment = entry.get("comment", "")
    key = entry.get("key", [])
    if "[boundary-copy-" in comment or "[supplement-" in comment or key == ["/.*/"]:
        entry["_is_static"] = False


def sort_entries(entries: list[dict]) -> list[dict]:
    """按 6 键排序，并注入排序所需的临时字段。

    6 键：(category, sub_order, stability, position, depth_key, _original_order)。
    详见 _sort_key 文档。

    注意：此函数会就地修改传入的 entries，为每个条目添加或
    setdefault _is_static、_original_order、_is_boundary_copy、
    _is_supplement 等临时字段。调用方应在输出前清理。

    Args:
        entries: 条目列表。

    Returns:
        排序后的新列表（sorted 返回新 list）。

    Notes:
        副作用：为每个条目 setdefault 临时字段。
        幂等：二次运行不会重复注入（setdefault 不覆盖）。
    """
    assert isinstance(entries, list)
    for e in entries:
        e.setdefault("_is_static", determine_static(e.get("content", "")))
        e.setdefault("_original_order", e.get("order", 100))
        e.setdefault("_is_boundary_copy", False)
        e.setdefault("_is_supplement", False)
    return sorted(entries, key=_sort_key)


def _sort_key(entry: dict) -> tuple:
    """6 键排序的 key 函数。

    排序优先级（全部升序）：
    1. category: 纯静态=0, 动态/副本/包裹=1
    2. sub_order: 包裹开=0, 条目=1, 包裹闭=2
    3. stability: pos4 depth>=10=0(核心), pos≠4=1(过渡), pos4 depth<10=2(变化)
    4. position: 按 0..7 自然排列
    5. depth_key: pos4 时 -depth（depth 越大越靠前），否则 0
    6. _original_order: 保持原始相对顺序

    Args:
        entry: 条目 dict，含 _is_static、_original_order 等临时字段。

    Returns:
        (category, sub_order, stability, pos, depth_key, original_order) 元组。

    Notes:
        不修改 entry。
        被 sort_entries 作为 sorted() 的 key 参数调用。
    """
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
