---
name: touchdesigner-kb-consultant
description: "在 TouchDesigner 相关任务中，先查本地知识库再生成方案的工作流。只要用户提到在 TouchDesigner 里创建、生成、搭建、组合、修改、自动生成任何节点、组件、网络、tox、toe、系统、效果、交互、工具链，或者要求给出 TouchDesigner 实现方案、节点选型、参数设置、版本兼容建议，都必须优先使用本技能。即使用户没有明确要求“查文档”，也要先用本技能完成版本判断、资料查证、可用节点确认，再继续输出创建方案。"
---

# TouchDesigner Knowledge-First Creation Guard

这个技能的目标不是直接替智能体“生成答案”，而是强制把 TouchDesigner 创建类任务变成“先查证、后生成”的工作流。

这样做的原因是：

- TouchDesigner 不同 build 之间节点和能力差异明显
- 官方文档里存在 stable / experimental 分流
- 直接凭记忆输出节点方案，容易出现幻觉、版本错配、错误参数和错误家族

因此，只要任务与 TouchDesigner 的创建、搭建、生成、改造有关，就先执行本技能。

## 适用任务

以下类型一律触发：

- 在 TouchDesigner 里创建某个效果、系统、装置逻辑、数据流、交互方案
- 生成节点网络、组件结构、tox、toe、模板、操作步骤
- 选择哪种 OP 家族、哪几个节点、哪些参数
- 判断某个节点、家族、方法、Python API 在指定版本是否可用
- 为用户已有需求生成 TouchDesigner 落地方案
- 把用户的自然语言需求翻译成 TouchDesigner 节点网络

以下情况也应触发：

- 用户没有给出版本，但希望你直接开始搭建
- 用户提到 POP、experimental、新节点、Python Class、Palette、导入导出、设备接入
- 用户要求“直接做方案”“别解释太多”“先搭一个出来”

## 内置资源

本技能已经把运行所需的知识库数据打包在技能目录内，优先使用这些内置资源，不依赖项目外部文件。

目录说明：

- `references/README.md`
	- 内置资源说明与推荐检索顺序
- `references/touchdesigner_kb/family_compatibility.jsonl`
	- OP 家族级版本兼容索引
- `references/touchdesigner_kb/version_compatibility.jsonl`
	- 实体级版本兼容索引
- `references/touchdesigner_kb/chunks.jsonl`
	- 切块后的检索语料
- `references/touchdesigner_kb/documents.jsonl`
	- 完整文档语料
- `references/touchdesigner_kb/assets_high_value.jsonl`
	- 高价值附件索引
- `references/touchdesigner_kb/stats.json`
	- 规模统计
- `scripts/query_kb.py`
	- 内置查询脚本

优先顺序：

1. 先用 `scripts/query_kb.py` 查询
2. 查询不到或需要上下文时，再直接读取 `references/touchdesigner_kb/*.jsonl`

## 固定工作流

### 第一步：确定目标版本

先从用户请求中识别目标 TouchDesigner 版本。

- 如果用户明确给出 build，例如 `2023.11600`，按该 build 判断
- 如果用户只说“2023 版”“2025 experimental”，按最接近的已知文档版本保守判断
- 如果用户没有给版本：
	- 默认采用保守策略
	- 只默认使用稳定文档里有明确证据的能力
	- 不默认使用 `experimental` 家族或仅在 experimental 中出现的能力
	- 在输出中明确写出版本假设

### 第二步：抽取计划使用的实体

把任务拆成待确认的实体：

- OP 家族，如 `TOP`、`CHOP`、`SOP`、`DAT`、`MAT`、`COMP`、`POP`
- 具体节点，如 `Add TOP`、`Feedback POP`
- Python Class，如 `addTOP Class`
- 关键机制，如 `Panel`、`DMX`、`OpenVR`、`Palette`、`TouchEngine`

如果用户只给目标效果，没有给节点名，也要先自己推导候选实体，再逐个验证。

### 第三步：先查版本兼容，再查正文内容

版本检查顺序必须固定为：

1. 先查 `references/touchdesigner_kb/family_compatibility.jsonl`
2. 再查 `references/touchdesigner_kb/version_compatibility.jsonl`
3. 确认实体可用后，才去查 `references/touchdesigner_kb/chunks.jsonl` 和 `references/touchdesigner_kb/documents.jsonl`

判断规则：

- 如果目标 build 早于家族首次出现版本，则该家族不可用
- 如果实体有 `earliest_explicit_build` 且目标 build 更早，则不默认可用
- 如果实体只在 `experimental` 有证据，而用户没有明确要求 experimental，则默认不采用
- 如果没有明确版本证据，必须在输出中标注“证据不足，保守不采用”或“证据不足，需人工确认”

### 第四步：收集创建所需证据

对每个候选实体，至少核实以下内容中的一部分：

