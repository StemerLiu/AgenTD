def build_task_brief(data: dict, routing_config: dict, context: dict):
	user_goal = str(data.get('user_goal') or data.get('goal') or '').strip()
	if not user_goal:
		raise ValueError('user_goal_required')
	task_type = context['normalize_task_type'](data.get('task_type', ''), user_goal)
	constraints = data.get('constraints', {})
	if not isinstance(constraints, dict):
		constraints = {}
	target_version = str(constraints.get('target_version') or '').strip()
	allow_experimental = bool(constraints.get('allow_experimental', False) or ('experimental' in target_version.lower()))
	task_defaults = routing_config.get('task_defaults', {}).get(task_type, {})
	seed_text = user_goal + '|' + str(data.get('scope') or '')
	seed_value = 0
	for idx, ch in enumerate(seed_text):
		seed_value = (seed_value + ((idx + 1) * ord(ch))) % 100000000
	task_id = str(data.get('task_id') or '').strip() or f'td-{task_type}-{seed_value:08d}'
	requires_state_read = bool(task_defaults.get('requires_state_read', True))
	requires_kb_check = context['should_require_kb'](task_type, user_goal, allow_experimental, routing_config)
	if 'requires_kb_check' in data:
		requires_kb_check = bool(data.get('requires_kb_check'))
	requires_edit = bool(task_defaults.get('requires_edit', task_type in ('create', 'modify', 'repair')))
	if 'requires_edit' in data:
		requires_edit = bool(data.get('requires_edit'))
	if task_type in ('read', 'verify'):
		requires_edit = False
	scope = str(data.get('scope') or routing_config.get('default_scope') or '/project1')
	priority = str(data.get('priority') or routing_config.get('default_priority') or 'high')
	return {
		'task_id': task_id,
		'task_type': task_type,
		'goal': user_goal,
		'scope': scope,
		'priority': priority,
		'constraints': {
			'target_version': target_version,
			'allow_experimental': allow_experimental,
			'allow_rebuild': bool(constraints.get('allow_rebuild', False))
		},
		'requires_state_read': requires_state_read,
		'requires_kb_check': requires_kb_check,
		'requires_edit': requires_edit,
		'next_action': 'dispatch_to_agent_1' if requires_state_read else 'dispatch_to_agent_0'
	}


def build_final_report(task_brief: dict, validation_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, context: dict):
	artifacts = [context['DEFAULT_INFORMATION_FILE'], context['DEFAULT_FRAMEWORK_FILE']]
	follow_up = []
	bootstrap_issue = context['detect_runtime_bootstrap_issue'](validation_brief.get('remaining_issues', []))
	if retry_request:
		follow_up.append(f'重试目标: {retry_request.get("retry_target", "")}')
		follow_up.append(f'失败摘要: {retry_request.get("failure_summary", "")}')
		if bootstrap_issue:
			follow_up.append(bootstrap_issue)
	elif compatibility_brief.get('compatible_choices'):
		follow_up.append('可继续把本次 brief 流转接到真实技能执行器')
	if state_brief.get('summary', {}).get('relevant_nodes'):
		follow_up.append('后续可基于 relevant_nodes 进一步缩小上下文范围')
	status = 'completed' if validation_brief.get('status') == 'pass' else 'failed'
	return {
		'task_id': task_brief['task_id'],
		'status': status,
		'summary': '多智能体最小执行流已完成' if status == 'completed' else '多智能体最小执行流完成，但存在需要回退的失败项',
		'artifacts': artifacts,
		'follow_up': follow_up
	}


def build_read_only_final_report(task_brief: dict, state_brief: dict, context: dict):
	relevant_nodes = state_brief.get('summary', {}).get('relevant_nodes', [])
	top_level_nodes = state_brief.get('summary', {}).get('top_level_nodes', [])
	key_connections = state_brief.get('summary', {}).get('key_connections', [])
	follow_up = []
	if relevant_nodes:
		follow_up.append('相关节点: ' + '；'.join([str(item) for item in relevant_nodes[:8]]))
	if top_level_nodes:
		follow_up.append('顶层节点数: ' + str(len(top_level_nodes)))
	if key_connections:
		follow_up.append('关键连接数: ' + str(len(key_connections)))
	follow_up.append('可继续基于 relevant_nodes 缩小后续编辑上下文')
	return {
		'task_id': task_brief['task_id'],
		'status': 'completed',
		'summary': '只读分析已完成，当前工程状态已返回给 Orchestrator。',
		'artifacts': list(state_brief.get('evidence_files', []) or [context['DEFAULT_INFORMATION_FILE'], context['DEFAULT_FRAMEWORK_FILE']]),
		'follow_up': follow_up
	}


