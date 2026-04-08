const DEEPSEEK_CONFIG = {
	provider: "deepseek",
	model: "deepseek-chat",
	baseUrl: "https://api.deepseek.com/chat/completions"
};

const QUICK_COMMANDS = [
	{ label: "reload", command: { cmd: "reload" } },
	{ label: "refresh_project_state", command: { cmd: "refresh_project_state", secret_agent_path: "/SecretAgent" } },
	{ label: "save_project", command: { cmd: "save_project" } },
	{ label: "replicate_framework", command: { cmd: "replicate_framework", file: "OP_Framework.json", clear_parent: true } }
];

const WORKFLOW_NODE_ORDER = ["orchestrator", "state_reader", "kb_consultant", "framework_editor", "verifier", "assistant"];
const WORKFLOW_NODE_META = {
	orchestrator: { title: "Orchestrator", hint: "任务调度与分析" },
	state_reader: { title: "State Reader", hint: "读取 TD 现状" },
	kb_consultant: { title: "KB Consultant", hint: "知识库校验" },
	framework_editor: { title: "Framework Editor", hint: "生成连线与执行草案" },
	verifier: { title: "Verifier", hint: "审计执行并控制回环" },
	assistant: { title: "Assistant", hint: "最终回复汇总" }
};

function createWorkflowState(statusText = "等待新任务") {
	const nodes = {};
	WORKFLOW_NODE_ORDER.forEach((key) => {
		nodes[key] = {
			status: "idle",
			summary: "",
			metrics: []
		};
	});
	return {
		statusText,
		metaText: "尚未开始",
		nodes,
		timeline: []
	};
}

const state = {
	messages: [],
	suggestedCommands: [],
	projectSummary: null,
	recentHistory: [],
	workflow: createWorkflowState()
};

const el = {
	model: document.getElementById("model"),
	baseUrl: document.getElementById("baseUrl"),
	apiKey: document.getElementById("apiKey"),
	temperature: document.getElementById("temperature"),
	tdHost: document.getElementById("tdHost"),
	tdPort: document.getElementById("tdPort"),
	modelStatus: document.getElementById("modelStatus"),
	chatMessages: document.getElementById("chatMessages"),
	userInput: document.getElementById("userInput"),
	customCommand: document.getElementById("customCommand"),
	testerOutput: document.getElementById("testerOutput"),
	testerBody: document.getElementById("testerBody"),
	quickButtons: document.getElementById("quickButtons"),
	sendBtn: document.getElementById("sendBtn"),
	commandDetails: document.getElementById("commandDetails"),
	commandSummary: document.getElementById("commandSummary"),
	commandJsonOutput: document.getElementById("commandJsonOutput"),
	btnRefreshSummary: document.getElementById("btnRefreshSummary"),
	autoRefreshSummary: document.getElementById("autoRefreshSummary"),
	summaryStatus: document.getElementById("summaryStatus"),
	workflowGraph: document.getElementById("workflowGraph"),
	workflowTimeline: document.getElementById("workflowTimeline"),
	workflowStatus: document.getElementById("workflowStatus"),
	workflowMeta: document.getElementById("workflowMeta"),
	btnCopyDebugInfo: document.getElementById("btnCopyDebugInfo")
};

function appendMessage(role, content) {
	const div = document.createElement("div");
	if (role === "user") {
		div.className = "msg user";
	} else if (role === "agent") {
		div.className = "msg agent";
	} else {
		div.className = "msg ai";
	}
	div.textContent = content;
	el.chatMessages.appendChild(div);
	el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
	return div;
}

function loadConfig() {
	const saved = localStorage.getItem("td_ai_console_config");
	if (!saved) {
		el.model.value = DEEPSEEK_CONFIG.model;
		el.baseUrl.value = DEEPSEEK_CONFIG.baseUrl;
		el.apiKey.value = "sk-3e6765a488f84d7b9fbbc828f15559bc";
		el.temperature.value = 0.2;
		el.tdHost.value = "127.0.0.1";
		el.tdPort.value = "9988";
		return;
	}
	try {
		const cfg = JSON.parse(saved);
		el.model.value = cfg.model || DEEPSEEK_CONFIG.model;
		el.baseUrl.value = cfg.baseUrl || DEEPSEEK_CONFIG.baseUrl;
		el.apiKey.value = cfg.apiKey || "sk-3e6765a488f84d7b9fbbc828f15559bc";
		el.temperature.value = cfg.temperature ?? 0.2;
		el.tdHost.value = cfg.tdHost || "127.0.0.1";
		el.tdPort.value = cfg.tdPort || 9988;
	} catch (err) {
		console.error(err);
		el.apiKey.value = "sk-3e6765a488f84d7b9fbbc828f15559bc";
	}
}

