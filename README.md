# 酒馆世界书 DeepSeek 缓存优化工具

## 免责声明

本项目由 DeepSeek AI 全程编写，未经人工全面审查，**无法完全保证正确性**。
使用前请自行审查代码逻辑，使用后请务必验证产物是否正确。

## 项目目的

优化 SillyTavern（酒馆）世界书（World Info）的结构，使其适配 DeepSeek API 的上下文缓存机制，提高多轮对话中的缓存命中率，降低推理成本与延迟。

## 实现方式

四步管线脚本：

1. **分析**（[analyze_entries](docs/实现/1-条目分析器.md)）：遍历世界书条目，检测是否含 EJS 模板、酒馆宏、变量引用等动态内容，判定三态（静态/动态/混合）
2. **拆分**（[split_entries](docs/实现/2-条目拆分器.md)）：将混合条目沿 Markdown 标题边界拆分为静态子条目和动态子条目，各自保留并重包裹 XML 标签
3. **重排序**（[reorder_entries](docs/实现/3-重排序与重映射.md)）：6 键排序将所有静态条目提到前缀区，动态条目推后到缓存断裂区；检测边界标签并创建副本；注入补充包裹隔离动态内容
4. **合并**（[merge_entries](docs/实现/4-静态条目合并器.md)）：同类型静态条目合并为一条，清空关键词，设为蓝灯常驻

详细设计文档：[docs/实现/脚本功能.md](docs/实现/脚本功能.md)

## 前置知识

参见 [docs/前置知识.md](docs/前置知识.md)，涵盖 DeepSeek 缓存机制、酒馆运行逻辑、世界书格式详解、ST-Prompt-Template 插件、小白X 插件等。

## 使用方式

### 快速开始

参见 [docs/使用/快速开始.md](docs/使用/快速开始.md)。

```bash
pip install pytest   # 可选，运行测试
python -m scripts.run_pipeline -i 世界书.json -d 输出目录
```

### 验证产物

```bash
# 全链检查
python -m scripts.tools.tool_validate \
    --pipeline-dir 输出目录 \
    --pipeline-name 世界书

# 最终产物完整性
python -m scripts.tools.tool_validate \
    -i 输出目录/世界书_merged.json --pipeline-check

# 缓存结构评估
python -m scripts.tools.tool_query \
    -i 输出目录/世界书_merged.json --summary-only

# 条目去向追踪
python -m scripts.tools.tool_diff \
    --original 世界书.json \
    --optimized 输出目录/世界书_merged.json
```

调试工具详细参考：[docs/实现/调试工具.md](docs/实现/调试工具.md)

### 使用 agent 辅助优化

在支持 `.agents/` 目录的 agent 工具（opencode、Cline、Roo Code 等）中，已内置优化与验证 skill：

```bash
# 在 agent 中加载 validate-worldbook-pipeline skill
# agent 将引导完成 执行管线 → 验证产物 → 确认结果 的完整流程
```

Skill 文件位于 `.agents/skills/validate-worldbook-pipeline/SKILL.md`，描述了 7 步验证工作流和通过标准。

### 逐脚本执行

```bash
python -m scripts.analyze_entries -i 世界书.json
python -m scripts.split_entries -i 世界书.json -a 世界书_analysis.json
python -m scripts.reorder_entries -i 世界书_split.json
python -m scripts.merge_entries -i 世界书_reordered.json
```

脚本 CLI 详细参考：[docs/使用/脚本参考.md](docs/使用/脚本参考.md)

### 运行测试

```bash
python -m pytest scripts/tests/ -v
```

参见 [docs/实现/单元测试.md](docs/实现/单元测试.md)、[docs/实现/集成测试.md](docs/实现/集成测试.md)。

## 产物文件

| 文件 | 说明 |
|------|------|
| `*_analysis.json` | 分析结果（条目三态、拆分边界） |
| `*_split.json` | 拆分后的子条目 |
| `*_reordered.json` | 重排序后的条目 |
| `*_merged.json` | **最终优化产物** |
| `*.backup_*.json` | 原始文件备份 |

## 常见问题

参见 [docs/使用/常见问题.md](docs/使用/常见问题.md)：

- 原始文件会被修改吗？— 不会
- 管线跑第二次会怎样？— 幂等
- 如何导入酒馆？— 导入 `_merged.json`
- 等等

## 注意事项

- 使用前备份原始世界书（管线会自动备份）
- 优化后务必在酒馆中验证对话效果并测试缓存命中率
- 原始文件中的 XML 跨标签问题会被检测但不会被修复
- 配置文件模板条目（outlet 类型）保持原样不变
- 如果遇到问题，请检查 `_merged.json` 中的 XML 标签配对是否完整
