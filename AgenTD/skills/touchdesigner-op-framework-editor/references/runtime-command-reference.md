# 运行时命令参考

本文件是技能内置的运行时命令速查，用来保证技能在脱离原仓库说明文档时仍能独立生成可执行链路。

## 当前推荐命令集合

结构编辑相关的主链路只围绕这些命令组织：

- `refresh_project_state`
- `write_framework_json`
- `reload`
- `replicate_framework`
- `save_project`

其中：

- `refresh_project_state` 只负责触发 `/SecretAgent.par.Updateinfo`
- 当前工程读取必须在刷新后通过 `OP_Information.json` 与 `OP_Framework.json` 完成

## 结构编辑唯一主链路

当用户目标涉及以下任何动作时：

- 创建节点
- 删除节点
- 调整节点层级
- 连线
- 普通参数修改
- 自定义参数修改
- DAT 内容修改

都应回到：

1. 刷新扫描结果
2. 读取 `OP_Information.json` / `OP_Framework.json`
3. 写 `forest`
4. `write_framework_json`
5. `reload`
6. `replicate_framework`
7. `save_project`

## 每条命令的职责

### refresh_project_state

职责：触发 `/SecretAgent.par.Updateinfo`，刷新 `OP_Information.json` 与 `OP_Framework.json`。

示例：

```json
{
	"cmd": "refresh_project_state",
	"secret_agent_path": "/SecretAgent"
}
```

规则：

- 这是扫描刷新命令，不是节点读取命令
- 刷新成功后，应重新读取两份 JSON，而不是沿用旧缓存

### write_framework_json

职责：把完整 `forest` 写入本地框架文件。

示例：

```json
{
	"cmd": "write_framework_json",
	"file": "OP_Framework.json",
	"forest": []
}
```

规则：

- `forest` 必须是标准 `OP_Framework` 树
- 优先使用 `file`
- 如果上游模型写成 `source`，应归一化回 `file`

### reload

职责：让运行时重新加载最新逻辑。

示例：

```json
{
	"cmd": "reload"
}
```

### replicate_framework

职责：按框架文件把结构复刻回 TouchDesigner。

示例：

```json
{
	"cmd": "replicate_framework",
	"file": "OP_Framework.json",
	"clear_parent": true
}
```

规则：

- 优先使用 `file`
- `clear_parent` 用于控制是否先清空目标父网络
- 如果上游模型写成 `source/target` 等 legacy 字段，应归一化为当前字段

### save_project

职责：在结构修改成功后保存工程。

示例：

```json
{
	"cmd": "save_project"
}
```

## 已废弃命令

以下命令属于旧式逐条编辑路径，不应再生成：

- `create`
- `par`
- `connect`
- `clear`
- `delete`
- `remove`
- `destroy`
- `hover`
- `build_glsl_cube`
- `save_tox`

如果用户目标本来需要这些效果，也要转换成 `OP_Framework` 树表达。

## 推荐执行顺序

### 场景 1：直接结构编辑

```json
[
	{"cmd":"write_framework_json","file":"OP_Framework.json","forest":[]},
	{"cmd":"reload"},
	{"cmd":"replicate_framework","file":"OP_Framework.json","clear_parent":true},
	{"cmd":"save_project"}
]
```

### 场景 2：先刷新扫描再编辑

```json
[
	{"cmd":"refresh_project_state","secret_agent_path":"/SecretAgent"},
	{"cmd":"write_framework_json","file":"OP_Framework.json","forest":[]},
	{"cmd":"reload"},
	{"cmd":"replicate_framework","file":"OP_Framework.json","clear_parent":true},
	{"cmd":"refresh_project_state","secret_agent_path":"/SecretAgent"},
	{"cmd":"save_project"}
]
```

## 生成命令时的修复思路

如果模型输出不稳定，按以下顺序自修复：

1. 把 legacy 字段归一化到当前字段名
2. 把扁平 forest 改成标准树
3. 把相对路径改成绝对路径
4. 把 family 类型改成具体 TD 类型
5. 补上缺失连接
6. 补上缺失参数
7. 拉开重叠坐标
8. 清除 bind 下错误的 `val`

## 最终交付标准

一组可交付命令至少应满足：

- 不包含已废弃命令
- 命令链包含 `refresh_project_state`
- 第一条结构编辑命令是 `write_framework_json`
- 命令链中包含 `replicate_framework`
- `forest` 不为空且可解释
- 用户要求的结构、参数、连接都已落到 `forest`
