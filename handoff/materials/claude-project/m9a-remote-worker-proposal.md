# M9a 遠端 worker：設計與實作（2026-10-13，已實作，PR #23 待驗收）

使用者需求（10-13 03:50）：API 服務、資料庫、worker、檔案都在自己的電腦上；主要用有頭模式執行與測試，一跑起來電腦就被瀏覽器視窗占住。有一台專門跑 worker 的機器。**把 M9「分散式 worker 與調度」的這一小塊提前做**，現有的本機模式保持不變。編號用 **M9a**（插在 M6 之後、M5 之前；M9 其餘部分——排程、通知、S3、Docker Compose——不動）。

依據：ADR 0008（SQLite 只允許單一程序）、ADR 0010（MVP 先行）、M3 的 `JobSource` 抽象（rpa_worker 本身就不碰資料庫）、路線圖「Runner 從一開始就無狀態」。

驗收：
1. 在 worker 機器執行 `rpa worker --server … --token …`，Portal 的「Worker」頁看到它上線（瀏覽器、能不能顯示視窗、版本）。
2. 在 Portal 選「遠端」執行 BA-001（有頭）：瀏覽器視窗出現在 worker 機器，自己的電腦不跳視窗；報告、截圖、Trace 回到 Portal，跟本機執行看起來一樣。
3. 驗證 → 發布門檻照常（雜湊由遠端 runner 算、伺服器再比對）。
4. 試驗場序列 BA-001 → BA-002 在遠端跑通，整個序列在同一台 worker。
5. 需要登入的場景在遠端執行：用 Portal 上保存的角色登入狀態；自動登入更新後的狀態傳回 Portal。
6. 取消遠端執行中的任務：worker 終止瀏覽器；拔掉 worker 網路：一分鐘後執行標為「worker 失聯」。
7. 沒有登記任何遠端 worker 時，一切跟現在完全一樣。

## 一、架構：worker 主動向 Portal 領取任務（HTTP）

```
你的電腦                                         worker 機器
┌──────────────────────────────┐                 ┌───────────────────────────┐
│ rpa serve                     │                 │ rpa worker                 │
│  Portal 頁面＋/api  127.0.0.1:8080 │ ← 只有本機    │  RemoteJobSource（HTTP）   │
│  Worker API   0.0.0.0:8081     │ ←── HTTPS/HTTP ─┤  Worker（沿用 M3）         │
│  本機 worker（執行緒，照舊）     │   Bearer 權杖    │  rpa_runner.execute（子程序）│
│  SQLite、data/（照舊）          │                 │  本機測試網站 127.0.0.1:8765 │
└──────────────────────────────┘                 └───────────────────────────┘
```

- **只有 Portal 存取資料庫**（ADR 0008 不變）；遠端 worker 只透過 Worker API。原定 M9 的 Procrastinate（worker 直接連 PostgreSQL）改掉：worker 機器不需要資料庫帳密，也不用開資料庫的網路。之後換 PostgreSQL、多台 worker 一樣適用。新增 **ADR 0012**。
- **worker 主動連 Portal**（拉取）：只要 worker 機器連得到你電腦的一個埠；你的電腦不需要連 worker。
- **Worker API 用獨立的埠**（`rpa serve --worker-port 8081`，預設聽 0.0.0.0），**只有** `/worker-api/v1/*`，每個請求都要權杖。Portal 頁面與 `/api` 仍然只聽 127.0.0.1——M3 沒有登入，不能整個開放給區網。
- 遠端 worker 就是現在的 `rpa_worker.Worker`，換一個任務來源 `RemoteJobSource`（HTTP 用標準函式庫，不加相依）。本機 worker 照舊是伺服器內的執行緒、直接用資料庫。

## 二、Worker API（v1）

