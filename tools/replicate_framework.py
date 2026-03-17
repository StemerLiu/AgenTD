import argparse
import json
import socket
import time
import os
import sys

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 9988
DEFAULT_TIMEOUT = 5.0


def send_and_recv(host, port, timeout, cmd_obj):
	s = None
	try:
		s = socket.create_connection((host, port), timeout=timeout)
		payload = json.dumps(cmd_obj, ensure_ascii=False) + '\r\n'
		s.sendall(payload.encode('utf-8'))
		s.settimeout(timeout)
		data = b''
		while True:
			chunk = s.recv(4096)
			if not chunk:
				break
			data += chunk
			if b'\r\n' in data:
				break
		resp = data.decode('utf-8', errors='ignore').strip()
		return resp
	finally:
		if s:
			try:
				s.close()
			except Exception:
				pass


def run(args):
	if not os.path.exists(args.framework_file):
		raise FileNotFoundError(f'Framework 文件不存在: {args.framework_file}')
	cmds = []
	if not args.skip_reload:
		cmds.append({'cmd': 'reload'})
	cmds.append({
		'cmd': 'replicate_framework',
		'file': args.framework_file,
		'clear_parent': (not args.no_clear)
	})
	if args.save_project:
		cmds.append({'cmd': 'save_project', 'file': args.save_project})
	for c in cmds:
		resp = send_and_recv(args.host, args.port, args.timeout, c)
		print('payload:', json.dumps(c, ensure_ascii=False))
		print('resp   :', resp)
		if resp.lower().startswith('error:'):
			raise RuntimeError(resp)
		time.sleep(args.interval)


def parse_args():
	p = argparse.ArgumentParser()
	p.add_argument('--host', default=DEFAULT_HOST)
	p.add_argument('--port', type=int, default=DEFAULT_PORT)
	p.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
	p.add_argument('--interval', type=float, default=0.2)
	p.add_argument('--framework-file', default='OP_Framework copy.json')
	p.add_argument('--skip-reload', action='store_true')
	p.add_argument('--no-clear', action='store_true')
	p.add_argument('--save-project', default='')
	return p.parse_args()


if __name__ == '__main__':
	try:
		args = parse_args()
		print(f'start replicate host={args.host} port={args.port} file={args.framework_file}')
		run(args)
		print('replicate done')
	except Exception as e:
		print(f'run failed: {e}')
		sys.exit(1)
