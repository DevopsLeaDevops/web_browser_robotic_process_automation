# CI 運行耗時紀錄

更新：2026-10-26 22:03 America/Los_Angeles（PDT，UTC−07:00）。共 587 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 238（0） | 124（0） | 3.4 分（0.0 分） | 6.9 分（0.0 分） | 0.0 分（0.0 分） | 1381／544／0 分（0／0／0 分） |
| 桌面端建置 | 178（0） | 135（0） | 4.1 分（0.0 分） | 7.1 分（0.0 分） | 0.1 分（0.0 分） | 18／541／770 分（0／0／0 分） |
| 伺服器分發包 | 64（0） | 59（0） | 2.0 分（0.0 分） | 5.4 分（0.0 分） | 0.1 分（0.0 分） | 247／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 76（0） | 49（0） | 3.1 分（0.0 分） | 17.1 分（0.0 分） | 0.1 分（0.0 分） | 449／316／195 分（0／0／0 分） |
| 每晚完整測試 | 16（0） | 0（0） | 40.0 分（0.0 分） | 60.2 分（0.0 分） | 0.1 分（0.0 分） | 577／563／414 分（0／0／0 分） |
| 發布 | 15（0） | 7（0） | 11.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 92／66／63 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-26 | 126 | 689 | 481 | 456 | 1627 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-26 21:49 America/Los_Angeles（PDT，UTC−07:00），合計 1364 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 173.8（173.8） | 14 | `apps/server/tests/test_portal.py` |
| 119.0（119.0） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 115.3（115.3） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 93.7（93.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 87.5（87.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 83.4（83.4） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 81.9（81.9） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 72.5（72.5） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 45.5（45.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 33.8（33.8） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-26 21:49 America/Los_Angeles（PDT，UTC−07:00），合計 526 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 82.4（86.8） | 11 | `apps/server/tests/test_portal.py` |
| 43.0（45.6） | 4 | `apps/server/tests/test_replay_flow.py` |
| 37.7（38.4） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 27.1（27.5） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 26.5（26.1） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 25.9（27.3） | 5 | `apps/server/tests/test_production_flow.py` |
| 20.5（19.7） | 18 | `apps/cli/tests/test_serve.py` |
| 16.1（19.9） | 29 | `apps/server/tests/test_api.py` |
| 16.0（15.6） | 11 | `apps/server/tests/test_gitsync.py` |
| 15.9（19.0） | 25 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-26 21:49 America/Los_Angeles（PDT，UTC−07:00），合計 1056 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 384.7（230.8） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 249.7（129.8） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 148.3（103.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 137.1（113.9） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 61.4（45.5） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 57.8（35.0） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 7.4（4.9） | 2 | `tests\smoke\test_browser.py` |
| 5.9（4.4） | 1 | `apps\desktop\tests\test_selftest.py` |
| 3.2（2.7） | 1 | `apps\worker\tests\test_worker.py` |

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

最近一次：2026-10-26 21:21 America/Los_Angeles（PDT，UTC−07:00），合計 953 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 109.1（90.1） | 14 | `apps/server/tests/test_portal.py` |
| 87.8（65.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 82.1（76.4） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 79.6（65.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 69.9（62.0） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 54.0（43.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 50.8（43.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 44.0（39.0） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.4（34.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.8（19.6） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-26 21:21 America/Los_Angeles（PDT，UTC−07:00），合計 923 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 108.5（87.7） | 14 | `apps/server/tests/test_portal.py` |
| 81.9（78.5） | 14 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.5（77.5） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 76.8（77.1） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 65.6（56.4） | 16 | `packages/rpa_runner/tests/test_debug.py` |
| 52.3（52.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 51.2（50.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 43.1（43.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.7（34.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.8（19.6） | 18 | `apps/cli/tests/test_serve.py` |

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

