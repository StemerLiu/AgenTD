# AgenTD

## 项目结构

- `agents/`
- `runtime/`
- `skills/`
- `tools/`
- `web/`
- `MULTIAGENT_WORKFLOW.md`
- `PROJECT_HANDOFF.md`
- `PROJECT_DIALOGUE_EXPORT.md`
- `OP_Framework.py`
- `OP_Information.py`
- `OP_Framework.json`
- `OP_Information.json`

## 目录职责

- `agents/`：放置多智能体角色配置、消息约定、Schema、manifest、contract 与各 agent runtime。
- `runtime/`：放置多智能体执行产物，包括 `briefs/`、`logs/`、`retries/`，用于调试 route / execute / retry 链路。
- `skills/`：放置可分发的 TouchDesigner 技能说明与参考资料。读取与编辑逻辑优先在这里沉淀。
- `tools/`：放置本地辅助脚本与桥接工具，例如命令发送、框架回灌、Web 网关；其中 `web_bridge.py` 是当前最核心的 API / 模型 / TD 执行桥接入口。
- `web/`：放置控制台前端界面，当前负责 DeepSeek 单模型入口、多智能体协作过程可视化、命令展示与手动调试。
- `MULTIAGENT_WORKFLOW.md`：多智能体目标架构与职责设计文档。
- `PROJECT_HANDOFF.md`：面向后续接手者的项目交接摘要。
- `PROJECT_DIALOGUE_EXPORT.md`：按项目相关性整理过的历史对话导出。
- `OP_Framework.py` / `OP_Information.py`：TouchDesigner 内部扫描脚本，是工程状态导出的真实来源。
- `OP_Framework.json` / `OP_Information.json`：扫描产物，是读取当前工程、执行前校验与验证回归的真实输入。

## 结构约束

- 新增 multiagent 相关能力时，优先补充到 `agents/`，不要继续把角色职责混进 `tools/`。
- 新增 route / execute / retry 的编排 helper 时，优先下沉到对应 agent runtime，尤其是 orchestrator runtime，不要继续在 `web_bridge.py` 中堆状态机细节。
- `runtime/` 目录是执行快照与调试真相源，不要把它当长期文档目录使用。
- 新增读取能力时，优先补充到 `skills/touchdesigner-project-state-reader/`，必要时再补 `tools/` 辅助脚本。
- 新增编辑能力时，优先补充到 `skills/touchdesigner-op-framework-editor/`，并保持围绕 `OP_Framework` 协议组织。
- 协议知识、使用规则、常见错误优先沉淀在 `skills/`，不要把核心流程再次分散到多个说明文件。
- `tools/` 只保留执行、桥接、打包、测试类工具，不承载重复文档职责。
- `web/` 只消费已有工具接口，不直接复制协议规则；模型入口当前以 DeepSeek 为单一默认路径。
- 扫描脚本与扫描产物保持在项目根级，避免被工具层包裹后增加路径复杂度。
- 读取当前工程时，必须对齐工作区根目录下真实的 `OP_Information.json` / `OP_Framework.json`，不要再回退到旧样本路径。

## 后续扩展原则

- 先判断变更属于 `agents`、`runtime`、`skills`、`tools`、`web` 还是扫描层，再动手修改。
- 优先复用现有目录，不随意新增并列顶层目录。
- 多智能体之间优先通过结构化 Brief 与 Schema 协作，不直接传递整段原始上下文。
- 如果能力既需要说明又需要执行入口，说明放 `skills/`，执行入口放 `tools/`。
- 如果变更涉及读取当前工程，继续以 `OP_Information.json` 与 `OP_Framework.json` 为真相源。
- 如果变更涉及编辑工程，继续以 `OP_Framework` 树与回灌链路为主路径。
- 如果变更涉及网页交互类生成，优先保证输出合法 TouchDesigner OP 类型，不允许生成 `WebContainer`、`Text` 这类伪类型。
