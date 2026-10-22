# CI 運行耗時紀錄

更新：2026-10-22 00:16 America/Los_Angeles（PDT，UTC−07:00）。共 214 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 112（0） | 66（0） | 2.7 分（0.0 分） | 5.1 分（0.0 分） | 0.0 分（0.0 分） | 471／219／0 分（0／0／0 分） |
| 桌面端建置 | 78（0） | 66（0） | 3.9 分（0.0 分） | 4.3 分（0.0 分） | 0.1 分（0.0 分） | 7／222／212 分（0／0／0 分） |
| 一鍵安裝腳本 | 21（0） | 11（0） | 3.2 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 119／82／26 分（0／0／0 分） |
| 每晚完整測試 | 2（0） | 0（0） | 40.0 分（0.0 分） | 40.7 分（0.0 分） | 0.0 分（0.0 分） | 80／80／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 4 | 13 | 7 | 4 | 23 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 00:12 America/Los_Angeles（PDT，UTC−07:00），合計 180 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 16.0（15.8） | 25 | `apps/server/tests/test_api.py` |
| 15.9（17.0） | 24 | `apps/server/tests/test_production_api.py` |
| 15.6（18.0） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 13.9（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 10.5（11.5） | 11 | `apps/server/tests/test_gitsync.py` |
| 8.5（12.1） | 17 | `apps/server/tests/test_recorder_api.py` |
| 8.3（10.9） | 14 | `apps/server/tests/test_workflow_api.py` |
| 7.9（7.2） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 6.4（6.5） | 12 | `apps/worker/tests/test_remote.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 00:12 America/Los_Angeles（PDT，UTC−07:00），合計 327 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 40.9（54.8） | 6 | `apps/server/tests/test_portal.py` |
| 28.8（41.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 22.7（33.3） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 20.4（30.0） | 5 | `apps/server/tests/test_production_flow.py` |
| 17.1（19.8） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 15.3（16.9） | 1 | `apps/server/tests/test_replay_flow.py` |
| 14.2（13.3） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.9（14.2） | 17 | `apps/worker/tests/test_recorder.py` |
| 10.8（15.7） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 10.6（15.6） | 24 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 00:12 America/Los_Angeles（PDT，UTC−07:00），合計 497 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 190.0（240.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 119.4（176.1） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 87.6（99.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 61.2（72.2） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 28.2（31.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.2（6.1） | 2 | `tests\smoke\test_browser.py` |
| 3.4（4.4） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.2（3.0） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 717 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 76.2（69.3） | 9 | `apps/server/tests/test_portal.py` |
| 74.1（68.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.1（66.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 50.3（46.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.2（43.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.6（45.6） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 44.7（43.6） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 37.3（37.3） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.2（15.3） | 21 | `apps/server/tests/test_remote_worker_api.py` |
| 18.4（17.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 716 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.7（78.6） | 9 | `apps/server/tests/test_portal.py` |
| 75.2（73.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.3（76.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.1（49.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.6（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.1（47.1） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 45.0（46.0） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 39.7（39.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.1（19.3） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.8（16.8） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 530 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.4（77.9） | 9 | `apps/server/tests/test_portal.py` |
| 74.2（72.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.1（78.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 48.3（48.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 48.2（46.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.0（47.0） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 38.9（39.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 37.3（38.1） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 17.0（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.7（16.7） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 536 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 79.1（77.9） | 9 | `apps/server/tests/test_portal.py` |
| 75.6（72.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.1（75.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 49.8（47.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.9（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.2（47.2） | 10 | `packages/rpa_runner/tests/test_video_browser.py` |
| 39.7（40.4） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 37.1（37.7） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.1（19.4） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 16.7（16.7） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1007 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.7（110.5） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.1（99.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 97.3（111.8） | 9 | `apps\server\tests\test_portal.py` |
| 68.6（77.3） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.1（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.1（56.9） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 51.4（51.4） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 51.2（53.5） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 37.7（37.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 29.3（29.3） | 11 | `apps\server\tests\test_gitsync.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 683 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.9（114.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 96.6（104.5） | 9 | `apps\server\tests\test_portal.py` |
| 93.5（98.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 66.0（72.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 61.4（64.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 52.2（52.2） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 50.3（54.9） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 44.4（46.0） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 27.2（27.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 22.7（25.9） | 4 | `apps\server\tests\test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-21 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 664 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 100.5（113.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 92.7（102.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 92.3（98.8） | 9 | `apps\server\tests\test_portal.py` |
| 64.2（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 60.5（62.9） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 51.5（51.5） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 49.1（53.0） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 43.1（45.4） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 26.5（26.5） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 22.7（23.7） | 4 | `apps\server\tests\test_recorder_flow.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-22 00:12 | CI | PR | feat/dynamic-values | success | 3.0 分 | 0.0 分 | [#39738902629](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39738902629/attempts/1) |
| 10-22 00:12 | 桌面端建置 | PR | feat/dynamic-values | success | 4.0 分 | 0.1 分 | [#39738902647](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39738902647/attempts/1) |
| 10-22 00:07 | CI | PR | docs/design-refresh | success | 2.8 分 | 0.0 分 | [#39738322317](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39738322317/attempts/1) |
| 10-22 00:02 | CI | PR | docs/design-refresh | failure | 3.0 分 | 0.1 分 | [#39737654796](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39737654796/attempts/1) |
| 10-21 23:59 | CI | PR | docs/design-refresh | cancelled | 2.9 分 | 0.0 分 | [#39737415423](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39737415423/attempts/1) |
| 10-21 23:54 | CI | PR | docs/design-refresh | failure | 3.2 分 | 0.1 分 | [#39736865604](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39736865604/attempts/1) |
| 10-21 14:11 | 一鍵安裝腳本 | 排程 | main | failure | 20.2 分 | 0.1 分 | [#39676733530](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39676733530/attempts/1) |
| 10-21 13:50 | 每晚完整測試 | 排程 | main | failure | 40.7 分 | 0.0 分 | [#39673814013](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39673814013/attempts/1) |
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