| 介面 | 做什麼 |
|---|---|
| `POST /worker-api/v1/hello` | 上線：名稱、版本、作業系統、已下載的瀏覽器、能不能顯示視窗。版本和 Portal 不同就拒絕（要兩邊 `git pull`） |
| `POST /worker-api/v1/claim` | 長輪詢（最多 25 秒）領取一個任務；回傳場景檔與腳本、入參、瀏覽器、網址、有頭／無頭、總期限、語言、角色登入設定與登入狀態、Secrets 的值 |
| `POST /worker-api/v1/runs/{id}/heartbeat` | 每 5 秒一次，可順便回報階段；回應 `{"cancel": true}` 就取消 |
| `PUT /worker-api/v1/runs/{id}/artifacts` | 上傳整個執行目錄（zip，大小上限；只接受執行目錄該有的檔名，不能含 `..`） |
| `PUT /worker-api/v1/runs/{id}/role-state` | 自動登入後更新的登入狀態 |
| `POST /worker-api/v1/runs/{id}/finish`、`…/fail` | 結果（result.json 的內容）或無法執行的原因；伺服器照 `RunQueue.finish/fail` 寫回，序列接著排下一個 |

- **權杖**：在 Portal 的「Worker」頁新增 worker 時產生，只顯示一次（附上整行啟動命令可以複製）；資料庫只存雜湊；可以停用。worker 機器上放在環境變數 `RPA_WORKER_TOKEN` 或 `--token-file`，不寫進命令列歷史。
- **租約**：領取時設 60 秒租約，每次心跳延長。過期 → 執行標為失敗「worker 失聯」（**不自動重跑**：可能已經有副作用）。worker 之後才回報結果 → 409，worker 丟棄。
- **Secrets 與登入狀態**只在領取的回應裡、只放 worker 的記憶體與暫存檔（只限本人、執行完刪除）；執行目錄上傳後刪除本機副本（`--keep-runs` 保留）。

## 三、調度（分派）

- 執行多一個欄位「**執行位置**」：本機／遠端／任一（`runs.target`），記錄由哪台 worker 執行（`runs.worker_id`）。
- 領取時只給「能跑」的任務：位置符合、瀏覽器有下載、有頭模式要有顯示器、版本相同；先進先出。
- 預設位置：Portal 設定「預設執行位置」，**預設是本機**（所以什麼都沒設定時跟現在一樣）；執行、驗證、序列的對話框可以改，只在登記過遠端 worker 後才出現這個選項。
- 有頭模式的檢查改看目標：本機看這台電腦，遠端看有沒有能顯示視窗的 worker；沒有線上的 worker 能接時，頁面顯示「等待可以執行的 worker」，可以取消。
- **試驗場序列整個在同一台 worker**：第一個節點由誰領取，後面的節點就固定給它（本機測試網站的資料、登入狀態一致）；它離線時後面的節點等著，可以取消。
- 一台 worker 一次一個任務（照 M3）；本機 worker 與各遠端 worker 可以同時跑，所以 Portal 這邊的同時執行數 = 1 + 線上的遠端 worker 數。`rpa serve --no-local-worker` 讓本機完全不跑。
- 錄製、逐步調試、人工登入仍在 Portal 這台電腦（要人操作）。
- 「排程」（定時執行）不在這一步，仍是 M9。

## 四、本機網址的問題

- 範例場景對 `http://127.0.0.1:8765`（測試網站）執行。**`rpa worker` 預設也在 worker 機器啟動自己的測試網站**，同樣的網址直接可用（`--no-testsite` 關閉）。
- 其他網址是 localhost／127.0.0.1 的場景送到遠端時，頁面提醒「遠端 worker 的 127.0.0.1 是它自己」。
- 真實的目標系統要從 worker 機器也連得到（公司網路、VPN）。

## 五、資料與頁面

- 遷移 0007：`workers`（id、名稱、權杖雜湊、停用、最後上線時間、版本、作業系統、瀏覽器、能否顯示、目前的執行）；`runs` 加 `target`、`worker_id`、`lease_until`；`workflow_runs` 加 `target`、`worker_id`；設定表（預設執行位置）。
- 頁面：「生產」選單加「Worker」：清單（線上／忙碌／離線、目前執行、最後上線）、新增（產生權杖與啟動命令）、停用、預設執行位置。執行報告與執行頁顯示由哪台 worker 執行，篩選加「執行位置」。
- 三種語言的訊息、文檔：新頁「遠端 worker」（worker 機器怎麼安裝、啟動、開機自動啟動）、架構與路線圖（M9a）、ADR 0012。

