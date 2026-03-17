# TD自动化项目实施与AI操作指南（基于当前代码状态）

## 1. 文档目标与边界

本文档用于统一当前 **TD自动化** 项目的实施方法，重点回答两件事：

1. 用户如何从零完成“让外部 AI 智能体实时操作 TouchDesigner（TD）”的部署；
2. AI 应该用什么具体操作协议，来完成在 TD 中的创建组件、修改参数、组件连线等动作。

本文内容完全基于当前仓库代码实现，不引入未落地的新机制。

当前版本的核心目标是：让用户以最小操作成本，把自己的 AI 智能体稳定接入任意 TouchDesigner 工程，并形成“读取工程 -> 分析问题 -> 生成标准 JSON -> 实时编辑工程 -> 回读验证”的闭环。

为避免误解，本文所有能力将明确标注为：

- **已实现（可直接使用）**：当前仓库代码已落地，按文档即可运行；
- **规划中（未实现）**：用于下一阶段重构，不应当作当前可用能力承诺。

---

## 2. 当前项目逻辑总览（端到端）

当前项目是一个“**TCP 文本命令驱动的 TD 执行层 + 工程结构化导出/导入能力 + Web 对话与测试控制台**”，链路如下：

1. TD 启动后，通过 `bootstrap.init()` 初始化自动化运行时；
2. `App` 单例注册到 `op('/').storage`，作为统一执行入口；
3. 外部客户端（可由 AI 驱动）通过 TCP 发送一行 JSON 指令；
4. TD 的 TCP/IP DAT 回调收到文本后，转发给 `commands.dispatch()`；
5. `dispatch` 根据 `cmd` 字段路由到 `App` 的具体方法执行；
6. TD 将执行结果或错误通过 TCP 回包给客户端；
7. 通过 `OP_Framework.py` 与 `OP_Information.py` 可导出工程逻辑与细节为标准 JSON；
8. 通过 `replicate_framework` 可将标准 JSON 复刻回真实 TD 工程。
9. 通过 `tools/web_bridge.py` 提供本地 HTTP 网关，把 Web 前端请求映射为 TD TCP 指令；
10. Web 前端 `web/index.html + web/app.js` 提供 ChatGPT 风格对话、模型配置、命令测试与一键执行。

该架构等价于：**AI 需要同时掌握“结构化读取 + 问题分析 + 标准 JSON 构建 + JSON 回灌执行 + 回读校验”**，即可完成远程闭环开发。

---

## 3. 用户侧实施步骤（从零到可用）

## 3.1 准备项目文件

确保 TD 工程目录下有以下关键文件：

- `lib/app.py`：核心能力（创建、参数设置、连线、保存、清理、示例搭建）；
- `lib/bootstrap.py`：启动初始化与热重载入口；
- `lib/commands.py`：命令路由；
- `lib/server_callbacks.py`：TCP/IP DAT 回调；
- `lib/config.json`：可选启动配置（初始节点与连线）；
- `tools/send_td_cmds.py`：外部本地发送示例。
- `tools/replicate_framework.py`：按结构化框架 JSON 一键复刻网络的外部脚本。
- `tools/web_bridge.py`：本地 Web 网关（HTTP -> LLM API / TD TCP）。
- `OP_Framework.py`：导出工程结构与关键运行参数（面向复刻）；
- `OP_Information.py`：导出更完整的参数模式、绑定、自定义参数定义等信息（面向分析与诊断）。
- `web/index.html`：Web 控制台页面结构；
- `web/app.js`：对话、模型配置、命令测试、批量执行逻辑；
- `web/style.css`：控制台样式与可访问性焦点样式。

## 3.2 在 TD 中完成启动引导

1. 在 TD 内准备一个用于启动的 DAT Execute（或等效启动脚本触发点）；
2. 在启动回调中执行：

```python
import bootstrap
bootstrap.init()
```

3. `bootstrap.init()` 会做三件事：
   - 把 `project.folder/lib` 加入 `sys.path`；
   - 重载并实例化 `App`；
   - 若 `lib/config.json` 存在，则自动批量创建节点与连线，并默认让新建节点 Viewer 开启。

## 3.3 在 TD 中配置 TCP 服务入口

