import json
import importlib.util
import os
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from urllib import request, error


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
WORKSPACE_ROOT = PROJECT_ROOT
WEB_ROOT = os.path.join(PROJECT_ROOT, 'web')
AGENTS_ROOT = os.path.join(PROJECT_ROOT, 'agents')
AGENTS_SHARED_ROOT = os.path.join(AGENTS_ROOT, 'shared')
AGENT_DIRS = {
	'agent-0-orchestrator': os.path.join(AGENTS_ROOT, 'orchestrator'),
	'agent-1-state-reader': os.path.join(AGENTS_ROOT, 'state_reader'),
	'agent-2-kb-consultant': os.path.join(AGENTS_ROOT, 'kb_consultant'),
	'agent-3-framework-editor': os.path.join(AGENTS_ROOT, 'framework_editor'),
	'agent-4-verifier': os.path.join(AGENTS_ROOT, 'verifier')
}
AGENT_RUNTIME_FILES = {
	'agent-0-orchestrator': os.path.join(AGENTS_ROOT, 'orchestrator', 'runtime.py'),
	'agent-1-state-reader': os.path.join(AGENTS_ROOT, 'state_reader', 'runtime.py'),
	'agent-2-kb-consultant': os.path.join(AGENTS_ROOT, 'kb_consultant', 'runtime.py'),
	'agent-3-framework-editor': os.path.join(AGENTS_ROOT, 'framework_editor', 'runtime.py'),
	'agent-4-verifier': os.path.join(AGENTS_ROOT, 'verifier', 'runtime.py')
}
ROUTING_CONFIG_FILE = os.path.join(AGENTS_SHARED_ROOT, 'routing.json')
RUNTIME_ROOT = os.path.join(PROJECT_ROOT, 'runtime')
RUNTIME_BRIEFS_ROOT = os.path.join(RUNTIME_ROOT, 'briefs')
RUNTIME_LOGS_ROOT = os.path.join(RUNTIME_ROOT, 'logs')
RUNTIME_RETRIES_ROOT = os.path.join(RUNTIME_ROOT, 'retries')
DEFAULT_TD_HOST = '127.0.0.1'
DEFAULT_TD_PORT = 9988
DEFAULT_TIMEOUT = 8
DEFAULT_FRAMEWORK_FILE = 'OP_Framework.json'
DEFAULT_INFORMATION_FILE = 'OP_Information.json'
FAMILY_COMPATIBILITY_FILE = os.path.join(
	PROJECT_ROOT,
	'skills',
	'touchdesigner-kb-consultant',
	'references',
	'touchdesigner_kb',
	'family_compatibility.jsonl'
)


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
	'refresh_project_state'
]

import threading

_thread_local = threading.local()

def _emit_stage(stage: str, status: str, message: str, summary: str = '', metrics: list = None):
	emit_fn = getattr(_thread_local, 'emit', None)
	if callable(emit_fn):
		emit_fn('stage', {
			'stage': stage,
			'status': status,
			'message': message,
			'summary': summary,
			'metrics': metrics or []
		})

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
		file_path = DEFAULT_FRAMEWORK_FILE
	if os.path.isabs(file_path):
		return file_path
	return os.path.join(WORKSPACE_ROOT, file_path)


def _ensure_runtime_dir(path: str):
	os.makedirs(path, exist_ok=True)
	return path


def _safe_task_id(task_id: str):
	text = str(task_id or '').strip() or 'unknown-task'
	safe_chars = []
	for ch in text:
		if ch.isalnum() or ch in ('-', '_'):
			safe_chars.append(ch)
		else:
			safe_chars.append('_')
	return ''.join(safe_chars)


def _runtime_timestamp():
	return datetime.now().strftime('%Y%m%d-%H%M%S')


def _write_json_file(file_path: str, payload):
	parent = os.path.dirname(file_path)
	if parent:
		_ensure_runtime_dir(parent)
	with open(file_path, 'w', encoding='utf-8') as f:
		json.dump(payload, f, ensure_ascii=False, indent='\t')
	return file_path


def _read_json_file(file_path: str):
	with open(file_path, 'r', encoding='utf-8') as f:
		return json.load(f)


def _latest_json_file(path: str):
	if not os.path.isdir(path):
		return ''
	candidates = []
	for name in os.listdir(path):
		if not name.endswith('.json'):
			continue
		full_path = os.path.join(path, name)
		if os.path.isfile(full_path):
			candidates.append(full_path)
	if not candidates:
		return ''
	candidates.sort(key=lambda item: os.path.getmtime(item), reverse=True)
	return candidates[0]


def _persist_multiagent_route_plan(plan: dict):
	task_id = _safe_task_id(plan.get('task_brief', {}).get('task_id', 'route'))
	task_dir = _ensure_runtime_dir(os.path.join(RUNTIME_LOGS_ROOT, task_id))
	payload = {
		'type': 'route_plan',
		'created_at': _runtime_timestamp(),
		'plan': plan
	}
	latest_path = _write_json_file(os.path.join(task_dir, 'route.latest.json'), payload)
	versioned_path = _write_json_file(os.path.join(task_dir, f'route.{payload["created_at"]}.json'), payload)
	return {
		'latest': latest_path,
		'versioned': versioned_path
	}


def _persist_multiagent_runtime(runtime: dict):
	plan = runtime.get('plan', {})
	outputs = runtime.get('outputs', {})
	messages = runtime.get('messages', [])
	task_brief = outputs.get('task_brief', {})
	task_id = _safe_task_id(task_brief.get('task_id', 'runtime'))
	timestamp = _runtime_timestamp()
	brief_dir = _ensure_runtime_dir(os.path.join(RUNTIME_BRIEFS_ROOT, task_id))
	log_dir = _ensure_runtime_dir(os.path.join(RUNTIME_LOGS_ROOT, task_id))
	retry_dir = _ensure_runtime_dir(os.path.join(RUNTIME_RETRIES_ROOT, task_id))
	briefs_payload = {
		'task_id': task_brief.get('task_id', ''),
		'created_at': timestamp,
		'outputs': outputs
	}
	log_payload = {
		'task_id': task_brief.get('task_id', ''),
		'created_at': timestamp,
		'plan': plan,
		'messages': messages,
		'outputs': outputs
	}
	paths = {
		'brief_latest': _write_json_file(os.path.join(brief_dir, 'latest.json'), briefs_payload),
		'brief_versioned': _write_json_file(os.path.join(brief_dir, f'{timestamp}.json'), briefs_payload),
		'log_latest': _write_json_file(os.path.join(log_dir, 'latest.json'), log_payload),
		'log_versioned': _write_json_file(os.path.join(log_dir, f'{timestamp}.json'), log_payload)
	}
	retry_request = outputs.get('retry_request')
	if isinstance(retry_request, dict):
		retry_payload = {
			'task_id': task_brief.get('task_id', ''),
			'created_at': timestamp,
			'retry_request': retry_request
		}
		paths['retry_latest'] = _write_json_file(os.path.join(retry_dir, 'latest.json'), retry_payload)
		paths['retry_versioned'] = _write_json_file(os.path.join(retry_dir, f'{timestamp}.json'), retry_payload)
	return paths


def _load_multiagent_runtime_bundle(task_id: str = ''):
	safe_task_id = _safe_task_id(task_id) if str(task_id or '').strip() else ''
	if safe_task_id:
		log_path = os.path.join(RUNTIME_LOGS_ROOT, safe_task_id, 'latest.json')
		brief_path = os.path.join(RUNTIME_BRIEFS_ROOT, safe_task_id, 'latest.json')
		retry_path = os.path.join(RUNTIME_RETRIES_ROOT, safe_task_id, 'latest.json')
	else:
		log_path = _latest_json_file(RUNTIME_LOGS_ROOT)
		brief_path = ''
		retry_path = ''
		if log_path:
			parent_dir = os.path.basename(os.path.dirname(log_path))
			brief_path = os.path.join(RUNTIME_BRIEFS_ROOT, parent_dir, 'latest.json')
			retry_path = os.path.join(RUNTIME_RETRIES_ROOT, parent_dir, 'latest.json')
	bundle = {
		'log': None,
		'briefs': None,
		'retry': None
	}
	if log_path and os.path.exists(log_path):
		bundle['log'] = _read_json_file(log_path)
	if brief_path and os.path.exists(brief_path):
		bundle['briefs'] = _read_json_file(brief_path)
	if retry_path and os.path.exists(retry_path):
		bundle['retry'] = _read_json_file(retry_path)
	return bundle


