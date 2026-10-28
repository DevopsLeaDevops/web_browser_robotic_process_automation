# CI 運行耗時紀錄

更新：2026-10-27 17:29 America/Los_Angeles（PDT，UTC−07:00）。共 632 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 209（41） | 102（26） | 3.7 分（2.7 分） | 7.2 分（4.9 分） | 0.0 分（0.0 分） | 1283／490／0 分（172／65／0 分） |
| 桌面端建置 | 150（34） | 112（27） | 4.5 分（3.8 分） | 10.2 分（4.2 分） | 0.1 分（0.1 分） | 16／459／683 分（3／89／87 分） |
| 伺服器分發包 | 75（0） | 70（0） | 2.0 分（0.0 分） | 7.2 分（0.0 分） | 0.1 分（0.0 分） | 297／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 75（15） | 55（7） | 2.9 分（3.0 分） | 20.1 分（15.5 分） | 0.1 分（0.1 分） | 406／300／205 分（69／47／17 分） |
| 每晚完整測試 | 17（1） | 0（0） | 47.2 分（39.3 分） | 57.5 分（39.3 分） | 0.1 分（0.0 分） | 648／625／519 分（36／39／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-27 | 44 | 203 | 101 | 78 | 383 |
| 2026-10-26 | 127 | 743 | 530 | 510 | 1783 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-27 09:09 America/Los_Angeles（PDT，UTC−07:00），合計 250 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.5（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 17.3（21.8） | 29 | `apps/server/tests/test_api.py` |
| 16.9（21.3） | 25 | `apps/server/tests/test_production_api.py` |
| 16.3（19.4） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.4（14.7） | 11 | `apps/server/tests/test_gitsync.py` |
| 11.9（14.3） | 20 | `apps/server/tests/test_recorder_api.py` |
| 9.9（12.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.4（9.4） | 24 | `apps/desktop/tests/test_updates.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-27 09:09 America/Los_Angeles（PDT，UTC−07:00），合計 465 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 74.5（85.1） | 11 | `apps/server/tests/test_portal.py` |
| 40.3（40.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 33.7（37.9） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 25.1（26.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 21.8（25.4） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 21.3（26.0） | 5 | `apps/server/tests/test_production_flow.py` |
| 19.4（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 14.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.8（19.2） | 29 | `apps/server/tests/test_api.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-27 09:09 America/Los_Angeles（PDT，UTC−07:00），合計 773 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 293.1（245.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 113.7（113.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 112.7（112.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 101.2（101.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 62.3（56.8） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 48.8（47.9） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 27.5（35.0） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.8（4.7） | 2 | `tests\smoke\test_browser.py` |
| 4.6（4.4） | 1 | `apps\desktop\tests\test_selftest.py` |
| 3.1（2.7） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 1281 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 146.9（131.7） | 14 | `apps/server/tests/test_portal.py` |
| 138.9（124.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 127.8（119.7） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 102.3（97.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 101.8（97.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 90.3（90.2） | 18 | `apps/cli/tests/test_serve.py` |
| 65.0（56.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 64.5（52.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 62.4（59.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.2（40.2） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 865 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 129.8（122.6） | 14 | `apps/server/tests/test_portal.py` |
| 104.7（87.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 103.5（89.2） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 100.3（97.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 86.0（87.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.9（62.2） | 9 | `apps/server/tests/test_production_flow.py` |
| 57.2（50.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 54.6（54.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.3（38.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 25.9（21.4） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 874 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 142.1（114.8） | 14 | `apps/server/tests/test_portal.py` |
| 109.8（93.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 99.6（92.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 98.7（88.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 90.6（90.6） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 61.2（67.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 59.0（60.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 54.9（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.3（40.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 27.7（22.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 815 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 95.7（94.9） | 14 | `apps/server/tests/test_portal.py` |
| 77.1（77.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 65.3（68.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 63.8（65.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 58.2（62.0） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 44.4（44.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.3（43.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.4（39.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 33.9（34.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 915 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.1（108.5） | 14 | `apps/server/tests/test_portal.py` |
| 80.4（80.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 75.6（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.4（76.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 65.5（65.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 51.5（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.9（50.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 42.2（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.9（35.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.8（19.8） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 643 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 106.7（89.7） | 14 | `apps/server/tests/test_portal.py` |
| 80.8（80.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 76.4（78.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.3（76.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 53.4（52.3） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 50.4（52.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.6（50.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.8（43.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 24.4（35.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 18.6（20.6） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 664 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 108.1（90.0） | 14 | `apps/server/tests/test_portal.py` |
| 81.4（78.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.2（77.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 75.2（77.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 53.8（51.9） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 50.0（53.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.0（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 42.7（43.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.0（35.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.0（19.3） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 1335 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 140.6（92.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 131.0（109.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 128.1（128.9） | 14 | `apps\server\tests\test_portal.py` |
| 99.8（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 81.6（81.6） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 71.0（72.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 64.3（63.0） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 63.3（57.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.6（39.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 37.2（31.8） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 863 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 122.1（108.1） | 14 | `apps\server\tests\test_portal.py` |
| 110.3（110.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 105.5（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 88.7（89.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 78.2（72.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 69.8（62.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 64.0（61.1） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 54.7（55.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.6（38.9） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.2（27.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-27 13:51 America/Los_Angeles（PDT，UTC−07:00），合計 880 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 127.4（106.3） | 14 | `apps\server\tests\test_portal.py` |
| 113.0（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 97.9（97.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 88.8（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 73.9（64.4） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 69.3（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 62.6（55.9） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 59.3（61.9） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 46.0（28.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 38.9（38.3） | 4 | `apps\server\tests\test_replay_flow.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-27 17:27 | 一鍵安裝腳本 | PR | m7c/upload | success | 0.2 分 | 0.0 分 | [#40608922100](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40608922100/attempts/1) |
| 10-27 17:27 | 伺服器分發包 | PR | m7c/upload | success | 1.9 分 | 0.1 分 | [#40608922077](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40608922077/attempts/1) |
| 10-27 14:16 | 一鍵安裝腳本 | 排程 | main | success | 24.0 分 | 0.1 分 | [#40585349033](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40585349033/attempts/1) |
| 10-27 13:51 | 每晚完整測試 | 排程 | main | failure | 52.8 分 | 0.1 分 | [#40581792306](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40581792306/attempts/1) |
| 10-27 09:09 | CI | PR | m7c/upload | failure | 4.6 分 | 0.1 分 | [#40538070442](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070442/attempts/1) |
| 10-27 09:09 | 一鍵安裝腳本 | PR | m7c/upload | success | 0.2 分 | 0.0 分 | [#40538070721](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070721/attempts/1) |
| 10-27 09:09 | 伺服器分發包 | PR | m7c/upload | success | 8.9 分 | 0.1 分 | [#40538070441](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070441/attempts/1) |
| 10-27 09:09 | 桌面端建置 | PR | m7c/upload | failure | 15.2 分 | 0.0 分 | [#40538070431](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070431/attempts/1) |
| 10-27 09:01 | 伺服器分發包 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40536742100](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40536742100/attempts/1) |
| 10-27 09:01 | CI | PR | feat/composite-replay | success | 2.0 分 | 0.1 分 | [#40536741936](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40536741936/attempts/1) |
| 10-27 09:01 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.1 分 | [#40536741906](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40536741906/attempts/1) |
| 10-27 08:53 | 一鍵安裝腳本 | PR | m7c/upload | success | 0.2 分 | 0.0 分 | [#40535493628](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40535493628/attempts/1) |
| 10-27 08:53 | 伺服器分發包 | PR | m7c/upload | success | 3.5 分 | 0.1 分 | [#40535492873](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40535492873/attempts/1) |
| 10-27 08:53 | CI | PR | m7c/upload | failure | 3.8 分 | 0.1 分 | [#40535493370](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40535493370/attempts/1) |
| 10-27 08:53 | 桌面端建置 | PR | m7c/upload | failure | 15.2 分 | 0.0 分 | [#40535492830](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40535492830/attempts/1) |
| 10-27 08:50 | 桌面端建置 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40534963409](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534963409/attempts/1) |
| 10-27 08:50 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40534963472](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534963472/attempts/1) |
| 10-27 08:50 | CI | PR | feat/composite-replay | success | 9.3 分 | 0.1 分 | [#40534963629](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534963629/attempts/1) |
| 10-27 08:45 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40534214731](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534214731/attempts/1) |
| 10-27 08:45 | 伺服器分發包 | PR | feat/composite-replay | success | 0.2 分 | 0.1 分 | [#40534214704](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534214704/attempts/1) |
| 10-27 08:45 | CI | PR | feat/composite-replay | failure | 3.5 分 | 0.1 分 | [#40534214729](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534214729/attempts/1) |
| 10-27 08:35 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40532439277](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40532439277/attempts/1) |
| 10-27 08:35 | 伺服器分發包 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40532439409](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40532439409/attempts/1) |
| 10-27 08:35 | CI | PR | feat/composite-replay | failure | 4.0 分 | 0.1 分 | [#40532439498](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40532439498/attempts/1) |
| 10-27 08:30 | 桌面端建置 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40531629512](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40531629512/attempts/1) |
| 10-27 08:30 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40531623030](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40531623030/attempts/1) |
| 10-27 08:30 | 伺服器分發包 | PR | feat/composite-replay | success | 1.9 分 | 0.1 分 | [#40531622978](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40531622978/attempts/1) |
| 10-27 08:30 | CI | PR | feat/composite-replay | failure | 3.8 分 | 0.1 分 | [#40531623654](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40531623654/attempts/1) |
| 10-27 08:24 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40530741469](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40530741469/attempts/1) |
| 10-27 08:24 | 伺服器分發包 | PR | feat/composite-replay | success | 0.3 分 | 0.0 分 | [#40530741686](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40530741686/attempts/1) |
| 10-27 08:24 | 桌面端建置 | PR | feat/composite-replay | success | 0.5 分 | 0.2 分 | [#40530741295](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40530741295/attempts/1) |
| 10-27 08:24 | CI | PR | feat/composite-replay | failure | 3.4 分 | 0.3 分 | [#40530741244](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40530741244/attempts/1) |
| 10-27 08:16 | 一鍵安裝腳本 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40529308064](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40529308064/attempts/1) |
| 10-27 08:16 | CI | PR | feat/composite-replay | failure | 6.6 分 | 0.1 分 | [#40529308396](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40529308396/attempts/1) |
| 10-27 08:16 | 伺服器分發包 | PR | feat/composite-replay | success | 8.5 分 | 0.1 分 | [#40529308103](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40529308103/attempts/1) |
| 10-27 08:10 | CI | PR | m7c/upload | success | 6.5 分 | 0.0 分 | [#40528203360](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40528203360/attempts/1) |
| 10-27 08:09 | 一鍵安裝腳本 | PR | m7c/upload | success | 0.2 分 | 0.1 分 | [#40528203643](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40528203643/attempts/1) |
| 10-27 08:09 | 伺服器分發包 | PR | m7c/upload | success | 0.1 分 | 0.0 分 | [#40528171340](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40528171340/attempts/1) |
| 10-27 08:09 | 一鍵安裝腳本 | PR | m7c/upload | cancelled | 0.2 分 | 0.0 分 | [#40528171390](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40528171390/attempts/1) |
| 10-27 08:09 | CI | PR | m7c/upload | cancelled | 0.6 分 | 0.0 分 | [#40528171425](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40528171425/attempts/1) |

