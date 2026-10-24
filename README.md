# CI 運行耗時紀錄

更新：2026-10-23 19:51 America/Los_Angeles（PDT，UTC−07:00）。共 355 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 168（0） | 89（0） | 3.0 分（0.0 分） | 6.6 分（0.0 分） | 0.0 分（0.0 分） | 878／356／0 分（0／0／0 分） |
| 桌面端建置 | 119（0） | 89（0） | 4.0 分（0.0 分） | 6.0 分（0.0 分） | 0.1 分（0.0 分） | 12／346／364 分（0／0／0 分） |
| 伺服器分發包 | 18（0） | 14（0） | 1.9 分（0.0 分） | 7.5 分（0.0 分） | 0.1 分（0.0 分） | 70／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 43（0） | 20（0） | 3.0 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 246／179／51 分（0／0／0 分） |
| 每晚完整測試 | 4（0） | 0（0） | 50.5 分（0.0 分） | 66.2 分（0.0 分） | 0.0 分（0.0 分） | 200／188／61 分（0／0／0 分） |
| 發布 | 3（0） | 2（0） | 5.9 分（0.0 分） | 6.8 分（0.0 分） | 0.1 分（0.0 分） | 7／13／23 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-23 19:49 America/Los_Angeles（PDT，UTC−07:00），合計 210 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 16.6（24.1） | 29 | `apps/server/tests/test_api.py` |
| 16.3（22.6） | 24 | `apps/server/tests/test_production_api.py` |
| 15.3（22.2） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 14.2（14.4） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.5（17.0） | 20 | `apps/server/tests/test_recorder_api.py` |
| 12.6（12.5） | 17 | `apps/cli/tests/test_serve.py` |
| 9.7（14.1） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.2（13.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 7.9（11.0） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-23 19:49 America/Los_Angeles（PDT，UTC−07:00），合計 229 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 17.9（21.0） | 29 | `apps/server/tests/test_api.py` |
| 16.8（20.1） | 24 | `apps/server/tests/test_production_api.py` |
| 16.2（19.2） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 14.5（14.9） | 20 | `apps/server/tests/test_recorder_api.py` |
| 14.2（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.0（12.2） | 17 | `apps/cli/tests/test_serve.py` |
| 11.3（12.9） | 11 | `apps/server/tests/test_gitsync.py` |
| 9.7（9.4） | 9 | `apps/server/tests/test_videos.py` |
| 9.3（12.5） | 14 | `apps/server/tests/test_workflow_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-23 18:47 America/Los_Angeles（PDT，UTC−07:00），合計 840 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 308.8（308.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 193.6（171.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 119.7（122.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 117.8（117.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 48.6（49.0） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 36.3（32.7） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.7（4.7） | 1 | `apps\desktop\tests\test_selftest.py` |
| 5.5（8.0） | 2 | `tests\smoke\test_browser.py` |
| 4.0（3.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1177 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 125.5（125.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 116.2（116.2） | 10 | `apps/server/tests/test_portal.py` |
| 111.0（111.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 109.4（109.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 106.5（106.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 77.2（77.2） | 17 | `apps/cli/tests/test_serve.py` |
| 68.8（68.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 58.2（58.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 53.3（53.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.5（39.5） | 2 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1352 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 244.8（244.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 217.4（217.4） | 10 | `apps/server/tests/test_portal.py` |
| 147.6（147.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 132.0（132.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 129.8（129.8） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 97.0（97.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 71.1（71.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 69.7（69.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.9（52.9） | 8 | `packages/rpa_runner/tests/test_tabs.py` |
| 46.6（46.6） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1061 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 150.0（150.0） | 10 | `apps/server/tests/test_portal.py` |
| 129.4（129.4） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 128.4（128.4） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 123.5（123.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 95.9（95.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 74.9（74.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 71.8（71.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 61.0（61.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 54.8（54.8） | 8 | `packages/rpa_runner/tests/test_tabs.py` |
| 54.2（54.2） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 642 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 63.9（70.0） | 10 | `apps/server/tests/test_portal.py` |
| 59.5（59.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 58.5（68.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 55.6（66.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 45.0（44.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 37.6（43.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.6（46.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 35.3（37.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 31.2（31.2） | 2 | `apps/server/tests/test_replay_flow.py` |
| 16.7（17.5） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 711 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 72.8（78.6） | 10 | `apps/server/tests/test_portal.py` |
| 65.8（73.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 63.8（76.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 62.4（62.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 47.9（47.5） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 43.1（49.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.0（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 38.5（39.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.8（32.8） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.0（19.3） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 531 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 69.8（77.9） | 10 | `apps/server/tests/test_portal.py` |
| 65.6（72.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 63.2（78.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 61.6（61.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 42.3（46.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 42.0（48.6） | 9 | `apps/server/tests/test_production_flow.py` |
| 39.2（39.0） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 37.9（39.9） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.7（32.7） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.0（18.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 534 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 69.9（77.9） | 10 | `apps/server/tests/test_portal.py` |
| 65.8（75.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 64.5（72.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 61.7（61.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 42.5（47.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 42.5（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 39.2（38.8） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 38.3（40.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 33.3（24.8） | 2 | `apps/server/tests/test_replay_flow.py` |
| 17.2（19.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 1167 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.4（115.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 102.8（101.1） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 94.3（111.8） | 10 | `apps\server\tests\test_portal.py` |
| 93.7（93.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 74.8（80.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 67.2（62.4） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 67.0（66.5） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.4（56.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 54.5（52.1） | 11 | `apps\server\tests\test_gitsync.py` |
| 39.7（31.0） | 3 | `apps\server\tests\test_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 817 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 108.4（110.5） | 10 | `apps\server\tests\test_portal.py` |
| 108.3（115.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 100.1（101.8） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.5（90.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 73.8（76.3） | 9 | `apps\server\tests\test_production_flow.py` |
| 64.0（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.0（57.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 53.2（50.5） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 37.0（37.0） | 2 | `apps\server\tests\test_replay_flow.py` |
| 27.6（27.6） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-23 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 816 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.8（115.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 105.3（105.3） | 10 | `apps\server\tests\test_portal.py` |
| 101.1（106.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.4（90.4） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 70.6（73.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 66.2（65.7） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.4（56.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 52.0（49.8） | 10 | `packages\rpa_runner\tests\test_debug.py` |
| 42.2（39.2） | 2 | `apps\server\tests\test_replay_flow.py` |
| 27.4（27.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-23 19:49 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40055791415](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791415/attempts/1) |
| 10-23 19:49 | CI | PR | claude/project-thread-fr1onb | success | 1.6 分 | 0.0 分 | [#40055791311](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791311/attempts/1) |
| 10-23 19:49 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40055791314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40055791314/attempts/1) |
| 10-23 19:06 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 0.1 分 | 0.0 分 | [#40052798345](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798345/attempts/1) |
| 10-23 19:06 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 0.2 分 | 0.0 分 | [#40052798310](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798310/attempts/1) |
| 10-23 19:06 | CI | PR | claude/project-thread-fr1onb | success | 1.9 分 | 0.1 分 | [#40052798341](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40052798341/attempts/1) |
| 10-23 18:47 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 1.9 分 | 0.1 分 | [#40051380469](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380469/attempts/1) |
| 10-23 18:47 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 3.3 分 | 0.1 分 | [#40051380395](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380395/attempts/1) |
| 10-23 18:47 | CI | PR | claude/project-thread-fr1onb | success | 5.0 分 | 0.0 分 | [#40051380526](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380526/attempts/1) |
| 10-23 18:47 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.3 分 | 0.1 分 | [#40051380418](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40051380418/attempts/1) |
| 10-23 18:35 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 1.7 分 | 0.1 分 | [#40050479134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479134/attempts/1) |
| 10-23 18:35 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | success | 2.7 分 | 0.0 分 | [#40050479154](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479154/attempts/1) |
| 10-23 18:35 | CI | PR | claude/project-thread-fr1onb | success | 4.3 分 | 0.0 分 | [#40050479167](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479167/attempts/1) |
| 10-23 18:35 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.5 分 | 0.1 分 | [#40050479096](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40050479096/attempts/1) |
| 10-23 18:11 | 伺服器分發包 | 推送 | main | success | 3.5 分 | 0.1 分 | [#40048678122](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048678122/attempts/1) |
| 10-23 18:11 | 桌面端建置 | 推送 | main | success | 6.3 分 | 0.1 分 | [#40048678072](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048678072/attempts/1) |
| 10-23 18:11 | CI | 推送 | main | failure | 6.6 分 | 0.0 分 | [#40048677994](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40048677994/attempts/1) |
| 10-23 14:11 | 一鍵安裝腳本 | 排程 | main | failure | 21.9 分 | 0.1 分 | [#40024981126](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40024981126/attempts/1) |
| 10-23 13:50 | 每晚完整測試 | 排程 | main | failure | 66.2 分 | 5.0 分 | [#40022244500](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40022244500/attempts/1) |
| 10-23 09:11 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 2.4 分 | 0.1 分 | [#39984702407](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702407/attempts/1) |
| 10-23 09:11 | CI | PR | claude/project-thread-fr1onb | failure | 4.6 分 | 0.1 分 | [#39984702558](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702558/attempts/1) |
| 10-23 09:11 | 桌面端建置 | PR | claude/project-thread-fr1onb | success | 6.7 分 | 1.2 分 | [#39984702320](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702320/attempts/1) |
| 10-23 09:11 | 一鍵安裝腳本 | PR | claude/project-thread-fr1onb | failure | 15.1 分 | 0.1 分 | [#39984702272](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39984702272/attempts/1) |
| 10-23 08:51 | 伺服器分發包 | PR | claude/project-thread-fr1onb | success | 7.5 分 | 0.1 分 | [#39981852267](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852267/attempts/1) |
| 10-23 08:51 | CI | PR | claude/project-thread-fr1onb | failure | 14.7 分 | 0.0 分 | [#39981852293](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852293/attempts/1) |
| 10-23 08:51 | 桌面端建置 | PR | claude/project-thread-fr1onb | failure | 15.2 分 | 0.1 分 | [#39981852243](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39981852243/attempts/1) |
| 10-23 06:44 | CI | PR | claude/project-thread-fr1onb | success | 11.9 分 | 0.1 分 | [#39963718445](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39963718445/attempts/1) |
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

