const PROVIDER_PRESETS = {
	openai: { model: "gpt-4o-mini", baseUrl: "https://api.openai.com/v1/chat/completions" },
	anthropic: { model: "claude-3-5-sonnet-latest", baseUrl: "https://api.anthropic.com/v1/messages" },
	nvidia: { model: "nvidia/llama-3.1-nemotron-70b-instruct", baseUrl: "https://integrate.api.nvidia.com/v1/chat/completions" },
	moonshotai: { model: "kimi-k2.5", baseUrl: "https://api.moonshot.cn/v1/chat/completions" },
	qwen: { model: "qwen-plus", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions" },
	minimax: { model: "MiniMax-Text-01", baseUrl: "https://api.minimax.chat/v1/text/chatcompletion_v2" },
	deepseek: { model: "deepseek-chat", baseUrl: "https://api.deepseek.com/chat/completions" },
	google: { model: "gemini-2.0-flash", baseUrl: "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent" }
};

const QUICK_COMMANDS = [
	{ label: "reload", command: { cmd: "reload" } },
	{ label: "list_children", command: { cmd: "list_children", parent: "/project1" } },
	{ label: "exists:/project1", command: { cmd: "exists", path: "/project1" } },
	{ label: "inspect:/project1", command: { cmd: "inspect", path: "/project1" } },
	{ label: "project_diagnostics", command: { cmd: "project_diagnostics", root: "/project1", recursive: true, include_clean: false, limit: 200 } },
	{ label: "save_project", command: { cmd: "save_project" } },
	{ label: "replicate_framework", command: { cmd: "replicate_framework", file: "OP_Framework copy.json", clear_parent: true } }
];

const state = {
	messages: [],
	suggestedCommands: []
};

const el = {
	provider: document.getElementById("provider"),
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
	commandJsonOutput: document.getElementById("commandJsonOutput")
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

function appendAgentCollaboration(collaboration) {
	if (!collaboration || typeof collaboration !== "object") {
		return;
	}
	const planner = collaboration.planner || {};
	const executor = collaboration.executor || {};
	const reviewer = collaboration.reviewer || {};
	const plannerTasks = Array.isArray(planner.tasks) ? planner.tasks.length : 0;
	const executorCommands = Array.isArray(executor.commands) ? executor.commands.length : 0;
	const reviewerRisks = Array.isArray(reviewer.risks) ? reviewer.risks.length : 0;
	appendMessage("agent", `Planner\n状态: 已实现\n任务数: ${plannerTasks}\n摘要: ${planner.summary || "无"}`);
	appendMessage("agent", `Executor\n状态: 已实现基础能力\n命令数: ${executorCommands}\n执行说明: ${executor.reply || "无"}`);
	appendMessage("agent", `Reviewer\n状态: 部分实现\n风险数: ${reviewerRisks}\n性能指标: ${reviewer.performance === "provided" ? "已提供" : "未实现"}`);
}

function loadConfig() {
	const saved = localStorage.getItem("td_ai_console_config");
	if (!saved) {
		return;
	}
	try {
		const cfg = JSON.parse(saved);
		el.provider.value = cfg.provider || "openai";
		el.model.value = cfg.model || "";
		el.baseUrl.value = cfg.baseUrl || "";
		el.apiKey.value = cfg.apiKey || "";
		el.temperature.value = cfg.temperature ?? 0.2;
		el.tdHost.value = cfg.tdHost || "127.0.0.1";
		el.tdPort.value = cfg.tdPort || 9988;
	} catch (err) {
		console.error(err);
	}
}

function saveConfig() {
	const cfg = getConfig();
	localStorage.setItem("td_ai_console_config", JSON.stringify(cfg));
	el.modelStatus.textContent = "配置已保存";
}

function normalizeTemperature(provider, model, temperature) {
	let next = Number(temperature);
	if (Number.isNaN(next)) {
		next = 0.2;
	}
	const p = String(provider || "").toLowerCase();
	const m = String(model || "").toLowerCase();
	if (p === "moonshotai" && m.startsWith("kimi-k2.5")) {
		return 1;
	}
	return next;
}

function normalizeBaseUrl(provider, baseUrl) {
	const p = String(provider || "").toLowerCase();
	const preset = PROVIDER_PRESETS[p] || null;
	let url = String(baseUrl || "").trim();
	if (!preset) {
		return url;
	}
	if (!url) {
		return preset.baseUrl;
	}
	if (url.includes("platform.moonshot.cn/docs")) {
		return preset.baseUrl;
	}
	if (url.startsWith("http://")) {
		url = "https://" + url.slice("http://".length);
	}
	if (!url.startsWith("https://")) {
		return preset.baseUrl;
	}
	return url;
}

function getConfig() {
	const provider = el.provider.value;
	const model = el.model.value.trim();
	const temperature = normalizeTemperature(provider, model, el.temperature.value || 0.2);
	const baseUrl = normalizeBaseUrl(provider, el.baseUrl.value);
	el.temperature.value = String(temperature);
	el.baseUrl.value = baseUrl;
	return {
		provider,
		model,
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

function hydrateProviderOptions() {
	const providers = Object.keys(PROVIDER_PRESETS);
	providers.forEach((name) => {
		const option = document.createElement("option");
		option.value = name;
		option.textContent = name;
		el.provider.appendChild(option);
	});
	el.provider.value = "openai";
}

function applyPresetForProvider() {
	const current = el.provider.value;
	const preset = PROVIDER_PRESETS[current];
	if (!preset) {
		return;
	}
	if (!el.model.value) {
		el.model.value = preset.model;
	}
	if (!el.baseUrl.value) {
		el.baseUrl.value = preset.baseUrl;
	}
	const nextTemperature = normalizeTemperature(current, el.model.value, el.temperature.value || 0.2);
	el.temperature.value = String(nextTemperature);
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

function applyChatResult(result, aiBubble, aiReplyRef) {
	if (!result || !result.ok) {
		aiBubble.textContent = `调用失败: ${(result && result.error) || "未知错误"}`;
		return aiReplyRef;
	}
	appendAgentCollaboration(result.collaboration);
	const reply = String(result.reply || "");
	if (!aiReplyRef && reply) {
		aiReplyRef = reply;
		aiBubble.textContent = aiReplyRef;
	}
	const nextCommands = Array.isArray(result.commands) ? result.commands : [];
	renderSuggestedCommands(nextCommands, { autoOpen: nextCommands.length > 0, suffix: "最终结果" });
	if (nextCommands.length) {
		appendMessage("ai", `已提取 ${nextCommands.length} 条命令，可点击“执行AI建议命令”`);
	} else {
		appendMessage("ai", "AI 本次没有生成可执行命令，请检查模型返回是否包含 write_framework_json / replicate_framework 链路");
	}
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
	const cfg = getConfig();
	const payload = {
		config: {
			provider: cfg.provider,
			model: cfg.model,
			baseUrl: cfg.baseUrl,
			apiKey: cfg.apiKey,
			temperature: cfg.temperature
		},
		messages: state.messages
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
			if (done) {
				break;
			}
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
					continue;
				}
				if (event === "stage") {
					appendMessage("agent", data.message || `${data.stage || "agent"}: ${data.status || "running"}`);
					if (data.stage === "executor" && data.status === "done" && Array.isArray(data.commands)) {
						renderSuggestedCommands(data.commands, { autoOpen: true, suffix: "Executor阶段" });
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
					throw new Error(data.message || "流式调用失败");
				}
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
	renderSuggestedCommands(state.suggestedCommands, { autoOpen: true, suffix: `执行后 ok=${Boolean(result.ok)}` });
	appendMessage("ai", `命令执行结果:\n${JSON.stringify(result, null, 2)}`);
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
	document.getElementById("btnDiagnostics").addEventListener("click", () => sendSingleCommand({ cmd: "project_diagnostics", root: "/project1", recursive: true, include_clean: false, limit: 300 }));
	el.provider.addEventListener("change", () => {
		el.model.value = "";
		el.baseUrl.value = "";
		applyPresetForProvider();
	});
	el.userInput.addEventListener("keydown", (event) => {
		if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
			sendChat();
		}
	});
}

function bootstrap() {
	hydrateProviderOptions();
	applyPresetForProvider();
	loadConfig();
	if (!el.model.value || !el.baseUrl.value) {
		applyPresetForProvider();
	}
	bindQuickButtons();
	bindEvents();
	appendMessage("ai", "已就绪：你可以直接描述目标，我会生成并可执行 TD JSON 命令。");
}

bootstrap();
