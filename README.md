# CI 運行耗時紀錄

更新：2026-10-21 08:37 America/Los_Angeles（PDT，UTC−07:00）。共 206 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 107（0） | 64（0） | 2.7 分（0.0 分） | 5.1 分（0.0 分） | 0.0 分（0.0 分） | 449／216／0 分（0／0／0 分） |
| 桌面端建置 | 77（0） | 65（0） | 3.9 分（0.0 分） | 4.3 分（0.0 分） | 0.1 分（0.0 分） | 7／218／209 分（0／0／0 分） |
| 一鍵安裝腳本 | 20（0） | 11（0） | 3.1 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 99／57／26 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 39.3 分（0.0 分） | 39.3 分（0.0 分） | 0.0 分（0.0 分） | 36／39／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-21 | 82 | 222 | 253 | 97 | 573 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-21 08:35 America/Los_Angeles（PDT，UTC−07:00），合計 225 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 20.7（18.0） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 20.0（18.9） | 24 | `apps/server/tests/test_production_api.py` |
| 17.7（16.0） | 25 | `apps/server/tests/test_api.py` |
| 14.9（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.3（12.2） | 17 | `apps/server/tests/test_recorder_api.py` |
| 13.6（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.9（12.6） | 14 | `apps/server/tests/test_workflow_api.py` |
| 11.8（11.9） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.2（8.5） | 9 | `apps/server/tests/test_replay.py` |
| 9.0（8.4） | 14 | `apps/server/tests/test_packs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-21 08:35 America/Los_Angeles（PDT，UTC−07:00），合計 198 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 16.2（15.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.9（15.8） | 24 | `apps/server/tests/test_production_api.py` |
| 15.3（14.7） | 25 | `apps/server/tests/test_api.py` |
| 13.5（14.2） | 17 | `apps/worker/tests/test_recorder.py` |
| 12.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.4（12.5） | 11 | `apps/server/tests/test_gitsync.py` |
| 11.3（11.8） | 14 | `apps/server/tests/test_workflow_api.py` |
| 10.9（11.4） | 17 | `apps/server/tests/test_recorder_api.py` |
| 7.8（7.2） | 8 | `apps/server/tests/test_videos.py` |
| 7.8（8.3） | 9 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-21 08:13 America/Los_Angeles（PDT，UTC−07:00），合計 2181 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 376.6（240.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 240.4（240.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 240.4（240.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 189.7（176.1） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 189.7（176.1） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 187.0（176.1） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 166.2（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 99.7（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 99.7（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 76.9（31.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |

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
| 10-21 08:35 | 桌面端建置 | PR | feat/dynamic-values | success | 0.1 分 | 0.0 分 | [#39627019438](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39627019438/attempts/1) |
| 10-21 08:35 | CI | PR | feat/dynamic-values | success | 1.6 分 | 0.0 分 | [#39627019151](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39627019151/attempts/1) |
| 10-21 08:13 | CI | PR | feat/dynamic-values | success | 3.9 分 | 0.0 分 | [#39622125851 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39622125851/attempts/2) |
| 10-21 08:02 | 桌面端建置 | PR | feat/dynamic-values | success | 4.2 分 | 0.1 分 | [#39622125845](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39622125845/attempts/1) |
| 10-21 08:02 | CI | PR | feat/dynamic-values | failure | 2.9 分 | 0.1 分 | [#39622125851](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39622125851/attempts/1) |
| 10-21 07:57 | CI | PR | feat/dynamic-values | cancelled | 4.4 分 | 0.0 分 | [#39621472371](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39621472371/attempts/1) |
| 10-21 07:57 | 桌面端建置 | PR | feat/dynamic-values | cancelled | 5.1 分 | 0.0 分 | [#39621472309](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39621472309/attempts/1) |
| 10-21 07:40 | 桌面端建置 | PR | m7b/popup | success | 0.2 分 | 0.1 分 | [#39618917896](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39618917896/attempts/1) |
| 10-21 07:40 | CI | PR | m7b/popup | success | 1.4 分 | 0.0 分 | [#39618917908](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39618917908/attempts/1) |
| 10-21 07:34 | CI | PR | m7b/popup | success | 3.9 分 | 0.1 分 | [#39618009102](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39618009102/attempts/1) |
| 10-21 07:34 | 桌面端建置 | PR | m7b/popup | success | 5.3 分 | 0.1 分 | [#39618008972](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39618008972/attempts/1) |
| 10-21 05:59 | 發布 | 推送 | v0.4.0 | success | 5.7 分 | 0.1 分 | [#39604149793](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39604149793/attempts/1) |
| 10-21 05:54 | 桌面端建置 | 推送 | main | success | 4.2 分 | 0.1 分 | [#39603383388](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39603383388/attempts/1) |
| 10-21 05:54 | CI | 推送 | main | success | 6.5 分 | 0.1 分 | [#39603383375](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39603383375/attempts/1) |
| 10-21 05:54 | 一鍵安裝腳本 | 推送 | main | failure | 15.1 分 | 0.0 分 | [#39603383447](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39603383447/attempts/1) |
| 10-21 05:24 | 一鍵安裝腳本 | PR | chore/release-0.4.0 | success | 0.1 分 | 0.0 分 | [#39599379921](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39599379921/attempts/1) |
| 10-21 05:24 | 桌面端建置 | PR | chore/release-0.4.0 | success | 0.1 分 | 0.0 分 | [#39599379731](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39599379731/attempts/1) |
| 10-21 05:24 | CI | PR | chore/release-0.4.0 | success | 1.5 分 | 0.1 分 | [#39599379901](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39599379901/attempts/1) |
| 10-21 05:17 | 一鍵安裝腳本 | PR | chore/release-0.4.0 | success | 3.0 分 | 0.1 分 | [#39598378351](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39598378351/attempts/1) |
| 10-21 05:17 | 桌面端建置 | PR | chore/release-0.4.0 | success | 3.8 分 | 0.0 分 | [#39598378343](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39598378343/attempts/1) |
| 10-21 05:17 | CI | PR | chore/release-0.4.0 | success | 4.3 分 | 0.1 分 | [#39598378356](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39598378356/attempts/1) |
| 10-21 05:13 | CI | 推送 | main | failure | 5.9 分 | 0.0 分 | [#39596592017 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39596592017/attempts/2) |
| 10-21 05:03 | 桌面端建置 | 推送 | main | success | 5.0 分 | 0.2 分 | [#39596592102](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39596592102/attempts/1) |
| 10-21 05:03 | CI | 推送 | main | failure | 6.2 分 | 0.0 分 | [#39596592017](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39596592017/attempts/1) |
| 10-21 04:52 | 桌面端建置 | PR | m12/replay-player | success | 0.1 分 | 0.0 分 | [#39595163375](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39595163375/attempts/1) |
| 10-21 04:52 | CI | PR | m12/replay-player | success | 1.6 分 | 0.1 分 | [#39595163278](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39595163278/attempts/1) |
| 10-21 04:44 | CI | PR | m12/replay-player | success | 2.4 分 | 0.1 分 | [#39594237971](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39594237971/attempts/1) |
| 10-21 04:44 | 桌面端建置 | PR | m12/replay-player | success | 5.2 分 | 0.1 分 | [#39594238217](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39594238217/attempts/1) |
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

