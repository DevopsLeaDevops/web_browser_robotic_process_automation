# CI 運行耗時紀錄

更新：2026-10-25 17:29 America/Los_Angeles（PDT，UTC−07:00）。共 445 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 199（0） | 105（0） | 3.2 分（0.0 分） | 6.6 分（0.0 分） | 0.0 分（0.0 分） | 1057／432／0 分（0／0／0 分） |
| 桌面端建置 | 139（0） | 106（0） | 4.0 分（0.0 分） | 6.5 分（0.0 分） | 0.1 分（0.0 分） | 14／420／544 分（0／0／0 分） |
| 伺服器分發包 | 36（0） | 31（0） | 2.0 分（0.0 分） | 6.7 分（0.0 分） | 0.1 分（0.0 分） | 149／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 60（0） | 35（0） | 3.2 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 393／264／144 分（0／0／0 分） |
| 每晚完整測試 | 8（0） | 0（0） | 47.4 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 396／379／232 分（0／0／0 分） |
| 發布 | 3（0） | 2（0） | 5.9 分（0.0 分） | 6.8 分（0.0 分） | 0.1 分（0.0 分） | 7／13／23 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-25 | 79 | 462 | 294 | 314 | 1069 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-25 17:27 America/Los_Angeles（PDT，UTC−07:00），合計 279 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 20.3（20.2） | 18 | `apps/cli/tests/test_serve.py` |
| 20.3（20.4） | 29 | `apps/server/tests/test_api.py` |
| 20.0（19.6） | 24 | `apps/server/tests/test_production_api.py` |
| 18.9（18.9） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 14.6（14.1） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.6（13.8） | 11 | `apps/server/tests/test_gitsync.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.2（12.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 10.2（10.6） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-25 17:27 America/Los_Angeles（PDT，UTC−07:00），合計 281 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 20.5（15.1） | 29 | `apps/server/tests/test_api.py` |
| 19.8（20.1） | 18 | `apps/cli/tests/test_serve.py` |
| 18.4（14.2） | 24 | `apps/server/tests/test_production_api.py` |
| 17.8（13.5） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.9（12.3） | 11 | `apps/server/tests/test_gitsync.py` |
| 14.0（10.8） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.9（13.8） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.5（10.0） | 14 | `apps/server/tests/test_workflow_api.py` |
| 10.6（7.7） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-25 17:20 America/Los_Angeles（PDT，UTC−07:00），合計 1204 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 226.3（228.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 226.3（228.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 116.7（126.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 116.7（126.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 99.8（103.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 99.8（103.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 85.0（91.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 85.0（91.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.7（40.5） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 38.7（40.5） | 8 | `packages\rpa_runner\tests\test_tabs.py` |

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
| 10-25 17:27 | 一鍵安裝腳本 | PR | chore/release-0.6.0 | success | 0.1 分 | 0.0 分 | [#40249483702](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40249483702/attempts/1) |
| 10-25 17:27 | 桌面端建置 | PR | chore/release-0.6.0 | success | 0.2 分 | 0.0 分 | [#40249483609](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40249483609/attempts/1) |
| 10-25 17:27 | CI | PR | chore/release-0.6.0 | success | 1.8 分 | 0.1 分 | [#40249483576](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40249483576/attempts/1) |
| 10-25 17:20 | CI | PR | chore/release-0.6.0 | success | 3.2 分 | 0.0 分 | [#40248356113 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356113/attempts/2) |
| 10-25 17:20 | 桌面端建置 | PR | chore/release-0.6.0 | success | 6.8 分 | 0.1 分 | [#40248356081 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356081/attempts/2) |
| 10-25 17:14 | 伺服器分發包 | PR | chore/release-0.6.0 | success | 3.9 分 | 0.3 分 | [#40248356036](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356036/attempts/1) |
| 10-25 17:14 | CI | PR | chore/release-0.6.0 | failure | 5.0 分 | 0.0 分 | [#40248356113](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356113/attempts/1) |
| 10-25 17:14 | 桌面端建置 | PR | chore/release-0.6.0 | failure | 5.1 分 | 0.1 分 | [#40248356081](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356081/attempts/1) |
| 10-25 17:14 | 一鍵安裝腳本 | PR | chore/release-0.6.0 | success | 5.4 分 | 0.1 分 | [#40248356169](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40248356169/attempts/1) |
| 10-25 17:08 | 伺服器分發包 | 推送 | main | success | 2.7 分 | 0.8 分 | [#40247858807](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247858807/attempts/1) |
| 10-25 17:08 | 一鍵安裝腳本 | 推送 | main | success | 3.0 分 | 0.1 分 | [#40247858729](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247858729/attempts/1) |
| 10-25 17:08 | 桌面端建置 | 推送 | main | success | 8.6 分 | 1.8 分 | [#40247858811](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247858811/attempts/1) |
| 10-25 17:08 | CI | 推送 | main | failure | 10.8 分 | 0.9 分 | [#40247858783](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247858783/attempts/1) |
| 10-25 17:07 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 1.9 分 | 0.1 分 | [#40247790524](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247790524/attempts/1) |
| 10-25 17:07 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 4.1 分 | 0.1 分 | [#40247790496](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247790496/attempts/1) |
| 10-25 17:07 | CI | PR | claude/project-thread-reisy3 | success | 5.8 分 | 0.0 分 | [#40247790502](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247790502/attempts/1) |
| 10-25 17:07 | 桌面端建置 | PR | claude/project-thread-reisy3 | success | 6.0 分 | 0.1 分 | [#40247790478](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247790478/attempts/1) |
| 10-25 16:58 | CI | 推送 | main | failure | 5.9 分 | 0.1 分 | [#40247055108](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247055108/attempts/1) |
| 10-25 16:56 | CI | PR | claude/project-thread-vql00s | success | 3.2 分 | 0.1 分 | [#40247001912](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40247001912/attempts/1) |
| 10-25 16:54 | 伺服器分發包 | 推送 | main | success | 1.8 分 | 0.1 分 | [#40246850246](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40246850246/attempts/1) |
| 10-25 16:54 | 一鍵安裝腳本 | 推送 | main | success | 3.4 分 | 0.1 分 | [#40246850191](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40246850191/attempts/1) |
| 10-25 16:54 | CI | 推送 | main | cancelled | 4.2 分 | 0.0 分 | [#40246850367](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40246850367/attempts/1) |
| 10-25 16:54 | 桌面端建置 | 推送 | main | success | 6.5 分 | 0.1 分 | [#40246850233](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40246850233/attempts/1) |
| 10-25 14:05 | 一鍵安裝腳本 | 排程 | main | failure | 20.1 分 | 0.0 分 | [#40233823205](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40233823205/attempts/1) |
| 10-25 13:44 | 每晚完整測試 | 排程 | main | failure | 49.8 分 | 0.2 分 | [#40232178229](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40232178229/attempts/1) |
| 10-25 08:25 | 伺服器分發包 | PR | fix/scheduled-test-failures | success | 1.9 分 | 0.1 分 | [#40206824784](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40206824784/attempts/1) |
| 10-25 08:25 | 一鍵安裝腳本 | PR | fix/scheduled-test-failures | success | 2.7 分 | 0.1 分 | [#40206824810](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40206824810/attempts/1) |
| 10-25 08:25 | CI | PR | fix/scheduled-test-failures | failure | 4.3 分 | 0.1 分 | [#40206824809](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40206824809/attempts/1) |
| 10-25 08:25 | 桌面端建置 | PR | fix/scheduled-test-failures | success | 6.5 分 | 0.1 分 | [#40206824808](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40206824808/attempts/1) |
| 10-25 08:25 | 每晚完整測試 | PR | fix/scheduled-test-failures | failure | 47.3 分 | 0.0 分 | [#40206824849](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40206824849/attempts/1) |
| 10-25 07:59 | 伺服器分發包 | PR | claude/project-thread-reisy3 | success | 2.0 分 | 0.1 分 | [#40204782961](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204782961/attempts/1) |
| 10-25 07:59 | 一鍵安裝腳本 | PR | claude/project-thread-reisy3 | success | 2.9 分 | 0.1 分 | [#40204782963](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204782963/attempts/1) |
| 10-25 07:59 | CI | PR | claude/project-thread-reisy3 | success | 4.6 分 | 0.1 分 | [#40204783070](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204783070/attempts/1) |
| 10-25 07:59 | 桌面端建置 | PR | claude/project-thread-reisy3 | success | 6.2 分 | 0.0 分 | [#40204782987](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204782987/attempts/1) |
| 10-25 07:53 | 伺服器分發包 | 推送 | main | success | 1.8 分 | 0.1 分 | [#40204385268](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204385268/attempts/1) |
| 10-25 07:53 | CI | 推送 | main | failure | 6.5 分 | 0.1 分 | [#40204385254](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204385254/attempts/1) |
| 10-25 07:53 | 桌面端建置 | 推送 | main | success | 6.6 分 | 0.0 分 | [#40204385291](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40204385291/attempts/1) |
| 10-25 07:47 | CI | PR | claude/project-thread-iqv8qq | success | 4.5 分 | 0.1 分 | [#40203913307](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40203913307/attempts/1) |
| 10-25 07:47 | 伺服器分發包 | PR | claude/project-thread-iqv8qq | success | 5.4 分 | 0.1 分 | [#40203913314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40203913314/attempts/1) |
| 10-25 07:47 | 桌面端建置 | PR | claude/project-thread-iqv8qq | success | 5.8 分 | 0.1 分 | [#40203913306](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40203913306/attempts/1) |