1. 新建一个 TCP/IP DAT，作为命令接收端；
2. 配置为服务器监听模式，端口与客户端保持一致（当前示例为 `9988`）；
3. 新建一个 Text DAT（建议命名 `server_callbacks`），文件源指向 `lib/server_callbacks.py`；
4. 在 TCP/IP DAT 中将 Callbacks DAT 指向该 `server_callbacks`；
5. 确保 TCP/IP DAT 处于激活监听状态。

## 3.4 先做连通性验证

在 TD 已启动且 TCP 监听后，运行外部脚本 `tools/send_td_cmds.py`（或等价客户端）：

- 能收到 `reload:ok` / `render:/...` / `hover:0|1` 等响应，说明链路已打通；
- 若返回 `error:...`，优先检查：
  - 是否已执行 `bootstrap.init()`；
  - 端口是否一致；
  - 是否以 `\r\n` 作为消息终止；
  - 回调脚本是否正确挂载。

## 3.5 推荐上线流程（稳定版）

1. 固化 `lib/config.json` 为项目最小可运行基线；
2. 每次更新 `lib/*.py` 后，先发送 `reload` 指令；
3. 再发送业务指令（`create/par/connect/...`）；
4. 每条命令都等待回包再发下一条，保证顺序一致性；
5. 定期 `save_project` 产出可回滚 `.toe`。

## 3.6 Web 控制台启动（新增，已实现）

在保持 TD 端 TCP 监听的前提下，可直接启动本地 Web 控制台：

```bash
python3 tools/web_bridge.py
```

默认访问地址：

- `http://127.0.0.1:8765/`

`web_bridge.py` 提供两类能力：

1. 将前端按钮/JSON 编辑器发送的命令转发到 TD TCP 服务；
2. 将对话消息转发到用户配置的大模型 API，并从回复中提取命令数组供一键执行。

## 3.7 Web 控制台使用步骤（新增，已实现）

1. 在左侧“连接设置”填写 TD Host/Port（默认 `127.0.0.1:9988`）；
2. 在“模型配置”选择 Provider，填写 API Key，可按需覆盖 `model/baseUrl`；
3. 点击“测试连通”验证所选模型通道可用；
4. 在中间对话区输入需求，系统会返回建议与可执行命令；
5. 对话区会实时展示 Planner/Executor/Reviewer 阶段状态，并以流式方式逐段输出 AI 回复；
6. 点击“执行AI建议命令”按顺序批量发送到 TD；
7. 可结合阶段状态与审计结论决定是否执行或调整命令；
8. 在底部可折叠测试区，用快捷按钮或自定义 JSON 做快速联调。

---

## 4. AI 操作协议与动作映射

## 4.1 通信协议

- 传输：TCP；
- 负载：单行 JSON 文本；
- 终止符：`\r\n`；
- 响应：成功文本或 `error:<详情>`。

AI 在运行时应遵循：

1. 连接；
2. 发送 1 条 JSON + `\r\n`；
3. 读取回包；
4. 根据回包判定成功/失败；
5. 再发下一条。

## 4.2 创建组件（Create）

### 指令

```json
{
  "cmd": "create",
  "parent": "/project1",
  "type": "constantCHOP",
  "name": "const1",
  "params": { "value0": 0.5 }
}
```

### AI 执行要点

- `parent` 必须是已存在路径；
- `type` 必须是 TD 可识别 OP 类型字符串；
- `name` 可选，不传则由 TD 默认命名；
- 若 `params` 提供，创建后立即设置参数。

## 4.3 修改组件参数（Par）

### 指令

```json
{
  "cmd": "par",
  "path": "/project1/const1",
  "params": { "value0": 0.8 }
}
```

### AI 执行要点

- `path` 必须精确到节点；
- `params` 可批量设置多个参数；
- 参数名无效时系统会跳过并打印调试信息，不会自动更名。

## 4.4 组件连线（Connect）

### 指令

```json
{
  "cmd": "connect",
  "dest": "/project1/merge1",
  "src": ["/project1/const1", "/project1/noise1"]
}
```

### AI 执行要点

- 连线按 `src` 数组顺序接入 `dest` 的输入口；
- 第 1 个 `src` -> input 0，第 2 个 `src` -> input 1；
- `dest` 或 `src` 任一路径不存在会直接报错。

