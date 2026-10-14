"""先固定契約與腳本，再以實際成功出參串接各節點。"""
import argparse
from copy import deepcopy
import html
import json
from pathlib import Path
import threading
import uuid
from contracts import scene_catalog
from workflow_parameters import prepare_workflow, resolve
from run_demo import BASE, execute_scene, write_json
from target.server import create_server


def run_workflow(graph, output_dir, *, catalog=None, timeout=45, headed=False, executor=execute_scene):
    if timeout <= 0:
        raise ValueError('總期限必須大於 0')
    prepared = prepare_workflow(graph, scene_catalog() if catalog is None else catalog)
    scripts = {p.name:p.read_text(encoding='utf-8') for p in (BASE/'scenes').glob('*.py')}
    folder = Path(output_dir)/('workflow-'+uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    write_json(folder/'workflow-snapshot.json', prepared)
    source = folder/'script-snapshot'
    source.mkdir()
    for name, text in scripts.items(): (source/name).write_text(text, encoding='utf-8')
    result = {'status':'running','total':prepared['total'],'calls':[], 'error':None}
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for node_id in prepared['order']:
            node = next(n for n in prepared['graph']['nodes'] if n['id'] == node_id)
            for iteration in range(1,node['repeat']+1):
                inputs = resolve(prepared['contracts'][node_id], prepared['plans'][node_id], result['calls'])
                metadata = {'nodeId':node_id,'iteration':iteration,'repeat':node['repeat'],
                            'bindings':prepared['plans'][node_id],
                            'sources':{name:next(c['runId'] for c in reversed(result['calls'])
                                                if c['nodeId'] == binding['source'] and c['status'] == 'passed')
                                       for name,binding in prepared['plans'][node_id].items() if binding['kind'] == 'output'}}
                call, artifact = executor(node['sceneId'], inputs, f'http://127.0.0.1:{server.server_port}/',
                                         folder, timeout, headed, contract=deepcopy(prepared['contracts'][node_id]),
                                         source_snapshot=deepcopy(scripts), metadata=metadata)
                item = {**metadata,'runId':call['runId'],'sceneId':node['sceneId'],'status':call['status'],
                        'inputs':inputs,'outputs':call['output'],'report':str(artifact.relative_to(folder)/'report.html')}
                result['calls'].append(item)
                if call['status'] != 'passed':
                    result['status'] = call['status']
                    result['error'] = call.get('error','前置節點失敗')
                    break
            if result['status'] != 'running': break
        if result['status'] == 'running': result['status'] = 'passed'
    except KeyboardInterrupt:
        result.update(status='cancelled',error='使用者中止；已完成的外部動作不回滾')
    except Exception as error:
        result.update(status='failed',error=str(error))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    write_json(folder/'result.json',result)
    e = html.escape
    rows = ''.join(f'<tr><td>{e(c["nodeId"])} / {c["iteration"]}</td><td>{e(c["sceneId"])}</td><td>{e(c["status"])}</td><td><a href="{e(c["report"])}">入參、出參與來源</a></td></tr>' for c in result['calls'])
    document = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>參數串聯真實報告</title><style>body{{font:14px/1.6 system-ui;color:#24334a;background:#f5f7fb;margin:24px auto;padding:16px;max-width:1080px}}section{{background:white;border:1px solid #e9edf3;padding:16px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #e9edf3;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}a{{color:#0b69c4}}</style><h1>參數串聯 · 真實本機執行</h1><p>結果：{e(result['status'])} · 已執行 {len(result['calls'])} / {result['total']} 次</p><p>{e(result['error'] or '建立兩次，再查詢最後一次成功的紀錄；同名與跨欄位傳遞均經獨立斷言。')}</p><section><table><thead><tr><th>節點 / 次數</th><th>場景</th><th>結果</th><th>報告</th></tr></thead><tbody>{rows}</tbody></table><h2>固定的參數解析計畫</h2><pre>{e(json.dumps(prepared['plans'],ensure_ascii=False,indent=2))}</pre><p><a href="workflow-snapshot.json">工作流與契約快照</a> · <a href="result.json">完整入出參紀錄</a></p></section></html>'''
    (folder/'index.html').write_text(document,encoding='utf-8')
    return result, folder


def main():
    parser = argparse.ArgumentParser(description='通用參數編排：真實本機瀏覽器範例')
    parser.add_argument('--workflow',type=Path,default=BASE/'examples/workflow.json')
    parser.add_argument('--output-dir',type=Path,default=BASE/'artifacts')
    parser.add_argument('--timeout',type=float,default=45)
    parser.add_argument('--headed',action='store_true')
    args = parser.parse_args()
    try:
        graph = json.loads(args.workflow.read_text(encoding='utf-8'))
        result, folder = run_workflow(graph,args.output_dir.resolve(),timeout=args.timeout,headed=args.headed)
        print('真實執行結果：'+result['status'])
        print('報告：'+str(folder/'index.html'))
        return 0 if result['status'] == 'passed' else 1
    except Exception as error:
        print('啟動前攔截：'+str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
