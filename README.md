# CI 運行耗時紀錄

更新：2026-10-27 08:50 America/Los_Angeles（PDT，UTC−07:00）。共 615 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 211（35） | 102（24） | 3.6 分（2.9 分） | 7.2 分（5.1 分） | 0.0 分（0.0 分） | 1279／482／0 分（149／65／0 分） |
| 桌面端建置 | 153（29） | 116（23） | 4.3 分（3.8 分） | 9.2 分（4.1 分） | 0.1 分（0.1 分） | 17／467／696 分（2／74／74 分） |
| 伺服器分發包 | 71（0） | 66（0） | 2.0 分（0.0 分） | 6.7 分（0.0 分） | 0.1 分（0.0 分） | 276／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 70（14） | 49（7） | 3.0 分（3.0 分） | 17.1 分（15.2 分） | 0.1 分（0.1 分） | 397／291／179 分（53／25／17 分） |
| 每晚完整測試 | 17（0） | 0（0） | 40.7 分（0.0 分） | 57.5 分（0.0 分） | 0.1 分（0.0 分） | 631／612／467 分（0／0／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-27 | 27 | 78 | 4 | 0 | 82 |
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

最近一次：2026-10-27 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 251 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.5（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 16.6（21.8） | 29 | `apps/server/tests/test_api.py` |
| 16.3（21.3） | 25 | `apps/server/tests/test_production_api.py` |
| 14.8（19.4） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 14.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 11.0（14.5） | 20 | `apps/server/tests/test_recorder_api.py` |
| 10.6（14.7） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.7（12.5） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.4（9.4） | 24 | `apps/desktop/tests/test_updates.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-27 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 516 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 73.7（91.0） | 11 | `apps/server/tests/test_portal.py` |
| 39.0（45.1） | 4 | `apps/server/tests/test_replay_flow.py` |
| 33.4（40.7） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 30.9（30.9） | 1 | `apps/server/tests/test_composite_replay_flow.py` |
| 25.1（31.0） | 5 | `apps/server/tests/test_production_flow.py` |
| 24.4（28.7） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 22.0（27.7） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 19.9（19.8） | 18 | `apps/cli/tests/test_serve.py` |
| 14.4（19.6） | 25 | `apps/server/tests/test_production_api.py` |
| 13.9（20.1） | 29 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-27 07:44 America/Los_Angeles（PDT，UTC−07:00），合計 613 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 221.4（230.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 113.1（113.1） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 101.6（129.8） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 96.1（99.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 47.9（45.5） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 22.2（35.0） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.6（4.9） | 2 | `tests\smoke\test_browser.py` |
| 3.4（4.4） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.5（2.7） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-27 08:50 | 桌面端建置 | PR | feat/composite-replay | success | 0.2 分 | 0.0 分 | [#40534963409](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40534963409/attempts/1) |
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
| 10-26 21:49 | CI | 推送 | main | failure | 6.8 分 | 0.0 分 | [#40451749029](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749029/attempts/1) |
| 10-26 21:48 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40451749054](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749054/attempts/1) |
| 10-26 21:48 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40451749025](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749025/attempts/1) |
| 10-26 21:47 | 伺服器分發包 | PR | fix/update-manifest-windows-tests | success | 0.1 分 | 0.0 分 | [#40451694434](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694434/attempts/1) |
| 10-26 21:47 | 一鍵安裝腳本 | PR | fix/update-manifest-windows-tests | success | 0.1 分 | 0.0 分 | [#40451694439](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694439/attempts/1) |
| 10-26 21:47 | CI | PR | fix/update-manifest-windows-tests | failure | 4.7 分 | 0.1 分 | [#40451694384](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694384/attempts/1) |
| 10-26 21:45 | 每晚完整測試 | PR | ci/layered-ci | failure | 53.5 分 | 0.1 分 | [#40451347645](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347645/attempts/1) |
| 10-26 21:44 | CI | 推送 | main | cancelled | 4.2 分 | 0.1 分 | [#40451366029](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451366029/attempts/1) |
| 10-26 21:44 | 桌面端建置 | 推送 | main | success | 0.1 分 | 0.0 分 | [#40451366021](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451366021/attempts/1) |
| 10-26 21:44 | 伺服器分發包 | 推送 | main | success | 2.2 分 | 0.1 分 | [#40451365890](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451365890/attempts/1) |
| 10-26 21:44 | 桌面端建置 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40451347544](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347544/attempts/1) |

