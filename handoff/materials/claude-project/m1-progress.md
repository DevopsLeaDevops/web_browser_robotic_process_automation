# 工作紀錄（#8～#20 已合併；#22 M6 進 main、#23 M9a 待合併）

## 2026-10-14 追加（交接補齊）

- **main 已合併**（UTC）：#23 M9a（10-14 03:54，151a935）、#25 你寫的受限語言模式安裝修正（03:58，e3daa6e）、#24 交接材料（03:58，8f91944）、#19 setup-uv 10.3.0（06:13，30fe7b8）。main CI 全綠。
- **人工驗收**：M9a 兩機驗收沒有通過紀錄。10-13 20:52（太平洋時間）回報 Windows「沒有 worker 這個命令」，原因是 #23 當時未合併；之後沒有回報。
- **交接包**：倉庫 `handoff/`（PR「docs(handoff): 補齊交接…」，分支 `docs/handoff-complete`）：總入口、驗收紀錄、未完成工作、決定與工作規則、運作環境、研發與 Git 方法、時間軸、原始材料（本專案 8 份文件的原文在 `handoff/materials/claude-project/`）。**接手先讀 `handoff/index.html`。**
- `ci/diag-windows`（10-11～12，已刪分支）結論：Firefox 初始化全新設定檔造成約 3 秒後的停頓；修正是預熱範本＋複製（`rpa_runner/profiles.py`，#12）。沒有遺留問題。
- 舊分支盤點：沒有獨有工作；可全刪。
- 規則：本日誌之後只追加、不覆蓋（10-13 曾整份改寫，之前的原文已不在）。

> 新 session 先讀這份、`claude/plan-v2-proposal.md`、`claude/m3-design-proposal.md`、`claude/m4-design-proposal.md`、`claude/m6-design-proposal.md`、`claude/m9a-remote-worker-proposal.md`、`claude/m5-design-proposal.md`，再看 GitHub 上的分支與 PR。

## 先看這裡（2026-10-13 18:54）

使用者週用量剩 12%，這週由使用者自己改。交接材料是 **PR #24 的 `HANDOFF.md`**（合併後在 main 根目錄）；**下週接手先讀它的第 6 節「交接紀錄」**與 `git log origin/main`。#22 已合併；#23 已 rebase 到 main、base 改成 main（內容不變，CI 綠），等使用者合併。

## 目前狀態（2026-10-13）

- M1～M4、#12～#18、#20（路線圖：M6 先於 M5）都在 main。
- **#21（M6）合併時 base 是 `docs/roadmap-m6-first`，所以 M6 沒進 main。** 已把它的 squash 提交 cherry-pick 到 `m6/main`，開 **PR #22**（base main，內容與那個分支完全相同）。合併後可刪 `docs/roadmap-m6-first`、`m6/playground`。
- 使用者指示（10-13 03:50）：主要用有頭模式，執行時電腦被占住；有一台專門跑 worker 的機器 → **提前做 M9 的遠端 worker，編號 M9a**（插在 M6 之後、M5 之前），本機模式保持。決定：worker 主動連使用者電腦、worker 機器是 **Windows**、HTTP＋權杖、預設執行位置本機。
- **PR #23 https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/pull/23**（分支 `m9a/remote-worker`，**base 是 `m6/main`**）。#22 squash 合併後：`git rebase --onto origin/main <m6/main 的提交 93fd8cd> m9a/remote-worker`、force push、把 #23 的 base 改成 main（PATCH base）。
- M5 仍要使用者決定模型與資料去向（`claude/m5-design-proposal.md` 第 1 點）。

## M9a 實作摘要（設計見 claude/m9a-remote-worker-proposal.md、ADR 0012）

