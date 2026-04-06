def build_compatibility_brief(task_brief: dict, state_brief: dict, candidate_plan: dict, context: dict):
	target_version = str(task_brief.get('constraints', {}).get('target_version') or '').strip()
	allow_experimental = bool(task_brief.get('constraints', {}).get('allow_experimental'))
	family_records = context['build_family_records']()
	requested_families = []
	if isinstance(candidate_plan, dict):
		for family in candidate_plan.get('candidate_families', []):
			text = str(family or '').strip().upper()
			if text and text not in requested_families:
				requested_families.append(text)
	if not requested_families:
		requested_families = context['detect_goal_families'](task_brief.get('goal', ''))
	if not requested_families:
		for node_text in state_brief.get('summary', {}).get('relevant_nodes', []):
			low = str(node_text).lower()
			for family in ('POP', 'TOP', 'CHOP', 'SOP', 'COMP', 'DAT', 'MAT'):
				if family.lower() in low and family not in requested_families:
					requested_families.append(family)
	compatible_choices = []
	rejected_choices = []
	evidence = []
	target_key = context['version_key'](target_version)
	target_is_experimental = 'experimental' in target_version.lower()
	for family in requested_families:
		record = family_records.get(family, {})
		introduced_key = context['version_key'](str(record.get('introduced_in_build') or ''))
		introduced_channel = str(record.get('introduced_channel') or 'stable').strip().lower()
		is_compatible = True
		if introduced_key != (0, 0) and target_key != (0, 0):
			is_compatible = introduced_key <= target_key
		if introduced_channel == 'experimental' and not (allow_experimental or target_is_experimental):
			is_compatible = False
		reason_parts = []
		if record.get('introduced_in_build'):
			reason_parts.append(f'首次引入于 {record.get("introduced_in_build")}')
		if introduced_channel:
			reason_parts.append(f'渠道 {introduced_channel}')
		if not reason_parts:
			reason_parts.append('知识库未给出版本门槛')
		target = compatible_choices if is_compatible else rejected_choices
		target.append({
			'entity': family,
			'reason': '，'.join(reason_parts)
		})
		evidence.append({
			'source': str(record.get('source_title') or 'family_compatibility.jsonl'),
			'key': family
		})
	version_assumption = target_version or 'current_project_runtime'
	if rejected_choices:
		recommendation = '当前目标涉及的 OP 家族存在版本或渠道限制，建议先调整版本假设或改用兼容方案。'
		next_action = 'dispatch_retry_to_agent_2'
	else:
		if compatible_choices:
			recommendation = '目标涉及的 OP 家族在当前版本假设下可用，可以继续进入编辑或验证阶段。'
		else:
			recommendation = '当前目标未命中需要知识库拦截的明确 OP 家族，可按现有扫描结果继续。'
		next_action = 'dispatch_to_agent_3' if task_brief.get('requires_edit') else 'dispatch_to_agent_4'
	return {
		'task_id': task_brief['task_id'],
		'scope': task_brief['scope'],
		'version_assumption': version_assumption,
		'compatible_choices': compatible_choices,
		'rejected_choices': rejected_choices,
		'evidence': evidence,
		'recommendation': recommendation,
		'next_action': next_action
	}


def build_retry_compatibility_brief(task_brief: dict, state_brief: dict, candidate_plan: dict, retry_request: dict, context: dict):
	result = build_compatibility_brief(task_brief, state_brief, candidate_plan, context)
	failure_summary = str(retry_request.get('failure_summary') or '').strip()
	if failure_summary:
		evidence = list(result.get('evidence', []))
		evidence.append({
			'source': 'retry_request',
			'key': failure_summary[:120]
		})
		result['evidence'] = evidence
		result['recommendation'] = (str(result.get('recommendation') or '').strip() + ' 失败复核: ' + failure_summary).strip()
	return result
