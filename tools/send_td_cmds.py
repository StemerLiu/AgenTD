import socket
import time
import json

HOST = '127.0.0.1'
PORT = 9988
TIMEOUT = 3


def send_and_recv(cmd_obj):
    s = None
    try:
        s = socket.create_connection((HOST, PORT), timeout=TIMEOUT)
        payload = json.dumps(cmd_obj) + '\r\n'
        s.sendall(payload.encode('utf-8'))
        s.settimeout(TIMEOUT)
        data = b''
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b'\r\n' in data:
                    break
        except socket.timeout:
            pass
        text = data.decode('utf-8', errors='ignore')
        print('payload:', payload.strip())
        print('resp   :', text.strip())
    except Exception as e:
        print('conn/send error:', e)
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


cmds = [
    {"cmd": "reload"},
    {"cmd": "build_glsl_cube", "parent": "/project1"},
    {"cmd": "hover", "parent": "/project1", "value": 1},
    {"cmd": "hover", "parent": "/project1", "value": 0},
]

if __name__ == '__main__':
    for c in cmds:
        send_and_recv(c)
        time.sleep(0.5)