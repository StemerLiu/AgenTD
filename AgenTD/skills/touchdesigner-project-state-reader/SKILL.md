---
name: touchdesigner-project-state-reader
description: 用于读取和理解 TouchDesigner 当前工程内容的独立技能。只要用户提到读取当前 TD 项目、先扫描再分析、刷新 OP_Information.json、刷新 OP_Framework.json、理解现有节点与参数、在编辑前先看现状、让 AI 理解当前工程结构，或要求先触发 SecretAgent 的 Updateinfo 信息收集流程，就应优先使用本技能。该技能先 pulse 根目录 /SecretAgent 的 Updateinfo 参数，再读取 OP_Information.json 与 OP_Framework.json，并根据用户需求做结构化分析。
---

# TouchDesigner Project State Reader

该技能用于在开始分析或编辑 TouchDesigner 工程之前，先把**当前工程真实状态**刷新并读出来。

它解决的问题不是“怎么改工程”，而是：

- 先触发一次 TouchDesigner 内部信息收集
- 拿到最新的 `OP_Information.json`
- 拿到最新的 `OP_Framework.json`
- 根据用户目标理解当前网络、参数、位置、DAT 内容、连接关系与非默认改动

如果用户要“先读现状”“先理解当前工程”“告诉我现在工程里有什么”“编辑前先同步扫描结果”，就先走本技能。

## 何时直接使用

出现以下任一意图时，直接使用本技能：

- “先读取当前 TouchDesigner 工程”
- “更新一下 OP_Information / OP_Framework 再分析”
- “帮我看看现在项目里有哪些节点和连接”
- “在改之前先理解当前 TD 网络”
- “刷新扫描结果后告诉我当前结构”
- “读取现存组件、参数、位置、DAT 内容”
- “先同步工程现状，再决定怎么改”

如果目标核心是**读取和理解当前 TD 工程内容**，优先使用本技能。

## 内置参考资料

按需读取：

- `references/scan-workflow.md`
- `references/json-reading-guide.md`

它们分别提供：

- 如何触发扫描、等待更新、读取产物
- 如何区分 `OP_Information.json` 与 `OP_Framework.json` 的语义

## 核心原则

1. 先刷新，再分析，不要基于旧 JSON 臆测当前工程状态。
2. 第一步必须是 pulse 根目录 `/SecretAgent` 的 `Updateinfo` 参数。
3. `OP_Information.json` 负责全量理解，`OP_Framework.json` 负责快速看非默认改动。
4. 禁止用任何运行时直连式读取去替代这条扫描读取链路。
5. 如果用户的问题只涉及当前结构理解，不要擅自进入结构编辑。
6. 分析时要明确区分“事实”和“推断”，不要把猜测写成已确认结论。

## 标准工作流

### 第 1 步：触发 TouchDesigner 信息收集

先在 TouchDesigner 中触发一次扫描：

- 目标组件：根目录下的 `/SecretAgent`
- 目标参数：`Updateinfo`
- 动作：对该参数执行一次 `pulse`

可把这一步理解为：

```text
pulse /SecretAgent.par.Updateinfo
```

这一步完成后，TouchDesigner 会重新生成或刷新：

- `OP_Information.json`
- `OP_Framework.json`

如果当前环境是通过自动化桥接层接入 TD，优先调用：

```json
{"cmd":"refresh_project_state","secret_agent_path":"/SecretAgent"}
```

这个命令的职责不是直接读取节点，而是远程触发一次 `/SecretAgent.par.Updateinfo` 的 `pulse`，让扫描产物刷新。

不要退回到运行时直连读取方案。即使运行时查询还能拿到节点列表，本技能也不应把它当作当前工程真相来源。

### 第 2 步：确认扫描产物已更新

在读取前，确认以下两份文件已经是本轮刷新后的结果：

- `OP_Information.json`
- `OP_Framework.json`

如果环境允许检查时间戳、内容变化或 hash，优先确认它们已更新；否则至少重新读取文件内容，不沿用旧缓存。

如果 `refresh_project_state` 的返回结果提示：

- `missing_dats` 非空
- `empty_dats` 非空
- `updated` 为 `false`

则应把问题判断为“扫描链路异常”，而不是偷偷改用别的读取方案。

### 第 3 步：读取两份 JSON

先读：

- `OP_Information.json`

再读：

- `OP_Framework.json`

读取顺序这样安排的原因是：

- `OP_Information.json` 信息最全，适合做完整理解
- `OP_Framework.json` 更精炼，适合快速定位非默认参数与当前显著改动

### 第 4 步：按文件语义分工分析

#### `OP_Information.json`

把它当成“全量工程快照”，优先用于回答：

- 当前有哪些节点
- 节点类型是什么
- 节点位置如何分布
- 当前连接关系是什么
- 普通参数有哪些页面与参数名
- 自定义参数有哪些定义和值
- DAT 内容是什么
- 当前节点的显示状态如何

