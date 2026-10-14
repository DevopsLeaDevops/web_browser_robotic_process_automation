# M6 自由試驗場：設計與實作（2026-10-13，已實作，待使用者驗收）

使用者指示（10-12 23:56）：M4 視為完成，**順序改為先做 M6，再做 M5**；繼續做、不要中途詢問。所以這份不是「待確認」的提案，而是已經照推薦選項實作的設計，決定列在最後，有意見再改。

依據：路線圖 v2 的 M6（已發布場景排成序列、固定版本、出參綁定、失敗即停）、MVP 原型「自由試驗場」（場景庫 → 序列 → 節點設定、匯出編排 JSON、沒有前置出參時執行前攔截）、原型建置指引的驗收清單（「編排下游只收到上游成功出參，前置失敗立即停止」）。

驗收：原型的試驗場流程（BA-001 → BA-002，recordId 綁定上游出參）在 Chromium 與 Firefox 真實執行通過；上游失敗時下游不執行。

## 一、序列的定義（rpa_core.workflow）

```json
{"version": 1, "mode": "serial", "onFailure": "stop",
 "nodes": [
   {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "試驗"}}},
   {"id": "n2", "sceneId": "ba-002", "revision": 1,
    "inputs": {"recordId": {"node": "n1", "output": "recordId"}}}]}
```

- 入參來源三選一：不寫 = 場景預設值；`{"value": …}` 固定值；`{"node", "output"}` 前面節點通過後發布的出參。
- 和原型的差異：原型寫 `'${node-1.output.recordId}'` 字串；改成結構化，才能在執行前檢查順序、出參存在、型別相容。
- 靜態檢查（`check_workflow`）：取自後面的節點、節點不存在、出參不存在、型別不相容（整數可給數字）、必填入參沒有來源、固定值不符合入參規則、序列是空的。
- 執行時取值（`resolve_inputs`）：上游沒通過或沒有那個出參就回報；綁定的值再由 `check_inputs` 校驗（不符合就不啟動瀏覽器）。
- 訊息在 rpa_core 的 `dsl.workflow.*`。

## 二、管理 Portal

- 資料：`workflows`（名稱、說明、定義 JSON、version＝存檔次數）、`workflow_runs`（定義快照、狀態、failed_node、reused、resumed_from、idempotency_key…）；`runs` 加 `workflow_run_id`（外鍵）與 `node_id`。遷移 0006。
- 節點的執行 = 一般的執行，目的 `workflow`（執行報告的「試驗場」），用序列固定的版本；只能是發布過的版本（`revisions.published_at` 有值），否則 409 `revision_unpublished`。
- 推進：`RunQueue.on_finished` → `Services.run_finished` → `WorkflowService.node_finished`；排隊中被取消也會通知。只處理序列執行裡最新的節點執行（重複通知不會排兩次）；同一把鎖。
- 失敗即停：節點狀態不是 passed（failed／timed_out／cancelled／needs_login）→ 序列執行停在那個節點，後面 skipped；綁定的值不符合規則 → 節點不開始，狀態 failed。
- 從停下的節點繼續：沿用前面已通過節點的執行（reused），不重複有副作用的操作；從頭再執行：同一份快照。
- 伺服器重啟：Services.recover 把中斷的執行標為失敗後，WorkflowService.recover 依最新節點的狀態接著處理。
- API：`/api/workflows`（清單、新增＝匯入、library、check、取得、PUT 存檔 baseVersion→409、刪除）、`/api/workflows/{id}/runs`、`/api/workflow-runs`（清單、取得、cancel、rerun resume）。
- 頁面：`/playground`（清單、最近的序列執行、新增、匯入 JSON、刪除）、`/playground/{id}`（設計系統的 flow-layout：場景庫｜序列｜節點設定；名稱相同、型別相容的入參自動接上最近的上游；改動即時檢查；儲存、執行（先自動存檔）、匯出 JSON）、`/playground/runs/{id}`（節點、入參值與來源、出參、報告；取消、從頭、從停下的節點繼續；每秒輪詢）。節點的執行頁連回序列執行，不顯示單獨的「重新執行」。
- 頁面的 JavaScript 文字放在 `wfjs.*`，只在試驗場頁面輸出（不加進每頁的 js_messages）。
- 移除 placeholder.html 與 `placeholder.*` 訊息。

## 三、測試

- rpa_core：`test_workflow.py`（格式、靜態檢查、取值、英文訊息）— 本機可跑。
- 伺服器（假的執行器、不開瀏覽器）：`test_workflow_api.py` — 存檔與 409、檢查、依序執行、失敗即停、需要登入後繼續、綁定的值不符合規則、取消、不能執行的情況、固定版本、重啟回復。
- 真實瀏覽器：`test_workflow_flow.py`（Chromium、Firefox：BA-001 → BA-002 通過；BA-002 查不存在的紀錄在前，後面的 BA-001 不執行）；`test_portal.py::test_playground_chains_published_scenarios`（在頁面上新增序列、自動接上 recordId、改固定值、執行到通過）。
- 樣板：`test_render.py` 的 M6 頁面（三種語言、英文沒有殘留中文）。

## 四、已採用的決定（有意見再改）

1. 入參綁定用結構化寫法（不是原型的 `${…}` 字串）。
2. 序列的定義可以存有問題的草稿（編輯到一半），但有問題不能執行。
3. 節點只能固定發布過的版本；場景發布新版本不自動升級，頁面提示。
4. 節點與其他執行共用同一個佇列（序列中的下一個節點排在佇列最後）。
5. 「從停下的節點繼續」沿用前面節點的出參（新增），「從頭再執行」用同一份快照。
6. 瀏覽器、視窗模式在執行序列時選，整個序列一樣；網址用各場景的設定。
7. MVP 不做條件、分支、平行、資料驅動（M7）。
