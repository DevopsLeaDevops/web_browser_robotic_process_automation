# CI 運行耗時紀錄

更新：2026-10-22 06:19 America/Los_Angeles（PDT，UTC−07:00）。共 257 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 132（0） | 77（0） | 2.8 分（0.0 分） | 5.2 分（0.0 分） | 0.0 分（0.0 分） | 586／268／0 分（0／0／0 分） |
| 桌面端建置 | 96（0） | 73（0） | 4.0 分（0.0 分） | 5.2 分（0.0 分） | 0.1 分（0.0 分） | 9／280／238 分（0／0／0 分） |
| 一鍵安裝腳本 | 26（0） | 14（0） | 3.1 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 137／93／33 分（0／0／0 分） |
| 每晚完整測試 | 2（0） | 0（0） | 40.0 分（0.0 分） | 40.7 分（0.0 分） | 0.0 分（0.0 分） | 80／80／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 47 | 148 | 126 | 36 | 310 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 06:16 America/Los_Angeles（PDT，UTC−07:00），合計 196 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.7（19.7） | 24 | `apps/server/tests/test_production_api.py` |
| 19.1（19.1） | 28 | `apps/server/tests/test_api.py` |
| 18.0（18.0） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 14.2（14.2） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.5（13.0） | 19 | `apps/server/tests/test_recorder_api.py` |
| 9.6（11.1） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.5（9.9） | 14 | `apps/server/tests/test_workflow_api.py` |
| 7.5（9.5） | 12 | `apps/server/tests/test_replay.py` |
| 7.4（7.4） | 27 | `apps/desktop/tests/test_recorder_app.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 06:16 America/Los_Angeles（PDT，UTC−07:00），合計 346 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 44.9（52.3） | 7 | `apps/server/tests/test_portal.py` |
| 32.8（34.5） | 2 | `apps/server/tests/test_replay_flow.py` |
| 30.1（36.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 22.9（29.6） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 21.9（25.6） | 5 | `apps/server/tests/test_production_flow.py` |
| 19.6（20.6） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 14.5（14.0） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 11.8（14.0） | 28 | `apps/server/tests/test_api.py` |
| 11.3（15.5） | 24 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 06:11 America/Los_Angeles（PDT，UTC−07:00），合計 655 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 226.0（239.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 135.3（124.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 118.0（114.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 96.0（95.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 45.9（35.8） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 23.8（23.8） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.2（5.2） | 2 | `tests\smoke\test_browser.py` |
| 3.0（3.8） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.7（3.0） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-22 06:16 | 桌面端建置 | PR | feat/macos-worker | cancelled | 2.9 分 | 0.1 分 | [#39785365660](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785365660/attempts/1) |
| 10-22 06:16 | CI | PR | feat/macos-worker | cancelled | 2.9 分 | 0.1 分 | [#39785365027](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785365027/attempts/1) |
| 10-22 06:11 | CI | PR | feat/macos-worker | failure | 4.1 分 | 0.1 分 | [#39784512248](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784512248/attempts/1) |
| 10-22 06:11 | 桌面端建置 | PR | feat/macos-worker | cancelled | 5.2 分 | 0.0 分 | [#39784512047](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784512047/attempts/1) |
| 10-22 06:09 | 桌面端建置 | PR | feat/macos-worker | cancelled | 1.6 分 | 0.0 分 | [#39784389134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784389134/attempts/1) |
| 10-22 06:09 | CI | PR | feat/macos-worker | cancelled | 1.7 分 | 0.1 分 | [#39784389471](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39784389471/attempts/1) |
| 10-22 05:59 | 一鍵安裝腳本 | PR | feat/linux-server-package | success | 2.5 分 | 0.1 分 | [#39782965442](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39782965442/attempts/1) |
| 10-22 05:59 | CI | PR | feat/linux-server-package | success | 2.8 分 | 0.0 分 | [#39782965444](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39782965444/attempts/1) |
| 10-22 05:59 | 桌面端建置 | PR | feat/linux-server-package | failure | 15.2 分 | 0.0 分 | [#39782965559](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39782965559/attempts/1) |
| 10-22 05:24 | CI | 推送 | main | failure | 6.5 分 | 0.1 分 | [#39778039255](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39778039255/attempts/1) |
| 10-22 05:24 | 桌面端建置 | 推送 | main | failure | 15.2 分 | 0.0 分 | [#39778039323](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39778039323/attempts/1) |
| 10-22 04:30 | 桌面端建置 | PR | feat/dynamic-values | success | 10.2 分 | 6.9 分 | [#39771036168](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39771036168/attempts/1) |
| 10-22 04:30 | CI | PR | feat/dynamic-values | success | 1.6 分 | 0.1 分 | [#39771036231](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39771036231/attempts/1) |
| 10-22 04:24 | CI | PR | feat/dynamic-values | success | 4.1 分 | 0.0 分 | [#39770306226](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39770306226/attempts/1) |
| 10-22 04:24 | 桌面端建置 | PR | feat/dynamic-values | cancelled | 5.8 分 | 0.0 分 | [#39770306210](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39770306210/attempts/1) |
| 10-22 03:37 | CI | 推送 | main | failure | 4.9 分 | 0.0 分 | [#39764418061](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39764418061/attempts/1) |
| 10-22 03:34 | CI | PR | docs/design-refresh | success | 2.8 分 | 0.0 分 | [#39764123632](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39764123632/attempts/1) |
| 10-22 03:30 | 一鍵安裝腳本 | 推送 | main | success | 2.5 分 | 0.0 分 | [#39763596414](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596414/attempts/1) |
| 10-22 03:30 | 桌面端建置 | 推送 | main | success | 5.1 分 | 0.5 分 | [#39763596489](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596489/attempts/1) |
| 10-22 03:30 | CI | 推送 | main | cancelled | 7.2 分 | 0.4 分 | [#39763596411](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596411/attempts/1) |
| 10-22 03:08 | CI | PR | fix/replay-multipage | success | 3.7 分 | 0.0 分 | [#39759862919 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862919/attempts/2) |
| 10-22 03:00 | 一鍵安裝腳本 | PR | fix/replay-multipage | success | 2.9 分 | 0.1 分 | [#39759862962](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862962/attempts/1) |
| 10-22 03:00 | CI | PR | fix/replay-multipage | failure | 5.0 分 | 0.1 分 | [#39759862919](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862919/attempts/1) |
| 10-22 03:00 | 桌面端建置 | PR | fix/replay-multipage | failure | 15.2 分 | 0.0 分 | [#39759862921](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862921/attempts/1) |
| 10-22 02:37 | 桌面端建置 | PR | feat/dynamic-values | failure | 15.0 分 | 0.0 分 | [#39754707569 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707569/attempts/2) |
| 10-22 02:21 | 桌面端建置 | PR | feat/dynamic-values | failure | 15.2 分 | 0.1 分 | [#39754707569](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707569/attempts/1) |
| 10-22 02:20 | CI | PR | feat/dynamic-values | success | 3.8 分 | 0.1 分 | [#39754707830](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707830/attempts/1) |
| 10-22 02:17 | CI | PR | feat/dynamic-values | failure | 3.4 分 | 0.1 分 | [#39754254129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754254129/attempts/1) |
| 10-22 02:17 | 桌面端建置 | PR | feat/dynamic-values | cancelled | 4.1 分 | 0.1 分 | [#39754254168](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754254168/attempts/1) |
| 10-22 00:52 | 桌面端建置 | PR | feat/dynamic-values | success | 0.1 分 | 0.0 分 | [#39743570456](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743570456/attempts/1) |
| 10-22 00:52 | CI | PR | feat/dynamic-values | success | 1.6 分 | 0.0 分 | [#39743570447](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743570447/attempts/1) |
| 10-22 00:49 | 桌面端建置 | PR | fix/replay-multipage | success | 6.0 分 | 2.1 分 | [#39743135105](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743135105/attempts/1) |
| 10-22 00:49 | CI | PR | fix/replay-multipage | success | 3.8 分 | 0.1 分 | [#39743134927](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743134927/attempts/1) |
| 10-22 00:48 | 一鍵安裝腳本 | PR | fix/replay-multipage | failure | 15.1 分 | 0.0 分 | [#39743135141](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743135141/attempts/1) |
| 10-22 00:46 | CI | PR | feat/dynamic-values | success | 3.9 分 | 0.0 分 | [#39742896430](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742896430/attempts/1) |
| 10-22 00:46 | 桌面端建置 | PR | feat/dynamic-values | success | 3.9 分 | 0.1 分 | [#39742896419](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742896419/attempts/1) |
| 10-22 00:45 | 一鍵安裝腳本 | PR | fix/replay-multipage | cancelled | 3.7 分 | 0.0 分 | [#39742681684](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681684/attempts/1) |
| 10-22 00:45 | CI | PR | fix/replay-multipage | cancelled | 4.0 分 | 0.0 分 | [#39742681627](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681627/attempts/1) |
| 10-22 00:45 | 桌面端建置 | PR | fix/replay-multipage | cancelled | 4.1 分 | 1.2 分 | [#39742681591](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681591/attempts/1) |
| 10-22 00:30 | 桌面端建置 | 推送 | main | success | 4.1 分 | 0.0 分 | [#39740982055](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39740982055/attempts/1) |

