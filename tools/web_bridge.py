import json
import os
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib import request, error


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
WEB_ROOT = os.path.join(PROJECT_ROOT, 'web')
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
	'write_framework_json', 'reload', 'replicate_framework', 'save_project',
	'exists', 'list_children', 'inspect', 'project_diagnostics'
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
	'任何涉及节点创建、删除、连线、参数修改、自定义参数、DAT内容修改的结构编辑，'
	'都必须通过 OP_Framework 标准JSON文件完成，并使用 reload -> replicate_framework -> save_project 的链路。'
	'必须先输出 write_framework_json 命令，把完整框架树写入 OP_Framework copy.json。'
	'write_framework_json 的格式为 {"cmd":"write_framework_json","file":"OP_Framework copy.json","forest":[...]}。'
	'forest 必须是 OP_Framework 标准树：每个节点为 {"nodeName":{"relPath":"...","type":"...","pos":{"x":0,"y":0},"parameters":{"Page":{"par":{"val":"...","mode":"ParMode.CONSTANT"}}},"connections":{"inputs":[{"port":0,"links":["srcNode"]}]}}}。'
	'如果用户要求连接，必须把连接写进目标节点的 connections.inputs。'
	'如果用户要求改参数，必须把参数写进 parameters 页面里，不能留空。'
	'如果要创建多个节点，不能把它们都放在相同坐标，可做简单横向布局。'
	'随后再输出 replicate_framework 所需命令。'
	'禁止输出 create/par/connect/clear/delete/hover/build_glsl_cube 等旧式编辑命令。'
)