function saveConfig() {
	const cfg = getConfig();
	localStorage.setItem("td_ai_console_config", JSON.stringify(cfg));
	el.modelStatus.textContent = "DeepSeek 配置已保存";
}

function normalizeTemperature(temperature) {
	let next = Number(temperature);
	if (Number.isNaN(next)) {
		next = 0.2;
	}
	next = Math.max(0, Math.min(1.5, next));
	return next;
}

function normalizeBaseUrl(baseUrl) {
	let url = String(baseUrl || "").trim();
	if (!url) {
		return DEEPSEEK_CONFIG.baseUrl;
	}
	if (url.startsWith("http://")) {
		url = "https://" + url.slice("http://".length);
	}
	if (!url.startsWith("https://")) {
		return DEEPSEEK_CONFIG.baseUrl;
	}
	return url;
}

function getConfig() {
	const model = el.model.value.trim();
	const temperature = normalizeTemperature(el.temperature.value || 0.2);
	const baseUrl = normalizeBaseUrl(el.baseUrl.value);
	el.temperature.value = String(temperature);
	el.baseUrl.value = baseUrl;
	return {
		provider: DEEPSEEK_CONFIG.provider,
		model: model || DEEPSEEK_CONFIG.model,
		baseUrl,
		apiKey: el.apiKey.value.trim(),
		temperature,
		tdHost: el.tdHost.value.trim() || "127.0.0.1",
		tdPort: Number(el.tdPort.value || 9988)
	};
}

async function postJson(url, body) {
	const resp = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body)
	});
	return resp.json();
}

async function testModelConnection() {
	const cfg = getConfig();
	el.modelStatus.textContent = "测试中...";
	const result = await postJson("/api/model/test", cfg);
	if (result.ok) {
		el.modelStatus.textContent = `连通成功: ${String(result.reply || "").slice(0, 80)}`;
	} else {
		el.modelStatus.textContent = `连通失败: ${result.error || "未知错误"}`;
	}
}

function ensureDeepSeekDefaults() {
	if (!el.model.value) {
		el.model.value = DEEPSEEK_CONFIG.model;
	}
	if (!el.baseUrl.value) {
		el.baseUrl.value = DEEPSEEK_CONFIG.baseUrl;
	}
	el.temperature.value = String(normalizeTemperature(el.temperature.value || 0.2));
}

function renderSuggestedCommands(commands, options = {}) {
	const arr = Array.isArray(commands) ? commands : [];
	state.suggestedCommands = arr;
	el.commandJsonOutput.textContent = JSON.stringify(arr, null, 2);
	const suffix = options.suffix ? ` - ${options.suffix}` : "";
	el.commandSummary.textContent = `AI生成命令 JSON（${arr.length} 条）${suffix}`;
	if (options.autoOpen && arr.length) {
		el.commandDetails.open = true;
	}
}

function setWorkflowStatus(text, metaText = "") {
	state.workflow.statusText = text || "等待新任务";
	if (metaText) {
		state.workflow.metaText = metaText;
	}
	renderWorkflow();
}

function resetWorkflow(statusText = "等待新任务") {
	state.workflow = createWorkflowState(statusText);
	renderWorkflow();
}

function updateWorkflowNode(stage, patch = {}) {
	if (!WORKFLOW_NODE_ORDER.includes(stage)) {
		return;
	}
	const node = state.workflow.nodes[stage];
	node.status = patch.status || node.status;
	node.summary = patch.summary !== undefined ? String(patch.summary || "") : node.summary;
	if (Array.isArray(patch.metrics)) {
		node.metrics = patch.metrics.filter((item) => typeof item === "string" && item.trim());
	}
	renderWorkflow();
}

