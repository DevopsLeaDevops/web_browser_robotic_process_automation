真實瀏覽器自動化最小範例
========================
Python 3.10+；macOS / Linux 建議使用 venv；Windows 啟用指令見下方。
本例沒有外部帳號、憑證或業務系統。只使用 127.0.0.1 的本機測試頁。

安裝（需網路）：
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -r requirements.txt
  python -m playwright install firefox
Windows 啟用：.venv\Scripts\activate
Linux 可能需要：python -m playwright install --with-deps firefox

執行：
  python run_demo.py
  python run_demo.py --headed
  python run_demo.py --input examples/input.json
  python -m unittest -v test_demo

成果：artifacts/session-.../index.html。
每個場景各有 input.json、facts.json、output.json（僅成功時）、Screenshot、
Schema、腳本快照、log、result.json、report.html。
用瀏覽器開啟彙總報告，即可查看兩個場景真實執行的結果。

實際錄製（兩個終端）：
  python target/server.py --port 8765
  python -m playwright codegen --browser firefox --target python -o draft.py http://127.0.0.1:8765/

錄製後比照 scenes/automation.py 提取參數、處理等待、保留 DOM 事實；
用 scenes/assertion.py 獨立檢查成功條件，不可只看腳本沒有拋錯。
不會把原始 codegen 輸出自動宣稱為標準腳本。

檔案：
  target/：可操作的本機建立／查詢頁面；資料僅存在記憶體。
  contracts.py：JSON Schema 2020-12 與預設入參。
  scenes/automation.py：每次啟動隔離 Context，操作及讀取 DOM。
  scenes/assertion.py：獨立斷言，回傳候選出參。
  run_demo.py：檢查入參、Worker 總期限、發布出參、HTML 報告。
  test_demo.py：成功鏈路、缺參攔截、斷言錯誤、超時與查無資料。

限制：
這是命令列垂直範例，HTML 管理原型尚未接到此執行器。
不包含管理 API、登入憑證保存、AI 服務或遠端瀏覽器畫面串流。
狀態與錯誤中的英文值是機器欄位；介面與指引使用繁體中文。
總期限限制自動化與斷言；產生本機報告、停止程序另需少量清理時間。
Windows 清理分支未實機驗證；團隊採用 Windows 時需補驗收。

注意：不要把 .venv、瀏覽器二進位、artifacts、登入資訊或 __pycache__ 提交到新工程版本庫。
