"""獨立程序比較 DOM 事實與入參；通過前不得發布成功出參。"""
import argparse
import json
import re
from pathlib import Path


def verify(scene, params, facts):
    if not re.fullmatch(r'DEMO-[A-Z0-9]+', facts.get('recordId', '')):
        raise AssertionError('未取得有效紀錄編號')
    if facts.get('status') != '已建立':
        raise AssertionError('紀錄狀態不符')
    if scene == 'BA-001':
        if facts['title'] != params['title'] or facts['quantity'] != params['quantity']:
            raise AssertionError('畫面標題或數量與本次入參不符')
    elif facts['recordId'] != params['recordId']:
        raise AssertionError('查詢結果不是指定紀錄')
    return {key: facts[key] for key in ('recordId', 'title', 'quantity')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', required=True, choices=['BA-001', 'BA-002'])
    for key in ('input', 'facts', 'output'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    output = verify(args.scene, read(args.input), read(args.facts))
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print('獨立斷言通過。', flush=True)
