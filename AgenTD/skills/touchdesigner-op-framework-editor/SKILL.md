---
name: touchdesigner-op-framework-editor
description: 将当前 TD自动化/AgenTD 项目里所有 TouchDesigner 结构编辑能力统一封装为一个技能。只要用户提到在 TouchDesigner 中创建节点、删除节点、连线、改参数、改自定义参数、改 DAT 内容、调整网络结构、根据 OP_Framework 编辑工程、让 AI 直接操作 TD，或要把自然语言需求转成可执行 TD 编辑链路，就应优先使用本技能。该技能强制使用 OP_Framework JSON 与 write_framework_json、reload、replicate_framework、save_project 组成的唯一编辑协议，禁止退回 create/par/connect/delete 等旧式命令。
---

# TouchDesigner OP Framework Editor

该技能用于在当前 **TD自动化 / AgenTD** 项目中，把“编辑 TouchDesigner 工程”的所有动作收敛到同一条稳定链路：

- 读取当前工程信息
- 按 `OP_Framework` 协议生成或改写结构树
- 通过 `write_framework_json`
- 再执行 `reload -> replicate_framework -> save_project`
- 最后做结果验证与修复

这个技能的重点不是“随便拼几条 TD 命令”，而是让模型始终遵守项目里已经定下来的**唯一结构编辑协议**，避免再次走回已经废弃的旧命令体系。

## 何时直接使用

出现以下任一意图时，直接使用本技能：

- “帮我在 TouchDesigner 里创建几个节点并连线”
- “修改某个 COMP/TOP/CHOP 的参数”
- “按当前工程结构改写一个网络”
- “根据 OP_Framework / OP_Information 生成可执行编辑方案”
- “让 AI 直接操作 TouchDesigner 项目”
- “把用户自然语言需求转成 TD 可执行 JSON”
- “在这个 TD 自动化项目里新增/删除/替换网络结构”

如果任务本质上是在**编辑 TD 工程结构**，不要拆成零散的 create / par / connect / delete 步骤，而是走本技能。

## 内置参考资料

这个技能已经内置了独立可分发所需的关键参考，不依赖仓库外部说明文件。

按需读取：

- `references/op-framework-protocol.md`
- `references/runtime-command-reference.md`

它们分别提供：

- `OP_Framework` 树结构、参数写法、bind 与 tuple 规则
- 当前运行时允许命令、标准执行顺序、常见错误修复点

## 读取实时项目上下文

如果当前工作区里恰好存在这些项目文件，可以把它们当成**实时上下文**进一步核对，但它们不是本技能可运行的前提：

- `OP_Framework.json`
- `OP_Information.json`
- `tools/web_bridge.py`
- `lib/commands.py`

使用原则：

- 内置参考负责“协议知识”
- 工作区文件负责“当前项目真实状态”

如果用户已经明确给出 `OP_Framework.json`、`OP_Information.json` 或局部导出结果，优先基于这些现成数据工作，不要重新臆造结构。

## 核心原则

1. 所有结构编辑统一走 `OP_Framework` 树，不走旧式逐条命令。
2. 禁止输出或依赖 `create`、`par`、`connect`、`clear`、`delete`、`remove`、`destroy`、`hover`、`build_glsl_cube`。
3. 如果参数名、页面名、节点类型、绑定来源不确定，先读工程信息，再生成编辑结果；不要用占位词糊弄过去。
4. 如果用户要求的是“真的改工程”，不要只给建议，要把框架 JSON 和执行链路一起准备好。
5. 如果发现生成结果不满足用户目标，要先修复框架树，再重新执行，不要把错误链路直接交给用户。

## 标准工作流

### 第 1 步：理解目标与编辑范围

先把用户需求归类为以下一种或多种：

- 新建节点
- 删除或替换节点
- 调整参数
- 修改自定义参数
- 修改 DAT 文本
- 调整节点连线
- 局部网络重构
- 整体网络重建

同时确定目标范围：

- 是整个 `/project1`
- 还是某个子网络，如 `/project1/container1`
- 是新增并保留原结构
- 还是允许清空后重建

如果用户没有说清楚，先按最小影响面假设执行，并在最终汇报里说明默认假设。

### 第 2 步：先读后改

