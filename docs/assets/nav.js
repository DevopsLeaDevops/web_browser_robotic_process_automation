// 文檔站導覽：頂部第一級、左側第二級（依介面設計系統 v1.0 的兩級 Portal）。
// 新增頁面時在這裡登記；tests/docs 會檢查每個頁面都已登記、每個連結都存在。
// 等號後面必須是嚴格的 JSON（測試會直接解析）。
window.DOCS_NAV = {
  "title": "瀏覽器 RPA",
  "subtitle": "ENGINEERING DOCS",
  "badge": "文檔 · M0",
  "groups": [
    {
      "id": "overview", "name": "總覽", "en": "OVERVIEW",
      "pages": [
        { "id": "home", "name": "首頁", "href": "index.html" },
        { "id": "roadmap", "name": "路線圖", "href": "roadmap.html" }
      ]
    },
    {
      "id": "design", "name": "設計", "en": "DESIGN",
      "pages": [
        { "id": "positioning", "name": "產品定位", "href": "design/positioning.html" },
        { "id": "dsl", "name": "場景 DSL", "href": "design/dsl.html" },
        { "id": "architecture", "name": "系統架構", "href": "design/architecture.html" },
        { "id": "tech-stack", "name": "技術選型", "href": "design/tech-stack.html" },
        { "id": "multi-user", "name": "多用戶與內網", "href": "design/multi-user.html" }
      ]
    },
    {
      "id": "adr", "name": "決策紀錄", "en": "DECISIONS",
      "pages": [
        { "id": "adr-index", "name": "決策索引", "href": "adr/index.html" },
        { "id": "adr-0001", "name": "0001 場景 DSL", "href": "adr/0001-dsl-as-source-of-truth.html" },
        { "id": "adr-0002", "name": "0002 Python", "href": "adr/0002-python-stack.html" },
        { "id": "adr-0003", "name": "0003 佇列", "href": "adr/0003-postgres-queue.html" },
        { "id": "adr-0004", "name": "0004 前端", "href": "adr/0004-react-frontend.html" },
        { "id": "adr-0005", "name": "0005 文檔", "href": "adr/0005-html-docs.html" },
        { "id": "adr-0006", "name": "0006 設計包", "href": "adr/0006-design-system.html" }
      ]
    },
    {
      "id": "develop", "name": "開發", "en": "DEVELOP",
      "pages": [
        { "id": "quickstart", "name": "本機從零運行", "href": "develop/quickstart.html" },
        { "id": "setup", "name": "開發環境", "href": "develop/setup.html" },
        { "id": "macos", "name": "macOS 本機運行", "href": "develop/macos.html" },
        { "id": "conventions", "name": "開發規範", "href": "develop/conventions.html" },
        { "id": "writing-docs", "name": "文檔與 ADR", "href": "develop/writing-docs.html" }
      ]
    },
    {
      "id": "style", "name": "介面風格", "en": "STYLE",
      "pages": [
        { "id": "style", "name": "風格總覽", "href": "style/index.html" }
      ]
    }
  ]
};
