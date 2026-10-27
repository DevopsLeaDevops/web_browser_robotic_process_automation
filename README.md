# CI 運行耗時紀錄

更新：2026-10-26 21:25 America/Los_Angeles（PDT，UTC−07:00）。共 565 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 231（0） | 122（0） | 3.4 分（0.0 分） | 7.0 分（0.0 分） | 0.0 分（0.0 分） | 1337／522／0 分（0／0／0 分） |
| 桌面端建置 | 172（0） | 130（0） | 4.1 分（0.0 分） | 7.4 分（0.0 分） | 0.1 分（0.0 分） | 17／529／736 分（0／0／0 分） |
| 伺服器分發包 | 59（0） | 54（0） | 2.0 分（0.0 分） | 5.4 分（0.0 分） | 0.1 分（0.0 分） | 236／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 73（0） | 46（0） | 3.3 分（0.0 分） | 17.1 分（0.0 分） | 0.1 分（0.0 分） | 449／316／195 分（0／0／0 分） |
| 每晚完整測試 | 15（0） | 0（0） | 40.7 分（0.0 分） | 60.2 分（0.0 分） | 0.1 分（0.0 分） | 536／539／390 分（0／0／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-26 | 104 | 592 | 423 | 398 | 1412 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-26 21:20 America/Los_Angeles（PDT，UTC−07:00），合計 234 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.6（19.9） | 18 | `apps/cli/tests/test_serve.py` |
| 15.7（15.8） | 29 | `apps/server/tests/test_api.py` |
| 15.7（16.1） | 25 | `apps/server/tests/test_production_api.py` |
| 14.3（14.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 13.8（13.8） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.0） | 14 | `apps/worker/tests/test_gateway.py` |
| 11.3（11.4） | 20 | `apps/server/tests/test_recorder_api.py` |
| 10.0（10.5） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.4（9.4） | 24 | `apps/desktop/tests/test_updates.py` |
| 9.3（13.2） | 11 | `apps/server/tests/test_gitsync.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-26 21:20 America/Los_Angeles（PDT，UTC−07:00），合計 287 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 20.7（19.9） | 29 | `apps/server/tests/test_api.py` |
| 20.4（19.0） | 25 | `apps/server/tests/test_production_api.py` |
| 19.7（19.7） | 18 | `apps/cli/tests/test_serve.py` |
| 19.2（17.9） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.2（15.2） | 11 | `apps/server/tests/test_gitsync.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.8（13.2） | 20 | `apps/server/tests/test_recorder_api.py` |
| 13.5（13.0） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.1（12.0） | 14 | `apps/server/tests/test_workflow_api.py` |
| 10.6（11.3） | 10 | `apps/server/tests/test_videos.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-26 20:53 America/Los_Angeles（PDT，UTC−07:00），合計 629 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 230.8（227.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 129.8（121.2） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 109.2（109.7） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 89.6（90.2） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 38.2（39.0） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 21.3（28.5） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 4.9（4.8） | 2 | `tests\smoke\test_browser.py` |
| 3.0（3.2） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.6（2.7） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-10-26 20:53 America/Los_Angeles（PDT，UTC−07:00），合計 1214 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 131.7（117.9） | 14 | `apps/server/tests/test_portal.py` |
| 125.4（106.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 124.2（81.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 101.5（94.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 97.3（97.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 90.2（89.7） | 18 | `apps/cli/tests/test_serve.py` |
| 61.8（51.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 59.6（58.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 52.8（56.1） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.2（37.0） | 4 | `apps/server/tests/test_replay_flow.py` |

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

最近一次：2026-10-26 20:51 America/Los_Angeles（PDT，UTC−07:00），合計 958 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 111.5（68.2） | 14 | `apps/server/tests/test_portal.py` |
| 81.5（74.2） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 79.3（62.2） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 78.6（60.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 65.1（51.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 55.5（40.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.6（38.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.6（37.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.7（32.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.8（17.3） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-26 20:51 America/Los_Angeles（PDT，UTC−07:00），合計 740 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 84.5（84.5） | 14 | `apps/server/tests/test_portal.py` |
| 74.7（74.7） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 57.8（77.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 57.3（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 52.7（54.5） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 38.4（49.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 37.2（49.9） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 36.0（42.3） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 32.7（34.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.6（19.5） | 18 | `apps/cli/tests/test_serve.py` |

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

最近一次：2026-10-26 20:53 America/Los_Angeles（PDT，UTC−07:00），合計 1242 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 134.4（117.1） | 14 | `apps\server\tests\test_portal.py` |
| 103.9（92.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 102.3（109.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 98.9（100.2） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 78.8（82.5） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 72.6（72.6） | 9 | `apps\server\tests\test_production_flow.py` |
| 58.1（56.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 54.0（62.5） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 39.6（39.5） | 4 | `apps\server\tests\test_replay_flow.py` |
| 31.6（32.1） | 11 | `apps\server\tests\test_gitsync.py` |

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
| 10-26 21:24 | 桌面端建置 | PR | fix/scheduled-update-tests | success | 0.1 分 | 0.0 分 | [#40449578137](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449578137/attempts/1) |
| 10-26 21:24 | 伺服器分發包 | PR | fix/scheduled-update-tests | success | 0.2 分 | 0.1 分 | [#40449578153](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449578153/attempts/1) |
| 10-26 21:20 | 桌面端建置 | PR | ci/layered-ci | success | 0.1 分 | 0.0 分 | [#40449194083](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449194083/attempts/1) |
| 10-26 21:20 | 一鍵安裝腳本 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40449194082](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449194082/attempts/1) |
| 10-26 21:20 | CI | PR | ci/layered-ci | success | 1.8 分 | 0.1 分 | [#40449194181](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449194181/attempts/1) |
| 10-26 21:10 | 桌面端建置 | 手動 | ci/layered-ci-probe | success | 9.2 分 | 4.6 分 | [#40448113960](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448113960/attempts/1) |
| 10-26 21:09 | 每晚完整測試 | PR | ci/layered-ci | cancelled | 11.8 分 | 3.8 分 | [#40448083456](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448083456/attempts/1) |
| 10-26 21:08 | 伺服器分發包 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40448083449](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448083449/attempts/1) |
| 10-26 21:08 | 一鍵安裝腳本 | PR | ci/layered-ci | success | 0.2 分 | 0.1 分 | [#40448083491](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448083491/attempts/1) |
| 10-26 21:08 | CI | PR | ci/layered-ci | success | 3.4 分 | 0.1 分 | [#40448083406](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448083406/attempts/1) |
| 10-26 21:08 | 桌面端建置 | PR | ci/layered-ci | success | 7.1 分 | 0.1 分 | [#40448083433](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448083433/attempts/1) |
| 10-26 21:08 | 桌面端建置 | 手動 | ci/layered-ci-probe | cancelled | 1.6 分 | 0.1 分 | [#40448079910](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40448079910/attempts/1) |
| 10-26 21:04 | 桌面端建置 | 手動 | ci/layered-ci-probe | failure | 2.3 分 | 0.1 分 | [#40447732366](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40447732366/attempts/1) |
| 10-26 21:01 | 桌面端建置 | PR | fix/update-manifest-windows-tests | success | 0.1 分 | 0.0 分 | [#40447383791](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40447383791/attempts/1) |
| 10-26 21:01 | CI | PR | fix/update-manifest-windows-tests | success | 1.8 分 | 0.0 分 | [#40447383736](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40447383736/attempts/1) |
| 10-26 20:54 | 桌面端建置 | 手動 | ci/layered-ci-probe | success | 9.6 分 | 2.8 分 | [#40446795562](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446795562/attempts/1) |
| 10-26 20:53 | 伺服器分發包 | PR | fix/scheduled-update-tests | success | 2.1 分 | 0.1 分 | [#40446668716](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446668716/attempts/1) |
| 10-26 20:53 | CI | PR | fix/scheduled-update-tests | success | 4.0 分 | 0.1 分 | [#40446668674](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446668674/attempts/1) |
| 10-26 20:53 | 桌面端建置 | PR | fix/scheduled-update-tests | success | 5.7 分 | 0.0 分 | [#40446668801](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446668801/attempts/1) |
| 10-26 20:53 | 每晚完整測試 | 手動 | fix/scheduled-update-tests | failure | 21.9 分 | 0.1 分 | [#40446663520](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446663520/attempts/1) |
| 10-26 20:51 | 每晚完整測試 | PR | ci/layered-ci | cancelled | 18.0 分 | 0.0 分 | [#40446418350](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446418350/attempts/1) |
| 10-26 20:50 | 桌面端建置 | PR | ci/layered-ci | success | 0.1 分 | 0.0 分 | [#40446418424](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446418424/attempts/1) |
| 10-26 20:50 | 一鍵安裝腳本 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40446418318](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446418318/attempts/1) |
| 10-26 20:50 | CI | PR | ci/layered-ci | success | 3.4 分 | 0.0 分 | [#40446418389](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40446418389/attempts/1) |
| 10-26 20:38 | 每晚完整測試 | 手動 | fix/update-manifest-windows-tests | failure | 21.5 分 | 0.2 分 | [#40445285336](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445285336/attempts/1) |
| 10-26 20:38 | CI | PR | fix/update-manifest-windows-tests | success | 5.9 分 | 1.3 分 | [#40445278739](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445278739/attempts/1) |
| 10-26 20:38 | 桌面端建置 | PR | fix/update-manifest-windows-tests | success | 11.3 分 | 5.5 分 | [#40445278672](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445278672/attempts/1) |
| 10-26 20:38 | CI | PR | ci/layered-ci | failure | 4.3 分 | 0.0 分 | [#40445262306](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445262306/attempts/1) |
| 10-26 20:38 | 每晚完整測試 | PR | ci/layered-ci | cancelled | 13.0 分 | 3.2 分 | [#40445262332](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445262332/attempts/1) |
| 10-26 20:38 | 伺服器分發包 | PR | ci/layered-ci | success | 2.2 分 | 0.1 分 | [#40445262236](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445262236/attempts/1) |
| 10-26 20:38 | 一鍵安裝腳本 | PR | ci/layered-ci | success | 3.5 分 | 1.4 分 | [#40445262229](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445262229/attempts/1) |
| 10-26 20:38 | 桌面端建置 | PR | ci/layered-ci | success | 5.8 分 | 0.0 分 | [#40445262144](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40445262144/attempts/1) |
| 10-26 20:15 | 伺服器分發包 | PR | fix/scheduled-update-tests | success | 2.1 分 | 0.1 分 | [#40443171338](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40443171338/attempts/1) |
| 10-26 20:15 | CI | PR | fix/scheduled-update-tests | success | 2.6 分 | 0.0 分 | [#40443171309](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40443171309/attempts/1) |
| 10-26 20:15 | 桌面端建置 | PR | fix/scheduled-update-tests | success | 7.4 分 | 0.1 分 | [#40443171354](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40443171354/attempts/1) |
| 10-26 20:15 | 每晚完整測試 | 手動 | fix/scheduled-update-tests | failure | 22.7 分 | 0.0 分 | [#40443170624](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40443170624/attempts/1) |
| 10-26 19:08 | CI | PR | docs/release-0-6-3-result | success | 3.4 分 | 0.1 分 | [#40436672074](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40436672074/attempts/1) |
| 10-26 14:13 | 一鍵安裝腳本 | 排程 | main | failure | 25.8 分 | 0.1 分 | [#40402544121](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40402544121/attempts/1) |
| 10-26 13:52 | 每晚完整測試 | 排程 | main | failure | 57.5 分 | 1.1 分 | [#40399471079](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40399471079/attempts/1) |
| 10-26 10:58 | 發布 | 推送 | v0.6.3 | success | 11.9 分 | 4.5 分 | [#40353916274 第 9 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40353916274/attempts/9) |