def build_read_only_completion(task_brief: dict, state_brief: dict, context: dict):
	final_report = build_read_only_final_report(task_brief, state_brief, context)
	return {
		'final_report': final_report,
		'final_message': build_phase_message_spec('agent-0-orchestrator', 'user', 'final_report', final_report, 'complete')
	}


def build_read_runtime_block(task_brief: dict, state_brief: dict, context: dict):
	completion = build_read_only_completion(task_brief, state_brief, context)
	return {
		'outputs': {
			'final_report': completion.get('final_report', {})
		},
		'final_message': completion.get('final_message', {})
	}


def build_agent_envelope(task_brief: dict, message_index: int, from_agent: str, to_agent: str, message_type: str, payload: dict, next_action: str):
	return {
		'task_id': task_brief['task_id'],
		'message_id': f'{task_brief["task_id"]}-msg-{message_index:04d}',
		'from_agent': from_agent,
		'to_agent': to_agent,
		'message_type': message_type,
		'scope': task_brief['scope'],
		'priority': task_brief['priority'],
		'payload': payload,
		'next_action': next_action
	}


def build_phase_message_spec(from_agent: str, to_agent: str, message_type: str, payload: dict, next_action: str):
	return {
		'from_agent': str(from_agent or '').strip(),
		'to_agent': str(to_agent or '').strip(),
		'message_type': str(message_type or '').strip(),
		'payload': payload if isinstance(payload, dict) else {},
		'next_action': str(next_action or '').strip()
	}


def append_agent_message(messages: list, task_brief: dict, message_index: int, from_agent: str, to_agent: str, message_type: str, payload: dict, next_action: str):
	if not isinstance(messages, list):
		messages = []
	envelope = build_agent_envelope(task_brief, message_index, from_agent, to_agent, message_type, payload, next_action)
	messages.append(envelope)
	return {
		'messages': messages,
		'message_index': int(message_index) + 1,
		'envelope': envelope
	}


def append_phase_message(messages: list, task_brief: dict, message_index: int, message_spec: dict):
	spec = message_spec if isinstance(message_spec, dict) else {}
	return append_agent_message(
		messages,
		task_brief,
		message_index,
		spec.get('from_agent', ''),
		spec.get('to_agent', ''),
		spec.get('message_type', ''),
		spec.get('payload', {}),
		spec.get('next_action', '')
	)


def decide_next_agent_after_state(task_brief: dict):
	if task_brief.get('task_type') == 'read':
		return 'agent-0-orchestrator'
	if task_brief.get('requires_kb_check'):
		return 'agent-2-kb-consultant'
	if task_brief.get('requires_edit'):
		return 'agent-3-framework-editor'
	return 'agent-4-verifier'


def decide_next_agent_after_compatibility(task_brief: dict, compatibility_brief: dict):
	if task_brief.get('requires_edit') and not compatibility_brief.get('rejected_choices'):
		return 'agent-3-framework-editor'
	return 'agent-4-verifier'


def build_fallback_state_brief(task_brief: dict):
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'summary': {
			'top_level_nodes': [],
			'relevant_nodes': [],
			'key_connections': [],
			'non_default_nodes': []
		},
		'evidence_files': [],
		'next_action': 'dispatch_to_agent_4'
	}


def build_default_edit_plan_brief(task_brief: dict):
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'edit_goal': task_brief.get('goal', ''),
		'framework_changes': [],
		'execution_chain': [],
		'risk_points': [],
		'next_action': 'dispatch_to_agent_4'
	}


def build_default_compatibility_brief(task_brief: dict):
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'version_assumption': str(task_brief.get('constraints', {}).get('target_version') or 'current_project_runtime'),
		'compatible_choices': [],
		'rejected_choices': [],
		'evidence': [],
		'recommendation': '当前任务不需要 KB 护栏。',
		'next_action': 'dispatch_to_agent_3' if task_brief.get('requires_edit') else 'dispatch_to_agent_4'
	}


