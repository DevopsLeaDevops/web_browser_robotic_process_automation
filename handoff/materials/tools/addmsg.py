"""把新的訊息鍵加到訊息目錄的最後（不重排）：python addmsg.py <locales 目錄> <新訊息.json>

新訊息.json：{"鍵": ["繁中", "English"], ...}。簡中先放繁中的內容，bootstrap 會重新產生。
已經存在的鍵會被更新（位置不變）。
"""

import json
import sys
from pathlib import Path

folder = Path(sys.argv[1])
new = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
for locale, index in (("zh-Hant", 0), ("en", 1), ("zh-Hans", 0)):
    path = folder / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, values in new.items():
        data[key] = values[index]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
sys.stdout.write(f"{len(new)} keys → {folder}\n")
