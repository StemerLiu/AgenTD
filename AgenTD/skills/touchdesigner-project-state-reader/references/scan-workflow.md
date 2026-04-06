# 扫描刷新工作流

本文件描述“读取当前 TouchDesigner 工程内容”时的固定刷新流程。

## 目标

在分析当前工程前，先触发一次 TouchDesigner 内部信息收集，让后续读取到的是最新状态，而不是旧缓存。

## 固定步骤

### 1. pulse `/SecretAgent.par.Updateinfo`

先在 TouchDesigner 根目录找到：

- 组件：`/SecretAgent`
- 参数：`Updateinfo`

然后对这个参数执行一次 `pulse`。

如果当前环境是通过远程命令接入 TouchDesigner，优先使用：

```json
{"cmd":"refresh_project_state","secret_agent_path":"/SecretAgent"}
```

这个命令应只负责触发扫描刷新，不负责直接返回节点结构。

可简记为：

```text
pulse /SecretAgent.par.Updateinfo
```

## pulse 之后会发生什么

这一步会触发工程内的信息收集脚本，随后更新两份文件：

- `OP_Information.json`
- `OP_Framework.json`

## 读取顺序

建议固定为：

1. 触发 pulse 或 `refresh_project_state`
2. 确认扫描产物已刷新
3. 读取 `OP_Information.json`
4. 读取 `OP_Framework.json`
5. 按用户问题做分析输出

## 为什么不能直接读旧文件

因为用户问的是“当前工程里有什么”，而不是“上一次扫描时工程里有什么”。

如果跳过 pulse，风险包括：

- 新增节点没读到
- 删掉的节点还在旧 JSON 里
- 参数和 bind 状态已变化但分析结果仍过期
- DAT 内容已经变了但摘要还是旧的

## 禁止的替代方案

任何运行时直连式读取都不能替代这条扫描工作流。

所有当前工程理解都必须回到 `refresh_project_state -> OP_Information.json / OP_Framework.json`。

如果扫描失败，应继续修复扫描链路本身，而不是偷偷切换到直连读取。

## 刷新后的检查点

如果环境允许，至少确认以下任一项：

- 文件时间戳已变化
- 文件内容 hash 已变化
- 文件内容重新读取成功

如果环境不方便做这些检查，也不要沿用旧缓存，至少重新读取文件正文。

## 默认产物语义

- `OP_Information.json`
	- 偏全量快照
	- 包含完整组件、参数、位置、内容等信息

- `OP_Framework.json`
	- 偏复刻与差异视图
	- 相比前者，参数通常只保留非默认部分

## 使用边界

本流程默认用于：

- 分析当前工程
- 为后续编辑做准备
- 排查当前网络
- 理解参数、bind、expression、DAT 内容

本流程本身不是结构编辑步骤，不负责创建或修改节点。
