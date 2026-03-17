import json
import os
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib import request, error


WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web')
DEFAULT_TD_HOST = '127.0.0.1'
DEFAULT_TD_PORT = 9988
DEFAULT_TIMEOUT = 8


PROVIDER_PRESETS = {
	'openai': {'base_url': 'https://api.openai.com/v1/chat/completions', 'model': 'gpt-4o-mini', 'api_style': 'openai'},
	'anthropic': {'base_url': 'https://api.anthropic.com/v1/messages', 'model': 'claude-3-5-sonnet-latest', 'api_style': 'anthropic'},
	'nvidia': {'base_url': 'https://integrate.api.nvidia.com/v1/chat/completions', 'model': 'nvidia/llama-3.1-nemotron-70b-instruct', 'api_style': 'openai'},
	'moonshotai': {'base_url': 'https://api.moonshot.cn/v1/chat/completions', 'model': 'kimi-k2.5', 'api_style': 'openai'},
	'qwen': {'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions', 'model': 'qwen-plus', 'api_style': 'openai'},
	'minimax': {'base_url': 'https://api.minimax.chat/v1/text/chatcompletion_v2', 'model': 'MiniMax-Text-01', 'api_style': 'openai'},
	'deepseek': {'base_url': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-chat', 'api_style': 'openai'},
	'google': {'base_url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent', 'model': 'gemini-2.0-flash', 'api_style': 'gemini'}
}


ALLOWED_CMDS = [
	'reload', 'create', 'par', 'connect', 'clear', 'save_tox', 'save_project',
	'build_glsl_cube', 'hover', 'replicate_framework', 'delete', 'exists',
	'list_children', 'inspect', 'project_diagnostics'
]

PLANNER_PROMPT = (
	'你是规划专家（Planner）。你的任务是把用户目标拆成可执行子任务。'
	'仅输出JSON对象，不要输出Markdown。'
	'JSON格式: {"summary":"", "tasks":[{"goal":"","target":"","priority":"high|medium|low"}], "assumptions":[""]}。'
)

EXECUTOR_PROMPT = (
	'你是执行者（Executor）。基于用户目标与规划，生成可执行TD命令。'
	'只允许使用以下cmd: ' + ', '.join(ALLOWED_CMDS) + '。'
	'仅输出JSON对象，不要输出Markdown。'
	'JSON格式: {"reply":"给用户的执行说明", "commands":[{"cmd":"..."}], "checks":["执行前校验点"]}。'
	'命令顺序必须安全，复杂任务遵循 reload -> create -> par -> connect。'
)

REVIEWER_PROMPT = (
	'你是审计员（Reviewer）。基于规划和执行草案做风险审计。'
	'必须覆盖 errors/warnings 视角；性能指标尚未接入时要明确标记未实现。'
	'仅输出JSON对象，不要输出Markdown。'
	'JSON格式: {"assessment":"", "risks":[""], "suggestions":[""], "performance":"not_implemented|provided"}。'
)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
	body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
	handler.send_response(status)
	handler.send_header('Content-Type', 'application/json; charset=utf-8')
	handler.send_header('Content-Length', str(len(body)))
	handler.send_header('Access-Control-Allow-Origin', '*')
	handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
	handler.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
	handler.end_headers()
	handler.wfile.write(body)


def _send_td_command(cmd_obj: dict, host: str, port: int, timeout_sec: int):
	payload = json.dumps(cmd_obj, ensure_ascii=False) + '\r\n'
	received = b''
	with socket.create_connection((host, port), timeout=timeout_sec) as sock:
		sock.sendall(payload.encode('utf-8'))
		sock.settimeout(timeout_sec)
		while True:
			chunk = sock.recv(4096)
			if not chunk:
				break
			received += chunk
			if b'\r\n' in received:
				break
	text = received.decode('utf-8', errors='ignore').strip()
	return text


def _build_provider_config(raw: dict):
	provider = str(raw.get('provider', 'openai')).strip().lower()
	preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS['openai'])
	base_url = str(raw.get('baseUrl') or preset['base_url']).strip()
	model = str(raw.get('model') or preset['model']).strip()
	api_key = str(raw.get('apiKey') or '').strip()
	temperature = raw.get('temperature', 0.2)
	try:
		temperature = float(temperature)
	except Exception:
		temperature = 0.2
	if provider == 'moonshotai' and model.lower().startswith('kimi-k2.5'):
		temperature = 1.0
	return {
		'provider': provider,
		'base_url': base_url,
		'model': model,
		'api_key': api_key,
		'temperature': temperature,
		'api_style': preset.get('api_style', 'openai')
	}


