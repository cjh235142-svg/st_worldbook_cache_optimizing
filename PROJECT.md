# 酒馆世界书 (SillyTavern World Book) 优化工具

## 1. 核心目的

优化 SillyTavern 世界书的 **DeepSeek KV 缓存命中率**。

世界书部分条目的 content 含有 EJS 脚本（如 `<%_ if (getvar(...)) { _%>...<%_ } _%>`），这些内容随游戏状态变化。变化的内容打断 DeepSeek 的 prefix cache，导致每次生成都需重算大量 token。

**优化策略**：将不可变条目（无 EJS）放在 prompt 前面，可变条目（含 EJS）放在 prompt 最后，使前缀缓存复用全部不可变内容，仅末尾变化部分需重新计算。

---

## 2. 主要功能

| 功能 | 脚本 | 输入→输出 |
|------|------|----------|
| EJS 拆分 | `split_world_book_ejs.py` | 原始世界书 → `_split.json`（新增 -EJS 条目） |
| 重排优化 | `reorder_world_book.py` | `_split.json` → `_reordered.json`（重排序+配置+补充条目） |
| 同步 originalData | `sync_original_data.py` | `_reordered.json` → 覆盖同文件（entries→originalData 反向映射） |
| 随机测试生成 | `generate_random_world_book.py` | 输出指定条目的随机世界书（含边缘情况） |
| 调试输出 | `print_sorted_names.py` | 按排序输出条目名称列表 |
| 调试输出 | `print_sorted_entries.py` | 按排序输出条目名称+内容 |
| 流水线编排 | `run_all.py` | 串联 1→2→3 + 全部测试 |
| 压力测试 | `tests/stress_test.py` | 自动生成多类型随机世界书并全流程测试 N 轮 |

---

## 3. 完整需求清单

### 3.1 EJS 条目拆分

- [x] 按 Markdown 标题（`#`/`##`）为最小单位拆分 content
- [x] EJS if/else/elseif 块内不拆分（`{` `}` 配对的完整块）
- [x] 拆分后 non-EJS 条目 comment 不变，EJS 条目 comment 追加 `-EJS`
- [x] 除 uid、comment、content 外所有字段继承原条目
- [x] 全 EJS 条目（无非 EJS 段落）仅重命名，不创建新条目
- [x] 首行非标题（非 `#`/`##`，非 `<Tag>`）时不拆分，仅重命名为 `-EJS`
- [x] 首行是 `<%_`（EJS 标签）时不拆分，仅重命名
- [x] XML 标签包裹的条目（如 `<魔法>...</魔法>`），拆分后 EJS 条目包裹为 `<魔法补充>...</魔法补充>`
- [x] 无 EJS 条目保持原样不变

### 3.2 排序与配置优化

- [x] non-EJS 条目：`constant=true`（蓝灯），`cooldown=0`，`probability=100`
- [x] position=4（atDepth）条目：depth<10 → `(pos=4, depth=0, role=1)`，depth≥10 → `(pos=4, depth=9999, role=1)`
- [x] position≠4 条目：position/depth 保持原值不变
- [x] EJS 条目：`position=4, depth=0, role=1`，constant/selective 保持原值
- [x] 补充条目：`constant=false`（绿灯），`key=["/.+/"]`，`selectiveLogic=0`
- [x] 排序采用三档制（band）：band=0(depth≥10) < band=1(others) < band=2(depth<10)，档内 pos, -depth, order
- [x] depth 仅对 position=4（atDepth）条目参与排序
- [x] 所有 EJS 条目通过 OFFSET 放在 non-EJS 之后
- [x] non-atDepth 条目 role 不为 null
- [x] entries dict key 与 entry.uid 一致

### 3.3 补充条目（section bracket）

- [x] 识别开始/结束标记对（comment 匹配 `(.*)开始$`/`(.*)结束$`）
- [x] 区间内含 EJS 条目 → 创建补充开始/结束；无 EJS → 跳过
- [x] 补充条目 comment = "{原名称}补充开始"/"{原名称}补充结束"
- [x] 补充条目 content 保留 XML 标签或 Markdown 标题 + "补充"
- [x] bracket 可能是 EJS 条目（无需特殊处理）
- [x] 含"补充"的 comment 不参与 bracket 匹配（防重复优化）