REPAIR_EXECUTOR_PROMPT = (
	'你是修复执行者（Executor Repair）。'
	'你会收到用户目标、上一版命令和校验失败原因。'
	'你必须输出修复后的最终 JSON，不要解释，不要Markdown。'
	'只允许使用以下cmd: ' + ', '.join(ALLOWED_CMDS) + '。'
	'JSON格式: {"reply":"", "commands":[{"cmd":"..."}], "checks":[""]}。'
	'必须修复所有校验失败项，尤其是缺失连接、缺失参数设置、错误字段名、节点重叠。'
	'必须输出可直接执行的 write_framework_json -> reload -> replicate_framework 链路。'
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


def _resolve_project_file(file_path: str):
	if not isinstance(file_path, str) or not file_path.strip():
		file_path = 'OP_Framework copy.json'
	if os.path.isabs(file_path):
		return file_path
	return os.path.join(PROJECT_ROOT, file_path)


def _execute_local_command(cmd_obj: dict):
	if not isinstance(cmd_obj, dict):
		raise ValueError('invalid_command')
	cmd = str(cmd_obj.get('cmd') or '')
	if cmd != 'write_framework_json':
		return None
	target_path = _resolve_project_file(str(cmd_obj.get('file') or 'OP_Framework copy.json'))
	forest = cmd_obj.get('forest', None)
	content = cmd_obj.get('content', None)
	if forest is None and not isinstance(content, str):
		raise ValueError('write_framework_json requires forest or content')
	if forest is not None:
		forest = _normalize_framework_forest(forest)
		body = json.dumps(forest, indent='\t', ensure_ascii=False)
	else:
		body = str(content)
	parent_dir = os.path.dirname(target_path)
	if parent_dir and not os.path.exists(parent_dir):
		os.makedirs(parent_dir, exist_ok=True)
	with open(target_path, 'w', encoding='utf-8') as f:
		f.write(body)
	node_count = len(forest) if isinstance(forest, list) else 0
	return f'write_framework_json:file={target_path};nodes={node_count}'


def _normalize_op_type(op_type: str, node_name: str = ''):
	raw = str(op_type or '').strip()
	if not raw:
		raw = 'baseCOMP'
	low = raw.lower()
	compact_name = ''.join([ch for ch in str(node_name or '').lower() if ch.isalnum()])
	aliases = {
		'audiofilein': 'audiofileinCHOP',
		'audiofileinchop': 'audiofileinCHOP',
		'audiodeviceout': 'audiodeviceoutCHOP',
		'audiodeviceoutchop': 'audiodeviceoutCHOP',
		'audiodevicein': 'audiodeviceinCHOP',
		'audiodeviceinchop': 'audiodeviceinCHOP',
		'container': 'containerCOMP',
		'base': 'baseCOMP',
		'null': 'nullCHOP'
	}
	name_aliases = {
		'audiofilein': 'audiofileinCHOP',
		'audiodeviceout': 'audiodeviceoutCHOP',
		'audiodevicein': 'audiodeviceinCHOP',
		'moviefilein': 'moviefileinTOP',
		'audiospectrum': 'audiospectrumCHOP',
		'nulltop': 'nullTOP',
		'nullchop': 'nullCHOP',
		'basecomp': 'baseCOMP',
		'containercomp': 'containerCOMP'
	}
	if low in aliases:
		return aliases[low]
	if low in ('top', 'chop', 'sop', 'comp', 'dat', 'mat'):
		for key, concrete in name_aliases.items():
			if key in compact_name:
				return concrete
	return raw


def _normalize_rel_path(node_name: str, raw_rel_path: str = '', parent_path: str = '/project1'):
	name = str(node_name or '').strip() or 'node1'
	path = str(raw_rel_path or '').strip()
	if path.startswith('/'):
		return path
	if path in ('', '.'):
		return f'{parent_path.rstrip("/")}/{name}'
	if path.startswith('./'):
		path = path[2:]
	if '/' not in path:
		return f'{parent_path.rstrip("/")}/{path}'
	return f'/{path.lstrip("/")}'


def _normalize_param_entry(raw_value):
	if isinstance(raw_value, dict):
		out = dict(raw_value)
		if 'mode' not in out:
			out['mode'] = 'ParMode.CONSTANT'
		if out.get('mode') != 'ParMode.BIND' and 'val' not in out:
			out['val'] = ''
		return out
	return {
		'val': str(raw_value),
		'mode': 'ParMode.CONSTANT'
	}


def _normalize_parameter_groups(raw_params):
	if not isinstance(raw_params, dict) or not raw_params:
		return {}
	is_paged = True
	for page_val in raw_params.values():
		if not isinstance(page_val, dict):
			is_paged = False
			break
		for par_val in page_val.values():
			if not isinstance(par_val, dict):
				is_paged = False
				break
		if not is_paged:
			break
	if is_paged:
		out = {}
		for page_name, page_pars in raw_params.items():
			page_out = {}
			for par_name, par_val in page_pars.items():
				page_out[str(par_name)] = _normalize_param_entry(par_val)
			out[str(page_name)] = page_out
		return out
	return {
		'Auto': {str(par_name): _normalize_param_entry(par_val) for par_name, par_val in raw_params.items()}
	}


def _normalize_position(spec: dict):
	pos = spec.get('pos')
	if isinstance(pos, dict):
		return {
			'x': int(float(pos.get('x', 0) or 0)),
			'y': int(float(pos.get('y', 0) or 0))
		}
	node_pos = spec.get('nodePosition')
	if isinstance(node_pos, (list, tuple)) and len(node_pos) >= 2:
		return {
			'x': int(float(node_pos[0] or 0)),
			'y': int(float(node_pos[1] or 0))
		}
	return {'x': 0, 'y': 0}


def _is_canonical_framework_forest(raw_forest):
	if not isinstance(raw_forest, list):
		return False
	for item in raw_forest:
		if not isinstance(item, dict) or len(item) != 1:
			return False
		node_info = list(item.values())[0]
		if not isinstance(node_info, dict):
			return False
		if 'relPath' not in node_info or 'type' not in node_info:
			return False
	return True


def _parse_port_index(raw_port):
	if isinstance(raw_port, int):
		return max(0, raw_port)
	text = str(raw_port or '').strip()
	digits = ''.join([ch for ch in text if ch.isdigit()])
	if not digits:
		return 0
	val = int(digits)
	return max(0, val - 1 if val > 0 else 0)


def _build_canonical_forest_from_legacy(raw_forest):
	nodes = {}
	connections = []
	for item in raw_forest:
		if not isinstance(item, dict):
			continue
		item_type = str(item.get('type', '') or '').strip().lower()
		if item_type == 'connection' or item.get('source') or item.get('destination') or item.get('dest'):
			connections.append(item)
			continue
		node_name = str(item.get('name') or item.get('node') or '').strip()
		if not node_name:
			continue
		parent_path = str(item.get('parent') or '/project1').strip() or '/project1'
		rel_path = _normalize_rel_path(node_name, str(item.get('relPath') or ''), parent_path)
		nodes[rel_path] = {
			'name': node_name,
			'relPath': rel_path,
			'type': _normalize_op_type(str(item.get('type') or item.get('opType') or 'baseCOMP'), node_name),
			'pos': _normalize_position(item),
			'parameters': _normalize_parameter_groups(item.get('parameters', {})),
			'customParameters': item.get('customParameters', {}) if isinstance(item.get('customParameters', {}), dict) else {},
			'drawState': item.get('drawState', {}) if isinstance(item.get('drawState', {}), dict) else {},
			'children': []
		}

	for link in connections:
		src_name = str(link.get('source') or link.get('src') or '').strip()
		dest_name = str(link.get('destination') or link.get('dest') or '').strip()
		if not src_name or not dest_name:
			continue
		dest_node = None
		for path_key, node_info in nodes.items():
			if node_info.get('name') == dest_name or path_key.endswith('/' + dest_name):
				dest_node = node_info
				break
		if dest_node is None:
			continue
		port = _parse_port_index(link.get('destinationInlet', link.get('port', 0)))
		conns = dest_node.setdefault('connections', {})
		inputs = conns.setdefault('inputs', [])
		entry = None
		for item in inputs:
			if isinstance(item, dict) and int(item.get('port', 0)) == port:
				entry = item
				break
		if entry is None:
			entry = {'port': port, 'links': []}
			inputs.append(entry)
		entry['links'].append(src_name)

	def attach_children(node_path: str):
		node_info = nodes[node_path]
		children = []
		prefix = node_path + '/'
		for child_path in sorted(nodes.keys()):
			if child_path == node_path or not child_path.startswith(prefix):
				continue
			parent_path = child_path.rsplit('/', 1)[0]
			if parent_path != node_path:
				continue
			attach_children(child_path)
			child_info = dict(nodes[child_path])
			child_name = child_info.pop('name')
			children.append({child_name: child_info})
		node_info['children'] = children

	top_level = []
	for path_key in sorted(nodes.keys()):
		parent_path = path_key.rsplit('/', 1)[0]
		if parent_path != '/project1':
			continue
		attach_children(path_key)
		node_info = dict(nodes[path_key])
		node_name = node_info.pop('name')
		top_level.append({node_name: node_info})
	return top_level


def _normalize_framework_forest(raw_forest):
	if _is_canonical_framework_forest(raw_forest):
		return _auto_layout_canonical_forest(_normalize_canonical_forest(raw_forest))
	if not isinstance(raw_forest, list):
		return []
	return _auto_layout_canonical_forest(_build_canonical_forest_from_legacy(raw_forest))


def _normalize_canonical_forest(forest, parent_path: str = '/project1'):
	if not isinstance(forest, list):
		return []
	out = []
	for item in forest:
		if not isinstance(item, dict) or len(item) != 1:
			continue
		node_name = list(item.keys())[0]
		node_info = item.get(node_name, {})
		if not isinstance(node_info, dict):
			continue
		info = dict(node_info)
		info['relPath'] = _normalize_rel_path(node_name, str(info.get('relPath') or ''), parent_path)
		info['type'] = _normalize_op_type(str(info.get('type') or 'baseCOMP'), node_name)
		info['pos'] = _normalize_position(info)
		info['parameters'] = _normalize_parameter_groups(info.get('parameters', {}))
		if not isinstance(info.get('customParameters', {}), dict):
			info['customParameters'] = {}
		if not isinstance(info.get('drawState', {}), dict):
			info['drawState'] = {}
		children_parent = info['relPath']
		info['children'] = _normalize_canonical_forest(info.get('children', []), children_parent)
		out.append({node_name: info})
	return out


def _walk_framework_nodes(forest):
	if not isinstance(forest, list):
		return
	for item in forest:
		if not isinstance(item, dict) or len(item) != 1:
			continue
		node_name = list(item.keys())[0]
		node_info = item.get(node_name, {})
		if not isinstance(node_info, dict):
			continue
		yield node_name, node_info
		children = node_info.get('children', [])
		if isinstance(children, list):
			for child in _walk_framework_nodes(children):
				yield child


def _auto_layout_canonical_forest(forest):
	if not isinstance(forest, list):
		return []
	out = json.loads(json.dumps(forest, ensure_ascii=False))

	def layout_siblings(items):
		if not isinstance(items, list):
			return
		seen = {}
		for item in items:
			if not isinstance(item, dict) or len(item) != 1:
				continue
			node_info = list(item.values())[0]
			if not isinstance(node_info, dict):
				continue
			pos = node_info.get('pos')
			if not isinstance(pos, dict):
				pos = {'x': 0, 'y': 0}
				node_info['pos'] = pos
			x = int(float(pos.get('x', 0) or 0))
			y = int(float(pos.get('y', 0) or 0))
			key = (x, y)
			offset = seen.get(key, 0)
			if offset > 0:
				pos['x'] = x + 180 * offset
				pos['y'] = y
			seen[key] = offset + 1
			children = node_info.get('children', [])
			if isinstance(children, list):
				layout_siblings(children)

	layout_siblings(out)
	return out


def _collect_framework_parameter_names(forest):
	names = set()
	for _, node_info in _walk_framework_nodes(forest):
		for group_name in ('parameters', 'customParameters'):
			group = node_info.get(group_name, {})
			if not isinstance(group, dict):
				continue
			for _, page_pars in group.items():
				if not isinstance(page_pars, dict):
					continue
				for par_name in page_pars.keys():
					names.add(str(par_name).strip().lower())
	return names


def _framework_has_connections(forest):
	for _, node_info in _walk_framework_nodes(forest):
		connections = node_info.get('connections', {})
		if not isinstance(connections, dict):
			continue
		inputs = connections.get('inputs', [])
		if isinstance(inputs, list) and inputs:
			for entry in inputs:
				if isinstance(entry, dict) and isinstance(entry.get('links'), list) and entry.get('links'):
					return True
	return False


def _count_framework_nodes(forest):
	count = 0
	for _ in _walk_framework_nodes(forest):
		count += 1
	return count


def _framework_has_distinct_positions(forest):
	pos_set = set()
	count = 0
	for _, node_info in _walk_framework_nodes(forest):
		count += 1
		pos = node_info.get('pos', {})
		if not isinstance(pos, dict):
			continue
		x = int(float(pos.get('x', 0) or 0))
		y = int(float(pos.get('y', 0) or 0))
		pos_set.add((x, y))
	if count <= 1:
		return True
	return len(pos_set) > 1


def _framework_has_family_placeholder_types(forest):
	for _, node_info in _walk_framework_nodes(forest):
		op_type = str(node_info.get('type') or '').strip().lower()
		if op_type in ('top', 'chop', 'sop', 'comp', 'dat', 'mat'):
			return True
	return False


def _framework_has_relative_paths(forest):
	for _, node_info in _walk_framework_nodes(forest):
		rel_path = str(node_info.get('relPath') or '').strip()
		if not rel_path.startswith('/'):
			return True
	return False


def _framework_has_placeholder_parameter_names(forest):
	for _, node_info in _walk_framework_nodes(forest):
		group = node_info.get('parameters', {})
		if not isinstance(group, dict):
			continue
		for page_name, page_pars in group.items():
			if str(page_name).strip().lower() in ('page', 'defaultpage'):
				return True
			if not isinstance(page_pars, dict):
				continue
			for par_name in page_pars.keys():
				if str(par_name).strip().lower() in ('par', 'param', 'parameter'):
					return True
	return False


def _extract_write_framework_forest(commands):
	if not isinstance(commands, list):
		return None
	for item in commands:
		if not isinstance(item, dict):
			continue
		if str(item.get('cmd') or '') == 'write_framework_json':
			forest = item.get('forest')
			if isinstance(forest, list):
				return forest
	return None


def _validate_framework_commands(user_goal: str, commands: list):
	issues = []
	if not isinstance(commands, list) or not commands:
		return ['未生成任何可执行命令']
	cmd_names = [str(item.get('cmd') or '') for item in commands if isinstance(item, dict)]
	if 'write_framework_json' not in cmd_names:
		issues.append('缺少 write_framework_json 命令')
	if 'replicate_framework' not in cmd_names:
		issues.append('缺少 replicate_framework 命令')
	forest = _extract_write_framework_forest(commands)
	if not isinstance(forest, list) or not forest:
		issues.append('write_framework_json 未包含有效 forest')
		return issues
	goal = str(user_goal or '').lower()
	goal_cn = str(user_goal or '')
	if _framework_has_family_placeholder_types(forest):
		issues.append('forest 中仍存在 TOP/CHOP/COMP 等占位类型，必须改成具体 TD OP 类型')
	if _framework_has_relative_paths(forest):
		issues.append('forest 中 relPath 不是绝对路径，必须写成 /project1/... 形式')
	if _framework_has_placeholder_parameter_names(forest):
		issues.append('forest 中使用了 Page/par 这类占位参数结构，必须改成真实页面名和参数名')
	if ('连接' in goal_cn or '连线' in goal_cn or 'connect' in goal) and not _framework_has_connections(forest):
		issues.append('用户要求连接，但 forest 中没有 connections.inputs')
	param_names = _collect_framework_parameter_names(forest)
	if ('单声道' in goal_cn or 'mono' in goal or '单通道' in goal_cn) and not ({'mono', 'channels', 'chanmode', 'channelmode'} & param_names):
		issues.append('用户要求单声道，但 forest 中没有 mono/channels 等相关参数设置')
	if _count_framework_nodes(forest) > 1 and not _framework_has_distinct_positions(forest):
		issues.append('多个节点位置完全重叠，需要给出不同坐标')
	return issues


def _normalize_command(item: dict):
	if not isinstance(item, dict):
		return None
	cmd = str(item.get('cmd') or '').strip()
	if not cmd:
		return None
	if cmd == 'write_framework_json':
		return {
			'cmd': 'write_framework_json',
			'file': str(item.get('file') or item.get('source') or 'OP_Framework copy.json'),
			'forest': _normalize_framework_forest(item.get('forest', []))
		}
	if cmd == 'reload':
		return {'cmd': 'reload'}
	if cmd == 'replicate_framework':
		return {
			'cmd': 'replicate_framework',
			'file': str(item.get('file') or item.get('source') or 'OP_Framework copy.json'),
			'clear_parent': bool(item.get('clear_parent', True))
		}
	if cmd == 'save_project':
		out = {'cmd': 'save_project'}
		if item.get('file'):
			out['file'] = str(item.get('file'))
		return out
	if cmd == 'exists':
		return {'cmd': 'exists', 'path': str(item.get('path') or '/project1')}
	if cmd == 'inspect':
		return {'cmd': 'inspect', 'path': str(item.get('path') or '/project1')}
	if cmd == 'list_children':
		return {'cmd': 'list_children', 'parent': str(item.get('parent') or '/project1')}
	if cmd == 'project_diagnostics':
		return {
			'cmd': 'project_diagnostics',
			'root': str(item.get('root') or '/project1'),
			'recursive': bool(item.get('recursive', True)),
			'include_clean': bool(item.get('include_clean', False)),
			'limit': int(item.get('limit', 200))
		}
	return item


def _normalize_commands(commands: list):
	if not isinstance(commands, list):
		return []
	out = []
	for item in commands:
		norm = _normalize_command(item)
		if isinstance(norm, dict) and norm.get('cmd'):
			out.append(norm)
	return out


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
	if cmd in ('exists', 'inspect', 'list_children', 'project_diagnostics', 'reload', 'save_project'):
		return checks
	if cmd == 'write_framework_json':
		return checks
	if cmd == 'replicate_framework':
		parent = '/project1'
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
	base_commands = _normalize_commands(base_commands)
	validation_issues = _validate_framework_commands(last_user_message, base_commands)
	if validation_issues:
		repair_input = (
			'请修复上一版命令，使其满足用户目标和协议要求。\n'
			f'用户目标:\n{last_user_message}\n'
			f'上一版命令:\n{_to_json_text(base_commands)}\n'
			f'必须修复的问题:\n{_to_json_text(validation_issues)}'
		)
		repair_raw, repair_data = _call_agent_json(REPAIR_EXECUTOR_PROMPT, repair_input, config, 60)
		repaired_commands = repair_data.get('commands', [])
		if not isinstance(repaired_commands, list) or not repaired_commands:
			repaired_commands = _extract_command_array(repair_raw)
		repaired_commands = _normalize_commands(repaired_commands)
		repaired_issues = _validate_framework_commands(last_user_message, repaired_commands)
		if repaired_commands and not repaired_issues:
			base_commands = repaired_commands
			executor_raw = repair_raw
			executor_data = repair_data if isinstance(repair_data, dict) else executor_data
			if not str(executor_data.get('reply') or '').strip():
				executor_data['reply'] = '已自动修复执行命令，使其满足框架协议与用户目标。'
	commands = _inject_guard_commands(base_commands)
	if callable(emit):
		emit('stage', {
			'stage': 'executor',
			'status': 'done',
			'message': 'Executor 命令生成完成',
			'commandCount': len(commands),
			'commands': commands
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
			resp = _execute_local_command(cmd)
			if resp is None:
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
				resp = _execute_local_command(cmd)
				if resp is None:
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
