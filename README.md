# 瀏覽器 RPA

瀏覽器自動化場景的生成、管理與執行平台。團隊共用、多用戶、面向內部系統。

> 文檔以 HTML 撰寫，放在 [`docs/`](docs/)（見 [ADR 0005](docs/adr/0005-html-docs.html)），有三種語言：
> 繁體中文 `docs/index.html`、简体中文 `docs/zh-Hans/index.html`、English `docs/en/index.html`。
> GitHub 上只能看到原始碼，請在本機直接開啟，或執行：
>
> ```bash
> uv run python -m http.server -d docs 8000   # 然後瀏覽 http://localhost:8000（英文版在 /en/）
> ```

## 快速開始

一條命令裝好環境並跑完測試（macOS、Linux；Windows 用 `scripts\setup.ps1`），說明見 `docs/develop/quickstart.html`：

```bash
./scripts/setup.sh
```

或手動執行：

```bash
uv sync                              # 安裝全部套件與開發工具
uv run playwright install chromium   # 下載瀏覽器
uv run pytest                        # 跑測試
uv run rpa --version
```

完整說明見 `docs/develop/setup.html`；在 Mac 上從零開始的逐步說明見 `docs/develop/macos.html`。

## 目前進度

M0 工程骨架已完成，下一步是 M1（DSL v0）。路線圖見 `docs/roadmap.html`。
