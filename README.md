# CI 運行耗時紀錄

更新：2026-10-24 17:21 America/Los_Angeles（PDT，UTC−07:00）。共 360 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 169（0） | 90（0） | 3.0 分（0.0 分） | 6.6 分（0.0 分） | 0.0 分（0.0 分） | 883／360／0 分（0／0／0 分） |
| 桌面端建置 | 119（0） | 89（0） | 4.0 分（0.0 分） | 6.0 分（0.0 分） | 0.1 分（0.0 分） | 12／346／364 分（0／0／0 分） |
| 伺服器分發包 | 19（0） | 15（0） | 1.9 分（0.0 分） | 7.5 分（0.0 分） | 0.1 分（0.0 分） | 74／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 45（0） | 21（0） | 3.0 分（0.0 分） | 17.1 分（0.0 分） | 0.1 分（0.0 分） | 268／209／80 分（0／0／0 分） |
| 每晚完整測試 | 5（0） | 0（0） | 47.5 分（0.0 分） | 66.2 分（0.0 分） | 0.0 分（0.0 分） | 248／235／107 分（0／0／0 分） |
| 發布 | 3（0） | 2（0） | 5.9 分（0.0 分） | 6.8 分（0.0 分） | 0.1 分（0.0 分） | 7／13／23 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-24 | 5 | 81 | 81 | 75 | 237 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 231 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.5（12.6） | 18 | `apps/cli/tests/test_serve.py` |
| 19.1（23.5） | 29 | `apps/server/tests/test_api.py` |
| 18.1（21.6） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 18.1（22.3） | 24 | `apps/server/tests/test_production_api.py` |
| 14.1（16.8） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.9（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.3（13.5） | 11 | `apps/server/tests/test_gitsync.py` |
| 10.5（13.1） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.3（11.0） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 474 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 62.8（65.7） | 8 | `apps/server/tests/test_portal.py` |
| 45.9（37.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 37.0（42.1） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 27.9（30.0） | 5 | `apps/server/tests/test_production_flow.py` |
| 27.8（31.8） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 23.4（23.9） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 19.4（12.2） | 18 | `apps/cli/tests/test_serve.py` |
| 17.5（19.6） | 29 | `apps/server/tests/test_api.py` |
| 16.5（18.1） | 24 | `apps/server/tests/test_production_api.py` |
| 16.2（17.2） | 22 | `apps/server/tests/test_remote_worker_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 632 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 229.6（234.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 114.8（118.2） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 106.4（141.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 95.2（106.5） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 45.1（45.1） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 24.9（24.9） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.2（4.7） | 1 | `apps\desktop\tests\test_selftest.py` |
| 5.4（5.4） | 2 | `tests\smoke\test_browser.py` |
| 4.2（3.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 1137 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 122.1（123.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 116.0（116.1） | 11 | `apps/server/tests/test_portal.py` |
| 112.1（111.5） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 101.3（103.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 99.7（104.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 76.2（76.7） | 17 | `apps/cli/tests/test_serve.py` |
| 69.4（69.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 58.9（56.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.4（54.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.2（37.9） | 2 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 778 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 122.6（170.0） | 11 | `apps/server/tests/test_portal.py` |
| 97.2（114.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 85.3（116.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 84.3（107.1） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 81.9（163.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 59.4（65.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 59.4（64.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 45.0（71.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 39.9（38.5） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.8（24.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 784 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 114.8（132.4） | 11 | `apps/server/tests/test_portal.py` |
| 107.6（101.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 92.5（108.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.2（106.3） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 72.4（100.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 69.5（70.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 68.2（64.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.8（59.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 38.7（38.6） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.6（23.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 669 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 67.4（67.4） | 11 | `apps/server/tests/test_portal.py` |
| 61.0（63.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 60.6（65.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 59.2（59.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 47.0（45.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 40.7（42.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 38.7（38.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.2（37.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 31.9（31.5） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.3（17.3） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 844 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 89.1（79.7） | 11 | `apps/server/tests/test_portal.py` |
| 82.1（75.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 79.0（78.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 66.7（64.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 53.5（50.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.9（47.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 51.5（47.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.6（40.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.3（34.0） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.4（19.5） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 644 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 89.0（78.4） | 11 | `apps/server/tests/test_portal.py` |
| 82.9（82.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 80.0（74.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.1（64.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 52.5（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.3（48.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.6（40.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 45.1（39.2） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 35.6（34.2） | 2 | `apps/server/tests/test_replay_flow.py` |
| 20.6（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 643 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 89.3（79.1） | 11 | `apps/server/tests/test_portal.py` |
| 81.3（78.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 78.6（75.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.0（64.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 53.9（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.5（49.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.2（41.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 44.8（39.2） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 35.3（29.0） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.0（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 1134 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 112.1（115.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 107.4（107.4） | 11 | `apps\server\tests\test_portal.py` |
| 98.2（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.1（92.4） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 71.5（74.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 68.2（67.2） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 63.5（66.1） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 53.9（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 52.6（35.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 36.9（37.1） | 2 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 804 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.0（108.4） | 11 | `apps\server\tests\test_portal.py` |
| 106.6（108.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.6（100.1） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 89.9（90.2） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 72.4（73.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 63.6（64.0） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.2（56.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 51.1（51.1） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 37.0（37.0） | 2 | `apps\server\tests\test_replay_flow.py` |
| 25.4（27.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-24 13:43 America/Los_Angeles（PDT，UTC−07:00），合計 812 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 106.3（105.4） | 11 | `apps\server\tests\test_portal.py` |
| 106.2（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 101.2（101.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.7（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 71.9（71.9） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.7（66.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.0（55.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 52.0（52.0） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 37.9（38.5） | 2 | `apps\server\tests\test_replay_flow.py` |
| 27.2（27.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-24 17:17 | 一鍵安裝腳本 | PR | fix/scheduled-test-failures | success | 2.7 分 | 0.1 分 | [#40146110080](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110080/attempts/1) |
| 10-24 17:17 | 伺服器分發包 | PR | fix/scheduled-test-failures | success | 3.1 分 | 0.1 分 | [#40146110058](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110058/attempts/1) |
| 10-24 17:17 | CI | PR | fix/scheduled-test-failures | success | 4.1 分 | 0.0 分 | [#40146110114](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110114/attempts/1) |
| 10-24 14:04 | 一鍵安裝腳本 | 排程 | main | failure | 21.2 分 | 0.1 分 | [#40132595370](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40132595370/attempts/1) |
| 10-24 13:43 | 每晚完整測試 | 排程 | main | failure | 47.5 分 | 0.0 分 | [#40131075488](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40131075488/attempts/1) |
| 10-23 19:49 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40055791415](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791415/attempts/1) |
| 10-23 19:49 | CI | PR | claude/project-thread-fr1onb | success | 1.6 分 | 0.0 分 | [#40055791311](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791311/attempts/1) |
| 10-23 19:49 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40055791314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791314/attempts/1) |
| 10-23 19:06 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40052798345](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798345/attempts/1) |
| 10-23 19:06 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40052798310](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798310/attempts/1) |
| 10-23 19:06 | CI | PR | claude/project-thread-fr1onb | success | 1.9 分 | 0.1 分 | [#40052798341](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798341/attempts/1) |
| 10-23 18:47 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 1.9 分 | 0.1 分 | [#40051380469](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380469/attempts/1) |
| 10-23 18:47 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 3.3 分 | 0.1 分 | [#40051380395](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380395/attempts/1) |
| 10-23 18:47 | CI | PR | claude/project-thread-fr1onb | success | 5.0 分 | 0.0 分 | [#40051380526](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380526/attempts/1) |
| 10-23 18:47 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.3 分 | 0.1 分 | [#40051380418](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380418/attempts/1) |
| 10-23 18:35 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 1.7 分 | 0.1 分 | [#40050479134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479134/attempts/1) |
| 10-23 18:35 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 2.7 分 | 0.0 分 | [#40050479154](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479154/attempts/1) |
| 10-23 18:35 | CI | PR | claude/project-thread-fr1onb | success | 4.3 分 | 0.0 分 | [#40050479167](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479167/attempts/1) |
| 10-23 18:35 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.5 分 | 0.1 分 | [#40050479096](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479096/attempts/1) |
| 10-23 18:11 | 伺服器分發包 | 推送 | main | success | 3.5 分 | 0.1 分 | [#40048678122](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048678122/attempts/1) |
| 10-23 18:11 | 桌面端建置 | 推送 | main | success | 6.3 分 | 0.1 分 | [#40048678072](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048678072/attempts/1) |
| 10-23 18:11 | CI | 推送 | main | failure | 6.6 分 | 0.0 分 | [#40048677994](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048677994/attempts/1) |
| 10-23 14:11 | 一鍵安裝腳本 | 排程 | main | failure | 21.9 分 | 0.1 分 | [#40024981126](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40024981126/attempts/1) |
| 10-23 13:50 | 每晚完整測試 | 排程 | main | failure | 66.2 分 | 5.0 分 | [#40022244500](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40022244500/attempts/1) |
| 10-23 09:11 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 2.4 分 | 0.1 分 | [#39984702407](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702407/attempts/1) |
| 10-23 09:11 | CI | PR | claude/project-thread-fr1onb | failure | 4.6 分 | 0.1 分 | [#39984702558](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702558/attempts/1) |
| 10-23 09:11 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.7 分 | 1.2 分 | [#39984702320](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702320/attempts/1) |
| 10-23 09:11 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | failure | 15.1 分 | 0.1 分 | [#39984702272](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702272/attempts/1) |
| 10-23 08:51 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 7.5 分 | 0.1 分 | [#39981852267](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852267/attempts/1) |
| 10-23 08:51 | CI | PR | claude/project-thread-fr1onb | failure | 14.7 分 | 0.0 分 | [#39981852293](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852293/attempts/1) |
| 10-23 08:51 | 桌面端建置 | PR | claude/project-thread-fr1onb | failure | 15.2 分 | 0.1 分 | [#39981852243](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852243/attempts/1) |
| 10-23 06:44 | CI | PR | claude/project-thread-fr1onb | success | 11.9 分 | 0.1 分 | [#39963718445](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39963718445/attempts/1) |
| 10-23 04:08 | CI | PR | claude/project-thread-u3rhl1 | success | 2.7 分 | 0.0 分 | [#39943337519 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337519/attempts/2) |
| 10-23 04:02 | CI | PR | claude/project-thread-u3rhl1 | failure | 3.5 分 | 0.0 分 | [#39943337519](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337519/attempts/1) |
| 10-23 04:02 | 伺服器分發包 | PR | claude/project-thread-u3rhl1 | success | 3.9 分 | 0.1 分 | [#39943337503](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337503/attempts/1) |
| 10-23 04:02 | 桌面端建置 | PR | claude/project-thread-u3rhl1 | success | 6.5 分 | 0.1 分 | [#39943337488](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337488/attempts/1) |
| 10-23 03:34 | CI | PR | claude/project-thread-ab62tv | success | 9.7 分 | 0.1 分 | [#39940096023](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39940096023/attempts/1) |
| 10-23 03:29 | CI | 推送 | main | failure | 6.6 分 | 0.0 分 | [#39939492994](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39939492994/attempts/1) |
| 10-22 23:40 | CI | PR | claude/project-thread-ab62tv | success | 4.4 分 | 0.1 分 | [#39912807129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39912807129/attempts/1) |
| 10-22 23:37 | CI | PR | claude/project-thread-ab62tv | cancelled | 2.9 分 | 0.1 分 | [#39912660139](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39912660139/attempts/1) |