### 3.4 originalData 同步

- [x] entries 修改后双向同步到 originalData.entries
- [x] 字段映射：keys, secondary_keys, insertion_order, enabled=`!disable` 等
- [x] 新增条目追加到 originalData，删除条目移除
- [x] character_filter 仅在已有时更新，不新增
- [x] role: null → 0（防止 ST 异常）
- [x] 默认保留 originalData，`--strip-original-data` 可移除

### 3.5 未定义行为检查

- [x] position≠4 同 order 不同 depth → WARNING
- [x] 同 (pos, depth_atDepth, order) → WARNING
- [x] bracket 未配对 → WARNING
- [x] EJS `<%_` 但无有效 EJS 区域 → WARNING
- [x] EJS brace 不平衡 → WARNING (split) / 测试 FAIL

### 3.6 测试覆盖

- [x] 拆分后格式合法性（entries dict、字段完整性、EJS 标签、brace 配对）
- [x] 重排后字段值（constant、cooldown、probability、depth、position、role）
- [x] 重排后同分区内相对顺序一致性
- [x] EJS 条目集合完整性与分区内顺序
- [x] non-EJS 全部在 EJS 之前
- [x] uid == dict key 一致性
- [x] originalData 同步后一致性
- [x] depth≥10 映射为 depth=9999
- [x] 随机生成器 + 压力测试（10 种配置，N 轮自动循环）

---

## 4. 当前实现细节

### 4.1 文件结构

```
ST/
├── scripts/
│   ├── world_book_utils.py            # 公共模块（字段映射、排序、日志、EJS 解析等）
│   ├── split_world_book_ejs.py        # Script 1: EJS 拆分
│   ├── reorder_world_book.py          # Script 2: 重排与配置优化
│   ├── sync_original_data.py          # Script 3: originalData 双向同步
│   ├── generate_random_world_book.py  # 随机世界书生成器
│   ├── print_sorted_names.py          # 输出排序后条目名称
│   └── print_sorted_entries.py        # 输出排序后条目名称+内容
├── tests/
│   ├── test_split.py                  # Test 1: 拆分后格式与 EJS 正确性
│   ├── test_reorder.py                # Test 2&3: 重排后格式、顺序、uid 对齐
│   ├── test_sync.py                   # Test 4: originalData 同步正确性
│   └── stress_test.py                # 压力测试（自动生成多配置随机书）
├── run_all.py                         # 一键流水线
└── PROJECT.md                         # 本文档
```

### 4.2 公共模块 `world_book_utils.py`

**数据结构：**

- `POSITION` / `ROLE` — 枚举常量（before=0, after=1, ANTop=2, ANBottom=3, atDepth=4, EMTop=5, EMBottom=6, outlet=7 / SYSTEM=0, USER=1, ASSISTANT=2）
- `ST_TO_ORIGINAL_KEY_MAP` — ST 字段→originalData 路径映射表（60+ 字段）
- `INVERT_MAP` — 取反字段映射（`disable`→`enabled`）

**文件 I/O：**

- `load_world_book(path)` / `save_world_book(path, data)` — JSON 读写（UTF-8 无 BOM）
- `get_entries_sorted(data)` / `set_entries_from_list(data, entries)` — dict↔list 互转

**EJS 解析：**

- `parse_ejs_regions(content)` — 通过 `<%_...%>` 标签和 `{``}` 嵌套深度追踪，返回 EJS 原子区域的 `[(start, end), ...]` 列表
- `is_inside_ejs(pos, regions)` — 判断位置是否在 EJS 区域内
- `find_markdown_headings(content)` — 找所有 `#`/`##` 标题行，返回 `[{start, end, level, text}]`

**排序 Key：**

- `atdepth_sort_key(entry, include_position)` — 最终排序 key，返回 `(band, pos, -depth, order)`。band：atDepth/depth≥10→0, others→1, atDepth/depth<10→2
- `dense_sort_key(entry)` — 密集编号 key，与 `atdepth_sort_key` 相同的三档逻辑

**Bracket 配对：**

