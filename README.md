# CI 運行耗時紀錄

更新：2026-10-30 01:56 America/Los_Angeles（PDT，UTC−07:00）。共 814 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 148（156） | 71（82） | 4.1 分（3.0 分） | 8.0 分（6.5 分） | 0.1 分（0.0 分） | 1037／307／0 分（782／339／0 分） |
| 桌面端建置 | 111（113） | 88（84） | 5.7 分（4.0 分） | 9.2 分（5.3 分） | 0.1 分（0.1 分） | 15／268／525 分（11／323／316 分） |
| 伺服器分發包 | 102（10） | 96（6） | 2.0 分（1.9 分） | 3.9 分（10.3 分） | 0.1 分（0.1 分） | 339／0／0 分（40／0／0 分） |
| 一鍵安裝腳本 | 98（37） | 87（16） | 0.2 分（3.0 分） | 14.3 分（15.2 分） | 0.0 分（0.1 分） | 336／289／215 分（210／144／45 分） |
| 每晚完整測試 | 18（3） | 1（0） | 47.4 分（40.7 分） | 57.5 分（60.2 分） | 0.1 分（0.0 分） | 703／681／655 分（157／140／0 分） |
| 發布 | 15（3） | 8（2） | 14.1 分（5.9 分） | 15.2 分（6.8 分） | 0.1 分（0.1 分） | 102／67／71 分（7／13／23 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-30 | 8 | 16 | 7 | 0 | 23 |
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