def _format_network_error(exc: Exception, base_url: str) -> str:
	msg = str(exc)
	if isinstance(exc, error.URLError):
		reason = getattr(exc, 'reason', None)
		if reason is not None:
			msg = str(reason)
	return f'网络连接失败({msg})，请检查 Base URL: {base_url}。如刚切换过VPN/代理，请恢复网络后重试。'


def _is_connection_refused(exc: Exception) -> bool:
	if not isinstance(exc, error.URLError):
		return False
	reason = getattr(exc, 'reason', None)
	if isinstance(reason, ConnectionRefusedError):
		return True
	text = str(reason if reason is not None else exc).lower()
	return 'connection refused' in text or 'errno 61' in text


def _request_json(url: str, headers: dict, body: dict, timeout_sec: int):
	data = json.dumps(body, ensure_ascii=False).encode('utf-8')
	req = request.Request(url, data=data, headers=headers, method='POST')
	try:
		with request.urlopen(req, timeout=timeout_sec) as resp:
			raw = resp.read().decode('utf-8', errors='ignore')
			if not raw:
				return {}
			return json.loads(raw)
	except error.URLError as exc:
		if not _is_connection_refused(exc):
			raise
		no_proxy_opener = request.build_opener(request.ProxyHandler({}))
		with no_proxy_opener.open(req, timeout=timeout_sec) as resp:
			raw = resp.read().decode('utf-8', errors='ignore')
			if not raw:
				return {}
			return json.loads(raw)


def _extract_text_from_openai(payload: dict):
	choices = payload.get('choices', [])
	if not isinstance(choices, list) or not choices:
		return ''
	first = choices[0] if isinstance(choices[0], dict) else {}
	message = first.get('message', {})
	if isinstance(message, dict):
		return str(message.get('content', '') or '')
	return ''


def _extract_text_from_anthropic(payload: dict):
	content = payload.get('content', [])
	if not isinstance(content, list):
		return ''
	chunks = []
	for item in content:
		if isinstance(item, dict) and item.get('type') == 'text':
			chunks.append(str(item.get('text', '')))
	return '\n'.join([x for x in chunks if x]).strip()


def _extract_text_from_gemini(payload: dict):
	candidates = payload.get('candidates', [])
	if not isinstance(candidates, list) or not candidates:
		return ''
	first = candidates[0] if isinstance(candidates[0], dict) else {}
	content = first.get('content', {})
	parts = content.get('parts', []) if isinstance(content, dict) else []
	chunks = []
	for part in parts:
		if isinstance(part, dict) and part.get('text'):
			chunks.append(str(part.get('text')))
	return '\n'.join(chunks).strip()


def _call_llm(messages: list, config: dict, timeout_sec: int):
	style = config.get('api_style', 'openai')
	if style == 'anthropic':
		return _call_anthropic(messages, config, timeout_sec)
	if style == 'gemini':
		return _call_gemini(messages, config, timeout_sec)
	return _call_openai_compatible(messages, config, timeout_sec)


def _call_openai_compatible(messages: list, config: dict, timeout_sec: int):
	headers = {
		'Authorization': f"Bearer {config['api_key']}",
		'Content-Type': 'application/json'
	}
	body = {
		'model': config['model'],
		'messages': messages,
		'temperature': config['temperature']
	}
	payload = _request_json(config['base_url'], headers, body, timeout_sec)
	return _extract_text_from_openai(payload)


