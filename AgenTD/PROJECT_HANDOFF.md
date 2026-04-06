# AgenTD 项目交接摘要

## 1. 项目目标

本项目的目标是把 TouchDesigner 自动化能力整理为：

- 可复用技能
- 可执行的多智能体协作链
- 可通过网页控制台发起任务、查看协作过程、执行 TD 命令

当前主线已经不是“从零设计”，而是“在已有多智能体闭环上继续收口架构并提升真实 TD 可用性”。

---

## 2. 当前总体状态

### 已完成

- TouchDesigner 读取链路已可用
- TouchDesigner 编辑链路已接入 `OP_Framework.json -> reload -> replicate_framework -> save_project`
- multiagent 最小闭环已落地：
	- Orchestrator
	- State Reader
	- KB Consultant
	- Framework Editor
	- Verifier
- manifest-driven runtime dispatch 已完成
- registry / descriptor / schema / contract flow 已接通
- 自动回环 retry 已完成
- `ValidationStateBrief` 已完成
- `CandidatePlan` 已完成
- `web_bridge.py` 已经过多轮 slimming，bridge 已明显收口
- Web 前端已收敛为 DeepSeek 单模型入口
- Web 前端已具备多智能体协作过程可视化

### 未完全收口

- `web_bridge.py` 仍然保留：
	- API 入口
	- TD 执行桥
	- runtime 持久化
	- 少量 route / execute 装配逻辑
- 网页交互类需求虽然已增加防呆和校验，但还没有完全模板化生成
- 真实 TouchDesigner 现场的复杂网页类创建，仍需要继续补强

---

## 3. 最重要的历史问题与处理结果

### 问题 A：multiagent 一直在看“假现状”

#### 现象

- `web_bridge.py` 早期一直读取：
	- `AgenTD/OP_Information.json`
	- `AgenTD/OP_Framework.json`

这是旧样本，不是 TouchDesigner 当前真正使用的文件。

#### 根因

- 手动调整项目结构后，TD 端导出路径和 bridge 读取路径都没同步更新

#### 结果

- 现已改为对齐真实工作区根目录文件
- 同时修复了：
	- [OP_Framework.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/OP_Framework.py)
	- [OP_Information.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/OP_Information.py)

的 JSON 导出路径

---

### 问题 B：旧模块加载与 reload 链断裂

#### 现象

- TouchDesigner 工程改结构后，旧模块路径不再正确
- `bootstrap.py` / `server_callbacks.py` / `commands.py` 链路出现失配

#### 结果

- 相关路径已修正
- `reload`
- `refresh_project_state`
- `replicate_framework`

这些主链后来都恢复到可回归状态

---

### 问题 C：bridge 一直想瘦，但文件一度没有变短

#### 现象

- `web_bridge.py` 的职责持续往 runtime 下沉
- 但早期为了过渡，引入过不少 wrapper，所以文件量不一定立刻下降

#### 结果

- 现在已进入“真正减层”阶段：
	- 增加了统一 orchestrator runtime 调用入口
	- 删除了多批纯机械转发 wrapper
	- 主链已从“手写状态机细节”转为“少量 block runner + 装配”

---

### 问题 D：网页类命令生成出非法 TD 节点类型

#### 真实失败案例

用户发送：

> 创建一个小球跟随鼠标移动的效果

系统曾生成：

- `WebContainer`
- `Text`

随后 `replicate_framework` 报错：

> `Unknown operator type. Value:'WebContainer'`

#### 根因

- `WebContainer` 不是合法 TD OP 类型
- `Text` 也不是合法 TD OP 类型
- 旧校验只拦截 `TOP/CHOP/COMP` 这类占位类型，没拦截这种“伪具体类型”

#### 已做修复

- 强化了执行提示词与修复提示词
- 增加类型归一化别名
- 增加非法 OP 类型检测
- 对网页交互类需求强制要求 `webrenderTOP`
- 如果修复后仍不合法，直接阻止命令下发

当前效果是：**不会再把明显不合法的网页类命令直接执行到 TD。**

---

## 4. 当前关键文件

### 核心桥接与执行

- [web_bridge.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/tools/web_bridge.py)
	- 整个项目最核心入口
	- 负责 Web API、模型调用、multiagent route / execute 装配、TD 命令桥接、runtime 持久化

### Orchestrator

- [runtime.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/orchestrator/runtime.py)
	- 目前大量 phase helper / block helper 已下沉到这里