- `rpa_worker.protocol`（JobPayload、zip 打包／安全解開、常數）、`environment`（has_display、installed_browsers、code_fingerprint、lan_address、WorkerInfo）、`remote`（WorkerClient、RemoteJobSource；notify 事件給 CLI）；`Job.locale`
- `rpa_server.dispatch.WorkerHub`（登記、權杖、hello、claim 長輪詢、heartbeat、artifacts、role-state、finish/fail、租約 reaper、預設執行位置）；`worker_api.py`（/worker-api/v1）；`middleware.PortGateMiddleware`；`jobs.RunQueue.claim_run/complete/fail_run` 共用；`Services.queue/workers/resolve_target/can_display/resolve_headless/locations`；遷移 0007
- 頁面 `/workers`（workers.html）、`_macros.location_field`、run_form／workflow 的執行位置、報告顯示 worker；JS `bindWorkers`、`bindTargetChoice`
- CLI：`rpa worker`（apps/cli/src/rpa_cli/worker.py）、`rpa serve --worker-port/--worker-host/--no-local-worker`
- 文檔：docs/adr/0012-remote-workers.html、docs/develop/remote-worker.html、portal.html#remote-workers 與手動驗收第 8 步、architecture、roadmap、index、ADR 0003／0010 註記（en 都已翻譯並 stamp）

## 環境（2026-10-13 的 session）

- PyPI 被擋（DNS）。系統 Python 3.13 有 pydantic、starlette、uvicorn、jinja2、playwright（只有 Chromium）；**沒有 fastapi、sqlalchemy、alembic、httpx2、opencc**。
- `.venv`：`uv venv --offline --system-site-packages .venv`；site-packages 放 `workspace.pth`（各套件 src、`~/.local/share/uv/tools/pytest/lib/python3.13/site-packages`）與假的 `rpa_*-0.1.0.dist-info/METADATA`。
  - 本機測試：`.venv/bin/python -m pytest -q -p no:cacheprovider packages apps/worker apps/cli/tests tests/docs tests/i18n/test_catalogs.py tests/i18n/test_tool.py tests/examples -m "not browser"`
  - 伺服器測試要 sqlalchemy，只能靠 CI。樣板可以本機檢查：把 test_render.py 複製成 apps/server/tests/test_zz_local.py，去掉 debugging／services 的 import（SceneNeeds 從 services.py 複製）與 _m4_pages，跑完刪掉。
- pyright：`/home/claude/venv-static`（.pth：各 src、repo 根、`/home/claude/deps/{fastapi,sqlalchemy/lib,alembic,httpx}`（GitHub clone，**只做靜態檢查，不執行**）、pytest site-packages、`/usr/local/lib/python3.13/dist-packages`、`/usr/lib/python3/dist-packages`）；設定 `/home/claude/pyright/pyrightconfig.json`；`~/.local/share/uv/tools/pyright/bin/pyright -p …`。剩 3 個 `tools.*` stub 錯誤是環境造成的，忽略。
- ruff：`~/.local/share/uv/tools/ruff/bin/ruff`
- GitHub：先 `mcp__claude-code-remote__add_repo`（access push）才能用 gh；**推送與開 PR 要使用者同意**（自動模式會擋「Unrequested Commit」）。
- **bootstrap**：提交訊息含 `[bootstrap]` 推送就會跑（uv.lock、簡中、ruff、pyright、pytest not browser），bot 會提交，記得 pull。它的「檢查」失敗時沒有 annotations：開 PR 讓 CI 跑，再讀 `gh api repos/…/check-runs/<job>/annotations?per_page=50`。
- 訊息目錄新增鍵：scratchpad 的 `addmsg.py <locales 目錄> <新訊息.json>`（{"鍵": ["繁中","English"]}，加在最後；簡中先放繁中，bootstrap 重新產生）；JS 訊息佔位符寫 `{{name}}`。
- 英文頁改完：`.venv/bin/python tools/i18n.py stamp docs/en/…`（不需要 OpenCC）；新英文頁的 `data-root` 和繁中同層級（例如 `../`）。
- 不要在 Bash 寫 `cat > 檔案` 而沒有輸入；PR 內容用 Write 寫到 scratchpad。

## 下一步

1. 使用者合併 #22；rebase #23 到 main
2. 使用者在 Windows 機器照「遠端 worker」文件試（管理 Portal › 手動驗收第 8 步）
3. 使用者決定 M5 的模型與資料去向，之後開工 M5
4. Dependabot 的 uv 群組更新在 main 仍失敗；PR #19（setup-uv 10.3.0）可以合併
