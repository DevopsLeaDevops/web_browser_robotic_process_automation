# CI 運行耗時紀錄

更新：2026-10-20 01:36 America/Los_Angeles（PDT，UTC−07:00）。共 22 次運行。

每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；本頁由 `tools/ci_metrics.py report` 產生，不要手改。耗時＝第一個工作建立到最後一個工作結束（含排隊）；機器時間＝各工作實際執行的時間總和。
規則與背景見 main 的 `docs/develop/ci.html`。

## 各流程：近 7 天（前 7 天）

| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 | 機器時間（Linux／Windows／macOS） |
|---|---|---|---|---|---|---|
| CI | 7（0） | 4（0） | 2.7 分（0.0 分） | 3.2 分（0.0 分） | 0.0 分（0.0 分） | 28／15／0 分（0／0／0 分） |
| 桌面端建置 | 8（0） | 4（0） | 3.1 分（0.0 分） | 4.1 分（0.0 分） | 0.1 分（0.0 分） | 1／19／20 分（0／0／0 分） |
| 一鍵安裝腳本 | 7（0） | 5（0） | 2.8 分（0.0 分） | 3.0 分（0.0 分） | 0.1 分（0.0 分） | 18／11／14 分（0／0／0 分） |
| 每晚完整測試 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |
| 發布 | 0（0） | 0（0） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0.0 分（0.0 分） | 0／0／0 分（0／0／0 分） |

## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）

| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |
|---|---|---|---|---|---|
| 2026-10-20 | 19 | 36 | 37 | 27 | 101 |
| 2026-10-19 | 3 | 10 | 8 | 6 | 25 |

## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）

### CI · pytest-report-3.12/pytest-report.xml

最近一次：2026-10-20 01:29 America/Los_Angeles（PDT，UTC−07:00），合計 127 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 14.4（14.5） | 17 | `apps/worker/tests/test_recorder.py` |
| 13.5（13.5） | 14 | `apps/worker/tests/test_gateway.py` |
| 12.7（13.0） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 12.3（13.3） | 24 | `apps/server/tests/test_api.py` |
| 12.2（12.9） | 20 | `apps/server/tests/test_production_api.py` |
| 9.0（9.3） | 14 | `apps/server/tests/test_workflow_api.py` |
| 7.4（7.4） | 27 | `apps/desktop/tests/test_recorder_app.py` |
| 6.5（6.6） | 12 | `apps/worker/tests/test_remote.py` |
| 6.2（5.6） | 17 | `apps/cli/tests/test_serve.py` |
| 5.4（6.3） | 12 | `apps/server/tests/test_recorder_api.py` |

### CI · pytest-report-3.13/pytest-report.xml

最近一次：2026-10-20 01:29 America/Los_Angeles（PDT，UTC−07:00），合計 302 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 48.3（46.2） | 6 | `apps/server/tests/test_portal.py` |
| 34.1（32.3） | 3 | `apps/server/tests/test_workflow_flow.py` |
| 28.0（27.0） | 3 | `apps/server/tests/test_remote_worker_flow.py` |
| 26.4（25.4） | 5 | `apps/server/tests/test_production_flow.py` |
| 21.0（19.9） | 4 | `packages/rpa_runner/tests/test_debug.py` |
| 14.0（13.8） | 14 | `apps/worker/tests/test_gateway.py` |
| 13.9（13.9） | 17 | `apps/worker/tests/test_recorder.py` |
| 11.5（10.7） | 24 | `apps/server/tests/test_api.py` |
| 11.3（11.0） | 20 | `apps/server/tests/test_remote_worker_api.py` |
| 11.3（10.6） | 20 | `apps/server/tests/test_production_api.py` |

### CI · pytest-report-windows/pytest-report.xml

最近一次：2026-10-20 01:29 America/Los_Angeles（PDT，UTC−07:00），合計 400 秒。

| 秒 | 測試數 | 檔案 |
|---|---|---|
| 255.6（229.6） | 11 | `packages\rpa_runner\tests\test_login.py` |
| 97.5（95.1） | 18 | `packages\rpa_runner\tests\test_run.py` |
| 30.0（27.6） | 1 | `packages\rpa_runner\tests\test_profiles.py` |
| 6.8（6.7） | 2 | `tests\smoke\test_browser.py` |
| 6.1（6.1） | 1 | `apps\desktop\tests\test_selftest.py` |
| 3.8（3.8） | 1 | `apps\worker\tests\test_worker.py` |

## 最近 40 次運行

| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |
|---|---|---|---|---|---|---|---|
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
| 10-19 23:44 | 桌面端建置 | 推送 | main | success | 4.2 分 | 0.1 分 | [#39382097547](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39382097547/attempts/1) |
| 10-19 23:44 | CI | 推送 | main | success | 5.2 分 | 0.0 分 | [#39382097480](https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation/actions/runs/39382097480/attempts/1) |

