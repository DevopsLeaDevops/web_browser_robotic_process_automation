# CI 運行耗時紀錄

更新：2026-10-22 03:37 America/Los_Angeles（PDT，UTC−07:00）。共 241 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 124（0） | 74（0） | 2.8 分（0.0 分） | 5.2 分（0.0 分） | 0.0 分（0.0 分） | 542／252／0 分（0／0／0 分） |
| 桌面端建置 | 89（0） | 72（0） | 3.9 分（0.0 分） | 4.5 分（0.0 分） | 0.1 分（0.0 分） | 8／257／231 分（0／0／0 分） |
| 一鍵安裝腳本 | 25（0） | 13（0） | 3.2 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 133／90／31 分（0／0／0 分） |
| 每晚完整測試 | 2（0） | 0（0） | 40.0 分（0.0 分） | 40.7 分（0.0 分） | 0.0 分（0.0 分） | 80／80／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 31 | 99 | 84 | 27 | 210 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 03:34 America/Los_Angeles（PDT，UTC−07:00），合計 221 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.3（19.8） | 24 | `apps/server/tests/test_production_api.py` |
| 18.5（19.2） | 21 | `apps/server/tests/test_remote_worker_api.py` |
| 17.6（17.9） | 24 | `apps/server/tests/test_api.py` |
| 14.8（14.6） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.3（14.0） | 17 | `apps/server/tests/test_recorder_api.py` |
| 13.6（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.4（13.6） | 14 | `apps/server/tests/test_workflow_api.py` |
| 12.4（13.2） | 11 | `apps/server/tests/test_gitsync.py` |
| 10.0（10.6） | 12 | `apps/server/tests/test_replay.py` |
| 9.9（8.2） | 14 | `apps/server/tests/test_packs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 03:34 America/Los_Angeles（PDT，UTC−07:00），合計 347 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 44.3（49.1） | 6 | `apps/server/tests/test_portal.py` |
| 32.3（34.0） | 2 | `apps/server/tests/test_replay_flow.py` |
| 29.8（36.9） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 24.6（27.8） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 20.7（19.3） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 19.8（24.3） | 5 | `apps/server/tests/test_production_flow.py` |
| 14.1（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.8（14.1） | 17 | `apps/worker/tests/test_recorder.py` |
| 10.9（15.2） | 24 | `apps/server/tests/test_production_api.py` |
| 9.8（14.6） | 21 | `apps/server/tests/test_remote_worker_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 03:30 America/Los_Angeles（PDT，UTC−07:00），合計 649 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 232.9（239.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 145.6（114.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 107.8（128.5） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 88.7（88.4） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 29.7（34.4） | 6 | `packages\rpa_runner\tests\test_tabs.py` |
| 26.9（26.9） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 10.0（5.2） | 2 | `tests\smoke\test_browser.py` |
| 3.8（3.4） | 1 | `apps\worker\tests\test_worker.py` |
| 3.8（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |

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
| 10-22 03:34 | CI | PR | docs/design-refresh | success | 2.8 分 | 0.0 分 | [#39764123632](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39764123632/attempts/1) |
| 10-22 03:30 | 一鍵安裝腳本 | 推送 | main | success | 2.5 分 | 0.0 分 | [#39763596414](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596414/attempts/1) |
| 10-22 03:30 | 桌面端建置 | 推送 | main | success | 5.1 分 | 0.5 分 | [#39763596489](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596489/attempts/1) |
| 10-22 03:30 | CI | 推送 | main | cancelled | 7.2 分 | 0.4 分 | [#39763596411](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39763596411/attempts/1) |
| 10-22 03:08 | CI | PR | fix/replay-multipage | success | 3.7 分 | 0.0 分 | [#39759862919 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862919/attempts/2) |
| 10-22 03:00 | 一鍵安裝腳本 | PR | fix/replay-multipage | success | 2.9 分 | 0.1 分 | [#39759862962](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862962/attempts/1) |
| 10-22 03:00 | CI | PR | fix/replay-multipage | failure | 5.0 分 | 0.1 分 | [#39759862919](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862919/attempts/1) |
| 10-22 03:00 | 桌面端建置 | PR | fix/replay-multipage | failure | 15.2 分 | 0.0 分 | [#39759862921](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39759862921/attempts/1) |
| 10-22 02:37 | 桌面端建置 | PR | feat/dynamic-values | failure | 15.0 分 | 0.0 分 | [#39754707569 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707569/attempts/2) |
| 10-22 02:21 | 桌面端建置 | PR | feat/dynamic-values | failure | 15.2 分 | 0.1 分 | [#39754707569](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707569/attempts/1) |
| 10-22 02:20 | CI | PR | feat/dynamic-values | success | 3.8 分 | 0.1 分 | [#39754707830](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754707830/attempts/1) |
| 10-22 02:17 | CI | PR | feat/dynamic-values | failure | 3.4 分 | 0.1 分 | [#39754254129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754254129/attempts/1) |
| 10-22 02:17 | 桌面端建置 | PR | feat/dynamic-values | cancelled | 4.1 分 | 0.1 分 | [#39754254168](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39754254168/attempts/1) |
| 10-22 00:52 | 桌面端建置 | PR | feat/dynamic-values | success | 0.1 分 | 0.0 分 | [#39743570456](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743570456/attempts/1) |
| 10-22 00:52 | CI | PR | feat/dynamic-values | success | 1.6 分 | 0.0 分 | [#39743570447](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743570447/attempts/1) |
| 10-22 00:49 | 桌面端建置 | PR | fix/replay-multipage | success | 6.0 分 | 2.1 分 | [#39743135105](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743135105/attempts/1) |
| 10-22 00:49 | CI | PR | fix/replay-multipage | success | 3.8 分 | 0.1 分 | [#39743134927](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743134927/attempts/1) |
| 10-22 00:48 | 一鍵安裝腳本 | PR | fix/replay-multipage | failure | 15.1 分 | 0.0 分 | [#39743135141](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39743135141/attempts/1) |
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

