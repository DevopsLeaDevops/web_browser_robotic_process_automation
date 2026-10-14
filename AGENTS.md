# Claude 與 ChatGPT／Codex 共用入口

本檔適用整個倉庫。Claude 與 ChatGPT／Codex 使用同一份協作規則；`CLAUDE.md` 只負責導向本檔。

## 開始任何修改前

1. 讀 [共用協作流程](handoff/collaboration.html)，這是現行協作流程的唯一維護位置。
2. 讀 [交接總入口](handoff/index.html)、[任務索引](handoff/tasks/index.html)，以及本次任務的交接紀錄。先接續既有任務，避免重複開工。
3. 檢查 `git status --short --branch`、`git log -5 --oneline`、`git worktree list`；連線可用時 `git fetch origin`，核對目標分支、PR、基準與最新提交。讀取權限不足時如實記錄。
4. 按任務需要讀 [決定](handoff/decisions.html)、[未完成工作](handoff/open-work.html)、[驗收](handoff/acceptance.html)、[環境](handoff/environment.html) 及相關 ADR／程式碼。
5. 實作遵循 [開發規範](docs/develop/conventions.html) 與 [文檔、多語言規則](docs/develop/writing-docs.html)。

## 執行摘要

- 以使用者當前需求與仍有效的授權為準；已授權的工作持續完成，不因切換模型而重複詢問。尚未決定的產品事項不得寫成已確認。
- 一個任務一個主責、一個實作分支、一份 `handoff/tasks/` 紀錄。同一分支同時只由一方寫入；並行任務使用獨立 checkout／worktree 並約定檔案範圍。任務紀錄是協調資訊，不是自動鎖。
- 保留他人未提交的修改。不要直接在 `main` 開發，不覆蓋或強推他人的分支；歷史重寫先交接寫入權並按共用流程驗證。
- 程式註解、提交摘要、工程文檔用繁體中文；對話跟隨使用者當前語言。產品與正式文檔維持繁中、英文、簡中，簡中由工具產生。
- 產品設計、API、資料庫、多語言與設計系統規則沿用現有規範。原始提案與舊環境操作是歷史資料，不代表目前實作或現在可以略過檢查。
- 驗證必須記錄版本、命令、環境、結果與缺口。區分本地測試、CI、人工驗收；未跑、跳過、取消不算通過。
- 每個實作任務在開工、交接、提交 PR／合併狀態變化時更新任務紀錄。只有本機可見的修改要明確標示；接收方取得同一版本並回填接收結果後，才算交接完成。
- 推送與 PR 依本次使用者授權執行；已有授權不重問，授權不明且確需外部寫入時，先完成可供審閱的成果再確認。合併預設由使用者負責；AI review 作為審閱證據，不自行代替使用者的合併決定。
- 不將 token、Secrets、登入狀態、業務資料或私人對話全文寫入交接檔案。記錄必要的結論、來源與安全的取得方式。

## 快速定位

- [任務範本](handoff/tasks/_template.html)：交接欄位、驗證紀錄、接收確認。
- [Claude 先前的操作歷史](handoff/workflow.html)：解釋 bootstrap、rebase 與環境限制，不作為新的環境豁免。
- [原始材料索引](handoff/materials.html)：保留歷史原文；新的決定與工作紀錄直接進倉庫。

純問答或只讀查詢不必建立任務卡；新功能、修復、流程修改或跨會話接力才需要。