def _load_project_scan_file(file_path: str):
	target_path = _resolve_project_file(file_path)
	if not os.path.exists(target_path):
		return [], target_path
	try:
		with open(target_path, 'r', encoding='utf-8-sig') as f:
			data = json.load(f)
	except Exception:
		return [], target_path
	if isinstance(data, list):
		return data, target_path
	return [], target_path


def _collect_forest_nodes(forest):
	nodes = []

	def walk(items):
		if not isinstance(items, list):
			return
		for item in items:
			if not isinstance(item, dict) or len(item) != 1:
				continue
			node_name = next(iter(item.keys()))
			node_info = item.get(node_name)
			if not isinstance(node_info, dict):
				continue
			path = str(node_info.get('relPath') or f'/project1/{node_name}')
			node_type = str(node_info.get('type') or 'Unknown')
			nodes.append({
				'name': str(node_name),
				'path': path,
				'type': node_type
			})
			walk(node_info.get('children', []))

	walk(forest)
	return nodes


def _collect_top_level_nodes(forest):
	out = []
	if not isinstance(forest, list):
		return out
	for item in forest:
		if not isinstance(item, dict) or len(item) != 1:
			continue
		node_name = next(iter(item.keys()))
		node_info = item.get(node_name)
		if not isinstance(node_info, dict):
			continue
		out.append({
			'name': str(node_name),
			'path': str(node_info.get('relPath') or f'/project1/{node_name}'),
			'type': str(node_info.get('type') or 'Unknown')
		})
	return out


def _build_project_summary():
	information_forest, information_path = _load_project_scan_file(DEFAULT_INFORMATION_FILE)
	framework_forest, framework_path = _load_project_scan_file(DEFAULT_FRAMEWORK_FILE)
	information_nodes = _collect_forest_nodes(information_forest)
	framework_nodes = _collect_forest_nodes(framework_forest)
	return {
		'information_file': information_path,
		'framework_file': framework_path,
		'information_node_count': len(information_nodes),
		'framework_node_count': len(framework_nodes),
		'top_level_nodes': _collect_top_level_nodes(information_forest)[:20],
		'non_default_nodes': framework_nodes[:40],
		'node_paths_sample': [item['path'] for item in information_nodes[:80]]
	}


def _load_json_object(file_path: str):
	with open(file_path, 'r', encoding='utf-8') as f:
		return json.load(f)


def _load_routing_config():
	if not os.path.exists(ROUTING_CONFIG_FILE):
		return {
			'default_priority': 'high',
			'default_scope': '/project1',
			'agent_order': [],
			'task_defaults': {},
			'kb_keywords': []
		}
	return _load_json_object(ROUTING_CONFIG_FILE)


def _load_agent_contracts():
	contracts = {}
	if not os.path.isdir(AGENTS_ROOT):
		return contracts
	for name in os.listdir(AGENTS_ROOT):
		agent_dir = os.path.join(AGENTS_ROOT, name)
		if not os.path.isdir(agent_dir):
			continue
		contract_path = os.path.join(agent_dir, 'agent.contract.json')
		if not os.path.exists(contract_path):
			continue
		try:
			contract = _load_json_object(contract_path)
		except Exception:
			continue
		agent_id = str(contract.get('agent_id') or '').strip()
		if agent_id:
			contracts[agent_id] = contract
	return contracts


def _empty_agent_assets():
	return {
		'agent_dir': '',
		'prompt_file': '',
		'prompt_available': False,
		'prompt_preview': '',
		'schema_file': '',
		'schema_available': False,
		'runtime_file': '',
		'runtime_available': False,
		'runtime_exports': {},
		'input_refs': [],
		'output_refs': []
	}


def _load_agent_assets(agent_id: str):
	agent_dir = AGENT_DIRS.get(str(agent_id or '').strip(), '')
	if not agent_dir:
		return _empty_agent_assets()
	prompt_path = os.path.join(agent_dir, 'prompts', 'system.txt')
	schema_path = os.path.join(agent_dir, 'schemas', 'manifest.json')
	runtime_path = AGENT_RUNTIME_FILES.get(str(agent_id or '').strip(), '')
	prompt_text = ''
	if os.path.exists(prompt_path):
		try:
			with open(prompt_path, 'r', encoding='utf-8') as f:
				prompt_text = str(f.read())
		except Exception:
			prompt_text = ''
	schema_manifest = {}
	if os.path.exists(schema_path):
		try:
			schema_manifest = _load_json_object(schema_path)
		except Exception:
			schema_manifest = {}
	return {
		'agent_dir': agent_dir,
		'prompt_file': prompt_path if os.path.exists(prompt_path) else '',
		'prompt_available': bool(prompt_text.strip()),
		'prompt_preview': prompt_text.strip()[:120],
		'schema_file': schema_path if os.path.exists(schema_path) else '',
		'schema_available': isinstance(schema_manifest, dict) and bool(schema_manifest),
		'runtime_file': runtime_path if runtime_path and os.path.exists(runtime_path) else '',
		'runtime_available': bool(runtime_path and os.path.exists(runtime_path)),
		'runtime_exports': schema_manifest.get('runtime_exports', {}) if isinstance(schema_manifest, dict) else {},
		'input_refs': schema_manifest.get('input_refs', []) if isinstance(schema_manifest, dict) else [],
		'output_refs': schema_manifest.get('output_refs', []) if isinstance(schema_manifest, dict) else []
	}


def _build_agent_descriptor(agent_id: str, contract: dict, assets: dict):
	if not isinstance(contract, dict):
		contract = {}
	if not isinstance(assets, dict):
		assets = _empty_agent_assets()
	produces = [item.get('message_type', '') for item in contract.get('produces', []) if isinstance(item, dict)]
	consumes = [item.get('message_type', '') if isinstance(item, dict) else str(item or '') for item in contract.get('consumes', [])]
	return {
		'agent_id': str(agent_id or '').strip(),
		'role': contract.get('role', ''),
		'skill': contract.get('skill', ''),
		'contract': contract,
		'assets': assets,
		'produces': produces,
		'consumes': consumes,
		'routes_to': list(contract.get('routes_to', [])) if isinstance(contract.get('routes_to', []), list) else []
	}


def _load_agent_registry():
	registry = {}
	contracts = _load_agent_contracts()
	known_agent_ids = set(list(AGENT_DIRS.keys()) + list(contracts.keys()))
	for agent_id in sorted(known_agent_ids):
		registry[agent_id] = _build_agent_descriptor(
			agent_id,
			contracts.get(agent_id, {}),
			_load_agent_assets(agent_id)
		)
	return registry


def _get_agent_descriptor(agent_id: str, registry: dict):
	if not isinstance(registry, dict):
		registry = {}
	descriptor = registry.get(str(agent_id or '').strip(), {})
	if isinstance(descriptor, dict):
		return descriptor
	return _build_agent_descriptor(str(agent_id or '').strip(), {}, _empty_agent_assets())


def _invoke_agent_runtime(agent_id: str, action_name: str, *args, registry: dict = None):
	if not isinstance(registry, dict):
		registry = _load_agent_registry()
	descriptor = _get_agent_descriptor(agent_id, registry)
	assets = descriptor.get('assets', {})
	runtime_exports = assets.get('runtime_exports', {})
	if not isinstance(runtime_exports, dict):
		runtime_exports = {}
	export_name = str(runtime_exports.get(action_name) or '').strip()
	if not export_name:
		raise ValueError(f'agent_runtime_export_not_found:{agent_id}:{action_name}')
	module = _load_agent_runtime_module(agent_id)
	handler = getattr(module, export_name, None)
	if handler is None or not callable(handler):
		raise ValueError(f'agent_runtime_handler_not_found:{agent_id}:{export_name}')
	return handler(*args)


def _load_multiagent_schema_defs():
	schema_path = os.path.join(AGENTS_SHARED_ROOT, 'multiagent.schema.json')
	if not os.path.exists(schema_path):
		return {}
	try:
		return _load_json_object(schema_path).get('$defs', {})
	except Exception:
		return {}


def _schema_ref_name(schema_ref: str):
	text = str(schema_ref or '').strip()
	if not text:
		return ''
	return text.rsplit('/', 1)[-1]


def _schema_for_name(schema_name: str, defs: dict):
	return defs.get(str(schema_name or '').strip(), {})


