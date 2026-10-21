# CI 運行耗時紀錄

更新：2026-10-21 04:47 America/Los_Angeles（PDT，UTC−07:00）。共 179 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 95（0） | 56（0） | 2.6 分（0.0 分） | 4.9 分（0.0 分） | 0.0 分（0.0 分） | 387／196／0 分（0／0／0 分） |
| 桌面端建置 | 66（0） | 55（0） | 3.9 分（0.0 分） | 4.2 分（0.0 分） | 0.1 分（0.0 分） | 6／187／183 分（0／0／0 分） |
| 一鍵安裝腳本 | 17（0） | 9（0） | 3.2 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 90／52／23 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 39.3 分（0.0 分） | 39.3 分（0.0 分） | 0.0 分（0.0 分） | 36／39／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-21 | 55 | 150 | 192 | 65 | 407 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-21 04:44 America/Los_Angeles（PDT，UTC−07:00），合計 214 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 18.7（16.9） | 24 | `apps/server/tests/test_production_api.py` |
| 18.2（16.1） | 21 | `apps/server/tests/test_remote_worker_api.py` |
| 16.0（14.6） | 24 | `apps/server/tests/test_api.py` |
| 14.5（14.2） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.4（12.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 13.1（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.3（11.6） | 17 | `apps/server/tests/test_recorder_api.py` |
| 11.5（11.2） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.6（9.6） | 9 | `apps/server/tests/test_replay.py` |
| 8.2（8.2） | 14 | `apps/server/tests/test_packs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-21 04:44 America/Los_Angeles（PDT，UTC−07:00），合計 326 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 43.7（47.5） | 6 | `apps/server/tests/test_portal.py` |
| 30.4（32.4） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 23.5（26.4） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 19.3（23.2） | 5 | `apps/server/tests/test_production_flow.py` |
| 17.7（18.4） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 14.3（14.3） | 1 | `apps/server/tests/test_replay_flow.py` |
| 14.0（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 11.5（11.6） | 11 | `apps/server/tests/test_gitsync.py` |
| 10.5（11.1） | 2 | `apps/server/tests/test_flow.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-21 04:39 America/Los_Angeles（PDT，UTC−07:00），合計 595 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 240.7（249.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 145.0（136.6） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 94.3（93.2） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 72.2（72.6） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 29.7（26.6） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.1（6.0） | 2 | `tests\smoke\test_browser.py` |
| 4.4（5.0） | 1 | `apps\desktop\tests\test_selftest.py` |
| 3.0（3.4） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 536 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 65.2（65.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 63.4（63.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 62.4（62.4） | 9 | `apps/server/tests/test_portal.py` |
| 42.7（42.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.5（42.5） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 38.8（38.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.3（37.3） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 16.3（16.3） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 14.1（14.1） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（14.0） | 14 | `apps/worker/tests/test_gateway.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 602 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.2（78.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 77.4（77.4） | 9 | `apps/server/tests/test_portal.py` |
| 71.6（71.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 50.4（50.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.1（47.1） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 47.0（47.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.0（40.0） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.5（19.5） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 14.0（14.0） | 14 | `apps/worker/tests/test_gateway.py` |
| 14.0（14.0） | 24 | `apps/server/tests/test_production_api.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 459 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 83.8（83.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 77.4（77.4） | 9 | `apps/server/tests/test_portal.py` |
| 70.6（70.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 49.0（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 45.5（45.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.9（40.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 38.9（38.9） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.7（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 13.4（13.4） | 1 | `packages/rpa_runner/tests/test_profiles.py` |
| 13.3（13.3） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 450 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.7（78.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 76.7（76.7） | 9 | `apps/server/tests/test_portal.py` |
| 68.4（68.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 48.8（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 45.5（45.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.0（41.0） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 38.3（38.3） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.7（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 13.4（13.4） | 3 | `apps/server/tests/test_flow.py` |
| 13.2（13.2） | 1 | `packages/rpa_runner/tests/test_profiles.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 934 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 126.3（126.3） | 9 | `apps\server\tests\test_portal.py` |
| 115.2（115.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.4（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 86.1（86.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.2（65.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.6（57.6） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 55.8（55.8） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 32.2（32.2） | 3 | `apps\server\tests\test_flow.py` |
| 26.9（26.9） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 25.4（25.4） | 20 | `apps\server\tests\test_remote_worker_api.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 669 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 122.2（122.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 112.5（112.5） | 9 | `apps\server\tests\test_portal.py` |
| 103.6（103.6） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 78.8（78.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 67.4（67.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 59.5（59.5） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 47.7（47.7） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 29.0（29.0） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 22.4（22.4） | 3 | `apps\server\tests\test_flow.py` |
| 16.1（16.1） | 1 | `packages\rpa_runner\tests\test_profiles.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 669 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 125.4（125.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 112.7（112.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 105.4（105.4） | 9 | `apps\server\tests\test_portal.py` |
| 76.9（76.9） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.2（65.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.9（56.9） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 47.6（47.6） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 24.7（24.7） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 23.5（23.5） | 3 | `apps\server\tests\test_flow.py` |
| 21.2（21.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-21 04:44 | CI | PR | m12/replay-player | success | 2.4 分 | 0.1 分 | [#39594237971](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39594237971/attempts/1) |
| 10-21 04:39 | 桌面端建置 | 推送 | main | success | 4.0 分 | 0.1 分 | [#39593545046](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39593545046/attempts/1) |
| 10-21 04:39 | CI | 推送 | main | failure | 4.6 分 | 0.1 分 | [#39593545119](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39593545119/attempts/1) |
| 10-21 04:32 | 桌面端建置 | PR | m12/replay | success | 0.1 分 | 0.0 分 | [#39592726238](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39592726238/attempts/1) |
| 10-21 04:32 | CI | PR | m12/replay | success | 1.5 分 | 0.0 分 | [#39592726249](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39592726249/attempts/1) |
| 10-21 04:26 | CI | PR | m12/replay | success | 3.6 分 | 0.0 分 | [#39592002765](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39592002765/attempts/1) |
| 10-21 04:26 | 桌面端建置 | PR | m12/replay | success | 4.5 分 | 0.0 分 | [#39592002925](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39592002925/attempts/1) |
| 10-21 04:12 | CI | 推送 | main | success | 4.2 分 | 0.0 分 | [#39590230335](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39590230335/attempts/1) |
| 10-21 04:12 | 桌面端建置 | 推送 | main | success | 4.5 分 | 0.0 分 | [#39590230272](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39590230272/attempts/1) |
| 10-21 04:09 | 桌面端建置 | PR | m12/replay | success | 0.1 分 | 0.0 分 | [#39589838405](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39589838405/attempts/1) |
| 10-21 04:09 | CI | PR | m12/replay | success | 1.1 分 | 0.0 分 | [#39589837910](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39589837910/attempts/1) |
| 10-21 03:37 | 桌面端建置 | PR | m7a/iframe | success | 0.1 分 | 0.0 分 | [#39585987704](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39585987704/attempts/1) |
| 10-21 03:37 | CI | PR | m7a/iframe | success | 1.5 分 | 0.0 分 | [#39585987856](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39585987856/attempts/1) |
| 10-21 03:32 | CI | PR | m7a/iframe | success | 2.7 分 | 0.1 分 | [#39585381579](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39585381579/attempts/1) |
| 10-21 03:32 | 桌面端建置 | PR | m7a/iframe | success | 4.0 分 | 0.0 分 | [#39585381755](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39585381755/attempts/1) |
| 10-21 03:30 | CI | PR | m12/replay | success | 2.3 分 | 0.0 分 | [#39584324700 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39584324700/attempts/2) |
| 10-21 03:25 | CI | PR | m12/replay-player | success | 2.8 分 | 0.1 分 | [#39584452017](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39584452017/attempts/1) |
| 10-21 03:25 | 桌面端建置 | PR | m12/replay-player | success | 4.3 分 | 0.1 分 | [#39584451946](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39584451946/attempts/1) |
| 10-21 03:24 | CI | PR | m12/replay | failure | 3.5 分 | 0.1 分 | [#39584324700](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39584324700/attempts/1) |
| 10-21 03:24 | 桌面端建置 | PR | m12/replay | success | 4.3 分 | 0.1 分 | [#39584324741](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39584324741/attempts/1) |
| 10-21 03:21 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 1.7 分 | 0.0 分 | [#39583944184](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39583944184/attempts/1) |
| 10-21 03:19 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 1.7 分 | 0.1 分 | [#39583689575](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39583689575/attempts/1) |
| 10-21 03:13 | CI | PR | m12/replay | failure | 2.9 分 | 0.0 分 | [#39583026691](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39583026691/attempts/1) |
| 10-21 03:13 | 桌面端建置 | PR | m12/replay | success | 3.8 分 | 0.1 分 | [#39583026727](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39583026727/attempts/1) |
| 10-21 02:58 | CI | PR | m12/replay | success | 3.2 分 | 0.1 分 | [#39580097031 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580097031/attempts/2) |
| 10-21 02:53 | 桌面端建置 | PR | m12/replay-player | success | 3.9 分 | 0.1 分 | [#39580459327](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580459327/attempts/1) |
| 10-21 02:53 | CI | PR | m12/replay-player | success | 3.0 分 | 0.0 分 | [#39580458452](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580458452/attempts/1) |
| 10-21 02:52 | CI | 推送 | main | success | 4.1 分 | 0.1 分 | [#39580322256](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580322256/attempts/1) |
| 10-21 02:52 | 一鍵安裝腳本 | 推送 | main | success | 11.6 分 | 0.1 分 | [#39580322455](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580322455/attempts/1) |
| 10-21 02:50 | 桌面端建置 | PR | m12/replay | success | 3.9 分 | 0.1 分 | [#39580097038](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580097038/attempts/1) |
| 10-21 02:50 | CI | PR | m12/replay | success | 7.1 分 | 0.0 分 | [#39580097031](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39580097031/attempts/1) |
| 10-21 02:46 | CI | PR | fix/browser-download-speed | success | 2.6 分 | 0.0 分 | [#39579549013](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579549013/attempts/1) |
| 10-21 02:46 | 一鍵安裝腳本 | PR | fix/browser-download-speed | success | 4.6 分 | 0.2 分 | [#39579548948](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579548948/attempts/1) |
| 10-21 02:46 | 桌面端建置 | PR | m7a/iframe | success | 3.9 分 | 0.1 分 | [#39579516242](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579516242/attempts/1) |
| 10-21 02:46 | CI | PR | m7a/iframe | success | 3.2 分 | 0.0 分 | [#39579516190](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579516190/attempts/1) |
| 10-21 02:42 | CI | PR | m7a/iframe | failure | 3.4 分 | 0.0 分 | [#39579013022](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579013022/attempts/1) |
| 10-21 02:42 | 桌面端建置 | PR | m7a/iframe | cancelled | 4.1 分 | 0.1 分 | [#39579012899](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39579012899/attempts/1) |
| 10-21 02:38 | CI | PR | m12/replay | failure | 3.7 分 | 0.1 分 | [#39578539164](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39578539164/attempts/1) |
| 10-21 02:38 | 桌面端建置 | PR | m12/replay | success | 4.2 分 | 0.1 分 | [#39578539210](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39578539210/attempts/1) |
| 10-21 02:32 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 3.4 分 | 0.1 分 | [#39577768353](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39577768353/attempts/1) |