最近一次：2026-10-26 21:21 America/Los_Angeles（PDT，UTC−07:00），合計 1261 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 128.9（128.9） | 14 | `apps\server\tests\test_portal.py` |
| 106.4（109.3） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 98.2（98.9） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 90.7（92.5） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 80.4（82.5） | 16 | `packages\rpa_runner\tests\test_debug.py` |
| 74.2（74.2） | 9 | `apps\server\tests\test_production_flow.py` |
| 63.0（62.5） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.1（56.8） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 55.1（27.9） | 29 | `apps\server\tests\test_api.py` |
| 39.4（39.4） | 4 | `apps\server\tests\test_replay_flow.py` |

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
| 10-26 21:57 | 桌面端建置 | 手動 | ci/layered-ci | success | 5.9 分 | 0.1 分 | [#40452459787](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40452459787/attempts/1) |
| 10-26 21:55 | 桌面端建置 | 手動 | ci/layered-ci | cancelled | 1.9 分 | 0.1 分 | [#40452363113](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40452363113/attempts/1) |
| 10-26 21:49 | CI | 推送 | main | failure | 6.8 分 | 0.0 分 | [#40451749029](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749029/attempts/1) |
| 10-26 21:48 | 伺服器分發包 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40451749054](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749054/attempts/1) |
| 10-26 21:48 | 一鍵安裝腳本 | 推送 | main | success | 0.2 分 | 0.0 分 | [#40451749025](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451749025/attempts/1) |
| 10-26 21:47 | 伺服器分發包 | PR | fix/update-manifest-windows-tests | success | 0.1 分 | 0.0 分 | [#40451694434](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694434/attempts/1) |
| 10-26 21:47 | 一鍵安裝腳本 | PR | fix/update-manifest-windows-tests | success | 0.1 分 | 0.0 分 | [#40451694439](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694439/attempts/1) |
| 10-26 21:47 | CI | PR | fix/update-manifest-windows-tests | failure | 4.7 分 | 0.1 分 | [#40451694384](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451694384/attempts/1) |
| 10-26 21:44 | CI | 推送 | main | cancelled | 4.2 分 | 0.1 分 | [#40451366029](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451366029/attempts/1) |
| 10-26 21:44 | 桌面端建置 | 推送 | main | success | 0.1 分 | 0.0 分 | [#40451366021](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451366021/attempts/1) |
| 10-26 21:44 | 伺服器分發包 | 推送 | main | success | 2.2 分 | 0.1 分 | [#40451365890](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451365890/attempts/1) |
| 10-26 21:44 | 桌面端建置 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40451347544](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347544/attempts/1) |
| 10-26 21:44 | 一鍵安裝腳本 | PR | ci/layered-ci | success | 0.2 分 | 0.0 分 | [#40451347563](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347563/attempts/1) |
| 10-26 21:44 | 伺服器分發包 | PR | ci/layered-ci | success | 2.0 分 | 0.1 分 | [#40451347652](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347652/attempts/1) |
| 10-26 21:44 | CI | PR | ci/layered-ci | success | 4.3 分 | 0.0 分 | [#40451347675](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40451347675/attempts/1) |
| 10-26 21:40 | CI | 推送 | main | cancelled | 4.2 分 | 0.1 分 | [#40450919685](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40450919685/attempts/1) |
| 10-26 21:39 | 伺服器分發包 | 推送 | main | success | 1.9 分 | 0.1 分 | [#40450919770](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40450919770/attempts/1) |
| 10-26 21:39 | 桌面端建置 | 推送 | main | success | 7.1 分 | 0.1 分 | [#40450919669](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40450919669/attempts/1) |
| 10-26 21:38 | CI | 推送 | main | cancelled | 1.7 分 | 0.1 分 | [#40450879277](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40450879277/attempts/1) |
| 10-26 21:35 | 桌面端建置 | 手動 | ci/layered-ci | success | 6.5 分 | 0.1 分 | [#40450579685](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40450579685/attempts/1) |
| 10-26 21:24 | 桌面端建置 | PR | fix/scheduled-update-tests | success | 0.1 分 | 0.0 分 | [#40449578137](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449578137/attempts/1) |
| 10-26 21:24 | 伺服器分發包 | PR | fix/scheduled-update-tests | success | 0.2 分 | 0.1 分 | [#40449578153](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449578153/attempts/1) |
| 10-26 21:24 | CI | PR | fix/scheduled-update-tests | success | 1.9 分 | 0.0 分 | [#40449578184](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449578184/attempts/1) |
| 10-26 21:21 | 每晚完整測試 | PR | ci/layered-ci | cancelled | 24.3 分 | 0.1 分 | [#40449194134](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/40449194134/attempts/1) |
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

