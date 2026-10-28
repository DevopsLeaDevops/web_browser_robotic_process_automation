"""把 pytest 與 pyright 的錯誤轉成 GitHub Actions 的 annotations。

CI 失敗時，原因直接標在 PR「Files changed」的對應行上；看不到 Actions 日誌的環境
（例如雲端開發環境）也能從 check run 的 annotations API 讀到完整的錯誤。

用法（CI 裡在測試或檢查之後執行）::

    uv run python tools/ci_annotations.py junit pytest-report.xml
    uv run python tools/ci_annotations.py pyright pyright.json
    uv run python tools/ci_annotations.py self-test self-test.json [self-test.log]

pytest 要用 ``--junitxml=… -o junit_family=xunit1``（xunit1 才有 file、line 屬性）；
pyright 要用 ``--outputjson``。self-test 是桌面 App 自我測試的報告（rpa_desktop.selftest，M10；
視窗自我測試與端到端也是同一種格式），失敗的每一步一則；報告沒有產生時，改用輸出日誌的最後一段。
全部通過時一則 notice，步驟有 ``detail`` 的話一併列出（例如 WebView2 的 User-Agent、權杖存在哪裡）。

GitHub 每個步驟最多顯示 10 個錯誤 annotation，所以 pytest 一個失敗的測試一則、
pyright 一個檔案一則，超過的部分合併成最後一則。

JUnit 報告有耗時資料時，另外一則 notice 列出測試時間總和、最慢的檔案與最慢的測試，
不下載日誌或報告也能看出時間花在哪裡。
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

LIMIT: Final = 10
"""GitHub 每個步驟顯示的錯誤 annotation 上限。"""

DETAIL_CHARS: Final = 4000
"""每則 annotation 保留的錯誤內容長度（保留結尾：斷言與例外通常在最後）。