#### `OP_Framework.json`

把它当成“复刻友好的差异快照”，优先用于回答：

- 当前哪些参数是非默认的
- 哪些连接是关键结构
- 哪些节点是当前网络里的核心改动点
- 如果后续要编辑，哪些部分最值得保留和继续复用

### 第 5 步：根据用户目标组织输出

读取完成后，不要把整份 JSON 原样倾倒给用户，而是围绕用户问题组织结果。

常见输出方向包括：

- 工程整体概览
- 指定节点说明
- 指定子网络梳理
- 参数与绑定关系梳理
- 非默认改动总结
- 为后续编辑准备上下文

## 输出建议

如果用户只说“帮我看看当前工程”，优先按以下顺序汇报：

1. 顶层节点列表
2. 主要连接关系
3. 关键非默认参数
4. 是否存在 bind / expression / DAT 内容
5. 与用户目标最相关的重点节点

如果用户问的是更具体的问题，例如：

- 哪个节点控制音频输出
- 当前音频文件从哪里进来
- 哪些参数被改过
- 某个 DAT 里写了什么

就直接围绕那个问题抽取对应字段，不做无关泛泛总结。

## 推荐分析框架

### 场景 1：整体理解当前网络

至少回答：

- 顶层有哪些节点
- 每个节点的类型
- 主要连接流向
- 是否存在明显的非默认参数

### 场景 2：为后续编辑做准备

至少回答：

- 与目标需求最相关的节点路径
- 真实页面名和参数名
- 当前已存在的连接关系
- 哪些参数已有 expression 或 bind
- 哪些值来自默认，哪些是显式修改

### 场景 3：排查某个节点为何这样工作

至少回答：

- 节点类型
- 上下游连接
- 当前关键参数
- 是否有 bind / expression
- 是否有 DAT 内容或自定义参数影响

## 重点字段解释

### 连接

优先读：

- `connections.inputs`
- `connections.outputs`

分析时要说清楚“谁连到谁”，不要只重复 JSON 字段。

### 参数模式

优先识别：

- `ParMode.CONSTANT`
- `ParMode.EXPRESSION`
- `ParMode.BIND`

尤其是：

- `EXPRESSION` 要同时读 `expr`
- `BIND` 要同时读 `bindExpr`、`bindRange`、`bindMaster`

### 非默认参数

`OP_Framework.json` 相比 `OP_Information.json` 的价值就在这里：

- 它更适合快速定位“被改过”的参数
- 如果某个参数只出现在 `OP_Information.json` 而没有出现在 `OP_Framework.json`，通常更接近默认状态

## 常见错误与避免方式

### 错误 1：直接读取旧 JSON

避免方式：

- 先 pulse `/SecretAgent.par.Updateinfo`
- 再读取产物

### 错误 2：把 `OP_Framework.json` 当成全量真相

避免方式：

- 用 `OP_Information.json` 做全量理解
- 用 `OP_Framework.json` 做差异理解

### 错误 3：只罗列字段，不做解释

避免方式：

- 把 JSON 翻译成网络结构、数据流向、控制关系、参数含义

### 错误 4：进入编辑模式

避免方式：

- 用户没要求改，就不要生成编辑方案
- 本技能默认是“读”和“理解”，不是“写”和“改”

### 错误 5：扫描失败后改走运行时直连读取

避免方式：

- 不要退回任何运行时直连式读取兜底
- 应明确报告 `/SecretAgent.par.Updateinfo` 刷新链路失败
- 然后继续修复扫描触发、DAT 更新、外部化写回或 JSON 产物挂载问题

## 示例任务

**示例 1：读取当前音频链路**

用户：先刷新一下当前 TouchDesigner 工程，然后告诉我音频是怎么从输入走到输出的。

你应先 pulse `/SecretAgent.par.Updateinfo`，再读取两份 JSON，重点解释音频相关节点、连接流向、关键参数。

**示例 2：为后续修改做准备**

用户：我等会儿要改音频播放逻辑，先帮我读一下当前项目里和音频有关的节点、参数和 bind。

你应先刷新扫描结果，再基于 `OP_Information.json` 和 `OP_Framework.json` 提炼真实页面名、参数名、连接与非默认状态。

**示例 3：快速看工程当前改动**

用户：帮我看看当前工程最重要的非默认参数都有哪些。

你应优先使用 `OP_Framework.json` 做总结，并在必要时回到 `OP_Information.json` 补上下文。

## 结束标准

只有在以下条件满足时，才算完成一次“读取当前 TD 工程”任务：

- 已触发 `/SecretAgent.par.Updateinfo`
- 已重新读取 `OP_Information.json`
- 已重新读取 `OP_Framework.json`
- 已根据用户需求完成结构化理解
- 未退回运行时直连读取
- 未越权进入编辑链路
