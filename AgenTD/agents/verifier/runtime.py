def build_validation_state_brief(task_brief: dict, execution_result: dict, data: dict, context: dict):
	host = str(data.get('host') or context.get('DEFAULT_TD_HOST'))
	port = int(data.get('port') or context.get('DEFAULT_TD_PORT'))
	timeout_sec = int(data.get('timeout') or context.get('DEFAULT_TIMEOUT'))
	secret_agent_path = str(data.get('secret_agent_path') or '/SecretAgent')
	should_refresh = bool(execution_result.get('executed_commands')) or bool(data.get('refresh_validation_state', False))
	if should_refresh:
		try:
			context['send_td_command']({
				'cmd': 'refresh_project_state',
				'secret_agent_path': secret_agent_path
			}, host, port, timeout_sec)
		except Exception:
			pass
	framework_forest, _ = context['load_project_scan_file'](context['DEFAULT_FRAMEWORK_FILE'])
	project_summary = context['build_project_summary']()
	non_default_nodes = []
	for item in project_summary.get('non_default_nodes', []):
		label = context['label_node_summary'](item)
		if label:
			non_default_nodes.append(label)
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'summary': {
			'top_level_nodes': project_summary.get('top_level_nodes', []),
			'relevant_nodes': context['build_relevant_nodes'](task_brief.get('goal', ''), project_summary),
			'key_connections': context['collect_framework_connections_summary'](framework_forest),
			'non_default_nodes': non_default_nodes[:40]
		},
		'evidence_files': [context['DEFAULT_INFORMATION_FILE'], context['DEFAULT_FRAMEWORK_FILE']],
		'executed_commands': [str(item) for item in execution_result.get('executed_commands', []) if str(item).strip()],
		'next_action': 'return_to_verifier'
	}


def build_validation_brief(task_brief: dict, state_brief: dict, validation_state_brief: dict, compatibility_brief: dict, edit_plan_brief: dict, execution_result: dict, context: dict):
	if compatibility_brief and compatibility_brief.get('rejected_choices'):
		return {
			'task_id': task_brief['task_id'],
			'status': 'fail',
			'result_type': 'compatibility_failure',
			'verified_changes': [],
			'remaining_issues': [item.get('entity', '') for item in compatibility_brief.get('rejected_choices', []) if isinstance(item, dict)],
			'retry_target': 'agent-2-kb-consultant',
			'next_action': 'dispatch_retry_to_agent_2'
		}
	if execution_result.get('status') == 'failed':
		remaining_issues = execution_result.get('runtime_notes', [])
		bootstrap_issue = context['detect_runtime_bootstrap_issue'](remaining_issues)
		if bootstrap_issue:
			remaining_issues = list(remaining_issues) + [bootstrap_issue]
		return {
			'task_id': task_brief['task_id'],
			'status': 'fail',
			'result_type': 'execution_failure',
			'verified_changes': execution_result.get('executed_commands', []),
			'remaining_issues': remaining_issues,
			'retry_target': 'agent-3-framework-editor',
			'next_action': 'dispatch_retry_to_agent_3'
		}
	if task_brief.get('requires_edit') and not edit_plan_brief.get('framework_changes'):
		return {
			'task_id': task_brief['task_id'],
			'status': 'fail',
			'result_type': 'framework_failure',
			'verified_changes': [],
			'remaining_issues': ['未生成 framework_changes'],
			'retry_target': 'agent-3-framework-editor',
			'next_action': 'dispatch_retry_to_agent_3'
		}
	verified_changes, remaining_issues = context['verify_framework_changes_against_project'](edit_plan_brief)
	if execution_result.get('executed_commands') and any('refresh_project_state:' in str(item) for item in execution_result.get('runtime_notes', [])):
		if remaining_issues:
			return {
				'task_id': task_brief['task_id'],
				'status': 'fail',
				'result_type': 'goal_mismatch',
				'verified_changes': verified_changes,
				'remaining_issues': remaining_issues,
				'retry_target': 'agent-3-framework-editor',
				'next_action': 'dispatch_retry_to_agent_3'
			}
	if not verified_changes:
		verified_changes = validation_state_brief.get('summary', {}).get('relevant_nodes', [])[:10]
	if not verified_changes:
		verified_changes = state_brief.get('summary', {}).get('relevant_nodes', [])[:10]
	return {
		'task_id': task_brief['task_id'],
		'status': 'pass',
		'result_type': 'goal_match',
		'verified_changes': verified_changes,
		'remaining_issues': [],
		'retry_target': '',
		'next_action': 'return_to_orchestrator'
	}


def build_retry_request(validation_brief: dict):
	if str(validation_brief.get('status') or '') != 'fail':
		return None
	failure_type = str(validation_brief.get('result_type') or 'goal_mismatch')
	retry_target = str(validation_brief.get('retry_target') or 'agent-0-orchestrator')
	remaining = validation_brief.get('remaining_issues', [])
	if not isinstance(remaining, list):
		remaining = []
	return {
		'task_id': validation_brief.get('task_id', ''),
		'message_type': 'retry_request',
		'failure_type': failure_type,
		'failure_summary': '；'.join([str(item) for item in remaining if str(item).strip()]) or failure_type,
		'retry_target': retry_target,
		'suggested_fix': '根据失败类型回到目标 agent，补充兼容性或框架调整后重试。',
		'next_action': f'dispatch_retry_to_{retry_target}'
	}
