# CI 運行耗時紀錄

更新：2026-11-04 14:03 America/Los_Angeles（PST，UTC−08:00）。共 834 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 25（174） | 13（78） | 4.7 分（4.0 分） | 7.9 分（9.1 分） | 0.0 分（0.1 分） | 175／57／0 分（1206／378／0 分） |
| 桌面端建置 | 19（129） | 13（95） | 2.8 分（5.3 分） | 7.0 分（15.0 分） | 0.0 分（0.1 分） | 3／30／60 分（15／348／584 分） |
| 伺服器分發包 | 17（96） | 12（91） | 2.0 分（2.0 分） | 3.0 分（5.4 分） | 0.1 分（0.1 分） | 46／0／0 分（343／0／0 分） |
| 一鍵安裝腳本 | 28（94） | 21（75） | 0.2 分（0.7 分） | 26.5 分（15.2 分） | 0.0 分（0.0 分） | 210／251／136 分（386／303／196 分） |
| 每晚完整測試 | 10（17） | 2（0） | 55.7 分（47.3 分） | 62.9 分（57.5 分） | 0.1 分（0.1 分） | 555／475／334 分（660／641／530 分） |
| 發布 | 2（15） | 2（7） | 11.9 分（11.9 分） | 14.1 分（15.2 分） | 2.4 分（0.1 分） | 14／9／21 分（95／65／69 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-11-04 | 2 | 117 | 87 | 0 | 203 |
| 2026-11-03 | 2 | 91 | 81 | 0 | 171 |
| 2026-11-02 | 2 | 87 | 90 | 0 | 177 |
| 2026-11-01 | 2 | 86 | 92 | 99 | 276 |
| 2026-10-31 | 3 | 80 | 86 | 97 | 263 |
| 2026-10-30 | 17 | 178 | 160 | 121 | 458 |
| 2026-10-29 | 73 | 364 | 228 | 233 | 825 |
| 2026-10-28 | 69 | 256 | 115 | 22 | 392 |
| 2026-10-27 | 76 | 286 | 142 | 101 | 528 |
| 2026-10-26 | 127 | 743 | 530 | 510 | 1783 |
| 2026-10-25 | 95 | 520 | 335 | 357 | 1212 |
| 2026-10-24 | 11 | 142 | 132 | 130 | 405 |
| 2026-10-23 | 33 | 204 | 123 | 115 | 441 |
| 2026-10-22 | 112 | 544 | 359 | 146 | 1048 |
| 2026-10-21 | 2 | 10 | 0 | 0 | 10 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 328 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 23.1（23.2） | 29 | `apps/server/tests/test_api.py` |
| 22.5（22.9） | 25 | `apps/server/tests/test_production_api.py` |
| 20.9（22.3） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 19.6（20.1） | 18 | `apps/cli/tests/test_serve.py` |
| 16.5（16.6） | 11 | `apps/server/tests/test_gitsync.py` |
| 15.7（16.4） | 20 | `apps/server/tests/test_recorder_api.py` |
| 14.1（14.8） | 13 | `apps/server/tests/test_replay.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.5（15.7） | 14 | `apps/server/tests/test_workflow_api.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 545 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.7（99.8） | 12 | `apps/server/tests/test_portal.py` |
| 39.9（46.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 35.4（44.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 25.8（31.7） | 10 | `packages/rpa_runner/tests/test_debug.py` |
| 24.7（28.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 22.9（31.2） | 5 | `apps/server/tests/test_production_flow.py` |
| 19.6（19.9） | 18 | `apps/cli/tests/test_serve.py` |
| 17.3（22.3） | 25 | `apps/server/tests/test_production_api.py` |
| 16.6（20.8） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 15.9（21.8） | 29 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-30 07:45 America/Los_Angeles（PDT，UTC−07:00），合計 785 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 284.3（244.1） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 140.4（140.8） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 111.3（104.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 91.7（106.4） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 66.7（71.4） | 17 | `packages\rpa_runner\tests\test_upload.py` |
| 50.7（49.4） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 27.2（27.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.6（5.2） | 2 | `tests\smoke\test_browser.py` |
| 4.3（4.5） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.8（2.8） | 1 | `apps\worker\tests\test_worker.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-1.xml

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 1446 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 172.0（149.9） | 15 | `apps/server/tests/test_portal.py` |
| 130.4（130.4） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 124.6（124.6） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 115.4（103.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 110.6（103.9） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 89.8（89.9） | 18 | `apps/cli/tests/test_serve.py` |
| 83.8（70.1） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 70.9（70.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 66.1（60.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.5（41.6） | 4 | `apps/server/tests/test_replay_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-2.xml

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 953 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 158.7（145.3） | 15 | `apps/server/tests/test_portal.py` |
| 122.8（105.3） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 106.0（104.7） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 95.0（97.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 91.8（93.3） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 70.0（70.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 65.7（64.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 46.2（50.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 40.0（40.0） | 4 | `apps/server/tests/test_replay_flow.py` |
| 25.1（20.7） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-macos-latest-3.13/pass-3.xml

