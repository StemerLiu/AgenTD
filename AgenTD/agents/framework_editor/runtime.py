import os
import json

def build_edit_plan_brief(task_brief: dict, state_brief: dict, compatibility_brief: dict, data: dict, context: dict, retry_request: dict = None):
	raw_changes = data.get('framework_changes')
	if not raw_changes:
		prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'system.txt')
		with open(prompt_path, 'r', encoding='utf-8') as f:
			system_prompt = f.read().strip()
		
		content_obj = {
			"task_brief": task_brief,
			"state_brief": state_brief,
			"compatibility_brief": compatibility_brief
		}
		if retry_request:
			content_obj["retry_request"] = retry_request
			
		user_content = json.dumps(content_obj, ensure_ascii=False, indent=2)
		
		try:
			_, llm_data = context['call_agent_json'](system_prompt, user_content, data.get('config', {}), 90)
			raw_changes = llm_data.get('framework_changes', []) if isinstance(llm_data, dict) else []
		except Exception as e:
			print(f"Agent-3 Error: {e}")
			raw_changes = []

	framework_changes = []
	if isinstance(raw_changes, list):
		for item in raw_changes:
			norm = context['normalize_framework_change'](item, task_brief.get('scope', '/project1'))
			if norm:
				framework_changes.append(norm)
	if not framework_changes:
		default_action = 'create' if task_brief.get('task_type') == 'create' else 'modify'
		framework_changes.append({
			'path': task_brief.get('scope', '/project1'),
			'type': 'baseCOMP',
			'action': default_action
		})
	risk_points = []
	if compatibility_brief.get('rejected_choices'):
		risk_points.append('知识库判定存在版本或渠道不兼容项')
	if not state_brief.get('summary', {}).get('relevant_nodes'):
		risk_points.append('扫描结果中没有明显命中目标的相关节点')
	if task_brief.get('constraints', {}).get('allow_rebuild'):
		risk_points.append('任务允许重建，执行前需要确认清空范围')
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'edit_goal': task_brief.get('goal', ''),
		'framework_changes': framework_changes,
		'execution_chain': ['write_framework_json', 'reload', 'replicate_framework', 'save_project'],
		'risk_points': risk_points,
		'next_action': 'dispatch_to_agent_4'
	}


def build_execution_result(task_brief: dict, edit_plan_brief: dict, data: dict, context: dict):
	if not task_brief.get('requires_edit'):
		return {
			'execution_result': {
				'task_id': task_brief['task_id'],
				'status': 'executed',
				'executed_commands': [],
				'runtime_notes': ['当前任务不需要编辑执行'],
				'next_action': 'dispatch_to_agent_4'
			},
			'runtime_commands': []
		}
	execute_commands = bool(data.get('execute_commands', False))
	runtime_commands = context['build_runtime_command_chain'](task_brief, edit_plan_brief, data)
	if not execute_commands:
		return {
			'execution_result': {
				'task_id': task_brief['task_id'],
				'status': 'executed',
				'executed_commands': [str(item.get('cmd') or '') for item in runtime_commands],
				'runtime_notes': ['当前为最小执行流，未实际下发 TouchDesigner 命令'],
				'next_action': 'dispatch_to_agent_4'
			},
			'runtime_commands': runtime_commands
		}
	host = str(data.get('host') or context.get('DEFAULT_TD_HOST'))
	port = int(data.get('port') or context.get('DEFAULT_TD_PORT'))
	timeout_sec = int(data.get('timeout') or context.get('DEFAULT_TIMEOUT'))
	status, executed_commands, runtime_notes = context['execute_runtime_commands'](runtime_commands, host, port, timeout_sec)
	if status == 'executed':
		refresh_response, refresh_ok = context['refresh_project_state_after_execution'](data)
		runtime_notes.append(f'refresh_project_state:{refresh_response}')
		if not refresh_ok:
			status = 'failed'
	return {
		'execution_result': {
			'task_id': task_brief['task_id'],
			'status': status,
			'executed_commands': executed_commands,
			'runtime_notes': runtime_notes,
			'next_action': 'dispatch_to_agent_4'
		},
		'runtime_commands': runtime_commands
	}


def build_retry_edit_plan_brief(task_brief: dict, state_brief: dict, compatibility_brief: dict, retry_request: dict, data: dict, context: dict):
	result = build_edit_plan_brief(task_brief, state_brief, compatibility_brief, data, context, retry_request)
	risk_points = list(result.get('risk_points', []))
	failure_summary = str(retry_request.get('failure_summary') or '').strip()
	suggested_fix = str(retry_request.get('suggested_fix') or '').strip()
	if failure_summary:
		risk_points.append('重试原因: ' + failure_summary)
	if suggested_fix:
		risk_points.append('修复建议: ' + suggested_fix)
	result['risk_points'] = risk_points
	return result