- [manifest.json](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/orchestrator/schemas/manifest.json)
	- runtime exports 已扩展到较完整状态

### 其他 agent runtime

- [state_reader/runtime.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/state_reader/runtime.py)
- [kb_consultant/runtime.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/kb_consultant/runtime.py)
- [framework_editor/runtime.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/framework_editor/runtime.py)
- [verifier/runtime.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/agents/verifier/runtime.py)

### TD 端文件

- [OP_Framework.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/OP_Framework.py)
- [OP_Information.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/OP_Information.py)

### 前端

- [index.html](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/web/index.html)
- [app.js](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/web/app.js)
- [style.css](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/web/style.css)

### 架构设计文档

- [MULTIAGENT_WORKFLOW.md](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/MULTIAGENT_WORKFLOW.md)

---

## 5. multiagent 当前能力边界

### 已具备

- 任务分类
- 结构化 route
- state read
- KB compatibility
- framework edit plan
- execution result
- validation
- retry request
- auto retry loop
- final report

### 当前摘要对象

- `TaskBrief`
- `ProjectStateBrief`
- `CompatibilityBrief`
- `EditPlanBrief`
- `ExecutionResult`
- `ValidationStateBrief`
- `ValidationBrief`
- `RetryRequest`
- `FinalReport`
- `CandidatePlan`

---

## 6. web_bridge 当前形态

### 已完成的收口

- route / execute / retry 主链已改成 block runner 风格
- 大量 orchestrator 纯转发 wrapper 已删除
- 已增加统一入口 `_invoke_orchestrator_runtime(...)`

### 还保留在 bridge 的东西

- HTTP API
- 模型接口桥
- TD socket 命令桥
- runtime 持久化
- 少量 route / execute 装配逻辑

### 判断

- 现在 bridge 更像“系统装配器”
- 但还没有彻底缩到最小终态

---

## 7. Web 前端当前状态

### 已完成

- 非 DeepSeek provider 入口已删除
- 保留 DeepSeek 单入口配置
- 增加了多智能体协作图形化可视化
- 增加流程状态与时间线显示

### 当前用途

- 发起用户请求
- 查看 AI 回复
- 查看推荐 TD 命令
- 观察多智能体阶段流转
- 手动发送 TD 命令

---

## 8. 最近一次重要修复

最近一次真正影响真实可用性的修复是：

### 目标

- 阻止网页类需求生成非法 TouchDesigner 节点类型

### 修改位置

- [web_bridge.py](file:///Users/stemerliu/Documents/SuperLib/TD自动化/AgenTD/tools/web_bridge.py)

### 修改内容

- 强化 `EXECUTOR_PROMPT`
- 强化 `REPAIR_EXECUTOR_PROMPT`
- 扩展 `_normalize_op_type()`
- 增加非法 operator type 检测
- 增加网页交互类 `webrenderTOP` 强制校验
- 增加最终失败硬拦截

### 当前意义

- 系统不再把明显不合法的网页结构直接下发到 TouchDesigner

---

## 9. 已验证内容

以下内容都已多轮验证过：

- `py_compile`
- route 回归
- execute 回归
- read-only 场景
- create 场景
- POP compatibility retry 场景
- Web 前端可打开与静态资源可返回

---

## 10. 下一位接手者最值得优先做的事

### 优先级 1：网页交互类需求模板化

当前网页类需求仍然部分依赖模型自由发挥。最值得继续做的是：

- 针对 HTML/CSS/JS 类需求走固定模板
- 直接生成合法：
	- `textDAT`
	- `webrenderTOP`

而不是继续让模型自行发明 `WebContainer`

### 优先级 2：bridge 最终收口

继续把 `web_bridge.py` 缩到更明确的最终边界，只保留：

- API 入口
- TD 执行桥
- runtime 持久化
- 最小装配逻辑

### 优先级 3：真实 TD 场景联测

当前大量回归已完成，但仍建议继续用真实 TouchDesigner 工程做：

- 网页交互类
- 复杂参数修改类
- 多节点连线类

的最终联测

---

## 11. 交接时最重要的一句话

这个项目现在**不是从零搭架子**，而是已经进入：

> **多智能体闭环已成型，正在把 bridge 收口并提升真实 TouchDesigner 可执行性**

接手时不要再回到“大改目录结构”或“重做 multiagent 设计”，应当直接从：

- 网页类模板化
- bridge 最终收口
- 真实 TD 联测

这三条线继续推进。

