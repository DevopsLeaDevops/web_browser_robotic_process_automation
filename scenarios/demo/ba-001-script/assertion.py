"""BA-001 的獨立斷言：比對頁面事實與入參，全部符合才寫出候選出參。"""

import argparse
import json
import re
import sys
from pathlib import Path


def verify(params: dict[str, object], facts: dict[str, object]) -> dict[str, object]:
    if not re.fullmatch(r"DEMO-[A-Z0-9]+", str(facts.get("recordId", ""))):
        raise AssertionError("未取得有效的紀錄編號")
    if facts.get("status") != "已建立":
        raise AssertionError("紀錄狀態不是已建立")
    if facts.get("title") != params["title"] or facts.get("quantity") != params["quantity"]:
        raise AssertionError("畫面上的標題或數量與本次入參不符")
    return {key: facts[key] for key in ("recordId", "title", "quantity")}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("input", "facts", "output"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    params = json.loads(Path(args.input).read_text(encoding="utf-8"))
    facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    try:
        output = verify(params, facts)
    except AssertionError as error:
        sys.stderr.write(f"獨立斷言失敗：{error}\n")
        return 1
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