- 它是否存在于目标版本
- 它属于哪个家族
- 它的用途是否匹配用户需求
- 关键参数、输入输出、限制条件是什么
- 是否存在更兼容的替代方案

优先从 `references/touchdesigner_kb/chunks.jsonl` 中取最相关段落，再用 `references/touchdesigner_kb/documents.jsonl` 做整页补充。

### 第五步：再生成方案

只有在完成版本与资料核实后，才允许输出创建方案。

方案必须基于已查证的节点与资料，不能凭印象补齐不存在的节点。

如果发现候选方案不兼容，应立即：

- 放弃不兼容节点
- 改用兼容家族或兼容节点
- 在方案中解释为何切换

## 输出要求

凡是创建类任务，输出中都应尽量包含以下结构：

### 1. 版本前提

- 用户指定版本，或你采用的默认版本假设
- 是否允许使用 experimental

### 2. 兼容性结论

- 哪些家族可用
- 哪些节点可用
- 哪些节点不可用
- 不可用时的替代路线

### 3. 文档依据

- 引用关键来源
- 尽量给出具体页面或知识库条目

### 4. 创建方案

- 采用哪些节点
- 节点之间如何连接
- 为什么这样选
- 需要关注哪些参数或限制

### 5. 风险与假设

- 哪些内容来自明确证据
- 哪些内容是保守推断
- 哪些需要用户实际在目标版本里再验证

## 决策原则

### 能保守就保守

如果版本不明确、证据不完整、页面版本下拉缺失，宁可降级到更老、更稳定、更常见的方案，也不要默认使用新家族或 experimental 能力。

### 不用未核实节点

没有经过版本索引或文档正文核实的节点，不要直接放进方案。

### 家族先行

如果家族本身在目标版本里都不存在，就不要继续讨论该家族下的具体节点。

### 创建前必须查

无论任务多简单，只要是在 TouchDesigner 中“创建东西”，都先查知识库。

## 推荐检索方式

优先使用内置查询脚本：

```bash
python3 scripts/query_kb.py families POP
python3 scripts/query_kb.py entities "feedback pop" --target-version 2023.11600
python3 scripts/query_kb.py chunks "add top"
python3 scripts/query_kb.py documents "particle trail"
```

如果需要做文本检索，优先围绕以下关键词组合查找：

- 用户目标效果名 + `TouchDesigner`
- 候选节点名
- 候选家族名
- `source_title`
- `supported_builds`
- `introduced_in_build`
- `compatibility_summary`

典型顺序：

1. 查家族是否可用
2. 查节点是否可用
3. 查节点的 Summary / Parameters / Inputs / Methods
4. 查是否有高价值附件或示例工程

## 遇到以下情况的处理方式

### 用户指定旧版本

旧版本优先检查：

- 家族是否存在
- 页面下拉里的最早 build
- 是否只有 experimental 才有对应能力

### 用户没有指定版本

默认按稳定文档保守生成，不主动引入 POP 或其他仅有 experimental 证据的内容。

### 用户要求使用某个节点，但该节点不兼容

不要硬用。直接说明不兼容，并给出兼容替代方案。

### 用户要求“直接做，不要查”

仍然先查。因为本技能的职责就是防止 TouchDesigner 方案出现版本和文档幻觉。

## 示例

**示例 1：**

用户请求：

```text
帮我在 TouchDesigner 2023.11600 里做一个粒子拖尾系统
```

处理方式：

- 先查 `POP` 家族是否可用于 `2023.11600`
- 若不可用，则不要使用 `POP`
- 改查 `TOP`、`SOP`、`CHOP` 是否能组合出替代方案
- 最终给出兼容版本的拖尾方案

**示例 2：**

用户请求：

```text
给我直接搭一个 POP 的点云处理网络
```

处理方式：

- 如果用户没有给版本，不默认采用 POP
- 先查 `references/touchdesigner_kb/family_compatibility.jsonl`
- 若 POP 仅在 experimental 中首次出现，则输出时说明该前提
- 若没有明确 experimental 前提，先询问版本不是必须，但要在回答里明确采用“保守不使用 POP”的默认策略，并给出非 POP 替代方案或提示需要 experimental 前提

## 自包含要求

本技能默认假设自己可能被单独分发给其他智能体环境，因此：

- 不要默认依赖工作区根目录中的 `touchdesigner_kb`
- 不要默认依赖工作区根目录中的 `touchdesigner_docs`
- 优先使用技能目录中的 `references/` 与 `scripts/`
- 只有当用户明确提供了新的本地知识库目录时，才允许切换到外部数据源

## 成功标准

使用本技能后，智能体在 TouchDesigner 创建任务中应做到：

- 先查证再生成
- 先判断版本再选节点
- 先排除不兼容家族再写方案
- 输出中有明确来源和版本前提
- 避免把新版本或 experimental 节点误用于旧版本方案
