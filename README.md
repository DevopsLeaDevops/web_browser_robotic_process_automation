# CI 運行耗時紀錄

更新：2026-10-28 06:33 America/Los_Angeles（PDT，UTC−07:00）。共 726 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 178（101） | 80（60） | 4.0 分（2.6 分） | 8.7 分（5.2 分） | 0.1 分（0.0 分） | 1213／390／0 分（425／204／0 分） |
| 桌面端建置 | 134（72） | 99（61） | 5.2 分（3.9 分） | 15.0 分（4.3 分） | 0.1 分（0.1 分） | 16／362／595 分（6／204／198 分） |
| 伺服器分發包 | 94（0） | 89（0） | 2.0 分（0.0 分） | 5.4 分（0.0 分） | 0.1 分（0.0 分） | 342／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 93（20） | 74（11） | 1.0 分（3.1 分） | 15.2 分（15.2 分） | 0.0 分（0.1 分） | 380／290／196 分（99／57／26 分） |
| 每晚完整測試 | 17（1） | 0（0） | 47.2 分（39.3 分） | 57.5 分（39.3 分） | 0.1 分（0.0 分） | 648／625／519 分（36／39／0 分） |
| 發布 | 15（1） | 7（1） | 11.9 分（5.7 分） | 15.2 分（5.7 分） | 0.1 分（0.1 分） | 95／65／69 分（1／5／4 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-28 | 62 | 159 | 20 | 10 | 189 |
| 2026-10-27 | 76 | 286 | 142 | 101 | 528 |
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