- `find_bracket_pairs(entries)` — 按 comment 匹配 `(.*)开始$` / `(.*)结束$`，排除含"补充"的 comment，返回 `[(start_entry, end_entry), ...]`

**补充条目内容：**

- `extract_heading_only(content, heading_text)` — 从原始 bracket 条目提取标题格式：XML 标签 `<Tag>` → `<Tag补充>`，Markdown `# Title` → `# Title补充`

**日志：**

- `configure_logging(level)` / `add_log_level_arg(parser)` — 统一日志 bootstrap

---

### 4.3 Script 1: EJS 拆分 (`split_world_book_ejs.py`)

#### 主流程 `main()`

```
1. 加载 JSON → 获取 entries 列表
2. max_uid = 最大 uid
3. 遍历每个条目 → process_entry()
4. entries 列表中加入新创建的 -EJS 条目
5. set_entries_from_list() → 重编号 entries dict
6. 保存 JSON
```

#### `process_entry(entry, new_entries, max_uid) → int`

返回新的 max_uid。

```
分支 0: content 为空 → 直接返回 max_uid
分支 1: content 不含 "<%_" → 直接返回 max_uid（无 EJS）

分支 2: parse_ejs_regions() 返回空 → WARNING + 返回 max_uid（检测到 <%_ 但无有效区域）

分支 3: 首行检查
  取首行非空文本，判 is_xml(<Tag>) / is_md(# 开头) / is_ejs(<%_ 开头)
  若 is_ejs 或 (!is_xml && !is_md) → comment += "-EJS"，返回（全 EJS 仅重命名）

分支 4: 正常拆分
  a) 建立 ejs_mask[0..len-1] — True=在 EJS 区域内
  b) 找到所有 Markdown 标题（包括 EJS 区域内的）
  c) 收集所有 split point：0, len, 标题 start, EJS 边界
  d) 遍历 sorted split points 之间的段落：
     - 取段落文本（跳过空段）
     - 通过 mask 判断 is_ejs  → ejs_parts 或 non_ejs_parts
  e) 组装 non_ejs_content / ejs_content

分支 4.1: comment 已以 "-EJS" 结尾 → 跳过（防重复处理）

分支 4.2: non_ejs_content 为空（全 EJS）
  - _detect_xml_tag(content) → 若有 XML 标签：
       _wrap_xml_supplement(tag, content) → <tag补充>...EJS内容...</tag补充>
  - comment += "-EJS"，返回

分支 4.3: 正常拆分（混合）
  - entry.content = non_ejs_content
  - new_entry = deepcopy(entry)，uid=max_uid+1, comment+="-EJS"
  - _detect_xml_tag(content) → 若有：new_entry.content = <tag补充>ejs_content</tag补充>
    若无：new_entry.content = ejs_content
  - new_entries.append(new_entry)
```

#### 辅助函数

- `_detect_xml_tag(content)` — 检查首行 `<Tag>` 和末行 `</Tag>` 是否配对，返回 tag 名
- `_wrap_xml_supplement(tag, content)` — 剥去原 `<Tag>/</Tag>` 包裹，换上 `<Tag补充>/</Tag补充>`

---

### 4.4 Script 2: 重排优化 (`reorder_world_book.py`)

#### 主流程 `main()`

