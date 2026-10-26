# CI 運行耗時紀錄

更新：2026-10-26 09:01 America/Los_Angeles（PDT，UTC−07:00）。共 516 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 222（0） | 114（0） | 3.3 分（0.0 分） | 7.1 分（0.0 分） | 0.0 分（0.0 分） | 1292／509／0 分（0／0／0 分） |
| 桌面端建置 | 159（0） | 119（0） | 4.1 分（0.0 分） | 6.9 分（0.0 分） | 0.1 分（0.0 分） | 16／496／657 分（0／0／0 分） |
| 伺服器分發包 | 54（0） | 49（0） | 2.0 分（0.0 分） | 6.7 分（0.0 分） | 0.1 分（0.0 分） | 224／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 67（0） | 42（0） | 3.3 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 417／277／162 分（0／0／0 分） |
| 每晚完整測試 | 8（0） | 0（0） | 47.4 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 396／379／232 分（0／0／0 分） |
| 發布 | 6（0） | 5（0） | 7.3 分（0.0 分） | 8.2 分（0.0 分） | 0.1 分（0.0 分） | 30／26／52 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-26 | 55 | 301 | 139 | 117 | 556 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-26 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 1129 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 138.0（138.0） | 14 | `apps/server/tests/test_portal.py` |
| 96.1（96.1） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 94.4（94.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 77.1（77.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 73.3（73.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 69.9（69.9） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 64.7（64.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 62.6（62.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.1（40.1） | 4 | `apps/server/tests/test_replay_flow.py` |
| 25.9（25.9） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-26 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 467 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 76.0（84.0） | 11 | `apps/server/tests/test_portal.py` |
| 39.1（43.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 34.2（38.6） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 23.7（27.2） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 23.4（28.5） | 5 | `apps/server/tests/test_production_flow.py` |
| 21.4（25.4） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 20.3（20.2） | 18 | `apps/cli/tests/test_serve.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.1（19.1） | 29 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-26 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 641 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 228.4（235.9） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 125.5（125.9） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 115.5（106.3） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 90.7（91.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 41.6（39.2） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 26.3（32.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.1（4.3） | 2 | `tests\smoke\test_browser.py` |
| 4.8（3.9） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.9（2.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 884 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 99.4（116.0） | 11 | `apps/server/tests/test_portal.py` |
| 90.3（106.5） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 82.1（82.1） | 17 | `apps/cli/tests/test_serve.py` |
| 79.6（97.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 74.7（97.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 62.7（81.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 45.6（68.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 44.7（53.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.9（51.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.2（37.0） | 2 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 651 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 96.6（108.6） | 11 | `apps/server/tests/test_portal.py` |
| 82.3（85.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 82.1（87.7） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 69.8（87.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.4（84.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 47.7（59.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.1（51.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.4（47.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.6（37.1） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.8（20.2） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 664 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 96.3（107.4） | 11 | `apps/server/tests/test_portal.py` |
| 81.7（92.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 80.8（83.2） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 76.6（89.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 64.9（78.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.8（61.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 49.3（67.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.1（45.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.4（38.5） | 2 | `apps/server/tests/test_replay_flow.py` |
| 19.5（21.0） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 694 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 66.6（68.2） | 11 | `apps/server/tests/test_portal.py` |
| 61.3（61.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 60.3（62.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 59.2（60.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 51.5（48.2） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 40.2（40.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 38.4（38.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.4（37.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.6（32.4） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.0（17.3） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 856 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.5（77.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 78.2（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 75.0（79.7） | 11 | `apps/server/tests/test_portal.py` |
| 66.3（66.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 60.3（54.5） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 54.3（49.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.7（49.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.7（42.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.0（34.0） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.2（19.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 648 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 89.7（85.7） | 11 | `apps/server/tests/test_portal.py` |
| 80.0（77.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 79.9（74.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 66.5（67.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 54.2（48.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.3（45.1） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 50.7（49.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.8（42.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.6（34.6） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.6（20.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 652 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 90.0（87.8） | 11 | `apps/server/tests/test_portal.py` |
| 80.6（74.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 80.3（75.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.9（67.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 54.3（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.9（44.8） | 14 | `packages/rpa_runner/tests/test_debug.py` |
| 51.8（49.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.2（42.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.4（33.7） | 2 | `apps/server/tests/test_replay_flow.py` |
| 21.3（19.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 1227 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.7（112.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 109.5（107.6） | 11 | `apps\server\tests\test_portal.py` |
| 101.0（100.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.6（91.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 84.4（68.2） | 14 | `packages\rpa_runner\tests\test_debug.py` |
| 75.9（72.5） | 9 | `apps\server\tests\test_production_flow.py` |
| 62.3（63.5） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.8（55.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.6（24.5） | 29 | `apps\server\tests\test_api.py` |
| 37.2（37.3） | 2 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 837 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 112.5（108.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 108.1（107.0） | 11 | `apps\server\tests\test_portal.py` |
| 98.9（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 91.4（89.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 75.4（72.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 62.8（62.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 61.1（53.2） | 14 | `packages\rpa_runner\tests\test_debug.py` |
| 58.0（56.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 42.2（37.6） | 2 | `apps\server\tests\test_replay_flow.py` |
| 27.2（27.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-25 13:44 America/Los_Angeles（PDT，UTC−07:00），合計 828 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 111.4（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.4（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 95.0（97.8） | 11 | `apps\server\tests\test_portal.py` |
| 91.4（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 75.8（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.2（66.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 64.4（57.0） | 14 | `packages\rpa_runner\tests\test_debug.py` |
| 59.7（55.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 37.2（37.9） | 2 | `apps\server\tests\test_replay_flow.py` |
| 28.4（27.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-26 08:45 | 伺服器分發包 | 推送 | main | success | 1.9 分 | 0.1 分 | [#40352477923](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352477923/attempts/1) |
| 10-26 08:45 | CI | 推送 | main | failure | 14.8 分 | 0.0 分 | [#40352478076](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352478076/attempts/1) |
| 10-26 08:45 | 桌面端建置 | 推送 | main | failure | 15.2 分 | 0.1 分 | [#40352477751](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352477751/attempts/1) |
| 10-26 08:43 | CI | PR | chore/release-0.6.3 | success | 3.3 分 | 0.1 分 | [#40349430960 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349430960/attempts/2) |
| 10-26 08:27 | 伺服器分發包 | PR | chore/release-0.6.3 | success | 2.0 分 | 0.1 分 | [#40349431129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431129/attempts/1) |
| 10-26 08:27 | CI | PR | chore/release-0.6.3 | failure | 12.2 分 | 0.1 分 | [#40349430960](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349430960/attempts/1) |
| 10-26 08:27 | 桌面端建置 | PR | chore/release-0.6.3 | failure | 20.2 分 | 0.0 分 | [#40349431057](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431057/attempts/1) |
| 10-26 08:27 | 一鍵安裝腳本 | PR | chore/release-0.6.3 | success | 23.2 分 | 20.6 分 | [#40349431075](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431075/attempts/1) |
| 10-26 08:24 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.3 分 | 0.0 分 | [#40337307053 第 3 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/3) |
| 10-26 08:24 | CI | 推送 | main | failure | 7.2 分 | 0.0 分 | [#40349006150](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349006150/attempts/1) |
| 10-26 08:24 | 伺服器分發包 | 推送 | main | success | 7.3 分 | 0.1 分 | [#40349005945](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349005945/attempts/1) |
| 10-26 08:24 | 桌面端建置 | 推送 | main | failure | 20.5 分 | 0.0 分 | [#40349006001](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349006001/attempts/1) |
| 10-26 07:31 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.0 分 | 0.0 分 | [#40337307053 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/2) |
| 10-26 07:12 | 伺服器分發包 | PR | fix/remote-debug-reload | success | 3.7 分 | 0.1 分 | [#40337307355](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307355/attempts/1) |
| 10-26 07:12 | CI | PR | fix/remote-debug-reload | success | 3.7 分 | 0.1 分 | [#40337307103](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307103/attempts/1) |
| 10-26 07:12 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.3 分 | 0.0 分 | [#40337307053](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/1) |
| 10-26 07:10 | 桌面端建置 | PR | fix/remote-debug-reload | cancelled | 1.6 分 | 0.0 分 | [#40337150811](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337150811/attempts/1) |
| 10-26 07:10 | CI | PR | fix/remote-debug-reload | cancelled | 1.8 分 | 0.1 分 | [#40337151171](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337151171/attempts/1) |
| 10-26 05:06 | 發布 | 推送 | v0.6.2 | success | 8.7 分 | 0.1 分 | [#40320045782](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40320045782/attempts/1) |
| 10-26 05:04 | CI | 推送 | main | failure | 5.1 分 | 0.0 分 | [#40319590219](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590219/attempts/1) |
| 10-26 05:03 | 伺服器分發包 | 推送 | main | success | 2.8 分 | 0.1 分 | [#40319590232](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590232/attempts/1) |
| 10-26 05:03 | 一鍵安裝腳本 | 推送 | main | success | 3.4 分 | 0.1 分 | [#40319590126](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590126/attempts/1) |
| 10-26 05:03 | 桌面端建置 | 推送 | main | success | 6.0 分 | 0.1 分 | [#40319590253](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590253/attempts/1) |
| 10-26 04:56 | CI | PR | chore/release-0.6.2 | success | 1.9 分 | 0.0 分 | [#40318816599](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318816599/attempts/1) |
| 10-26 04:56 | 一鍵安裝腳本 | PR | chore/release-0.6.2 | success | 0.1 分 | 0.0 分 | [#40318814074](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318814074/attempts/1) |
| 10-26 04:56 | 伺服器分發包 | PR | chore/release-0.6.2 | success | 0.2 分 | 0.0 分 | [#40318814050](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318814050/attempts/1) |
| 10-26 04:48 | 伺服器分發包 | PR | chore/release-0.6.2 | success | 1.9 分 | 0.1 分 | [#40317826908](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317826908/attempts/1) |
| 10-26 04:48 | 一鍵安裝腳本 | PR | chore/release-0.6.2 | success | 3.7 分 | 0.5 分 | [#40317826682](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317826682/attempts/1) |
| 10-26 04:48 | CI | PR | chore/release-0.6.2 | success | 4.1 分 | 0.0 分 | [#40317826718](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317826718/attempts/1) |
| 10-26 04:48 | 桌面端建置 | PR | chore/release-0.6.2 | success | 6.2 分 | 0.1 分 | [#40317826710](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317826710/attempts/1) |
| 10-26 04:46 | 伺服器分發包 | 推送 | main | success | 2.9 分 | 0.1 分 | [#40317590910](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317590910/attempts/1) |
| 10-26 04:46 | 桌面端建置 | 推送 | main | success | 6.9 分 | 0.1 分 | [#40317590938](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317590938/attempts/1) |
| 10-26 04:46 | CI | 推送 | main | cancelled | 17.9 分 | 0.0 分 | [#40317590911](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40317590911/attempts/1) |
| 10-26 04:17 | 桌面端建置 | PR | fix/device-update-version | success | 0.1 分 | 0.0 分 | [#40313906636](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40313906636/attempts/1) |
| 10-26 04:17 | 伺服器分發包 | PR | fix/device-update-version | success | 0.1 分 | 0.0 分 | [#40313906714](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40313906714/attempts/1) |
| 10-26 04:17 | CI | PR | fix/device-update-version | success | 1.8 分 | 0.1 分 | [#40313906715](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40313906715/attempts/1) |
| 10-26 03:58 | 桌面端建置 | PR | fix/device-update-version | success | 6.0 分 | 0.1 分 | [#40311293027](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40311293027/attempts/1) |
| 10-26 03:57 | CI | PR | fix/device-update-version | success | 13.0 分 | 0.0 分 | [#40311293033](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40311293033/attempts/1) |
| 10-26 03:56 | 伺服器分發包 | PR | fix/device-update-version | success | 2.8 分 | 0.1 分 | [#40311293095](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40311293095/attempts/1) |
| 10-26 03:42 | 伺服器分發包 | PR | fix/device-update-version | success | 3.8 分 | 0.1 分 | [#40309495394](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40309495394/attempts/1) |

