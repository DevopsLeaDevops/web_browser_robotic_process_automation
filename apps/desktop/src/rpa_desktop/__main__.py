"""``python -m rpa_desktop``。

打包後由啟動器 :mod:`rpa_update.boot` 選好程式碼層，再執行這裡（ADR 0018）。
"""

from rpa_desktop.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
