# CI 運行耗時紀錄

更新：2026-10-20 07:21 America/Los_Angeles（PDT，UTC−07:00）。共 67 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 29（0） | 19（0） | 2.7 分（0.0 分） | 3.4 分（0.0 分） | 0.0 分（0.0 分） | 107／54／0 分（0／0／0 分） |
| 桌面端建置 | 26（0） | 21（0） | 3.8 分（0.0 分） | 4.1 分（0.0 分） | 0.1 分（0.0 分） | 2／63／63 分（0／0／0 分） |
| 一鍵安裝腳本 | 12（0） | 7（0） | 2.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 34／20／17 分（0／0／0 分） |
| 每晚完整測試 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 64 | 133 | 128 | 73 | 334 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 07:17 America/Los_Angeles（PDT，UTC−07:00），合計 153 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 16.1（14.6） | 24 | `apps/server/tests/test_production_api.py` |
| 15.1（14.7） | 24 | `apps/server/tests/test_api.py` |
| 14.9（14.6） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 14.0（14.5） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 11.4（11.2） | 14 | `apps/server/tests/test_workflow_api.py` |
| 9.9（8.2） | 16 | `apps/server/tests/test_recorder_api.py` |
| 6.9（6.5） | 14 | `apps/server/tests/test_packs.py` |
| 6.9（7.3） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 6.7（6.6） | 12 | `apps/worker/tests/test_remote.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 07:17 America/Los_Angeles（PDT，UTC−07:00），合計 261 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 39.2（43.9） | 6 | `apps/server/tests/test_portal.py` |
| 26.8（29.6） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 21.3（23.6） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 20.0（23.4） | 5 | `apps/server/tests/test_production_flow.py` |
| 16.5（18.2） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 10.3（8.6） | 2 | `apps/server/tests/test_recorder_flow.py` |
| 10.1（12.1） | 24 | `apps/server/tests/test_production_api.py` |
| 9.2（11.6） | 24 | `apps/server/tests/test_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-20 07:17 America/Los_Angeles（PDT，UTC−07:00），合計 376 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 247.4（244.8） | 14 | `packages\rpa_runner\tests\test_login.py` |
| 90.5（94.7） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 23.6（28.1） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.7（6.7） | 2 | `tests\smoke\test_browser.py` |
| 5.9（4.7） | 1 | `apps\desktop\tests\test_selftest.py` |
| 2.1（3.1） | 1 | `apps\worker\tests\test_worker.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-20 07:17 | 桌面端建置 | 推送 | main | success | 3.6 分 | 0.1 分 | [#39437870292](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437870292/attempts/1) |
| 10-20 07:17 | CI | PR | m11/domain-packs | success | 2.9 分 | 0.0 分 | [#39437854127](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39437854127/attempts/1) |
| 10-20 06:42 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.5 分 | 0.1 分 | [#39432681104](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39432681104/attempts/1) |
| 10-20 06:42 | CI | PR | fix/linux-setup-mirrors | success | 1.1 分 | 0.0 分 | [#39432681166](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39432681166/attempts/1) |
| 10-20 06:25 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.0 分 | 0.0 分 | [#39428051091 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051091/attempts/2) |
| 10-20 06:09 | CI | PR | fix/linux-setup-mirrors | success | 2.3 分 | 0.1 分 | [#39428051105](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051105/attempts/1) |
| 10-20 06:09 | 一鍵安裝腳本 | PR | fix/linux-setup-mirrors | failure | 15.2 分 | 0.0 分 | [#39428051091](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39428051091/attempts/1) |
| 10-20 06:07 | 桌面端建置 | PR | fix/firefox-background-login | success | 0.1 分 | 0.0 分 | [#39427677841](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39427677841/attempts/1) |
| 10-20 06:07 | CI | PR | fix/firefox-background-login | success | 1.1 分 | 0.0 分 | [#39427677897](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39427677897/attempts/1) |
| 10-20 05:59 | CI | PR | fix/firefox-background-login | success | 2.4 分 | 0.0 分 | [#39426565078](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39426565078/attempts/1) |
| 10-20 05:59 | 桌面端建置 | PR | fix/firefox-background-login | success | 3.8 分 | 0.1 分 | [#39426564960](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39426564960/attempts/1) |
| 10-20 05:54 | 桌面端建置 | PR | m11/composite-packs | success | 0.1 分 | 0.0 分 | [#39426003000](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39426003000/attempts/1) |
| 10-20 05:54 | CI | PR | m11/composite-packs | success | 1.3 分 | 0.0 分 | [#39426003030](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39426003030/attempts/1) |
| 10-20 05:46 | CI | PR | m11/composite-packs | success | 3.0 分 | 0.0 分 | [#39424750458](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424750458/attempts/1) |
| 10-20 05:45 | 桌面端建置 | PR | m11/composite-packs | success | 3.9 分 | 0.1 分 | [#39424750588](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424750588/attempts/1) |
| 10-20 05:45 | CI | PR | m11/composite-packs | cancelled | 1.7 分 | 0.1 分 | [#39424704707](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424704707/attempts/1) |
| 10-20 05:41 | CI | PR | m11/composite-packs | failure | 2.8 分 | 0.0 分 | [#39424287391](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424287391/attempts/1) |
| 10-20 05:41 | 桌面端建置 | PR | m11/composite-packs | cancelled | 3.9 分 | 0.1 分 | [#39424287412](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424287412/attempts/1) |
| 10-20 05:40 | 桌面端建置 | 推送 | main | success | 4.3 分 | 0.1 分 | [#39424148002](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424148002/attempts/1) |
| 10-20 05:40 | CI | 推送 | main | success | 4.9 分 | 0.0 分 | [#39424147964](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39424147964/attempts/1) |
| 10-20 05:37 | 桌面端建置 | PR | fix/login-check-on-device | success | 0.1 分 | 0.0 分 | [#39423708760](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39423708760/attempts/1) |
| 10-20 05:37 | CI | PR | fix/login-check-on-device | success | 1.1 分 | 0.0 分 | [#39423708791](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39423708791/attempts/1) |
| 10-20 05:33 | CI | PR | m11/composite-packs | failure | 3.4 分 | 0.0 分 | [#39423242212](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39423242212/attempts/1) |
| 10-20 05:33 | 桌面端建置 | PR | m11/composite-packs | success | 4.1 分 | 0.1 分 | [#39423242172](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39423242172/attempts/1) |
| 10-20 05:33 | CI | PR | fix/login-check-on-device | success | 2.7 分 | 0.0 分 | [#39422382519 第 2 次](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39422382519/attempts/2) |
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