function pushWorkflowEvent(text) {
	const stamp = new Date().toLocaleTimeString();
	state.workflow.timeline.unshift(`${stamp} · ${text}`);
	state.workflow.timeline = state.workflow.timeline.slice(0, 10);
	renderWorkflow();
}

function renderWorkflow() {
	el.workflowStatus.textContent = state.workflow.statusText;
	el.workflowMeta.textContent = state.workflow.metaText || "尚未开始";
	el.workflowGraph.innerHTML = "";
	WORKFLOW_NODE_ORDER.forEach((stage, index) => {
		const nodeState = state.workflow.nodes[stage];
		const meta = WORKFLOW_NODE_META[stage];
		const card = document.createElement("article");
		card.className = `workflow-card ${nodeState.status}`;
		const title = document.createElement("h3");
		title.textContent = meta.title;
		const hint = document.createElement("div");
		hint.className = "workflow-hint";
		hint.textContent = meta.hint;
		const status = document.createElement("div");
		status.className = "workflow-card-status";
		status.textContent = `状态：${nodeState.status}`;
		const summary = document.createElement("div");
		summary.className = "workflow-card-summary";
		summary.textContent = nodeState.summary || "等待触发";
		const metrics = document.createElement("div");
		metrics.className = "workflow-metrics";
		(nodeState.metrics || []).forEach((item) => {
			const pill = document.createElement("span");
			pill.className = "workflow-metric";
			pill.textContent = item;
			metrics.appendChild(pill);
		});
		card.appendChild(title);
		card.appendChild(hint);
		card.appendChild(status);
		card.appendChild(summary);
		if ((nodeState.metrics || []).length) {
			card.appendChild(metrics);
		}
		el.workflowGraph.appendChild(card);
		if (index < WORKFLOW_NODE_ORDER.length - 1) {
			const arrow = document.createElement("div");
			arrow.className = "workflow-arrow";
			arrow.textContent = "→";
			el.workflowGraph.appendChild(arrow);
		}
	});
	el.workflowTimeline.innerHTML = "";
	if (!state.workflow.timeline.length) {
		const empty = document.createElement("div");
		empty.className = "workflow-timeline-empty";
		empty.textContent = "暂无协作事件";
		el.workflowTimeline.appendChild(empty);
		return;
	}
	state.workflow.timeline.forEach((item) => {
		const row = document.createElement("div");
		row.className = "workflow-event";
		row.textContent = item;
		el.workflowTimeline.appendChild(row);
	});
}

function applyCollaboration(collaboration, replyText = "") {
	if (!collaboration || typeof collaboration !== "object") {
		return;
	}
	const task_brief = collaboration.outputs?.task_brief || {};
	const edit_plan_brief = collaboration.outputs?.edit_plan_brief || {};
	const validation_brief = collaboration.outputs?.validation_brief || {};
	const compatibility_brief = collaboration.outputs?.compatibility_brief || {};

	updateWorkflowNode("orchestrator", {
		status: "done",
		summary: task_brief.summary || "任务调度完成",
		metrics: [
			`任务分类: ${task_brief.task_type || "未知"}`
		]
	});
	updateWorkflowNode("state_reader", {
		status: "done",
		summary: "项目现状已读取",
		metrics: []
	});
	updateWorkflowNode("kb_consultant", {
		status: "done",
		summary: compatibility_brief.compatibility_issues ? "发现兼容性问题" : "兼容性正常",
		metrics: [
			`风险数: ${Array.isArray(compatibility_brief.compatibility_issues) ? compatibility_brief.compatibility_issues.length : 0}`
		]
	});
	updateWorkflowNode("framework_editor", {
		status: "done",
		summary: "连线草案生成",
		metrics: [
			`改动: ${Array.isArray(edit_plan_brief.framework_changes) ? edit_plan_brief.framework_changes.length : 0} 处`
		]
	});
	updateWorkflowNode("verifier", {
		status: "done",
		summary: validation_brief.validation_status === "approved" ? "审计通过" : "审计发现问题",
		metrics: [
			`重试次数: ${collaboration.outputs?.auto_retry_count || 0}`
		]
	});
	updateWorkflowNode("assistant", {
		status: "done",
		summary: replyText || "最终回复已生成",
		metrics: [
			`回复 ${String(replyText || "").length} 字符`
		]
	});
	setWorkflowStatus("多智能体协作已完成", `Orchestrator / State Reader / KB Consultant / Framework Editor / Verifier`);
}