最近一次：2026-10-30 01:17 America/Los_Angeles（PDT，UTC−07:00），合計 350 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 21.4（24.2） | 29 | `apps/server/tests/test_api.py` |
| 20.0（20.0） | 18 | `apps/cli/tests/test_serve.py` |
| 19.6（23.4） | 25 | `apps/server/tests/test_production_api.py` |
| 19.1（22.7） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 17.7（16.6） | 11 | `apps/server/tests/test_gitsync.py` |
| 15.8（15.7） | 14 | `apps/server/tests/test_workflow_api.py` |
| 14.9（14.4） | 13 | `apps/server/tests/test_replay.py` |
| 14.6（16.6） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.6） | 14 | `apps/worker/tests/test_gateway.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-30 01:17 America/Los_Angeles（PDT，UTC−07:00），合計 542 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.4（101.8） | 12 | `apps/server/tests/test_portal.py` |
| 39.0（46.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 33.5（44.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 24.7（31.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 22.0（32.0） | 5 | `apps/server/tests/test_production_flow.py` |
| 20.4（20.1） | 18 | `apps/cli/tests/test_serve.py` |
| 18.9（29.6） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 17.0（19.6） | 15 | `apps/server/tests/test_replay.py` |
| 14.7（21.8） | 29 | `apps/server/tests/test_api.py` |
| 13.8（13.8） | 17 | `apps/worker/tests/test_recorder.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-30 01:17 America/Los_Angeles（PDT，UTC−07:00），合計 778 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 236.0（244.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 137.6（140.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 107.3（104.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 92.4（106.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 74.0（71.4） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 49.9（47.4） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 41.4（9.0） | 2 | `packages\rpa_runner\tests\test_download_browser.py` |
| 26.7（27.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.8（5.1） | 2 | `tests\smoke\test_browser.py` |
| 4.6（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 1513 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 174.2（149.5） | 15 | `apps/server/tests/test_portal.py` |
| 136.9（127.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 127.6（101.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 125.1（124.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 108.2（102.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.5（75.2） | 9 | `apps/server/tests/test_production_flow.py` |
| 89.8（90.2） | 18 | `apps/cli/tests/test_serve.py` |
| 83.7（62.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 65.9（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 46.9（38.2） | 17 | `packages/rpa_runner/tests/test_upload.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 964 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 153.5（137.0） | 15 | `apps/server/tests/test_portal.py` |
| 137.9（97.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 107.3（93.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 105.3（103.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 79.1（63.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 77.2（93.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 67.1（70.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 46.6（50.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.8（40.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 22.0（22.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 1212 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 217.5（145.6） | 15 | `apps/server/tests/test_portal.py` |
| 168.0（102.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 121.6（95.0） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 109.6（67.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 104.5（103.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 103.7（60.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 87.2（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 54.1（51.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 47.6（40.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 39.1（19.4） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 922 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 104.8（105.8） | 15 | `apps/server/tests/test_portal.py` |
| 88.4（81.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 71.3（71.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.1（66.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 62.2（65.1） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 47.2（47.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.2（45.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 39.0（39.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.1（35.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 1040 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 114.8（109.1） | 15 | `apps/server/tests/test_portal.py` |
| 95.0（81.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.3（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 78.1（76.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 69.3（65.6） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.4（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 53.4（50.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.3（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.0（36.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.8（19.2） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 755 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 114.4（107.4） | 15 | `apps/server/tests/test_portal.py` |
| 95.0（82.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.4（80.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 77.7（77.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 60.8（55.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 54.7（54.2） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.9（50.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.4（44.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.7（35.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.0（21.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 758 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.9（108.1） | 15 | `apps/server/tests/test_portal.py` |
| 95.1（81.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.4（80.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 78.6（78.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 60.7（55.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 55.3（54.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.7（51.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.2（44.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.7（36.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.0（21.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 1373 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 139.0（128.9） | 15 | `apps\server\tests\test_portal.py` |
| 108.4（99.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 107.2（106.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 103.5（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 86.5（81.1） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 72.8（72.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.1（63.0） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.8（57.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.7（39.2） | 4 | `apps\server\tests\test_replay_flow.py` |
| 32.2（31.6） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 934 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 135.3（126.9） | 15 | `apps\server\tests\test_portal.py` |
| 104.7（110.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 104.4（104.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 104.2（91.2） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 73.6（65.2） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 72.4（74.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.1（64.6） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.6（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.9（40.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 29.1（29.1） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-29 13:58 America/Los_Angeles（PDT，UTC−07:00），合計 929 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 134.7（127.4） | 15 | `apps\server\tests\test_portal.py` |
| 105.1（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 104.0（91.4） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 101.8（99.1） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 73.5（69.2） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 71.7（71.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 64.1（64.1） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.7（55.9） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.4（38.9） | 4 | `apps\server\tests\test_replay_flow.py` |
| 29.2（29.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-30 01:55 | 伺服器分發包 | PR | feat/python-nodes | success | 0.3 分 | 0.1 分 | [#41029762241](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762241/attempts/1) |
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
| 10-29 18:21 | CI | PR | feat/python-nodes | failure | 4.9 分 | 0.0 分 | [#40985373814](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985373814/attempts/1) |
| 10-29 18:21 | 桌面端建置 | PR | feat/python-nodes | success | 7.4 分 | 0.1 分 | [#40985373809](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985373809/attempts/1) |
| 10-29 18:19 | 伺服器分發包 | PR | feat/python-nodes | failure | 0.5 分 | 0.1 分 | [#40985192142](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985192142/attempts/1) |
| 10-29 18:19 | 桌面端建置 | PR | feat/python-nodes | failure | 0.6 分 | 0.1 分 | [#40985192155](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985192155/attempts/1) |
| 10-29 18:19 | 一鍵安裝腳本 | PR | feat/python-nodes | cancelled | 2.7 分 | 0.0 分 | [#40985192143](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40985192143/attempts/1) |
| 10-29 14:20 | 一鍵安裝腳本 | 排程 | main | failure | 31.7 分 | 0.1 分 | [#40956982407](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40956982407/attempts/1) |
| 10-29 13:58 | 每晚完整測試 | 排程 | main | success | 62.9 分 | 0.1 分 | [#40953751001](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40953751001/attempts/1) |
| 10-29 06:37 | 發布 | 推送 | v0.8.0 | success | 14.1 分 | 2.9 分 | [#40883651046](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883651046/attempts/1) |
| 10-29 06:37 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40883612917](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883612917/attempts/1) |

