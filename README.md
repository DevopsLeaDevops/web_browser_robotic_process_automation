# CI 運行耗時紀錄

更新：2026-10-29 06:51 America/Los_Angeles（PDT，UTC−07:00）。共 776 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 157（138） | 68（81） | 4.1 分（2.9 分） | 8.7 分（5.2 分） | 0.1 分（0.0 分） | 1132／330／0 分（632／281／0 分） |
| 桌面端建置 | 115（100） | 91（77） | 5.2 分（4.0 分） | 9.2 分（5.3 分） | 0.1 分（0.1 分） | 15／280／537 分（9／292／256 分） |
| 伺服器分發包 | 103（0） | 98（0） | 1.9 分（0.0 分） | 4.8 分（0.0 分） | 0.1 分（0.0 分） | 354／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 98（27） | 80（15） | 0.2 分（3.2 分） | 15.2 分（15.2 分） | 0.0 分（0.1 分） | 365／289／187 分（140／96／35 分） |
| 每晚完整測試 | 18（2） | 0（0） | 47.4 分（40.0 分） | 57.5 分（40.7 分） | 0.1 分（0.0 分） | 721／685／584 分（80／80／0 分） |
| 發布 | 17（1） | 9（1） | 11.9 分（5.7 分） | 15.1 分（5.7 分） | 0.1 分（0.1 分） | 109／75／90 分（1／5／4 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-29 | 43 | 198 | 78 | 75 | 352 |
| 2026-10-28 | 69 | 256 | 115 | 22 | 392 |
| 2026-10-27 | 76 | 286 | 142 | 101 | 528 |
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

