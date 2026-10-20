# CI 運行耗時紀錄

更新：2026-10-20 05:31 America/Los_Angeles（PDT，UTC−07:00）。共 42 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 16（0） | 9（0） | 3.0 分（0.0 分） | 4.7 分（0.0 分） | 0.0 分（0.0 分） | 61／33／0 分（0／0／0 分） |
| 桌面端建置 | 17（0） | 13（0） | 3.8 分（0.0 分） | 4.1 分（0.0 分） | 0.1 分（0.0 分） | 1／41／42 分（0／0／0 分） |
| 一鍵安裝腳本 | 9（0） | 7（0） | 2.8 分（0.0 分） | 3.0 分（0.0 分） | 0.1 分（0.0 分） | 21／13／17 分（0／0／0 分） |
| 每晚完整測試 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 39 | 74 | 79 | 52 | 204 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 05:27 America/Los_Angeles（PDT，UTC−07:00），合計 128 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 14.4（14.5） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.2（14.3） | 24 | `apps/server/tests/test_production_api.py` |
| 12.1（14.7） | 24 | `apps/server/tests/test_api.py` |
| 11.9（15.1） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 9.3（10.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 7.8（7.8） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 6.8（6.7） | 16 | `apps/server/tests/test_recorder_api.py` |
| 6.6（6.6） | 12 | `apps/worker/tests/test_remote.py` |
| 6.3（6.5） | 17 | `apps/cli/tests/test_serve.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 05:27 America/Los_Angeles（PDT，UTC−07:00），合計 269 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 42.0（47.4） | 6 | `apps/server/tests/test_portal.py` |
| 28.7（33.9） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 22.9（26.5） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 22.3（25.2） | 5 | `apps/server/tests/test_production_flow.py` |
| 16.5（20.2） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 13.8（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.4（11.5） | 24 | `apps/server/tests/test_production_api.py` |
| 11.1（11.6） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 11.1（11.9） | 24 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-20 05:27 America/Los_Angeles（PDT，UTC−07:00），合計 508 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 336.9（265.5） | 14 | `packages\rpa_runner\tests\test_login.py` |
| 114.7（103.0） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 43.7（30.6） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.1（6.1） | 2 | `tests\smoke\test_browser.py` |
| 4.0（6.2） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.8（3.8） | 1 | `apps\worker\tests\test_worker.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-20 05:27 | CI | PR | fix/login-check-on-device | failure | 3.4 分 | 0.0 分 | [#39422382519](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39422382519/attempts/1) |
| 10-20 05:27 | 桌面端建置 | PR | fix/login-check-on-device | success | 3.8 分 | 0.1 分 | [#39422382496](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39422382496/attempts/1) |
| 10-20 05:25 | CI | PR | m11/composite-packs | failure | 3.1 分 | 0.0 分 | [#39422190617](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39422190617/attempts/1) |
| 10-20 05:25 | 桌面端建置 | PR | m11/composite-packs | success | 3.9 分 | 0.1 分 | [#39422190515](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39422190515/attempts/1) |
| 10-20 05:20 | CI | PR | m11/composite-packs | failure | 3.0 分 | 0.1 分 | [#39421549993](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39421549993/attempts/1) |
| 10-20 05:20 | 桌面端建置 | PR | m11/composite-packs | success | 4.2 分 | 0.1 分 | [#39421549998](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39421549998/attempts/1) |
| 10-20 04:59 | 桌面端建置 | PR | m11/domain-packs | success | 0.1 分 | 0.0 分 | [#39418876575](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39418876575/attempts/1) |
| 10-20 04:59 | CI | PR | m11/domain-packs | success | 1.2 分 | 0.0 分 | [#39418876605](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39418876605/attempts/1) |
| 10-20 04:49 | 桌面端建置 | PR | m11/domain-packs | success | 0.1 分 | 0.0 分 | [#39417668051](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39417668051/attempts/1) |
| 10-20 04:49 | CI | PR | m11/domain-packs | success | 1.2 分 | 0.1 分 | [#39417668017](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39417668017/attempts/1) |
| 10-20 04:43 | CI | PR | m11/domain-packs | success | 3.3 分 | 0.0 分 | [#39417042583](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39417042583/attempts/1) |
| 10-20 04:43 | 桌面端建置 | PR | m11/domain-packs | success | 3.8 分 | 0.1 分 | [#39417042561](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39417042561/attempts/1) |
| 10-20 04:38 | CI | PR | m11/domain-packs | failure | 3.1 分 | 0.0 分 | [#39416377357](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39416377357/attempts/1) |
| 10-20 04:38 | 桌面端建置 | PR | m11/domain-packs | success | 4.0 分 | 0.1 分 | [#39416377341](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39416377341/attempts/1) |
| 10-20 01:39 | 一鍵安裝腳本 | 推送 | main | success | 2.9 分 | 0.1 分 | [#39394980793](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394980793/attempts/1) |
| 10-20 01:39 | 桌面端建置 | 推送 | main | success | 4.0 分 | 0.1 分 | [#39394980783](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394980783/attempts/1) |
| 10-20 01:39 | CI | 推送 | main | success | 4.7 分 | 0.0 分 | [#39394980731](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394980731/attempts/1) |
| 10-20 01:37 | 一鍵安裝腳本 | PR | fix/headless-server-hints | success | 0.1 分 | 0.0 分 | [#39394748492](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394748492/attempts/1) |
| 10-20 01:37 | 桌面端建置 | PR | fix/headless-server-hints | success | 0.1 分 | 0.0 分 | [#39394748689](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394748689/attempts/1) |
| 10-20 01:37 | CI | PR | fix/headless-server-hints | success | 1.2 分 | 0.0 分 | [#39394748866](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39394748866/attempts/1) |
| 10-20 01:33 | 桌面端建置 | PR | fix/headless-server-hints | success | 2.8 分 | 0.0 分 | [#39393763887 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393763887/attempts/2) |
| 10-20 01:30 | 桌面端建置 | PR | fix/headless-server-hints | failure | 3.4 分 | 0.1 分 | [#39393763887](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393763887/attempts/1) |
| 10-20 01:29 | 一鍵安裝腳本 | PR | fix/headless-server-hints | success | 3.0 分 | 0.2 分 | [#39393764073](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393764073/attempts/1) |
| 10-20 01:29 | CI | PR | fix/headless-server-hints | success | 3.2 分 | 0.0 分 | [#39393764042](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393764042/attempts/1) |
| 10-20 01:26 | CI | PR | fix/headless-server-hints | failure | 2.4 分 | 0.0 分 | [#39393375958](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393375958/attempts/1) |
| 10-20 01:26 | 一鍵安裝腳本 | PR | fix/headless-server-hints | success | 2.8 分 | 0.1 分 | [#39393375767](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393375767/attempts/1) |
| 10-20 01:26 | 桌面端建置 | PR | fix/headless-server-hints | cancelled | 4.1 分 | 0.1 分 | [#39393375761](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39393375761/attempts/1) |
| 10-20 00:52 | 桌面端建置 | PR | fix/headless-server-hints | success | 0.1 分 | 0.0 分 | [#39389432896](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39389432896/attempts/1) |
| 10-20 00:52 | 一鍵安裝腳本 | PR | fix/headless-server-hints | success | 0.1 分 | 0.0 分 | [#39389432880](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39389432880/attempts/1) |
| 10-20 00:52 | CI | PR | fix/headless-server-hints | success | 1.1 分 | 0.1 分 | [#39389432933](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39389432933/attempts/1) |
| 10-20 00:47 | 桌面端建置 | PR | fix/headless-server-hints | success | 4.1 分 | 0.1 分 | [#39388669854](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388669854/attempts/1) |
| 10-20 00:46 | CI | PR | fix/headless-server-hints | success | 3.0 分 | 0.0 分 | [#39388669893](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388669893/attempts/1) |
| 10-20 00:46 | 一鍵安裝腳本 | PR | fix/headless-server-hints | success | 3.2 分 | 0.1 分 | [#39388669978](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388669978/attempts/1) |
| 10-20 00:44 | 一鍵安裝腳本 | PR | fix/headless-server-hints | cancelled | 2.1 分 | 0.1 分 | [#39388406946](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388406946/attempts/1) |
| 10-20 00:44 | 桌面端建置 | PR | fix/headless-server-hints | cancelled | 2.9 分 | 0.1 分 | [#39388407063](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388407063/attempts/1) |
| 10-20 00:44 | CI | PR | fix/headless-server-hints | cancelled | 2.7 分 | 0.1 分 | [#39388406958](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388406958/attempts/1) |
| 10-20 00:42 | CI | PR | fix/headless-server-hints | cancelled | 1.7 分 | 0.0 分 | [#39388291182](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388291182/attempts/1) |
| 10-20 00:42 | 桌面端建置 | PR | fix/headless-server-hints | cancelled | 1.8 分 | 0.1 分 | [#39388291278](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388291278/attempts/1) |
| 10-20 00:42 | 一鍵安裝腳本 | PR | fix/headless-server-hints | cancelled | 1.9 分 | 0.2 分 | [#39388291167](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39388291167/attempts/1) |
| 10-19 23:44 | 一鍵安裝腳本 | 推送 | main | success | 2.8 分 | 0.1 分 | [#39382097492](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39382097492/attempts/1) |