def build_execution_brief_seed(task_brief: dict):
	return {
		'state_brief': None,
		'validation_state_brief': build_fallback_state_brief(task_brief),
		'candidate_plan': None,
		'compatibility_brief': None,
		'edit_plan_brief': build_default_edit_plan_brief(task_brief)
	}


def build_state_read_phase(task_brief: dict, state_brief: dict):
	next_agent = decide_next_agent_after_state(task_brief)
	return {
		'state_message': build_phase_message_spec(
			'agent-1-state-reader',
			next_agent,
			'project_state_brief',
			state_brief,
			state_brief.get('next_action', 'return_to_orchestrator')
		)
	}


def build_state_phase_block(task_brief: dict, state_brief: dict):
	phase = build_state_read_phase(task_brief, state_brief)
	return {
		'outputs': {
			'project_state_brief': state_brief if isinstance(state_brief, dict) else {}
		},
		'state_message': phase.get('state_message', {})
	}


def build_candidate_compatibility_phase(task_brief: dict, candidate_plan: dict, compatibility_brief: dict):
	next_agent = decide_next_agent_after_compatibility(task_brief, compatibility_brief)
	return {
		'candidate_message': build_phase_message_spec(
			'agent-0-orchestrator',
			'agent-2-kb-consultant',
			'candidate_plan',
			candidate_plan,
			candidate_plan.get('next_action', 'dispatch_to_agent_2')
		),
		'compatibility_message': build_phase_message_spec(
			'agent-2-kb-consultant',
			next_agent,
			'compatibility_brief',
			compatibility_brief,
			compatibility_brief.get('next_action', 'return_to_orchestrator')
		)
	}


def build_kb_phase_block(task_brief: dict, candidate_plan: dict, compatibility_brief: dict):
	phase = build_candidate_compatibility_phase(task_brief, candidate_plan, compatibility_brief)
	return {
		'outputs': {
			'candidate_plan': candidate_plan if isinstance(candidate_plan, dict) else {},
			'compatibility_brief': compatibility_brief if isinstance(compatibility_brief, dict) else {}
		},
		'candidate_message': phase.get('candidate_message', {}),
		'compatibility_message': phase.get('compatibility_message', {})
	}


def build_execution_state(plan: dict):
	task_brief = plan.get('task_brief', {}) if isinstance(plan, dict) else {}
	envelope = plan.get('envelope', {}) if isinstance(plan, dict) else {}
	return {
		'messages': [envelope] if isinstance(envelope, dict) and envelope else [],
		'outputs': {
			'task_brief': task_brief
		},
		'message_index': 2
	}


def build_runtime_payload(plan: dict, messages: list, outputs: dict):
	if not isinstance(messages, list):
		messages = []
	if not isinstance(outputs, dict):
		outputs = {}
	return {
		'plan': plan if isinstance(plan, dict) else {},
		'messages': messages,
		'outputs': outputs
	}


def build_execution_bundle_outputs(execution_bundle: dict):
	if not isinstance(execution_bundle, dict):
		execution_bundle = {}
	execution_result = execution_bundle.get('execution_result', {})
	runtime_commands = execution_bundle.get('runtime_commands', [])
	if not isinstance(execution_result, dict):
		execution_result = {}
	if not isinstance(runtime_commands, list):
		runtime_commands = []
	return {
		'execution_result': execution_result,
		'runtime_commands': runtime_commands
	}


def build_auto_retry_policy(data: dict):
	if not isinstance(data, dict):
		data = {}
	max_auto_retries = int(data.get('max_auto_retries', 1) or 0)
	if max_auto_retries < 0:
		max_auto_retries = 0
	return {
		'auto_retry_enabled': bool(data.get('auto_retry', True)),
		'max_auto_retries': max_auto_retries
	}


def build_final_report_completion(task_brief: dict, validation_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, context: dict):
	final_report = build_final_report(task_brief, validation_brief, state_brief, compatibility_brief, retry_request, context)
	return {
		'final_report': final_report,
		'final_message': build_phase_message_spec('agent-0-orchestrator', 'user', 'final_report', final_report, 'complete'),
		'clear_retry_request': not bool(retry_request)
	}


def build_finalization_block(task_brief: dict, validation_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, context: dict):
	completion = build_final_report_completion(task_brief, validation_brief, state_brief, compatibility_brief, retry_request, context)
	return {
		'outputs': {
			'final_report': completion.get('final_report', {})
		},
		'final_message': completion.get('final_message', {}),
		'clear_retry_request': bool(completion.get('clear_retry_request'))
	}