编辑前优先用扫描结果确认上下文。标准顺序是：

1. 先触发 `refresh_project_state`，让 `/SecretAgent.par.Updateinfo` 刷新扫描产物
2. 再读取 `OP_Framework.json` / `OP_Information.json`
3. 仅基于扫描结果确认真实页面名、参数名、连接关系、自定义参数定义

不要把任何运行时直连式读取结果当成结构读取真相源。

如果用户要求修改现有节点的具体参数，而你还不知道真实参数页名或参数名，必须先读取扫描结果，不要写 `Page/par` 这类占位结构。

### 第 3 步：把需求转成 OP_Framework 树

所有真正的编辑内容，都必须落到 `forest` 数组里。顶层格式始终是：

```json
[
	{
		"nodeName": {
			"relPath": "/project1/nodeName",
			"type": "containerCOMP",
			"pos": {
				"x": 0,
				"y": 0
			},
			"parameters": {},
			"customParameters": {},
			"drawState": {},
			"connections": {},
			"children": []
		}
	}
]
```

写树时遵守这些规则：

- `relPath` 必须是绝对路径，如 `/project1/foo/bar`
- `type` 必须是具体 TD OP 类型，如 `audiofileinCHOP`、`containerCOMP`、`nullTOP`，不能只写 `TOP/CHOP/COMP`
- 多个节点不要全堆在同一坐标，至少给出简单布局
- 连接写到**目标节点**的 `connections.inputs`
- 要修改参数，就把真实参数写进 `parameters`
- 要修改 DAT 内容，就写 `datContent`
- 需要恢复显示状态时再写 `drawState`

### 第 4 步：处理参数与自定义参数

#### 普通参数

普通参数按页面分组，单个参数基本格式：

```json
"parameters": {
	"Common": {
		"tx": {
			"val": "0.0",
			"mode": "ParMode.CONSTANT"
		}
	}
}
```

规则：

- `ParMode.CONSTANT` 写 `val`
- `ParMode.EXPRESSION` 写 `expr`
- `ParMode.BIND` 不写 `val`

绑定参数写法：

```json
"edgecolorb": {
	"mode": "ParMode.BIND",
	"bind": {
		"bindExpr": "parent().par.Edgecolor2b",
		"bindRange": "False",
		"bindMaster": "/project1/container1.par.Edgecolor2b"
	}
}
```

#### 自定义参数

自定义参数必须保留定义信息，而且 tuple 参数不能拆碎。

错误示例是把 `Fromrangey1`、`Fromrangey2` 分开写成两条。

正确做法是按组写：

```json
"customParameters": {
	"属性": {
		"Fromrangey": {
			"val": ["0.0", "1.0"],
			"mode": ["ParMode.CONSTANT", "ParMode.CONSTANT"],
			"size": 2,
			"components": ["Fromrangey1", "Fromrangey2"],
			"definition": {
				"name": "Fromrangey",
				"style": "Float",
				"styleSize": "Float Size 2",
				"size": 2,
				"componentNames": ["Fromrangey1", "Fromrangey2"]
			}
		}
	}
}
```

额外注意：

- 页面顺序尽量遵循扫描结果中的 `customPages` 顺序
- bind 模式下同样不要输出 `val`
- 如果自定义参数定义未知，先读取扫描结果

### 第 5 步：处理连接

如果用户要求“连线”“接到”“输入到”“把 A 接进 B”，就必须在 `forest` 中体现连接关系，不能只创建节点不连线。

写法示例：

```json
"connections": {
	"inputs": [
		{
			"port": 0,
			"links": ["noise1"]
		}
	]
}
```

要点：

- `inputs` 写在目标节点上
- `port` 是目标输入口
- `links` 中是来源节点名；如果协议上下文要求更完整路径，优先遵循当前项目扫描结果
- 如果用户要求多个节点连线，检查整个链路是否闭合，不要漏中间节点

### 第 6 步：生成执行链路

在当前项目里，真正执行结构编辑时，优先生成这组命令：

```json
[
	{
		"cmd": "write_framework_json",
		"file": "OP_Framework.json",
		"forest": []
	},
	{
		"cmd": "reload"
	},
	{
		"cmd": "replicate_framework",
		"file": "OP_Framework.json",
		"clear_parent": true
	},
	{
		"cmd": "save_project"
	}
]
```

