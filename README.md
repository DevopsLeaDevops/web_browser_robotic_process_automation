# CI 運行耗時紀錄

更新：2026-10-25 04:38 America/Los_Angeles（PDT，UTC−07:00）。共 389 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 182（0） | 96（0） | 3.1 分（0.0 分） | 6.6 分（0.0 分） | 0.0 分（0.0 分） | 943／381／0 分（0／0／0 分） |
| 桌面端建置 | 124（0） | 93（0） | 4.0 分（0.0 分） | 6.5 分（0.0 分） | 0.1 分（0.0 分） | 12／366／416 分（0／0／0 分） |
| 伺服器分發包 | 24（0） | 19（0） | 2.0 分（0.0 分） | 7.5 分（0.0 分） | 0.1 分（0.0 分） | 101／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 50（0） | 26（0） | 3.1 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 303／220／95 分（0／0／0 分） |
| 每晚完整測試 | 6（0） | 0（0） | 47.3 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 297／282／152 分（0／0／0 分） |
| 發布 | 3（0） | 2（0） | 5.9 分（0.0 分） | 6.8 分（0.0 分） | 0.1 分（0.0 分） | 7／13／23 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-25 | 23 | 109 | 48 | 57 | 215 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-25 04:34 America/Los_Angeles（PDT，UTC−07:00），合計 247 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 18.7（18.7） | 29 | `apps/server/tests/test_api.py` |
| 18.1（17.9） | 17 | `apps/cli/tests/test_serve.py` |
| 17.7（17.7） | 24 | `apps/server/tests/test_production_api.py` |
| 16.4（16.4） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.5（12.5） | 20 | `apps/server/tests/test_recorder_api.py` |
| 11.9（11.9） | 11 | `apps/server/tests/test_gitsync.py` |
| 11.0（10.8） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.6（8.6） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-25 04:34 America/Los_Angeles（PDT，UTC−07:00），合計 523 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 69.4（66.9） | 8 | `apps/server/tests/test_portal.py` |
| 42.8（42.2） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 37.0（36.8） | 2 | `apps/server/tests/test_replay_flow.py` |
| 33.0（31.1） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 30.6（30.1） | 5 | `apps/server/tests/test_production_flow.py` |
| 23.1（21.4） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 18.1（17.9） | 17 | `apps/cli/tests/test_serve.py` |
| 17.7（17.2） | 29 | `apps/server/tests/test_api.py` |
| 16.9（16.9） | 24 | `apps/server/tests/test_production_api.py` |
| 16.6（16.0） | 22 | `apps/server/tests/test_remote_worker_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-25 04:34 America/Los_Angeles（PDT，UTC−07:00），合計 672 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 240.2（229.6） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 132.6（111.9） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 122.8（115.1） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 98.5（98.5） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.9（46.8） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 25.3（27.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.3（5.4） | 2 | `tests\smoke\test_browser.py` |
| 4.0（4.0） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.6（2.6） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 1083 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 130.7（116.2） | 11 | `apps/server/tests/test_portal.py` |
| 100.6（111.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 97.4（101.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.9（99.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 89.1（77.2） | 18 | `apps/cli/tests/test_serve.py` |
| 78.8（122.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 70.4（69.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 60.4（58.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.0（51.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 39.9（39.5） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 755 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.0（109.0） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 101.0（122.6） | 11 | `apps/server/tests/test_portal.py` |
| 87.7（87.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 85.6（85.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 81.1（97.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 51.5（59.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.3（59.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 50.0（50.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 38.6（38.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.4（21.4） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 800 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.4（114.8） | 11 | `apps/server/tests/test_portal.py` |
| 94.9（94.9） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 89.7（95.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 88.4（88.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 80.0（83.2） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 69.4（68.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 67.4（69.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.1（52.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.8（38.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 28.7（28.7） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 698 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 74.2（59.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 68.2（67.8） | 11 | `apps/server/tests/test_portal.py` |
| 62.2（62.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 60.2（62.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 48.2（46.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 40.4（41.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 37.5（38.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 36.4（37.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.4（31.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.5（6.3） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 843 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 87.7（83.7） | 11 | `apps/server/tests/test_portal.py` |
| 81.5（66.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.5（76.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 77.1（77.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 54.5（50.4） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 49.9（48.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 49.9（50.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.3（41.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.8（34.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.6（6.0） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 624 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 85.7（82.1） | 11 | `apps/server/tests/test_portal.py` |
| 80.9（67.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.4（75.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 72.7（78.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.1（48.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.6（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.5（40.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 42.2（41.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.9（35.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 20.1（19.9） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 626 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 87.8（83.4） | 11 | `apps/server/tests/test_portal.py` |
| 78.7（67.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 75.5（75.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.3（76.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.5（49.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 49.0（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.8（41.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.6（40.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 36.5（33.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.0（19.5） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 1166 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 116.8（115.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 111.0（109.2） | 11 | `apps\server\tests\test_portal.py` |
| 100.2（99.8） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 87.5（91.1） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 72.5（73.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.9（66.6） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 62.7（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 53.8（54.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 43.9（17.5） | 18 | `packages\rpa_runner\tests\test_profiles.py` |
| 40.0（37.3） | 4 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 785 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 112.0（110.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 103.8（107.7） | 11 | `apps\server\tests\test_portal.py` |
| 92.7（99.8） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 88.6（89.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 67.7（73.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 58.0（63.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.7（56.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 49.6（50.4） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 37.6（37.0） | 4 | `apps\server\tests\test_replay_flow.py` |
| 27.3（27.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-24 17:17 America/Los_Angeles（PDT，UTC−07:00），合計 797 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.3（112.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 97.8（105.3） | 11 | `apps\server\tests\test_portal.py` |
| 90.6（90.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 88.9（101.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 67.8（71.2） | 9 | `apps\server\tests\test_production_flow.py` |
| 59.0（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.6（52.0） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 57.5（56.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 37.1（37.9） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.8（27.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-25 04:34 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 2.0 分 | 0.1 分 | [#40189406755](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40189406755/attempts/1) |
| 10-25 04:34 | CI | PR | claude/project-thread-reisy3 | failure | 4.1 分 | 0.0 分 | [#40189406751](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40189406751/attempts/1) |
| 10-25 04:34 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 3.3 分 | 0.1 分 | [#40189406766](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40189406766/attempts/1) |
| 10-25 04:26 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 3.4 分 | 0.0 分 | [#40188863243](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40188863243/attempts/1) |
| 10-25 04:26 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 3.6 分 | 0.1 分 | [#40188862935](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40188862935/attempts/1) |
| 10-25 04:26 | CI | PR | claude/project-thread-reisy3 | success | 4.0 分 | 0.0 分 | [#40188862909](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40188862909/attempts/1) |
| 10-25 04:26 | 桌面端建置 | PR | claude/project-thread-reisy3 | success | 6.9 分 | 0.1 分 | [#40188862942](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40188862942/attempts/1) |
| 10-25 03:44 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 3.1 分 | 0.1 分 | [#40186013688](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40186013688/attempts/1) |
| 10-25 03:44 | CI | PR | claude/project-thread-reisy3 | failure | 5.5 分 | 0.1 分 | [#40186013698](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40186013698/attempts/1) |
| 10-25 03:44 | 桌面端建置 | PR | claude/project-thread-reisy3 | success | 7.1 分 | 0.1 分 | [#40186013652](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40186013652/attempts/1) |
| 10-25 03:44 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 9.2 分 | 0.1 分 | [#40186013669](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40186013669/attempts/1) |
| 10-25 03:02 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 1.9 分 | 0.1 分 | [#40182993568](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182993568/attempts/1) |
| 10-25 03:01 | 桌面端建置 | PR | claude/project-thread-reisy3 | success | 6.2 分 | 0.1 分 | [#40182993643](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182993643/attempts/1) |
| 10-25 03:00 | CI | PR | claude/project-thread-reisy3 | success | 4.0 分 | 0.1 分 | [#40182993633](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182993633/attempts/1) |
| 10-25 03:00 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 7.7 分 | 0.1 分 | [#40182993569](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182993569/attempts/1) |
| 10-25 02:55 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 3.1 分 | 0.1 分 | [#40182637678](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182637678/attempts/1) |
| 10-25 02:55 | CI | PR | claude/project-thread-reisy3 | failure | 4.1 分 | 0.0 分 | [#40182637684](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182637684/attempts/1) |
| 10-25 02:55 | 桌面端建置 | PR | claude/project-thread-reisy3 | cancelled | 6.3 分 | 0.1 分 | [#40182637687](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182637687/attempts/1) |
| 10-25 02:55 | 伺服器分發包 | PR | claude/project-thread-reisy3 | cancelled | 6.7 分 | 0.1 分 | [#40182637690](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40182637690/attempts/1) |
| 10-25 02:13 | CI | PR | claude/project-thread-reisy3 | success | 1.6 分 | 0.0 分 | [#40179729143](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40179729143/attempts/1) |
| 10-25 02:06 | CI | PR | claude/project-thread-reisy3 | success | 3.3 分 | 0.1 分 | [#40179171731](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40179171731/attempts/1) |
| 10-25 02:04 | CI | PR | claude/project-thread-reisy3 | cancelled | 1.7 分 | 0.0 分 | [#40179140052](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40179140052/attempts/1) |
| 10-25 01:57 | CI | 推送 | main | failure | 6.5 分 | 0.0 分 | [#40178684895](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40178684895/attempts/1) |
| 10-24 22:53 | CI | PR | claude/project-thread-vql00s | success | 3.0 分 | 0.0 分 | [#40167131388](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40167131388/attempts/1) |
| 10-24 22:52 | CI | PR | claude/project-thread-vql00s | cancelled | 0.4 分 | 0.0 分 | [#40167121401](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40167121401/attempts/1) |
| 10-24 20:39 | CI | PR | claude/project-thread-vql00s | success | 3.2 分 | 0.1 分 | [#40158956688](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40158956688/attempts/1) |
| 10-24 20:37 | CI | PR | claude/project-thread-vql00s | cancelled | 1.7 分 | 0.0 分 | [#40158889362](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40158889362/attempts/1) |
| 10-24 17:17 | 一鍵安裝腳本 | PR | fix/scheduled-test-failures | success | 2.7 分 | 0.1 分 | [#40146110080](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110080/attempts/1) |
| 10-24 17:17 | 伺服器分發包 | PR | fix/scheduled-test-failures | success | 3.1 分 | 0.1 分 | [#40146110058](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110058/attempts/1) |
| 10-24 17:17 | CI | PR | fix/scheduled-test-failures | success | 4.1 分 | 0.0 分 | [#40146110114](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110114/attempts/1) |
| 10-24 17:17 | 桌面端建置 | PR | fix/scheduled-test-failures | success | 6.5 分 | 0.1 分 | [#40146110075](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110075/attempts/1) |
| 10-24 17:17 | 每晚完整測試 | PR | fix/scheduled-test-failures | failure | 47.2 分 | 0.1 分 | [#40146110029](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40146110029/attempts/1) |
| 10-24 14:04 | 一鍵安裝腳本 | 排程 | main | failure | 21.2 分 | 0.1 分 | [#40132595370](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40132595370/attempts/1) |
| 10-24 13:43 | 每晚完整測試 | 排程 | main | failure | 47.5 分 | 0.0 分 | [#40131075488](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40131075488/attempts/1) |
| 10-23 19:49 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40055791415](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791415/attempts/1) |
| 10-23 19:49 | CI | PR | claude/project-thread-fr1onb | success | 1.6 分 | 0.0 分 | [#40055791311](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791311/attempts/1) |
| 10-23 19:49 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40055791314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791314/attempts/1) |
| 10-23 19:06 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40052798345](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798345/attempts/1) |
| 10-23 19:06 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40052798310](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798310/attempts/1) |
| 10-23 19:06 | CI | PR | claude/project-thread-fr1onb | success | 1.9 分 | 0.1 分 | [#40052798341](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798341/attempts/1) |

