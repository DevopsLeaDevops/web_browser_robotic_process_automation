# CI 運行耗時紀錄

更新：2026-10-21 02:00 America/Los_Angeles（PDT，UTC−07:00）。共 137 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 70（0） | 41（0） | 2.5 分（0.0 分） | 4.7 分（0.0 分） | 0.0 分（0.0 分） | 285／90／0 分（0／0／0 分） |
| 桌面端建置 | 51（0） | 41（0） | 3.9 分（0.0 分） | 4.2 分（0.0 分） | 0.1 分（0.0 分） | 4／141／140 分（0／0／0 分） |
| 一鍵安裝腳本 | 15（0） | 7（0） | 3.0 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 69／47／17 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 39.3 分（0.0 分） | 39.3 分（0.0 分） | 0.0 分（0.0 分） | 36／39／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-21 | 13 | 25 | 35 | 16 | 76 |
| 2026-10-20 | 121 | 359 | 274 | 134 | 767 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-21 01:58 America/Los_Angeles（PDT，UTC−07:00），合計 16 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 16.5（16.5） | 2 | `packages/rpa_runner/tests/test_zz_diag_cancel.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-21 01:58 America/Los_Angeles（PDT，UTC−07:00），合計 18 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 17.9（17.9） | 2 | `packages/rpa_runner/tests/test_zz_diag_cancel.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-21 01:58 America/Los_Angeles（PDT，UTC−07:00），合計 21 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 20.9（20.9） | 2 | `packages\rpa_runner\tests\test_zz_diag_cancel.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.12/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 536 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 65.2（65.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 63.4（63.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 62.4（62.4） | 9 | `apps/server/tests/test_portal.py` |
| 42.7（42.7） | 9 | `apps/server/tests/test_production_flow.py` |
| 42.5（42.5） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 38.8（38.8） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 37.3（37.3） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 16.3（16.3） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 14.1（14.1） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（14.0） | 14 | `apps/worker/tests/test_gateway.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 602 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.2（78.2） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 77.4（77.4） | 9 | `apps/server/tests/test_portal.py` |
| 71.6（71.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 50.4（50.4） | 9 | `apps/server/tests/test_production_flow.py` |
| 47.1（47.1） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 47.0（47.0） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.0（40.0） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 19.5（19.5） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 14.0（14.0） | 14 | `apps/worker/tests/test_gateway.py` |
| 14.0（14.0） | 24 | `apps/server/tests/test_production_api.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-2.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 459 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 83.8（83.8） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 77.4（77.4） | 9 | `apps/server/tests/test_portal.py` |
| 70.6（70.6） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 49.0（49.0） | 9 | `apps/server/tests/test_production_flow.py` |
| 45.5（45.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 40.9（40.9） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 38.9（38.9） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.7（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 13.4（13.4） | 1 | `packages/rpa_runner/tests/test_profiles.py` |
| 13.3（13.3） | 3 | `apps/server/tests/test_flow.py` |

### 每晚完整測試 · test-results-ubuntu-latest-3.13/pass-3.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 450 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 78.7（78.7） | 16 | `packages/rpa_runner/tests/test_login.py` |
| 76.7（76.7） | 9 | `apps/server/tests/test_portal.py` |
| 68.4（68.4） | 6 | `apps/server/tests/test_workflow_flow.py` |
| 48.8（48.8） | 9 | `apps/server/tests/test_production_flow.py` |
| 45.5（45.5） | 5 | `apps/server/tests/test_remote_worker_flow.py` |
| 41.0（41.0） | 18 | `packages/rpa_runner/tests/test_run.py` |
| 38.3（38.3） | 8 | `packages/rpa_runner/tests/test_debug.py` |
| 19.7（19.7） | 4 | `apps/server/tests/test_recorder_flow.py` |
| 13.4（13.4） | 3 | `apps/server/tests/test_flow.py` |
| 13.2（13.2） | 1 | `packages/rpa_runner/tests/test_profiles.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-1.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 934 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 126.3（126.3） | 9 | `apps\server\tests\test_portal.py` |
| 115.2（115.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 99.4（99.4） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 86.1（86.1） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.2（65.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 57.6（57.6） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 55.8（55.8） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 32.2（32.2） | 3 | `apps\server\tests\test_flow.py` |
| 26.9（26.9） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 25.4（25.4） | 20 | `apps\server\tests\test_remote_worker_api.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-2.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 669 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 122.2（122.2） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 112.5（112.5） | 9 | `apps\server\tests\test_portal.py` |
| 103.6（103.6） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 78.8（78.8） | 9 | `apps\server\tests\test_production_flow.py` |
| 67.4（67.4） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 59.5（59.5） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 47.7（47.7） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 29.0（29.0） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 22.4（22.4） | 3 | `apps\server\tests\test_flow.py` |
| 16.1（16.1） | 1 | `packages\rpa_runner\tests\test_profiles.py` |

### 每晚完整測試 · test-results-windows-latest-3.13/pass-3.xml

最近一次：2026-10-20 13:50 America/Los_Angeles（PDT，UTC−07:00），合計 669 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 125.4（125.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 112.7（112.7） | 6 | `apps\server\tests\test_workflow_flow.py` |
| 105.4（105.4） | 9 | `apps\server\tests\test_portal.py` |
| 76.9（76.9） | 9 | `apps\server\tests\test_production_flow.py` |
| 65.2（65.2） | 5 | `apps\server\tests\test_remote_worker_flow.py` |
| 56.9（56.9） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 47.6（47.6） | 8 | `packages\rpa_runner\tests\test_debug.py` |
| 24.7（24.7） | 4 | `apps\server\tests\test_recorder_flow.py` |
| 23.5（23.5） | 3 | `apps\server\tests\test_flow.py` |
| 21.2（21.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-21 01:58 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 1.4 分 | 0.1 分 | [#39573187318](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39573187318/attempts/1) |
| 10-21 01:57 | CI | 手動 | tmp/m12-firefox-video-diag | cancelled | 1.6 分 | 0.1 分 | [#39573149135](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39573149135/attempts/1) |
| 10-21 01:34 | 桌面端建置 | PR | m12/replay | success | 4.0 分 | 0.1 分 | [#39570295082](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39570295082/attempts/1) |
| 10-21 01:27 | CI | PR | m7a/iframe | success | 3.3 分 | 0.0 分 | [#39569174958](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569174958/attempts/1) |
| 10-21 01:27 | 桌面端建置 | PR | m7a/iframe | success | 4.0 分 | 0.1 分 | [#39569174834](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569174834/attempts/1) |
| 10-21 01:25 | CI | PR | m12/replay | failure | 3.5 分 | 0.0 分 | [#39569168145](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569168145/attempts/1) |
| 10-21 01:25 | 桌面端建置 | PR | m12/replay | success | 3.9 分 | 0.1 分 | [#39569168152](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569168152/attempts/1) |
| 10-21 01:25 | CI | PR | m7a/iframe | cancelled | 1.6 分 | 0.0 分 | [#39569144532](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569144532/attempts/1) |
| 10-21 01:25 | 桌面端建置 | PR | m7a/iframe | cancelled | 1.6 分 | 0.1 分 | [#39569144534](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39569144534/attempts/1) |
| 10-21 01:12 | CI | PR | m12/replay | failure | 3.7 分 | 0.0 分 | [#39567535880](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39567535880/attempts/1) |
| 10-21 01:12 | 桌面端建置 | PR | m12/replay | success | 4.0 分 | 0.1 分 | [#39567536044](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39567536044/attempts/1) |
| 10-21 01:06 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 2.1 分 | 0.0 分 | [#39566825305](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39566825305/attempts/1) |
| 10-21 01:02 | CI | 手動 | tmp/m12-firefox-video-diag | failure | 2.3 分 | 0.1 分 | [#39566241679](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39566241679/attempts/1) |
| 10-20 23:20 | CI | 推送 | main | success | 1.4 分 | 0.0 分 | [#39554827230](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39554827230/attempts/1) |
| 10-20 21:48 | CI | PR | m12/replay | failure | 2.6 分 | 0.0 分 | [#39546044758](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39546044758/attempts/1) |
| 10-20 21:48 | 桌面端建置 | PR | m12/replay | success | 4.2 分 | 0.1 分 | [#39546044793](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39546044793/attempts/1) |
| 10-20 21:05 | CI | PR | docs/m11-wrap-up-main | success | 2.5 分 | 0.0 分 | [#39542122137](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39542122137/attempts/1) |
| 10-20 20:47 | CI | PR | docs/m12-replay-design | success | 1.4 分 | 0.0 分 | [#39540532284](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39540532284/attempts/1) |
| 10-20 20:45 | CI | PR | chore/git-history-viewer | success | 2.6 分 | 0.1 分 | [#39540235210](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39540235210/attempts/1) |
| 10-20 20:44 | CI | PR | docs/m12-replay-design | success | 2.7 分 | 0.1 分 | [#39540115533](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39540115533/attempts/1) |
| 10-20 20:43 | CI | PR | chore/git-history-viewer | cancelled | 1.7 分 | 0.0 分 | [#39540143419](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39540143419/attempts/1) |
| 10-20 20:43 | CI | PR | docs/m12-replay-design | cancelled | 1.6 分 | 0.0 分 | [#39540091556](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39540091556/attempts/1) |
| 10-20 20:12 | 桌面端建置 | 推送 | main | success | 4.2 分 | 0.1 分 | [#39537160817](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39537160817/attempts/1) |
| 10-20 20:11 | CI | 推送 | main | success | 5.3 分 | 0.0 分 | [#39537160834](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39537160834/attempts/1) |
| 10-20 20:10 | CI | 推送 | main | cancelled | 1.7 分 | 0.0 分 | [#39537091049](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39537091049/attempts/1) |
| 10-20 20:10 | 桌面端建置 | 推送 | main | cancelled | 1.7 分 | 0.1 分 | [#39537091076](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39537091076/attempts/1) |
| 10-20 19:38 | CI | PR | m11/wrap-up | success | 2.5 分 | 0.0 分 | [#39534166497](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39534166497/attempts/1) |
| 10-20 19:29 | CI | PR | m11/wrap-up | failure | 2.5 分 | 0.0 分 | [#39533286713](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39533286713/attempts/1) |
| 10-20 19:29 | CI | PR | m11/leftovers | success | 2.4 分 | 0.0 分 | [#39533263476](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39533263476/attempts/1) |
| 10-20 19:29 | 桌面端建置 | PR | m11/leftovers | success | 4.2 分 | 0.1 分 | [#39533263523](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39533263523/attempts/1) |
| 10-20 19:24 | CI | PR | m11/leftovers | failure | 2.3 分 | 0.1 分 | [#39532877311](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532877311/attempts/1) |
| 10-20 19:24 | 桌面端建置 | PR | m11/leftovers | success | 4.0 分 | 0.1 分 | [#39532877272](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532877272/attempts/1) |
| 10-20 19:19 | CI | PR | fix/worker-stop-test | success | 3.1 分 | 0.0 分 | [#39532359925](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532359925/attempts/1) |
| 10-20 19:19 | 桌面端建置 | PR | fix/worker-stop-test | success | 4.0 分 | 0.1 分 | [#39532360002](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532360002/attempts/1) |
| 10-20 19:16 | 桌面端建置 | 推送 | main | success | 3.8 分 | 0.1 分 | [#39532105599](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532105599/attempts/1) |
| 10-20 19:16 | CI | 推送 | main | success | 5.3 分 | 0.0 分 | [#39532105515](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39532105515/attempts/1) |
| 10-20 18:11 | 桌面端建置 | PR | m11/git-sync | success | 3.3 分 | 0.0 分 | [#39525059052 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39525059052/attempts/2) |
| 10-20 18:03 | CI | PR | m11/git-sync | success | 2.0 分 | 0.1 分 | [#39525059107](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39525059107/attempts/1) |
| 10-20 18:03 | 桌面端建置 | PR | m11/git-sync | failure | 4.0 分 | 0.1 分 | [#39525059052](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39525059052/attempts/1) |
| 10-20 17:54 | CI | PR | m11/git-sync | failure | 2.5 分 | 0.0 分 | [#39524099794](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39524099794/attempts/1) |