def _validate_schema_node(value, schema: dict, defs: dict, path: str, errors: list):
	if not isinstance(schema, dict):
		return
	if '$ref' in schema:
		ref_name = _schema_ref_name(schema.get('$ref', ''))
		ref_schema = _schema_for_name(ref_name, defs)
		if not ref_schema:
			errors.append(f'{path}:missing_schema_ref:{ref_name}')
			return
		return _validate_schema_node(value, ref_schema, defs, path, errors)
	if 'const' in schema and value != schema.get('const'):
		errors.append(f'{path}:const_mismatch')
	if 'enum' in schema and value not in schema.get('enum', []):
		errors.append(f'{path}:enum_mismatch')
	schema_type = schema.get('type')
	if schema_type == 'object':
		if not isinstance(value, dict):
			errors.append(f'{path}:expected_object')
			return
		properties = schema.get('properties', {})
		required = schema.get('required', [])
		for key in required:
			if key not in value:
				errors.append(f'{path}.{key}:required')
		if schema.get('additionalProperties') is False:
			for key in value.keys():
				if key not in properties:
					errors.append(f'{path}.{key}:unexpected_property')
		for key, prop_schema in properties.items():
			if key in value:
				_validate_schema_node(value.get(key), prop_schema, defs, f'{path}.{key}', errors)
		return
	if schema_type == 'array':
		if not isinstance(value, list):
			errors.append(f'{path}:expected_array')
			return
		item_schema = schema.get('items')
		if isinstance(item_schema, dict):
			for index, item in enumerate(value):
				_validate_schema_node(item, item_schema, defs, f'{path}[{index}]', errors)
		return
	if schema_type == 'string':
		if not isinstance(value, str):
			errors.append(f'{path}:expected_string')
			return
		min_length = schema.get('minLength')
		if isinstance(min_length, int) and len(value) < min_length:
			errors.append(f'{path}:min_length')
		return
	if schema_type == 'boolean':
		if not isinstance(value, bool):
			errors.append(f'{path}:expected_boolean')
		return


def _validate_schema_payload(schema_name: str, payload):
	defs = _load_multiagent_schema_defs()
	schema = _schema_for_name(schema_name, defs)
	errors = []
	if not schema:
		return {
			'schema': schema_name,
			'ok': False,
			'errors': [f'missing_schema:{schema_name}']
		}
	_validate_schema_node(payload, schema, defs, schema_name, errors)
	return {
		'schema': schema_name,
		'ok': not errors,
		'errors': errors
	}


def _contract_message_types(entries):
	message_types = []
	if not isinstance(entries, list):
		return message_types
	for item in entries:
		if isinstance(item, dict):
			message_type = str(item.get('message_type') or '').strip()
			if message_type:
				message_types.append(message_type)
	return message_types


def _validate_contract_flow(messages: list, contracts: dict):
	errors = []
	for index, message in enumerate(messages):
		if not isinstance(message, dict):
			errors.append(f'messages[{index}]:expected_object')
			continue
		message_type = str(message.get('message_type') or '').strip()
		from_agent = str(message.get('from_agent') or '').strip()
		to_agent = str(message.get('to_agent') or '').strip()
		if from_agent not in ('', 'user'):
			contract = contracts.get(from_agent, {})
			produces = _contract_message_types(contract.get('produces', []))
			if produces and message_type not in produces:
				errors.append(f'messages[{index}]:{from_agent}_cannot_produce_{message_type}')
		if to_agent not in ('', 'user'):
			contract = contracts.get(to_agent, {})
			consumes = _contract_message_types(contract.get('consumes', []))
			if consumes and message_type not in consumes:
				errors.append(f'messages[{index}]:{to_agent}_cannot_consume_{message_type}')
	return errors


def _build_multiagent_validation(plan: dict, messages: list, outputs: dict, registry: dict = None):
	schema_checks = {}
	output_schema_map = {
		'task_brief': 'taskBrief',
		'project_state_brief': 'projectStateBrief',
		'validation_state_brief': 'validationStateBrief',
		'candidate_plan': 'candidatePlan',
		'compatibility_brief': 'compatibilityBrief',
		'edit_plan_brief': 'editPlanBrief',
		'execution_result': 'executionResult',
		'validation_brief': 'validationBrief',
		'retry_request': 'retryRequest',
		'final_report': 'finalReport'
	}
	for key, schema_name in output_schema_map.items():
		if key in outputs:
			schema_checks[key] = _validate_schema_payload(schema_name, outputs.get(key))
	envelope_checks = []
	for index, message in enumerate(messages):
		check = _validate_schema_payload('messageEnvelope', message)
		check['index'] = index
		envelope_checks.append(check)
	if not isinstance(registry, dict):
		registry = _load_agent_registry()
	contracts = {
		agent_id: descriptor.get('contract', {})
		for agent_id, descriptor in registry.items()
		if isinstance(descriptor, dict)
	}
	contract_errors = _validate_contract_flow(messages, contracts)
	ok = (
		all(item.get('ok') for item in schema_checks.values())
		and all(item.get('ok') for item in envelope_checks)
		and not contract_errors
	)
	return {
		'ok': ok,
		'schema_checks': schema_checks,
		'envelope_checks': envelope_checks,
		'contract_flow': {
			'ok': not contract_errors,
			'errors': contract_errors
		},
		'route_length': len(plan.get('route', [])) if isinstance(plan, dict) else 0
	}


def _normalize_task_type(raw_task_type: str, user_goal: str):
	task_type = str(raw_task_type or '').strip().lower()
	if task_type in ('read', 'create', 'modify', 'repair', 'verify'):
		return task_type
	goal = str(user_goal or '').lower()
	if any(token in goal for token in ['读取', '查看', '分析', '现状', '内容有什么']):
		return 'read'
	if any(token in goal for token in ['修复', '纠错', '重试', '失败']):
		return 'repair'
	if any(token in goal for token in ['验证', '检查结果', '校验']):
		return 'verify'
	if any(token in goal for token in ['创建', '新建', '搭建', '生成']):
		return 'create'
	return 'modify'


def _should_require_kb(task_type: str, user_goal: str, allow_experimental: bool, routing_config: dict):
	if task_type in ('create', 'repair'):
		return True
	if allow_experimental:
		return True
	goal = str(user_goal or '').lower()
	for keyword in routing_config.get('kb_keywords', []):
		if str(keyword).lower() in goal:
			return True
	return False


def _build_task_brief(data: dict, routing_config: dict, registry: dict = None):
	return _invoke_agent_runtime(
		'agent-0-orchestrator',
		'build_task_brief',
		data,
		routing_config,
		_build_agent_runtime_context(),
		registry=registry
	)


def _build_route_steps(task_brief: dict, registry: dict):
	steps = _invoke_orchestrator_runtime('build_route_agent_ids', task_brief, registry=registry)
	if not isinstance(steps, list):
		steps = []
	route = []
	for agent_id in steps:
		descriptor = _get_agent_descriptor(agent_id, registry)
		route.append(_invoke_orchestrator_runtime('build_route_entry', agent_id, descriptor, registry=registry))
	return route


def _build_multiagent_route_plan(data: dict, registry: dict = None):
	routing_config = _load_routing_config()
	if not isinstance(registry, dict):
		registry = _load_agent_registry()
	task_brief = _build_task_brief(data, routing_config, registry=registry)
	route = _build_route_steps(task_brief, registry)
	envelope = _invoke_orchestrator_runtime(
		'build_agent_envelope',
		task_brief,
		1,
		'agent-0-orchestrator',
		route[0]['agent_id'] if route else 'agent-0-orchestrator',
		'task_brief',
		task_brief,
		task_brief['next_action'],
		registry=registry
	)
	orchestrator_descriptor = _get_agent_descriptor('agent-0-orchestrator', registry)
	registry_summary = _invoke_orchestrator_runtime('build_agent_registry_summary', registry, registry=registry)
	plan = _invoke_orchestrator_runtime('build_route_plan_payload', orchestrator_descriptor, task_brief, envelope, route, registry_summary, routing_config, registry=registry)
	plan['validation'] = _build_multiagent_validation(plan, [envelope], {'task_brief': task_brief}, registry=registry)
	return plan


def _load_json_lines(file_path: str):
	if not os.path.exists(file_path):
		return []
	out = []
	with open(file_path, 'r', encoding='utf-8') as f:
		for raw_line in f:
			line = raw_line.strip()
			if not line:
				continue
			try:
				item = json.loads(line)
			except Exception:
				continue
			if isinstance(item, dict):
				out.append(item)
	return out


def _version_key(raw_version: str):
	text = str(raw_version or '').strip()
	if not text:
		return (0, 0)
	candidate = ''.join([ch if (ch.isdigit() or ch == '.') else ' ' for ch in text]).split()
	if not candidate:
		return (0, 0)
	version_token = candidate[0]
	parts = [part for part in version_token.split('.') if part]
	if not parts:
		return (0, 0)
	major = int(parts[0]) if parts[0].isdigit() else 0
	minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
	return (major, minor)