def build_retry_compatibility_failure(task_brief: dict, compatibility_brief: dict):
	return {
		'task_id': task_brief['task_id'],
		'status': 'fail',
		'result_type': 'compatibility_failure',
		'verified_changes': [],
		'remaining_issues': [item.get('entity', '') for item in compatibility_brief.get('rejected_choices', []) if isinstance(item, dict)],
		'retry_target': 'agent-2-kb-consultant',
		'next_action': 'dispatch_retry_to_agent_2'
	}


def build_retry_cycle_completion(validation_state_brief: dict, candidate_plan: dict, compatibility_brief: dict, edit_plan_brief: dict, validation_brief: dict, retry_request: dict, message_index: int):
	return {
		'validation_state_brief': validation_state_brief if isinstance(validation_state_brief, dict) else {},
		'candidate_plan': candidate_plan if isinstance(candidate_plan, dict) else candidate_plan,
		'compatibility_brief': compatibility_brief if isinstance(compatibility_brief, dict) else compatibility_brief,
		'edit_plan_brief': edit_plan_brief if isinstance(edit_plan_brief, dict) else edit_plan_brief,
		'validation_brief': validation_brief if isinstance(validation_brief, dict) else {},
		'retry_request': retry_request if isinstance(retry_request, dict) else retry_request,
		'message_index': int(message_index),
		'clear_retry_request': not bool(retry_request)
	}


def build_retry_history(history: list, retry_request: dict):
	items = list(history) if isinstance(history, list) else []
	request = retry_request if isinstance(retry_request, dict) else {}
	items.append({
		'retry_target': str(request.get('retry_target') or '').strip(),
		'failure_type': str(request.get('failure_type') or ''),
		'failure_summary': str(request.get('failure_summary') or '')
	})
	return items


def build_multiagent_output_patch(compatibility_brief: dict, edit_plan_brief: dict, execution_result: dict, runtime_commands: list, validation_state_brief: dict, validation_brief: dict, retry_request: dict):
	patch = {}
	if isinstance(compatibility_brief, dict) and compatibility_brief:
		patch['compatibility_brief'] = compatibility_brief
	if isinstance(edit_plan_brief, dict) and edit_plan_brief:
		patch['edit_plan_brief'] = edit_plan_brief
	if isinstance(execution_result, dict) and execution_result:
		patch['execution_result'] = execution_result
	if isinstance(runtime_commands, list):
		patch['runtime_commands'] = runtime_commands
	if isinstance(validation_state_brief, dict) and validation_state_brief:
		patch['validation_state_brief'] = validation_state_brief
	if isinstance(validation_brief, dict) and validation_brief:
		patch['validation_brief'] = validation_brief
	if isinstance(retry_request, dict) and retry_request:
		patch['retry_request'] = retry_request
	return {
		'outputs': patch,
		'clear_retry_request': not bool(retry_request)
	}


def build_retry_compatibility_phase(task_brief: dict, compatibility_brief: dict):
	next_agent = decide_next_agent_after_compatibility(task_brief, compatibility_brief)
	validation_brief = build_retry_compatibility_failure(task_brief, compatibility_brief) if compatibility_brief.get('rejected_choices') else None
	return {
		'compatibility_message': build_phase_message_spec(
			'agent-2-kb-consultant',
			next_agent,
			'compatibility_brief',
			compatibility_brief,
			compatibility_brief.get('next_action', 'return_to_orchestrator')
		),
		'validation_brief': validation_brief,
		'validation_message': build_phase_message_spec(
			'agent-4-verifier',
			'agent-0-orchestrator',
			'validation_brief',
			validation_brief,
			validation_brief.get('next_action', 'return_to_orchestrator')
		) if isinstance(validation_brief, dict) and validation_brief else None
	}


def build_execution_validation_phase(task_brief: dict, execution_result: dict, validation_brief: dict):
	source_agent = decide_execution_result_source_agent(task_brief)
	return {
		'execution_message': build_phase_message_spec(
			source_agent,
			'agent-4-verifier',
			'execution_result',
			execution_result,
			execution_result.get('next_action', 'return_to_orchestrator')
		),
		'validation_message': build_phase_message_spec(
			'agent-4-verifier',
			'agent-0-orchestrator',
			'validation_brief',
			validation_brief,
			validation_brief.get('next_action', 'return_to_orchestrator')
		)
	}


