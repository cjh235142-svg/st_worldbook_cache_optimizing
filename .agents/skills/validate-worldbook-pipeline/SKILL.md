---
name: validate-worldbook-pipeline
description: 执行世界书缓存优化管线并验证产物
license: MIT
compatibility: opencode, claude, cline, roo-code
---

# 世界书缓存优化管线 — 执行与验证

## 适用场景

对酒馆（SillyTavern）世界书执行 DeepSeek KV 缓存优化管线（`run_pipeline.py`），将世界书条目按动态/静态拆分、重排序、合并，使静态稳定内容进入缓存前缀、动态变化内容排在缓存断裂边界之后，以最大化缓存命中率。并系统性地验证优化产物的正确性。

## 管线结构

```
_analysis.json  →  分析结果（条目三态、拆分边界）
_split.json     →  拆分后条目
_reordered.json →  重排序 + 边界副本 + 补充包裹
_merged.json    →  最终产物 ★
```

## 工具

所有脚本通过 `python -m scripts.xxx` 调用：

| 命令 | 用途 |
|------|------|
| `scripts.run_pipeline` | 执行完整优化管线 |
| `scripts.tools.tool_validate` | XML/EJS 结构检查 + 管线完整性检查 |
| `scripts.tools.tool_query` | 类型筛选、统计摘要、产物完整性验证 |
| `scripts.tools.tool_diff` | 原始/优化后条目去向追踪 |

## 执行流程

### 步骤 1：运行管线

```bash
python -m scripts.run_pipeline -i <输入文件.json> -d <输出目录>
```

### 步骤 2：全链完整性

```bash
python -m scripts.tools.tool_validate \
    --pipeline-dir <输出目录> \
    --pipeline-name <文件名前缀>
```

| 检查点 | 期望 |
|--------|------|
| C1 产物文件完整 | 4 个产物文件均存在 |
| C2 条目数单调 | `split >= analysis`，`reordered >= split`，`merged <= reordered` |
| C3 备份存在 | 原始目录下存在 `.backup_*` 文件 |

### 步骤 3：最终产物完整性

```bash
python -m scripts.tools.tool_validate \
    -i <输出目录>/<前缀>_merged.json --pipeline-check
```

| 检查点 | 期望 |
|--------|------|
| P1 order 连续 | 从 0 到 N-1 |
| P2 uid 连续 | 从 0 到 N-1 |
| P3 无临时字段残留 | 无 `_is_static`、`_pair_id` 等 |
| P5 排序约束 | 所有静态条目均在动态条目之前 |

### 步骤 4：缓存结构评估

```bash
python -m scripts.tools.tool_query \
    -i <输出目录>/<前缀>_merged.json --summary-only
```

关键指标：

| 指标 | 含义 |
|------|------|
| `static + merged` 数量与 order 范围 | 缓存前缀长度 |
| `dynamic + boundary + supplement` 最小 order | 缓存断裂边界 |
| `temp_field_residue: none` | 输出清洁 |

### 步骤 5：XML/EJS 结构检查

```bash
python -m scripts.tools.tool_validate \
    -i <输出目录>/<前缀>_merged.json
```

注意：发现的错误需与原始文件对比。原始文件已有的 XML 跨标签、EJS 未闭合等问题不是管线引入的。

### 步骤 6：条目去向追踪

```bash
python -m scripts.tools.tool_diff \
    --original <原始文件.json> \
    --optimized <输出目录>/<前缀>_merged.json
```

查看汇总部分的拆分/合并/保持/新建数量是否合理。

### 步骤 7：动态条目属性检查

```bash
python -m scripts.tools.tool_query \
    -i <输出目录>/<前缀>_merged.json --search "getvar"
python -m scripts.tools.tool_query \
    -i <输出目录>/<前缀>_merged.json --search "<%"
```

所有动态条目应满足：`position=4`，`depth=0`，`role=1`。

## 通过标准

| 步骤 | 要求 |
|------|------|
| 2–4 | 0 error（backup 警告可接受） |
| 5 | 所有 error 均可在原始文件中复现 |
| 6 | 拆分+合并+保持 ≈ 原始条目数 |
| 7 | 100% 动态条目满足 pos=4, depth=0, role=1 |

## 注意事项

- 输入路径和输出目录均支持中文文件名
- 管线自动备份原始文件，备份在同目录下
- 输出目录不存在时自动创建
- 步骤 5 的 XML 错误中有部分属于已知误报：`<user>`、`<char>`、`<br>` 等宏/HTML 标签
