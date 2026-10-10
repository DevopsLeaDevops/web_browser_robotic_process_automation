"""真實執行最小鏈路：BA-001 → BA-002；不需要原工程服務。"""
import argparse
import hashlib
import html
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contracts import DEFAULTS, INPUT_SCHEMA, OUTPUT_SCHEMA, QUERY_SCHEMA, validate
from target.server import create_server

BASE = Path(__file__).resolve().parent


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def stop_process(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def run_process(command, log_path, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('總期限已到，未啟動下一階段')
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=(os.name != 'nt'))
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            stop_process(process)
            raise TimeoutError('Worker 達到總期限；已終止程序群組') from None
        except BaseException:
            stop_process(process)
            raise
    if code != 0:
        raise RuntimeError(f'腳本結束碼 {code}；請查看 {log_path.name}')


def write_report(folder, result):
    esc = lambda value: html.escape(str(value))
    pretty = lambda value: esc(json.dumps(value, ensure_ascii=False, indent=2))
    status = {'passed': '通過', 'failed': '失敗', 'timed_out': '超時', 'cancelled': '已取消'}[result['status']]
    screenshot = '<img src="screenshot.png" alt="本次瀏覽器畫面">' if (folder/'screenshot.png').exists() else '<p>本次未取得截圖；可能在瀏覽器啟動前失敗或已用完期限。</p>'
    links = ' · '.join(f'<a href="{p.name}">{p.name}</a>' for p in folder.iterdir()
                       if p.is_file() and p.name != 'report.html')
    diagnostics = (folder/'diagnostic.json').read_text(encoding='utf-8') if (folder/'diagnostic.json').exists() else '無額外頁面診斷'
    document = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(result['sceneId'])} 真實執行報告</title><style>body{{font:13px/1.6 system-ui;background:#f5f7fb;color:#24334a;max-width:1040px;margin:20px auto;padding:16px}}section{{background:white;border:1px solid #e9edf3;padding:16px;margin:12px 0;border-radius:9px}}h1{{font-size:21px}}h2{{font-size:15px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fb;padding:12px}}img{{width:100%;border:1px solid #e9edf3}}a{{color:#0b69c4}}table{{width:100%;border-collapse:collapse}}td{{padding:8px;border-bottom:1px solid #e9edf3}}</style><h1>{esc(result['sceneId'])} · {status}</h1><p>真實本機瀏覽器執行 · 版本 1 · {esc(result['runId'])} · {result['durationSeconds']} 秒</p><section><h2>階段</h2><table>{''.join('<tr><td>'+esc(s['name'])+'</td><td>'+esc(s['status'])+'</td></tr>' for s in result['steps'])}</table><p>{esc(result.get('error') or '無異常')}</p></section><section><h2>本次入參</h2><pre>{pretty(result['input'])}</pre><h2>成功出參</h2><pre>{pretty(result['output'])}</pre></section><section><h2>頁面證據</h2>{screenshot}<pre>{esc(diagnostics)}</pre></section><section><h2>檔案與版本</h2><p>{links}</p><p>自動化 SHA-256：{esc(result['automationHash'])}</p><p>斷言 SHA-256：{esc(result['assertionHash'])}</p><p>腳本快照位於 script-snapshot/；出參只在所有檢查通過後發布。</p></section></html>'''
    (folder/'report.html').write_text(document, encoding='utf-8')


def execute_scene(scene, params, base_url, session_dir, timeout=45, headed=False):
    run_id = scene + '-' + uuid.uuid4().hex[:8]
    folder = Path(session_dir)/run_id
    folder.mkdir(parents=True)
    snapshot = folder/'script-snapshot'
    snapshot.mkdir()
    for source in (BASE/'scenes').glob('*.py'):
        shutil.copy2(source, snapshot/source.name)
    write_json(folder/'input.json', params)
    schema = INPUT_SCHEMA if scene == 'BA-001' else QUERY_SCHEMA
    write_json(folder/'input.schema.json', schema)
    write_json(folder/'output.schema.json', OUTPUT_SCHEMA)
    started = time.monotonic()
    deadline = started + timeout
    result = {'runId': run_id, 'sceneId': scene, 'revision': 1, 'status': 'running',
              'startedAt': datetime.now(timezone.utc).isoformat(), 'input': params, 'output': None,
              'automationHash': hashlib.sha256((snapshot/'automation.py').read_bytes()).hexdigest(),
              'assertionHash': hashlib.sha256((snapshot/'assertion.py').read_bytes()).hexdigest(), 'steps': []}
    stage = '入參驗證'
    candidate = folder/'candidate-output.json'
    try:
        validate(params, schema)
        result['steps'].append({'name': stage, 'status': 'passed'})
        stage = '瀏覽器自動化'
        command = [sys.executable, str(snapshot/'automation.py'), '--scene', scene,
                   '--input', str(folder/'input.json'), '--facts', str(folder/'facts.json'),
                   '--screenshot', str(folder/'screenshot.png'), '--target-url',
                   base_url + ('?view=query' if scene == 'BA-002' else ''),
                   '--timeout', str(max(0.001, deadline-time.monotonic()))]
        if headed:
            command.append('--headed')
        run_process(command, folder/'automation.log', deadline)
        result['steps'].append({'name': stage, 'status': 'passed'})
        stage = '獨立斷言'
        run_process([sys.executable, str(snapshot/'assertion.py'), '--scene', scene,
                     '--input', str(folder/'input.json'), '--facts', str(folder/'facts.json'),
                     '--output', str(candidate)], folder/'assertion.log', deadline)
        result['steps'].append({'name': stage, 'status': 'passed'})
        stage = '出參驗證與發布'
        if time.monotonic() >= deadline:
            raise TimeoutError('出參發布前總期限已到')
        output = json.loads(candidate.read_text(encoding='utf-8'))
        validate(output, OUTPUT_SCHEMA)
        if time.monotonic() >= deadline:
            raise TimeoutError('出參驗證後總期限已到')
        candidate.replace(folder/'output.json')
        result['output'] = output
        result['steps'].append({'name': stage, 'status': 'passed'})
        result['status'] = 'passed'
    except KeyboardInterrupt:
        result['status'] = 'cancelled'
        result['error'] = '使用者中止；已停止目前程序。'
        result['steps'].append({'name': stage, 'status': 'cancelled'})
    except Exception as error:
        result['status'] = 'timed_out' if isinstance(error, TimeoutError) else 'failed'
        result['error'] = f'{type(error).__name__}: {error}'
        result['steps'].append({'name': stage, 'status': result['status']})
    finally:
        candidate.unlink(missing_ok=True)
        result['durationSeconds'] = round(time.monotonic()-started, 3)
        write_json(folder/'result.json', result)
        write_report(folder, result)
    return result, folder


def main():
    parser = argparse.ArgumentParser(description='真實瀏覽器自動化最小鏈路')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output-dir', type=Path, default=BASE/'artifacts')
    parser.add_argument('--timeout', type=float, default=45, help='每個場景的總期限（秒）')
    parser.add_argument('--headed', action='store_true')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout 必須大於 0')
    params = json.loads(args.input.read_text(encoding='utf-8')) if args.input else DEFAULTS.copy()
    session = args.output_dir.resolve()/('session-'+uuid.uuid4().hex[:10])
    session.mkdir(parents=True)
    server = create_server()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    results = []
    try:
        url = f'http://127.0.0.1:{server.server_port}/'
        previous = None
        for scene in ('BA-001', 'BA-002'):
            inputs = params if scene == 'BA-001' else {'recordId': previous['recordId']}
            result, folder = execute_scene(scene, inputs, url, session, args.timeout, args.headed)
            results.append((result, folder))
            print(f"{scene}：{result['status']} · {folder/'report.html'}", flush=True)
            if result['status'] != 'passed':
                print('前置節點未通過；停止後續執行。', flush=True)
                break
            previous = result['output']
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    index = '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>真實執行彙總</title><style>body{font:14px/1.8 system-ui;max-width:900px;margin:40px auto;color:#24334a}a{color:#0b69c4}</style><h1>本機瀏覽器自動化 · 真實結果</h1><p>BA-001 建立 → BA-002 查詢；下游入參來自上游成功出參。</p><ul>'
    for result, folder in results:
        index += f'<li><a href="{folder.name}/report.html">{result["sceneId"]} · {result["status"]} · {result["durationSeconds"]} 秒</a></li>'
    index += '</ul><p>每個場景都有獨立 BrowserContext、腳本快照、入參與報告。瀏覽器資料在執行結束後釋放；產物保留在本目錄。</p></html>'
    (session/'index.html').write_text(index, encoding='utf-8')
    print(f'彙總報告：{session/"index.html"}', flush=True)
    return 0 if len(results) == 2 and all(r['status'] == 'passed' for r, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