其中：

- `write_framework_json` 先把完整框架树写到本地文件
- `reload` 让 TD 重新加载最新 Python 逻辑
- `replicate_framework` 让 TD 真正按 JSON 复刻网络
- `save_project` 在成功后保存工程

如果只是先做执行前后校验，也应继续沿用 `refresh_project_state -> 读取 OP_Information.json / OP_Framework.json` 这条读取链路，不要退回运行时直连式方法。

如果需要更完整的字段约束或命令说明，优先加载技能内置的：

- `references/op-framework-protocol.md`
- `references/runtime-command-reference.md`

## 生成结果前的自检清单

在提交最终命令或执行前，逐项检查：

- 是否误用了旧式编辑命令
- 是否缺少 `write_framework_json`
- `forest` 是否是标准树，而不是扁平 legacy 结构
- `relPath` 是否全部为绝对路径
- `type` 是否全部为具体 OP 类型
- 是否出现 `Page/par` 这类占位参数名
- 用户要求连接时，是否真的写了 `connections.inputs`
- 用户要求改参数时，是否真的写了参数
- 多节点是否出现完全重叠坐标
- bind 参数是否错误包含 `val`
- tuple 自定义参数是否被错误拆分

如果任一项不通过，先修复再继续。

## 默认输出方式

如果用户要的是“给我一套可执行方案”，输出应包含：

1. 简短说明你准备改什么
2. 命令数组
3. 必要时附上关键 `forest` 片段
4. 执行后验证结果或下一步校验方式

如果用户要的是“直接完成修改”，则应：

1. 先读取需要的上下文
2. 改写框架文件或生成命令数组
3. 执行链路
4. 再做 `refresh_project_state` 并回读扫描结果验证
5. 把结果与假设告诉用户

## 常见错误与修复策略

### 错误 1：生成了 `TOP` / `CHOP` / `COMP`

这不是可执行的具体类型。改成真实类型，如：

- `nullTOP`
- `audiofileinCHOP`
- `containerCOMP`
- `baseCOMP`

如果仍不确定，先读工程扫描结果，不要猜。

### 错误 2：路径写成相对路径

把 `movie1`、`container1/null1` 这类相对写法改成绝对路径，如：

- `/project1/movie1`
- `/project1/container1/null1`

### 错误 3：参数结构用了占位字段

`Page/par` 不是可执行结果。必须先根据扫描结果替换成真实页面名与参数名。

### 错误 4：只创建节点，没有完成用户要求的连接或参数设置

回到用户目标，逐条比对是否缺失：

- 是否连线
- 是否开关某参数
- 是否设置 mono、file、resolution 等关键值
- 是否存在布局冲突

### 错误 5：bind 或 tuple 参数写坏

重点检查：

- bind 下不能有 `val`
- `bindMaster` 应是明确引用位置
- tuple 组要合并写，不拆成 `foo1/foo2`

## 示例任务

**示例 1：创建并连线**

用户：在 `/project1` 下创建一个 `noiseTOP` 和一个 `nullTOP`，并把 `noiseTOP` 接到 `nullTOP`。

你应优先输出一棵包含两个节点与连接关系的 `forest`，再走 `write_framework_json -> reload -> replicate_framework -> save_project`。

**示例 2：修改现有参数**

用户：把 `/project1/audiofilein1` 设置成单声道并指定音频文件。

你应先确认真实参数页和参数名；如果未知，先刷新并读取扫描结果，再写入真实参数，而不是写占位字段。

**示例 3：修改自定义参数绑定**

用户：把某容器的自定义颜色参数绑定到父组件对应参数。

你应输出 `ParMode.BIND` 结构，包含 `bindExpr`、`bindRange`、`bindMaster`，且不写 `val`。

## 结束标准

只有在以下条件满足时，才算完成一次 TD 编辑任务：

- 工程编辑方案符合 `OP_Framework` 协议
- 未使用废弃命令
- 命令链路可执行
- 关键结构、参数、连接都已落到 `forest`
- 已做至少一轮结果验证

如果用户给的是模糊需求，也要先完成一版最合理的结构化实现，再说明你的默认假设，而不是停在空泛讨论。
