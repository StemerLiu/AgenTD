# JSON 阅读指南

本文件说明如何把 `OP_Information.json` 和 `OP_Framework.json` 读成可解释的工程理解结果。

## 两份文件的分工

### OP_Information.json

把它当成“全量工程快照”。

更适合回答：

- 当前有哪些节点
- 每个节点是什么类型
- 节点在哪里
- 当前有哪些输入输出连接
- 普通参数有哪些页面和参数名
- 哪些参数是 constant / expression / bind
- DAT 内容是什么
- 是否存在自定义参数与 drawState

### OP_Framework.json

把它当成“差异化工程快照”。

更适合回答：

- 哪些参数是明显被改过的
- 当前网络中最重要的结构保留点是什么
- 后续如果要编辑，哪些信息值得直接复用

## 推荐阅读顺序

### 1. 先看节点名、路径、类型

优先字段：

- 外层节点名
- `relPath`
- `type`
- `pos`

这一步用来建立“网络地图”。

### 2. 再看连接

优先字段：

- `connections.inputs`
- `connections.outputs`

解释时不要只说“有 inputs / outputs”，而要翻译成：

- 谁是上游
- 谁是下游
- 数据流从哪里到哪里

## 3. 再看参数模式

优先识别：

- `ParMode.CONSTANT`
- `ParMode.EXPRESSION`
- `ParMode.BIND`

其中：

- `CONSTANT` 看 `val`
- `EXPRESSION` 看 `expr`
- `BIND` 看 `bind.bindExpr`、`bind.bindRange`、`bind.bindMaster`

如果用户关心“为什么这个节点这样工作”，参数模式往往比单纯参数值更重要。

## 4. 最后看差异

通过对照：

- `OP_Information.json`
- `OP_Framework.json`

可以快速判断：

- 哪些参数只是默认状态
- 哪些参数是显式改动
- 哪些连接是当前结构中的关键关系

## 输出时的推荐组织方式

### 如果用户要整体理解

建议输出：

1. 顶层节点清单
2. 关键连接流向
3. 重要非默认参数
4. 特殊模式参数
5. 后续值得关注的节点

### 如果用户要局部理解

建议围绕目标节点输出：

1. 节点路径与类型
2. 上下游连接
3. 当前关键参数
4. 非默认改动
5. bind / expression / DAT 内容

### 如果用户要为编辑做准备

建议输出：

1. 相关节点路径
2. 真实页面名
3. 真实参数名
4. 已存在连接
5. 已存在 bind / expression
6. 哪些值最好保留

## 来自当前项目样本的典型例子

以下是从项目扫描结果中可以直接学到的阅读方式。

### 例 1：音频输入到音频输出

在样本中可以看到：

- `audio_file_in`
	- 类型：`audiofileinCHOP`
- `audio_device_out`
	- 类型：`audiodeviceoutCHOP`

连接关系里：

- `audio_device_out.connections.inputs[0].links` 指向 `audio_file_in`
- `audio_file_in.connections.outputs[0].links` 指向 `audio_device_out`

这说明当前音频链路是从音频文件输入流向音频设备输出。

### 例 2：找关键非默认参数

在样本 `OP_Framework.json` 中，`audio_file_in` 的以下参数被保留：

- `file`
- `index`
- `mono`
- `timecodeop`

这意味着这些参数更值得优先关注，因为它们相对默认状态更可能被显式设置过。

### 例 3：识别 bind

样本里 `audio_file_in` 的 `file` 参数是：

- `mode: ParMode.BIND`
- 带 `bind.bindExpr`
- 带 `bind.bindRange`

分析时应明确说明：

- 该参数不是常量值
- 它当前通过 bind 获得值
- 因此后续若要改文件路径，可能需要先处理 bind 关系

## 常见误读

### 误读 1：看到 `outputs` 就只解释输出，不回看输入

应当同时看输入和输出，这样才能确认完整链路。

### 误读 2：只看 `OP_Framework.json` 就以为掌握了全部参数

不对。

`OP_Framework.json` 更像浓缩版，不适合作为“完整参数总表”。

### 误读 3：把 bind 当常量值

如果 `mode` 是 `ParMode.BIND`，重点就不是 `val`，而是绑定来源。

### 误读 4：只报节点列表，不做关系解释

用户通常需要的是“结构理解”，不是原始字段抄录。