GitHub 只保留 annotation 訊息的前 4096 個字元，超過的結尾直接截掉；保留的長度要在這之內，
否則最後的斷言與例外反而看不到（2026-10-27，組合運行回看的瀏覽器測試）。"""

SLOWEST: Final = 15
"""耗時摘要列出幾個最慢的檔案與測試。"""


@dataclass(frozen=True, slots=True)
class Annotation:
    title: str
    message: str
    file: str | None = None
    line: int | None = None
    col: int | None = None

    def command(self) -> str:
        properties = [f"title={_escape_property(self.title)}"]
        if self.file:
            properties.append(f"file={_escape_property(self.file)}")
        if self.line:
            properties.append(f"line={self.line}")
        if self.col:
            properties.append(f"col={self.col}")
        return f"::error {','.join(properties)}::{_escape_data(self.message)}"


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _tail(text: str, chars: int = DETAIL_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= chars else "…\n" + text[-chars:]


def _relative(path: str) -> str:
    root = Path(os.environ.get("GITHUB_WORKSPACE") or Path.cwd())
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def limit(annotations: Sequence[Annotation], title: str) -> list[Annotation]:
    """超過上限時，把多出來的合併成最後一則。"""
    if len(annotations) <= LIMIT:
        return list(annotations)
    kept = list(annotations[: LIMIT - 1])
    rest = annotations[LIMIT - 1 :]
    lines = [f"{item.title}: {(item.message.splitlines() or [''])[0]}" for item in rest]
    kept.append(Annotation(f"{title}（另外 {len(rest)} 則）", _tail("\n".join(lines))))
    return kept


def from_junit(path: Path) -> list[Annotation]:
    """JUnit XML 中每個失敗或錯誤的測試一則。"""
    found: list[Annotation] = []
    for case in ET.parse(path).getroot().iter("testcase"):
        for problem in [*case.findall("failure"), *case.findall("error")]:
            name = "::".join(part for part in (case.get("classname"), case.get("name")) if part)
            message = problem.get("message") or ""
            detail = problem.text or ""
            line = case.get("line")
            found.append(
                Annotation(
                    title=f"pytest {problem.tag}: {name}",
                    message=_tail(f"{message}\n\n{detail}" if detail else message),
                    file=_relative(file) if (file := case.get("file")) else None,
                    # xunit1 的 line 從 0 起算
                    line=int(line) + 1 if line and line.isdigit() else None,
                )
            )
    return limit(found, "pytest")


def slowest(path: Path, count: int = SLOWEST) -> str | None:
    """耗時摘要：測試時間總和、最慢的檔案與測試；報告沒有耗時資料時回傳 None。

    平行執行（pytest -n）時總和大於實際經過的時間；用 --dist loadfile 時，
    最慢的那個檔案就是整體時間的下限。
    """
    tests: list[tuple[float, str]] = []
    files: dict[str, float] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        try:
            seconds = float(case.get("time") or 0)
        except ValueError:
            continue
        file = _relative(case.get("file") or (case.get("classname") or "?").replace(".", "/"))
        tests.append((seconds, f"{file}::{case.get('name') or ''}"))
        files[file] = files.get(file, 0.0) + seconds
    total = sum(seconds for seconds, _ in tests)
    if total <= 0:
        return None
    lines = [f"測試時間總和 {total:.0f} 秒（{len(tests)} 個）", "", "最慢的檔案："]
    ranked = sorted(files.items(), key=lambda item: item[1], reverse=True)[:count]
    lines += [f"{seconds:.1f}s  {file}" for file, seconds in ranked]
    lines += ["", "最慢的測試："]
    lines += [f"{seconds:.1f}s  {name}" for seconds, name in sorted(tests, reverse=True)[:count]]
    return "\n".join(lines)


def from_pyright(data: object) -> list[Annotation]:
    """pyright --outputjson 的結果：每個檔案一則，列出該檔案的全部錯誤。"""
    report = cast("dict[str, object]", data if isinstance(data, dict) else {})
    diagnostics = cast("list[dict[str, object]]", report.get("generalDiagnostics") or [])
    by_file: dict[str, list[tuple[int, int, str]]] = {}
    for item in diagnostics:
        if item.get("severity") != "error":
            continue
        start = cast("dict[str, dict[str, int]]", item.get("range") or {}).get("start", {})
        line, col = start.get("line", 0) + 1, start.get("character", 0) + 1
        rule = f" [{item['rule']}]" if item.get("rule") else ""
        by_file.setdefault(_relative(str(item.get("file", ""))), []).append(
            (line, col, f"{item.get('message', '')}{rule}")
        )
    found: list[Annotation] = []
    for file, problems in by_file.items():
        problems.sort()
        first_line, first_col, _ = problems[0]
        lines = [f"L{line}:{col} {message}" for line, col, message in problems]
        found.append(
            Annotation(
                title=f"pyright: {len(problems)} 個錯誤",
                message=_tail("\n".join(lines)),
                file=file,
                line=first_line,
                col=first_col,
            )
        )
    return limit(found, "pyright")


def from_self_test(report: Path, log: Path | None = None) -> list[Annotation]:
    """桌面 App 自我測試：失敗的每一步一則；沒有報告時用日誌的結尾。"""
    if not report.exists():
        text = log.read_text(encoding="utf-8", errors="replace") if log and log.exists() else ""
        return [Annotation("self-test: 沒有產生報告", _tail(text) or "（沒有輸出）")]
    data = json.loads(report.read_text(encoding="utf-8"))
    summary = cast("dict[str, object]", data if isinstance(data, dict) else {})
    steps = cast("list[dict[str, object]]", summary.get("steps") or [])
    found: list[Annotation] = []
    for step in steps:
        if step.get("ok"):
            continue
        name = step.get("scenario") or step.get("engine") or ""
        # 錯誤放前面、一定保留；輸出很長時只保留結尾
        head = "\n".join(
            f"{key}: {step[key]}" for key in ("status", "exitCode", "error") if step.get(key)
        )
        output = str(step.get("output") or "").strip()
        if output:
            budget = max(DETAIL_CHARS - len(head), DETAIL_CHARS // 2)
            head = f"{head}\n{_tail(output, budget)}" if head else _tail(output, budget)
        found.append(Annotation(f"self-test {step.get('step')}: {name}", head))
    if not found and not summary.get("ok"):
        found.append(Annotation("self-test: 失敗", _tail(json.dumps(summary, ensure_ascii=False))))
    return limit(found, "self-test")


def passing_details(report: Path) -> str:
    """全部通過時，每一步的 ``detail``（一步一行）；沒有就是空字串。"""
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    summary = cast("dict[str, object]", data if isinstance(data, dict) else {})
    steps = cast("list[dict[str, object]]", summary.get("steps") or [])
    return "\n".join(
        f"{step.get('step')}: {step['detail']}" for step in steps if step.get("detail")
    )


def emit(annotations: Iterable[Annotation]) -> None:
    for annotation in annotations:
        print(annotation.command())


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "self-test":
        annotations = from_self_test(Path(args[1]), Path(args[2]))
    elif len(args) == 2 and args[0] == "self-test":
        annotations = from_self_test(Path(args[1]))
    else:
        annotations = None
    if annotations is not None:
        emit(annotations)
        if not annotations:
            details = passing_details(Path(args[1]))
            suffix = _escape_data("\n" + details) if details else ""
            print(f"::notice title=self-test::全部通過{suffix}")
        return 0
    if len(args) != 2 or args[0] not in ("junit", "pyright"):
        print(__doc__, file=sys.stderr)
        return 2
    kind, path = args[0], Path(args[1])
    if not path.exists():
        print(f"::warning title=ci_annotations::找不到 {path}，略過")
        return 0
    if kind == "junit":
        annotations = from_junit(path)
        emit(annotations)
        if not annotations:
            total = sum(1 for _ in ET.parse(path).getroot().iter("testcase"))
            print(f"::notice title=pytest::{path.name} 沒有失敗的測試（{total} 個）")
        if summary := slowest(path):
            title = _escape_property(f"pytest 耗時（{path.name}）")
            print(f"::notice title={title}::{_escape_data(summary)}")
    else:
        emit(from_pyright(json.loads(path.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
