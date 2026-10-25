"""rpa_update：分層更新（ADR 0018）。

只用標準函式庫，而且跟著執行環境走（伺服器的 runtimes/、桌面 App 的外殼），不放進更新檔：
驗證更新檔的程式與信任的公鑰都不會被更新檔換掉。它的原始碼一改，環境代號就跟著改。

- :mod:`rpa_update.ed25519`：簽章與驗證（RFC 8032）
- :mod:`rpa_update.manifest`：更新檔的清單、讀取、解開與核對
- :mod:`rpa_update.runtime`：執行環境與環境代號
- :mod:`rpa_update.keys`：發布用的公鑰
"""