最近一次：2026-10-29 06:37 America/Los_Angeles（PDT，UTC−07:00），合計 1665 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 196.1（196.0） | 15 | `apps/server/tests/test_portal.py` |
| 137.8（137.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 136.3（136.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 130.1（130.1） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 101.3（93.0） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 95.7（95.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 90.3（90.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 80.4（77.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 50.8（47.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 34.4（34.4） | 3 | `apps/server/tests/test_flow.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-29 06:37 America/Los_Angeles（PDT，UTC−07:00），合計 678 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 102.5（100.3） | 12 | `apps/server/tests/test_portal.py` |
| 45.0（45.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 42.5（42.1） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 33.0（31.9） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 32.0（30.9） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 31.3（30.7） | 5 | `apps/server/tests/test_production_flow.py` |
| 22.7（22.0） | 25 | `apps/server/tests/test_production_api.py` |
| 22.1（22.3） | 29 | `apps/server/tests/test_api.py` |
| 20.6（20.2） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 19.9（19.8） | 18 | `apps/cli/tests/test_serve.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-29 06:07 America/Los_Angeles（PDT，UTC−07:00），合計 2335 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 349.4（297.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 244.1（297.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 244.1（297.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 177.8（94.5） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 141.0（139.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 136.5（108.3） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 114.7（139.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 114.7（139.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 104.6（108.3） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 104.6（108.3） | 20 | `packages\rpa_runner\tests\test_run.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 1337 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 149.9（146.9） | 15 | `apps/server/tests/test_portal.py` |
| 137.1（125.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 114.3（124.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 103.9（99.0） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 102.4（101.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 89.9（90.2） | 18 | `apps/cli/tests/test_serve.py` |
| 75.2（65.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 60.1（55.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 56.7（59.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.6（41.6） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 934 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 145.3（129.8） | 15 | `apps/server/tests/test_portal.py` |
| 100.9（100.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 97.7（87.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 93.5（91.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 93.3（97.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 73.0（70.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 64.3（54.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 56.6（50.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.0（38.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 31.5（23.3） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 925 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 148.3（142.1） | 15 | `apps/server/tests/test_portal.py` |
| 103.9（92.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 102.6（93.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 99.1（94.9） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 93.5（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 67.3（67.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 66.6（60.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 51.0（51.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.9（40.7） | 4 | `apps/server/tests/test_replay_flow.py` |
| 24.5（24.4） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 919 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.8（105.8） | 15 | `apps/server/tests/test_portal.py` |
| 79.8（79.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 72.8（65.1） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 68.2（68.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.5（66.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 45.4（45.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 44.0（44.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.3（39.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.5（35.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 1078 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 120.7（108.8） | 15 | `apps/server/tests/test_portal.py` |
| 85.1（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 84.6（81.9） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 84.1（76.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 72.2（65.6） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 58.5（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 53.2（50.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 46.2（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.8（36.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 22.8（19.2） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 769 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 117.6（106.7） | 15 | `apps/server/tests/test_portal.py` |
| 84.9（78.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 83.5（80.8） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 80.6（76.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 62.3（53.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 57.8（52.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 53.2（50.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.0（34.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 46.8（43.6） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 22.4（19.9） | 17 | `packages/rpa_runner/tests/test_upload.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 768 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 121.0（107.9） | 15 | `apps/server/tests/test_portal.py` |
| 85.1（81.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 85.1（77.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 83.0（77.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 62.7（53.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 59.0（53.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 52.6（50.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 46.6（43.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 37.3（35.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 22.5（19.8） | 17 | `packages/rpa_runner/tests/test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 1117 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 111.2（128.1） | 15 | `apps\server\tests\test_portal.py` |
| 96.0（106.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 82.4（94.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 81.6（98.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 74.6（81.1） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 57.3（72.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 52.2（61.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 47.4（57.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.8（23.7） | 3 | `apps\server\tests\test_flow.py` |
| 36.4（39.2） | 4 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 754 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 111.4（122.1） | 15 | `apps\server\tests\test_portal.py` |
| 89.0（110.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 82.2（90.0） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 80.1（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 63.5（64.0） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 57.2（74.4） | 9 | `apps\server\tests\test_production_flow.py` |
| 52.5（62.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 48.7（55.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 35.5（40.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 22.5（26.1） | 17 | `packages\rpa_runner\tests\test_upload.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-29 04:48 America/Los_Angeles（PDT，UTC−07:00），合計 734 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 105.5（126.3） | 15 | `apps\server\tests\test_portal.py` |
| 86.0（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 81.0（89.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 79.6（97.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 63.3（65.8） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 56.6（70.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 49.9（61.9） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 46.8（55.9） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 35.3（38.7） | 4 | `apps\server\tests\test_replay_flow.py` |
| 22.1（26.8） | 17 | `packages\rpa_runner\tests\test_upload.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-29 06:37 | 發布 | 推送 | v0.8.0 | success | 14.1 分 | 2.9 分 | [#40883651046](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883651046/attempts/1) |
| 10-29 06:37 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40883612917](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883612917/attempts/1) |
| 10-29 06:37 | 伺服器分發包 | 推送 | main | success | 0.3 分 | 0.1 分 | [#40883612929](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883612929/attempts/1) |
| 10-29 06:37 | CI | 推送 | main | success | 8.2 分 | 0.1 分 | [#40883612948](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40883612948/attempts/1) |
| 10-29 06:31 | 伺服器分發包 | PR | chore/release-0.8.0 | success | 0.2 分 | 0.0 分 | [#40882772469](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40882772469/attempts/1) |
| 10-29 06:31 | 桌面端建置 | PR | chore/release-0.8.0 | success | 0.3 分 | 0.0 分 | [#40882772306](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40882772306/attempts/1) |
| 10-29 06:31 | CI | PR | chore/release-0.8.0 | success | 3.8 分 | 0.0 分 | [#40882772622](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40882772622/attempts/1) |
| 10-29 06:26 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40881952424](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40881952424/attempts/1) |
| 10-29 06:26 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40881952291](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40881952291/attempts/1) |
| 10-29 06:26 | CI | 推送 | main | success | 8.7 分 | 0.1 分 | [#40881952176](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40881952176/attempts/1) |
| 10-29 06:12 | CI | PR | feat/replay-chapters | success | 4.0 分 | 0.1 分 | [#40879735746](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40879735746/attempts/1) |
| 10-29 06:11 | 桌面端建置 | PR | feat/replay-chapters | cancelled | 0.2 分 | 0.0 分 | [#40879713926](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40879713926/attempts/1) |
| 10-29 06:11 | 一鍵安裝腳本 | PR | feat/replay-chapters | cancelled | 0.2 分 | 0.0 分 | [#40879713861](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40879713861/attempts/1) |
| 10-29 06:11 | CI | PR | feat/replay-chapters | cancelled | 0.5 分 | 0.0 分 | [#40879713968](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40879713968/attempts/1) |
| 10-29 06:07 | CI | PR | feat/replay-chapters | success | 3.9 分 | 0.0 分 | [#40878153717 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40878153717/attempts/2) |
| 10-29 06:01 | 桌面端建置 | PR | feat/replay-chapters | success | 0.1 分 | 0.0 分 | [#40878153751](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40878153751/attempts/1) |
| 10-29 06:01 | 一鍵安裝腳本 | PR | feat/replay-chapters | success | 0.2 分 | 0.0 分 | [#40878153701](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40878153701/attempts/1) |
| 10-29 06:01 | CI | PR | feat/replay-chapters | failure | 5.5 分 | 0.1 分 | [#40878153717](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40878153717/attempts/1) |
| 10-29 05:56 | 一鍵安裝腳本 | PR | feat/replay-chapters | success | 0.2 分 | 0.0 分 | [#40877487362](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40877487362/attempts/1) |
| 10-29 05:56 | 伺服器分發包 | PR | feat/replay-chapters | success | 2.1 分 | 0.1 分 | [#40877487318](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40877487318/attempts/1) |
| 10-29 05:56 | 桌面端建置 | PR | feat/replay-chapters | success | 2.8 分 | 0.0 分 | [#40877487108](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40877487108/attempts/1) |
| 10-29 05:56 | CI | PR | feat/replay-chapters | failure | 4.0 分 | 0.0 分 | [#40877487329](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40877487329/attempts/1) |
| 10-29 05:26 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40873329571](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40873329571/attempts/1) |
| 10-29 05:26 | 桌面端建置 | 推送 | main | success | 0.2 分 | 0.1 分 | [#40873329558](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40873329558/attempts/1) |
| 10-29 05:26 | CI | 推送 | main | failure | 7.6 分 | 0.1 分 | [#40873329611](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40873329611/attempts/1) |
| 10-29 05:22 | 一鍵安裝腳本 | PR | feat/replay-chapters | success | 0.2 分 | 0.0 分 | [#40872730230](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40872730230/attempts/1) |
| 10-29 05:22 | 桌面端建置 | PR | feat/replay-chapters | success | 4.2 分 | 0.0 分 | [#40872730249](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40872730249/attempts/1) |
| 10-29 05:22 | 伺服器分發包 | PR | feat/replay-chapters | success | 4.8 分 | 0.1 分 | [#40872730411](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40872730411/attempts/1) |
| 10-29 05:22 | CI | PR | feat/replay-chapters | failure | 5.3 分 | 0.0 分 | [#40872730266](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40872730266/attempts/1) |
| 10-29 04:48 | 桌面端建置 | PR | fix/nightly-windows-sockets | success | 0.2 分 | 0.0 分 | [#40868233487](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40868233487/attempts/1) |
| 10-29 04:48 | 一鍵安裝腳本 | PR | fix/nightly-windows-sockets | success | 0.2 分 | 0.0 分 | [#40868233516](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40868233516/attempts/1) |
| 10-29 04:48 | CI | PR | fix/nightly-windows-sockets | success | 3.4 分 | 0.0 分 | [#40868233533](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40868233533/attempts/1) |
| 10-29 04:48 | 每晚完整測試 | PR | fix/nightly-windows-sockets | failure | 54.6 分 | 0.0 分 | [#40868233654](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40868233654/attempts/1) |
| 10-29 04:10 | 發布 | 推送 | v0.7.1 | success | 9.7 分 | 1.8 分 | [#40863309319](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863309319/attempts/1) |
| 10-29 04:09 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40863129691](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863129691/attempts/1) |
| 10-29 04:09 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40863129918](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863129918/attempts/1) |
| 10-29 04:09 | CI | 推送 | main | failure | 7.8 分 | 0.0 分 | [#40863129661](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863129661/attempts/1) |
| 10-29 04:08 | 桌面端建置 | PR | chore/release-0.7.1 | success | 0.2 分 | 0.0 分 | [#40863069317](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863069317/attempts/1) |
| 10-29 04:08 | 一鍵安裝腳本 | PR | chore/release-0.7.1 | success | 0.3 分 | 0.1 分 | [#40863069347](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863069347/attempts/1) |
| 10-29 04:08 | CI | PR | chore/release-0.7.1 | success | 4.0 分 | 0.1 分 | [#40863069398](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40863069398/attempts/1) |