function applyChatResult(result, aiBubble, aiReplyRef) {
	if (!result || !result.ok) {
		aiBubble.textContent = `调用失败: ${(result && result.error) || "未知错误"}`;
		setWorkflowStatus("协作失败", "请检查模型配置或网络状态");
		return aiReplyRef;
	}
	const reply = String(result.reply || "");
	if (!aiReplyRef && reply) {
		aiReplyRef = reply;
		aiBubble.textContent = aiReplyRef;
	} else if (!aiReplyRef) {
		const assistantOutputs = result.collaboration?.outputs?.final_report || {};
		if (assistantOutputs.summary) {
			aiReplyRef = assistantOutputs.summary;
			aiBubble.textContent = aiReplyRef;
		}
	}
	const nextCommands = Array.isArray(result.commands) ? result.commands : [];
	renderSuggestedCommands(nextCommands, { autoOpen: nextCommands.length > 0, suffix: "最终结果" });
	if (nextCommands.length) {
		appendMessage("ai", `已提取 ${nextCommands.length} 条命令，可点击“执行AI建议命令”`);
	} else {
		appendMessage("ai", "AI 本次没有生成可执行命令，请检查模型返回是否包含 write_framework_json / replicate_framework 链路");
	}
	applyCollaboration(result.collaboration, aiReplyRef);
	return aiReplyRef;
}

async function sendChat() {
	const text = el.userInput.value.trim();
	if (!text) {
		return;
	}
	appendMessage("user", text);
	state.messages.push({ role: "user", content: text });
	el.userInput.value = "";
	resetWorkflow("多智能体协作中...");
	pushWorkflowEvent(`收到新目标：${text}`);
	const cfg = getConfig();
	const payload = {
		config: {
			provider: DEEPSEEK_CONFIG.provider,
			model: cfg.model,
			baseUrl: cfg.baseUrl,
			apiKey: cfg.apiKey,
			temperature: cfg.temperature
		},
		messages: state.messages,
		context: {
			summary: state.projectSummary,
			history: state.recentHistory
		}
	};
	let aiReply = "";
	let lastDonePayload = null;
	const aiBubble = appendMessage("ai", "");
	el.sendBtn.disabled = true;
	renderSuggestedCommands([], { suffix: "等待生成" });
	try {
		const resp = await fetch("/api/model/chat_stream", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(payload)
		});
		if (resp.status === 404) {
			const fallback = await postJson("/api/model/chat", payload);
			aiReply = applyChatResult(fallback, aiBubble, aiReply);
			if (aiReply) {
				state.messages.push({ role: "assistant", content: aiReply });
			}
			return;
		}
		if (!resp.ok || !resp.body) {
			throw new Error(`HTTP ${resp.status}`);
		}
		const reader = resp.body.getReader();
		const decoder = new TextDecoder("utf-8");
		let buffer = "";
		while (true) {
			const { value, done } = await reader.read();
			if (value) {
				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split("\n");
				buffer = lines.pop() || "";
				for (const line of lines) {
					const textLine = line.trim();
					if (!textLine) {
						continue;
					}
					let packet = null;
					try {
						packet = JSON.parse(textLine);
					} catch (err) {
						continue;
					}
					const event = packet.event;
					const data = packet.data || {};
					if (event === "start") {
						appendMessage("agent", data.message || "开始处理");
						setWorkflowStatus(data.message || "已开始处理请求", "DeepSeek 正在驱动多智能体协作");
						pushWorkflowEvent(data.message || "开始处理请求");
						continue;
					}
					if (event === "stage") {
						appendMessage("agent", data.message || `${data.stage || "agent"}: ${data.status || "running"}`);
						const stage = String(data.stage || "");
						if (WORKFLOW_NODE_ORDER.includes(stage)) {
							const metrics = [];
							if (typeof data.taskCount === "number") {
								metrics.push(`任务 ${data.taskCount} 条`);
							}
							if (typeof data.commandCount === "number") {
								metrics.push(`命令 ${data.commandCount} 条`);
							}
							if (data.performance) {
								metrics.push(`性能 ${data.performance === "provided" ? "已提供" : "未实现"}`);
							}
							updateWorkflowNode(stage, {
								status: data.status === "running" || data.status === "streaming" ? "running" : "done",
								summary: data.summary || data.message || "",
								metrics
							});
							setWorkflowStatus(`当前阶段：${WORKFLOW_NODE_META[stage].title}`, data.message || "");
							pushWorkflowEvent(`${WORKFLOW_NODE_META[stage].title} · ${data.message || data.status || "处理中"}`);
						}
						if (data.stage === "framework_editor" && data.status === "done" && Array.isArray(data.commands)) {
							renderSuggestedCommands(data.commands, { autoOpen: true, suffix: "Framework Editor阶段" });
						}
						continue;
					}
					if (event === "reply_delta") {
						aiReply += String(data.delta || "");
						aiBubble.textContent = aiReply;
						el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
						continue;
					}
					if (event === "done") {
						lastDonePayload = data;
						continue;
					}
					if (event === "error") {
						setWorkflowStatus("协作失败", data.message || "流式调用失败");
						pushWorkflowEvent(`失败：${data.message || "流式调用失败"}`);
						throw new Error(data.message || "流式调用失败");
					}
				}
			}
			if (done) {
				buffer += decoder.decode();
				if (buffer.trim()) {
					try {
						const packet = JSON.parse(buffer.trim());
						if (packet.event === "done") lastDonePayload = packet.data;
					} catch(e) {
						console.error("JSON parse error on final buffer:", e, buffer.substring(0, 200));
					}
				}
				break;
			}
		}
		if (lastDonePayload && typeof lastDonePayload === "object") {
			aiReply = applyChatResult({ ok: true, ...lastDonePayload }, aiBubble, aiReply);
		}
		if (!aiReply) {
			aiReply = "已完成处理，但没有返回可显示文本。";
			aiBubble.textContent = aiReply;
		}
		state.messages.push({ role: "assistant", content: aiReply });
	} catch (err) {
		aiBubble.textContent = `调用失败: ${err.message || "未知错误"}`;
		setWorkflowStatus("协作失败", err.message || "未知错误");
	} finally {
		el.sendBtn.disabled = false;
	}
}

