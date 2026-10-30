"""啟動器：``python -m rpa_script automation.py --input … --facts … [其他參數]``。

Runner 用它啟動運行環境模式的 Python 節點（ADR 0020）：

1. 依參數與環境變數建立這次的 :class:`rpa_script.Run`；主控台輸出遮罩 Secrets 的值。
2. 以 ``__main__`` 執行腳本，``sys.argv`` 與 ``sys.path[0]`` 和直接 ``python automation.py …``
   相同，所以照契約自己讀寫檔案的腳本不必改。
3. 腳本用 ``@automation`` 標出進入點時，接著呼叫它。
4. 不論成敗都寫出 facts.json 與 steps.json（失敗時是已經有的部分）。

結束碼：0 成功；1 自動化失敗（例外、``StepError``）；腳本自己 ``sys.exit`` 的照原樣。
"""

import runpy
import sys
from pathlib import Path

from rpa_script.core import MaskedStream, Run, activate, print_error, registered


def _arguments(argv: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for index, item in enumerate(argv[:-1]):
        if item in ("--input", "--facts"):
            found[item[2:]] = argv[index + 1]
    return found


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: python -m rpa_script SCRIPT [ARGS...]\n")
        return 2
    script = Path(args[0]).resolve()
    options = _arguments(args[1:])
    options["script"] = str(script)
    run = Run.from_environment(options)
    activate(run)
    sys.stdout = MaskedStream(sys.stdout, run)  # pyright: ignore[reportAttributeAccessIssue]
    sys.stderr = MaskedStream(sys.stderr, run)  # pyright: ignore[reportAttributeAccessIssue]
    sys.argv = [str(script), *args[1:]]
    sys.path[0] = str(script.parent)
    code = 0
    try:
        runpy.run_path(str(script), run_name="__main__")
        entry = registered()
        if entry is not None:
            entry(run)
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
        if stop.code is not None and not isinstance(stop.code, int):
            sys.stderr.write(f"{stop.code}\n")
    except BaseException as error:
        if error is not run.step_error:
            run.outside_failure(error)
        print_error(error, script)
        code = 1
    finally:
        run.write_facts()
        sys.stdout.flush()
        sys.stderr.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
