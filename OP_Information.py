import json
import hashlib

def log_target_network_full(target_dat_name='OP_Information'):
	target_dat = op(target_dat_name)
	if not target_dat:
		print(f"Error: Text DAT '{target_dat_name}' not found inside {me.parent().name}.")
		return

	target_comp = me.parent().parent()
	if not target_comp:
		print("Error: No parent component found to scan.")
		return

	project1 = op('/project1')
	if not project1:
		print("Error: '/project1' not found.")
		return

	def to_rel_path(path_str):
		base = target_comp.path
		if base == '/':
			return path_str
		if path_str == base:
			return '.'
		prefix = base + '/'
		if path_str.startswith(prefix):
			return path_str[len(prefix):]
		return path_str

	def is_excluded(path_str):
		node_name = path_str.rsplit('/', 1)[-1] if '/' in path_str else path_str
		if '__XX__' in node_name:
			return True
		if path_str == '/project1':
			return False
		return not path_str.startswith('/project1/')

	def get_node_pos(o):
		x = 0
		y = 0
		try:
			x = int(o.nodeX)
		except:
			try:
				x = int(o.x)
			except:
				x = 0
		try:
			y = int(o.nodeY)
		except:
			try:
				y = int(o.y)
			except:
				y = 0
		return {'x': x, 'y': y}

	def get_display_render_state(o):
		def to_bool(val):
			try:
				if isinstance(val, bool):
					return val
			except:
				pass
			try:
				return bool(int(val))
			except:
				pass
			try:
				s = str(val).strip().lower()
				if s in ('true', 'on', '1'):
					return True
				if s in ('false', 'off', '0'):
					return False
			except:
				pass
			return None

		def read_flag(flag_name):
			try:
				raw = getattr(o, flag_name, None)
				if raw is not None and not callable(raw):
					v = to_bool(raw)
					if v is not None:
						return v
			except:
				pass
			try:
				par = getattr(o.par, flag_name, None)
				if par is not None:
					v = to_bool(par.val)
					if v is not None:
						return v
			except:
				pass
			try:
				par = getattr(o.par, flag_name.capitalize(), None)
				if par is not None:
					v = to_bool(par.val)
					if v is not None:
						return v
			except:
				pass
			return None

		def is_top_op():
			try:
				fam = str(getattr(o, 'family', ''))
				if fam.upper().endswith('TOP') or fam.upper() == 'TOP':
					return True
			except:
				pass
			try:
				tp = str(getattr(o, 'OPType', getattr(o, 'opType', ''))).lower()
				if tp.endswith('top') or 'top' in tp:
					return True
			except:
				pass
			return False

		state = {}
		flag_names = ['display', 'render', 'template', 'compare', 'pickable']
		if is_top_op():
			flag_names = [n for n in flag_names if n != 'render']
		for fn in flag_names:
			v = read_flag(fn)
			if v is not None:
				state[fn] = v
		return state

	def get_input_links(o):
		result = []
		connectors = []
		try:
			connectors = list(o.inputConnectors)
		except:
			connectors = []

		for i, c in enumerate(connectors):
			links = []
			try:
				for conn in c.connections:
					src_op = None
					try:
						src_op = conn.owner
					except:
						try:
							src_op = conn.OP
						except:
							src_op = None
					if src_op and hasattr(src_op, 'path'):
						src_path = src_op.path
						if not is_excluded(src_path):
							links.append(str(src_op.name))
			except:
				pass

			if not links:
				try:
					if i < len(o.inputs) and o.inputs[i]:
						src_op = o.inputs[i]
						src_path = src_op.path
						if not is_excluded(src_path):
							links.append(str(src_op.name))
				except:
					pass

			if links:
				links = sorted(set(links))
				result.append({
					'port': i,
					'links': links
				})
		return result

	def get_output_links(o):
		result = []
		connectors = []
		try:
			connectors = list(o.outputConnectors)
		except:
			connectors = []

		for i, c in enumerate(connectors):
			links = []
			try:
				for conn in c.connections:
					dst_op = None
					try:
						dst_op = conn.owner
					except:
						try:
							dst_op = conn.OP
						except:
							dst_op = None
					if dst_op and hasattr(dst_op, 'path'):
						dst_path = dst_op.path
						if not is_excluded(dst_path):
							links.append(str(dst_op.name))
			except:
				pass

			if links:
				links = sorted(set(links))
				result.append({
					'port': i,
					'links': links
				})
		return result

	def enrich_mode_info(par, param_info):
		mode_str = ''
		try:
			mode_str = str(par.mode)
		except:
			mode_str = ''

		if mode_str == 'ParMode.EXPRESSION':
			try:
				param_info['expr'] = str(par.expr)
			except:
				pass

		if mode_str == 'ParMode.BIND':
			bind_info = {}
			try:
				bind_expr = str(par.bindExpr)
				if bind_expr:
					bind_info['bindExpr'] = bind_expr
			except:
				pass
			try:
				bind_range = str(par.bindRange)
				if bind_range:
					bind_info['bindRange'] = bind_range
			except:
				pass
			try:
				bind_master = getattr(par, 'bindMaster', None)
				if callable(bind_master):
					bind_master = bind_master()
				if bind_master is not None:
					try:
						owner = getattr(bind_master, 'owner', None)
						pname = getattr(bind_master, 'name', None)
						if owner is not None and pname:
							bind_info['bindMaster'] = f"{owner.path}.par.{pname}"
						else:
							bind_info['bindMaster'] = bind_master.path
					except:
						bind_info['bindMaster'] = str(bind_master)
			except:
				pass
			if bind_info:
				param_info['bind'] = bind_info

	def strip_val_for_bind(param_info):
		try:
			mode_val = param_info.get('mode')
		except:
			mode_val = None
		if isinstance(mode_val, str):
			if mode_val == 'ParMode.BIND' and 'val' in param_info:
				param_info.pop('val', None)
			return
		if isinstance(mode_val, list):
			has_bind = False
			for m in mode_val:
				if str(m) == 'ParMode.BIND':
					has_bind = True
					break
			if has_bind and 'val' in param_info:
				param_info.pop('val', None)

	def get_params(o):
		parameters = {}
		params_list = []
		try:
			raw_pars = o.pars
			params_list = raw_pars() if callable(raw_pars) else raw_pars
		except:
			try:
				params_list = o.customPars
			except:
				params_list = []

		if not isinstance(params_list, (list, tuple)):
			params_list = []

		for p in params_list:
			try:
				page_name = p.page.name if p.page else 'Unknown'
				if page_name == 'Unknown':
					continue

				val_str = str(p.val)
				mode_str = ''
				try:
					mode_str = str(p.mode)
				except:
					mode_str = ''
				param_info = {
					'val': val_str,
					'mode': mode_str
				}
				enrich_mode_info(p, param_info)
				strip_val_for_bind(param_info)

				if page_name not in parameters:
					parameters[page_name] = {}
				parameters[page_name][p.name] = param_info
			except:
				continue

		sorted_parameters = {}
		for page_name in sorted(parameters.keys()):
			sorted_page = {}
			for par_name in sorted(parameters[page_name].keys()):
				sorted_page[par_name] = parameters[page_name][par_name]
			sorted_parameters[page_name] = sorted_page
		return sorted_parameters

	def get_custom_params(o):
		def read_def_attr(p, attr_name):
			try:
				v = getattr(p, attr_name)
			except:
				return None
			try:
				if callable(v):
					v = v()
			except:
				pass
			if v is None:
				return None
			try:
				if isinstance(v, (str, int, float, bool)):
					return v
			except:
				pass
			try:
				return str(v)
			except:
				return None

		parameters = {}
		params_list = []
		page_order = []
		try:
			pages = list(o.customPages)
		except:
			pages = []
		for pg in pages:
			try:
				page_order.append(pg.name)
			except:
				pass

		try:
			raw_custom = o.customPars
			params_list = raw_custom() if callable(raw_custom) else raw_custom
		except:
			params_list = []

		if not isinstance(params_list, (list, tuple)):
			params_list = []

		processed_par_names = set()
		for p in params_list:
			try:
				par_name = str(p.name)
				if par_name in processed_par_names:
					continue
				page_name = p.page.name if p.page else 'Unknown'
				try:
					tuplet_pars = list(p.tuplet)
				except:
					tuplet_pars = [p]
				if not isinstance(tuplet_pars, (list, tuple)) or len(tuplet_pars) <= 0:
					tuplet_pars = [p]
				is_group = len(tuplet_pars) > 1

				group_name = par_name
				try:
					tuplet_name = str(p.tupletName)
					if tuplet_name:
						group_name = tuplet_name
				except:
					pass

				vals = []
				modes = []
				exprs = []
				binds = []
				component_names = []
				for tp in tuplet_pars:
					try:
						tp_name = str(tp.name)
						component_names.append(tp_name)
						processed_par_names.add(tp_name)
					except:
						pass
					try:
						vals.append(str(tp.val))
					except:
						vals.append('')
					try:
						tp_mode = str(tp.mode)
					except:
						tp_mode = ''
					modes.append(tp_mode)
					tmp_info = {}
					enrich_mode_info(tp, tmp_info)
					exprs.append(tmp_info.get('expr', None))
					binds.append(tmp_info.get('bind', None))

				if is_group:
					param_info = {
						'val': vals,
						'mode': modes,
						'size': len(tuplet_pars),
						'components': component_names
					}
					if any(e is not None for e in exprs):
						param_info['expr'] = exprs
					if any(b is not None for b in binds):
						param_info['bind'] = binds
					strip_val_for_bind(param_info)
				else:
					param_info = {
						'val': vals[0] if vals else '',
						'mode': modes[0] if modes else ''
					}
					if exprs and exprs[0] is not None:
						param_info['expr'] = exprs[0]
					if binds and binds[0] is not None:
						param_info['bind'] = binds[0]
					strip_val_for_bind(param_info)

				def_info = {}
				def_attr_names = [
					'name', 'label', 'style', 'page', 'section',
					'enable', 'enableExpr', 'readOnly', 'readOnlyExpr',
					'startSection', 'help', 'default',
					'min', 'max', 'normMin', 'normMax',
					'clampMin', 'clampMax', 'clampNormMin', 'clampNormMax',
					'isMomentary', 'isMenu', 'menuSource'
				]
				for attr_name in def_attr_names:
					attr_val = read_def_attr(p, attr_name)
					if attr_val is not None:
						def_info[attr_name] = attr_val
				try:
					mn = list(p.menuNames)
					def_info['menuNames'] = [str(x) for x in mn]
				except:
					pass
				try:
					ml = list(p.menuLabels)
					def_info['menuLabels'] = [str(x) for x in ml]
				except:
					pass
				if is_group:
					def_info['size'] = len(tuplet_pars)
					def_info['componentNames'] = component_names
					try:
						style_val = def_info.get('style', '')
						if style_val:
							def_info['styleSize'] = f"{style_val} Size {len(tuplet_pars)}"
					except:
						pass
					def_info['name'] = group_name
				if def_info:
					param_info['definition'] = def_info

				if page_name not in parameters:
					parameters[page_name] = {}
				parameters[page_name][group_name] = param_info
			except:
				continue

		out = {}
		seen = set()
		for pn in page_order:
			if pn in parameters:
				out[pn] = parameters[pn]
				seen.add(pn)
		for pn in parameters.keys():
			if pn not in seen:
				out[pn] = parameters[pn]
		return out

	def read_text_dat_content(dat_op):
		text_val = ''
		try:
			text_val = str(dat_op.text)
		except:
			try:
				text_val = str(dat_op.asText())
			except:
				text_val = ''
		lines = text_val.splitlines()
		meta = {
			'lines': len(lines),
			'chars': len(text_val),
			'sha1': hashlib.sha1(text_val.encode('utf-8', errors='ignore')).hexdigest()
		}
		out = {
			'kind': 'text',
			'meta': meta,
			'full': text_val
		}
		return out

	def read_table_dat_content(dat_op):
		row_count = 0
		col_count = 0
		try:
			row_count = int(dat_op.numRows)
		except:
			row_count = 0
		try:
			col_count = int(dat_op.numCols)
		except:
			col_count = 0

		def get_rows(max_rows):
			rows = []
			limit = row_count if max_rows is None else min(row_count, max_rows)
			for r in range(limit):
				row_vals = []
				for c in range(col_count):
					cell_val = ''
					try:
						cell = dat_op[r, c]
						try:
							cell_val = str(cell.val)
						except:
							cell_val = str(cell)
					except:
						cell_val = ''
					row_vals.append(cell_val)
				rows.append(row_vals)
			return rows

		full_rows = get_rows(None)
		hash_src = json.dumps(full_rows, ensure_ascii=False)
		out = {
			'kind': 'table',
			'meta': {
				'rows': row_count,
				'cols': col_count,
				'sha1': hashlib.sha1(hash_src.encode('utf-8', errors='ignore')).hexdigest()
			},
			'rows': full_rows
		}
		return out

	def get_dat_content(o):
		op_type = str(getattr(o, 'OPType', getattr(o, 'opType', ''))).lower()
		if not op_type.endswith('dat'):
			return None
		if 'tabledat' in op_type:
			return read_table_dat_content(o)
		return read_text_dat_content(o)

	def build_node_tree(o):
		if is_excluded(o.path):
			return None

		node_name = str(getattr(o, 'name', 'Unnamed'))
		node_info = {
			'relPath': to_rel_path(o.path),
			'type': str(getattr(o, 'OPType', getattr(o, 'opType', 'Unknown'))),
			'pos': get_node_pos(o),
			'parameters': get_params(o)
		}
		custom_params = get_custom_params(o)
		if custom_params:
			node_info['customParameters'] = custom_params
		draw_state = get_display_render_state(o)
		if draw_state:
			node_info['drawState'] = draw_state

		dat_content = get_dat_content(o)
		if dat_content is not None:
			node_info['datContent'] = dat_content

		inputs_data = get_input_links(o)
		outputs_data = get_output_links(o)
		if inputs_data or outputs_data:
			node_info['connections'] = {}
			if inputs_data:
				node_info['connections']['inputs'] = inputs_data
			if outputs_data:
				node_info['connections']['outputs'] = outputs_data

		children_data = []
		try:
			children = list(o.children)
		except:
			children = []

		children = sorted(children, key=lambda x: str(getattr(x, 'name', '')))
		for ch in children:
			child_info = build_node_tree(ch)
			if child_info is not None:
				children_data.append(child_info)

		if children_data:
			node_info['children'] = children_data

		return {
			node_name: node_info
		}

	forest = []
	try:
		project1_children = list(project1.children)
	except:
		project1_children = []
	project1_children = sorted(project1_children, key=lambda x: str(getattr(x, 'name', '')))

	for ch in project1_children:
		ch_info = build_node_tree(ch)
		if ch_info is not None:
			forest.append(ch_info)

	try:
		target_dat.text = json.dumps(forest, indent='\t', ensure_ascii=False)
		print(f"Success! Scanned {len(forest)} top-level nodes in /project1.")
	except Exception as e:
		print(f"Failed to write: {e}")

log_target_network_full()
