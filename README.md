# CI 運行耗時紀錄

更新：2026-10-20 07:58 America/Los_Angeles（PDT，UTC−07:00）。共 75 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 34（0） | 23（0） | 2.8 分（0.0 分） | 4.9 分（0.0 分） | 0.0 分（0.0 分） | 141／65／0 分（0／0／0 分） |
| 桌面端建置 | 29（0） | 23（0） | 3.8 分（0.0 分） | 4.1 分（0.0 分） | 0.1 分（0.0 分） | 2／74／74 分（0／0／0 分） |
| 一鍵安裝腳本 | 12（0） | 7（0） | 2.9 分（0.0 分） | 15.2 分（0.0 分） | 0.1 分（0.0 分） | 34／20／17 分（0／0／0 分） |
| 每晚完整測試 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 72 | 167 | 151 | 84 | 402 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 07:56 America/Los_Angeles（PDT，UTC−07:00），合計 164 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 17.2（16.1） | 24 | `apps/server/tests/test_production_api.py` |
| 15.5（15.3） | 24 | `apps/server/tests/test_api.py` |
| 15.0（15.0） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 14.6（14.6） | 17 | `apps/worker/tests/test_recorder.py` |
| 14.0（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.0（13.0） | 14 | `apps/server/tests/test_workflow_api.py` |
| 10.8（10.8） | 16 | `apps/server/tests/test_recorder_api.py` |
| 7.3（7.3） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 7.2（7.5） | 14 | `apps/server/tests/test_packs.py` |
| 6.7（6.7） | 12 | `apps/worker/tests/test_remote.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 07:56 America/Los_Angeles（PDT，UTC−07:00），合計 267 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 38.7（41.7） | 6 | `apps/server/tests/test_portal.py` |
| 27.1（29.4） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 21.2（23.2） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 18.9（21.4） | 5 | `apps/server/tests/test_production_flow.py` |
| 17.1（17.4） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 14.2（13.6） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 11.2（13.4） | 24 | `apps/server/tests/test_production_api.py` |
| 10.1（12.5） | 24 | `apps/server/tests/test_api.py` |
| 9.8（12.6） | 20 | `apps/server/tests/test_remote_worker_api.py` |

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

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
| 10-20 07:56 | CI | PR | fix/linux-setup-mirrors | success | 2.1 分 | 0.0 分 | [#39443848931](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39443848931/attempts/1) |
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