async function runSuggestedCommands() {
	if (!state.suggestedCommands.length) {
		appendMessage("ai", "当前没有可执行的AI建议命令");
		return;
	}
	const cfg = getConfig();
	const result = await postJson("/api/td/batch", {
		host: cfg.tdHost,
		port: cfg.tdPort,
		commands: state.suggestedCommands
	});
	
	state.recentHistory.push({
		commands: state.suggestedCommands,
		result: result
	});
	if (state.recentHistory.length > 5) {
		state.recentHistory.shift();
	}
	
	renderSuggestedCommands(state.suggestedCommands, { autoOpen: true, suffix: `执行后 ok=${Boolean(result.ok)}` });
	appendMessage("ai", `命令执行结果:\n${JSON.stringify(result, null, 2)}`);
	
	if (el.autoRefreshSummary.checked) {
		await refreshProjectSummary();
	}
}

async function sendSingleCommand(cmd) {
	const cfg = getConfig();
	const result = await postJson("/api/td/send", {
		host: cfg.tdHost,
		port: cfg.tdPort,
		command: cmd
	});
	el.testerOutput.textContent = JSON.stringify(result, null, 2);
}

async function sendCustomCommand() {
	try {
		const cmd = JSON.parse(el.customCommand.value);
		await sendSingleCommand(cmd);
	} catch (err) {
		el.testerOutput.textContent = `JSON解析失败: ${err.message}`;
	}
}

async function sendBatchCommands() {
	try {
		const arr = JSON.parse(el.customCommand.value);
		if (!Array.isArray(arr)) {
			throw new Error("必须是JSON数组");
		}
		const cfg = getConfig();
		const result = await postJson("/api/td/batch", {
			host: cfg.tdHost,
			port: cfg.tdPort,
			commands: arr
		});
		el.testerOutput.textContent = JSON.stringify(result, null, 2);
	} catch (err) {
		el.testerOutput.textContent = `批量JSON解析失败: ${err.message}`;
	}
}

