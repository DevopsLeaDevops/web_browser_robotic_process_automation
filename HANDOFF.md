# 交接材料（2026-10-13）

給接下來一週自己動手改的你，以及下週回來接手的 Claude。
這份檔案不在文檔站裡（不用翻譯）。**改了什麼、做到哪，請記在最後的「交接紀錄」**，下週接手時會先讀那裡和 `git log`。

---

## 1. 現況

| 項目 | 狀態 |
|---|---|
| M0～M4、M6 自由試驗場 | 都在 main（M6 原本誤合併到別的分支，已由 #22 補進 main） |
| **M9a 遠端 worker** | **PR #23**，已改接到 main，CI 全綠（含 Windows、macOS，以及真實瀏覽器經過 Worker API 的端對端測試），**等你合併** |
| 兩台電腦的實機驗收 | **還沒做**：CI 只模擬了同一台電腦上的遠端 worker |
| M5 AI 助手 | 等你決定 AI 模型與資料去向（見第 4 節） |
| PR #19（Dependabot：setup-uv 10.3.0） | 可以合併 |
| 舊分支 `docs/roadmap-m6-first`、`m6/playground`、`m6/main` | 已經合併，可以在 GitHub 上刪掉 |

路線圖順序：M6 → **M9a（進行中）** → M5（MVP 完成）→ M7 → M8 → M9。見 `docs/roadmap.html`。

## 2. M9a 遠端 worker 做了什麼

設計：`docs/adr/0012-remote-workers.html`；操作：`docs/develop/remote-worker.html`；
管理 Portal 的說明：`docs/design/portal.html#remote-workers`（手動驗收第 8 步是兩台電腦的流程）。

- `rpa serve --worker-port 8081` 另開一個埠，只有 Worker API（`/worker-api/v1`，每個請求都要權杖）；管理頁面仍然只在 127.0.0.1。
- 「場景生產 › 遠端 Worker」頁：登記 worker、產生權杖（只顯示一次）、停用、重新產生權杖、刪除、預設執行位置。
- worker 機器：`uv run rpa worker --server http://你的IP:8081 --name win-01`（權杖放環境變數 `RPA_WORKER_TOKEN`）。
- 執行、驗證、序列的表單多了「執行位置」：本機／遠端 worker／任一。預設本機，所以沒有登記 worker 時和以前一樣。
- 60 秒沒有心跳就判定 worker 失聯，那次執行標為失敗，不自動重跑。試驗場序列整個固定在第一個節點的 worker。

### 程式地圖

| 位置 | 內容 |
|---|---|
| `apps/worker/src/rpa_worker/protocol.py` | Worker API 的資料格式（任務、zip 打包與安全解開、常數） |
| `apps/worker/src/rpa_worker/environment.py` | 能否顯示視窗、已下載的瀏覽器、程式指紋、區網位址 |
| `apps/worker/src/rpa_worker/remote.py` | `WorkerClient`、`RemoteJobSource`（長輪詢、心跳、上傳、重試） |
| `apps/server/src/rpa_server/dispatch.py` | `WorkerHub`：登記、權杖、領取時的配對、租約、結果寫回 |
| `apps/server/src/rpa_server/worker_api.py` | `/worker-api/v1` 的路由 |
| `apps/server/src/rpa_server/jobs.py` | `RunQueue`：本機與遠端共用的領取（`claim_run`）與寫回（`complete`、`fail_run`） |
| `apps/server/src/rpa_server/services.py` | `resolve_target`、`can_display`、`resolve_headless`、`locations` |
| `apps/server/src/rpa_server/middleware.py` | `PortGateMiddleware`：兩個埠各自只能用自己的路徑 |
| `apps/server/src/rpa_server/migrations/versions/0007_remote_workers.py` | `workers`、`settings`；`runs`、`workflow_runs` 的新欄位 |
| `apps/server/src/rpa_server/templates/workers.html`、`static/portal.js`（`bindWorkers`、`bindTargetChoice`） | 頁面 |
| `apps/cli/src/rpa_cli/worker.py`、`serve.py` | `rpa worker`；`rpa serve --worker-port/--worker-host/--no-local-worker` |
| 測試 | `apps/worker/tests/test_protocol.py`、`test_remote.py`；`apps/server/tests/test_remote_worker_api.py`、`test_remote_worker_flow.py`；`apps/cli/tests/test_worker_cli.py` |

## 3. 接下來要做的事（建議順序）

### 3.1 合併 #23，做兩台電腦的驗收（必做）

照 `docs/develop/remote-worker.html` 做一次（大約 20 分鐘）：

1. 你的電腦：`uv run rpa serve --data data-check --worker-port 8081`，允許防火牆的連入詢問。
2. Portal「場景生產 › 遠端 Worker」新增 `win-01`，複製權杖與 PowerShell 命令。
3. Windows 機器：跑 `scripts\setup.ps1` 安裝，再貼上命令啟動 `rpa worker`；worker 頁要變成「線上」。
4. 選「遠端 worker」＋有頭模式執行 BA-001：視窗出現在 Windows 那台，你的電腦不跳視窗；報告「通過」、截圖看得到、執行頁顯示「執行的電腦：win-01」。
5. 用「遠端 worker」跑 BA-001 → BA-002 的序列：兩個節點都在 win-01。
6. 執行中在 Windows 按 Ctrl+C：Portal 上那次變成「已取消」。拔掉 Windows 的網路：約一分鐘後變成失敗「worker 失聯」。

