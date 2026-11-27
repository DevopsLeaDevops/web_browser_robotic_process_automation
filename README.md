# CI 運行耗時紀錄

更新：2026-11-27 07:46 America/Los_Angeles（PST，UTC−08:00）。共 877 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 1（0） | 0（0） | 4.8 分（0.0 分） | 4.8 分（0.0 分） | 0.0 分（0.0 分） | 7／5／0 分（0／0／0 分） |
| 桌面端建置 | 1（0） | 1（0） | 7.2 分（0.0 分） | 7.2 分（0.0 分） | 0.1 分（0.0 分） | 0／5／12 分（0／0／0 分） |
| 伺服器分發包 | 1（0） | 1（0） | 2.4 分（0.0 分） | 2.4 分（0.0 分） | 0.1 分（0.0 分） | 4／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 1（0） | 1（0） | 0.2 分（0.0 分） | 0.2 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 61.7 分（0.0 分） | 61.7 分（0.0 分） | 1.4 分（0.0 分） | 56／59／73 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-11-27 | 5 | 68 | 69 | 85 | 222 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 380 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 25.7（21.0） | 29 | `apps/server/tests/test_api.py` |
| 24.8（19.5） | 25 | `apps/server/tests/test_production_api.py` |
| 23.3（20.9） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 19.8（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 18.6（16.1） | 11 | `apps/server/tests/test_gitsync.py` |
| 17.6（14.6） | 14 | `apps/server/tests/test_workflow_api.py` |
| 16.8（16.3） | 13 | `apps/server/tests/test_replay.py` |
| 15.0（14.5） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.1（13.1） | 14 | `apps/worker/tests/test_gateway.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 700 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 102.7（103.2） | 12 | `apps/server/tests/test_portal.py` |
| 44.7（45.1） | 4 | `apps/server/tests/test_replay_flow.py` |
| 42.0（43.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 30.5（31.1） | 5 | `apps/server/tests/test_production_flow.py` |
| 30.5（30.0） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 29.9（30.4） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 20.9（20.9） | 29 | `apps/server/tests/test_api.py` |
| 20.8（20.8） | 25 | `apps/server/tests/test_production_api.py` |
| 20.6（20.1） | 15 | `apps/server/tests/test_replay.py` |
| 20.2（20.2） | 18 | `apps/cli/tests/test_serve.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 841 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 236.4（242.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 219.1（140.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 94.5（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 90.1（96.9） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 60.3（71.4） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 48.0（48.0） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 39.5（34.8） | 2 | `packages\rpa_runner\tests\test_download_browser.py` |
| 31.5（27.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 14.4（5.2） | 2 | `tests\smoke\test_browser.py` |
| 3.7（2.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1510 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 160.7（160.7） | 15 | `apps/server/tests/test_portal.py` |
| 132.1（108.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 127.9（114.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 127.4（130.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 123.0（115.4） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 90.1（89.9） | 18 | `apps/cli/tests/test_serve.py` |
| 69.6（69.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 69.0（70.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 62.4（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 45.6（41.6） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1018 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 147.0（147.8） | 15 | `apps/server/tests/test_portal.py` |
| 113.5（107.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 111.4（106.1） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 109.1（105.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 107.4（91.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 71.0（70.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 62.3（64.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 53.0（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.3（40.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 26.9（22.5） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1088 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 174.0（148.7） | 15 | `apps/server/tests/test_portal.py` |
| 117.7（102.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 117.0（114.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 111.1（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 106.3（104.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 82.3（70.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 63.6（66.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 53.6（51.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.3（41.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 28.8（23.9） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 993 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.1（107.7） | 15 | `apps/server/tests/test_portal.py` |
| 90.4（89.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 74.4（73.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 68.2（65.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 64.6（64.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 46.6（46.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.6（46.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.2（39.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.0（35.2） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.8（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 926 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 99.8（110.8） | 15 | `apps/server/tests/test_portal.py` |
| 86.4（90.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 70.6（78.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 64.0（67.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 60.4（70.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 43.0（49.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.8（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 36.7（39.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.0（36.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 656 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 100.5（108.4） | 15 | `apps/server/tests/test_portal.py` |
| 86.3（90.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.0（76.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 61.3（67.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 50.2（55.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 45.8（50.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 42.1（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 37.6（40.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 33.9（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 17.5（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 662 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 102.6（107.9） | 15 | `apps/server/tests/test_portal.py` |
| 87.4（89.7） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.7（73.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 62.1（66.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 50.1（54.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 42.8（47.2） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.7（47.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.1（40.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.4（35.2） | 4 | `apps/server/tests/test_replay_flow.py` |
| 17.7（17.8） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1462 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 143.0（128.4） | 15 | `apps\server\tests\test_portal.py` |
| 118.1（103.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 113.3（104.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 106.9（90.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 99.8（89.9） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 75.1（66.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 62.8（58.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 60.0（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.5（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.9（30.4） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 995 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 144.8（119.5） | 15 | `apps\server\tests\test_portal.py` |
| 110.7（97.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 107.2（93.3） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 105.0（98.1） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 74.8（65.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 74.0（65.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 64.6（58.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.9（53.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.2（37.8） | 4 | `apps\server\tests\test_replay_flow.py` |
| 28.9（24.2） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-11-27 06:44 America/Los_Angeles（PST，UTC−08:00），合計 990 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 139.8（121.4） | 15 | `apps\server\tests\test_portal.py` |
| 109.0（98.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 107.4（89.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 106.9（97.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 74.7（67.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 72.4（68.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 63.4（58.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 58.2（52.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.7（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 30.9（25.0） | 17 | `packages\rpa_runner\tests\test_upload.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 11-27 06:44 | 一鍵安裝腳本 | PR | dependabot/github_actions/actions-ab053d56de | success | 0.2 分 | 0.0 分 | [#46018662872](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/46018662872/attempts/1) |
| 11-27 06:44 | 伺服器分發包 | PR | dependabot/github_actions/actions-ab053d56de | success | 2.4 分 | 0.1 分 | [#46018662877](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/46018662877/attempts/1) |
| 11-27 06:44 | CI | PR | dependabot/github_actions/actions-ab053d56de | failure | 4.8 分 | 0.0 分 | [#46018662840](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/46018662840/attempts/1) |
| 11-27 06:44 | 桌面端建置 | PR | dependabot/github_actions/actions-ab053d56de | success | 7.2 分 | 0.1 分 | [#46018662887](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/46018662887/attempts/1) |
| 11-27 06:44 | 每晚完整測試 | PR | dependabot/github_actions/actions-ab053d56de | failure | 61.7 分 | 1.4 分 | [#46018662891](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/46018662891/attempts/1) |
| 11-06 18:15 | 一鍵安裝腳本 | PR | m7/flow | success | 0.2 分 | 0.0 分 | [#42328277342](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328277342/attempts/1) |
| 11-06 18:14 | 伺服器分發包 | PR | docs/m6-status | success | 0.2 分 | 0.0 分 | [#42328230522](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328230522/attempts/1) |
| 11-06 18:14 | 桌面端建置 | PR | docs/m6-status | success | 0.2 分 | 0.1 分 | [#42328230681](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328230681/attempts/1) |
| 11-06 18:14 | CI | PR | m7/flow | cancelled | 1.0 分 | 0.0 分 | [#42328190068](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328190068/attempts/1) |
| 11-06 18:13 | 伺服器分發包 | PR | m7/flow | success | 0.2 分 | 0.0 分 | [#42328170486](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328170486/attempts/1) |
| 11-06 18:13 | 桌面端建置 | PR | m7/flow | success | 0.2 分 | 0.0 分 | [#42328170468](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328170468/attempts/1) |
| 11-06 18:13 | CI | PR | m7/flow | cancelled | 0.5 分 | 0.0 分 | [#42328170464](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328170464/attempts/1) |
| 11-06 18:12 | 伺服器分發包 | PR | docs/refresh-v0-8 | success | 0.2 分 | 0.0 分 | [#42328082011](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328082011/attempts/1) |
| 11-06 18:12 | 一鍵安裝腳本 | PR | docs/refresh-v0-8 | success | 0.3 分 | 0.0 分 | [#42328082006](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42328082006/attempts/1) |
| 11-06 18:08 | 伺服器分發包 | PR | docs/m6-status | success | 0.1 分 | 0.0 分 | [#42327694541](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42327694541/attempts/1) |
| 11-06 18:08 | 一鍵安裝腳本 | PR | docs/m6-status | success | 0.2 分 | 0.0 分 | [#42327694594](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42327694594/attempts/1) |
| 11-06 18:08 | CI | PR | docs/m6-status | failure | 3.0 分 | 0.1 分 | [#42327694704](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42327694704/attempts/1) |
| 11-06 17:50 | 桌面端建置 | 推送 | main | success | 5.7 分 | 0.1 分 | [#42326194813](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42326194813/attempts/1) |
| 11-06 17:50 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#42326194342](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42326194342/attempts/1) |
| 11-06 17:50 | 伺服器分發包 | 推送 | main | success | 0.3 分 | 0.1 分 | [#42326194564](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42326194564/attempts/1) |
| 11-06 17:50 | CI | 推送 | main | success | 6.1 分 | 0.1 分 | [#42326194587](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42326194587/attempts/1) |
| 11-06 13:22 | 一鍵安裝腳本 | 排程 | main | failure | 28.0 分 | 0.1 分 | [#42296151794](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42296151794/attempts/1) |
| 11-06 12:59 | 每晚完整測試 | 排程 | main | failure | 57.5 分 | 2.8 分 | [#42292913380](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42292913380/attempts/1) |
| 11-06 06:44 | 一鍵安裝腳本 | PR | dependabot/github_actions/actions-7313d4f700 | success | 0.2 分 | 0.0 分 | [#42236674103](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42236674103/attempts/1) |
| 11-06 06:44 | 伺服器分發包 | PR | dependabot/github_actions/actions-7313d4f700 | success | 3.6 分 | 0.1 分 | [#42236674134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42236674134/attempts/1) |
| 11-06 06:44 | CI | PR | dependabot/github_actions/actions-7313d4f700 | success | 4.6 分 | 0.0 分 | [#42236674194](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42236674194/attempts/1) |
| 11-06 06:44 | 桌面端建置 | PR | dependabot/github_actions/actions-7313d4f700 | failure | 20.2 分 | 0.1 分 | [#42236674425](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42236674425/attempts/1) |
| 11-06 06:44 | 每晚完整測試 | PR | dependabot/github_actions/actions-7313d4f700 | failure | 53.5 分 | 0.1 分 | [#42236674206](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42236674206/attempts/1) |
| 11-06 04:55 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#42221329311](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42221329311/attempts/1) |
| 11-06 04:55 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#42221329544](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42221329544/attempts/1) |
| 11-06 04:55 | CI | 推送 | main | failure | 6.1 分 | 0.0 分 | [#42221329340](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42221329340/attempts/1) |
| 11-05 17:37 | 伺服器分發包 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#42145024170](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42145024170/attempts/1) |
| 11-05 17:37 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#42145024168](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42145024168/attempts/1) |
| 11-05 17:37 | CI | PR | feat/python-nodes | success | 2.4 分 | 0.0 分 | [#42145024195](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42145024195/attempts/1) |
| 11-05 17:20 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#42143133781](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42143133781/attempts/1) |
| 11-05 17:20 | 伺服器分發包 | PR | feat/python-nodes | success | 3.5 分 | 0.1 分 | [#42143133892](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42143133892/attempts/1) |
| 11-05 17:20 | CI | PR | feat/python-nodes | failure | 4.2 分 | 0.0 分 | [#42143133908](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42143133908/attempts/1) |
| 11-05 17:20 | 桌面端建置 | PR | feat/python-nodes | success | 6.5 分 | 0.9 分 | [#42143133938](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42143133938/attempts/1) |
| 11-05 17:14 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#42142485847](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42142485847/attempts/1) |
| 11-05 17:14 | 桌面端建置 | 推送 | main | success | 0.2 分 | 0.0 分 | [#42142485808](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42142485808/attempts/1) |

