# CI 運行耗時紀錄

更新：2026-10-27 09:14 America/Los_Angeles（PDT，UTC−07:00）。共 626 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 213（37） | 104（24） | 3.7 分（2.8 分） | 7.2 分（4.9 分） | 0.0 分（0.0 分） | 1298／490／0 分（157／65／0 分） |
| 桌面端建置 | 153（30） | 116（23） | 4.3 分（3.8 分） | 9.6 分（4.2 分） | 0.1 分（0.1 分） | 17／467／694 分（2／79／76 分） |
| 伺服器分發包 | 73（0） | 68（0） | 2.0 分（0.0 分） | 6.7 分（0.0 分） | 0.1 分（0.0 分） | 282／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 74（14） | 53（7） | 2.9 分（3.0 分） | 17.1 分（15.2 分） | 0.1 分（0.1 分） | 398／291／179 分（53／25／17 分） |
| 每晚完整測試 | 17（0） | 0（0） | 40.7 分（0.0 分） | 57.5 分（0.0 分） | 0.1 分（0.0 分） | 631／612／467 分（0／0／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-27 | 38 | 112 | 16 | 0 | 128 |
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

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 1315 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 149.5（130.7） | 14 | `apps/server/tests/test_portal.py` |
| 124.9（81.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 119.7（106.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 103.9（97.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 99.0（94.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 90.5（89.7） | 18 | `apps/cli/tests/test_serve.py` |
| 75.9（56.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 70.1（59.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 55.8（52.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.0（39.9） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 891 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 137.0（122.6） | 14 | `apps/server/tests/test_portal.py` |
| 110.7（89.2） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 109.4（97.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 104.2（97.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.4（87.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 70.8（62.2） | 9 | `apps/server/tests/test_production_flow.py` |
| 63.4（59.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 50.1（50.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.0（38.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 23.7（21.8） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 924 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 153.9（114.8） | 14 | `apps/server/tests/test_portal.py` |
| 114.2（88.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 108.7（93.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 105.4（92.3） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 91.7（92.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 74.3（69.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 66.3（61.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 50.4（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.7（38.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 24.4（22.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 825 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 94.9（93.8） | 14 | `apps/server/tests/test_portal.py` |
| 77.5（77.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.2（68.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.3（65.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 58.5（62.0） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 44.9（44.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.4（43.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.5（39.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 33.9（34.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.6（19.6） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 942 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.9（87.7） | 14 | `apps/server/tests/test_portal.py` |
| 82.4（81.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 79.7（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 77.3（77.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 72.5（60.3） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 52.4（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.8（50.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.7（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.5（34.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.8（19.6） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 676 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.4（89.0） | 14 | `apps/server/tests/test_portal.py` |
| 82.9（78.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 78.0（78.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 76.6（76.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 55.3（45.9） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 52.5（52.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.4（50.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.6（43.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.7（35.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.0（20.6） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 676 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.9（89.3） | 14 | `apps/server/tests/test_portal.py` |
| 81.9（78.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.8（77.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 77.3（77.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 55.3（48.7） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 53.4（53.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.5（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.5（43.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.1（35.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.0（21.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 1205 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 110.1（128.9） | 14 | `apps\server\tests\test_portal.py` |
| 105.3（109.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 95.5（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.8（91.8） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 81.1（82.5） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 71.4（74.2） | 9 | `apps\server\tests\test_production_flow.py` |
| 61.8（62.3） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.4（57.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.2（39.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.4（27.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 832 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 126.9（108.1） | 14 | `apps\server\tests\test_portal.py` |
| 105.7（108.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 96.5（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.0（90.0） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 69.4（72.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.2（61.0） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 62.2（62.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 54.4（56.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.9（38.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 26.6（27.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-26 21:45 America/Los_Angeles（PDT，UTC−07:00），合計 825 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 126.3（105.3） | 14 | `apps\server\tests\test_portal.py` |
| 105.0（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 94.3（99.1） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 89.1（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 70.6（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.8（63.3） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 61.6（66.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 53.6（55.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.7（38.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 25.5（27.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-27 09:09 | CI | PR | m7c/upload | failure | 4.6 分 | 0.1 分 | [#40538070442](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070442/attempts/1) |
| 10-27 09:09 | 一鍵安裝腳本 | PR | m7c/upload | success | 0.2 分 | 0.0 分 | [#40538070721](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40538070721/attempts/1) |
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
| 10-27 07:44 | 一鍵安裝腳本 | PR | feat/composite-report | success | 0.1 分 | 0.0 分 | [#40524081377](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40524081377/attempts/1) |
| 10-27 07:44 | 桌面端建置 | PR | feat/composite-report | success | 0.2 分 | 0.0 分 | [#40524081412](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40524081412/attempts/1) |
| 10-27 07:44 | CI | PR | feat/composite-report | success | 4.0 分 | 0.1 分 | [#40524081366](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40524081366/attempts/1) |
| 10-27 07:44 | 伺服器分發包 | PR | feat/composite-report | success | 9.9 分 | 0.1 分 | [#40524081398](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40524081398/attempts/1) |
| 10-26 21:57 | 桌面端建置 | 手動 | ci/layered-ci | success | 5.9 分 | 0.1 分 | [#40452459787](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40452459787/attempts/1) |
| 10-26 21:55 | 桌面端建置 | 手動 | ci/layered-ci | cancelled | 1.9 分 | 0.1 分 | [#40452363113](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40452363113/attempts/1) |