## 4.5 其他已支持能力

- `clear`：清空父容器下直接子节点；
- `save_tox`：保存 COMP 为 `.tox`；
- `save_project`：保存工程 `.toe`；
- `build_glsl_cube`：一键搭建自转立方体 + hover 联动示例；
- `hover`：手动写入 `uHover`；
- `reload`：热重载 `app.py` 并替换单例。
- `replicate_framework`：按导出的结构化 JSON 完整复刻网络（节点、坐标、参数、连线、DAT 内容、自定义参数页、drawState）。
- `delete/remove/destroy`：删除指定节点；
- `exists`：判断路径节点是否存在；
- `list_children`：列出父容器直接子节点；
- `inspect`：读取节点类型、父子关系、errors/warnings 等诊断信息。

## 4.6 结构化框架复刻（Replicate Framework）

### 指令

```json
{
	"cmd": "replicate_framework",
	"file": "OP_Framework copy.json",
	"clear_parent": true
}
```

### AI 执行要点

- `file` 支持绝对路径或相对 `project.folder` 的路径；
- 框架文件按 `utf-8-sig` 读取，可兼容带 BOM 的 JSON；
- `clear_parent=true` 时先清空 `/project1`，再按层级重建，确保可重复执行；
- 复刻会恢复 `drawState`（包含 `display/render/template/compare/pickable/...`）；
- 复刻会恢复 `customParameters`（含页面、定义、组参数 `size/components/componentNames`）；
- 参数模式会恢复 `ParMode`，并处理 `ParMode.BIND` 的 `bindExpr/bindMaster/bindRange`。

## 4.7 查询与诊断（面向分析闭环）

### 查询类指令

```json
{ "cmd": "exists", "path": "/project1/someNode" }
```

```json
{ "cmd": "list_children", "parent": "/project1" }
```

```json
{ "cmd": "inspect", "path": "/project1/someNode" }
```

```json
{ "cmd": "project_diagnostics", "root": "/project1", "recursive": true, "include_clean": false, "limit": 500 }
```

### 编辑类补充指令

```json
{ "cmd": "delete", "path": "/project1/someNode" }
```

### AI 执行要点

- 在批量编辑前先 `exists/list_children/inspect` 做状态确认，减少盲操作；
- `inspect` 回包可用于实时收敛错误与警告；
- `project_diagnostics` 用于抓取工程范围内的错误与警告快照（支持递归与条数限制）；
- 当用户要求“部分模块编辑”时，优先在目标容器内局部执行，不做全局 `clear`。

## 4.8 Web 网关接口（新增，已实现）

当前 `tools/web_bridge.py` 暴露以下本地接口：

1. `POST /api/td/send`：发送单条 TD 命令；
2. `POST /api/td/batch`：按顺序发送命令数组，遇到 `error:` 自动中断；
3. `POST /api/model/test`：按 Provider 协议做模型连通性测试；
4. `POST /api/model/chat`：非流式对话接口，返回完整结果；
5. `POST /api/model/chat_stream`：流式对话接口，按事件返回阶段状态与回复增量。

`/api/model/chat_stream` 事件类型包括：

- `start`：会话开始；
- `stage`：阶段状态（planner/executor/reviewer/assistant）；
- `reply_delta`：AI 回复增量文本；
- `done`：最终汇总（`reply/commands/collaboration`）；
- `error`：错误事件。

其中 `provider` 已内置兼容：

- `anthropic`
- `openai`
- `nvidia`
- `moonshotai`
- `qwen`
- `minimax`
- `deepseek`
- `google`

前端底部测试区已封装当前项目高频命令按钮，包括：

- `reload`
- `build_glsl_cube`
- `hover`
- `list_children`
- `exists`
- `inspect`
- `project_diagnostics`
- `save_project`
- `clear`
- `create`
- `replicate_framework`

---

## 5. 给 AI 的标准化执行策略（建议直接固化到智能体提示词）

为减少误操作，建议 AI 始终按以下策略执行：