```
S0: 未定义行为检查（密集编号前）
  _check_order_collisions(entries)
  对每个条目取 (pos, depth仅atDepth, order) → 若重复则 WARNING

S1: 密集编号
  entries.sort(key=dense_sort_key)
  每个条目 order = seq; _seq = seq
  T = len(entries)

S2: OFFSET
  OFFSET = T

S3: 分类
  non_ejs = 不含 -EJS 的条目
  ejs_list = 含 -EJS 的条目
  bracket_pairs = find_bracket_pairs(entries)（排除含"补充"的 comment）

S4: 字段调整 _apply_field_adjustments()
  对 non_ejs：
    - 跳过含"补充"的条目
    - constant=true, cooldown=0, probability=100, useProbability=true, selective=true
    - 若 position==atDepth:
        depth<10 → depth=0, role=USER; depth≥10 → depth=9999, role=USER
    - 否则: role = role or SYSTEM（防 null）
  对 ejs_list：
    - position=atDepth, depth=0, role=USER
    （constant/selective 保持原值）

S5: 补充条目 _create_supplement_entries()
  遍历每个 bracket_pair(start_entry, end_entry):
    用 _seq 找出区间内 ejs_list 中的 EJS 条目 (section_ejs)
    分支 A: section_ejs 为空 → log skip
    分支 B: min_seq<=start_order 或 max_seq>=end_order → WARNING skip
    分支 C: 创建补充条目
      - supp_start = deepcopy(start_entry), supp_end = deepcopy(end_entry)
      - uid: 新 uid
      - comment: "{section_name}补充开始" / "{section_name}补充结束"
      - constant=false, selective=true, key=["/.+/"], selectiveLogic=0
      - position=atDepth, depth=0, role=USER
      - probability=100, useProbability=true
      - order=offset + (min_seq-1) / offset + (max_seq+1)
      - content = extract_heading_only(原始bracket的content, section_name)

S6: 最终排序
  all_entries.sort(key=atdepth_sort_key)
  排序结果：(band=0) atDepth/depth≥10 → (band=1) others → (band=2) atDepth/depth<10

S7: extensions 同步
  sync_extensions(entry) → extensions 子字段与顶层字段对齐

S8: uid 对齐 + 清理
  每个条目 uid = index（列表位置）
  清理 _orig_uid, _seq（内部追踪字段）
  set_entries_from_list() → 写入 JSON
```

#### `_check_order_collisions(entries)`

```
对每个条目取 collision_key = (pos, depth if atDepth else None, order)
若 collide_key 已存在 → WARNING（同 position+order 但不同 depth 的未定义行为）
```

#### `_apply_field_adjustments(non_ejs, ejs_list)`

```
non_ejs 循环：
  跳过 "补充" comment 条目
  constant=true, cooldown=0, probability=100, useProbability=true, selective=true
  若 position==atDepth:
    depth<10 → depth=0, role=USER
    depth≥10 → depth=9999, role=USER
  否则:
    role = role or SYSTEM  （null→0）

ejs_list 循环：
  position=atDepth, depth=0, role=USER
  （constant/selective 不变）
```

#### `_create_supplement_entries(entries, ejs_list, bracket_pairs, offset, start_uid)`

```
遍历每个 (start_entry, end_entry):
  1. 用 _seq 在 ejs_list 中筛选：start_order < _seq < end_order
  2. 若为空 → skip
  3. min_seq = min(_seq), max_seq = max(_seq)
  4. 若 min_seq≤start_order 或 max_seq≥end_order → WARNING skip
  5. 创建 supp_start:
     - deepcopy(start_entry)
     - uid=新值, comment="{name}补充开始"
     - constant=false, selective=true, key=["/.+/"], selectiveLogic=0
     - position=atDepth, depth=0, role=USER
     - probability=100, useProbability=true
     - order = offset + (min_seq - 1)
     - content = extract_heading_only(start_entry["content"], section_name)
  6. 创建 supp_end: 同上但 order=offset+(max_seq+1), comment="{name}补充结束"
```

---

### 4.5 Script 3: originalData 同步 (`sync_original_data.py`)

#### 主流程 `main()`

```
1. 检查 originalData 是否存在 → 无则跳过
2. 建立 orig_by_uid 映射：id → originalData index
3. 遍历 ST entries：
   匹配到 → _st_to_original_update()  更新现有
   未匹配 → _st_to_original_new()     创建新记录
4. 移除 originalData 中已不存在的 uid
5. 保存（覆盖写入）
```

#### `_st_to_original_update(st_entry, orig_entry)`

```
字段映射：
  直接映射：id=uid, keys=key, secondary_keys=keysecondary,
           comment, content, constant, selective,
           insertion_order=order, enabled=!disable
  ST_TO_ORIGINAL_KEY_MAP 遍历 → set_nested_value(orig, orig_path, value)
  INVERT_MAP 处理（disable→enabled 取反）
  character_filter → character_filter（仅当 orig 已有此字段时更新）
  _ensure_extensions()  → 填充 extensions 默认值
  position 0/1 → top-level position 设为 before_char/after_char
```

#### `_st_to_original_new(st_entry) → dict`

