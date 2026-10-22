# CI 運行耗時紀錄

更新：2026-10-22 14:49 America/Los_Angeles（PDT，UTC−07:00）。共 301 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 149（0） | 81（0） | 2.9 分（0.0 分） | 5.9 分（0.0 分） | 0.0 分（0.0 分） | 706／318／0 分（0／0／0 分） |
| 桌面端建置 | 109（0） | 83（0） | 3.9 分（0.0 分） | 5.2 分（0.0 分） | 0.1 分（0.0 分） | 11／307／283 分（0／0／0 分） |
| 伺服器分發包 | 6（0） | 5（0） | 1.8 分（0.0 分） | 10.3 分（0.0 分） | 0.1 分（0.0 分） | 27／0／0 分（0／0／0 分） |
| 一鍵安裝腳本 | 33（0） | 15（0） | 3.2 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 194／135／35 分（0／0／0 分） |
| 每晚完整測試 | 3（0） | 0（0） | 40.7 分（0.0 分） | 60.2 分（0.0 分） | 0.0 分（0.0 分） | 157／140／0 分（0／0／0 分） |
| 發布 | 1（0） | 1（0） | 5.7 分（0.0 分） | 5.7 分（0.0 分） | 0.1 分（0.0 分） | 1／5／4 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-22 | 91 | 432 | 305 | 84 | 821 |
| 2026-10-21 | 86 | 295 | 318 | 97 | 711 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-22 08:19 America/Los_Angeles（PDT，UTC−07:00），合計 414 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 43.6（31.0） | 29 | `apps/server/tests/test_api.py` |
| 42.6（28.3） | 24 | `apps/server/tests/test_production_api.py` |
| 41.4（28.2） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 34.3（22.5） | 20 | `apps/server/tests/test_recorder_api.py` |
| 31.1（19.7） | 11 | `apps/server/tests/test_gitsync.py` |
| 22.0（10.0） | 12 | `apps/server/tests/test_replay.py` |
| 22.0（13.3） | 9 | `apps/server/tests/test_videos.py` |
| 20.1（13.0） | 14 | `apps/server/tests/test_workflow_api.py` |
| 15.4（14.7） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.4（11.8） | 6 | `apps/server/tests/test_composites.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-22 08:19 America/Los_Angeles（PDT，UTC−07:00），合計 813 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 115.5（113.0） | 7 | `apps/server/tests/test_portal.py` |
| 82.7（82.7） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 65.8（65.5） | 5 | `apps/server/tests/test_production_flow.py` |
| 65.1（62.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 54.6（54.6） | 2 | `apps/server/tests/test_replay_flow.py` |
| 37.6（34.2） | 29 | `apps/server/tests/test_api.py` |
| 37.2（34.5） | 24 | `apps/server/tests/test_production_api.py` |
| 36.4（34.9） | 22 | `apps/server/tests/test_remote_worker_api.py` |
| 33.0（31.9） | 5 | `packages/rpa_runner/tests/test_debug.py` |
| 31.2（26.8） | 11 | `apps/server/tests/test_gitsync.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-22 08:19 America/Los_Angeles（PDT，UTC−07:00），合計 1160 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 401.4（393.9） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 232.7（173.0） | 10 | `packages\rpa_runner\tests\test_frames.py` |
| 187.5（178.6） | 14 | `packages\rpa_runner\tests\test_video_browser.py` |
| 183.5（153.7） | 20 | `packages\rpa_runner\tests\test_run.py` |
| 81.2（60.1） | 8 | `packages\rpa_runner\tests\test_tabs.py` |
| 53.6（53.8） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 8.0（8.8） | 2 | `tests\smoke\test_browser.py` |
| 7.6（4.8） | 1 | `apps\desktop\tests\test_selftest.py` |
| 4.5（3.9） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-22 07:57 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | failure | 15.2 分 | 0.1 分 | [#39800058860](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800058860/attempts/1) |
| 10-22 07:55 | 一鍵安裝腳本 | PR | claude/project-thread-ab62tv | cancelled | 1.6 分 | 0.1 分 | [#39800025722](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025722/attempts/1) |
| 10-22 07:55 | 伺服器分發包 | PR | claude/project-thread-ab62tv | cancelled | 0.0 分 | 0.0 分 | [#39800025740](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025740/attempts/1) |
| 10-22 07:55 | CI | PR | claude/project-thread-ab62tv | cancelled | 1.7 分 | 0.1 分 | [#39800025834](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025834/attempts/1) |
| 10-22 07:55 | 桌面端建置 | PR | claude/project-thread-ab62tv | cancelled | 1.7 分 | 0.0 分 | [#39800025261](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39800025261/attempts/1) |
| 10-22 07:33 | CI | 推送 | main | failure | 13.3 分 | 0.1 分 | [#39796583943](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796583943/attempts/1) |
| 10-22 07:33 | 桌面端建置 | 推送 | main | success | 3.4 分 | 0.0 分 | [#39796583661](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796583661/attempts/1) |
| 10-22 07:32 | 伺服器分發包 | 推送 | main | success | 1.9 分 | 0.1 分 | [#39796582221](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796582221/attempts/1) |
| 10-22 07:32 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 3.6 分 | 0.0 分 | [#39796459340](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459340/attempts/1) |
| 10-22 07:32 | CI | PR | claude/project-thread-ab62tv | failure | 6.7 分 | 0.0 分 | [#39796459295](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459295/attempts/1) |
| 10-22 07:32 | 伺服器分發包 | PR | claude/project-thread-ab62tv | success | 10.3 分 | 0.1 分 | [#39796459275](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39796459275/attempts/1) |
| 10-22 07:29 | CI | 推送 | main | cancelled | 4.3 分 | 0.0 分 | [#39795916099](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795916099/attempts/1) |
| 10-22 07:28 | 桌面端建置 | 推送 | main | cancelled | 0.2 分 | 0.0 分 | [#39795916087](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795916087/attempts/1) |
| 10-22 07:26 | CI | PR | feat/macos-worker | failure | 5.0 分 | 0.0 分 | [#39795568711](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795568711/attempts/1) |
| 10-22 07:24 | CI | PR | feat/macos-worker | cancelled | 0.0 分 | 0.0 分 | [#39795465612](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795465612/attempts/1) |
| 10-22 07:24 | 桌面端建置 | PR | feat/macos-worker | cancelled | 1.7 分 | 0.0 分 | [#39795465789](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39795465789/attempts/1) |
| 10-22 07:18 | 伺服器分發包 | 推送 | main | success | 0.1 分 | 0.0 分 | [#39794604622](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604622/attempts/1) |
| 10-22 07:18 | 一鍵安裝腳本 | 推送 | main | failure | 1.3 分 | 4.0 分 | [#39794604600](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604600/attempts/1) |
| 10-22 07:18 | 桌面端建置 | 推送 | main | success | 3.7 分 | 0.0 分 | [#39794604647](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604647/attempts/1) |
| 10-22 07:18 | CI | 推送 | main | cancelled | 10.5 分 | 0.1 分 | [#39794604795](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39794604795/attempts/1) |
| 10-22 06:49 | 桌面端建置 | PR | feat/macos-worker | success | 0.2 分 | 0.1 分 | [#39790298065](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39790298065/attempts/1) |
| 10-22 06:49 | CI | PR | feat/macos-worker | success | 2.5 分 | 0.1 分 | [#39790297868](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39790297868/attempts/1) |
| 10-22 06:43 | 桌面端建置 | PR | claude/project-thread-ab62tv | success | 3.9 分 | 0.0 分 | [#39789364884](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39789364884/attempts/1) |
| 10-22 06:43 | CI | PR | claude/project-thread-ab62tv | failure | 13.2 分 | 0.1 分 | [#39789364904](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39789364904/attempts/1) |
| 10-22 06:35 | CI | PR | feat/macos-worker | success | 12.9 分 | 0.0 分 | [#39785688742 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785688742/attempts/2) |
| 10-22 06:26 | CI | PR | feat/linux-server-package | success | 1.4 分 | 0.0 分 | [#39786831412](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39786831412/attempts/1) |
| 10-22 06:19 | 桌面端建置 | PR | feat/macos-worker | success | 5.3 分 | 0.1 分 | [#39785688647](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39785688647/attempts/1) |