## 六、命令列

```
# 你的電腦
rpa serve --worker-port 8081            # 開啟 Worker API（聽 0.0.0.0:8081）
rpa serve --worker-port 8081 --no-local-worker

# worker 機器
export RPA_WORKER_TOKEN=…（Portal 產生）
rpa worker --server http://你的電腦:8081 [--name mac-mini] [--no-testsite] [--keep-runs]
```

worker 斷線、Portal 重啟時自動重連（逐步拉長間隔）。

## 七、測試

- 本機可跑：`RemoteJobSource` 對一個假的 HTTP 伺服器（打包、上傳、心跳取消、重連、409）。
- 伺服器（CI）：Worker API 用 TestClient——權杖、版本不符、領取的配對（位置、瀏覽器、顯示器）、租約過期、取消、上傳的檔名檢查、序列固定同一台 worker、登入狀態傳回。
- 端對端（CI，真實瀏覽器）：uvicorn 在執行緒跑 Portal＋Worker API，另一個執行緒跑遠端 worker（`--no-local-worker`），BA-001 → BA-002 在 Chromium 與 Firefox 通過；報告檔案回到 Portal。
- 手動驗收：管理 Portal › 手動驗收加一節「兩台電腦」。

## 八、使用者的決定（10-13 04:00）

1. 網路：worker 機器連得到使用者的電腦（拉取）。
2. worker 機器：**Windows**（文檔以 Windows 為例，含開機自動啟動）。
3. 傳輸：HTTP＋權杖（信任的區網）。
4. 預設執行位置：本機（沒問，照推薦；worker 頁可改）。

## 九、原本的選項（保留參考）

1. **網路**：worker 機器連得到你的電腦（同一個區網或 VPN）／只有你的電腦連得到 worker 機器（要改成推送，較麻煩）。
2. **worker 機器的作業系統**：macOS／Windows／有桌面的 Linux／沒有桌面的 Linux（只能無頭；那就解決不了「有頭占用電腦」的需求，除非用虛擬桌面）。
3. **傳輸**：同一個信任的區網上用 HTTP＋權杖（推薦，設定最少；Secrets 與登入狀態會以明文經過區網）／Worker API 用 HTTPS（`rpa serve` 自動產生自簽憑證，worker 第一次連線時確認指紋）。
4. **預設執行位置**：本機（推薦，跟現在一樣，要遠端時在對話框選）／有遠端 worker 在線時預設遠端。

## 十、實作備註

- 程式指紋（`rpa_worker.environment.code_fingerprint`）：rpa_core、rpa_runner、rpa_worker 所有檔案的雜湊（換行統一 LF），只提醒不拒絕；協定版本 `PROTOCOL = 1` 不同才拒絕。
- 兩個埠用同一個 uvicorn（`sockets=[portal, worker]`），`PortGateMiddleware` 依 `scope["server"]` 的埠號分流；`rpa serve` 設 `timeout_graceful_shutdown=5`，Ctrl+C 不必等長輪詢。
- `RunQueue.claim_run(worker_id, targets, accepts, lease_until)` 本機與遠端共用；第一次領取序列節點時寫 `workflow_runs.worker_id`，後續節點 `required_worker`。
- 遠端 worker 執行中被取消：`Services.cancel_run` 只對本機執行呼叫 `on_cancel`，遠端靠心跳回應 `{"cancel": true}`。
- 任務裡的 `login` 不含 state 路徑；worker 寫到 `worker-data/jobs/<run>/state.json`（0600），內容變了才 PUT role-state。
- 測試：apps/worker test_protocol、test_remote（本機可跑）；apps/server test_remote_worker_api（TestClient，base_url 帶 :8081）、test_remote_worker_flow（真實 uvicorn 兩個埠＋背景執行緒的 RemoteJobSource，Chromium／Firefox）；apps/cli test_worker_cli。