**有問題請記在第 6 節**：哪一步、看到的訊息、`rpa worker` 終端機的輸出。Windows 上最可能出問題的是防火牆、路徑與換行；雜湊不符（驗證通過卻被標失敗）也請特別記下來。

### 3.2 M9a 還沒做的小項目（選做，你可以自己寫）

原本設計提到、但這次沒做的：

1. **執行報告的篩選加「執行位置」**：`render.run_filters` 加一個選單，`Services.list_runs` 加篩選條件（`Run.target` 或 `Run.worker_id`），`pages.runs` 傳參數。
2. **網址是 localhost／127.0.0.1 時提醒**：選「遠端」而場景網址是本機位址時，`run_form.html` 顯示提醒（測試網站 8765 除外，worker 有自己的）。
3. **排隊中等待 worker 的提示**：執行頁狀態是「排隊中」、位置是遠端、而沒有線上的 worker 能接時，顯示「等待可以執行的 worker」（`WorkerHub.list_workers()` 看狀態）。
4. **HTTPS**（選用）：`rpa serve` 產生自簽憑證、worker 第一次連線確認指紋。只有網路不信任時才需要。

### 3.3 M5 AI 助手：需要你決定

設計提案在 Claude 專案的 `claude/m5-design-proposal.md`。開工前要決定：

- **用哪個 AI 模型**：Claude API、公司內部模型、還是本機模型？
- **資料去向**：公司內部頁面的內容（DOM、截圖、場景）能不能送到外部 API？如果不能，就要用內部或本機模型。

決定後寫在第 6 節，下週直接開工。

## 4. 修改時的規則（CI 會檢查）

詳細規範在 `docs/develop/conventions.html`、`docs/develop/writing-docs.html`。

**每次提交前在專案資料夾執行：**

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyright                      # strict 模式
uv run pytest -m "not browser"      # 快；要跑真實瀏覽器的就拿掉 -m
uv run python tools/i18n.py check   # 簡中是否同步、英文是否跟上繁中
```

- **改資料庫模型就要新增遷移**：下一個是 `0008`，`down_revision = "0007"`；`test_migrations.py` 會比對模型與遷移，也要更新資料表清單（依字母排序）。
- **介面文字不能寫死在程式或樣板裡**：放在 `locales/zh-Hant.json`、`en.json`（三個語言的鍵與 `{佔位符}` 要相同）；`zh-Hans.json` 由 `uv run python tools/i18n.py sync` 從繁中產生，不要手改。`test_render.py` 會檢查英文頁面沒有殘留中文。給 JavaScript 用的訊息（`js.` 開頭）要加到 `render.js_messages()`，佔位符寫成 `{{name}}`。
- **文檔是 HTML**：新頁面登記在 `docs/assets/nav.js`；英文頁放 `docs/en/` 同路徑，翻譯完執行 `uv run python tools/i18n.py stamp docs/en/路徑.html`；最後 `uv run python tools/i18n.py sync` 產生簡中。
- **不要改** `apps/server/src/rpa_server/static/portal.css`、`shell.js`：它們是設計系統的複製品，要改請先改 `docs/design-system/`。自己的樣式放 `portal-app.css`。
- **提交訊息**：`feat(m9a): …`、`fix(…): …`、`docs: …`；開分支、開 PR，CI 綠了再合併。
- **CI 失敗**：錯誤會標在 PR 的「Files changed」對應的行上（`tools/ci_annotations.py`）。
- 一個小技巧：提交訊息裡寫 `[bootstrap]` 推上去，GitHub Actions 會自動產生 `uv.lock` 與簡中並提交回分支（記得之後 `git pull`）。

## 5. 下週接手時（給 Claude）

1. 讀這份檔案的第 6 節與 `git log origin/main`（從 2026-10-13 之後），以及 GitHub 上開著的 PR。
2. 讀 Claude 專案的 `claude/m1-progress.md`（工作紀錄與雲端環境的注意事項）、`claude/m9a-remote-worker-proposal.md`、`claude/m5-design-proposal.md`。
3. 先處理第 6 節裡的問題與實機驗收的回報，再依使用者的決定開工 M5。
4. 交接完成後刪掉這份檔案，或把有用的部分移到文檔站。

## 6. 交接紀錄（請你填寫）

> 每次做了什麼就加一條，格式隨意。例如：
> - 10-15：合併 #23。兩台電腦驗收第 4 步失敗：Windows 上 `rpa worker` 顯示「……」。
> - 10-16：加了執行報告的「執行位置」篩選（PR #25）。
> - M5 決定：用 ……；公司內部頁面的內容可以／不可以送到外部 API。

-
