# TCP/IP DAT 的回调脚本：把收到的 JSON 文本转交给 lib/commands.dispatch
# 将此文件作为 Text DAT（命名 server_callbacks）的 File 源，并把 TCP/IP DAT 的 Callbacks DAT 指向该 Text DAT。

import importlib

# 同时兼容两套签名：
# 1) 现代签名（推荐）：
#    onConnect(dat, peer)
#    onReceive(dat, rowIndex, message, bytes, peer)
#    onClose(dat, peer)
# 2) 旧版签名（部分构建会出现）：
#    onConnect(dat, rowIndex, peerAddress, peerPort)
#    onReceive(dat, rowIndex, message, bytes, peerAddress, peerPort)


def onConnect(dat, *args):
    peer = None
    rowIndex = None
    peerAddress = None
    peerPort = None

    # 现代：仅传入 peer
    if len(args) == 1 and hasattr(args[0], 'address'):
        peer = args[0]
        peerAddress = getattr(peer, 'address', None)
        peerPort = getattr(peer, 'port', None)
    # 旧版：rowIndex, peerAddress, peerPort
    elif len(args) >= 3:
        rowIndex, peerAddress, peerPort = args[0], args[1], args[2]
    # 仅有 rowIndex 的极简情况
    elif len(args) >= 1:
        rowIndex = args[0]

    print('[TD-Automation] TCP connected:', peerAddress, peerPort, 'row', rowIndex)
    return


def onReceive(dat, *args):
    try:
        import commands
        importlib.reload(commands)

        rowIndex = None
        message = None
        bytes_data = None
        peer = None
        peerAddress = None
        peerPort = None

        # 现代：rowIndex, message, bytes, peer
        if len(args) >= 4 and hasattr(args[-1], 'address'):
            rowIndex, message, bytes_data, peer = args[0], args[1], args[2], args[3]
            peerAddress = getattr(peer, 'address', None)
            peerPort = getattr(peer, 'port', None)
        # 旧版：rowIndex, message, bytes, peerAddress, peerPort
        elif len(args) >= 5:
            rowIndex, message, bytes_data, peerAddress, peerPort = args[0], args[1], args[2], args[3], args[4]
        else:
            # 极简：rowIndex, message, bytes
            if len(args) >= 3:
                rowIndex, message, bytes_data = args[0], args[1], args[2]

        payload = ''
        if message:
            payload = message if isinstance(message, str) else str(message, 'utf-8', errors='ignore')
        elif bytes_data:
            try:
                payload = bytes_data.decode('utf-8', errors='ignore')
            except Exception:
                payload = str(bytes_data)

        if not payload or not payload.strip():
            return

        result = commands.dispatch(payload)
        # 兜底：防止 result 为空字符串或 None，保证客户端能收到明确应答
        if result is None or (isinstance(result, str) and not result.strip()):
            result = 'ok'
        print('[TD-Automation] payload:', payload)
        print('[TD-Automation] result:', result, 'from', peerAddress, peerPort, 'row', rowIndex)
        try:
            # 明确指定换行作为终止符，避免不同平台默认终止符造成缓冲未刷新
            dat.send(result, terminator='\r\n')
        except Exception as e2:
            print('[TD-Automation] send back error:', e2)
    except Exception as e:
        print('[TD-Automation] dispatch error:', e)
        # 异常情况下也回包，便于客户端快速定位问题
        try:
            dat.send('error:' + str(e), terminator='\r\n')
        except Exception:
            pass
    return


def onDisconnect(dat, *args):
    # 兼容现代（peer）与旧版（rowIndex）两种方式
    info = None
    if len(args) == 1 and hasattr(args[0], 'address'):
        p = args[0]
        info = f"{getattr(p, 'address', None)}:{getattr(p, 'port', None)}"
    elif len(args) >= 1:
        info = f'row {args[0]}'
    print('[TD-Automation] TCP disconnected:', info)
    return