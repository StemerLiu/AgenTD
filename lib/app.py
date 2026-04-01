# TouchDesigner 自动化核心
# 运行环境：TouchDesigner 的内置 Python（可访问 op(), project 等）
from typing import Dict, Any, List, Optional
import os
import json

class App:
    """
    全局管理器（类似“单例”）：会把自身引用存到根 COMP（/）的 storage 里，供任何代码 op('/').fetch('app') 访问。
    """
    def __init__(self):
        self.root = op('/')
        self.store_key = 'app'
        # 注册到全局 storage，确保项目里全局可取
        # 始终覆盖存储中的实例，确保热重载后使用最新类代码
        self.root.store(self.store_key, self)

        # 可选：约定一个工作区（父容器），便于把自动生成的内容集中管理
        self.workspace_path = '/project1'
        self.ensure_workspace()

    def ensure_workspace(self):
        # 如果 /project1 不存在，则在根下创建一个 Base COMP 作为工作区
        if not op('/project1'):
            parent = op('/')
            try:
                # 使用字符串类型名，避免依赖未注入的类型常量
                ws = parent.create('baseCOMP')  # 在根下创建 Base COMP
                ws.name = 'project1'
                self.workspace_path = ws.path
            except Exception as e:
                debug(f'Create workspace failed: {e}')

    def get(self):
        """获取当前 App 单例"""
        return self.root.fetch(self.store_key, self)

    def _set_par_values(self, node_path: str, params: Dict[str, Any]) -> None:
        node = op(node_path)
        if not node:
            raise Exception(f'Node not found: {node_path}')
        for k, v in params.items():
            par = getattr(node.par, k, None)
            if par is None:
                debug(f'Param not found: {node.path}.{k}')
                continue
            try:
                par.val = v
            except Exception:
                try:
                    setattr(node.par, k, v)
                except Exception as e:
                    debug(f'Set param failed: {node.path}.{k} -> {v}: {e}')

    def _create_child(self, parent_path: str, op_type_token: str, name: Optional[str] = None,
                      params: Optional[Dict[str, Any]] = None) -> str:
        parent = op(parent_path)
        if not parent:
            raise Exception(f'Parent not found: {parent_path}')
        child = parent.create(op_type_token)
        if name:
            child.name = name
        self._enable_viewer(child)
        if params:
            self._set_par_values(child.path, params)
        return child.path

    def _enable_viewer(self, node: Any) -> None:
        try:
            node.viewer = True
            return
        except Exception:
            pass
        try:
            node.viewer = 1
            return
        except Exception:
            pass
        try:
            node.par.viewer = 1
        except Exception:
            pass

    def _connect_inputs(self, dest_path: str, src_paths: List[str]) -> None:
        dest = op(dest_path)
        if not dest:
            raise Exception(f'Dest not found: {dest_path}')
        for i, sp in enumerate(src_paths):
            src = op(sp)
            if not src:
                raise Exception(f'Src not found: {sp}')
            try:
                dest.inputConnectors[i].connect(src)
            except Exception as e:
                debug(f'Connect failed: {dest_path}[{i}] <- {sp}: {e}')

    def exists(self, node_path: str) -> bool:
        return bool(op(node_path))

    def list_children(self, parent_path: str = '/project1') -> List[str]:
        parent = op(parent_path)
        if not parent:
            raise Exception(f'Parent not found: {parent_path}')
        return sorted([str(ch.path) for ch in list(parent.children)])

    def inspect(self, node_path: str) -> Dict[str, Any]:
        node = op(node_path)
        if not node:
            raise Exception(f'Node not found: {node_path}')
        parent_path = ''
        try:
            p = node.parent()
            parent_path = p.path if p else ''
        except Exception:
            parent_path = ''
        out = {
            'path': str(node.path),
            'name': str(getattr(node, 'name', '')),
            'type': str(getattr(node, 'OPType', getattr(node, 'opType', 'Unknown'))),
            'parent': parent_path,
            'children': sorted([str(ch.path) for ch in list(getattr(node, 'children', []))])
        }
        errs = self._safe_string_list(getattr(node, 'errors', None))
        warns = self._safe_string_list(getattr(node, 'warnings', None))
        if errs:
            out['errors'] = errs
        if warns:
            out['warnings'] = warns
        return out

    def project_diagnostics(
        self,
        root_path: str = '/project1',
        recursive: bool = True,
        include_clean: bool = False,
        limit: int = 500
    ) -> Dict[str, Any]:
        root = op(root_path)
        if not root:
            raise Exception(f'Root not found: {root_path}')
        nodes = self._collect_diag_nodes(root, recursive)
        issues = []
        for node in nodes:
            errs = self._safe_string_list(getattr(node, 'errors', None))
            warns = self._safe_string_list(getattr(node, 'warnings', None))
            if not errs and not warns and not include_clean:
                continue
            item = {
                'path': str(node.path),
                'type': str(getattr(node, 'OPType', getattr(node, 'opType', 'Unknown')))
            }
            if errs:
                item['errors'] = errs
            if warns:
                item['warnings'] = warns
            if not errs and not warns:
                item['status'] = 'clean'
            issues.append(item)
            if len(issues) >= max(1, int(limit)):
                break
        return {
            'root': str(root.path),
            'recursive': bool(recursive),
            'count': len(issues),
            'items': issues
        }

    def _collect_diag_nodes(self, root: Any, recursive: bool) -> List[Any]:
        out = [root]
        if not recursive:
            try:
                out.extend(list(root.children))
            except Exception:
                pass
            return out
        queue = []
        try:
            queue = list(root.children)
        except Exception:
            queue = []
        while queue:
            n = queue.pop(0)
            out.append(n)
            try:
                queue.extend(list(n.children))
            except Exception:
                pass
        return out

    def _safe_string_list(self, raw: Any) -> List[str]:
        if raw is None:
            return []
        try:
            if callable(raw):
                raw = raw()
        except Exception:
            pass
        if isinstance(raw, (list, tuple, set)):
            return [str(x) for x in raw if str(x)]
        try:
            text = str(raw)
            if not text:
                return []
            return [text]
        except Exception:
            return []

    def _clear_children(self, parent_path: str) -> int:
        parent = op(parent_path)
        if not parent:
            raise Exception(f'Parent not found: {parent_path}')
        cnt = 0
        # 拷贝列表，避免遍历中集合变化
        for ch in list(parent.children):
            try:
                ch.destroy()
                cnt += 1
            except Exception as e:
                debug(f'Destroy failed: {ch.path}: {e}')
        return cnt

    def save_project(self, file_path: Optional[str] = None) -> str:
        """
        保存工程为 .toe
        """
        # 保存前临时从 storage 移除 App，避免 TouchDesigner 在保存 .toe 时尝试 pickle 此对象报错
        removed = False
        try:
            if self.root.fetch(self.store_key, None) is not None:
                self.root.unstore(self.store_key)
                removed = True
        except Exception:
            pass
        try:
            abs_path = self._abs(file_path) if file_path else None
            if abs_path:
                project.save(abs_path)
                return abs_path
            else:
                project.save()
                return project.folder
        finally:
            # 保存完成后恢复存储
            try:
                if removed:
                    self.root.store(self.store_key, self)
            except Exception:
                pass

    def apply_config(self, cfg: Dict[str, Any]) -> None:
        """
        根据 JSON 配置批量创建/设置/连线
        cfg 结构示例：
        {
          "nodes": [
            {"parent": "/project1", "type": "constantCHOP", "name": "const1", "params": {"value0": 0.5}},
            {"parent": "/project1", "type": "noiseCHOP", "name": "noise1", "params": {"amplitude": 1.0}}
          ],
          "wires": [
            {"dest": "/project1/merge1", "src": ["/project1/const1", "/project1/noise1"]}
          ]
        }
        """
        for n in cfg.get('nodes', []):
            self._create_child(n['parent'], n['type'], n.get('name'), n.get('params'))
        for w in cfg.get('wires', []):
            self._connect_inputs(w['dest'], w['src'])

    def replicate_framework(self, framework_file: str, clear_parent: bool = True) -> Dict[str, Any]:
        abs_path = self._abs(framework_file)
        with open(abs_path, 'r', encoding='utf-8-sig') as f:
            forest = json.load(f)
        if not isinstance(forest, list):
            raise Exception('framework json must be a list')
        records = self._collect_framework_nodes(forest)
        if clear_parent:
            self._clear_children('/project1')
        created = 0
        for rec in sorted(records, key=lambda x: x['path'].count('/')):
            node_path = rec['path']
            parent_path = self._parent_path(node_path)
            parent = op(parent_path)
            if not parent:
                raise Exception(f'Parent not found while creating: {parent_path}')
            existing = op(node_path)
            if existing:
                try:
                    existing.destroy()
                except Exception:
                    pass
            self._create_child(parent_path, rec['type'], rec['name'])
            node = op(node_path)
            if not node:
                raise Exception(f'Create failed: {node_path}')
            self._set_node_pos(node, rec.get('pos'))
            if rec.get('has_children_spec', False):
                self._destroy_all_children(node)
            created += 1
        for rec in records:
            self._apply_framework_node_data(rec)
        self._apply_framework_connections(records)
        return {'file': abs_path, 'nodes': created}

    def _collect_framework_nodes(self, forest: List[Any]) -> List[Dict[str, Any]]:
        records = []
        for item in forest:
            if not isinstance(item, dict):
                continue
            for node_name, node_info in item.items():
                self._collect_framework_node(records, node_name, node_info)
        return records

    def _collect_framework_node(self, out: List[Dict[str, Any]], node_name: str, node_info: Dict[str, Any]) -> None:
        rel_path = str(node_info.get('relPath', '') or '')
        if not rel_path:
            rel_path = f"/project1/{node_name}"
        rec = {
            'name': rel_path.rsplit('/', 1)[-1],
            'path': rel_path,
            'type': node_info.get('type'),
            'pos': node_info.get('pos', {}),
            'parameters': node_info.get('parameters', {}),
            'customParameters': node_info.get('customParameters', {}),
            'drawState': node_info.get('drawState', {}),
            'connections': node_info.get('connections', {}),
            'datContent': node_info.get('datContent'),
            'has_children_spec': bool(node_info.get('children', []))
        }
        if not rec['type']:
            raise Exception(f"Node type missing: {rel_path}")
        out.append(rec)
        children = node_info.get('children', [])
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict):
                    continue
                for ch_name, ch_info in child.items():
                    self._collect_framework_node(out, ch_name, ch_info)

    def _set_node_pos(self, node: Any, pos: Dict[str, Any]) -> None:
        if not isinstance(pos, dict):
            return
        x = pos.get('x')
        y = pos.get('y')
        try:
            if x is not None:
                node.nodeX = int(float(x))
        except Exception:
            try:
                if x is not None:
                    node.x = int(float(x))
            except Exception:
                pass
        try:
            if y is not None:
                node.nodeY = int(float(y))
        except Exception:
            try:
                if y is not None:
                    node.y = int(float(y))
            except Exception:
                pass

    def _destroy_all_children(self, node: Any) -> None:
        try:
            children = list(node.children)
        except Exception:
            children = []
        for ch in children:
            try:
                ch.destroy()
            except Exception:
                pass

    def _apply_framework_node_data(self, rec: Dict[str, Any]) -> None:
        node = op(rec['path'])
        if not node:
            raise Exception(f"Node not found after create: {rec['path']}")
        custom_parameters = rec.get('customParameters', {})
        if isinstance(custom_parameters, dict):
            self._apply_custom_parameters(node, custom_parameters)
        parameters = rec.get('parameters', {})
        if isinstance(parameters, dict):
            for _, page_pars in parameters.items():
                if not isinstance(page_pars, dict):
                    continue
                for par_name, par_info in page_pars.items():
                    self._set_framework_par(node, par_name, par_info)
        draw_state = rec.get('drawState', {})
        if isinstance(draw_state, dict):
            self._apply_draw_state(node, draw_state)
        dat_content = rec.get('datContent', None)
        if dat_content:
            self._set_framework_dat_content(node, dat_content)
        self._repair_geometry_sop_path(node, rec)

    def _apply_custom_parameters(self, node: Any, custom_parameters: Dict[str, Any]) -> None:
        for page_name, page_pars in custom_parameters.items():
            if not isinstance(page_pars, dict):
                continue
            page = self._get_or_create_custom_page(node, str(page_name))
            if page is None:
                continue
            for par_name, par_info in page_pars.items():
                if not isinstance(par_info, dict):
                    continue
                if self._is_group_custom_parameter(par_info):
                    self._apply_group_custom_parameter(node, page, str(par_name), par_info)
                    continue
                par = getattr(node.par, str(par_name), None)
                if par is None:
                    self._create_custom_parameter(page, str(par_name), par_info)
                par = getattr(node.par, str(par_name), None)
                if par is not None:
                    definition = par_info.get('definition', {})
                    if isinstance(definition, dict):
                        self._apply_custom_definition(par, definition)
                self._set_framework_par(node, str(par_name), par_info)

    def _is_group_custom_parameter(self, par_info: Dict[str, Any]) -> bool:
        components = par_info.get('components')
        if not isinstance(components, list):
            return False
        if len(components) <= 1:
            return False
        return True

    def _apply_group_custom_parameter(self, node: Any, page: Any, par_name: str, par_info: Dict[str, Any]) -> None:
        group_par = getattr(node.par, par_name, None)
        if group_par is None:
            self._create_custom_parameter(page, par_name, par_info)
            group_par = getattr(node.par, par_name, None)
        if group_par is not None:
            self._ensure_group_parameter_shape(group_par, par_info)
        definition = par_info.get('definition', {})
        if group_par is not None and isinstance(definition, dict):
            self._apply_custom_definition(group_par, definition)

        components = [str(x) for x in (par_info.get('components') or []) if str(x)]
        values = par_info.get('val')
        modes = par_info.get('mode')
        exprs = par_info.get('expr')
        group_label = ''
        if isinstance(definition, dict) and definition.get('label') not in (None, ''):
            group_label = str(definition.get('label'))

        missing_components = [n for n in components if getattr(node.par, n, None) is None]
        if missing_components:
            self._create_missing_group_components(page, par_info, missing_components)

        for i, comp_name in enumerate(components):
            comp_par = getattr(node.par, comp_name, None)
            if comp_par is None:
                continue
            if isinstance(definition, dict):
                self._apply_custom_definition(comp_par, definition)
            if group_label:
                try:
                    comp_par.label = group_label
                except Exception:
                    pass
            item = {
                'val': self._pick_group_item(values, i),
                'mode': self._pick_group_item(modes, i)
            }
            expr_item = self._pick_group_item(exprs, i)
            if expr_item not in (None, ''):
                item['expr'] = expr_item
            self._set_framework_par(node, comp_name, item)

    def _pick_group_item(self, v: Any, idx: int) -> Any:
        if isinstance(v, (list, tuple)):
            if 0 <= idx < len(v):
                return v[idx]
            return None
        return v

    def _get_or_create_custom_page(self, node: Any, page_name: str) -> Any:
        pages = []
        try:
            pages = list(node.customPages)
        except Exception:
            pages = []
        for p in pages:
            try:
                if str(getattr(p, 'name', '')) == page_name:
                    return p
            except Exception:
                pass
        try:
            return node.appendCustomPage(page_name)
        except Exception:
            return None

    def _create_custom_parameter(self, page: Any, par_name: str, par_info: Dict[str, Any]) -> None:
        definition = par_info.get('definition', {})
        style = ''
        label = par_name
        group_size = self._get_group_size(par_info)
        component_names = self._get_group_components(par_info)
        if isinstance(definition, dict):
            style = str(definition.get('style', '') or '').lower()
            if definition.get('label') not in (None, ''):
                label = str(definition.get('label'))
        style_method_map = {
            'header': ['appendHeader'],
            'toggle': ['appendToggle'],
            'int': ['appendInt'],
            'integer': ['appendInt'],
            'float': ['appendFloat'],
            'xy': ['appendXY', 'appendFloat'],
            'xyz': ['appendXYZ', 'appendFloat'],
            'rgb': ['appendRGB', 'appendFloat'],
            'rgba': ['appendRGBA', 'appendRGB', 'appendFloat'],
            'str': ['appendStr', 'appendString'],
            'string': ['appendString', 'appendStr'],
            'menu': ['appendMenu', 'appendStr', 'appendString'],
            'pulse': ['appendPulse', 'appendToggle']
        }
        if style in style_method_map:
            for method_name in style_method_map[style]:
                if self._append_custom_parameter(page, method_name, par_name, label, group_size, component_names):
                    return
        value = par_info.get('val', '')
        if self._looks_bool(value):
            methods = ['appendToggle']
        elif self._looks_int(value):
            methods = ['appendInt', 'appendFloat']
        elif self._looks_float(value):
            methods = ['appendFloat']
        else:
            methods = ['appendStr', 'appendString']
        for method_name in methods:
            if self._append_custom_parameter(page, method_name, par_name, label, group_size, component_names):
                return
        for fallback in ['appendFloat', 'appendInt', 'appendToggle', 'appendStr', 'appendString', 'appendMenu', 'appendHeader']:
            if self._append_custom_parameter(page, fallback, par_name, label, group_size, component_names):
                return

    def _append_custom_parameter(
        self,
        page: Any,
        method_name: str,
        par_name: str,
        label: str,
        group_size: int = 1,
        component_names: Optional[List[str]] = None
    ) -> bool:
        fn = getattr(page, method_name, None)
        if not callable(fn):
            return False
        kwargs_list = [{}, {'label': label}]
        if group_size > 1:
            kwargs_list = [
                {'size': group_size},
                {'label': label, 'size': group_size},
                {'size': group_size, 'componentNames': component_names or []},
                {'label': label, 'size': group_size, 'componentNames': component_names or []}
            ] + kwargs_list
        args_list = [par_name, [par_name]]
        for args in args_list:
            for kwargs in kwargs_list:
                try:
                    fn(args, **kwargs)
                    return True
                except Exception:
                    pass
        return False

    def _ensure_group_parameter_shape(self, group_par: Any, par_info: Dict[str, Any]) -> None:
        group_size = self._get_group_size(par_info)
        components = self._get_group_components(par_info)
        if group_size > 1:
            try:
                group_par.size = int(group_size)
            except Exception:
                pass
        if components:
            try:
                group_par.componentNames = [str(x) for x in components]
            except Exception:
                pass

    def _create_missing_group_components(self, page: Any, group_info: Dict[str, Any], missing_components: List[str]) -> None:
        group_values = group_info.get('val')
        group_modes = group_info.get('mode')
        group_exprs = group_info.get('expr')
        all_components = self._get_group_components(group_info)
        for comp_name in missing_components:
            idx = all_components.index(comp_name) if comp_name in all_components else 0
            item = {
                'val': self._pick_group_item(group_values, idx),
                'mode': self._pick_group_item(group_modes, idx)
            }
            expr_item = self._pick_group_item(group_exprs, idx)
            if expr_item not in (None, ''):
                item['expr'] = expr_item
            definition = group_info.get('definition', {})
            if isinstance(definition, dict):
                d = dict(definition)
                d['name'] = comp_name
                d['size'] = 1
                d.pop('componentNames', None)
                item['definition'] = d
            self._create_custom_parameter(page, comp_name, item)

    def _get_group_size(self, par_info: Dict[str, Any]) -> int:
        size = par_info.get('size')
        if size is None and isinstance(par_info.get('definition'), dict):
            size = par_info['definition'].get('size')
        try:
            n = int(size)
            if n > 1:
                return n
        except Exception:
            pass
        components = self._get_group_components(par_info)
        if len(components) > 1:
            return len(components)
        return 1

    def _get_group_components(self, par_info: Dict[str, Any]) -> List[str]:
        components = par_info.get('components')
        if not isinstance(components, list) or not components:
            definition = par_info.get('definition', {})
            if isinstance(definition, dict):
                components = definition.get('componentNames', [])
        if not isinstance(components, list):
            return []
        return [str(x) for x in components if str(x)]

    def _apply_custom_definition(self, par: Any, definition: Dict[str, Any]) -> None:
        attr_map = {
            'label': 'label',
            'section': 'section',
            'enable': 'enable',
            'enableExpr': 'enableExpr',
            'readOnly': 'readOnly',
            'readOnlyExpr': 'readOnlyExpr',
            'startSection': 'startSection',
            'help': 'help',
            'default': 'default',
            'min': 'min',
            'max': 'max',
            'normMin': 'normMin',
            'normMax': 'normMax',
            'clampMin': 'clampMin',
            'clampMax': 'clampMax',
            'clampNormMin': 'clampNormMin',
            'clampNormMax': 'clampNormMax',
            'isMomentary': 'isMomentary',
            'isMenu': 'isMenu'
        }
        for source_key, target_attr in attr_map.items():
            if source_key not in definition:
                continue
            val = self._coerce_definition_value(source_key, definition.get(source_key))
            try:
                setattr(par, target_attr, val)
            except Exception:
                pass
        if 'menuNames' in definition:
            try:
                par.menuNames = [str(x) for x in (definition.get('menuNames') or [])]
            except Exception:
                pass
        if 'menuLabels' in definition:
            try:
                par.menuLabels = [str(x) for x in (definition.get('menuLabels') or [])]
            except Exception:
                pass
        if 'menuSource' in definition:
            try:
                par.menuSource = str(definition.get('menuSource') or '')
            except Exception:
                pass
        ignored = {'name', 'style', 'page', 'menuNames', 'menuLabels', 'menuSource'}
        for source_key, raw_val in definition.items():
            if source_key in ignored or source_key in attr_map:
                continue
            try:
                setattr(par, source_key, raw_val)
            except Exception:
                pass

    def _coerce_definition_value(self, key: str, raw_val: Any) -> Any:
        if key in (
            'enable', 'readOnly', 'startSection', 'clampMin', 'clampMax',
            'clampNormMin', 'clampNormMax', 'isMomentary', 'isMenu'
        ):
            return self._coerce_framework_bool(raw_val)
        if key in ('min', 'max', 'normMin', 'normMax', 'default'):
            return self._coerce_number_or_text(raw_val)
        return raw_val

    def _coerce_number_or_text(self, raw_val: Any) -> Any:
        if isinstance(raw_val, (int, float, bool)):
            return raw_val
        if raw_val is None:
            return ''
        if isinstance(raw_val, str):
            s = raw_val.strip()
            if not s:
                return ''
            if s.lower() in ('true', 'false'):
                return self._coerce_framework_bool(s)
            try:
                if '.' in s:
                    return float(s)
                return int(s)
            except Exception:
                return raw_val
        return raw_val

    def _looks_bool(self, v: Any) -> bool:
        if isinstance(v, bool):
            return True
        if isinstance(v, str):
            return v.strip().lower() in ('true', 'false', '0', '1', 'on', 'off', 'yes', 'no')
        if isinstance(v, (int, float)):
            return v in (0, 1)
        return False

    def _looks_int(self, v: Any) -> bool:
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            return True
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return False
            if s.startswith('-'):
                s = s[1:]
            return s.isdigit()
        return False

    def _looks_float(self, v: Any) -> bool:
        if isinstance(v, bool):
            return False
        if isinstance(v, float):
            return True
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return False
            try:
                float(s)
                return True
            except Exception:
                return False
        return False

    def _repair_geometry_sop_path(self, node: Any, rec: Dict[str, Any]) -> None:
        if str(rec.get('type', '')) != 'geometryCOMP':
            return
        if self._has_framework_par(rec.get('parameters', {}), 'soppath'):
            return
        if self._has_framework_par(rec.get('parameters', {}), 'sop'):
            return
        in1 = op(f"{node.path}/in1")
        if not in1:
            return
        try:
            node.par.soppath = in1
            return
        except Exception:
            pass
        try:
            node.par.soppath = in1.path
            return
        except Exception:
            pass
        try:
            node.par.sop = in1
            return
        except Exception:
            pass
        try:
            node.par.sop = in1.path
        except Exception:
            pass

    def _has_framework_par(self, parameters: Any, par_name: str) -> bool:
        if not isinstance(parameters, dict):
            return False
        target = str(par_name).lower()
        for _, page_pars in parameters.items():
            if not isinstance(page_pars, dict):
                continue
            for key in page_pars.keys():
                if str(key).lower() == target:
                    return True
        return False

    def _apply_draw_state(self, node: Any, draw_state: Dict[str, Any]) -> None:
        key_aliases = {
            'display': ['display', 'displayFlag'],
            'render': ['render', 'renderFlag'],
            'template': ['template', 'templateFlag'],
            'compare': ['compare', 'compareFlag'],
            'pickable': ['pickable', 'pickableFlag'],
            'bypass': ['bypass', 'bypassFlag'],
            'lock': ['lock', 'lockFlag']
        }
        for key, aliases in key_aliases.items():
            if key not in draw_state:
                continue
            value = self._coerce_framework_bool(draw_state.get(key))
            self._set_flag_bool(node, aliases, value)
        for key, raw_val in draw_state.items():
            if key in key_aliases:
                continue
            value = self._coerce_framework_bool(raw_val)
            aliases = [str(key), f"{key}Flag"]
            self._set_flag_bool(node, aliases, value)

    def _set_flag_bool(self, node: Any, names: List[str], value: bool) -> None:
        for name in names:
            try:
                setattr(node, name, value)
                return
            except Exception:
                pass
        method_names = []
        for name in names:
            if not name:
                continue
            method_names.append(f"set{name[0].upper()}{name[1:]}")
        for m in method_names:
            fn = getattr(node, m, None)
            if callable(fn):
                try:
                    fn(value)
                    return
                except Exception:
                    pass

    def _coerce_framework_bool(self, raw_val: Any) -> bool:
        if isinstance(raw_val, bool):
            return raw_val
        if isinstance(raw_val, (int, float)):
            return bool(raw_val)
        if isinstance(raw_val, str):
            v = raw_val.strip().lower()
            if v in ('1', 'true', 'on', 'yes'):
                return True
            if v in ('0', 'false', 'off', 'no', ''):
                return False
        return bool(raw_val)

    def _set_framework_par(self, node: Any, par_name: str, par_info: Any) -> None:
        par = getattr(node.par, par_name, None)
        if par is None:
            return
        if not isinstance(par_info, dict):
            try:
                par.val = par_info
            except Exception:
                try:
                    setattr(node.par, par_name, par_info)
                except Exception:
                    pass
            return
        mode = str(par_info.get('mode', '') or '')
        raw_val = par_info.get('val')
        expr = par_info.get('expr')
        self._apply_framework_par_mode(par, mode)
        if mode == 'ParMode.BIND':
            bind_expr, bind_master, bind_range = self._extract_bind_info(par_info, expr)
            if bind_expr not in (None, ''):
                try:
                    par.bindExpr = str(bind_expr)
                except Exception:
                    pass
            if bind_master not in (None, ''):
                try:
                    bm = op(str(bind_master))
                    par.bindMaster = bm if bm else str(bind_master)
                except Exception:
                    pass
            if bind_range not in (None, ''):
                try:
                    par.bindRange = self._coerce_framework_bool(bind_range)
                except Exception:
                    pass
        if mode == 'ParMode.EXPRESSION' and expr is not None:
            try:
                par.expr = str(expr)
                return
            except Exception:
                pass
        value = self._coerce_framework_value(raw_val)
        try:
            par.val = value
        except Exception:
            try:
                setattr(node.par, par_name, value)
            except Exception:
                pass

    def _apply_framework_par_mode(self, par: Any, mode: str) -> None:
        mode_str = str(mode or '').strip()
        if not mode_str:
            return
        try:
            current_mode = str(par.mode)
            if current_mode == mode_str:
                return
        except Exception:
            pass
        token = mode_str.split('.')[-1]
        enum_value = None
        try:
            enum_value = getattr(ParMode, token)  # type: ignore
        except Exception:
            enum_value = None
        if enum_value is None:
            try:
                import td  # type: ignore
                enum_value = getattr(td.ParMode, token)
            except Exception:
                enum_value = None
        if enum_value is not None:
            try:
                par.mode = enum_value
                return
            except Exception:
                pass
        try:
            par.mode = mode_str
        except Exception:
            pass

    def _extract_bind_info(self, par_info: Dict[str, Any], expr_fallback: Any) -> Any:
        bind_expr = par_info.get('bindExpr')
        bind_master = par_info.get('bindMaster')
        bind_range = par_info.get('bindRange')
        bind_obj = par_info.get('bind')
        if isinstance(bind_obj, dict):
            if bind_expr in (None, ''):
                bind_expr = bind_obj.get('bindExpr', bind_obj.get('expr', bind_expr))
            if bind_master in (None, ''):
                bind_master = bind_obj.get('bindMaster', bind_obj.get('master', bind_master))
            if bind_range in (None, ''):
                bind_range = bind_obj.get('bindRange', bind_obj.get('range', bind_range))
        elif bind_obj not in (None, '') and bind_expr in (None, ''):
            bind_expr = bind_obj
        if bind_expr in (None, ''):
            bind_expr = expr_fallback
        return bind_expr, bind_master, bind_range

    def _set_framework_dat_content(self, node: Any, dat_content: Dict[str, Any]) -> None:
        kind = str(dat_content.get('kind', '') or '').lower()
        if kind == 'table':
            rows = dat_content.get('rows', [])
            if not isinstance(rows, list):
                return
            try:
                node.clear()
            except Exception:
                pass
            for row in rows:
                try:
                    node.appendRow(list(row) if isinstance(row, (list, tuple)) else [str(row)])
                except Exception:
                    pass
            return
        if kind == 'text':
            text = str(dat_content.get('full', ''))
            try:
                node.text = text
            except Exception:
                try:
                    node.write(text)
                except Exception:
                    pass

    def _apply_framework_connections(self, records: List[Dict[str, Any]]) -> None:
        for rec in records:
            dest_path = rec['path']
            dest = op(dest_path)
            if not dest:
                continue
            conns = rec.get('connections', {})
            if not isinstance(conns, dict):
                continue
            inputs = conns.get('inputs', [])
            if not isinstance(inputs, list):
                continue
            for entry in sorted(inputs, key=lambda x: int(x.get('port', 0)) if isinstance(x, dict) else 0):
                if not isinstance(entry, dict):
                    continue
                port = int(entry.get('port', 0))
                links = entry.get('links', [])
                if not isinstance(links, list):
                    continue
                for link in links:
                    src_path = self._resolve_framework_link(dest_path, link)
                    src = op(src_path)
                    if not src:
                        raise Exception(f'Src not found: {src_path}')
                    try:
                        dest.inputConnectors[port].connect(src)
                    except Exception as e:
                        debug(f'Connect failed: {dest_path}[{port}] <- {src_path}: {e}')

    def _resolve_framework_link(self, dest_path: str, link: Any) -> str:
        link_str = str(link)
        if link_str.startswith('/'):
            return link_str
        if '/' in link_str:
            return link_str
        parent_path = self._parent_path(dest_path)
        candidate = f'{parent_path}/{link_str}'
        if op(candidate):
            return candidate
        candidate2 = f'/project1/{link_str}'
        if op(candidate2):
            return candidate2
        return candidate

    def _parent_path(self, path: str) -> str:
        if not path or path == '/':
            return '/'
        idx = path.rfind('/')
        if idx <= 0:
            return '/'
        return path[:idx]

    def _coerce_framework_value(self, raw_val: Any) -> Any:
        if isinstance(raw_val, (int, float, bool)):
            return raw_val
        if raw_val is None:
            return ''
        if not isinstance(raw_val, str):
            return raw_val
        v = raw_val.strip()
        lv = v.lower()
        if lv == 'true':
            return 1
        if lv == 'false':
            return 0
        try:
            if '.' in v:
                return float(v)
            return int(v)
        except Exception:
            return raw_val

    def _abs(self, p: str) -> str:
        if os.path.isabs(p):
            return p
        return os.path.join(project.folder, p)

def debug(msg: str) -> None:
    # TouchDesigner 的调试输出，可以改为在 Textport 或自定义日志 DAT 里打印
    print('[TD-Automation]', msg)

# 在 TD 外部或某些导入场景下，op/project 可能未注入为全局。做一次兼容性兜底。
try:
    op  # type: ignore
    project  # type: ignore
except NameError:
    try:
        import td  # TouchDesigner 的 Python 模块
        op = td.op
        project = td.project
    except Exception as e:
        raise NameError("未检测到 TouchDesigner 运行环境：全局 'op' 或 'project' 未定义。请确保在 TD 内通过 DAT Execute 调用 bootstrap.init()。")
