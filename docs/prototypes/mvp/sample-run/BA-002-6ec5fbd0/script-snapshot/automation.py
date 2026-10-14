"""BA-001 建立 / BA-002 查詢；同一個標準入口，獨立瀏覽器工作階段。"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def run(args):
    # 本 Demo 刻意只允許本機測試頁，避免誤用在其他網站。
    target = urlsplit(args.target_url)
    if target.scheme != 'http' or target.hostname != '127.0.0.1':
        raise ValueError('本範例只允許本機目標頁')
    params = json.loads(Path(args.input).read_text(encoding='utf-8'))
    deadline = time.monotonic() + args.timeout
    stage = '啟動瀏覽器'

    def remaining():
        milliseconds = int((deadline - time.monotonic()) * 1000)
        if milliseconds <= 0:
            raise TimeoutError(f'總期限已到；目前階段：{stage}')
        return min(milliseconds, 15000)

    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(headless=not args.headed, timeout=remaining())
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        context.set_default_timeout(5000)
        try:
            stage = '開啟目標頁'
            print(stage, flush=True)
            page.goto(args.target_url, wait_until='domcontentloaded', timeout=remaining())
            if args.scene == 'BA-001':
                stage = '填寫表單'
                print(stage, flush=True)
                page.get_by_label('標題', exact=True).fill(params['title'], timeout=remaining())
                page.get_by_label('數量', exact=True).fill(str(params['quantity']), timeout=remaining())
                stage = '建立紀錄（只點擊一次）'
                print(stage, flush=True)
                page.get_by_role('button', name='建立紀錄', exact=True).click(timeout=remaining())
            else:
                stage = '查詢紀錄'
                print(stage, flush=True)
                page.get_by_label('紀錄編號', exact=True).fill(params['recordId'], timeout=remaining())
                page.get_by_role('button', name='查詢', exact=True).click(timeout=remaining())
            stage = '等待可見的紀錄詳情'
            print(stage, flush=True)
            page.locator('#receipt').wait_for(state='visible', timeout=remaining())
            facts = {'recordId': page.locator('#record-id').inner_text(timeout=remaining()),
                     'title': page.locator('#record-title').inner_text(timeout=remaining()),
                     'quantity': int(page.locator('#record-quantity').inner_text(timeout=remaining())),
                     'status': page.locator('#record-status').inner_text(timeout=remaining()),
                     'sourceUrl': page.url, 'sceneId': args.scene}
            stage = '保留證據'
            write_json(args.facts, facts)
            page.screenshot(path=args.screenshot, timeout=remaining(), full_page=True)
            print('自動化完成；等待獨立斷言。', flush=True)
        except Exception as error:
            write_json(str(Path(args.facts).with_name('diagnostic.json')),
                       {'stage': stage, 'url': page.url, 'errorType': type(error).__name__,
                        'error': str(error), 'remainingSeconds': max(0, deadline-time.monotonic())})
            # 失敗截圖也只能消耗剩餘時間；外層 Worker 有硬期限。
            try:
                page.screenshot(path=args.screenshot, timeout=remaining())
            except Exception:
                pass
            raise
        finally:
            context.close()
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', choices=['BA-001', 'BA-002'], required=True)
    for key in ('input', 'facts', 'screenshot', 'target-url'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('--headed', action='store_true')
    run(parser.parse_args())
