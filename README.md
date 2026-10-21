# CI 運行耗時紀錄

更新：2026-10-20 19:32 America/Los_Angeles（PDT，UTC−07:00）。共 109 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 51（0） | 33（0） | 2.6 分（0.0 分） | 4.9 分（0.0 分） | 0.0 分（0.0 分） | 216／68／0 分（0／0／0 分） |
| 桌面端建置 | 42（0） | 34（0） | 3.9 分（0.0 分） | 4.2 分（0.0 分） | 0.1 分（0.0 分） | 4／111／112 分（0／0／0 分） |
| 一鍵安裝腳本 | 15（0） | 7（0） | 3.0 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 69／47／17 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 39.3 分（0.0 分） | 39.3 分（0.0 分） | 0.0 分（0.0 分） | 36／39／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 106 | 314 | 257 | 122 | 693 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 19:29 America/Los_Angeles（PDT，UTC−07:00），合計 188 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 19.1（18.2） | 24 | `apps/server/tests/test_production_api.py` |
| 17.5（16.7） | 24 | `apps/server/tests/test_api.py` |
| 17.2（16.7） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 14.6（14.6） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.1（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.0（13.0） | 14 | `apps/server/tests/test_workflow_api.py` |
| 11.7（11.1） | 16 | `apps/server/tests/test_recorder_api.py` |
| 11.0（10.3） | 11 | `apps/server/tests/test_gitsync.py` |
| 7.7（7.7） | 14 | `apps/server/tests/test_packs.py` |
| 7.4（7.4） | 27 | `apps/desktop/tests/test_recorder_app.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 19:29 America/Los_Angeles（PDT，UTC−07:00），合計 348 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 48.2（44.2） | 6 | `apps/server/tests/test_portal.py` |
| 35.6（29.0） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 27.6（22.6） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 25.0（21.7） | 5 | `apps/server/tests/test_production_flow.py` |
| 18.9（17.8） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 14.3（14.1） | 24 | `apps/server/tests/test_production_api.py` |
| 14.1（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.5（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 12.7（12.7） | 24 | `apps/server/tests/test_api.py` |
| 12.6（10.2） | 14 | `apps/server/tests/test_workflow_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-20 19:19 America/Los_Angeles（PDT，UTC−07:00），合計 430 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 272.0（255.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 102.9（92.4） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 41.0（30.9） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 7.1（6.7） | 2 | `tests\smoke\test_browser.py` |
| 4.1（3.8） | 1 | `apps\worker\tests\test_worker.py` |
| 2.9（5.0） | 1 | `apps\desktop\tests\test_selftest.py` |

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
| 10-20 19:29 | CI | PR | m11/wrap-up | failure | 2.5 分 | 0.0 分 | [#39533286713](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39533286713/attempts/1) |
| 10-20 19:29 | CI | PR | m11/leftovers | success | 2.4 分 | 0.0 分 | [#39533263476](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39533263476/attempts/1) |
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
| 10-20 17:54 | 桌面端建置 | PR | m11/git-sync | success | 4.2 分 | 0.1 分 | [#39524099784](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39524099784/attempts/1) |
| 10-20 17:45 | 桌面端建置 | PR | m11/git-sync | success | 0.1 分 | 0.0 分 | [#39523252238](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39523252238/attempts/1) |
| 10-20 17:45 | CI | PR | m11/git-sync | success | 1.3 分 | 0.1 分 | [#39523252240](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39523252240/attempts/1) |
| 10-20 17:41 | CI | PR | m11/git-sync | success | 1.2 分 | 0.1 分 | [#39459275810 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39459275810/attempts/2) |
| 10-20 17:39 | 桌面端建置 | 推送 | main | success | 3.9 分 | 0.1 分 | [#39522608943](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39522608943/attempts/1) |
| 10-20 17:39 | CI | 推送 | main | success | 4.2 分 | 0.0 分 | [#39522608958](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39522608958/attempts/1) |
| 10-20 14:11 | 一鍵安裝腳本 | 排程 | main | failure | 17.1 分 | 0.1 分 | [#39498314752](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39498314752/attempts/1) |
| 10-20 13:50 | 每晚完整測試 | 排程 | main | failure | 39.3 分 | 0.0 分 | [#39495466237](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39495466237/attempts/1) |
| 10-20 09:38 | 桌面端建置 | PR | m11/git-sync | success | 0.1 分 | 0.0 分 | [#39459275827](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39459275827/attempts/1) |
| 10-20 09:38 | CI | PR | m11/git-sync | failure | 1.4 分 | 0.0 分 | [#39459275810](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39459275810/attempts/1) |
| 10-20 09:30 | CI | PR | m11/git-sync | success | 2.6 分 | 0.1 分 | [#39457969054](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39457969054/attempts/1) |
| 10-20 09:30 | 桌面端建置 | PR | m11/git-sync | success | 3.9 分 | 0.1 分 | [#39457969192](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39457969192/attempts/1) |
| 10-20 09:21 | CI | PR | m11/git-sync | failure | 2.5 分 | 0.0 分 | [#39456734127](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39456734127/attempts/1) |
| 10-20 09:21 | 桌面端建置 | PR | m11/git-sync | success | 3.9 分 | 0.1 分 | [#39456734081](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39456734081/attempts/1) |
| 10-20 09:14 | CI | PR | fix/sqlite-migration-fk | success | 2.2 分 | 0.0 分 | [#39455614661](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39455614661/attempts/1) |
| 10-20 09:14 | 桌面端建置 | PR | fix/sqlite-migration-fk | success | 3.7 分 | 0.1 分 | [#39455614641](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39455614641/attempts/1) |
| 10-20 09:10 | CI | PR | m11/git-sync | failure | 2.6 分 | 0.0 分 | [#39455076333](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39455076333/attempts/1) |
| 10-20 09:10 | 桌面端建置 | PR | m11/git-sync | failure | 4.5 分 | 0.1 分 | [#39455076337](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39455076337/attempts/1) |
| 10-20 09:09 | CI | PR | fix/sqlite-migration-fk | failure | 2.4 分 | 0.1 分 | [#39454917465](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39454917465/attempts/1) |
| 10-20 08:18 | CI | 推送 | main | success | 5.2 分 | 0.0 分 | [#39447249830](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39447249830/attempts/1) |
| 10-20 08:18 | 一鍵安裝腳本 | 推送 | main | failure | 15.2 分 | 0.1 分 | [#39447249863](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39447249863/attempts/1) |
| 10-20 07:56 | CI | PR | fix/linux-setup-mirrors | success | 2.1 分 | 0.0 分 | [#39443848931](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39443848931/attempts/1) |
| 10-20 07:56 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.1 分 | 0.1 分 | [#39443849384](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39443849384/attempts/1) |
| 10-20 07:38 | 桌面端建置 | 推送 | main | success | 4.0 分 | 0.1 分 | [#39441058633](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39441058633/attempts/1) |
| 10-20 07:38 | CI | 推送 | main | success | 4.7 分 | 0.1 分 | [#39441058561](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39441058561/attempts/1) |
| 10-20 07:34 | CI | 推送 | main | cancelled | 3.9 分 | 0.1 分 | [#39440514776](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39440514776/attempts/1) |
| 10-20 07:34 | 桌面端建置 | 推送 | main | cancelled | 4.0 分 | 0.1 分 | [#39440514735](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39440514735/attempts/1) |
| 10-20 07:34 | CI | 手動 | m11/composite-packs | success | 5.4 分 | 0.0 分 | [#39440416565](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39440416565/attempts/1) |