最近一次：2026-11-01 12:51 America/Los_Angeles（PST，UTC−08:00），合計 990 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 148.7（148.3） | 15 | `apps/server/tests/test_portal.py` |
| 124.8（109.8） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 112.7（103.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 106.3（93.5） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 102.5（99.6） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 77.8（70.3） | 9 | `apps/server/tests/test_production_flow.py` |
| 63.5（66.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.5（50.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 42.2（40.9） | 4 | `apps/server/tests/test_replay_flow.py` |
| 27.0（20.4） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 1029 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.1（114.6） | 15 | `apps/server/tests/test_portal.py` |
| 92.5（91.9） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 81.5（79.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 73.7（72.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 72.4（66.6） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 53.2（51.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 53.1（51.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.9（41.8） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.8（35.8） | 4 | `apps/server/tests/test_replay_flow.py` |
| 19.9（19.8） | 18 | `apps/cli/tests/test_serve.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 990 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 110.8（108.5） | 15 | `apps/server/tests/test_portal.py` |
| 90.5（89.5） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 78.7（73.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 70.5（65.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 67.9（67.9） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 50.5（47.7） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 49.6（48.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 39.6（39.1） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 36.0（34.4） | 4 | `apps/server/tests/test_replay_flow.py` |
| 21.5（14.7） | 22 | `apps/server/tests/test_remote_worker_api.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 696 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 108.4（108.4） | 15 | `apps/server/tests/test_portal.py` |
| 90.3（90.0） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 76.7（76.7） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 67.1（67.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 55.5（54.5） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 50.4（48.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 48.9（48.9） | 9 | `apps/server/tests/test_production_flow.py` |
| 40.4（40.4） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.8（35.5） | 4 | `apps/server/tests/test_replay_flow.py` |
| 18.4（18.1） | 4 | `apps/server/tests/test_recorder_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 681 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 107.9（107.9） | 15 | `apps/server/tests/test_portal.py` |
| 89.7（89.3） | 16 | `packages/rpa_runner/tests/test_video_browser.py` |
| 73.9（73.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 66.8（66.9） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 54.8（53.8） | 19 | `packages/rpa_runner/tests/test_debug.py` |
| 47.2（47.3） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 47.2（47.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 40.5（40.2） | 20 | `packages/rpa_runner/tests/test_run.py` |
| 35.2（35.2） | 4 | `apps/server/tests/test_replay_flow.py` |
| 18.0（18.0） | 8 | `packages/rpa_runner/tests/test_tabs.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 1280 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 137.4（120.4） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 119.4（110.0） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 118.8（131.9） | 15 | `apps\server\tests\test_portal.py` |
| 88.2（90.5） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 84.8（90.1） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 64.5（69.0） | 9 | `apps\server\tests\test_production_flow.py` |
| 59.4（59.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.6（56.6） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 36.0（37.6） | 4 | `apps\server\tests\test_replay_flow.py` |
| 30.5（28.1） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 857 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 117.9（119.5） | 15 | `apps\server\tests\test_portal.py` |
| 101.2（101.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 98.1（99.6） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 91.7（93.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 71.3（71.3） | 9 | `apps\server\tests\test_production_flow.py` |
| 63.9（66.5） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 58.7（59.8） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 55.0（55.0） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 37.8（38.1） | 4 | `apps\server\tests\test_replay_flow.py` |
| 26.8（26.3） | 10 | `packages\rpa_runner\tests\test_frames.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-11-04 13:06 America/Los_Angeles（PST，UTC−08:00），合計 855 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 119.9（121.4） | 15 | `apps\server\tests\test_portal.py` |
| 107.2（106.7） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 97.0（97.0） | 16 | `packages\rpa_runner\tests\test_video_browser.py` |
| 89.7（89.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 68.7（68.7） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.8（69.0） | 19 | `packages\rpa_runner\tests\test_debug.py` |
| 58.2（58.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 52.7（52.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 36.8（37.4） | 4 | `apps\server\tests\test_replay_flow.py` |
| 25.9（25.9） | 17 | `packages\rpa_runner\tests\test_upload.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 11-04 13:30 | 一鍵安裝腳本 | 排程 | main | failure | 26.5 分 | 0.1 分 | [#41916641496](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41916641496/attempts/1) |
| 11-04 13:06 | 每晚完整測試 | 排程 | main | failure | 57.2 分 | 0.0 分 | [#41912880655](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41912880655/attempts/1) |
| 11-03 13:24 | 一鍵安裝腳本 | 排程 | main | failure | 22.4 分 | 0.1 分 | [#41721456924](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41721456924/attempts/1) |
| 11-03 13:01 | 每晚完整測試 | 排程 | main | failure | 49.4 分 | 0.1 分 | [#41717981858](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41717981858/attempts/1) |
| 11-02 13:24 | 一鍵安裝腳本 | 排程 | main | failure | 27.9 分 | 0.1 分 | [#41527996629](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41527996629/attempts/1) |
| 11-02 12:57 | 每晚完整測試 | 排程 | main | failure | 52.0 分 | 0.1 分 | [#41523925177](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41523925177/attempts/1) |
| 11-01 13:15 | 一鍵安裝腳本 | 排程 | main | success | 26.6 分 | 0.1 分 | [#41351111726](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41351111726/attempts/1) |
| 11-01 12:51 | 每晚完整測試 | 排程 | main | failure | 58.2 分 | 8.2 分 | [#41349013309](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41349013309/attempts/1) |
| 10-31 16:17 | 每晚完整測試 | 排程 | main | success | 7.2 分 | 0.1 分 | [#41251871759](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41251871759/attempts/1) |
| 10-31 14:14 | 一鍵安裝腳本 | 排程 | main | success | 26.0 分 | 0.1 分 | [#41242687723](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41242687723/attempts/1) |
| 10-31 13:51 | 每晚完整測試 | 排程 | main | failure | 46.6 分 | 0.1 分 | [#41240812130](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41240812130/attempts/1) |
| 10-30 14:17 | 一鍵安裝腳本 | 排程 | main | failure | 25.0 分 | 0.0 分 | [#41129907174](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41129907174/attempts/1) |
| 10-30 13:55 | 每晚完整測試 | 排程 | main | failure | 64.3 分 | 6.6 分 | [#41127092839](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41127092839/attempts/1) |
| 10-30 07:45 | 一鍵安裝腳本 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 0.2 分 | 0.0 分 | [#41074479339](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479339/attempts/1) |
| 10-30 07:45 | CI | PR | dependabot/github_actions/actions-d7d93b8548 | success | 4.8 分 | 0.0 分 | [#41074479301](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479301/attempts/1) |
| 10-30 07:45 | 伺服器分發包 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 6.1 分 | 0.1 分 | [#41074479298](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479298/attempts/1) |
| 10-30 07:45 | 桌面端建置 | PR | dependabot/github_actions/actions-d7d93b8548 | success | 7.0 分 | 0.0 分 | [#41074479437](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479437/attempts/1) |
| 10-30 07:45 | 每晚完整測試 | PR | dependabot/github_actions/actions-d7d93b8548 | failure | 56.8 分 | 0.1 分 | [#41074479686](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41074479686/attempts/1) |
| 10-30 01:55 | 伺服器分發包 | PR | feat/python-nodes | success | 0.3 分 | 0.1 分 | [#41029762241](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762241/attempts/1) |
| 10-30 01:55 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.4 分 | 0.1 分 | [#41029762184](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762184/attempts/1) |
| 10-30 01:55 | CI | PR | feat/python-nodes | success | 2.4 分 | 0.1 分 | [#41029762226](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41029762226/attempts/1) |
| 10-30 01:17 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.1 分 | [#41025469534](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469534/attempts/1) |
| 10-30 01:17 | 伺服器分發包 | PR | feat/python-nodes | success | 3.0 分 | 0.1 分 | [#41025469544](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469544/attempts/1) |
| 10-30 01:17 | 桌面端建置 | PR | feat/python-nodes | success | 3.1 分 | 0.0 分 | [#41025469542](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469542/attempts/1) |
| 10-30 01:17 | CI | PR | feat/python-nodes | success | 4.7 分 | 0.0 分 | [#41025469550](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41025469550/attempts/1) |
| 10-30 00:05 | 桌面端建置 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41017890384](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890384/attempts/1) |
| 10-30 00:05 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.1 分 | [#41017890394](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890394/attempts/1) |
| 10-30 00:05 | CI | PR | feat/python-nodes | success | 2.2 分 | 0.1 分 | [#41017890369](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41017890369/attempts/1) |
| 10-29 23:57 | CI | PR | feat/python-nodes | success | 4.5 分 | 0.1 分 | [#41016235428 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235428/attempts/2) |
| 10-29 23:48 | 桌面端建置 | PR | feat/python-nodes | success | 3.1 分 | 0.0 分 | [#41016235409](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235409/attempts/1) |
| 10-29 23:48 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.3 分 | 0.0 分 | [#41016235505](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235505/attempts/1) |
| 10-29 23:48 | 伺服器分發包 | PR | feat/python-nodes | success | 2.8 分 | 0.1 分 | [#41016235405](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235405/attempts/1) |
| 10-29 23:48 | CI | PR | feat/python-nodes | failure | 7.9 分 | 0.0 分 | [#41016235428](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41016235428/attempts/1) |
| 10-29 23:42 | 桌面端建置 | PR | feat/python-nodes | cancelled | 6.0 分 | 0.1 分 | [#41015618715](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618715/attempts/1) |
| 10-29 23:42 | CI | PR | feat/python-nodes | failure | 4.7 分 | 0.0 分 | [#41015618744](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618744/attempts/1) |
| 10-29 23:42 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41015618635](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618635/attempts/1) |
| 10-29 23:42 | 伺服器分發包 | PR | feat/python-nodes | failure | 2.0 分 | 0.1 分 | [#41015618773](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015618773/attempts/1) |
| 10-29 23:37 | 一鍵安裝腳本 | PR | feat/python-nodes | success | 0.2 分 | 0.0 分 | [#41015158314](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158314/attempts/1) |
| 10-29 23:37 | 伺服器分發包 | PR | feat/python-nodes | failure | 2.0 分 | 0.1 分 | [#41015158337](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158337/attempts/1) |
| 10-29 23:37 | CI | PR | feat/python-nodes | cancelled | 5.4 分 | 0.0 分 | [#41015158302](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/41015158302/attempts/1) |