1. **先热重载**：会话开始先发 `reload`；
2. **再变更**：所有网络结构操作按“创建 -> 参数 -> 连线”顺序；
3. **强校验**：每条命令必须读取回包，若 `error:` 立即停止后续批处理；
4. **小步提交**：复杂网络分多条命令发，不一次塞过大 JSON；
5. **可恢复**：关键里程碑后调用 `save_project`；
6. **最小破坏**：仅在明确需要时才执行 `clear`。

---

## 6. 当前配置基线（config.json）解读

当前 `lib/config.json` 的语义是：

1. 在 `/project1` 下创建：
   - `const1`（constantCHOP，`value0=0.5`）；
   - `noise1`（noiseCHOP，`amplitude=1.0`）；
   - `merge1`（mergeCHOP）；
2. 将 `const1` 和 `noise1` 连接到 `merge1`。

这份配置可作为“启动后自动生成基础网络”的最小模板。

---

## 7. 开发过程沉淀的关键经验（避免重复踩坑）

1. **连线不能假设 `setInput` 可用**  
   对通用 OP，采用 `inputConnectors[i].connect(src)` 更稳。

2. **TCP 回调签名要做多版本兼容**  
   不同 TD 构建在 `onConnect/onReceive` 的参数形态可能不同，必须兼容现代签名与旧签名。

3. **回包终止符要明确设为 `\r\n`**  
   否则客户端可能因终止符不一致出现读阻塞或“看似无响应”。

4. **热重载必须替换 App 实例**  
   仅 reload 模块不够，旧实例方法仍可能指向旧代码。

5. **模块加载要规避 DAT 同名遮蔽**  
   使用磁盘路径 + 别名加载可降低 `/app`、`/bootstrap` 等命名冲突风险。

6. **保存 `.toe` 前需临时移除单例存储**  
   可规避保存时序列化（pickle）对象失败问题，保存后再恢复。  
   另外，`reload` 的模块加载必须使用稳定模块名并注册到 `sys.modules`，否则可能出现 `Can't pickle ... import of module failed`。

7. **参数命名/接口存在版本差异**  
   例如材质、背景 TOP、DAT 文本写入、Viewer 开关、Flag 字段名等，都需要降级兜底写法。

8. **组参数不是“一个参数”**  
   对 `size>1` 的自定义参数组，必须按 `components/componentNames` 恢复每个分量，并同步组定义（label、范围、模式）。

9. **BIND 模式不只是一条字符串**  
   新导出格式里 `bind` 可能是对象，需解析 `bindExpr/bindMaster/bindRange`，不能只写 `val`。

10. **geometryCOMP 默认子节点与 SOP 路径要修复**  
   清理默认子节点后，需要确保 `soppath` 指向正确输入（如 `in1`），否则会出现网络存在但几何不显示。

11. **BIND 导出格式存在两种形态**  
   既可能是扁平字段，也可能是 `bind` 对象；导入时必须兼容两种结构并恢复 `bindRange`。

12. **组参数需同时恢复“组定义 + 分量”**  
   对 `size>1` 参数组，必须同时恢复 `size/componentNames/components`，避免只创建组名而丢失分量参数。

---

## 8. 验收清单（部署完成标准）

满足以下条件可判定部署完成：

1. TD 启动后自动执行 `bootstrap.init()` 且不报错；
2. `/project1` 可被创建或复用；
3. `config.json` 节点与连线可自动落地；
4. 外部发送 `create/par/connect/reload/replicate_framework` 均有稳定回包；
5. 出错时客户端能收到 `error:` 详情；
6. 能成功执行一次 `save_project` 产出工程文件；
7. 能通过 `OP_Framework.py` 或 `OP_Information.py` 导出结构化 JSON；
8. 能通过 `replicate_framework` 将标准 JSON 回灌并复刻成功；
9. 能通过 `exists/list_children/inspect` 完成基础查询与诊断闭环；
10. 能启动 `python3 tools/web_bridge.py` 并打开 `http://127.0.0.1:8765/`；
11. 模型配置区可对目标 Provider 完成 API 连通性测试；
12. 对话区可提取并执行命令数组，底部测试区按钮可稳定触发 TD 回包。

---

## 9. 现状评价（基于当前实现）

### 9.1 优势（已实现）