def _call_anthropic(messages: list, config: dict, timeout_sec: int):
	headers = {
		'x-api-key': config['api_key'],
		'anthropic-version': '2023-06-01',
		'Content-Type': 'application/json'
	}
	system_messages = [m['content'] for m in messages if m.get('role') == 'system']
	chat_messages = [m for m in messages if m.get('role') != 'system']
	system_text = '\n'.join([x for x in system_messages if isinstance(x, str)])
	body = {
		'model': config['model'],
		'max_tokens': 1024,
		'system': system_text,
		'messages': chat_messages,
		'temperature': config['temperature']
	}
	payload = _request_json(config['base_url'], headers, body, timeout_sec)
	return _extract_text_from_anthropic(payload)


def _call_gemini(messages: list, config: dict, timeout_sec: int):
	url = config['base_url']
	if '{model}' in url:
		url = url.replace('{model}', config['model'])
	elif '/models/' not in url and ':generateContent' in url:
		url = f"https://generativelanguage.googleapis.com/v1beta/models/{config['model']}:generateContent"
	sep = '&' if '?' in url else '?'
	url_with_key = f'{url}{sep}key={config["api_key"]}'
	prompt_lines = []
	for m in messages:
		role = str(m.get('role', 'user'))
		content = str(m.get('content', ''))
		prompt_lines.append(f'{role}: {content}')
	full_text = '\n'.join(prompt_lines)
	body = {'contents': [{'parts': [{'text': full_text}]}]}
	headers = {'Content-Type': 'application/json'}
	payload = _request_json(url_with_key, headers, body, timeout_sec)
	return _extract_text_from_gemini(payload)


def _extract_command_array(text: str):
	if not isinstance(text, str) or '[' not in text or ']' not in text:
		return []
	start = text.find('[')
	end = text.rfind(']')
	if start < 0 or end <= start:
		return []
	try:
		maybe = json.loads(text[start:end + 1])
		if isinstance(maybe, list):
			return [x for x in maybe if isinstance(x, dict) and x.get('cmd')]
	except Exception:
		return []
	return []


def _extract_json_object(text: str):
	if not isinstance(text, str) or '{' not in text or '}' not in text:
		return {}
	start = text.find('{')
	end = text.rfind('}')
	if start < 0 or end <= start:
		return {}
	try:
		maybe = json.loads(text[start:end + 1])
		if isinstance(maybe, dict):
			return maybe
	except Exception:
		return {}
	return {}


def _call_agent_json(system_prompt: str, user_content: str, config: dict, timeout_sec: int):
	text = _call_llm([
		{'role': 'system', 'content': system_prompt},
		{'role': 'user', 'content': user_content}
	], config, timeout_sec)
	return text, _extract_json_object(text)


def _command_guard_checks(command: dict):
	cmd = str(command.get('cmd') or '')
	checks = []
	if cmd in ('exists', 'inspect', 'list_children', 'project_diagnostics', 'reload', 'save_tox', 'save_project'):
		return checks
	if cmd in ('create', 'clear', 'build_glsl_cube'):
		parent = command.get('parent')
		if isinstance(parent, str) and parent:
			checks.append({'cmd': 'exists', 'path': parent})
			checks.append({'cmd': 'inspect', 'path': parent})
	if cmd == 'par':
		path = command.get('path')
		if isinstance(path, str) and path:
			checks.append({'cmd': 'exists', 'path': path})
			checks.append({'cmd': 'inspect', 'path': path})
	if cmd == 'connect':
		dest = command.get('dest')
		if isinstance(dest, str) and dest:
			checks.append({'cmd': 'exists', 'path': dest})
			checks.append({'cmd': 'inspect', 'path': dest})
		src = command.get('src')
		if isinstance(src, list):
			for item in src:
				if isinstance(item, str) and item:
					checks.append({'cmd': 'exists', 'path': item})
	if cmd in ('delete', 'remove', 'destroy'):
		path = command.get('path')
		if isinstance(path, str) and path:
			checks.append({'cmd': 'exists', 'path': path})
			checks.append({'cmd': 'inspect', 'path': path})
	if cmd == 'hover':
		mat_path = command.get('mat')
		parent = command.get('parent')
		if isinstance(mat_path, str) and mat_path:
			checks.append({'cmd': 'exists', 'path': mat_path})
			checks.append({'cmd': 'inspect', 'path': mat_path})
		elif isinstance(parent, str) and parent:
			checks.append({'cmd': 'exists', 'path': parent})
			checks.append({'cmd': 'inspect', 'path': parent})
	return checks


