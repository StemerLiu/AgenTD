# OP_Framework 协议速查

本文件是技能内置协议参考，用来保证技能在脱离原仓库文档时仍能独立工作。

## 目标

把 TouchDesigner 的结构编辑统一表达为一棵 `OP_Framework` 树，并通过固定链路一次性落地，而不是回退到旧式逐条编辑命令。

标准执行链路：

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

## 顶层结构

顶层必须是数组，数组元素是一个节点块：

```json
[
	{
		"geo1": {
			"relPath": "/project1/geo1",
			"type": "geometryCOMP",
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

## 节点块字段

- 外层键必须等于节点名
- `relPath` 必须是绝对路径
- `type` 必须是具体 TD OP 类型
- `pos` 是工作区坐标
- `parameters` 是普通参数
- `customParameters` 是自定义参数
- `drawState` 是显示与渲染状态
- `datContent` 是 DAT 正文
- `connections` 是连接信息
- `children` 是子节点数组

## 普通参数

基础写法：

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

### bind 写法

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

要点：

- bind 参数不要再输出 `val`
- `bindMaster` 应是可定位的真实引用位置

## 自定义参数

自定义参数需要同时保留值与定义信息。

### 单值参数

```json
"customParameters": {
	"属性": {
		"Speed": {
			"val": "1.0",
			"mode": "ParMode.CONSTANT",
			"definition": {
				"name": "Speed",
				"label": "速度",
				"style": "Float"
			}
		}
	}
}
```

### tuple 参数

tuple 不能拆成 `foo1/foo2/foo3` 多条，必须按组输出：

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

要点：

- tuple 参数必须按组写
- `styleSize`、`size`、`componentNames` 要和真实定义一致
- bind 模式下同样不能保留 `val`

## 连接写法

连接写在目标节点的 `connections.inputs`：

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

规则：

- `port` 是目标输入口
- `links` 是来源节点列表
- 用户要求连线时，`forest` 中必须体现连接关系

## 路径与类型

始终检查：

- `relPath` 必须是 `/project1/...` 这类绝对路径
- `type` 必须是具体节点类型，如 `nullTOP`、`audiofileinCHOP`、`containerCOMP`
- 不要使用 `TOP`、`CHOP`、`COMP` 这种占位 family

## 占位结构禁止项

以下结构视为无效或待修复：

- 相对路径
- `TOP/CHOP/COMP` 这类占位类型
- `Page/par` 这类占位参数页名与参数名
- 缺失 `connections.inputs`
- 多节点完全重叠
- tuple 参数被拆碎
- bind 参数同时包含 `val`

## 生成前自检

输出最终 `forest` 前，至少确认：

- 有 `write_framework_json`
- 有有效 `forest`
- 有 `replicate_framework`
- 用户要求参数修改时，参数已写入
- 用户要求连线时，连接已写入
- 没有退回旧式命令
