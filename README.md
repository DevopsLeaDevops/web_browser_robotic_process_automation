# CI 運行耗時紀錄

更新：2026-10-22 08:17 America/Los_Angeles（PDT，UTC−07:00）。共 292 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 147（0） | 81（0） | 2.9 分（0.0 分） | 5.4 分（0.0 分） | 0.0 分（0.0 分） | 693／311／0 分（0／0／0 分） |
| 桌面端建置 | 107（0） | 81（0） | 3.9 分（0.0 分） | 5.2 分（0.0 分） | 0.1 分（0.0 分） | 10／303／275 分（0／0／0 分） |
| 伺服器分發包 | 5（0） | 4（0） | 1.8 分（0.0 分） | 10.3 分（0.0 分） | 0.1 分（0.0 分） | 15／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 30（0） | 15（0） | 3.1 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 150／99／35 分（0／0／0 分） |
| 每晚完整測試 | 2（0） | 0（0） | 40.0 分（0.0 分） | 40.7 分（0.0 分） | 0.0 分（0.0 分） | 80／80／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 82 | 285 | 197 | 76 | 558 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 08:10 America/Los_Angeles（PDT，UTC−07:00），合計 578 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 31.0（27.9） | 29 | `apps/server/tests/test_api.py` |
| 31.0（27.9） | 29 | `apps/server/tests/test_api.py` |
| 28.3（28.3） | 24 | `apps/server/tests/test_production_api.py` |
| 28.3（28.3） | 24 | `apps/server/tests/test_production_api.py` |
| 27.6（27.6） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 27.6（27.6） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 21.7（21.7） | 20 | `apps/server/tests/test_recorder_api.py` |
| 21.7（21.7） | 20 | `apps/server/tests/test_recorder_api.py` |
| 18.1（18.1） | 11 | `apps/server/tests/test_gitsync.py` |
| 18.1（18.1） | 11 | `apps/server/tests/test_gitsync.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 08:10 America/Los_Angeles（PDT，UTC−07:00），合計 1024 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 75.5（113.0） | 7 | `apps/server/tests/test_portal.py` |
| 75.5（113.0） | 7 | `apps/server/tests/test_portal.py` |
| 46.6（82.4） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 46.6（82.4） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 39.0（62.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.0（62.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.4（61.8） | 5 | `apps/server/tests/test_production_flow.py` |
| 38.4（61.8） | 5 | `apps/server/tests/test_production_flow.py` |
| 37.6（54.4） | 2 | `apps/server/tests/test_replay_flow.py` |
| 37.6（54.4） | 2 | `apps/server/tests/test_replay_flow.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 08:10 America/Los_Angeles（PDT，UTC−07:00），合計 3545 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 491.2（377.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 491.2（377.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 368.0（377.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 291.9（171.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 191.1（167.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 191.1（167.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 189.3（151.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 189.3（151.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 171.3（171.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 171.3（171.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 717 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 76.2（69.3） | 9 | `apps/server/tests/test_portal.py` |
| 74.1（68.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.1（66.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 50.3（46.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.2（43.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.6（45.6） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 44.7（43.6） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 37.3（37.3） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.2（15.3） | 21 | `apps/server/tests/test_remote_worker_api.py` |
| 18.4（17.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 716 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.7（78.6） | 9 | `apps/server/tests/test_portal.py` |
| 75.2（73.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.3（76.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.1（49.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.6（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.1（47.1） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 45.0（46.0） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 39.7（39.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.1（19.3） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.8（16.8） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 530 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.4（77.9） | 9 | `apps/server/tests/test_portal.py` |
| 74.2（72.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.1（78.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 48.3（48.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.2（46.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.0（47.0） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 38.9（39.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 37.3（38.1） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 17.0（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.7（16.7） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 536 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.1（77.9） | 9 | `apps/server/tests/test_portal.py` |
| 75.6（72.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.1（75.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.8（47.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.9（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.2（47.2） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 39.7（40.4） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 37.1（37.7） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.1（19.4） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.7（16.7） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1007 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.7（110.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.1（99.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 97.3（111.8） | 9 | `apps\server\tests\test_portal.py` |
| 68.6（77.3） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.1（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.1（56.9） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 51.4（51.4） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 51.2（53.5） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 37.7（37.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 29.3（29.3） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 683 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.9（114.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 96.6（104.5） | 9 | `apps\server\tests\test_portal.py` |
| 93.5（98.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 66.0（72.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 61.4（64.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 52.2（52.2） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 50.3（54.9） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 44.4（46.0） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 27.2（27.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 22.7（25.9） | 4 | `apps\server\tests\test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 664 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 100.5（113.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 92.7（102.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 92.3（98.8） | 9 | `apps\server\tests\test_portal.py` |
| 64.2（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 60.5（62.9） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 51.5（51.5） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 49.1（53.0） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 43.1（45.4） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 26.5（26.5） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 22.7（23.7） | 4 | `apps\server\tests\test_recorder_flow.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-22 08:10 | CI | PR | claude/project-thread-ab62tv | failure | 6.9 分 | 0.1 分 | [#39800058876 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058876/attempts/2) |
| 10-22 07:57 | CI | PR | claude/project-thread-ab62tv | failure | 3.6 分 | 0.0 分 | [#39800058876](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058876/attempts/1) |
| 10-22 07:57 | 伺服器分發包 | PR | claude/project-thread-ab62tv | success | 1.8 分 | 0.1 分 | [#39800059052](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800059052/attempts/1) |
| 10-22 07:57 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 5.2 分 | 0.1 分 | [#39800058923](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058923/attempts/1) |
| 10-22 07:57 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | failure | 15.2 分 | 0.1 分 | [#39800058860](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058860/attempts/1) |
| 10-22 07:55 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | cancelled | 1.6 分 | 0.1 分 | [#39800025722](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025722/attempts/1) |
| 10-22 07:55 | 伺服器分發包 | PR | claude/project-thread-ab62tv | cancelled | 0.0 分 | 0.0 分 | [#39800025740](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025740/attempts/1) |
| 10-22 07:55 | CI | PR | claude/project-thread-ab62tv | cancelled | 1.7 分 | 0.1 分 | [#39800025834](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025834/attempts/1) |
| 10-22 07:55 | 桌面端建置 | PR | claude/project-thread-ab62tv | cancelled | 1.7 分 | 0.0 分 | [#39800025261](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025261/attempts/1) |
| 10-22 07:33 | CI | 推送 | main | failure | 13.3 分 | 0.1 分 | [#39796583943](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796583943/attempts/1) |
| 10-22 07:33 | 桌面端建置 | 推送 | main | success | 3.4 分 | 0.0 分 | [#39796583661](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796583661/attempts/1) |
| 10-22 07:32 | 伺服器分發包 | 推送 | main | success | 1.9 分 | 0.1 分 | [#39796582221](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796582221/attempts/1) |
| 10-22 07:32 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 3.6 分 | 0.0 分 | [#39796459340](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459340/attempts/1) |
| 10-22 07:32 | CI | PR | claude/project-thread-ab62tv | failure | 6.7 分 | 0.0 分 | [#39796459295](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459295/attempts/1) |
| 10-22 07:32 | 伺服器分發包 | PR | claude/project-thread-ab62tv | success | 10.3 分 | 0.1 分 | [#39796459275](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459275/attempts/1) |
| 10-22 07:29 | CI | 推送 | main | cancelled | 4.3 分 | 0.0 分 | [#39795916099](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795916099/attempts/1) |
| 10-22 07:28 | 桌面端建置 | 推送 | main | cancelled | 0.2 分 | 0.0 分 | [#39795916087](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795916087/attempts/1) |
| 10-22 07:26 | CI | PR | feat/macos-worker | failure | 5.0 分 | 0.0 分 | [#39795568711](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795568711/attempts/1) |
| 10-22 07:24 | CI | PR | feat/macos-worker | cancelled | 0.0 分 | 0.0 分 | [#39795465612](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795465612/attempts/1) |
| 10-22 07:24 | 桌面端建置 | PR | feat/macos-worker | cancelled | 1.7 分 | 0.0 分 | [#39795465789](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795465789/attempts/1) |
| 10-22 07:18 | 伺服器分發包 | 推送 | main | success | 0.1 分 | 0.0 分 | [#39794604622](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604622/attempts/1) |
| 10-22 07:18 | 一鍵安裝腳本 | 推送 | main | failure | 1.3 分 | 4.0 分 | [#39794604600](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604600/attempts/1) |
| 10-22 07:18 | 桌面端建置 | 推送 | main | success | 3.7 分 | 0.0 分 | [#39794604647](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604647/attempts/1) |
| 10-22 07:18 | CI | 推送 | main | cancelled | 10.5 分 | 0.1 分 | [#39794604795](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604795/attempts/1) |
| 10-22 06:49 | 桌面端建置 | PR | feat/macos-worker | success | 0.2 分 | 0.1 分 | [#39790298065](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39790298065/attempts/1) |
| 10-22 06:49 | CI | PR | feat/macos-worker | success | 2.5 分 | 0.1 分 | [#39790297868](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39790297868/attempts/1) |
| 10-22 06:43 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 3.9 分 | 0.0 分 | [#39789364884](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39789364884/attempts/1) |
| 10-22 06:43 | CI | PR | claude/project-thread-ab62tv | failure | 13.2 分 | 0.1 分 | [#39789364904](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39789364904/attempts/1) |
| 10-22 06:35 | CI | PR | feat/macos-worker | success | 12.9 分 | 0.0 分 | [#39785688742 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785688742/attempts/2) |
| 10-22 06:26 | CI | PR | feat/linux-server-package | success | 1.4 分 | 0.0 分 | [#39786831412](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39786831412/attempts/1) |
| 10-22 06:19 | 桌面端建置 | PR | feat/macos-worker | success | 5.3 分 | 0.1 分 | [#39785688647](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785688647/attempts/1) |
| 10-22 06:19 | CI | PR | feat/macos-worker | failure | 3.6 分 | 0.1 分 | [#39785688742](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785688742/attempts/1) |
| 10-22 06:16 | CI | PR | feat/linux-server-package | success | 3.3 分 | 0.1 分 | [#39785385535](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785385535/attempts/1) |
| 10-22 06:16 | 一鍵安裝腳本 | PR | feat/linux-server-package | success | 3.3 分 | 0.1 分 | [#39785385506](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785385506/attempts/1) |
| 10-22 06:16 | 桌面端建置 | PR | feat/linux-server-package | success | 5.7 分 | 0.0 分 | [#39785385717](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785385717/attempts/1) |
| 10-22 06:16 | 桌面端建置 | PR | feat/macos-worker | cancelled | 2.9 分 | 0.1 分 | [#39785365660](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785365660/attempts/1) |
| 10-22 06:16 | CI | PR | feat/macos-worker | cancelled | 2.9 分 | 0.1 分 | [#39785365027](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785365027/attempts/1) |
| 10-22 06:11 | CI | PR | feat/macos-worker | failure | 4.1 分 | 0.1 分 | [#39784512248](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784512248/attempts/1) |
| 10-22 06:11 | 桌面端建置 | PR | feat/macos-worker | cancelled | 5.2 分 | 0.0 分 | [#39784512047](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784512047/attempts/1) |
| 10-22 06:09 | 桌面端建置 | PR | feat/macos-worker | cancelled | 1.6 分 | 0.0 分 | [#39784389134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784389134/attempts/1) |

