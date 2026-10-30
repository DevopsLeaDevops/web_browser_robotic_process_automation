# CI 運行耗時紀錄

更新：2026-10-30 15:00 America/Los_Angeles（PDT，UTC−07:00）。共 823 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 143（163） | 70（85） | 4.1 分（3.0 分） | 7.8 分（6.7 分） | 0.1 分（0.0 分） | 982／304／0 分（848／347／0 分） |
| 桌面端建置 | 109（116） | 87（86） | 5.7 分（4.0 分） | 8.6 分（5.8 分） | 0.1 分（0.1 分） | 14／261／518 分（11／334／334 分） |
| 伺服器分發包 | 100（13） | 94（9） | 2.0 分（2.0 分） | 3.9 分（10.3 分） | 0.1 分（0.1 分） | 331／0／0 分（58／0／0 分） |
| 一鍵安裝腳本 | 99（39） | 89（16） | 0.2 分（3.1 分） | 9.2 分（15.5 分） | 0.0 分（0.1 分） | 339／287／247 分（239／174／45 分） |
| 每晚完整測試 | 19（4） | 1（0） | 47.5 分（50.5 分） | 57.5 分（66.2 分） | 0.1 分（0.0 分） | 770／748／672 分（200／188／61 分） |
| 發布 | 15（3） | 8（2） | 14.1 分（5.9 分） | 15.2 分（6.8 分） | 0.1 分（0.1 分） | 102／67／71 分（7／13／23 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-30 | 17 | 178 | 160 | 121 | 458 |
| 2026-10-29 | 73 | 364 | 228 | 233 | 825 |
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

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 328 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 23.1（23.2） | 29 | `apps/server/tests/test_api.py` |
| 22.5（22.9） | 25 | `apps/server/tests/test_production_api.py` |
| 20.9（22.3） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 19.6（20.1） | 18 | `apps/cli/tests/test_serve.py` |
| 16.5（16.6） | 11 | `apps/server/tests/test_gitsync.py` |
| 15.7（16.4） | 20 | `apps/server/tests/test_recorder_api.py` |
| 14.1（14.8） | 13 | `apps/server/tests/test_replay.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.5（15.7） | 14 | `apps/server/tests/test_workflow_api.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 545 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.7（99.8） | 12 | `apps/server/tests/test_portal.py` |
| 39.9（46.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 35.4（44.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 25.8（31.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 24.7（28.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 22.9（31.2） | 5 | `apps/server/tests/test_production_flow.py` |
| 19.6（19.9） | 18 | `apps/cli/tests/test_serve.py` |
| 17.3（22.3） | 25 | `apps/server/tests/test_production_api.py` |
| 16.6（20.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.9（21.8） | 29 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 785 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 284.3（244.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 140.4（140.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 111.3（104.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 91.7（106.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 66.7（71.4） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 50.7（49.4） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 27.2（27.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.6（5.2） | 2 | `tests\smoke\test_browser.py` |
| 4.3（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.8（2.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 1424 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 169.5（149.5） | 15 | `apps/server/tests/test_portal.py` |
| 143.8（127.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 120.9（102.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 112.1（102.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 111.0（124.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 90.3（90.2） | 18 | `apps/cli/tests/test_serve.py` |
| 71.2（62.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 70.1（70.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 55.7（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.7（41.7） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 1016 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 154.5（145.3） | 15 | `apps/server/tests/test_portal.py` |
| 118.5（103.0） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 117.6（105.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 105.3（104.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 97.5（97.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 70.8（64.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 66.3（70.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 55.8（55.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.6（41.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 32.0（31.2） | 17 | `packages/rpa_runner/tests/test_upload.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 937 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 145.2（145.6） | 15 | `apps/server/tests/test_portal.py` |
| 114.7（108.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 103.0（103.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 101.9（99.1） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 89.8（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 70.3（70.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 66.6（66.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.9（51.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.4（40.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 23.9（24.5） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 999 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 114.6（105.8） | 15 | `apps/server/tests/test_portal.py` |
| 91.9（83.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 79.7（71.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 72.2（65.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 66.6（62.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 51.7（47.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.0（45.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 41.8（39.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.1（35.1） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.0（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 848 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 94.4（109.1） | 15 | `apps/server/tests/test_portal.py` |
| 84.8（84.6） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 65.6（75.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 59.6（65.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 59.2（73.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 43.7（50.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.5（51.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 37.3（42.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.2（35.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.4（19.8） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 613 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 95.9（107.4） | 15 | `apps/server/tests/test_portal.py` |
| 87.0（83.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 65.2（76.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 61.4（73.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 50.1（54.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 40.5（48.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.7（50.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 36.5（41.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.7（35.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 16.7（18.6） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 608 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 97.0（108.1） | 15 | `apps/server/tests/test_portal.py` |
| 85.4（85.1） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 65.4（77.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 57.8（75.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 48.5（53.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 42.2（50.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 40.1（50.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 36.4（42.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.7（35.2） | 4 | `apps/server/tests/test_replay_flow.py` |
| 16.9（18.9） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 1452 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 143.6（108.4） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 139.4（138.5） | 15 | `apps\server\tests\test_portal.py` |
| 116.5（110.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 107.7（103.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.2（86.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 75.9（72.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 68.2（65.1） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 58.7（57.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.5（39.2） | 4 | `apps\server\tests\test_replay_flow.py` |
| 35.4（33.9） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 970 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 141.9（135.3） | 15 | `apps\server\tests\test_portal.py` |
| 112.4（108.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 108.2（105.0） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 105.6（91.2） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 76.7（73.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 75.0（73.6） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 68.1（66.0） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 59.4（55.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.9（39.9） | 4 | `apps\server\tests\test_replay_flow.py` |
| 30.2（29.1） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-30 13:55 America/Los_Angeles（PDT，UTC−07:00），合計 988 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 145.7（134.4） | 15 | `apps\server\tests\test_portal.py` |
| 117.9（101.8） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 109.7（106.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 105.8（98.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 78.6（73.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 77.4（71.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 70.3（64.1） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.9（56.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.6（39.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 30.3（28.9） | 17 | `packages\rpa_runner\tests\test_upload.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-30 14:17 | 一鍵安裝腳本 | 排程 | main | failure | 25.0 分 | 0.0 分 | [#41129907174](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41129907174/attempts/1) |
| 10-30 13:55 | 每晚完整測試 | 排程 | main | failure | 64.3 分 | 6.6 分 | [#41127092839](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41127092839/attempts/1) |
| 10-30 07:45 | 一鍵安裝腳本 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 0.2 分 | 0.0 分 | [#41074479339](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479339/attempts/1) |
| 10-30 07:45 | CI | PR | dependabot/github_actions/actions-d7d93b8548 | success | 4.8 分 | 0.0 分 | [#41074479301](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479301/attempts/1) |
| 10-30 07:45 | 伺服器分發包 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 6.1 分 | 0.1 分 | [#41074479298](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479298/attempts/1) |
| 10-30 07:45 | 桌面端建置 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 7.0 分 | 0.0 分 | [#41074479437](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479437/attempts/1) |
| 10-30 07:45 | 每晚完整測試 | PR | dependabot/github_actions/actions-d7d93b8548 | failure | 56.8 分 | 0.1 分 | [#41074479686](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479686/attempts/1) |
| 10-30 01:55 | 伺服器分發包 | PR | feat/python-nodes | success | 0.3 分 | 0.1 分 | [#41029762241](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762241/attempts/1) |
| 10-30 01:55 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.4 分 | 0.1 分 | [#41029762184](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762184/attempts/1) |
| 10-30 01:55 | CI | PR | feat/python-nodes | success | 2.4 分 | 0.1 分 | [#41029762226](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762226/attempts/1) |
| 10-30 01:17 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.1 分 | [#41025469534](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469534/attempts/1) |
| 10-30 01:17 | 伺服器分發包 | PR | feat/python-nodes | success | 3.0 分 | 0.1 分 | [#41025469544](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469544/attempts/1) |
| 10-30 01:17 | 桌面端建置 | PR | feat/python-nodes | success | 3.1 分 | 0.0 分 | [#41025469542](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469542/attempts/1) |
| 10-30 01:17 | CI | PR | feat/python-nodes | success | 4.7 分 | 0.0 分 | [#41025469550](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469550/attempts/1) |
| 10-30 00:05 | 桌面端建置 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41017890384](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890384/attempts/1) |
| 10-30 00:05 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.1 分 | [#41017890394](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890394/attempts/1) |
| 10-30 00:05 | CI | PR | feat/python-nodes | success | 2.2 分 | 0.1 分 | [#41017890369](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890369/attempts/1) |
| 10-29 23:57 | CI | PR | feat/python-nodes | success | 4.5 分 | 0.1 分 | [#41016235428 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235428/attempts/2) |
| 10-29 23:48 | 桌面端建置 | PR | feat/python-nodes | success | 3.1 分 | 0.0 分 | [#41016235409](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235409/attempts/1) |
| 10-29 23:48 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.3 分 | 0.0 分 | [#41016235505](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235505/attempts/1) |
| 10-29 23:48 | 伺服器分發包 | PR | feat/python-nodes | success | 2.8 分 | 0.1 分 | [#41016235405](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235405/attempts/1) |
| 10-29 23:48 | CI | PR | feat/python-nodes | failure | 7.9 分 | 0.0 分 | [#41016235428](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235428/attempts/1) |
| 10-29 23:42 | 桌面端建置 | PR | feat/python-nodes | cancelled | 6.0 分 | 0.1 分 | [#41015618715](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618715/attempts/1) |
| 10-29 23:42 | CI | PR | feat/python-nodes | failure | 4.7 分 | 0.0 分 | [#41015618744](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618744/attempts/1) |
| 10-29 23:42 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41015618635](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618635/attempts/1) |
| 10-29 23:42 | 伺服器分發包 | PR | feat/python-nodes | failure | 2.0 分 | 0.1 分 | [#41015618773](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618773/attempts/1) |
| 10-29 23:37 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41015158314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158314/attempts/1) |
| 10-29 23:37 | 伺服器分發包 | PR | feat/python-nodes | failure | 2.0 分 | 0.1 分 | [#41015158337](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158337/attempts/1) |
| 10-29 23:37 | CI | PR | feat/python-nodes | cancelled | 5.4 分 | 0.0 分 | [#41015158302](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158302/attempts/1) |
| 10-29 23:37 | 桌面端建置 | PR | feat/python-nodes | cancelled | 5.5 分 | 0.1 分 | [#41015158418](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158418/attempts/1) |
| 10-29 18:59 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#40988997670](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40988997670/attempts/1) |
| 10-29 18:59 | 伺服器分發包 | PR | feat/python-nodes | failure | 2.2 分 | 0.1 分 | [#40988997644](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40988997644/attempts/1) |
| 10-29 18:59 | CI | PR | feat/python-nodes | success | 4.0 分 | 0.0 分 | [#40988997701](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40988997701/attempts/1) |
| 10-29 18:59 | 桌面端建置 | PR | feat/python-nodes | failure | 6.2 分 | 0.2 分 | [#40988997655](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40988997655/attempts/1) |
| 10-29 18:45 | CI | PR | feat/python-nodes | failure | 4.6 分 | 0.0 分 | [#40987682472](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40987682472/attempts/1) |
| 10-29 18:45 | 伺服器分發包 | PR | feat/python-nodes | failure | 0.5 分 | 0.1 分 | [#40987682464](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40987682464/attempts/1) |
| 10-29 18:45 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 2.7 分 | 0.1 分 | [#40987682346](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40987682346/attempts/1) |
| 10-29 18:45 | 桌面端建置 | PR | feat/python-nodes | failure | 7.3 分 | 0.2 分 | [#40987682337](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40987682337/attempts/1) |
| 10-29 18:22 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 3.5 分 | 0.1 分 | [#40985373840](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985373840/attempts/1) |
| 10-29 18:21 | 伺服器分發包 | PR | feat/python-nodes | success | 2.0 分 | 0.1 分 | [#40985373823](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985373823/attempts/1) |