def _inject_guard_commands(commands: list):
	if not isinstance(commands, list):
		return []
	guarded = []
	seen = set()
	for item in commands:
		if not isinstance(item, dict) or not item.get('cmd'):
			continue
		checks = _command_guard_checks(item)
		for check in checks:
			key = json.dumps(check, ensure_ascii=False, sort_keys=True)
			if key in seen:
				continue
			seen.add(key)
			guarded.append(check)
		guarded.append(item)
	return guarded


def _to_json_text(payload):
	try:
		return json.dumps(payload, ensure_ascii=False)
	except Exception:
		return '{}'


def _split_chunks(text: str, size: int = 20):
	if not isinstance(text, str) or not text:
		return []
	out = []
	i = 0
	n = len(text)
	while i < n:
		out.append(text[i:i + size])
		i += size
	return out


def _build_collaboration_payload(messages: list, config: dict, emit=None):
	last_user_message = ''
	for m in reversed(messages):
		if isinstance(m, dict) and m.get('role') == 'user':
			last_user_message = str(m.get('content', ''))
			break
	history_lines = []
	for m in messages[-8:]:
		if not isinstance(m, dict):
			continue
		role = str(m.get('role', 'user'))
		content = str(m.get('content', ''))
		history_lines.append(f'{role}: {content}')
	history_text = '\n'.join(history_lines)
	if callable(emit):
		emit('stage', {'stage': 'planner', 'status': 'running', 'message': 'Planner 正在拆解任务'})
	planner_input = (
		'请根据以下对话上下文与最新用户目标做任务拆分。\n'
		f'对话上下文:\n{history_text}\n'
		f'最新目标:\n{last_user_message}'
	)
	planner_raw, planner_data = _call_agent_json(PLANNER_PROMPT, planner_input, config, 60)
	if callable(emit):
		emit('stage', {
			'stage': 'planner',
			'status': 'done',
			'message': 'Planner 任务拆解完成',
			'summary': planner_data.get('summary', ''),
			'taskCount': len(planner_data.get('tasks', [])) if isinstance(planner_data.get('tasks', []), list) else 0
		})
	if callable(emit):
		emit('stage', {'stage': 'executor', 'status': 'running', 'message': 'Executor 正在生成命令'})
	executor_input = (
		'请根据用户目标和规划结果生成命令。\n'
		f'用户目标:\n{last_user_message}\n'
		f'规划结果:\n{_to_json_text(planner_data)}'
	)
	executor_raw, executor_data = _call_agent_json(EXECUTOR_PROMPT, executor_input, config, 60)
	base_commands = executor_data.get('commands', [])
	if not isinstance(base_commands, list) or not base_commands:
		base_commands = _extract_command_array(executor_raw)
	commands = _inject_guard_commands(base_commands)
	if callable(emit):
		emit('stage', {
			'stage': 'executor',
			'status': 'done',
			'message': 'Executor 命令生成完成',
			'commandCount': len(commands)
		})
	if callable(emit):
		emit('stage', {'stage': 'reviewer', 'status': 'running', 'message': 'Reviewer 正在审计风险'})
	reviewer_input = (
		'请对规划与执行结果做审计。\n'
		f'规划结果:\n{_to_json_text(planner_data)}\n'
		f'执行草案:\n{_to_json_text({"reply": executor_data.get("reply", ""), "commands": commands})}'
	)
	reviewer_raw, reviewer_data = _call_agent_json(REVIEWER_PROMPT, reviewer_input, config, 60)
	executor_reply = str(executor_data.get('reply') or '').strip()
	if not executor_reply:
		executor_reply = executor_raw.strip()
	reviewer_assessment = str(reviewer_data.get('assessment') or '').strip()
	reviewer_perf = str(reviewer_data.get('performance') or 'not_implemented').strip()
	reply = '\n'.join([
		executor_reply or '已生成执行方案。',
		'',
		f'审计结论: {reviewer_assessment or "已完成风险审计"}',
		f'性能指标: {"未实现" if reviewer_perf == "not_implemented" else "已提供"}'
	]).strip()
	if callable(emit):
		emit('stage', {
			'stage': 'reviewer',
			'status': 'done',
			'message': 'Reviewer 审计完成',
			'performance': reviewer_perf
		})
	collaboration = {
		'planner': {
			'status': 'implemented',
			'summary': planner_data.get('summary', ''),
			'tasks': planner_data.get('tasks', []),
			'assumptions': planner_data.get('assumptions', []),
			'raw': planner_raw
		},
		'executor': {
			'status': 'implemented_basic',
			'reply': executor_reply,
			'checks': executor_data.get('checks', []),
			'commands': commands,
			'raw': executor_raw
		},
		'reviewer': {
			'status': 'partial',
			'assessment': reviewer_assessment,
			'risks': reviewer_data.get('risks', []),
			'suggestions': reviewer_data.get('suggestions', []),
			'performance': reviewer_perf,
			'raw': reviewer_raw
		}
	}
	if callable(emit):
		emit('stage', {'stage': 'assistant', 'status': 'streaming', 'message': 'AI 回复流式输出中'})
		for chunk in _split_chunks(reply, 18):
			emit('reply_delta', {'delta': chunk})
		emit('stage', {'stage': 'assistant', 'status': 'done', 'message': 'AI 回复输出完成'})
	return {'reply': reply, 'commands': commands, 'collaboration': collaboration}


