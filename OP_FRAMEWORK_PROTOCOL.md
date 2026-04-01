# OP_Framework 协议

本文件定义当前项目面向 AI 的唯一推荐结构编辑协议。

## 总原则

- AI 不再通过 `create/par/connect/clear/delete` 逐条改动 TouchDesigner 网络
- AI 必须先读取 `OP_Framework.py` 与 `OP_Information.py` 的导出结果
- AI 必须按 `OP_Framework copy.json` 的格式改写结构
- TouchDesigner 侧统一通过 `reload -> replicate_framework -> save_project` 落地

## 顶层结构

顶层必须是数组，每个数组元素表示一个顶层节点块：

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

- `组件名`
	- 节点块外层键，必须等于节点名
- `relPath`
	- 组件完整路径
- `type`
	- TouchDesigner OP 类型名
- `pos`
	- 工作区坐标，格式为 `{ "x": 0, "y": 0 }`
- `parameters`
	- 普通参数
- `customParameters`
	- 自定义参数页与参数
- `drawState`
	- 节点显示/渲染相关 flag
- `datContent`
	- DAT 组件的正文内容
- `connections`
	- 输入输出连接
- `children`
	- 子节点数组，结构与顶层一致

## parameters 写法

普通参数按页面分组：

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

- `OP_Information` 可保留全量参数
- `OP_Framework` 普通参数仅保留非默认值
- `ParMode.EXPRESSION` 要写 `expr`
- `ParMode.BIND` 不写 `val`，改写为：

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

## customParameters 写法

自定义参数必须全量保留，不做默认值过滤。

页面顺序必须保持 TouchDesigner 原始 `customPages` 顺序。

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

### 多值组参数

多值 tuple 参数不能拆开写成 `foo1/foo2/foo3` 多条，必须按组输出：

```json
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
```

## drawState 写法

用于描述节点可见性与交互 flag。

```json
"drawState": {
	"display": true,
	"render": false,
	"template": false,
	"compare": false,
	"pickable": true
}
```

规则：

- TOP 类型通常不写 `render`
- geometry/COMP/SOP 等节点可包含 `display/render/template/compare/pickable`

## DAT 内容写法

### 文本类 DAT

```json
"datContent": {
	"kind": "text",
	"meta": {
		"lines": 10,
		"chars": 100,
		"sha1": "..."
	},
	"full": "完整文本"
}
```

### 表格 DAT

```json
"datContent": {
	"kind": "table",
	"meta": {
		"rows": 2,
		"cols": 2,
		"sha1": "..."
	},
	"rows": [
		["a", "1"],
		["b", "2"]
	]
}
```

## connections 写法

连接统一用组件名，不写完整路径：

```json
"connections": {
	"inputs": [
		{
			"port": 0,
			"links": ["noise1"]
		}
	],
	"outputs": [
		{
			"port": 0,
			"links": ["container1"]
		}
	]
}
```

## AI 操作步骤

1. 从 `OP_Framework.py` / `OP_Information.py` 获取当前结构
2. 仅修改 `OP_Framework copy.json`
3. 保证 JSON 完整且符合上述结构
4. 执行 `tools/replicate_framework.py`
5. 必要时执行 `save_project`

## 禁止事项

- 不要再输出 `create/par/connect/clear/delete` 作为常规结构编辑方案
- 不要把 bind 参数写成普通常量值
- 不要把多值自定义参数拆开
- 不要跳过自定义参数页或页内参数定义信息
