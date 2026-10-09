# 瀏覽器 RPA

瀏覽器自動化場景的生成、管理與執行平台。團隊共用、多用戶、面向內部系統。

> 文檔以 HTML 撰寫，放在 [`docs/`](docs/)（見 [ADR 0005](docs/adr/0005-html-docs.html)）。
> GitHub 上只能看到原始碼，請在本機開啟 `docs/index.html`，或執行：
>
> ```bash
> python -m http.server -d docs 8000   # 然後瀏覽 http://localhost:8000
> ```

## 快速開始

```bash
uv sync                              # 安裝全部套件與開發工具
uv run playwright install chromium   # 下載瀏覽器
uv run pytest                        # 跑測試
uv run rpa --version
```

完整說明見 `docs/develop/setup.html`。

## 目前進度

M0：工程骨架與設計文件。路線圖見 `docs/roadmap.html`。
