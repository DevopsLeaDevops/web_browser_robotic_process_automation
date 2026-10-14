# 方案 v2 提案：結合 MVP 原型與原方案（2026-10-10，待確認）

來源：使用者上傳的「02-browser-automation-mvp」（HTML 離線原型 + python-demo 真實 Playwright 範例 + contracts/ + sample-run/）。
原型的 portal.css、shell.js 與倉庫 docs/design-system 的完全相同（設計系統 v1.0）。

## 一、兩份方案的對照與 v2 取捨

| 面向 | 原方案（M0 文件） | MVP 原型 | v2 採用 |
|---|---|---|---|
| 場景表示 | 聲明式 YAML DSL（ADR 0001） | 每個場景 automation.py + assertion.py | DSL 為主；Python 腳本為受控逃生門；兩者共用同一份場景契約（待決定） |
| 成功判定 | 步驟內的 expect | 獨立斷言比對 facts 與入參，通過才發布出參 | 採用原型：steps → facts → verify → outputs |
| 入參／出參 | params（型別、預設值） | JSON Schema 入參、出參、預設值、樣例 | inputs / outputs，支援常用 JSON Schema 限制；啟動瀏覽器前校驗 |
| 版本 | 不可變版本 | 草稿 → 驗證中 → 通過／失敗 → 已發布；驗證版本＝發布版本（雜湊） | 採用原型的發布門檻 |
| 執行 | 無狀態 Runner、worker 佇列 | 子程序 + 單調時鐘總期限 + 程序群組終止；有副作用的動作不自動重試 | 結合：worker 以子程序跑 Runner；總期限、取消；重試只用於無副作用步驟 |
| 產物 | 截圖、Trace、日誌 | input/facts/output.json、截圖、log、腳本快照、result.json、report.html | 採用原型的執行目錄契約，加上 Trace |
| 生成 | 錄製 → DSL；AI 自然語言 → DSL | 原始錄製稿 → 助手對話調試 → 真實驗證 → 人工發布 | 錄製與 AI 都只產生草稿，走同一條驗證、發布流程；助手工具受限 |
| 組合 | 子場景（原 M3） | 自由試驗場：序列、出參綁定、失敗停止 | 編排 Workflow：先做序列、固定版本 |
| 登入 | storage state 重用（原 M3） | 每角色獨立 Context；needs_login → 人工重新登入；credentialRef | 採用原型，納入 MVP |
| 介面 | React + TS（ADR 0004）；頁面原型待做（原 M6） | 頂部一級／左側二級 Portal，設計系統 v1.0 | 原型就是頁面原型；技術待決定 |
| 後端 | FastAPI + PostgreSQL + Procrastinate + S3 | Flask + SQLite + 檔案目錄；單機、單使用者、序列 | MVP 單機 SQLite + 檔案目錄（ADR 0008 已允許）；之後擴充 |
| 多用戶 | 原 M7 | 非目標 | 移到 MVP 之後 |
| 語言 | 三種 | 只有繁中 | 維持三種（已建好） |
| 瀏覽器 | Chromium | Firefox | 待決定 |

原型明確的 MVP 非目標：任意 DAG、分散式叢集、多租戶權限、跨環境排程。

## 二、v2 核心模型：場景契約

```
場景 Scenario（穩定 id、分類、預設網址）
 └ 版本 Revision（不可變、雜湊；草稿→驗證中→通過/失敗→已發布）
     ├ inputs   入參 Schema + 預設值（啟動瀏覽器前校驗）
     ├ steps    自動化步驟（DSL）── 或 script: automation.py（逃生門）
     ├ facts    執行中 extract 的頁面事實（不是宣稱成功）
     ├ verify   獨立斷言：比對 facts 與 inputs ── 或 script: assertion.py
     └ outputs  出參 Schema + 從 facts 取值；verify 通過才發布 output.json
執行 Run：queued → running → passed / failed / timed_out / cancelled / needs_login
編排 Workflow：固定版本的場景序列，上游出參綁到下游入參，失敗即停
執行目錄：input.json、facts.json、output.json、screenshot.png、*.log、scenario 快照、trace.zip、result.json、report.html
```

## 三、新路線圖（提案）

