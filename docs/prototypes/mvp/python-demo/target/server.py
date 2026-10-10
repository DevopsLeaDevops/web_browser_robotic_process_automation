"""僅提供本機中性測試頁；資料只在目前程序存活期間保留。"""
import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote


def create_server(port=0):
    records = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, content_type='application/json; charset=utf-8'):
            payload = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                self.reply(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
            elif path.startswith('/api/records/'):
                with lock:
                    value = records.get(unquote(path.removeprefix('/api/records/')))
                self.reply(200 if value else 404, value or {'error': '查無紀錄'})
            else:
                self.reply(404, {'error': '找不到頁面'})

        def do_POST(self):
            if self.path != '/api/records':
                return self.reply(404, {'error': '找不到介面'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    raise ValueError('資料大小不符')
                data = json.loads(self.rfile.read(size))
                title, quantity = data['title'], data['quantity']
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
                    raise ValueError('標題長度不符')
                if type(quantity) is not int or not 1 <= quantity <= 30:
                    raise ValueError('數量需為 1–30 的整數')
            except (ValueError, KeyError, TypeError) as error:
                return self.reply(400, {'error': str(error)})
            record = {'recordId': 'DEMO-' + uuid.uuid4().hex[:12].upper(), 'title': title,
                      'quantity': quantity, 'status': '已建立'}
            with lock:
                records[record['recordId']] = record
            self.reply(201, record)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='本機錄製目標頁')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with create_server(args.port) as server:
        print(f'本機範例：http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
