# 启动引导：把 lib 放到 sys.path、初始化 App，并支持热重载
import sys, os, importlib, json

def _lib_path():
    return os.path.join(project.folder, 'lib')

def _ensure_sys_path():
    lp = _lib_path()
    if lp not in sys.path:
        sys.path.append(lp)

def init(config_relpath: str = 'lib/config.json'):
    """
    在 DAT Execute 的 onStart 里调用：
        import bootstrap
        bootstrap.init()
    """
    _ensure_sys_path()
    import app
    importlib.reload(app)
    a = app.App()

    # 可选：如果存在配置文件，批量应用
    cfg_abs = os.path.join(project.folder, config_relpath)
    if os.path.exists(cfg_abs):
        try:
            with open(cfg_abs, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            a.apply_config(cfg)
        except Exception as e:
            app.debug(f'Load config failed: {e}')
    return a

def reload_modules():
    """
    热重载：重新加载 app 模块，并用新类替换存储中的单例。
    重要：必须用新的 App 实例覆盖旧的实例，否则旧实例的方法代码不会更新。
    """
    _ensure_sys_path()
    import app
    importlib.reload(app)
    # 创建新的 App 实例并覆盖存储
    new_app = app.App()
    op('/').store('app', new_app)
    return new_app