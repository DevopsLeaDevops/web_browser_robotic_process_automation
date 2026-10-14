"""離線 HTML 互動回歸；不連接外部網站。"""
import argparse
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parent

def run(index, screenshots=None):
    url=index.resolve().as_uri(); errors=[];checks=[]
    with sync_playwright() as p:
        browser=p.firefox.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':900},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.set_default_timeout(5000)
        def fresh(route='playground'):
            page.goto(url+'#'+route);page.evaluate("localStorage.removeItem('automation-demo-v2')");page.reload();page.wait_for_selector('#content > *')
        def snap():return page.evaluate('FlowDemo.snapshot()')
        def mode(name,value):page.locator(f'[data-mode-field="{name}"][value="{value}"]').check(force=True)
        fresh()
        for w,h in [(1440,900),(1280,720),(390,844)]:
            page.set_viewport_size({'width':w,'height':h})
            for route in ['scenarios','recording','reports','playground','architecture','contracts','increments','start']:
                page.goto(url+'#'+route);page.wait_for_selector('#content > *')
                size=page.evaluate('({s:document.documentElement.scrollWidth,c:document.documentElement.clientWidth})')
                assert size['s']<=size['c'],(w,route,size)
            page.goto(url+'#playground')
            if screenshots:
                screenshots.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(screenshots/f'playground-{w}.png'),full_page=True,animations='disabled')
        checks.append('8 頁 × 3 尺寸：無整頁水平溢出')
        page.set_viewport_size({'width':1440,'height':900});fresh()
        before=snap();page.locator('#wf-fit').click();after=snap()
        assert before['draft']==after['draft'] and before['dirty']==after['dirty']
        assert page.locator('.wf-hit[marker-end]').count()==0
        checks.append('畫布適應不改座標或儲存狀態；命中層無重複箭頭')
        fresh();page.locator('#wf-run').click();page.wait_for_function('FlowDemo.snapshot().last && !FlowDemo.snapshot().busy')
        result=snap()['last'];assert len(result['calls'])==3 and result['status'].startswith('全部通過'),result
        a,b,c=result['calls'];assert a['outputs']['recordId']!=b['outputs']['recordId']
        assert c['inputs']['recordId']==b['outputs']['recordId'] and c['inputs']['expectedTitle']==b['outputs']['title']
        assert page.evaluate('state.reports[0].workflow.sources.recordId')==b['runId']
        checks.append('同名與跨欄位綁定、重複最後出參、來源 Run 記錄')
        fresh();mode('note','value');field=page.locator('[data-manual="note"]');field.fill('保留這份輸入')
        assert field.evaluate('(e)=>e===document.activeElement')
        height=page.locator('#wf-parameters').bounding_box()['height'];page.locator('#wf-collapse').click()
        assert page.locator('#wf-parameters').bounding_box()['height']==height
        page.locator('#wf-collapse').click();assert page.locator('[data-manual="note"]').input_value()=='保留這份輸入'
        page.locator('#wf-repeat').fill('2');page.locator('#wf-repeat').dispatch_event('change')
        assert page.locator('[data-manual="note"]').input_value()=='保留這份輸入'
        mode('quantity','value');page.locator('[data-manual="quantity"]').fill('not-json');page.locator('#wf-save-params').click()
        assert '有效 JSON' in page.locator('#wf-save-state').inner_text()
        assert page.locator('[data-manual="quantity"]').input_value()=='not-json'
        checks.append('人工模式聚焦、收合固定高度、節點改動保留草稿、無效 JSON 不丟失')
        page.locator('[data-manual="quantity"]').fill('12');page.locator('#wf-save-params').click()
        assert '已儲存' in page.locator('#wf-save-state').inner_text();page.reload()
        assert page.locator('[data-manual="note"]').input_value()=='保留這份輸入'
        assert page.evaluate("state.scenes.find(s=>s.id==='BA-002').defaults.note")=='預設驗證說明'
        checks.append('覆蓋保存與重載；不修改場景庫預設')
        page.locator('#wf-reset-params').click();page.locator('#wf-save-params').click()
        assert snap()['draft']['nodes'][1]['bindings']=={}
        mode('quantity','default');page.locator('#wf-save-params').click()
        assert snap()['draft']['nodes'][1]['bindings']['quantity']=={'kind':'default'}
        checks.append('重設清除覆蓋與強制腳本預設')
        fresh();mode('note','value');page.locator('[data-manual="note"]').fill('儲存失敗也保留')
        page.evaluate("window.originalWriter=storeWrite;storeWrite=()=>false")
        page.locator('#wf-save-params').click()
        assert '儲存失敗' in page.locator('#wf-save-state').inner_text()
        assert page.locator('[data-manual="note"]').input_value()=='儲存失敗也保留'
        page.evaluate('storeWrite=window.originalWriter')
        checks.append('儲存失敗保留原始輸入')
        fresh();page.locator('[data-source="create"][data-field="title"]').click();page.locator('[data-input-port="note"]').click()
        assert snap()['draft']['nodes'][1]['bindings']['note']=={'kind':'output','source':'create','field':'title'}
        page.locator('[data-unlink="create"]').click()
        assert snap()['draft']['edges']==[] and snap()['draft']['nodes'][1]['bindings']=={}
        checks.append('點選出參連線；移除依賴清理所有受影響引用')
        fresh();page.locator('[data-source="create"][data-field="title"]').drag_to(page.locator('[data-input-port="note"]'))
        assert snap()['draft']['nodes'][1]['bindings']['note']['field']=='title'
        checks.append('拖曳出參至入參')
        fresh();page.locator('[data-node="create"]').press('Enter');page.locator('#wf-source').select_option('verify');page.locator('#wf-connect').click()
        assert '循環' in page.locator('#toast').inner_text();assert len(snap()['draft']['edges'])==1
        node=page.locator('[data-node="create"]');box=node.bounding_box();page.mouse.move(box['x']+80,box['y']+15);page.mouse.down();page.mouse.move(box['x']+125,box['y']+50,steps=5);page.mouse.up()
        assert snap()['dirty'] and snap()['draft']['nodes'][0]['x']>40
        checks.append('循環攔截與節點拖動')
        fresh();page.locator('#wf-fail').select_option('create');page.locator('#wf-run').click();page.wait_for_function('!FlowDemo.snapshot().busy')
        assert len(snap()['last']['calls'])==1 and snap()['last']['status']=='失敗'
        fresh();page.locator('#wf-run').click();page.locator('#wf-stop').click();page.wait_for_function('!FlowDemo.snapshot().busy')
        assert snap()['last']['status']=='已停止'
        checks.append('前置失敗停止、使用者停止')
        fresh();page.locator('[data-add="BA-001"]').click();extra=snap()['draft']['nodes'][-1]['id'];page.locator('[data-node="verify"]').press('Enter');page.locator('#wf-source').select_option(extra);page.locator('#wf-connect').click();page.locator('#wf-run').click()
        assert '多個同名' in page.locator('#wf-save-state').inner_text();assert snap()['last'] is None
        checks.append('多上游同名衝突在執行前攔截')
        fresh();page.evaluate("localStorage.setItem('automation-demo-v2',JSON.stringify({...state,workflowRevision:9}))");page.locator('#wf-save').click()
        assert '其他頁面變更' in page.locator('#wf-save-state').inner_text()
        checks.append('版本衝突不覆寫其他頁面')
        fresh('scenarios');page.locator('[data-action=run][data-id=BA-001]').click();page.locator('#run-params').fill('{"quantity":12}');page.locator('#dialog-action').click()
        assert '缺少必填' in page.locator('#run-error').inner_text()
        page.locator('#run-params').fill('{"title":"驗收紀錄","quantity":19}');page.locator('#dialog-action').click();page.wait_for_selector('[data-report]');page.locator('[data-report]').first.click()
        with page.expect_download() as d:page.locator('#dialog-action').click()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'report.html';d.value.save_as(f);assert '驗收紀錄' in f.read_text() and '離線模擬' in f.read_text()
        page.locator('#dialog-close').click();page.goto(url+'#scenarios');page.locator('[data-action=inputs][data-id=BA-001]').click();page.locator('#values').fill('{"title":"修改預設值","quantity":20}');page.locator('#dialog-action').click()
        assert page.locator('[data-action=run][data-id=BA-001]').is_disabled()
        page.goto(url+'#recording');page.locator('#record-start').click();page.locator('#draft-validate').click();assert page.locator('#draft-publish').is_enabled()
        page.locator('#draft-code').fill(page.locator('#draft-code').input_value()+'\n# 重驗內容\n');assert page.locator('#draft-publish').is_disabled();page.locator('#draft-save').click();page.locator('#draft-validate').click();page.locator('#draft-publish').click()
        page.goto(url+'#scenarios');assert page.locator('[data-action=run][data-id=BA-001]').is_enabled()
        checks.append('既有缺參、報告下載、版本失效、草稿修改與重新發布')
        fresh();page.locator('#wf-run').click();page.wait_for_function('!FlowDemo.snapshot().busy');page.goto(url+'#reports');page.locator('#report-scenes').select_option('BA-002');assert page.locator('#report-table tbody tr').count()==1
        page.locator('#report-scenes').select_option(['BA-001','BA-002']);assert page.locator('#report-table tbody tr').count()==3
        page.locator('[data-report]').first.click();assert 'create' in page.locator('#dialog-content').inner_text();page.locator('#dialog-close').click()
        checks.append('報告多選與入出參來源展示')
        page.set_viewport_size({'width':390,'height':844});page.locator('#menu-toggle').click();assert page.locator('#menu-toggle').get_attribute('aria-expanded')=='true';page.locator('#sidenav a').first.click();assert page.locator('#menu-toggle').get_attribute('aria-expanded')=='false'
        assert not errors,errors
        browser.close()
    return {'passed':len(checks),'checks':checks,'javascriptErrors':errors}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=Path,default=BASE.parent/'index.html');parser.add_argument('--screenshots',type=Path);args=parser.parse_args()
    print(json.dumps(run(args.index,args.screenshots),ensure_ascii=False,indent=2))