function bindQuickButtons() {
	QUICK_COMMANDS.forEach((item) => {
		const button = document.createElement("button");
		button.textContent = item.label;
		button.addEventListener("click", () => {
			el.customCommand.value = JSON.stringify(item.command, null, 2);
			sendSingleCommand(item.command);
		});
		el.quickButtons.appendChild(button);
	});
}

function bindEvents() {
	document.getElementById("saveConfigBtn").addEventListener("click", saveConfig);
	document.getElementById("testModelBtn").addEventListener("click", testModelConnection);
	document.getElementById("sendBtn").addEventListener("click", sendChat);
	document.getElementById("execSuggestedBtn").addEventListener("click", runSuggestedCommands);
	document.getElementById("sendCustomBtn").addEventListener("click", sendCustomCommand);
	document.getElementById("sendBatchBtn").addEventListener("click", sendBatchCommands);
	document.getElementById("toggleTester").addEventListener("click", () => {
		el.testerBody.classList.toggle("hidden");
	});
	document.getElementById("btnReload").addEventListener("click", () => sendSingleCommand({ cmd: "reload" }));
	document.getElementById("btnDiagnostics").addEventListener("click", refreshProjectSummary);
	document.getElementById("btnRefreshSummary").addEventListener("click", refreshProjectSummary);
	document.getElementById("btnCopyDebugInfo").addEventListener("click", copyDebugInfo);
	el.userInput.addEventListener("keydown", (event) => {
		if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
			sendChat();
		}
	});
}

function bootstrap() {
	ensureDeepSeekDefaults();
	loadConfig();
	ensureDeepSeekDefaults();
	bindQuickButtons();
	bindEvents();
	renderWorkflow();
	appendMessage("ai", "已就绪：你可以直接描述目标，我会生成并可执行 TD JSON 命令。");
}

function copyDebugInfo() {
	const lastUserMsg = state.messages.slice().reverse().find(m => m.role === 'user');
	const userQuestion = lastUserMsg ? lastUserMsg.content : '暂无最近提问';
	
	const generatedCommands = state.suggestedCommands && state.suggestedCommands.length > 0 
		? JSON.stringify(state.suggestedCommands, null, 2) 
		: '暂无生成的命令';
		
	let executionResult = '尚未执行命令';
	if (state.recentHistory && state.recentHistory.length > 0) {
		const latestHistory = state.recentHistory[state.recentHistory.length - 1];
		if (JSON.stringify(latestHistory.commands) === JSON.stringify(state.suggestedCommands)) {
			executionResult = JSON.stringify(latestHistory.result, null, 2);
		}
	}
	
	const debugText = `=== 提问的问题 ===\n${userQuestion}\n\n=== AI生成的方案(Commands) ===\n${generatedCommands}\n\n=== 最终的运行结果 ===\n${executionResult}`;
	
	navigator.clipboard.writeText(debugText).then(() => {
		const originalText = el.btnCopyDebugInfo.textContent;
		el.btnCopyDebugInfo.textContent = "✅ 已复制";
		setTimeout(() => {
			el.btnCopyDebugInfo.textContent = originalText;
		}, 2000);
	}).catch(err => {
		console.error("复制失败:", err);
		alert("复制失败，请重试");
	});
}

document.addEventListener("DOMContentLoaded", bootstrap);

async function refreshProjectSummary() {
	const cfg = getConfig();
	try {
		el.summaryStatus.textContent = "刷新中...";
		const result = await postJson("/api/project/summary", {
			host: cfg.tdHost,
			port: cfg.tdPort,
			refresh: true,
			secret_agent_path: "/SecretAgent"
		});
		if (result.ok && result.summary) {
			state.projectSummary = result.summary;
			const count = Number(result.summary.information_node_count || 0);
			el.summaryStatus.textContent = `已刷新 ${count} 个节点 (${new Date().toLocaleTimeString()})`;
			return;
		}
		el.summaryStatus.textContent = `刷新失败: ${result.error || "未知错误"}`;
	} catch (err) {
		el.summaryStatus.textContent = `请求失败: ${err.message}`;
	}
}
