# CI 運行耗時紀錄

更新：2026-11-06 18:08 America/Los_Angeles（PST，UTC−08:00）。共 862 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 6（139） | 3（67） | 5.3 分（4.1 分） | 6.1 分（7.8 分） | 0.0 分（0.1 分） | 48／8／0 分（955／295／0 分） |
| 桌面端建置 | 4（106） | 3（84） | 6.1 分（5.4 分） | 20.2 分（8.6 分） | 0.1 分（0.0 分） | 1／10／18 分（14／250／488 分） |
| 伺服器分發包 | 7（96） | 7（90） | 0.2 分（2.0 分） | 3.5 分（4.6 分） | 0.0 分（0.1 分） | 12／0／0 分（319／0／0 分） |
| 一鍵安裝腳本 | 13（96） | 8（86） | 22.4 分（0.2 分） | 27.9 分（14.3 分） | 0.1 分（0.0 分） | 189／247／102 分（332／282／241 分） |
| 每晚完整測試 | 9（19） | 1（1） | 53.5 分（47.5 分） | 57.5 分（57.5 分） | 0.1 分（0.1 分） | 498／419／200 分（770／748／672 分） |
| 發布 | 0（15） | 0（8） | 0.0 分（14.1 分） | 0.0 分（15.2 分） | 0.0 分（0.1 分） | 0／0／0 分（102／67／71 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-11-06 | 16 | 182 | 149 | 115 | 446 |
| 2026-11-05 | 12 | 105 | 100 | 9 | 214 |
| 2026-11-04 | 2 | 117 | 87 | 0 | 203 |
| 2026-11-03 | 2 | 91 | 81 | 0 | 171 |
| 2026-11-02 | 2 | 87 | 90 | 0 | 177 |
| 2026-11-01 | 2 | 86 | 92 | 99 | 276 |
| 2026-10-31 | 3 | 80 | 86 | 97 | 263 |
| 2026-10-30 | 17 | 178 | 160 | 121 | 458 |
| 2026-10-29 | 73 | 364 | 228 | 233 | 825 |
| 2026-10-28 | 69 | 256 | 115 | 22 | 392 |
| 2026-10-27 | 76 | 286 | 142 | 101 | 528 |
| 2026-10-26 | 127 | 743 | 530 | 510 | 1783 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 3 | 4 | 0 | 0 | 4 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-11-06 17:50 America/Los_Angeles（PST，UTC−08:00），合計 1200 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 133.2（133.2） | 15 | `apps/server/tests/test_portal.py` |
| 104.7（103.8） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 94.2（92.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 84.4（84.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 69.7（71.2） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 62.5（65.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 59.7（59.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 53.1（60.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.0（39.1） | 4 | `apps/server/tests/test_replay_flow.py` |
| 22.6（22.6） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-11-06 17:50 America/Los_Angeles（PST，UTC−08:00），合計 552 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.4（103.8） | 12 | `apps/server/tests/test_portal.py` |
| 39.2（45.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 32.6（44.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 25.0（31.6） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 22.7（31.8） | 5 | `apps/server/tests/test_production_flow.py` |
| 20.7（30.1） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 20.0（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 17.4（19.6） | 15 | `apps/server/tests/test_replay.py` |
| 17.2（21.1） | 29 | `apps/server/tests/test_api.py` |
| 15.4（21.5） | 25 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 758 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 251.2（242.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 134.1（140.4） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 104.2（104.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 86.9（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 61.4（71.4） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 46.7（49.9） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 38.5（31.1） | 2 | `packages\rpa_runner\tests\test_download_browser.py` |
| 23.6（27.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.8（4.9） | 2 | `tests\smoke\test_browser.py` |
| 4.4（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 1365 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 157.7（157.7） | 15 | `apps/server/tests/test_portal.py` |
| 119.8（130.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 110.4（110.4） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 101.3（102.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 97.9（114.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 90.1（89.9） | 18 | `apps/cli/tests/test_serve.py` |
| 66.4（70.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 63.9（63.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.5（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.4（41.4） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 982 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 147.8（147.8） | 15 | `apps/server/tests/test_portal.py` |
| 110.5（97.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 107.6（106.0） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 106.1（105.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 90.8（91.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 71.0（70.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 64.0（64.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 50.4（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.3（40.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 25.2（24.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 1012 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 153.8（148.3） | 15 | `apps/server/tests/test_portal.py` |
| 114.7（114.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 107.7（101.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 107.7（103.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 95.4（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 69.8（69.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 67.0（66.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.3（51.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.0（41.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 27.1（23.2） | 17 | `packages/rpa_runner/tests/test_upload.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 1089 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.3（107.7） | 15 | `apps/server/tests/test_portal.py` |
| 94.2（89.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 85.2（73.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 75.9（65.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 68.8（64.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.7（47.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.0（48.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.8（39.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.4（35.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.6（18.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 947 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 104.8（110.8） | 15 | `apps/server/tests/test_portal.py` |
| 88.6（90.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 72.4（78.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.9（70.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 60.9（68.7） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 46.5（49.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.3（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.9（39.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 33.8（36.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 683 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 104.8（108.4） | 15 | `apps/server/tests/test_portal.py` |
| 88.5（90.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 72.1（76.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 64.9（67.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 52.5（55.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 45.0（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.3（50.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.0（40.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.8（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 17.9（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 679 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 103.7（107.9） | 15 | `apps/server/tests/test_portal.py` |
| 88.7（89.7） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 71.0（73.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.1（67.0） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 51.9（54.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 44.6（47.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.3（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.9（40.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.2（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 17.8（17.8） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 1273 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.4（128.4） | 15 | `apps\server\tests\test_portal.py` |
| 96.1（23.6） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 95.7（103.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 93.3（104.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 89.9（89.9） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 87.0（90.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 66.1（66.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 54.2（58.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 50.9（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 35.9（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 805 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 117.9（119.5） | 15 | `apps\server\tests\test_portal.py` |
| 93.4（98.1） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 87.8（97.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 81.2（93.3） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 63.0（65.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 60.8（65.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 51.7（58.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 46.5（53.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 35.0（37.8） | 4 | `apps\server\tests\test_replay_flow.py` |
| 21.5（21.0） | 3 | `apps\server\tests\test_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-11-06 12:59 America/Los_Angeles（PST，UTC−08:00），合計 800 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.1（121.4） | 15 | `apps\server\tests\test_portal.py` |
| 93.9（97.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 93.8（98.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 84.2（89.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 60.5（67.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 55.2（68.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 50.1（58.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 47.7（52.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 35.1（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 22.6（22.8） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 11-06 18:08 | 伺服器分發包 | PR | docs/m6-status | success | 0.1 分 | 0.0 分 | [#42327694541](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42327694541/attempts/1) |
| 11-06 18:08 | 一鍵安裝腳本 | PR | docs/m6-status | success | 0.2 分 | 0.0 分 | [#42327694594](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42327694594/attempts/1) |
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
| 11-05 17:14 | CI | 推送 | main | failure | 6.0 分 | 0.0 分 | [#42142485832](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42142485832/attempts/1) |
| 11-05 13:26 | 一鍵安裝腳本 | 排程 | main | failure | 27.8 分 | 0.1 分 | [#42112596205](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42112596205/attempts/1) |
| 11-05 13:03 | 每晚完整測試 | 排程 | main | failure | 56.9 分 | 0.1 分 | [#42109158349](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/42109158349/attempts/1) |
| 11-04 13:30 | 一鍵安裝腳本 | 排程 | main | failure | 26.5 分 | 0.1 分 | [#41916641496](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41916641496/attempts/1) |
| 11-04 13:06 | 每晚完整測試 | 排程 | main | failure | 57.2 分 | 0.0 分 | [#41912880655](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41912880655/attempts/1) |
| 11-03 13:24 | 一鍵安裝腳本 | 排程 | main | failure | 22.4 分 | 0.1 分 | [#41721456924](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41721456924/attempts/1) |
| 11-03 13:01 | 每晚完整測試 | 排程 | main | failure | 49.4 分 | 0.1 分 | [#41717981858](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41717981858/attempts/1) |
| 11-02 13:24 | 一鍵安裝腳本 | 排程 | main | failure | 27.9 分 | 0.1 分 | [#41527996629](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41527996629/attempts/1) |
| 11-02 12:57 | 每晚完整測試 | 排程 | main | failure | 52.0 分 | 0.1 分 | [#41523925177](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41523925177/attempts/1) |
| 11-01 13:15 | 一鍵安裝腳本 | 排程 | main | success | 26.6 分 | 0.1 分 | [#41351111726](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41351111726/attempts/1) |
| 11-01 12:51 | 每晚完整測試 | 排程 | main | failure | 58.2 分 | 8.2 分 | [#41349013309](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41349013309/attempts/1) |
| 10-31 16:17 | 每晚完整測試 | 排程 | main | success | 7.2 分 | 0.1 分 | [#41251871759](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41251871759/attempts/1) |
| 10-31 14:14 | 一鍵安裝腳本 | 排程 | main | success | 26.0 分 | 0.1 分 | [#41242687723](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41242687723/attempts/1) |
| 10-31 13:51 | 每晚完整測試 | 排程 | main | failure | 46.6 分 | 0.1 分 | [#41240812130](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41240812130/attempts/1) |
| 10-30 14:17 | 一鍵安裝腳本 | 排程 | main | failure | 25.0 分 | 0.0 分 | [#41129907174](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41129907174/attempts/1) |

