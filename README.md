# 瀏覽器 RPA

瀏覽器自動化場景的生成、管理與執行平台。團隊共用、多用戶、面向內部系統。

共同開發（Claude、ChatGPT／Codex 與使用者）：從 [AGENTS.md](AGENTS.md) 進入[共用協作流程](handoff/collaboration.html)，再查看[本次任務紀錄](handoff/tasks/index.html)。Claude 的 [CLAUDE.md](CLAUDE.md) 使用同一份規則。

> 文檔以 HTML 撰寫，放在 [`docs/`](docs/)（見 [ADR 0005](docs/adr/0005-html-docs.html)），有三種語言：
> 繁體中文 `docs/index.html`、简体中文 `docs/zh-Hans/index.html`、English `docs/en/index.html`。
> GitHub 上只能看到原始碼，請在本機直接開啟，或執行：
>
> ```bash
> uv run python -m http.server -d docs 8000   # 然後瀏覽 http://localhost:8000（英文版在 /en/）
> ```

## 快速開始

一條命令裝好環境並跑完測試（macOS、Linux；Windows 用 `scripts\setup.ps1`），說明見 `docs/develop/quickstart.html`：

```bash
./scripts/setup.sh
```

或手動執行：

```bash
uv sync                              # 安裝全部套件與開發工具
uv run playwright install chromium firefox   # 下載瀏覽器
uv run pytest                        # 跑測試
uv run rpa --version
uv run rpa validate scenarios/       # 校驗範例場景
uv run python -m testsite &          # 本機測試網站（127.0.0.1:8765）
uv run rpa run scenarios/demo/ba-001.yaml -i title=測試   # 真實執行一個場景，報告在 runs/
uv run rpa serve                     # 管理 Portal：http://127.0.0.1:8080，一起啟動測試網站（資料在 data/）
uv run rpa serve --data data-m4      # 另用一份全新的資料夾（例如驗收新版本）；見 docs/design/portal.html#data-folder
```

完整說明見 `docs/develop/setup.html`；在 Mac 上從零開始的逐步說明見 `docs/develop/macos.html`。

## 目前進度

> 交接材料（2026-10-13）：[`handoff/index.html`](handoff/index.html)；專案脈絡與對話備忘：[`handoff/history.html`](handoff/history.html)。

方案 v2：結合 MVP 原型（`docs/prototypes/mvp/`），先交付單機、單使用者的 MVP。
M1 場景 DSL、M1.1 場景契約、M2 Runner 已完成：`rpa run` 在 Chromium 或 Firefox 中真實執行場景，產生執行目錄與報告。
M3 管理 Portal 已完成：`rpa serve` 在瀏覽器裡建立、驗證、發布、執行場景並查看報告（`docs/design/portal.html`）。
M4 場景生產與登入進行中：錄製（`rpa record` 或 Portal）轉成 DSL 草稿、逐步調試、每個角色獨立的登入狀態與 needs_login、入參出參的表單編輯。
範例在 `scenarios/`，規格見 `docs/design/dsl.html`。路線圖見 `docs/roadmap.html`。

M10 桌面端分發（設計中，2026-10-15）：錄製端（macOS）與 Worker（Windows）以桌面 App 分發，見 [桌面端分發](docs/design/desktop.html) 與 [ADR 0014](docs/adr/0014-desktop-apps.html)；M5、M8、M9 其餘部分往後放。

M6 DAG 組合場景已完成（#28，2026-10-14 合併）：DAG 畫布、四種入參來源、組合場景卡片管理與舊序列相容。示範場景與舊資料已人工驗收；實際業務系統與兩台電腦的驗收列在[未完成工作](handoff/open-work.html#m6-gaps)。詳見 [任務紀錄](handoff/tasks/20261014-dag-composite-scenes.html) 與 [Portal 設計](docs/design/portal.html#playground)。
