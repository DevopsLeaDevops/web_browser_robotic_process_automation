# CI 運行耗時紀錄

更新：2026-10-29 04:09 America/Los_Angeles（PDT，UTC−07:00）。共 738 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 157（125） | 68（74） | 4.1 分（2.8 分） | 9.3 分（5.2 分） | 0.1 分（0.0 分） | 1116／341／0 分（550／252／0 分） |
| 桌面端建置 | 119（89） | 90（72） | 5.4 分（3.9 分） | 10.2 分（4.5 分） | 0.1 分（0.1 分） | 15／309／562 分（8／257／231 分） |
| 伺服器分發包 | 96（0） | 91（0） | 2.0 分（0.0 分） | 5.4 分（0.0 分） | 0.1 分（0.0 分） | 343／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 92（25） | 75（13） | 0.2 分（3.2 分） | 15.2 分（15.5 分） | 0.0 分（0.1 分） | 372／295／191 分（133／90／31 分） |
| 每晚完整測試 | 17（2） | 0（0） | 47.3 分（40.0 分） | 57.5 分（40.7 分） | 0.1 分（0.0 分） | 660／641／530 分（80／80／0 分） |
| 發布 | 15（1） | 7（1） | 11.9 分（5.7 分） | 15.2 分（5.7 分） | 0.1 分（0.1 分） | 95／65／69 分（1／5／4 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-29 | 5 | 11 | 0 | 0 | 11 |
| 2026-10-28 | 69 | 256 | 115 | 22 | 392 |
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

最近一次：2026-10-29 03:54 America/Los_Angeles（PDT，UTC−07:00），合計 1182 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 135.4（187.1） | 15 | `apps/server/tests/test_portal.py` |
| 93.1（111.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 92.4（126.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 90.3（130.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 75.1（99.0） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 67.3（76.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 66.6（95.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 59.2（83.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.3（46.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 23.1（32.9） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-29 03:54 America/Los_Angeles（PDT，UTC−07:00），合計 722 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.4（97.0） | 12 | `apps/server/tests/test_portal.py` |
| 50.2（45.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 46.8（41.3） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 34.8（32.5） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 32.8（29.9） | 5 | `apps/server/tests/test_production_flow.py` |
| 31.5（27.8） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 26.6（20.4） | 29 | `apps/server/tests/test_api.py` |
| 25.4（20.5） | 25 | `apps/server/tests/test_production_api.py` |
| 23.3（19.1） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 22.6（17.0） | 11 | `apps/server/tests/test_gitsync.py` |

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

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 1051 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 119.3（95.7） | 15 | `apps/server/tests/test_portal.py` |
| 83.3（77.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 81.8（68.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 79.8（65.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 69.7（62.0） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 57.8（44.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.0（43.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.3（39.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.9（34.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 22.7（18.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 895 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 102.4（108.5） | 15 | `apps/server/tests/test_portal.py` |
| 78.5（80.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.5（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.0（76.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 63.2（65.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 46.0（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.6（50.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.6（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.4（35.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.5（19.8） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 638 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 99.4（99.4） | 15 | `apps/server/tests/test_portal.py` |
| 78.6（80.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.6（77.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.0（73.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 52.7（52.7） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 45.5（50.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.3（49.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.5（42.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.9（34.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 18.0（20.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 640 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 102.2（102.2） | 15 | `apps/server/tests/test_portal.py` |
| 78.7（78.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.4（77.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.1（75.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 53.2（53.2） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 45.0（50.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.1（50.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.9（42.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.7（35.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 17.8（19.0） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 1406 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 142.8（128.9） | 15 | `apps\server\tests\test_portal.py` |
| 114.1（109.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 104.4（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 99.8（94.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 91.1（81.6） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 75.6（72.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.9（63.0） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 59.5（58.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.3（39.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 34.5（31.8） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 936 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 136.9（122.1） | 15 | `apps\server\tests\test_portal.py` |
| 113.3（112.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 105.1（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.2（90.0） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 76.9（64.0） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 76.5（74.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 67.2（62.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.8（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.3（40.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 29.8（29.8） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-28 13:57 America/Los_Angeles（PDT，UTC−07:00），合計 953 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 138.0（126.3） | 15 | `apps\server\tests\test_portal.py` |
| 113.3（111.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 105.6（97.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 98.8（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 76.6（65.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 74.4（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 68.2（61.9） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 59.0（57.5） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.8（38.7） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.5（31.5） | 17 | `packages\rpa_runner\tests\test_upload.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-29 04:08 | 桌面端建置 | PR | chore/release-0.7.1 | success | 0.2 分 | 0.0 分 | [#40863069317](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863069317/attempts/1) |
| 10-29 04:08 | 一鍵安裝腳本 | PR | chore/release-0.7.1 | success | 0.3 分 | 0.1 分 | [#40863069347](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863069347/attempts/1) |
| 10-29 03:54 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40861182800](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40861182800/attempts/1) |
| 10-29 03:54 | 桌面端建置 | 推送 | main | success | 0.3 分 | 0.1 分 | [#40861182828](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40861182828/attempts/1) |
| 10-29 03:54 | CI | 推送 | main | failure | 6.0 分 | 0.1 分 | [#40861182890](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40861182890/attempts/1) |
| 10-28 14:18 | 一鍵安裝腳本 | 排程 | main | failure | 30.1 分 | 0.0 分 | [#40770867716](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40770867716/attempts/1) |
| 10-28 13:57 | 每晚完整測試 | 排程 | main | failure | 56.7 分 | 5.3 分 | [#40767854003](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40767854003/attempts/1) |
| 10-28 06:52 | 伺服器分發包 | PR | fix/replay-ux | success | 0.2 分 | 0.0 分 | [#40700523880](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40700523880/attempts/1) |
| 10-28 06:52 | 一鍵安裝腳本 | PR | fix/replay-ux | success | 0.2 分 | 0.0 分 | [#40700524251](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40700524251/attempts/1) |
| 10-28 06:52 | CI | PR | fix/replay-ux | success | 2.1 分 | 0.1 分 | [#40700524238](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40700524238/attempts/1) |
| 10-28 06:33 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40697502609](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40697502609/attempts/1) |
| 10-28 06:33 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40697502605](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40697502605/attempts/1) |
| 10-28 06:33 | CI | 推送 | main | success | 8.0 分 | 0.0 分 | [#40697502762](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40697502762/attempts/1) |
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

