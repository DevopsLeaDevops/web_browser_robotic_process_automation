# CI 運行耗時紀錄

更新：2026-10-26 20:17 America/Los_Angeles（PDT，UTC−07:00）。共 530 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 223（0） | 115（0） | 3.3 分（0.0 分） | 7.1 分（0.0 分） | 0.0 分（0.0 分） | 1298／509／0 分（0／0／0 分） |
| 桌面端建置 | 159（0） | 119（0） | 4.1 分（0.0 分） | 6.9 分（0.0 分） | 0.1 分（0.0 分） | 16／496／657 分（0／0／0 分） |
| 伺服器分發包 | 55（0） | 50（0） | 2.0 分（0.0 分） | 6.7 分（0.0 分） | 0.1 分（0.0 分） | 228／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 69（0） | 42（0） | 3.3 分（0.0 分） | 17.1 分（0.0 分） | 0.1 分（0.0 分） | 444／314／192 分（0／0／0 分） |
| 每晚完整測試 | 9（0） | 0（0） | 47.5 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 452／432／288 分（0／0／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-26 | 69 | 454 | 268 | 214 | 937 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-26 19:08 America/Los_Angeles（PDT，UTC−07:00），合計 296 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 22.6（22.8） | 29 | `apps/server/tests/test_api.py` |
| 22.0（22.2） | 25 | `apps/server/tests/test_production_api.py` |
| 20.8（21.0） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 20.2（19.9） | 18 | `apps/cli/tests/test_serve.py` |
| 16.1（16.3） | 11 | `apps/server/tests/test_gitsync.py` |
| 14.9（15.9） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.1（13.7） | 14 | `apps/server/tests/test_workflow_api.py` |
| 12.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 11.4（11.8） | 12 | `apps/server/tests/test_replay.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-26 19:08 America/Los_Angeles（PDT，UTC−07:00），合計 582 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 94.5（84.0） | 11 | `apps/server/tests/test_portal.py` |
| 47.3（43.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 42.1（38.6） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 32.1（28.5） | 5 | `apps/server/tests/test_production_flow.py` |
| 31.0（27.2） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 26.1（25.1） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 19.9（18.9） | 25 | `apps/server/tests/test_production_api.py` |
| 19.8（20.2） | 18 | `apps/cli/tests/test_serve.py` |
| 18.9（18.9） | 29 | `apps/server/tests/test_api.py` |
| 18.0（17.4） | 22 | `apps/server/tests/test_remote_worker_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-26 08:45 America/Los_Angeles（PDT，UTC−07:00），合計 641 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 228.4（235.9） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 125.5（125.9） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 115.5（106.3） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 90.7（91.1） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 41.6（39.2） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 26.3（32.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.1（4.3） | 2 | `tests\smoke\test_browser.py` |
| 4.8（3.9） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.9（2.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 1347 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 154.1（116.1） | 14 | `apps/server/tests/test_portal.py` |
| 138.3（101.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 134.3（108.8） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 127.6（99.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 94.4（96.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 90.5（85.6） | 18 | `apps/cli/tests/test_serve.py` |
| 80.9（69.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 78.7（56.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 52.2（51.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 43.9（38.2） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 976 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 161.8（115.6） | 14 | `apps/server/tests/test_portal.py` |
| 116.7（92.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 105.3（88.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 103.0（86.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 97.3（90.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 84.5（60.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 76.3（55.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 61.6（48.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 41.5（37.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 27.9（20.8） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 945 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 145.6（111.1） | 14 | `apps/server/tests/test_portal.py` |
| 125.8（83.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 120.8（87.8） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 95.0（93.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 93.3（91.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.4（68.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 60.3（60.6） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 55.7（48.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.4（38.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 30.5（17.1） | 10 | `packages/rpa_runner/tests/test_frames.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 823 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 93.8（68.2） | 14 | `apps/server/tests/test_portal.py` |
| 76.4（67.6） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 65.8（62.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 65.2（60.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 62.0（51.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 43.8（40.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 43.7（38.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 39.0（37.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 34.5（32.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.6（12.2） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 952 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 108.8（87.7） | 14 | `apps/server/tests/test_portal.py` |
| 82.5（72.3） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 82.0（78.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 80.0（78.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 66.9（56.4） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 52.9（52.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.2（50.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.0（43.7） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 37.3（34.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.5（21.2） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 703 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 110.1（89.0） | 14 | `apps/server/tests/test_portal.py` |
| 82.9（71.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 82.3（80.0） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 81.6（79.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 57.6（52.5） | 9 | `apps/server/tests/test_production_flow.py` |
| 56.7（45.9） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 52.0（50.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 45.2（44.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.9（35.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.3（20.6） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 708 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.9（89.3） | 14 | `apps/server/tests/test_portal.py` |
| 83.6（71.1） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.3（80.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 83.0（78.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 57.9（53.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 57.2（48.7） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 53.7（51.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 46.1（45.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.1（35.3） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.4（21.0） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 1329 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 133.2（109.5） | 14 | `apps\server\tests\test_portal.py` |
| 112.9（101.0） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 110.8（112.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 92.5（92.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 84.0（70.8） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 74.7（74.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 72.6（63.5） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.0（56.4） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 55.0（24.5） | 29 | `apps\server\tests\test_api.py` |
| 42.2（38.4） | 4 | `apps\server\tests\test_replay_flow.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 886 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 131.1（108.1） | 14 | `apps\server\tests\test_portal.py` |
| 117.6（112.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 104.7（99.6） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 92.4（90.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 74.4（73.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 73.7（61.0） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 64.6（63.6） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.1（56.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 40.3（38.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.4（27.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-26 13:52 America/Los_Angeles（PDT，UTC−07:00），合計 876 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 135.0（105.3） | 14 | `apps\server\tests\test_portal.py` |
| 109.8（109.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.1（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 93.4（90.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 74.8（71.9） | 9 | `apps\server\tests\test_production_flow.py` |
| 69.2（57.6） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 66.2（66.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.9（55.9） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 39.4（38.3） | 4 | `apps\server\tests\test_replay_flow.py` |
| 29.5（28.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-26 20:15 | 伺服器分發包 | PR | fix/scheduled-update-tests | success | 2.1 分 | 0.1 分 | [#40443171338](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40443171338/attempts/1) |
| 10-26 19:08 | CI | PR | docs/release-0-6-3-result | success | 3.4 分 | 0.1 分 | [#40436672074](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40436672074/attempts/1) |
| 10-26 14:13 | 一鍵安裝腳本 | 排程 | main | failure | 25.8 分 | 0.1 分 | [#40402544121](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40402544121/attempts/1) |
| 10-26 13:52 | 每晚完整測試 | 排程 | main | failure | 57.5 分 | 1.1 分 | [#40399471079](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40399471079/attempts/1) |
| 10-26 10:58 | 發布 | 推送 | v0.6.3 | success | 11.9 分 | 4.5 分 | [#40353916274 第 9 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/9) |
| 10-26 10:43 | 發布 | 推送 | v0.6.3 | cancelled | 15.0 分 | 0.0 分 | [#40353916274 第 8 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/8) |
| 10-26 10:27 | 發布 | 推送 | v0.6.3 | failure | 15.1 分 | 0.0 分 | [#40353916274 第 7 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/7) |
| 10-26 10:11 | 發布 | 推送 | v0.6.3 | success | -72.0 分 | 0.0 分 | [#40353916274 第 6 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/6) |
| 10-26 09:56 | 發布 | 推送 | v0.6.3 | failure | 15.2 分 | 0.0 分 | [#40353916274 第 5 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/5) |
| 10-26 09:41 | 發布 | 推送 | v0.6.3 | failure | 15.0 分 | 0.0 分 | [#40353916274 第 4 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/4) |
| 10-26 09:25 | 發布 | 推送 | v0.6.3 | failure | 15.0 分 | 0.0 分 | [#40353916274 第 3 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/3) |
| 10-26 09:10 | 發布 | 推送 | v0.6.3 | failure | 15.0 分 | 0.0 分 | [#40353916274 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/2) |
| 10-26 08:54 | 發布 | 推送 | v0.6.3 | failure | 15.3 分 | 0.1 分 | [#40353916274](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/1) |
| 10-26 08:45 | 伺服器分發包 | 推送 | main | success | 1.9 分 | 0.1 分 | [#40352477923](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352477923/attempts/1) |
| 10-26 08:45 | CI | 推送 | main | failure | 14.8 分 | 0.0 分 | [#40352478076](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352478076/attempts/1) |
| 10-26 08:45 | 一鍵安裝腳本 | 推送 | main | failure | 15.2 分 | 0.0 分 | [#40352478021](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352478021/attempts/1) |
| 10-26 08:45 | 桌面端建置 | 推送 | main | failure | 15.2 分 | 0.1 分 | [#40352477751](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40352477751/attempts/1) |
| 10-26 08:43 | CI | PR | chore/release-0.6.3 | success | 3.3 分 | 0.1 分 | [#40349430960 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349430960/attempts/2) |
| 10-26 08:27 | 伺服器分發包 | PR | chore/release-0.6.3 | success | 2.0 分 | 0.1 分 | [#40349431129](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431129/attempts/1) |
| 10-26 08:27 | CI | PR | chore/release-0.6.3 | failure | 12.2 分 | 0.1 分 | [#40349430960](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349430960/attempts/1) |
| 10-26 08:27 | 桌面端建置 | PR | chore/release-0.6.3 | failure | 20.2 分 | 0.0 分 | [#40349431057](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431057/attempts/1) |
| 10-26 08:27 | 一鍵安裝腳本 | PR | chore/release-0.6.3 | success | 23.2 分 | 20.6 分 | [#40349431075](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349431075/attempts/1) |
| 10-26 08:24 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.3 分 | 0.0 分 | [#40337307053 第 3 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/3) |
| 10-26 08:24 | CI | 推送 | main | failure | 7.2 分 | 0.0 分 | [#40349006150](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349006150/attempts/1) |
| 10-26 08:24 | 伺服器分發包 | 推送 | main | success | 7.3 分 | 0.1 分 | [#40349005945](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349005945/attempts/1) |
| 10-26 08:24 | 桌面端建置 | 推送 | main | failure | 20.5 分 | 0.0 分 | [#40349006001](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40349006001/attempts/1) |
| 10-26 07:31 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.0 分 | 0.0 分 | [#40337307053 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/2) |
| 10-26 07:12 | 伺服器分發包 | PR | fix/remote-debug-reload | success | 3.7 分 | 0.1 分 | [#40337307355](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307355/attempts/1) |
| 10-26 07:12 | CI | PR | fix/remote-debug-reload | success | 3.7 分 | 0.1 分 | [#40337307103](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307103/attempts/1) |
| 10-26 07:12 | 桌面端建置 | PR | fix/remote-debug-reload | failure | 15.3 分 | 0.0 分 | [#40337307053](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337307053/attempts/1) |
| 10-26 07:10 | 桌面端建置 | PR | fix/remote-debug-reload | cancelled | 1.6 分 | 0.0 分 | [#40337150811](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337150811/attempts/1) |
| 10-26 07:10 | CI | PR | fix/remote-debug-reload | cancelled | 1.8 分 | 0.1 分 | [#40337151171](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40337151171/attempts/1) |
| 10-26 05:06 | 發布 | 推送 | v0.6.2 | success | 8.7 分 | 0.1 分 | [#40320045782](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40320045782/attempts/1) |
| 10-26 05:04 | CI | 推送 | main | failure | 5.1 分 | 0.0 分 | [#40319590219](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590219/attempts/1) |
| 10-26 05:03 | 伺服器分發包 | 推送 | main | success | 2.8 分 | 0.1 分 | [#40319590232](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590232/attempts/1) |
| 10-26 05:03 | 一鍵安裝腳本 | 推送 | main | success | 3.4 分 | 0.1 分 | [#40319590126](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590126/attempts/1) |
| 10-26 05:03 | 桌面端建置 | 推送 | main | success | 6.0 分 | 0.1 分 | [#40319590253](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40319590253/attempts/1) |
| 10-26 04:56 | CI | PR | chore/release-0.6.2 | success | 1.9 分 | 0.0 分 | [#40318816599](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318816599/attempts/1) |
| 10-26 04:56 | 一鍵安裝腳本 | PR | chore/release-0.6.2 | success | 0.1 分 | 0.0 分 | [#40318814074](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318814074/attempts/1) |
| 10-26 04:56 | 伺服器分發包 | PR | chore/release-0.6.2 | success | 0.2 分 | 0.0 分 | [#40318814050](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40318814050/attempts/1) |

