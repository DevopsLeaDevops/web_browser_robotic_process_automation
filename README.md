# CI 運行耗時紀錄

更新：2026-10-22 00:51 America/Los_Angeles（PDT，UTC−07:00）。共 223 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 116（0） | 69（0） | 2.8 分（0.0 分） | 5.2 分（0.0 分） | 0.0 分（0.0 分） | 494／230／0 分（0／0／0 分） |
| 桌面端建置 | 82（0） | 69（0） | 3.9 分（0.0 分） | 4.3 分（0.0 分） | 0.1 分（0.0 分） | 8／234／223 分（0／0／0 分） |
| 一鍵安裝腳本 | 22（0） | 11（0） | 3.4 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 122／84／26 分（0／0／0 分） |
| 每晚完整測試 | 2（0） | 0（0） | 40.0 分（0.0 分） | 40.7 分（0.0 分） | 0.0 分（0.0 分） | 80／80／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 13 | 40 | 32 | 14 | 85 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 00:46 America/Los_Angeles（PDT，UTC−07:00），合計 210 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 17.6（17.6） | 24 | `apps/server/tests/test_production_api.py` |
| 17.3（17.3） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 16.4（16.2） | 25 | `apps/server/tests/test_api.py` |
| 14.4（14.3） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.7（12.9） | 19 | `apps/server/tests/test_recorder_api.py` |
| 13.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.7（11.2） | 11 | `apps/server/tests/test_gitsync.py` |
| 10.7（10.7） | 14 | `apps/server/tests/test_workflow_api.py` |
| 8.2（8.2） | 9 | `apps/server/tests/test_replay.py` |
| 7.8（7.3） | 27 | `apps/desktop/tests/test_recorder_app.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 00:46 America/Los_Angeles（PDT，UTC−07:00），合計 435 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 55.0（54.1） | 6 | `apps/server/tests/test_portal.py` |
| 41.7（41.2） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 33.0（31.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 31.1（28.7） | 5 | `apps/server/tests/test_production_flow.py` |
| 21.2（20.3） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 17.5（15.3） | 24 | `apps/server/tests/test_production_api.py` |
| 17.4（16.9） | 1 | `apps/server/tests/test_replay_flow.py` |
| 17.3（14.7） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 16.0（14.0） | 25 | `apps/server/tests/test_api.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 00:46 America/Los_Angeles（PDT，UTC−07:00），合計 603 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 231.0（239.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 129.5（132.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 91.6（91.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 64.5（76.2） | 10 | `packages\rpa_runner\tests\test_video_browser.py` |
| 47.1（33.3） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 28.5（28.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.6（5.2） | 2 | `tests\smoke\test_browser.py` |
| 3.6（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.4（3.0） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-22 00:46 | CI | PR | feat/dynamic-values | success | 3.9 分 | 0.0 分 | [#39742896430](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742896430/attempts/1) |
| 10-22 00:46 | 桌面端建置 | PR | feat/dynamic-values | success | 3.9 分 | 0.1 分 | [#39742896419](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742896419/attempts/1) |
| 10-22 00:45 | 一鍵安裝腳本 | PR | fix/replay-multipage | cancelled | 3.7 分 | 0.0 分 | [#39742681684](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681684/attempts/1) |
| 10-22 00:45 | CI | PR | fix/replay-multipage | cancelled | 4.0 分 | 0.0 分 | [#39742681627](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681627/attempts/1) |
| 10-22 00:45 | 桌面端建置 | PR | fix/replay-multipage | cancelled | 4.1 分 | 1.2 分 | [#39742681591](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39742681591/attempts/1) |
| 10-22 00:30 | 桌面端建置 | 推送 | main | success | 4.1 分 | 0.0 分 | [#39740982055](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39740982055/attempts/1) |
| 10-22 00:30 | CI | 推送 | main | success | 6.7 分 | 0.1 分 | [#39740981965](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39740981965/attempts/1) |
| 10-22 00:17 | 桌面端建置 | PR | feat/dynamic-values | success | 0.1 分 | 0.0 分 | [#39739522001](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39739522001/attempts/1) |
| 10-22 00:17 | CI | PR | feat/dynamic-values | success | 1.6 分 | 0.0 分 | [#39739521546](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39739521546/attempts/1) |
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