1. **协议闭环完整**  
   已具备“读取 -> 分析 -> 生成 -> 执行 -> 回读”的最小闭环，支持 AI 做自检与纠错。
2. **工程化解耦清晰**  
   TD 内部网络被抽象为结构化 JSON，外部 Agent 不需要依赖 TD 底层实现细节。
3. **稳定性细节已沉淀**  
   包括 `inputConnectors` 连线、热重载实例替换、BIND 兼容、BOM 兼容、保存 pickle 风险处理等。
4. **编辑能力覆盖主路径**  
   已支持创建、改参、连线、删除、复刻、自定义参数恢复、查询与诊断、工程保存。
5. **Web 人机交互层已落地**  
   已提供 ChatGPT 风格对话 UI、模型配置与命令测试区，降低非脚本用户的接入门槛。
6. **思考可视化与流式输出已落地**  
   对话区可显示多智能体阶段进度，并以流式方式输出最终回复文本。

### 9.2 风险与不足（当前仍存在）

1. **缺少规划层（未实现）**  
   当前是命令执行层，不是任务分解器；复杂目标仍依赖外部 Agent 自行规划。
2. **上下文膨胀风险（部分缓解，未根治）**  
   已有 `exists/list_children/inspect` 渐进查询，但仍缺少内建长期记忆与摘要压缩机制。
3. **实时性与批量修改冲突（未系统治理）**  
   顺序执行保证一致性，但对高负载工程可能造成卡顿，尚无批处理节流与事务执行策略。
4. **密钥管理仍偏本地开发形态（未系统治理）**  
   当前 Web 端配置默认保存在浏览器本地存储，适合本地开发，不适合共享终端或生产环境。

---

## 10. 进阶重构路线图（明确区分已实现/未实现）

### 10.1 架构升级：三智能体协作

- **规划专家（Planner）**：把复杂视觉需求拆分为可执行子任务。  
  状态：**已实现基础能力**（Web 对话链路已接入任务拆分）
- **执行者（Executor）**：生成并执行 JSON 指令流，执行前先做 exists/inspect。  
  状态：**已实现增强能力**（已在命令生成阶段自动注入 exists/inspect 前置校验）
- **审计员（Reviewer）**：基于 errors/warnings 与性能数据给出优化建议。  
  状态：**部分实现**（已接入执行审计与风险建议，性能指标仍未实现）

### 10.2 上下文工程：渐进式披露

- `list_children -> inspect -> 定向编辑` 的分层读取流程。  
  状态：**已实现**
- NoteTool/长期记忆机制（记录关键路径、绑定关系、阶段状态）。  
  状态：**未实现（规划中）**
- 全量扫描抑制与摘要化输出策略。  
  状态：**未实现（规划中）**

### 10.3 协议增强：从低层指令到高层技能

- 低层命令（create/par/connect/delete/replicate_framework）  
  状态：**已实现**
- 高层技能（如 `build_feedback_loop`、`build_interactive_particle_system`）  
  状态：**未实现（规划中）**

### 10.4 下一阶段三大优先级

1. **状态监测与断点续传**  
   目标：失败后可恢复并继续执行。  
   状态：**部分实现**（已有 `save_project` 快照；断点续传流程未实现）
2. **性能分析深度集成（Performance Analytics）**  
   目标：把帧耗时/GPU占用结构化回传给 Agent。  
   状态：**未实现（规划中）**
3. **人类在环反馈机制（Human-in-the-loop）**  
   目标：关键步骤触发画面反馈（截图/导出）后再继续。  
   状态：**未实现（规划中）**

---

## 11. 面向后续扩展的建议（不影响当前可用性）

1. 建议引入 `request_id` 字段，实现请求-响应对齐与审计日志；
2. 建议维护 OP 类型与参数白名单，降低 AI 误指令风险；
3. 建议将 `OP_Information.json` 从空数组升级为“能力清单/别名映射”；
4. 建议为 Web 网关增加 API Key 加密存储与过期策略；
5. 建议将客户端示例升级为可批处理、可重试、可超时策略化的 SDK；
6. 建议把 `/api/model/chat` 的命令提取升级为“代码块 + 多段容错”解析策略。

以上建议属于增强项，当前版本已具备可运行的远程控制主链路。
