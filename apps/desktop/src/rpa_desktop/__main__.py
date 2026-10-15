"""``python -m rpa_desktop``，也是 PyInstaller 的入口腳本。"""

from rpa_desktop.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