```
特殊处理：
  - role 为 None → 写入 0（SQL null 兼容）
  - character_filter 仅当有实际过滤内容(names/tags/isExclude)时才创建
  - extensions 所有字段 fill default
```

#### `_ensure_extensions(orig_entry)`

```
extensions 默认值填充（25+ 个字段，setdefault 保证不覆盖已有值）：
  position(取 top-level position), depth=4, probability=100,
  selectiveLogic=0, role=0, vectorized=false,
  sticky=cooldown=delay=0, triggers=[], ignore_budget=false,
  match_* 系列 = false, scan_depth/case_sensitive/match_whole_words=null
```

---

### 4.6 排序 Key 定义

**`dense_sort_key(entry)`** — 密集编号用（`split_world_book_ejs.py` 中 `process_entry` 也使用的 S1 排序标准）

```
返回 (band, pos, -depth, order)
  pos==4 (atDepth):
    depth>=10 → band=0
    depth<10  → band=2
  pos!=4 → band=1

作用：三个 band 内先按 position、再按 depth DESC、最后 order ASC 排序
```

**`atdepth_sort_key(entry, include_position=True)`** — 最终排序用（`print_sorted_*.py` / `test_reorder.py` 共用的 S6 排序标准）

```
与 dense_sort_key 相同逻辑，include_position=False 时去掉 pos 维度
```

**S1 只排序不重编号 depth/position → S6 重编号后输出：**

- band=0: pos=4, depth≥10 的条目（插入位置很深/无法确定，放在最前）
- band=1: 所有其他 position 的条目（中间位置，顺序与原始一致）
- band=2: pos=4, depth<10 的条目（插入位置很浅/变化较大，放在最后）

---

### 4.7 SillyTavern prompt 中的位置与排序解释

ST 的 prompt 组装流程（`world-info.js:5082-5144`）：

1. 所有激活条目按 `order` DESC 排序
2. 迭代每条目 → `unshift` 到对应 position 分组数组
3. position=0 (before) 位于整个 prompt 顶部（聊天之前）
4. position=4 (atDepth) 按 (depth, role) 分组，插入到对应聊天深度
5. position=1 (after) 位于 prompt 底部（聊天之后）

**depth 仅对 position=4 参与排序**。position≠4 的条目 depth 值不影响 prompt 中的位置（它们之间仅靠 order 排序）。两个 position≠4 的条目若 order 相同但 depth 不同，产生未定义行为（WARNING）。

**三档制 (band) 解释：**

- depth≥10 的 atDepth 条目插入到很深的聊天位置（如 depth=9999 几乎在 prompt 末端），虽然它们的 chat-relative 位置可能不确定，但为缓存优化将它们排在所有条目前面（band=0）保证不被经常变化的聊天内容打断缓存
- 所有其他条目（band=1）保持原有相对顺序
- depth<10 的 atDepth 条目插入到浅层聊天位置（如 depth=0 紧跟第一条消息后），变化可能性大，放在最后（band=2）减少缓存断裂

---

### 4.8 `run_all.py` 流水线

```
1. 备份原始文件（--no-backup 跳过）
2. Script 1: split_world_book_ejs.py → _split.json
3. Test 1: test_split.py
4. Script 2: reorder_world_book.py → _reordered.json
5. Test 2&3: test_reorder.py
6. Script 3: sync_original_data.py → 覆盖 _reordered.json
7. 可选剥离 originalData（--strip-original-data）
8. 复制 _reordered.json → 输入文件
9. Test 4: test_sync.py
10. 清理中间产物（--keep-intermediate 保留）
```

---

### 4.9 字段调整总表（Script 2 输出）

| 条目类型 | constant | cooldown | probability | position | depth | role |
|---------|----------|----------|------------|----------|-------|------|
| non-EJS (pos≠4) | true | 0 | 100 | 保持 | 保持 | 保持/0 |
| non-EJS (pos=4, orig<10) | true | 0 | 100 | 4 | 0 | 1 |
| non-EJS (pos=4, orig≥10) | true | 0 | 100 | 4 | 9999 | 1 |
| EJS | 保持 | 保持 | 保持 | 4 | 0 | 1 |
| 补充(新) | false | 继承 | 100 | 4 | 0 | 1 |