def build_retry_request_phase(retry_request: dict):
	if not isinstance(retry_request, dict) or not retry_request:
		return {
			'retry_message': None,
			'clear_retry_request': True
		}
	return {
		'retry_message': build_phase_message_spec(
			'agent-4-verifier',
			retry_request.get('retry_target', 'agent-0-orchestrator'),
			'retry_request',
			retry_request,
			retry_request.get('next_action', 'return_to_orchestrator')
		),
		'clear_retry_request': False
	}


def decide_execution_result_source_agent(task_brief: dict):
	if task_brief.get('requires_edit'):
		return 'agent-3-framework-editor'
	return 'agent-1-state-reader'


def build_route_agent_ids(task_brief: dict):
	steps = []
	if task_brief.get('requires_state_read'):
		steps.append('agent-1-state-reader')
	if task_brief.get('requires_kb_check'):
		steps.append('agent-2-kb-consultant')
	if task_brief.get('requires_edit'):
		steps.append('agent-3-framework-editor')
	if task_brief.get('task_type') != 'read':
		steps.append('agent-4-verifier')
	return steps


def build_candidate_plan(task_brief: dict, state_brief: dict, context: dict):
	candidate_nodes = list(state_brief.get('summary', {}).get('relevant_nodes', []))
	if not candidate_nodes:
		for item in state_brief.get('summary', {}).get('top_level_nodes', []):
			if not isinstance(item, dict):
				continue
			path = str(item.get('path') or '').strip()
			if path:
				candidate_nodes.append(path)
	requested_families = context['detect_goal_families'](task_brief.get('goal', ''))
	if not requested_families:
		for item in candidate_nodes:
			low = str(item).lower()
			for family in ('POP', 'TOP', 'CHOP', 'SOP', 'COMP', 'DAT', 'MAT'):
				if family.lower() in low and family not in requested_families:
					requested_families.append(family)
	strategy = '基于当前相关节点与目标家族做兼容性筛查'
	if not candidate_nodes:
		strategy = '当前扫描未命中明显候选节点，优先按目标描述推断候选家族'
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'goal': task_brief.get('goal', ''),
		'candidate_nodes': candidate_nodes[:20],
		'candidate_families': requested_families,
		'strategy': strategy,
		'next_action': 'dispatch_to_agent_2'
	}


def build_route_entry(agent_id: str, descriptor: dict):
	if not isinstance(descriptor, dict):
		descriptor = {}
	return {
		'agent_id': str(agent_id or '').strip(),
		'role': descriptor.get('role', ''),
		'skill': descriptor.get('skill', ''),
		'produces': descriptor.get('produces', []),
		'assets': descriptor.get('assets', {})
	}


def build_agent_registry_summary(registry: dict):
	if not isinstance(registry, dict):
		registry = {}
	return {
		agent_id: {
			'role': descriptor.get('role', ''),
			'skill': descriptor.get('skill', ''),
			'produces': descriptor.get('produces', []),
			'consumes': descriptor.get('consumes', []),
			'assets': descriptor.get('assets', {})
		}
		for agent_id, descriptor in registry.items()
		if isinstance(descriptor, dict)
	}


def build_route_plan_payload(orchestrator_descriptor: dict, task_brief: dict, envelope: dict, route: list, registry_summary: dict, routing_config: dict):
	if not isinstance(orchestrator_descriptor, dict):
		orchestrator_descriptor = {}
	if not isinstance(route, list):
		route = []
	if not isinstance(registry_summary, dict):
		registry_summary = {}
	if not isinstance(routing_config, dict):
		routing_config = {}
	return {
		'orchestrator': orchestrator_descriptor.get('contract', {}),
		'orchestrator_assets': orchestrator_descriptor.get('assets', {}),
		'task_brief': task_brief if isinstance(task_brief, dict) else {},
		'envelope': envelope if isinstance(envelope, dict) else {},
		'route': route,
		'contracts_loaded': sorted(list(registry_summary.keys())),
		'agent_registry': registry_summary,
		'routing_config': {
			'agent_order': routing_config.get('agent_order', []),
			'default_scope': routing_config.get('default_scope', '/project1')
		}
	}