class BridgeHandler(BaseHTTPRequestHandler):
	def do_OPTIONS(self):
		self.send_response(204)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
		self.end_headers()

	def do_GET(self):
		if self.path in ('/', '/index.html'):
			file_path = os.path.join(WEB_ROOT, 'index.html')
			return self._send_file(file_path, 'text/html; charset=utf-8')
		if self.path == '/app.js':
			file_path = os.path.join(WEB_ROOT, 'app.js')
			return self._send_file(file_path, 'text/javascript; charset=utf-8')
		if self.path == '/style.css':
			file_path = os.path.join(WEB_ROOT, 'style.css')
			return self._send_file(file_path, 'text/css; charset=utf-8')
		_json_response(self, 404, {'ok': False, 'error': 'not_found'})

	def do_POST(self):
		length = int(self.headers.get('Content-Length', '0') or '0')
		raw = self.rfile.read(length) if length > 0 else b'{}'
		try:
			data = json.loads(raw.decode('utf-8', errors='ignore'))
		except Exception:
			return _json_response(self, 400, {'ok': False, 'error': 'invalid_json'})

		if self.path == '/api/td/send':
			return self._api_td_send(data)
		if self.path == '/api/td/batch':
			return self._api_td_batch(data)
		if self.path == '/api/model/test':
			return self._api_model_test(data)
		if self.path == '/api/model/chat':
			return self._api_model_chat(data)
		if self.path == '/api/model/chat_stream':
			return self._api_model_chat_stream(data)
		_json_response(self, 404, {'ok': False, 'error': 'not_found'})

	def _api_td_send(self, data: dict):
		cmd = data.get('command')
		if not isinstance(cmd, dict):
			return _json_response(self, 400, {'ok': False, 'error': 'command_required'})
		host = str(data.get('host') or DEFAULT_TD_HOST)
		port = int(data.get('port') or DEFAULT_TD_PORT)
		timeout_sec = int(data.get('timeout') or DEFAULT_TIMEOUT)
		try:
			resp = _send_td_command(cmd, host, port, timeout_sec)
			ok = not resp.startswith('error:')
			return _json_response(self, 200, {'ok': ok, 'response': resp, 'command': cmd})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc), 'command': cmd})

	def _api_td_batch(self, data: dict):
		commands = data.get('commands', [])
		if not isinstance(commands, list):
			return _json_response(self, 400, {'ok': False, 'error': 'commands_must_be_array'})
		host = str(data.get('host') or DEFAULT_TD_HOST)
		port = int(data.get('port') or DEFAULT_TD_PORT)
		timeout_sec = int(data.get('timeout') or DEFAULT_TIMEOUT)
		results = []
		for cmd in commands:
			if not isinstance(cmd, dict):
				continue
			try:
				resp = _send_td_command(cmd, host, port, timeout_sec)
				ok = not resp.startswith('error:')
				item = {'ok': ok, 'response': resp, 'command': cmd}
				results.append(item)
				if not ok:
					break
			except Exception as exc:
				results.append({'ok': False, 'error': str(exc), 'command': cmd})
				break
		all_ok = all(item.get('ok') for item in results) if results else False
		return _json_response(self, 200, {'ok': all_ok, 'results': results})

	def _api_model_test(self, data: dict):
		config = _build_provider_config(data)
		if not config['api_key']:
			return _json_response(self, 200, {'ok': False, 'error': 'apiKey不能为空'})
		test_messages = [
			{'role': 'system', 'content': '你是连通性测试助手，只回复OK'},
			{'role': 'user', 'content': '请只回复OK'}
		]
		try:
			text = _call_llm(test_messages, config, 20)
			return _json_response(self, 200, {'ok': bool(text), 'reply': text})
		except error.HTTPError as exc:
			raw = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
			return _json_response(self, 200, {'ok': False, 'error': f'HTTP {exc.code}: {raw}'})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': _format_network_error(exc, config['base_url'])})

	def _api_model_chat(self, data: dict):
		config = _build_provider_config(data.get('config', {}))
		messages = data.get('messages', [])
		if not isinstance(messages, list) or not messages:
			return _json_response(self, 400, {'ok': False, 'error': 'messages_required'})
		if not config['api_key']:
			return _json_response(self, 200, {'ok': False, 'error': 'apiKey不能为空'})
		try:
			payload = _build_collaboration_payload(messages, config, None)
			return _json_response(self, 200, {'ok': True, 'reply': payload['reply'], 'commands': payload['commands'], 'collaboration': payload['collaboration']})
		except error.HTTPError as exc:
			raw = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
			return _json_response(self, 200, {'ok': False, 'error': f'HTTP {exc.code}: {raw}'})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': _format_network_error(exc, config['base_url'])})

	def _api_model_chat_stream(self, data: dict):
		config = _build_provider_config(data.get('config', {}))
		messages = data.get('messages', [])
		if not isinstance(messages, list) or not messages:
			return _json_response(self, 400, {'ok': False, 'error': 'messages_required'})
		if not config['api_key']:
			return _json_response(self, 200, {'ok': False, 'error': 'apiKey不能为空'})
		self.send_response(200)
		self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
		self.send_header('Cache-Control', 'no-cache')
		self.send_header('Connection', 'keep-alive')
		self.send_header('Access-Control-Allow-Origin', '*')
		self.end_headers()

		def emit(event_name: str, payload: dict):
			packet = {'event': event_name, 'data': payload}
			line = json.dumps(packet, ensure_ascii=False) + '\n'
			self.wfile.write(line.encode('utf-8'))
			self.wfile.flush()

		try:
			emit('start', {'message': '已开始处理请求'})
			payload = _build_collaboration_payload(messages, config, emit)
			emit('done', payload)
		except error.HTTPError as exc:
			raw = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
			emit('error', {'message': f'HTTP {exc.code}: {raw}'})
		except Exception as exc:
			emit('error', {'message': _format_network_error(exc, config['base_url'])})

	def _send_file(self, file_path: str, content_type: str):
		if not os.path.exists(file_path):
			return _json_response(self, 404, {'ok': False, 'error': 'not_found'})
		with open(file_path, 'rb') as f:
			body = f.read()
		self.send_response(200)
		self.send_header('Content-Type', content_type)
		self.send_header('Content-Length', str(len(body)))
		self.end_headers()
		self.wfile.write(body)


def run(host: str = '127.0.0.1', port: int = 8765):
	server = ThreadingHTTPServer((host, port), BridgeHandler)
	print(f'Web bridge running at http://{host}:{port}')
	server.serve_forever()


if __name__ == '__main__':
	run()
