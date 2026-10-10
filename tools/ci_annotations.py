"""把 pytest 與 pyright 的錯誤轉成 GitHub Actions 的 annotations。

CI 失敗時，原因直接標在 PR「Files changed」的對應行上；看不到 Actions 日誌的環境
（例如雲端開發環境）也能從 check run 的 annotations API 讀到完整的錯誤。

用法（CI 裡在測試或檢查之後執行）::

    uv run python tools/ci_annotations.py junit pytest-report.xml
    uv run python tools/ci_annotations.py pyright pyright.json

pytest 要用 ``--junitxml=… -o junit_family=xunit1``（xunit1 才有 file、line 屬性）；
pyright 要用 ``--outputjson``。

GitHub 每個步驟最多顯示 10 個錯誤 annotation，所以 pytest 一個失敗的測試一則、
pyright 一個檔案一則，超過的部分合併成最後一則。
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

DETAIL_CHARS: Final = 6000
"""每則 annotation 保留的錯誤內容長度（保留結尾：斷言與例外通常在最後）。"""


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


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= DETAIL_CHARS else "…\n" + text[-DETAIL_CHARS:]


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


def emit(annotations: Iterable[Annotation]) -> None:
    for annotation in annotations:
        print(annotation.command())


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in ("junit", "pyright"):
        print(__doc__, file=sys.stderr)
        return 2
    kind, path = args[0], Path(args[1])
    if not path.exists():
        print(f"::warning title=ci_annotations::找不到 {path}，略過")
        return 0
    if kind == "junit":
        emit(from_junit(path))
    else:
        emit(from_pyright(json.loads(path.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
