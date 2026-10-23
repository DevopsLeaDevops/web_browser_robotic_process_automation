# CI 運行耗時紀錄

更新：2026-10-23 04:11 America/Los_Angeles（PDT，UTC−07:00）。共 328 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 160（0） | 84（0） | 3.0 分（0.0 分） | 6.5 分（0.0 分） | 0.0 分（0.0 分） | 813／339／0 分（0／0／0 分） |
| 桌面端建置 | 114（0） | 85（0） | 4.0 分（0.0 分） | 5.4 分（0.0 分） | 0.1 分（0.0 分） | 11／326／325 分（0／0／0 分） |
| 伺服器分發包 | 11（0） | 7（0） | 1.9 分（0.0 分） | 10.3 分（0.0 分） | 0.1 分（0.0 分） | 46／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 37（0） | 16（0） | 3.0 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 210／144／45 分（0／0／0 分） |
| 每晚完整測試 | 3（0） | 0（0） | 40.7 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 157／140／0 分（0／0／0 分） |
| 發布 | 3（0） | 2（0） | 5.9 分（0.0 分） | 6.8 分（0.0 分） | 0.1 分（0.0 分） | 7／13／23 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-23 | 6 | 36 | 3 | 9 | 48 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-23 04:08 America/Los_Angeles（PDT，UTC−07:00），合計 381 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 18.7（21.1） | 29 | `apps/server/tests/test_api.py` |
| 18.7（21.1） | 29 | `apps/server/tests/test_api.py` |
| 16.8（20.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 16.8（20.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 16.7（20.8） | 24 | `apps/server/tests/test_production_api.py` |
| 16.7（20.8） | 24 | `apps/server/tests/test_production_api.py` |
| 14.1（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.1（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（13.8） | 14 | `apps/worker/tests/test_gateway.py` |
| 14.0（13.8） | 14 | `apps/worker/tests/test_gateway.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-23 04:08 America/Los_Angeles（PDT，UTC−07:00），合計 1465 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 75.5（75.5） | 8 | `apps/server/tests/test_portal.py` |
| 75.5（75.5） | 8 | `apps/server/tests/test_portal.py` |
| 75.5（75.5） | 8 | `apps/server/tests/test_portal.py` |
| 41.4（41.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 41.4（41.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 41.4（41.5） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 35.3（35.3） | 2 | `apps/server/tests/test_replay_flow.py` |
| 35.3（35.3） | 2 | `apps/server/tests/test_replay_flow.py` |
| 35.3（35.3） | 2 | `apps/server/tests/test_replay_flow.py` |
| 33.1（33.1） | 3 | `apps/server/tests/test_remote_worker_flow.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 23:04 America/Los_Angeles（PDT，UTC−07:00），合計 610 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 220.9（401.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 110.1（187.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 108.8（174.7） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 97.3（155.3） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 41.2（60.3） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 21.5（54.0） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.2（9.0） | 2 | `tests\smoke\test_browser.py` |
| 3.7（5.2） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.6（4.1） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 854 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 87.6（76.2） | 10 | `apps/server/tests/test_portal.py` |
| 82.4（67.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 82.3（74.1） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.6（56.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 55.6（50.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 54.0（44.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 53.0（48.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.9（37.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.9（28.4） | 2 | `apps/server/tests/test_replay_flow.py` |
| 20.0（20.0） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 935 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 103.1（79.7） | 10 | `apps/server/tests/test_portal.py` |
| 94.8（75.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.7（78.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 72.3（59.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 64.4（50.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 62.1（47.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 57.2（47.1） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 50.5（40.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 37.4（26.9） | 2 | `apps/server/tests/test_replay_flow.py` |
| 23.9（19.5） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 727 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 99.1（78.4） | 10 | `apps/server/tests/test_portal.py` |
| 95.7（83.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 90.6（74.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 71.1（59.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 61.8（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 59.4（48.2） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.3（40.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 49.9（38.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 37.2（26.6） | 2 | `apps/server/tests/test_replay_flow.py` |
| 23.0（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 716 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 100.5（79.1） | 10 | `apps/server/tests/test_portal.py` |
| 95.3（75.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.3（78.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 71.1（59.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 62.1（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 60.9（49.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 50.4（41.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 49.8（38.3） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 24.8（20.1） | 2 | `apps/server/tests/test_replay_flow.py` |
| 23.0（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 1417 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 144.9（126.3） | 10 | `apps\server\tests\test_portal.py` |
| 136.0（115.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 131.6（91.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 130.2（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.8（66.1） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 90.7（86.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 70.8（57.6） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 63.1（55.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 52.1（40.7） | 11 | `apps\server\tests\test_gitsync.py` |
| 39.7（28.7） | 2 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 1136 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 192.4（122.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 146.0（112.5） | 10 | `apps\server\tests\test_portal.py` |
| 122.8（103.6） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 105.6（47.7） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 98.9（75.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 84.0（78.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 79.4（67.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 68.0（47.6） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 67.4（59.5） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.9（28.2） | 2 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-22 13:49 America/Los_Angeles（PDT，UTC−07:00），合計 973 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 158.3（112.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 136.6（105.4） | 10 | `apps\server\tests\test_portal.py` |
| 121.8（121.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 96.4（74.0） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 80.4（76.9） | 9 | `apps\server\tests\test_production_flow.py` |
| 69.8（65.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 63.9（56.9） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 57.0（47.6） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 39.2（27.9） | 2 | `apps\server\tests\test_replay_flow.py` |
| 34.6（30.6） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-23 04:08 | CI | PR | claude/project-thread-u3rhl1 | success | 2.7 分 | 0.0 分 | [#39943337519 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337519/attempts/2) |
| 10-23 04:02 | CI | PR | claude/project-thread-u3rhl1 | failure | 3.5 分 | 0.0 分 | [#39943337519](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337519/attempts/1) |
| 10-23 04:02 | 伺服器分發包 | PR | claude/project-thread-u3rhl1 | success | 3.9 分 | 0.1 分 | [#39943337503](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337503/attempts/1) |
| 10-23 04:02 | 桌面端建置 | PR | claude/project-thread-u3rhl1 | success | 6.5 分 | 0.1 分 | [#39943337488](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39943337488/attempts/1) |
| 10-23 03:34 | CI | PR | claude/project-thread-ab62tv | success | 9.7 分 | 0.1 分 | [#39940096023](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39940096023/attempts/1) |
| 10-23 03:29 | CI | 推送 | main | failure | 6.6 分 | 0.0 分 | [#39939492994](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39939492994/attempts/1) |
| 10-22 23:40 | CI | PR | claude/project-thread-ab62tv | success | 4.4 分 | 0.1 分 | [#39912807129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39912807129/attempts/1) |
| 10-22 23:37 | CI | PR | claude/project-thread-ab62tv | cancelled | 2.9 分 | 0.1 分 | [#39912660139](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39912660139/attempts/1) |
| 10-22 23:19 | 發布 | 推送 | v0.5.0 | success | 6.8 分 | 0.1 分 | [#39900384051 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39900384051/attempts/2) |
| 10-22 23:04 | 伺服器分發包 | 推送 | main | success | 2.2 分 | 0.1 分 | [#39909285109](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39909285109/attempts/1) |
| 10-22 23:04 | 一鍵安裝腳本 | 推送 | main | success | 3.1 分 | 0.0 分 | [#39909284974](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39909284974/attempts/1) |
| 10-22 23:04 | 桌面端建置 | 推送 | main | success | 5.4 分 | 0.1 分 | [#39909285041](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39909285041/attempts/1) |
| 10-22 23:04 | CI | 推送 | main | failure | 16.5 分 | 0.0 分 | [#39909285016](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39909285016/attempts/1) |
| 10-22 21:49 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | failure | 1.1 分 | 0.1 分 | [#39901713199 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713199/attempts/2) |
| 10-22 21:49 | CI | PR | claude/project-thread-ab62tv | failure | 6.2 分 | 0.0 分 | [#39901713098 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713098/attempts/2) |
| 10-22 21:42 | 桌面端建置 | PR | claude/project-thread-ab62tv | failure | 5.9 分 | 0.1 分 | [#39901713170](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713170/attempts/1) |
| 10-22 21:42 | CI | PR | claude/project-thread-ab62tv | failure | 5.3 分 | 0.1 分 | [#39901713098](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713098/attempts/1) |
| 10-22 21:42 | 伺服器分發包 | PR | claude/project-thread-ab62tv | failure | 1.7 分 | 0.1 分 | [#39901713182](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713182/attempts/1) |
| 10-22 21:42 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | failure | 2.5 分 | 0.1 分 | [#39901713199](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901713199/attempts/1) |
| 10-22 21:38 | 伺服器分發包 | PR | claude/project-thread-ab62tv | failure | 2.0 分 | 0.1 分 | [#39901408812](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901408812/attempts/1) |
| 10-22 21:38 | CI | PR | claude/project-thread-ab62tv | cancelled | 3.9 分 | 0.1 分 | [#39901408789](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901408789/attempts/1) |
| 10-22 21:38 | 桌面端建置 | PR | claude/project-thread-ab62tv | cancelled | 4.3 分 | 0.1 分 | [#39901408843](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39901408843/attempts/1) |
| 10-22 21:27 | 發布 | 推送 | v0.5.0 | failure | 5.9 分 | 0.1 分 | [#39900384051](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39900384051/attempts/1) |
| 10-22 21:00 | 伺服器分發包 | 推送 | main | failure | 1.9 分 | 0.1 分 | [#39898016309](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39898016309/attempts/1) |
| 10-22 21:00 | 一鍵安裝腳本 | 推送 | main | failure | 2.8 分 | 0.0 分 | [#39898016283](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39898016283/attempts/1) |
| 10-22 21:00 | 桌面端建置 | 推送 | main | failure | 4.9 分 | 0.0 分 | [#39898016447](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39898016447/attempts/1) |
| 10-22 21:00 | CI | 推送 | main | failure | 9.5 分 | 0.0 分 | [#39898016316](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39898016316/attempts/1) |
| 10-22 14:13 | 一鍵安裝腳本 | 排程 | main | failure | 31.1 分 | 0.1 分 | [#39855480410](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39855480410/attempts/1) |
| 10-22 13:49 | 每晚完整測試 | 排程 | main | failure | 60.2 分 | 0.0 分 | [#39852131374](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39852131374/attempts/1) |
| 10-22 08:19 | CI | PR | claude/project-thread-ab62tv | failure | 9.1 分 | 0.0 分 | [#39803693629](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803693629/attempts/1) |
| 10-22 08:19 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | failure | 15.2 分 | 0.1 分 | [#39803693675](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803693675/attempts/1) |
| 10-22 08:19 | 伺服器分發包 | PR | claude/project-thread-ab62tv | success | 10.9 分 | 0.1 分 | [#39803693753](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803693753/attempts/1) |
| 10-22 08:19 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 5.2 分 | 0.1 分 | [#39803693808](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803693808/attempts/1) |
| 10-22 08:18 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 0.2 分 | 0.0 分 | [#39803664821](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803664821/attempts/1) |
| 10-22 08:18 | CI | PR | claude/project-thread-ab62tv | cancelled | 0.7 分 | 0.0 分 | [#39803664824](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39803664824/attempts/1) |
| 10-22 08:18 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | cancelled | 1.0 分 | 0.0 分 | [#39800058860 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058860/attempts/2) |
| 10-22 08:10 | CI | PR | claude/project-thread-ab62tv | failure | 6.9 分 | 0.1 分 | [#39800058876 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058876/attempts/2) |
| 10-22 07:57 | CI | PR | claude/project-thread-ab62tv | failure | 3.6 分 | 0.0 分 | [#39800058876](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058876/attempts/1) |
| 10-22 07:57 | 伺服器分發包 | PR | claude/project-thread-ab62tv | success | 1.8 分 | 0.1 分 | [#39800059052](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800059052/attempts/1) |
| 10-22 07:57 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 5.2 分 | 0.1 分 | [#39800058923](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058923/attempts/1) |