def _extract_goal_terms(goal: str):
	text = str(goal or '').strip().lower()
	if not text:
		return []
	preferred = [
		'pop', 'top', 'chop', 'sop', 'comp', 'dat', 'mat',
		'feedback', 'audio', 'video', 'camera', 'null',
		'container', 'table', 'script', 'python', 'dmx',
		'openvr', 'touchengine', 'palette', '节点', '组件',
		'连接', '连线', '参数', '版本', '兼容', '反馈', '声音', '图像'
	]
	seen = set()
	out = []
	for token in preferred:
		if token in text and token not in seen:
			seen.add(token)
			out.append(token)
	for chunk in text.replace('/', ' ').replace('_', ' ').replace('-', ' ').split():
		chunk = chunk.strip()
		if len(chunk) >= 3 and chunk not in seen:
			seen.add(chunk)
			out.append(chunk)
	return out[:24]


def _label_node_summary(item: dict):
	if not isinstance(item, dict):
		return ''
	name = str(item.get('name') or '').strip()
	node_type = str(item.get('type') or '').strip()
	path = str(item.get('path') or '').strip()
	return ' | '.join([part for part in [name, node_type, path] if part])


def _collect_framework_connections_summary(forest):
	out = []
	for _, node_info in _walk_framework_nodes(forest):
		rel_path = str(node_info.get('relPath') or '').strip()
		connections = node_info.get('connections', {})
		if not isinstance(connections, dict):
			continue
		inputs = connections.get('inputs', [])
		if not isinstance(inputs, list) or not inputs:
			continue
		links = []
		for entry in inputs:
			if not isinstance(entry, dict):
				continue
			for source_name in entry.get('links', []):
				links.append(str(source_name))
		if links:
			out.append({
				'target': rel_path,
				'inputs': links[:8]
			})
	return out[:20]


def _build_relevant_nodes(goal: str, summary: dict):
	terms = _extract_goal_terms(goal)
	candidates = []
	for item in summary.get('top_level_nodes', []):
		if isinstance(item, dict):
			candidates.append(item)
	for item in summary.get('non_default_nodes', []):
		if isinstance(item, dict):
			candidates.append(item)
	matched = []
	seen = set()
	for item in candidates:
		label = _label_node_summary(item)
		if not label:
			continue
		low = label.lower()
		if not terms or any(term in low for term in terms):
			if label not in seen:
				seen.add(label)
				matched.append(label)
	return matched[:20]


