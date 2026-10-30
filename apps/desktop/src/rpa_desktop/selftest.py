"""自我測試（M10.0）：證明打包後的 App 真的能下載瀏覽器、執行場景。CI 建好 App 後執行一次。

    App --self-test [--report 檔案] [--engine chromium] [--skip-install]

1. 用 App 內附的 Playwright driver 下載瀏覽器（``playwright install``；已經下載過就很快）。
   CI 把 ``PLAYWRIGHT_BROWSERS_PATH`` 指到全新的資料夾，確定是打包後的 driver 下載的。
2. 在背景啟動測試網站（隨機埠）。
3. 以無頭模式執行 BA-001（DSL 場景，子程序走 ``--rpa-module``）與它的 Python 腳本版
   （走 ``--rpa-script``），兩個都要「通過」。
4. RPA Worker 再執行範例 Python 節點（ADR 0020，運行環境模式）：從 App 附帶的壓縮檔解壓
   RPA Python 運行環境（已經解壓過就沿用），用 pandas、openpyxl 合併出一份 Excel。
   開發環境找得到運行環境（例如 ``tools/build_python_runtime.py build --install``）時也執行。
5. 以 JSON 印出摘要（``--report`` 另外寫一份檔案）；全部成功才回傳 0。

範例場景：打包後在 App 裡（``rpa_desktop/scenarios``，建置時從 ``scenarios/demo`` 與
``scenarios/examples/python-node`` 複製）；開發環境直接用倉庫裡的。
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from rpa_desktop.build_info import load, shell_file
from rpa_runner.commands import is_frozen, playwright_command
from rpa_runner.pyruntime import ENV_RUNTIME, available_versions
from rpa_runner.run import execute
from testsite.server import running

__all__ = [
    "BUNDLED_SCENARIOS",
    "PYTHON_NODES",
    "SCENARIOS",
    "main",
    "python_nodes",
    "scenario_root",
]

SCENARIOS: Final = ("ba-001.yaml", "ba-001-script/scenario.yaml")
"""要執行的範例場景（相對於範例資料夾）：DSL 場景與 Python 腳本場景各一。"""
PYTHON_NODES: Final = ("python-node/scenario.yaml",)
"""RPA Worker 另外執行的範例 Python 節點（運行環境模式，ADR 0020）。"""
BUNDLED_SCENARIOS: Final = "scenarios"
"""打包時範例場景放在 rpa_desktop 套件資料夾內的這個子資料夾。"""
INSTALL_SECONDS: Final = 900
_TAIL: Final = 2000


def scenario_root() -> Path:
    """範例場景的資料夾：App 裡的那份，沒有就用倉庫的 scenarios/demo。"""
    bundled = shell_file(BUNDLED_SCENARIOS)
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[4] / "scenarios" / "demo"


def python_node_root() -> Path:
    """範例 Python 節點的資料夾：App 裡和其他範例放在一起，開發環境是 scenarios/examples。"""
    bundled = shell_file(BUNDLED_SCENARIOS)
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[4] / "scenarios" / "examples"


def python_nodes(app: str, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """要執行的範例 Python 節點：RPA Worker 一定要（附帶運行環境）；錄製端不執行；開發環境
    找得到 RPA Python 運行環境 1 才執行。"""
    if app == "worker":
        return PYTHON_NODES
    if app != "development":
        return ()
    env = os.environ if environ is None else environ
    found = bool(env.get(ENV_RUNTIME)) or any(
        version.split(".")[0] == "1" for version in available_versions(env)
    )
    return PYTHON_NODES if found else ()


def _install(engine: str) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            playwright_command(["install", engine]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=INSTALL_SECONDS,
            check=False,
        )
        ok, code, output = completed.returncode == 0, completed.returncode, completed.stdout
        output += completed.stderr
    except subprocess.TimeoutExpired:
        ok, code, output = False, None, f"timed out after {INSTALL_SECONDS}s"
    return {
        "step": "install",
        "engine": engine,
        "ok": ok,
        "exitCode": code,
        "seconds": round(time.monotonic() - started, 1),
        "output": output[-_TAIL:],
    }


def _run(path: Path, url: str | None, out: Path, engine: str | None) -> dict[str, object]:
    started = time.monotonic()
    try:
        result = execute(path, {}, out_root=out, base_url=url, engine=engine, headed=False)
    except Exception as error:  # 場景本身有問題、或子程序根本起不來：一樣記下來、判定失敗
        return {
            "step": "run",
            "scenario": path.name,
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
            "seconds": round(time.monotonic() - started, 1),
        }
    summary: dict[str, object] = {
        "step": "run",
        "scenario": result.scenario_id,
        "ok": result.status == "passed",
        "status": result.status,
        "error": result.error,
        "seconds": round(time.monotonic() - started, 1),
    }
    if result.python is not None:
        summary["python"] = result.python
    return summary


def run_self_test(engine: str = "chromium", *, install: bool = True) -> dict[str, object]:
    """執行自我測試，回傳摘要（``ok`` 是全部成功與否）。"""
    steps: list[dict[str, object]] = []
    if install:
        steps.append(_install(engine))
    root = scenario_root()
    build = load()
    if all(step["ok"] for step in steps):
        with running() as url, tempfile.TemporaryDirectory(prefix="rpa-self-test-") as folder:
            for relative in SCENARIOS:
                steps.append(_run(root / relative, url, Path(folder), engine))
            for relative in python_nodes(build.app):
                steps.append(_run(python_node_root() / relative, None, Path(folder), None))
    return {
        "ok": bool(steps) and all(step["ok"] for step in steps) and len(steps) > int(install),
        "frozen": is_frozen(),
        "build": build.to_json(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "scenarios": str(root),
        "steps": steps,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(prog="--self-test")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--engine", choices=["chromium", "firefox"], default="chromium")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args(list(argv))
    summary = run_self_test(args.engine, install=not args.skip_install)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if summary["ok"] else 1
