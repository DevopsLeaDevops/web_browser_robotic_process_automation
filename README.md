# CI 運行耗時紀錄

更新：2026-11-06 07:38 America/Los_Angeles（PST，UTC−08:00）。共 854 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 5（145） | 2（70） | 4.6 分（4.1 分） | 6.1 分（7.9 分） | 0.0 分（0.1 分） | 38／8／0 分（1003／312／0 分） |
| 桌面端建置 | 3（111） | 2（88） | 6.5 分（5.7 分） | 20.2 分（9.2 分） | 0.1 分（0.1 分） | 1／10／9 分（15／269／527 分） |
| 伺服器分發包 | 5（102） | 5（96） | 0.2 分（2.0 分） | 3.6 分（4.6 分） | 0.0 分（0.1 分） | 12／0／0 分（343／0／0 分） |
| 一鍵安裝腳本 | 11（100） | 6（89） | 25.0 分（0.2 分） | 27.8 分（14.3 分） | 0.1 分（0.0 分） | 194／240／97 分（336／289／215 分） |
| 每晚完整測試 | 9（19） | 1（1） | 53.5 分（47.5 分） | 58.2 分（57.5 分） | 0.1 分（0.1 分） | 492／428／197 分（760／737／666 分） |
| 發布 | 0（15） | 0（8） | 0.0 分（14.1 分） | 0.0 分（15.2 分） | 0.0 分（0.1 分） | 0／0／0 分（102／67／71 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-11-06 | 8 | 87 | 64 | 0 | 151 |
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
| 2026-10-23 | 26 | 154 | 120 | 105 | 379 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 338 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 21.0（21.0） | 29 | `apps/server/tests/test_api.py` |
| 19.9（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 19.5（19.5） | 25 | `apps/server/tests/test_production_api.py` |
| 18.6（20.9） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.6（15.7） | 11 | `apps/server/tests/test_gitsync.py` |
| 14.3（14.5） | 20 | `apps/server/tests/test_recorder_api.py` |
| 14.2（13.1） | 14 | `apps/worker/tests/test_gateway.py` |
| 14.0（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.4（13.4） | 14 | `apps/server/tests/test_workflow_api.py` |
| 12.9（14.7） | 13 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 758 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.2（103.8） | 12 | `apps/server/tests/test_portal.py` |
| 49.4（46.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 47.6（45.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 33.2（32.3） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 33.1（31.9） | 5 | `apps/server/tests/test_production_flow.py` |
| 32.2（30.7） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 23.5（19.6） | 15 | `apps/server/tests/test_replay.py` |
| 23.1（22.4） | 29 | `apps/server/tests/test_api.py` |
| 23.0（22.6） | 25 | `apps/server/tests/test_production_api.py` |
| 20.8（20.5） | 22 | `apps/server/tests/test_remote_worker_api.py` |

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

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 1446 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 172.0（149.9） | 15 | `apps/server/tests/test_portal.py` |
| 130.4（130.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 124.6（124.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 115.4（103.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 110.6（103.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 89.8（89.9） | 18 | `apps/cli/tests/test_serve.py` |
| 83.8（70.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 70.9（70.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 66.1（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.5（41.6） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 953 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 158.7（145.3） | 15 | `apps/server/tests/test_portal.py` |
| 122.8（105.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 106.0（104.7） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 95.0（97.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.8（93.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 70.0（70.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 65.7（64.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 46.2（50.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.0（40.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 25.1（20.7） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 990 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 148.7（148.3） | 15 | `apps/server/tests/test_portal.py` |
| 124.8（109.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 112.7（103.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 106.3（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 102.5（99.6） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.8（70.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 63.5（66.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.5（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.2（40.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 27.0（20.4） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 964 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.7（107.7） | 15 | `apps/server/tests/test_portal.py` |
| 88.1（89.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 71.6（73.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 64.3（64.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 62.9（65.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 45.3（48.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.0（47.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 38.0（39.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.1（35.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1096 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 116.0（110.8） | 15 | `apps/server/tests/test_portal.py` |
| 95.0（90.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 85.6（78.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 78.2（70.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 71.3（68.7） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.2（49.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.0（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.7（39.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.5（36.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.8（19.2） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 798 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.0（108.4） | 15 | `apps/server/tests/test_portal.py` |
| 96.0（90.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 84.8（76.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 80.1（67.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 61.2（55.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.9（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 54.3（50.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.3（40.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 37.5（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.5（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 786 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 114.7（107.9） | 15 | `apps/server/tests/test_portal.py` |
| 95.7（89.7） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 82.8（73.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 79.6（67.0） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 61.2（54.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.9（47.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.8（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.1（40.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.2（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.2（17.8） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 1307 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 128.4（128.4） | 15 | `apps\server\tests\test_portal.py` |
| 104.0（104.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 95.7（103.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 94.3（90.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 80.3（84.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 65.0（65.0） | 9 | `apps\server\tests\test_production_flow.py` |
| 57.4（58.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 49.9（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 37.4（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 29.7（8.0） | 7 | `apps\server\tests\test_agent_api.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 883 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 125.6（119.5） | 15 | `apps\server\tests\test_portal.py` |
| 98.7（98.7） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 97.4（97.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 93.3（93.3） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 65.8（65.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 63.9（65.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 57.3（58.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 53.1（53.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 37.6（37.8） | 4 | `apps\server\tests\test_replay_flow.py` |
| 25.8（25.8） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-11-06 06:44 America/Los_Angeles（PST，UTC−08:00），合計 922 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 128.9（121.4） | 15 | `apps\server\tests\test_portal.py` |
| 100.9（97.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 100.3（89.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 98.0（98.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 69.4（68.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.6（67.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 62.1（58.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 58.5（52.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.9（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 25.4（23.7） | 4 | `apps\server\tests\test_recorder_flow.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
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
| 10-30 13:55 | 每晚完整測試 | 排程 | main | failure | 64.3 分 | 6.6 分 | [#41127092839](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41127092839/attempts/1) |
| 10-30 07:45 | 一鍵安裝腳本 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 0.2 分 | 0.0 分 | [#41074479339](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479339/attempts/1) |
| 10-30 07:45 | CI | PR | dependabot/github_actions/actions-d7d93b8548 | success | 4.8 分 | 0.0 分 | [#41074479301](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479301/attempts/1) |
| 10-30 07:45 | 伺服器分發包 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 6.1 分 | 0.1 分 | [#41074479298](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479298/attempts/1) |
| 10-30 07:45 | 桌面端建置 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 7.0 分 | 0.0 分 | [#41074479437](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479437/attempts/1) |
| 10-30 07:45 | 每晚完整測試 | PR | dependabot/github_actions/actions-d7d93b8548 | failure | 56.8 分 | 0.1 分 | [#41074479686](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479686/attempts/1) |
| 10-30 01:55 | 伺服器分發包 | PR | feat/python-nodes | success | 0.3 分 | 0.1 分 | [#41029762241](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762241/attempts/1) |
| 10-30 01:55 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.4 分 | 0.1 分 | [#41029762184](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762184/attempts/1) |

