# CI 運行耗時紀錄

更新：2026-10-20 18:05 America/Los_Angeles（PDT，UTC−07:00）。共 99 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 46（0） | 30（0） | 2.6 分（0.0 分） | 4.7 分（0.0 分） | 0.0 分（0.0 分） | 192／65／0 分（0／0／0 分） |
| 桌面端建置 | 37（0） | 30（0） | 3.8 分（0.0 分） | 4.2 分（0.0 分） | 0.1 分（0.0 分） | 3／97／94 分（0／0／0 分） |
| 一鍵安裝腳本 | 15（0） | 7（0） | 3.0 分（0.0 分） | 15.5 分（0.0 分） | 0.1 分（0.0 分） | 69／47／17 分（0／0／0 分） |
| 每晚完整測試 | 1（0） | 0（0） | 39.3 分（0.0 分） | 39.3 分（0.0 分） | 0.0 分（0.0 分） | 36／39／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 96 | 290 | 240 | 104 | 633 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 18:03 America/Los_Angeles（PDT，UTC−07:00），合計 183 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 18.2（17.1） | 24 | `apps/server/tests/test_production_api.py` |
| 17.6（15.6） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 16.8（15.5） | 24 | `apps/server/tests/test_api.py` |
| 14.6（14.5） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.6（13.8） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.2（13.2） | 14 | `apps/server/tests/test_workflow_api.py` |
| 11.4（10.6） | 16 | `apps/server/tests/test_recorder_api.py` |
| 8.3（8.3） | 14 | `apps/server/tests/test_packs.py` |
| 8.0（7.6） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 7.7（5.8） | 9 | `apps/server/tests/test_gitsync.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 18:03 America/Los_Angeles（PDT，UTC−07:00），合計 257 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 37.1（50.3） | 6 | `apps/server/tests/test_portal.py` |
| 25.5（33.8） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 19.7（26.5） | 5 | `apps/server/tests/test_production_flow.py` |
| 18.9（27.9） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 16.2（20.0） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 13.8（14.0） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.0（13.1） | 14 | `apps/worker/tests/test_gateway.py` |
| 9.5（14.2） | 24 | `apps/server/tests/test_production_api.py` |
| 8.8（13.3） | 24 | `apps/server/tests/test_api.py` |
| 8.2（12.7） | 20 | `apps/server/tests/test_remote_worker_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-20 07:38 America/Los_Angeles（PDT，UTC−07:00），合計 405 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 285.5（247.4） | 16 | `packages\rpa_runner\tests\test_login.py` |
| 77.5（92.4） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 27.4（29.2） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 5.8（5.0） | 1 | `apps\desktop\tests\test_selftest.py` |
| 4.5（6.7） | 2 | `tests\smoke\test_browser.py` |
| 4.3（3.1） | 1 | `apps\worker\tests\test_worker.py` |

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
| 10-20 18:03 | CI | PR | m11/git-sync | success | 2.0 分 | 0.1 分 | [#39525059107](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39525059107/attempts/1) |
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
| 10-20 07:17 | 桌面端建置 | 推送 | main | success | 3.6 分 | 0.1 分 | [#39437870292](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437870292/attempts/1) |
| 10-20 07:17 | CI | 推送 | main | success | 5.1 分 | 0.1 分 | [#39437870326](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437870326/attempts/1) |
| 10-20 07:17 | CI | PR | m11/domain-packs | success | 2.9 分 | 0.0 分 | [#39437854127](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437854127/attempts/1) |
| 10-20 07:17 | 桌面端建置 | PR | m11/domain-packs | success | 3.8 分 | 0.1 分 | [#39437851137](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437851137/attempts/1) |
| 10-20 06:42 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.5 分 | 0.1 分 | [#39432681104](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39432681104/attempts/1) |
| 10-20 06:42 | CI | PR | fix/linux-setup-mirrors | success | 1.1 分 | 0.0 分 | [#39432681166](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39432681166/attempts/1) |
| 10-20 06:25 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.0 分 | 0.0 分 | [#39428051091 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051091/attempts/2) |
| 10-20 06:09 | CI | PR | fix/linux-setup-mirrors | success | 2.3 分 | 0.1 分 | [#39428051105](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051105/attempts/1) |
| 10-20 06:09 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.2 分 | 0.0 分 | [#39428051091](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051091/attempts/1) |
| 10-20 06:07 | 桌面端建置 | PR | fix/firefox-background-login | success | 0.1 分 | 0.0 分 | [#39427677841](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39427677841/attempts/1) |