最近一次：2026-10-28 03:51 America/Los_Angeles（PDT，UTC−07:00），合計 265 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.4（19.7） | 18 | `apps/cli/tests/test_serve.py` |
| 16.4（22.8） | 29 | `apps/server/tests/test_api.py` |
| 16.2（21.4） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 16.1（22.3） | 25 | `apps/server/tests/test_production_api.py` |
| 14.0（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.9（16.7） | 11 | `apps/server/tests/test_gitsync.py` |
| 12.3（16.2） | 20 | `apps/server/tests/test_recorder_api.py` |
| 10.9（12.5） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.8（12.2） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-28 03:51 America/Los_Angeles（PDT，UTC−07:00），合計 491 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 75.1（92.3） | 12 | `apps/server/tests/test_portal.py` |
| 38.5（44.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 31.2（40.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 25.7（31.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 22.9（28.2） | 5 | `apps/server/tests/test_production_flow.py` |
| 20.2（26.8） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 19.4（19.6） | 18 | `apps/cli/tests/test_serve.py` |
| 14.0（13.1） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.2（20.5） | 25 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-28 01:35 America/Los_Angeles（PDT，UTC−07:00），合計 713 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 254.3（287.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 117.3（139.0） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 94.5（92.9） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 88.3（112.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 66.3（69.1） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 51.6（51.6） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 28.7（28.7） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.0（5.5） | 2 | `tests\smoke\test_browser.py` |
| 4.0（3.8） | 1 | `apps\desktop\tests\test_selftest.py` |
| 3.1（3.1） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-28 06:33 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40697502609](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40697502609/attempts/1) |
| 10-28 03:51 | 桌面端建置 | PR | fix/replay-ux | success | 0.2 分 | 0.0 分 | [#40675466158](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40675466158/attempts/1) |
| 10-28 03:51 | 一鍵安裝腳本 | PR | fix/replay-ux | success | 0.3 分 | 0.0 分 | [#40675466183](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40675466183/attempts/1) |
| 10-28 03:51 | 伺服器分發包 | PR | fix/replay-ux | success | 2.3 分 | 0.1 分 | [#40675466298](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40675466298/attempts/1) |
| 10-28 03:51 | CI | PR | fix/replay-ux | success | 3.0 分 | 0.0 分 | [#40675466206](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40675466206/attempts/1) |
| 10-28 03:46 | 桌面端建置 | PR | fix/replay-ux | success | 0.2 分 | 0.1 分 | [#40674735147](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40674735147/attempts/1) |
| 10-28 03:46 | 一鍵安裝腳本 | PR | fix/replay-ux | success | 0.2 分 | 0.1 分 | [#40674735099](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40674735099/attempts/1) |
| 10-28 03:46 | 伺服器分發包 | PR | fix/replay-ux | success | 2.1 分 | 0.1 分 | [#40674735012](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40674735012/attempts/1) |
| 10-28 03:46 | CI | PR | fix/replay-ux | failure | 3.9 分 | 0.1 分 | [#40674735016](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40674735016/attempts/1) |
| 10-28 02:35 | 桌面端建置 | PR | docs/refresh-main | success | 0.2 分 | 0.0 分 | [#40665437608](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40665437608/attempts/1) |
| 10-28 02:35 | 一鍵安裝腳本 | PR | docs/refresh-main | success | 0.2 分 | 0.0 分 | [#40665437499](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40665437499/attempts/1) |
| 10-28 02:35 | CI | PR | docs/refresh-main | success | 4.0 分 | 0.0 分 | [#40665437665](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40665437665/attempts/1) |
| 10-28 02:31 | 發布 | 推送 | v0.7.0 | success | 7.7 分 | 0.1 分 | [#40664954438](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40664954438/attempts/1) |
| 10-28 02:30 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40664753848](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40664753848/attempts/1) |
| 10-28 02:30 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.1 分 | [#40664753757](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40664753757/attempts/1) |
| 10-28 02:30 | CI | 推送 | main | failure | 8.7 分 | 0.1 分 | [#40664753756](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40664753756/attempts/1) |
| 10-28 02:10 | 桌面端建置 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.0 分 | [#40662245318](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40662245318/attempts/1) |
| 10-28 02:10 | 伺服器分發包 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.1 分 | [#40662245550](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40662245550/attempts/1) |
| 10-28 02:10 | CI | PR | chore/release-0.7.0 | success | 3.8 分 | 0.1 分 | [#40662245488](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40662245488/attempts/1) |
| 10-28 02:06 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40661668691](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40661668691/attempts/1) |
| 10-28 02:06 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40661668757](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40661668757/attempts/1) |
| 10-28 02:06 | CI | 推送 | main | success | 8.0 分 | 0.0 分 | [#40661668695](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40661668695/attempts/1) |
| 10-28 01:41 | 一鍵安裝腳本 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40658557585](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40658557585/attempts/1) |
| 10-28 01:41 | 桌面端建置 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40658557632](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40658557632/attempts/1) |
| 10-28 01:41 | CI | PR | fix/main-ci-red | success | 2.1 分 | 0.0 分 | [#40658557491](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40658557491/attempts/1) |
| 10-28 01:35 | CI | PR | fix/main-ci-red | success | 4.4 分 | 0.1 分 | [#40657765470](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657765470/attempts/1) |
| 10-28 01:35 | 伺服器分發包 | PR | fix/main-ci-red | success | 2.6 分 | 0.1 分 | [#40657765348](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657765348/attempts/1) |
| 10-28 01:35 | 桌面端建置 | PR | fix/main-ci-red | success | 4.8 分 | 0.0 分 | [#40657765516](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657765516/attempts/1) |
| 10-28 01:34 | 伺服器分發包 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.0 分 | [#40657822163](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657822163/attempts/1) |
| 10-28 01:34 | 桌面端建置 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.1 分 | [#40657822190](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657822190/attempts/1) |
| 10-28 01:34 | CI | PR | chore/release-0.7.0 | success | 2.1 分 | 0.0 分 | [#40657822150](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657822150/attempts/1) |
| 10-28 01:34 | 一鍵安裝腳本 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40657765163](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657765163/attempts/1) |
| 10-28 01:33 | 一鍵安裝腳本 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40657707680](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657707680/attempts/1) |
| 10-28 01:33 | 桌面端建置 | PR | fix/main-ci-red | cancelled | 1.7 分 | 0.0 分 | [#40657707715](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657707715/attempts/1) |
| 10-28 01:33 | CI | PR | fix/main-ci-red | cancelled | 1.8 分 | 0.1 分 | [#40657707694](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40657707694/attempts/1) |
| 10-28 01:25 | 伺服器分發包 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40656640474](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40656640474/attempts/1) |
| 10-28 01:25 | 一鍵安裝腳本 | PR | fix/main-ci-red | success | 0.2 分 | 0.0 分 | [#40656640473](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40656640473/attempts/1) |
| 10-28 01:25 | CI | PR | fix/main-ci-red | failure | 3.9 分 | 0.0 分 | [#40656640463](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40656640463/attempts/1) |
| 10-28 01:22 | 一鍵安裝腳本 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.0 分 | [#40656281500](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40656281500/attempts/1) |
| 10-28 01:22 | 桌面端建置 | PR | chore/release-0.7.0 | success | 0.2 分 | 0.1 分 | [#40656281426](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40656281426/attempts/1) |

