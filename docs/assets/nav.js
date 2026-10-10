// 文檔站導覽與外殼文字：頂部第一級、左側第二級（依介面設計系統 v1.0 的兩級 Portal）。
// 新增頁面時在這裡登記，名稱同時寫 "zh-Hant" 與 "en"；"zh-Hans" 由 tools/i18n.py sync 自動產生，不要手改。
// href 是相對於該語言根目錄的路徑（繁中在 docs/，其他語言在 docs/<語言>/，目錄結構相同）。
// tests/docs 會檢查每個頁面都已登記、每個連結都存在。等號後面必須是嚴格的 JSON，排版由 tools/i18n.py 固定。
window.DOCS_NAV = {
  "default": "zh-Hant",
  "languages": [
    {"code": "zh-Hant", "label": "繁體中文", "short": "繁"},
    {"code": "zh-Hans", "label": "简体中文", "short": "简"},
    {"code": "en", "label": "English", "short": "EN"}
  ],
  "subtitle": "ENGINEERING DOCS",
  "text": {
    "title": {"zh-Hant": "瀏覽器 RPA", "zh-Hans": "瀏覽器 RPA", "en": "Browser RPA"},
    "badge": {"zh-Hant": "文檔 · M0", "zh-Hans": "文檔 · M0", "en": "Docs · M0"},
    "skip": {"zh-Hant": "跳至主要內容", "zh-Hans": "跳至主要內容", "en": "Skip to main content"},
    "topnav": {"zh-Hant": "第一級選單", "zh-Hans": "第一級選單", "en": "Primary navigation"},
    "sidenav": {"zh-Hant": "第二級選單", "zh-Hans": "第二級選單", "en": "Section navigation"},
    "sideCaption": {"zh-Hant": "本分類頁面", "zh-Hans": "本分類頁面", "en": "In this section"},
    "sideFoot": {
      "zh-Hant": "工程文檔 · 介面設計系統 v1.0",
      "zh-Hans": "工程文檔 · 介面設計系統 v1.0",
      "en": "Engineering docs · Interface design system v1.0"
    },
    "menu": {"zh-Hant": "展開第二級選單", "zh-Hans": "展開第二級選單", "en": "Open section navigation"},
    "crumb": {"zh-Hant": "文檔", "zh-Hans": "文檔", "en": "Docs"},
    "footName": {"zh-Hant": "瀏覽器 RPA 工程文檔", "zh-Hans": "瀏覽器 RPA 工程文檔", "en": "Browser RPA engineering docs"},
    "footNote": {"zh-Hant": "離線可讀", "zh-Hans": "離線可讀", "en": "Readable offline"},
    "language": {"zh-Hant": "語言", "zh-Hans": "語言", "en": "Language"}
  },
  "groups": [
    {
      "id": "overview",
      "caption": "OVERVIEW",
      "name": {"zh-Hant": "總覽", "zh-Hans": "總覽", "en": "Overview"},
      "pages": [
        {"id": "home", "href": "index.html", "name": {"zh-Hant": "首頁", "zh-Hans": "首頁", "en": "Home"}},
        {
          "id": "roadmap",
          "href": "roadmap.html",
          "name": {"zh-Hant": "路線圖", "zh-Hans": "路線圖", "en": "Roadmap"}
        }
      ]
    },
    {
      "id": "design",
      "caption": "DESIGN",
      "name": {"zh-Hant": "設計", "zh-Hans": "設計", "en": "Design"},
      "pages": [
        {
          "id": "positioning",
          "href": "design/positioning.html",
          "name": {"zh-Hant": "產品定位", "zh-Hans": "產品定位", "en": "Positioning"}
        },
        {
          "id": "dsl",
          "href": "design/dsl.html",
          "name": {"zh-Hant": "場景 DSL", "zh-Hans": "場景 DSL", "en": "Scenario DSL"}
        },
        {
          "id": "architecture",
          "href": "design/architecture.html",
          "name": {"zh-Hant": "系統架構", "zh-Hans": "系統架構", "en": "Architecture"}
        },
        {
          "id": "tech-stack",
          "href": "design/tech-stack.html",
          "name": {"zh-Hant": "技術選型", "zh-Hans": "技術選型", "en": "Tech stack"}
        },
        {
          "id": "multi-user",
          "href": "design/multi-user.html",
          "name": {"zh-Hant": "多用戶與內網", "zh-Hans": "多用戶與內網", "en": "Multi-user & intranet"}
        }
      ]
    },
    {
      "id": "adr",
      "caption": "DECISIONS",
      "name": {"zh-Hant": "決策紀錄", "zh-Hans": "決策紀錄", "en": "Decisions"},
      "pages": [
        {
          "id": "adr-index",
          "href": "adr/index.html",
          "name": {"zh-Hant": "決策索引", "zh-Hans": "決策索引", "en": "Decision index"}
        },
        {
          "id": "adr-0001",
          "href": "adr/0001-dsl-as-source-of-truth.html",
          "name": {"zh-Hant": "0001 場景 DSL", "zh-Hans": "0001 場景 DSL", "en": "0001 Scenario DSL"}
        },
        {
          "id": "adr-0002",
          "href": "adr/0002-python-stack.html",
          "name": {"zh-Hant": "0002 Python", "zh-Hans": "0002 Python", "en": "0002 Python"}
        },
        {
          "id": "adr-0003",
          "href": "adr/0003-postgres-queue.html",
          "name": {"zh-Hant": "0003 佇列", "zh-Hans": "0003 佇列", "en": "0003 Queue"}
        },
        {
          "id": "adr-0004",
          "href": "adr/0004-react-frontend.html",
          "name": {"zh-Hant": "0004 前端", "zh-Hans": "0004 前端", "en": "0004 Frontend"}
        },
        {
          "id": "adr-0005",
          "href": "adr/0005-html-docs.html",
          "name": {"zh-Hant": "0005 文檔", "zh-Hans": "0005 文檔", "en": "0005 Docs"}
        },
        {
          "id": "adr-0006",
          "href": "adr/0006-design-system.html",
          "name": {"zh-Hant": "0006 設計包", "zh-Hans": "0006 設計包", "en": "0006 Design system"}
        },
        {
          "id": "adr-0007",
          "href": "adr/0007-i18n.html",
          "name": {"zh-Hant": "0007 多語言", "zh-Hans": "0007 多語言", "en": "0007 Multilingual"}
        }
      ]
    },
    {
      "id": "develop",
      "caption": "DEVELOP",
      "name": {"zh-Hant": "開發", "zh-Hans": "開發", "en": "Develop"},
      "pages": [
        {
          "id": "quickstart",
          "href": "develop/quickstart.html",
          "name": {"zh-Hant": "本機從零運行", "zh-Hans": "本機從零運行", "en": "Run locally"}
        },
        {
          "id": "setup",
          "href": "develop/setup.html",
          "name": {"zh-Hant": "開發環境", "zh-Hans": "開發環境", "en": "Dev environment"}
        },
        {
          "id": "macos",
          "href": "develop/macos.html",
          "name": {"zh-Hant": "macOS 本機運行", "zh-Hans": "macOS 本機運行", "en": "Run on macOS"}
        },
        {
          "id": "conventions",
          "href": "develop/conventions.html",
          "name": {"zh-Hant": "開發規範", "zh-Hans": "開發規範", "en": "Conventions"}
        },
        {
          "id": "writing-docs",
          "href": "develop/writing-docs.html",
          "name": {"zh-Hant": "文檔與 ADR", "zh-Hans": "文檔與 ADR", "en": "Docs & ADRs"}
        }
      ]
    },
    {
      "id": "style",
      "caption": "STYLE",
      "name": {"zh-Hant": "介面風格", "zh-Hans": "介面風格", "en": "Interface style"},
      "pages": [
        {
          "id": "style",
          "href": "style/index.html",
          "name": {"zh-Hant": "風格總覽", "zh-Hans": "風格總覽", "en": "Style overview"}
        }
      ]
    }
  ]
};