def _build_project_state_brief(task_brief: dict, data: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-1-state-reader', 'build_project_state_brief', task_brief, data, _build_agent_runtime_context(), registry=registry)


def _build_family_records():
	records = {}
	for item in _load_json_lines(FAMILY_COMPATIBILITY_FILE):
		family = str(item.get('family') or '').strip().upper()
		if family and family not in records:
			records[family] = item
	return records


def _detect_goal_families(goal: str):
	goal_lower = str(goal or '').lower()
	families = []
	for family in ('POP', 'TOP', 'CHOP', 'SOP', 'COMP', 'DAT', 'MAT'):
		if family.lower() in goal_lower:
			families.append(family)
	return families


def _load_agent_runtime_module(agent_id: str):
	module_path = AGENT_RUNTIME_FILES.get(str(agent_id or '').strip(), '')
	if not module_path or not os.path.exists(module_path):
		raise ValueError(f'agent_runtime_not_found:{agent_id}')
	module_name = 'agent_runtime_' + ''.join([ch if ch.isalnum() else '_' for ch in str(agent_id or '')])
	spec = importlib.util.spec_from_file_location(module_name, module_path)
	if spec is None or spec.loader is None:
		raise ValueError(f'agent_runtime_invalid:{agent_id}')
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _build_agent_runtime_context():
	return {
		'DEFAULT_TD_HOST': DEFAULT_TD_HOST,
		'DEFAULT_TD_PORT': DEFAULT_TD_PORT,
		'DEFAULT_TIMEOUT': DEFAULT_TIMEOUT,
		'DEFAULT_FRAMEWORK_FILE': DEFAULT_FRAMEWORK_FILE,
		'DEFAULT_INFORMATION_FILE': DEFAULT_INFORMATION_FILE,
		'FAMILY_COMPATIBILITY_FILE': FAMILY_COMPATIBILITY_FILE,
		'normalize_task_type': _normalize_task_type,
		'should_require_kb': _should_require_kb,
		'send_td_command': _send_td_command,
		'load_project_scan_file': _load_project_scan_file,
		'build_project_summary': _build_project_summary,
		'label_node_summary': _label_node_summary,
		'build_relevant_nodes': _build_relevant_nodes,
		'collect_framework_connections_summary': _collect_framework_connections_summary,
		'build_family_records': _build_family_records,
		'detect_goal_families': _detect_goal_families,
		'version_key': _version_key,
		'normalize_framework_change': _normalize_framework_change,
		'build_runtime_command_chain': _build_runtime_command_chain,
		'execute_runtime_commands': _execute_runtime_commands,
		'refresh_project_state_after_execution': _refresh_project_state_after_execution,
		'detect_runtime_bootstrap_issue': _detect_runtime_bootstrap_issue,
		'verify_framework_changes_against_project': _verify_framework_changes_against_project,
		'call_agent_json': _call_agent_json
	}


def _build_candidate_plan(task_brief: dict, state_brief: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-0-orchestrator', 'build_candidate_plan', task_brief, state_brief, _build_agent_runtime_context(), registry=registry)


def _build_compatibility_brief(task_brief: dict, state_brief: dict, candidate_plan: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-2-kb-consultant', 'build_compatibility_brief', task_brief, state_brief, candidate_plan, _build_agent_runtime_context(), registry=registry)


def _build_retry_compatibility_brief(task_brief: dict, state_brief: dict, candidate_plan: dict, retry_request: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-2-kb-consultant', 'build_retry_compatibility_brief', task_brief, state_brief, candidate_plan, retry_request, _build_agent_runtime_context(), registry=registry)


def _normalize_framework_change(item: dict, scope: str):
	if not isinstance(item, dict):
		return None
	path = str(item.get('path') or scope or '/project1').strip() or '/project1'
	if not path.startswith('/'):
		path = '/' + path.lstrip('/')
	return {
		'path': path,
		'type': str(item.get('type') or 'baseCOMP').strip() or 'baseCOMP',
		'action': str(item.get('action') or 'modify').strip() or 'modify',
		'parameters': item.get('parameters', {}),
		'connections': item.get('connections', {})
	}


def _build_edit_plan_brief(task_brief: dict, state_brief: dict, compatibility_brief: dict, data: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-3-framework-editor', 'build_edit_plan_brief', task_brief, state_brief, compatibility_brief, data, _build_agent_runtime_context(), registry=registry)


def _build_retry_edit_plan_brief(task_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, data: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-3-framework-editor', 'build_retry_edit_plan_brief', task_brief, state_brief, compatibility_brief, retry_request, data, _build_agent_runtime_context(), registry=registry)


def _node_name_from_path(path: str):
	text = str(path or '').strip().rstrip('/')
	if not text:
		return 'node1'
	name = text.rsplit('/', 1)[-1].strip()
	return name or 'node1'


def _build_tree_from_paths(path_specs: list, parent_path: str = '/project1'):
	node_map = {}
	for item in path_specs:
		if not isinstance(item, dict):
			continue
		rel_path = str(item.get('path') or '').strip()
		if not rel_path.startswith('/project1/'):
			continue
		node_map[rel_path] = {
			'name': _node_name_from_path(rel_path),
			'relPath': rel_path,
			'type': _normalize_op_type(str(item.get('type') or 'baseCOMP'), _node_name_from_path(rel_path)),
			'pos': item.get('pos', {'x': 0, 'y': 0}),
			'parameters': item.get('parameters', {}),
			'connections': item.get('connections', {}),
			'children': []
		}
	for rel_path in sorted(node_map.keys(), key=lambda value: value.count('/'), reverse=True):
		parent = rel_path.rsplit('/', 1)[0]
		if parent in node_map:
			child_info = dict(node_map[rel_path])
			child_name = child_info.pop('name')
			node_map[parent]['children'].append({child_name: child_info})
	top_level = []
	for rel_path in sorted(node_map.keys()):
		if rel_path.rsplit('/', 1)[0] != parent_path:
			continue
		node_info = dict(node_map[rel_path])
		node_name = node_info.pop('name')
		top_level.append({node_name: node_info})
	return _normalize_framework_forest(top_level)


def _build_forest_from_framework_changes(task_brief: dict, edit_plan_brief: dict):
	path_specs = []
	for index, item in enumerate(edit_plan_brief.get('framework_changes', [])):
		if not isinstance(item, dict):
			continue
		path = str(item.get('path') or '').strip()
		if not path:
			continue
		path_specs.append({
			'path': path,
			'type': str(item.get('type') or 'baseCOMP'),
			'parameters': item.get('parameters', {}),
			'connections': item.get('connections', {}),
			'pos': {'x': index * 180, 'y': 0}
		})
	if not path_specs:
		scope = str(task_brief.get('scope') or '/project1').strip() or '/project1'
		if scope == '/project1':
			scope = '/project1/generated1'
		path_specs.append({
			'path': scope,
			'type': 'baseCOMP',
			'parameters': {},
			'pos': {'x': 0, 'y': 0}
		})
	return _build_tree_from_paths(path_specs)


def _build_runtime_command_chain(task_brief: dict, edit_plan_brief: dict, data: dict):
	raw_commands = data.get('commands', [])
	if isinstance(raw_commands, list) and raw_commands:
		return _normalize_commands(raw_commands)
	raw_forest = data.get('framework_forest', [])
	if isinstance(raw_forest, list) and raw_forest:
		forest = _normalize_framework_forest(raw_forest)
	else:
		forest = _build_forest_from_framework_changes(task_brief, edit_plan_brief)
	file_name = str(data.get('framework_file') or DEFAULT_FRAMEWORK_FILE)
	return [
		{'cmd': 'write_framework_json', 'file': file_name, 'forest': forest},
		{'cmd': 'reload'},
		{'cmd': 'replicate_framework', 'file': 'AgenTD/' + file_name, 'clear_parent': bool(task_brief.get('constraints', {}).get('allow_rebuild', False))},
		{'cmd': 'save_project'}
	]


def _execute_runtime_commands(commands: list, host: str, port: int, timeout_sec: int):
	status = 'executed'
	executed_commands = []
	runtime_notes = []
	for cmd in _normalize_commands(commands):
		try:
			resp = _execute_local_command(cmd)
			if resp is None:
				resp = _send_td_command(cmd, host, port, timeout_sec)
			executed_commands.append(str(cmd.get('cmd') or ''))
			runtime_notes.append(str(resp))
			if str(resp).startswith('error:'):
				status = 'failed'
				break
		except Exception as exc:
			status = 'failed'
			executed_commands.append(str(cmd.get('cmd') or ''))
			runtime_notes.append(str(exc))
			break
	return status, executed_commands, runtime_notes


def _refresh_project_state_after_execution(data: dict):
	host = str(data.get('host') or DEFAULT_TD_HOST)
	port = int(data.get('port') or DEFAULT_TD_PORT)
	timeout_sec = int(data.get('timeout') or DEFAULT_TIMEOUT)
	secret_agent_path = str(data.get('secret_agent_path') or '/SecretAgent')
	try:
		resp = _send_td_command({
			'cmd': 'refresh_project_state',
			'secret_agent_path': secret_agent_path
		}, host, port, timeout_sec)
		return resp, not str(resp).startswith('error:')
	except Exception as exc:
		return str(exc), False


def _collect_project_node_paths():
	information_forest, _ = _load_project_scan_file(DEFAULT_INFORMATION_FILE)
	return {str(item.get('path') or '').strip() for item in _collect_forest_nodes(information_forest) if isinstance(item, dict)}


def _verify_framework_changes_against_project(edit_plan_brief: dict):
	project_paths = _collect_project_node_paths()
	verified = []
	missing = []
	for item in edit_plan_brief.get('framework_changes', []):
		if not isinstance(item, dict):
			continue
		path = str(item.get('path') or '').strip()
		if not path:
			continue
		label = f'{item.get("action", "")}:{path}:{item.get("type", "")}'
		if path in project_paths:
			verified.append(label)
		else:
			missing.append(f'未在扫描结果中发现 {path}')
	return verified, missing


def _detect_runtime_bootstrap_issue(runtime_notes: list):
	if not isinstance(runtime_notes, list):
		return ''
	for item in runtime_notes:
		text = str(item or '')
		if "spec not found for the module 'commands'" in text:
			return 'TouchDesigner 侧仍在使用旧的 commands 模块对象，sys.modules 中的旧实例没有可重载 spec。需更新 lib/server_callbacks.py 的加载逻辑，并在 TD 内重新加载 callbacks DAT 或重启 TCP 服务。'
	return ''


def _build_execution_result(task_brief: dict, edit_plan_brief: dict, data: dict, registry: dict = None):
	return _invoke_agent_runtime(
		'agent-3-framework-editor',
		'build_execution_result',
		task_brief,
		edit_plan_brief,
		data,
		_build_agent_runtime_context(),
		registry=registry
	)


def _build_validation_state_brief(task_brief: dict, execution_result: dict, data: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-4-verifier', 'build_validation_state_brief', task_brief, execution_result, data, _build_agent_runtime_context(), registry=registry)


def _build_validation_brief(task_brief: dict, state_brief: dict, validation_state_brief: dict, compatibility_brief: dict, edit_plan_brief: dict, execution_result: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-4-verifier', 'build_validation_brief', task_brief, state_brief, validation_state_brief, compatibility_brief, edit_plan_brief, execution_result, _build_agent_runtime_context(), registry=registry)


def _build_retry_request(validation_brief: dict, registry: dict = None):
	return _invoke_agent_runtime('agent-4-verifier', 'build_retry_request', validation_brief, registry=registry)


def _invoke_orchestrator_runtime(runtime_name: str, *args, registry: dict = None):
	return _invoke_agent_runtime('agent-0-orchestrator', runtime_name, *args, registry=registry)


def _append_phase_message(messages: list, task_brief: dict, message_index: int, message_spec: dict, registry: dict = None):
	return _invoke_orchestrator_runtime('append_phase_message', messages, task_brief, message_index, message_spec, registry=registry)


def _run_retry_compatibility_block(task_brief: dict, state_brief: dict, candidate_plan: dict, retry_request: dict, messages: list, message_index: int, registry: dict):
	compatibility_brief = _build_retry_compatibility_brief(task_brief, state_brief, candidate_plan, retry_request, registry=registry)
	compatibility_phase = _invoke_orchestrator_runtime('build_retry_compatibility_phase', task_brief, compatibility_brief, registry=registry)
	message_update = _append_phase_message(messages, task_brief, message_index, compatibility_phase.get('compatibility_message', {}), registry=registry)
	return {
		'messages': message_update.get('messages', messages),
		'message_index': int(message_update.get('message_index', message_index)),
		'compatibility_brief': compatibility_brief,
		'validation_brief': compatibility_phase.get('validation_brief'),
		'validation_message': compatibility_phase.get('validation_message', {})
	}


def _run_retry_failure_finalize_block(task_brief: dict, validation_state_brief: dict, compatibility_brief: dict, edit_plan_brief: dict, validation_brief: dict, validation_message: dict, candidate_plan: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	if isinstance(validation_brief, dict) and validation_brief:
		message_update = _append_phase_message(messages, task_brief, message_index, validation_message, registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	next_retry_request = _build_retry_request(validation_brief, registry=registry)
	output_patch = _invoke_orchestrator_runtime('build_multiagent_output_patch', compatibility_brief, edit_plan_brief, None, None, validation_state_brief, validation_brief, next_retry_request, registry=registry)
	outputs.update(output_patch.get('outputs', {}))
	retry_phase = _invoke_orchestrator_runtime('build_retry_request_phase', next_retry_request, registry=registry)
	if retry_phase.get('retry_message'):
		message_update = _append_phase_message(messages, task_brief, message_index, retry_phase.get('retry_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	if output_patch.get('clear_retry_request') or retry_phase.get('clear_retry_request'):
		outputs.pop('retry_request', None)
	completion = _invoke_orchestrator_runtime('build_retry_cycle_completion', validation_state_brief, candidate_plan, compatibility_brief, edit_plan_brief, validation_brief, next_retry_request, message_index, registry=registry)
	completion['messages'] = messages
	return completion


def _run_retry_execution_validation_block(task_brief: dict, state_brief: dict, validation_state_brief: dict, compatibility_brief: dict, edit_plan_brief: dict, data: dict, retry_request: dict, candidate_plan: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	edit_plan_brief = _build_retry_edit_plan_brief(task_brief, state_brief, compatibility_brief, retry_request, data, registry=registry)
	execution_bundle = _build_execution_result(task_brief, edit_plan_brief, data, registry=registry)
	execution_outputs = _invoke_orchestrator_runtime('build_execution_bundle_outputs', execution_bundle, registry=registry)
	execution_result = execution_outputs.get('execution_result', {})
	runtime_commands = execution_outputs.get('runtime_commands', [])
	validation_state_brief = _build_validation_state_brief(task_brief, execution_result, data, registry=registry)
	validation_brief = _build_validation_brief(task_brief, state_brief, validation_state_brief, compatibility_brief, edit_plan_brief, execution_result, registry=registry)
	execution_phase = _invoke_orchestrator_runtime('build_execution_validation_phase', task_brief, execution_result, validation_brief, registry=registry)
	message_update = _append_phase_message(messages, task_brief, message_index, execution_phase.get('execution_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	message_index = int(message_update.get('message_index', message_index))
	message_update = _append_phase_message(messages, task_brief, message_index, execution_phase.get('validation_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	message_index = int(message_update.get('message_index', message_index))
	next_retry_request = _build_retry_request(validation_brief, registry=registry)
	output_patch = _invoke_orchestrator_runtime('build_multiagent_output_patch', compatibility_brief, edit_plan_brief, execution_result, runtime_commands, validation_state_brief, validation_brief, next_retry_request, registry=registry)
	outputs.update(output_patch.get('outputs', {}))
	retry_phase = _invoke_orchestrator_runtime('build_retry_request_phase', next_retry_request, registry=registry)
	if retry_phase.get('retry_message'):
		message_update = _append_phase_message(messages, task_brief, message_index, retry_phase.get('retry_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	completion = _invoke_orchestrator_runtime('build_retry_cycle_completion', validation_state_brief, candidate_plan, compatibility_brief, edit_plan_brief, validation_brief, next_retry_request, message_index, registry=registry)
	if output_patch.get('clear_retry_request') or retry_phase.get('clear_retry_request') or completion.get('clear_retry_request'):
		outputs.pop('retry_request', None)
	completion['messages'] = messages
	return completion


def _run_retry_cycle(task_brief: dict, state_brief: dict, validation_state_brief: dict, candidate_plan: dict, compatibility_brief: dict, edit_plan_brief: dict, data: dict, retry_request: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	retry_target = str(retry_request.get('retry_target') or '').strip()
	outputs['retry_history'] = _invoke_orchestrator_runtime('build_retry_history', outputs.get('retry_history', []), retry_request, registry=registry)
	if retry_target == 'agent-2-kb-consultant':
		compatibility_result = _run_retry_compatibility_block(task_brief, state_brief, candidate_plan, retry_request, messages, message_index, registry)
		messages = compatibility_result.get('messages', messages)
		message_index = int(compatibility_result.get('message_index', message_index))
		compatibility_brief = compatibility_result.get('compatibility_brief', compatibility_brief)
		validation_brief = compatibility_result.get('validation_brief')
		if isinstance(validation_brief, dict) and validation_brief:
			return _run_retry_failure_finalize_block(task_brief, validation_state_brief, compatibility_brief, edit_plan_brief, validation_brief, compatibility_result.get('validation_message', {}), candidate_plan, messages, outputs, message_index, registry)
	return _run_retry_execution_validation_block(task_brief, state_brief, validation_state_brief, compatibility_brief, edit_plan_brief, data, retry_request, candidate_plan, messages, outputs, message_index, registry)


def _run_state_block(task_brief: dict, data: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	state_brief = None
	if task_brief.get('requires_state_read'):
		state_brief = _build_project_state_brief(task_brief, data, registry=registry)
		state_block = _invoke_orchestrator_runtime('build_state_phase_block', task_brief, state_brief, registry=registry)
		outputs.update(state_block.get('outputs', {}))
		message_update = _append_phase_message(messages, task_brief, message_index, state_block.get('state_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	else:
		state_brief = _invoke_orchestrator_runtime('build_fallback_state_brief', task_brief, registry=registry)
	return {
		'messages': messages,
		'state_brief': state_brief,
		'message_index': message_index
	}


def _run_read_only_block(plan: dict, task_brief: dict, state_brief: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	read_block = _invoke_orchestrator_runtime('build_read_runtime_block', task_brief, state_brief, _build_agent_runtime_context(), registry=registry)
	outputs.update(read_block.get('outputs', {}))
	message_update = _append_phase_message(messages, task_brief, message_index, read_block.get('final_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	runtime = _invoke_orchestrator_runtime('build_runtime_payload', plan, messages, outputs, registry=registry)
	runtime['validation'] = _build_multiagent_validation(plan, messages, outputs, registry=registry)
	runtime['runtime_paths'] = _persist_multiagent_runtime(runtime)
	return runtime


def _run_kb_block(task_brief: dict, state_brief: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	candidate_plan = None
	compatibility_brief = None
	if task_brief.get('requires_kb_check'):
		candidate_plan = _build_candidate_plan(task_brief, state_brief, registry=registry)
		compatibility_brief = _build_compatibility_brief(task_brief, state_brief, candidate_plan, registry=registry)
		kb_block = _invoke_orchestrator_runtime('build_kb_phase_block', task_brief, candidate_plan, compatibility_brief, registry=registry)
		outputs.update(kb_block.get('outputs', {}))
		message_update = _append_phase_message(messages, task_brief, message_index, kb_block.get('candidate_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
		message_update = _append_phase_message(messages, task_brief, message_index, kb_block.get('compatibility_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	else:
		compatibility_brief = _invoke_orchestrator_runtime('build_default_compatibility_brief', task_brief, registry=registry)
	return {
		'messages': messages,
		'candidate_plan': candidate_plan,
		'compatibility_brief': compatibility_brief,
		'message_index': message_index
	}


def _run_execution_validation_block(task_brief: dict, state_brief: dict, compatibility_brief: dict, edit_plan_brief: dict, data: dict, messages: list, outputs: dict, message_index: int, registry: dict):
	if task_brief.get('requires_edit') and not compatibility_brief.get('rejected_choices'):
		edit_plan_brief = _build_edit_plan_brief(task_brief, state_brief, compatibility_brief, data, registry=registry)
		outputs['edit_plan_brief'] = edit_plan_brief
	execution_bundle = _build_execution_result(task_brief, edit_plan_brief, data, registry=registry)
	execution_outputs = _invoke_orchestrator_runtime('build_execution_bundle_outputs', execution_bundle, registry=registry)
	execution_result = execution_outputs.get('execution_result', {})
	runtime_commands = execution_outputs.get('runtime_commands', [])
	validation_state_brief = _build_validation_state_brief(task_brief, execution_result, data, registry=registry)
	validation_brief = _build_validation_brief(task_brief, state_brief, validation_state_brief, compatibility_brief, edit_plan_brief, execution_result, registry=registry)
	execution_phase = _invoke_orchestrator_runtime('build_execution_validation_phase', task_brief, execution_result, validation_brief, registry=registry)
	message_update = _append_phase_message(messages, task_brief, message_index, execution_phase.get('execution_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	message_index = int(message_update.get('message_index', message_index))
	message_update = _append_phase_message(messages, task_brief, message_index, execution_phase.get('validation_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	message_index = int(message_update.get('message_index', message_index))
	retry_request = _build_retry_request(validation_brief, registry=registry)
	output_patch = _invoke_orchestrator_runtime('build_multiagent_output_patch', compatibility_brief, edit_plan_brief, execution_result, runtime_commands, validation_state_brief, validation_brief, retry_request, registry=registry)
	outputs.update(output_patch.get('outputs', {}))
	retry_phase = _invoke_orchestrator_runtime('build_retry_request_phase', retry_request, registry=registry)
	if retry_phase.get('retry_message'):
		message_update = _append_phase_message(messages, task_brief, message_index, retry_phase.get('retry_message', {}), registry=registry)
		messages = message_update.get('messages', messages)
		message_index = int(message_update.get('message_index', message_index))
	return {
		'messages': messages,
		'validation_state_brief': validation_state_brief,
		'edit_plan_brief': edit_plan_brief,
		'validation_brief': validation_brief,
		'retry_request': retry_request,
		'output_patch': output_patch,
		'retry_phase': retry_phase,
		'message_index': message_index
	}


def _run_finalization_block(plan: dict, task_brief: dict, validation_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, messages: list, outputs: dict, message_index: int, registry: dict, clear_retry_request: bool):
	final_block = _invoke_orchestrator_runtime('build_finalization_block', task_brief, validation_brief, state_brief, compatibility_brief, retry_request, _build_agent_runtime_context(), registry=registry)
	if clear_retry_request or final_block.get('clear_retry_request'):
		outputs.pop('retry_request', None)
	outputs.update(final_block.get('outputs', {}))
	message_update = _append_phase_message(messages, task_brief, message_index, final_block.get('final_message', {}), registry=registry)
	messages = message_update.get('messages', messages)
	runtime = _invoke_orchestrator_runtime('build_runtime_payload', plan, messages, outputs, registry=registry)
	runtime['validation'] = _build_multiagent_validation(plan, messages, outputs, registry=registry)
	runtime['runtime_paths'] = _persist_multiagent_runtime(runtime)
	return runtime


def _build_multiagent_execution(data: dict):
	_emit_stage('orchestrator', 'running', 'Orchestrator 正在规划路线...')
	registry = _load_agent_registry()
	plan = _build_multiagent_route_plan(data, registry=registry)
	task_brief = plan['task_brief']
	_emit_stage('orchestrator', 'done', '路线规划完成', task_brief.get('summary', ''))
	
	execution_state = _invoke_orchestrator_runtime('build_execution_state', plan, registry=registry)
	messages = execution_state.get('messages', []) if isinstance(execution_state, dict) else []
	outputs = execution_state.get('outputs', {}) if isinstance(execution_state, dict) else {}
	message_index = execution_state.get('message_index', 2) if isinstance(execution_state, dict) else 2
	execution_seed = _invoke_orchestrator_runtime('build_execution_brief_seed', task_brief, registry=registry)
	state_brief = execution_seed.get('state_brief')
	validation_state_brief = execution_seed.get('validation_state_brief', {})
	candidate_plan = execution_seed.get('candidate_plan')
	compatibility_brief = execution_seed.get('compatibility_brief')
	edit_plan_brief = execution_seed.get('edit_plan_brief', {})
	
	_emit_stage('state_reader', 'running', 'State Reader 正在读取项目现状...')
	state_result = _run_state_block(task_brief, data, messages, outputs, message_index, registry)
	messages = state_result.get('messages', messages)
	state_brief = state_result.get('state_brief', state_brief)
	message_index = int(state_result.get('message_index', message_index))
	_emit_stage('state_reader', 'done', '项目现状已读取')
	
	if task_brief.get('task_type') == 'read':
		return _run_read_only_block(plan, task_brief, state_brief, messages, outputs, message_index, registry)
		
	_emit_stage('kb_consultant', 'running', 'KB Consultant 正在校验兼容性...')
	kb_result = _run_kb_block(task_brief, state_brief, messages, outputs, message_index, registry)
	messages = kb_result.get('messages', messages)
	candidate_plan = kb_result.get('candidate_plan', candidate_plan)
	compatibility_brief = kb_result.get('compatibility_brief', compatibility_brief)
	message_index = int(kb_result.get('message_index', message_index))
	_emit_stage('kb_consultant', 'done', '知识校验完成')
	
	_emit_stage('framework_editor', 'running', 'Framework Editor 正在生成方案...')
	execution_result = _run_execution_validation_block(task_brief, state_brief, compatibility_brief, edit_plan_brief, data, messages, outputs, message_index, registry)
	messages = execution_result.get('messages', messages)
	validation_state_brief = execution_result.get('validation_state_brief', validation_state_brief)
	edit_plan_brief = execution_result.get('edit_plan_brief', edit_plan_brief)
	validation_brief = execution_result.get('validation_brief', {})
	retry_request = execution_result.get('retry_request')
	output_patch = execution_result.get('output_patch', {})
	retry_phase = execution_result.get('retry_phase', {})
	message_index = int(execution_result.get('message_index', message_index))
	_emit_stage('framework_editor', 'done', '连线方案已生成并校验')
	
	retry_policy = _invoke_orchestrator_runtime('build_auto_retry_policy', data, registry=registry)
	auto_retry_enabled = bool(retry_policy.get('auto_retry_enabled', True))
	max_auto_retries = int(retry_policy.get('max_auto_retries', 0))
	auto_retry_count = 0
	
	while retry_request and auto_retry_enabled and auto_retry_count < max_auto_retries:
		_emit_stage('verifier', 'running', f'Verifier 触发自动回环重试 (第 {auto_retry_count + 1} 次)...')
		retry_result = _run_retry_cycle(task_brief, state_brief, validation_state_brief, candidate_plan, compatibility_brief, edit_plan_brief, data, retry_request, messages, outputs, message_index, registry)
		messages = retry_result.get('messages', messages)
		validation_state_brief = retry_result.get('validation_state_brief', validation_state_brief)
		candidate_plan = retry_result.get('candidate_plan', candidate_plan)
		compatibility_brief = retry_result.get('compatibility_brief', compatibility_brief)
		edit_plan_brief = retry_result.get('edit_plan_brief', edit_plan_brief)
		validation_brief = retry_result.get('validation_brief', validation_brief)
		retry_request = retry_result.get('retry_request')
		message_index = int(retry_result.get('message_index', message_index))
		auto_retry_count += 1
		_emit_stage('verifier', 'done', f'第 {auto_retry_count} 次回环重试结束')
		
	outputs['auto_retry_count'] = auto_retry_count
	clear_retry_request = bool(output_patch.get('clear_retry_request')) or bool(retry_phase.get('clear_retry_request'))
	
	_emit_stage('assistant', 'running', '正在汇总最终报告...')
	final_runtime = _run_finalization_block(plan, task_brief, validation_brief, state_brief, compatibility_brief, retry_request, messages, outputs, message_index, registry, clear_retry_request)
	_emit_stage('assistant', 'done', '报告汇总完成')
	
	final_outputs = final_runtime.get('outputs', {})
	final_commands = final_outputs.get('runtime_commands', [])
	if final_commands:
		emit_fn = getattr(_thread_local, 'emit', None)
		if callable(emit_fn):
			emit_fn('stage', {
				'stage': 'framework_editor',
				'status': 'done',
				'message': '命令生成',
				'commandCount': len(final_commands),
				'commands': final_commands
			})
	return final_runtime


def _execute_local_command(cmd_obj: dict):
	if not isinstance(cmd_obj, dict):
		raise ValueError('invalid_command')
	cmd = str(cmd_obj.get('cmd') or '')
	if cmd != 'write_framework_json':
		return None
	target_path = _resolve_project_file(str(cmd_obj.get('file') or DEFAULT_FRAMEWORK_FILE))
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
	compact = ''.join([ch for ch in low if ch.isalnum()])
	compact_name = ''.join([ch for ch in str(node_name or '').lower() if ch.isalnum()])
	aliases = {
		'audiofilein': 'audiofileinCHOP',
		'audiofileinchop': 'audiofileinCHOP',
		'audiodeviceout': 'audiodeviceoutCHOP',
		'audiodeviceoutchop': 'audiodeviceoutCHOP',
		'audiodevicein': 'audiodeviceinCHOP',
		'audiodeviceinchop': 'audiodeviceinCHOP',
		'container': 'containerCOMP',
		'containercomp': 'containerCOMP',
		'base': 'baseCOMP',
		'null': 'nullCHOP',
		'text': 'textDAT',
		'textdat': 'textDAT',
		'textcomp': 'textCOMP',
		'webcontainer': 'containerCOMP',
		'webrender': 'webrenderTOP',
		'webrendertop': 'webrenderTOP',
		'webpage': 'webrenderTOP',
		'webtop': 'webrenderTOP'
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
		'containercomp': 'containerCOMP',
		'html': 'textDAT',
		'css': 'textDAT',
		'js': 'textDAT',
		'script': 'textDAT',
		'text': 'textDAT',
		'webrender': 'webrenderTOP',
		'browser': 'webrenderTOP'
	}
	if compact in aliases:
		return aliases[compact]
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


def _collect_invalid_framework_operator_types(forest):
	invalid = []
	for _, node_info in _walk_framework_nodes(forest):
		op_type = str(node_info.get('type') or '').strip()
		low = op_type.lower()
		if not op_type:
			invalid.append('(empty)')
			continue
		if low in ('top', 'chop', 'sop', 'comp', 'dat', 'mat'):
			continue
		if low.endswith(('top', 'chop', 'sop', 'comp', 'dat', 'mat')):
			continue
		invalid.append(op_type)
	return sorted(set(invalid))


def _is_web_content_goal(user_goal: str):
	goal = str(user_goal or '').lower()
	tokens = (
		'html',
		'css',
		'javascript',
		'js',
		'网页',
		'浏览器',
		'web',
		'鼠标',
		'小球',
		'ball'
	)
	return any(token in goal for token in tokens)


def _framework_has_operator_type(forest, operator_type: str):
	target = str(operator_type or '').strip().lower()
	if not target:
		return False
	for _, node_info in _walk_framework_nodes(forest):
		op_type = str(node_info.get('type') or '').strip().lower()
		if op_type == target:
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
	invalid_op_types = _collect_invalid_framework_operator_types(forest)
	if invalid_op_types:
		issues.append('forest 中存在非法或伪造的 TD OP 类型: ' + ', '.join(invalid_op_types))
	if _framework_has_family_placeholder_types(forest):
		issues.append('forest 中仍存在 TOP/CHOP/COMP 等占位类型，必须改成具体 TD OP 类型')
	if _framework_has_relative_paths(forest):
		issues.append('forest 中 relPath 不是绝对路径，必须写成 /project1/... 形式')
	if _framework_has_placeholder_parameter_names(forest):
		issues.append('forest 中使用了 Page/par 这类占位参数结构，必须改成真实页面名和参数名')
	if _is_web_content_goal(user_goal) and not _framework_has_operator_type(forest, 'webrenderTOP'):
		issues.append('网页交互类需求缺少 webrenderTOP 渲染节点，不能只创建容器或 Text DAT')
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
			'file': str(item.get('file') or item.get('source') or DEFAULT_FRAMEWORK_FILE),
			'forest': _normalize_framework_forest(item.get('forest', []))
		}
	if cmd == 'reload':
		return {'cmd': 'reload'}
	if cmd == 'replicate_framework':
		return {
			'cmd': 'replicate_framework',
			'file': 'AgenTD/' + str(item.get('file') or item.get('source') or DEFAULT_FRAMEWORK_FILE),
			'clear_parent': bool(item.get('clear_parent', True))
		}
	if cmd == 'save_project':
		out = {'cmd': 'save_project'}
		if item.get('file'):
			out['file'] = str(item.get('file'))
		return out
	if cmd == 'refresh_project_state':
		return {
			'cmd': 'refresh_project_state',
			'secret_agent_path': str(item.get('secret_agent_path') or '/SecretAgent')
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
	return []


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




class BridgeHandler(BaseHTTPRequestHandler):
	def do_OPTIONS(self):
		self.send_response(204)
		self.send_header('Access-Control-Allow-Origin', '*')
		self.send_header('Access-Control-Allow-Headers', 'Content-Type')
		self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
		self.end_headers()

	def do_GET(self):
		parsed = urlparse(self.path)
		path = parsed.path
		query = parse_qs(parsed.query or '')
		if path in ('/', '/index.html'):
			file_path = os.path.join(WEB_ROOT, 'index.html')
			return self._send_file(file_path, 'text/html; charset=utf-8')
		if path == '/app.js':
			file_path = os.path.join(WEB_ROOT, 'app.js')
			return self._send_file(file_path, 'text/javascript; charset=utf-8')
		if path == '/style.css':
			file_path = os.path.join(WEB_ROOT, 'style.css')
			return self._send_file(file_path, 'text/css; charset=utf-8')
		if path == '/api/multiagent/runtime/latest':
			return self._api_multiagent_runtime_latest(query)
		if path == '/api/multiagent/runtime/task':
			return self._api_multiagent_runtime_task(query)
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
		if self.path == '/api/project/summary':
			return self._api_project_summary(data)
		if self.path == '/api/multiagent/route':
			return self._api_multiagent_route(data)
		if self.path == '/api/multiagent/execute':
			return self._api_multiagent_execute(data)
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

	def _api_project_summary(self, data: dict):
		host = str(data.get('host') or DEFAULT_TD_HOST)
		port = int(data.get('port') or DEFAULT_TD_PORT)
		timeout_sec = int(data.get('timeout') or DEFAULT_TIMEOUT)
		secret_agent_path = str(data.get('secret_agent_path') or '/SecretAgent')
		refresh = bool(data.get('refresh', True))
		refresh_response = ''
		if refresh:
			try:
				refresh_response = _send_td_command({
					'cmd': 'refresh_project_state',
					'secret_agent_path': secret_agent_path
				}, host, port, timeout_sec)
			except Exception as exc:
				return _json_response(self, 200, {'ok': False, 'error': str(exc)})
			if refresh_response.startswith('error:'):
				return _json_response(self, 200, {'ok': False, 'error': refresh_response, 'refresh_response': refresh_response})
		summary = _build_project_summary()
		return _json_response(self, 200, {'ok': True, 'summary': summary, 'refresh_response': refresh_response})

	def _api_multiagent_route(self, data: dict):
		try:
			plan = _build_multiagent_route_plan(data)
			runtime_paths = _persist_multiagent_route_plan(plan)
			return _json_response(self, 200, {'ok': True, 'plan': plan, 'runtime_paths': runtime_paths})
		except ValueError as exc:
			return _json_response(self, 400, {'ok': False, 'error': str(exc)})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc)})

	def _api_multiagent_execute(self, data: dict):
		try:
			runtime = _build_multiagent_execution(data)
			return _json_response(self, 200, {'ok': True, 'runtime': runtime})
		except ValueError as exc:
			return _json_response(self, 400, {'ok': False, 'error': str(exc)})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc)})

	def _api_multiagent_runtime_latest(self, query: dict):
		try:
			task_id = ''
			values = query.get('task_id', [])
			if isinstance(values, list) and values:
				task_id = str(values[0] or '')
			bundle = _load_multiagent_runtime_bundle(task_id)
			return _json_response(self, 200, {'ok': any(bundle.values()), 'runtime': bundle})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc)})

	def _api_multiagent_runtime_task(self, query: dict):
		try:
			values = query.get('task_id', [])
			task_id = str(values[0] or '').strip() if isinstance(values, list) and values else ''
			if not task_id:
				return _json_response(self, 400, {'ok': False, 'error': 'task_id_required'})
			bundle = _load_multiagent_runtime_bundle(task_id)
			return _json_response(self, 200, {'ok': any(bundle.values()), 'task_id': task_id, 'runtime': bundle})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc)})

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
		context = data.get('context', {})
		if not isinstance(messages, list) or not messages:
			return _json_response(self, 400, {'ok': False, 'error': 'messages_required'})
		if not config['api_key']:
			return _json_response(self, 200, {'ok': False, 'error': 'apiKey不能为空'})
		try:
			last_user_message = ''
			for m in reversed(messages):
				if isinstance(m, dict) and m.get('role') == 'user':
					last_user_message = str(m.get('content', ''))
					break
					
			payload_data = {
				'user_goal': last_user_message,
				'messages': messages,
				'config': config,
				'context': context,
				'host': context.get('host', '127.0.0.1') if context else '127.0.0.1',
				'port': context.get('port', 9988) if context else 9988
			}
			runtime = _build_multiagent_execution(payload_data)
			outputs = runtime.get('outputs', {})
			commands = outputs.get('runtime_commands', [])
			reply = outputs.get('final_report', {}).get('summary', '多智能体执行完成')
			
			return _json_response(self, 200, {'ok': True, 'reply': reply, 'commands': commands, 'collaboration': runtime})
		except error.HTTPError as exc:
			raw = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
			return _json_response(self, 200, {'ok': False, 'error': f'HTTP {exc.code}: {raw}'})
		except Exception as exc:
			return _json_response(self, 200, {'ok': False, 'error': str(exc)})

	def _api_model_chat_stream(self, data: dict):
		config = _build_provider_config(data.get('config', {}))
		messages = data.get('messages', [])
		context = data.get('context', {})
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
			_thread_local.emit = emit
			
			last_user_message = ''
			for m in reversed(messages):
				if isinstance(m, dict) and m.get('role') == 'user':
					last_user_message = str(m.get('content', ''))
					break
					
			payload_data = {
				'user_goal': last_user_message,
				'messages': messages,
				'config': config,
				'context': context,
				'host': context.get('host', '127.0.0.1') if context else '127.0.0.1',
				'port': context.get('port', 9988) if context else 9988
			}
			runtime = _build_multiagent_execution(payload_data)
			
			outputs = runtime.get('outputs', {})
			commands = outputs.get('runtime_commands', [])
			reply = outputs.get('final_report', {}).get('summary', '多智能体执行完成')
			
			emit('done', {
				'reply': reply,
				'commands': commands,
				'collaboration': runtime
			})
		except error.HTTPError as exc:
			raw = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
			emit('error', {'message': f'HTTP {exc.code}: {raw}'})
		except Exception as exc:
			emit('error', {'message': str(exc)})
		finally:
			_thread_local.emit = None

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