| 階段 | 名稱 | 內容 | 驗收 |
|---|---|---|---|
| M0 | 工程骨架 | 已完成（需小修） | |
| M1 | DSL v0 | 已完成（#8 已合併，需補契約） | |
| M1.1 | 場景契約 | inputs / outputs / verify / deadline / category；範例移到 scenarios/；原型 BA-001、BA-002 的 DSL 版；匯入原型到 docs/prototypes/mvp/；文檔與 ADR 改為 v2 | rpa validate 通過 BA-001、BA-002 |
| M2 | Runner 與執行契約 | 子程序執行、總期限、取消、執行目錄與 report.html、測試網站（沿用原型 target）、rpa run；（若採用）Python 腳本場景 | BA-001 → BA-002 真實串聯；原型 5 個回歸情境 |
| M3 | 管理 Portal | 伺服器 + SQLite + 背景 worker；場景卡片、版本與發布門檻、入出參編輯、執行、報告篩選 | 瀏覽器內完成 建立→驗證→發布→執行→看報告 |
| M4 | 場景生產與登入 | 原始錄製稿 → DSL 草稿 → 調試工作階段（隔離瀏覽器）→ 候選驗證 → 人工發布；credentialRef、每角色 storageState、needs_login | 錄製後發布並執行成功；兩個角色隔離 |
| M5 | AI 助手 | 對話調試、受限工具、自然語言生成、校驗失敗自動修正、選擇器自癒 | 助手只改草稿；一句話生成可驗證的場景 |
| M6 | 自由試驗場 | 序列編排、固定版本、出參綁定、失敗停止 | 原型試驗場流程以真實執行跑通 |
| —— | MVP 完成 | | |
| M7 | 流程能力 | 條件、迴圈、重試（僅無副作用）、iframe、分頁、上傳下載、子場景、資料驅動 | 複雜範例通過 |
| M8 | 多用戶與治理 | 認證（OIDC／LDAP）、專案權限、Secrets 加密、稽核、PostgreSQL | API 測試在 SQLite 與 PostgreSQL 都通過 |
| M9 | 營運 | 分散式 worker、排程、通知、S3、Docker Compose | docker compose up |

原 M6（頁面原型）由 MVP 原型交付；原 M8（Web UI）拆進 M3～M6，每階段交付自己的頁面。

## 四、M0、M1 要修正的地方

M1（DSL）：
1. params 改名 inputs，支援 minLength、maxLength、pattern、minimum、maximum、enum；可匯出單一場景的入參 JSON Schema
2. 新增 outputs（Schema + from）與 verify（獨立斷言）；extract 結果放在 facts 命名空間
3. 新增 deadline（整次執行總期限，毫秒）；defaults.timeout 保留為單步預設
4. 新增 category（分類，報告篩選用）
5. examples/ 移到 scenarios/（architecture.html 寫的是 scenarios/，目前不一致），加入 BA-001、BA-002 的 DSL 版
6. {{ }} 引用檢查擴充到 inputs、facts（extract 的 as 要在引用之前）
7. （依決定）script 逃生門：automation / assertion 用原型的命令列契約

M0（文件與工程）：
1. 產品定位的核心概念、架構（MVP 單機拓撲）、路線圖、技術選型、多用戶頁改為 v2
2. 新 ADR：場景契約與獨立斷言；MVP 先行的範圍；Web 技術選擇（ADR 0004 改為已取代或延後）
3. 匯入原型到 docs/prototypes/mvp/，比照設計系統用 MANIFEST 檢查、不翻譯
4. 若支援 Firefox：CI 與冒煙測試加 Firefox
5. 固定一個手動觸發的 bootstrap workflow（產生 uv.lock 與簡中），取代每次加了又刪的暫時 workflow（雲端環境連不到 PyPI）
6. main 上 Dependabot 的 uv 群組更新失敗（看不到日誌），要查原因

## 五、待使用者決定

1. 場景表示：DSL 為主＋Python 逃生門（推薦）／只用 DSL／以 Python 腳本為主
2. Web 技術：FastAPI + Jinja 伺服器端渲染（推薦）／Flask + Jinja（原型任務書）／FastAPI + React（原方案）
3. 瀏覽器：Chromium 與 Firefox 都支援、CI 都測（推薦）／Firefox 為主／Chromium 為主
4. 路線圖與 M0、M1 修正是否照提案
