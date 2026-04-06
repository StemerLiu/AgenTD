def build_project_state_brief(task_brief: dict, data: dict, context: dict):
	host = str(data.get('host') or context.get('DEFAULT_TD_HOST'))
	port = int(data.get('port') or context.get('DEFAULT_TD_PORT'))
	timeout_sec = int(data.get('timeout') or context.get('DEFAULT_TIMEOUT'))
	secret_agent_path = str(data.get('secret_agent_path') or '/SecretAgent')
	refresh = bool(data.get('refresh', False))
	if refresh:
		context['send_td_command']({
			'cmd': 'refresh_project_state',
			'secret_agent_path': secret_agent_path
		}, host, port, timeout_sec)
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
		'next_action': 'return_to_orchestrator' if task_brief.get('task_type') == 'read' else ('dispatch_to_agent_2' if task_brief.get('requires_kb_check') else ('dispatch_to_agent_3' if task_brief.get('requires_edit') else 'dispatch_to_agent_4'))
	}
