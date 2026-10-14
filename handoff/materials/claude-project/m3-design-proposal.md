# M3 管理 Portal：設計提案（2026-10-10，待確認）

依據：ADR 0008（SQLite + SQLAlchemy 2.0 + Alembic）、ADR 0010（MVP 先行）、ADR 0011（FastAPI + Jinja）、系統架構頁（apps/server、apps/worker），以及 MVP 原型「建置指引」裡的資料模型與 API 提案。M3 建在 M2（PR #10）之上，**PR #10 合併後才開工**。

驗收：在瀏覽器內完成「建立 → 驗證 → 發布 → 執行 → 看報告」。

## 一、元件

| 元件 | 位置 | 內容 |
|---|---|---|
| rpa-server | `apps/server`（`rpa_server`） | FastAPI：`/api/*` JSON API 與 Jinja 頁面；靜態檔直接用 `docs/design-system` 的 portal.css、shell.js |
| rpa-worker | `apps/worker`（`rpa_worker`） | 從資料庫領取 queued 的執行，呼叫 `rpa_runner.execute`，回寫狀態。M3 在伺服器程序內以背景執行緒跑、一次一個（ADR 0008：SQLite 只允許單一程序） |
| 資料 | `RPA_DATABASE_URL`（預設 `data/rpa.db`）、`RPA_DATA_DIR`（預設 `data/`） | SQLite 存元資料；檔案目錄存版本內容與執行目錄 |
| 命令列 | `rpa serve [--host 127.0.0.1] [--port 8000]` | 啟動伺服器與 worker；預設只聽本機 |

rpa-runner 要補一個小改動：`execute(..., cancel=threading.Event)`，worker 收到取消時終止程序群組，狀態為 cancelled（目前只處理 Ctrl+C）。

## 二、資料模型

```
scenes      id（＝DSL 的 id，例如 ba-001；永不重用，只能封存）、name、category、
            default_url、published_revision、archived、created_at
revisions   id、scene_id、number（1, 2, 3…）、content_hash（場景檔＋腳本的 sha256）、
            status（draft → validating → passed / failed；published）、created_at
            內容存在 data/scenes/<id>/revisions/<number>/（scenario.yaml、automation.py…）
runs        id（沿用 M2 的執行編號）、scene_id、revision_id、purpose（validation / execution）、
            status（queued → running → passed / failed / timed_out / cancelled）、
            engine、input、output、error、idempotency_key（唯一）、時間戳
            產物在 data/runs/<id>/（就是 M2 的執行目錄）
```

規則：
- **版本不可變**：每次儲存都建立新版本；儲存時帶 `baseRevision`，不是最新版本就回 409。
- **發布門檻**：只有「狀態為 passed、而且通過那次驗證執行的場景快照雜湊等於這個版本的雜湊」的版本可以發布，並要使用者在頁面確認。改了內容就是新版本，舊的驗證結果不能拿來發布。
- **一般執行只用已發布版本**；驗證執行可以跑任何版本。

## 三、API（沿用原型提案，M3 範圍）

| 介面 | 用途 |
|---|---|
| `GET /api/scenes`、`POST /api/scenes` | 清單（分類、搜尋）、建立 |
| `GET /api/scenes/{id}`、`PATCH /api/scenes/{id}` | 詳情；改名稱、分類、預設網址、封存 |
| `POST /api/scenes/{id}/revisions` | 儲存新版本（先跑 `rpa validate` 的校驗；有錯誤回 422 並附行號） |
| `POST /api/revisions/{id}/validate` | 用指定入參建立驗證執行 |
| `POST /api/revisions/{id}/publish` | 發布（檢查發布門檻） |
| `POST /api/scenes/{id}/runs` | 以已發布版本執行；先校驗入參，202 回執行編號；`idempotencyKey` 防止重複送出 |
| `GET /api/runs`、`GET /api/runs/{id}` | 報告清單（分類、場景多選、結果、時間）與單次狀態 |
| `POST /api/runs/{id}/cancel` | 取消；不回滾已經發生的外部動作 |
| `GET /runs/{id}/files/{name}` | 報告與產物；只回傳執行目錄內的檔案，不暴露絕對路徑 |

調試工作階段（`/api/debug-sessions`）在 M4，編排（`/api/workflows`）在 M6。

## 四、頁面（照原型的頂部一級、左側二級）

- **場景管理**：統計卡、搜尋與分類篩選、場景卡片；空資料庫時可一鍵匯入 `scenarios/demo`。
- **場景詳情**：
  - 總覽：已發布版本、最近執行、預設網址
  - 場景內容：YAML 編輯區，儲存時顯示校驗錯誤（檔案行號、步驟、欄位）
  - 入參與出參：依 Schema 顯示表格；執行表單依入參 Schema 自動產生，帶入預設值
  - 版本：歷史、每個版本的驗證結果、發布按鈕
- **執行報告**：依分類、場景（多選）、結果篩選；重新整理後仍可查看歷史；點進去看 M2 的 report.html。
- 執行進度用每秒輪詢 `GET /api/runs/{id}`（伺服器推送事件之後再說）。
- 「場景生產」「自由試驗場」在導覽中保留位置，標示 M4、M6。

## 五、請確認的決定（我推薦第一個選項）

1. **場景內容在 M3 以 YAML 文字編輯，入參與出參先做唯讀表格**／M3 就做入參與出參的表單編輯（要能把表單寫回 YAML，註解會遺失）。
2. **worker 在伺服器程序內的背景執行緒、一次只跑一個**／一開始就是獨立程序（`rpa worker`）。
3. **M3 不做登入，預設只聽 127.0.0.1**（多用戶在 M8）／M3 先做簡單的密碼保護。
4. **執行進度用輪詢**／用伺服器推送事件（SSE）。
5. **場景 id 就是 DSL 的 id**（例如 ba-001），存檔時不一致就拒絕／系統另外編號（例如 BA-001），DSL 的 id 只當顯示。

## 六、測試與相依套件

- 新相依：fastapi、uvicorn、sqlalchemy、alembic（jinja2 已有）；測試用 httpx。頁面以 fetch 送 JSON，不需要 python-multipart。
- API 測試用 FastAPI TestClient + 暫存 SQLite。
- 驗收測試：Playwright 操作 Portal 跑完「建立 → 驗證 → 發布 → 執行 → 看報告」，場景本身在 Chromium 與 Firefox 各跑一次。
- PostgreSQL 的 CI 矩陣在 M8 加入（ADR 0008 已註明）。
