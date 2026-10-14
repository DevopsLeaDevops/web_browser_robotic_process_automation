真實瀏覽器自動化與參數編排範例 · v2.0
========================================
Python 3.10+；目標頁只使用 127.0.0.1，不需要外部帳號或原工程服務。

安裝（需網路下載套件及瀏覽器）：
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  python -m playwright install firefox
Windows 啟用：.venv\Scripts\activate
Linux 可能需要：python -m playwright install --with-deps firefox

新版參數工作流：
  python run_workflow.py
  python run_workflow.py --headed
  python run_workflow.py --workflow examples/workflow.json
  python run_workflow.py --workflow workflow.json --timeout 45

預設：BA-001 重複 2 次，再由 BA-002 查詢第 2 次成功出參。
recordId、quantity 同名匹配；expectedTitle 固定連接 create.title；note 使用預設值。
輸入全圖先校驗，再啟動本機服務與瀏覽器；下游執行前校驗實際入參。
命令列接受 HTML 匯出的工作流 JSON；範例場景庫只有 BA-001 / BA-002。
HTML 若新增場景，需先實作對應的 Python 場景與契約才能執行。

回歸：
  python -m unittest discover -p 'test_*.py' -v
  python check_ui.py
  python check_ui.py --screenshots artifacts/ui-check

保留原有兩步直連：
  python run_demo.py
  python run_demo.py --input examples/input.json

真實錄製（兩個終端）：
  python target/server.py --port 8765
  python -m playwright codegen --browser firefox --target python -o draft.py http://127.0.0.1:8765/

產物：artifacts/workflow-.../index.html
  workflow-snapshot.json：全圖、契約、預設值與解析計畫。
  script-snapshot/：工作流開始時的腳本版本。
  result.json：每次呼叫的來源、實際入參、成功出參與狀態。
  各節點執行目錄：input.json、facts.json、output.json（僅成功）、
  workflow-context.json、Schema、腳本快照、截圖、log、result.json、report.html。

核心檔案：
  contracts.py：完整 JSON Schema 2020-12 驗證與場景庫，拒絕遠端 Schema 引用。
  workflow_parameters.py：四種取值來源、型別相容、占位符與全圖預檢。
  run_workflow.py：固定快照、拓撲串行執行、重複次數、失敗停止與彙總報告。
  run_demo.py：場景執行、獨立 Worker 總期限、斷言、出參發布與 HTML 報告。
  scenes/automation.py：隔離 BrowserContext、操作與擷取 DOM 事實。
  scenes/assertion.py：獨立檢查紀錄編號、數量、標題及狀態。
  test_demo.py / test_workflow_parameters.py：後端與真實瀏覽器行為回歸。
  check_ui.py：HTML 互動、窄屏、保存失敗與參數編排行為檢查。

規則：
- 入參覆蓋保存在節點 bindings，不修改場景庫預設值。
- 自動匹配只找直接上游的唯一同名相容欄位；多來源衝突在啟動前攔截。
- 上游全部重複次數通過後，使用最後一次成功出參；缺少欄位不回退樣例或預設。
- 重複下游每次使用相同的最後上游出參；本節點預設占位符則於每次呼叫解析。
- 入參以 input.json 傳入，不使用文字替換 Python 程式碼，不使用 eval。
- 任一失敗、超時或取消都停止後續節點，不自動重試或回滾外部動作。
- --timeout 是每次場景呼叫中自動化與斷言的共用總期限；不是整圖總期限。
  報告寫入、服務關閉和程序清理需要少量額外時間。

限制：
HTML 為獨立原型，尚未串接 Python 執行器。管理 API、AI、登入、畫面串流仍待建置。
只提供拓撲串行，不提供條件分支、平行排程、跨節點交易、巢狀參數路徑或資料聚合。
已驗證 macOS + Firefox；Windows / Linux 及其他瀏覽器需團隊另行驗收。
狀態與錯誤中的英文是程式欄位；使用者介面及指引使用繁體中文。

不要把 .venv、瀏覽器二進位、artifacts、登入資訊或 __pycache__ 提交到新工程版本庫。
