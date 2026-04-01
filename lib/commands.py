# 远程命令路由：解析 JSON 字符串并执行
import json
import os
import importlib.util
import sys

# 在 TD 外部或作为模块导入时，确保可访问 op()/project
try:
    op  # type: ignore
    project  # type: ignore
except NameError:
    try:
        import td  # TouchDesigner 的 Python 模块
        op = td.op
        project = td.project
    except Exception:
        # 在非 TD 环境下运行时，允许后续抛出更明确的异常
        pass

def _app():
    a = op('/').fetch('app', None)
    if not a:
        raise Exception('App singleton not found. Did bootstrap.init() run?')
    return a

def _load_disk_module(module_name: str, filename: str):
    """从磁盘以独立别名加载模块，避免被 DAT 同名模块（如 '/bootstrap'、'/app'）遮蔽"""
    abs_path = os.path.join(project.folder, 'lib', filename)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if not spec or not spec.loader:
        raise Exception(f'Cannot load module: {filename}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

def dispatch(payload: str) -> str:
    """
    传入 JSON 字符串，返回结果字符串（可选）
    当前唯一结构编辑协议：
      - reload: { "cmd":"reload" }
      - replicate_framework:{ "cmd":"replicate_framework", "file":"OP_Framework copy.json", "clear_parent":true }
      - save_project:{ "cmd":"save_project", "file":"build/project_saved.toe" }
      - exists:{ "cmd":"exists", "path":"/project1/node1" }
      - list_children:{ "cmd":"list_children", "parent":"/project1" }
      - inspect:{ "cmd":"inspect", "path":"/project1/node1" }
      - project_diagnostics:{ "cmd":"project_diagnostics", "root":"/project1", "recursive":true, "include_clean":false, "limit":500 }
    """
    a = _app()
    cmd = json.loads(payload)

    c = cmd.get('cmd')
    deprecated = {'create', 'par', 'connect', 'clear', 'delete', 'remove', 'destroy', 'hover', 'build_glsl_cube', 'save_tox'}
    if c in deprecated:
        raise Exception(f'Deprecated cmd: {c}. Use OP_Framework JSON + reload -> replicate_framework -> save_project.')
    if c == 'save_project':
        fp = a.save_project(cmd.get('file'))
        return f'save_project:{fp}'
    elif c == 'reload':
        disk_app = _load_disk_module('app', 'app.py')
        new_app = disk_app.App()
        op('/').store('app', new_app)
        return 'reload:ok'
    elif c == 'replicate_framework':
        result = a.replicate_framework(cmd['file'], bool(cmd.get('clear_parent', True)))
        return f"replicate_framework:file={result['file']};nodes={result['nodes']}"
    elif c == 'exists':
        ok = a.exists(cmd['path'])
        return f'exists:{1 if ok else 0}'
    elif c == 'list_children':
        parent = cmd.get('parent', '/project1')
        arr = a.list_children(parent)
        return 'list_children:' + json.dumps(arr, ensure_ascii=False)
    elif c == 'inspect':
        info = a.inspect(cmd['path'])
        return 'inspect:' + json.dumps(info, ensure_ascii=False)
    elif c in ('project_diagnostics', 'diagnostics', 'debug_snapshot'):
        info = a.project_diagnostics(
            cmd.get('root', '/project1'),
            bool(cmd.get('recursive', True)),
            bool(cmd.get('include_clean', False)),
            int(cmd.get('limit', 500))
        )
        return 'project_diagnostics:' + json.dumps(info, ensure_ascii=False)
    else:
        raise Exception(f'Unknown cmd: {c}')
