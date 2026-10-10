"""tools/ci_annotations.py：pytest 與 pyright 的錯誤轉成 GitHub annotations。"""

from pathlib import Path

import pytest

import tools.ci_annotations as tool

JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest">
  <testcase classname="tests.test_a" name="test_ok" file="tests/test_a.py" line="3"/>
  <testcase classname="tests.test_a" name="test_bad" file="tests/test_a.py" line="9">
    <failure message="AssertionError: 差異:a,b">def test_bad():
&gt;       assert 1 == 2
E       assert 1 == 2</failure>
  </testcase>
  <testcase classname="" name="tests.test_b">
    <error message="collection failure">ImportError: No module named 'x'</error>
  </testcase>
</testsuite></testsuites>
"""


def test_junit_failures_and_errors(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(JUNIT, encoding="utf-8")

    first, second = tool.from_junit(report)

    assert first.title == "pytest failure: tests.test_a::test_bad"
    assert (first.file, first.line) == ("tests/test_a.py", 10)
    assert first.message.startswith("AssertionError: 差異:a,b\n\ndef test_bad():")
    assert second.title == "pytest error: tests.test_b"
    assert second.file is None
    assert "ImportError" in second.message


def test_command_escapes_newlines_and_property_separators() -> None:
    annotation = tool.Annotation("a: b, c", "50% 完成\n下一行", file="x.py", line=2, col=3)

    assert annotation.command() == (
        "::error title=a%3A b%2C c,file=x.py,line=2,col=3::50%25 完成%0A下一行"
    )


def test_pyright_groups_errors_by_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))

    def diagnostic(file: str, line: int, message: str, severity: str = "error") -> object:
        return {
            "file": str(tmp_path / file),
            "severity": severity,
            "message": message,
            "rule": "reportX",
            "range": {"start": {"line": line, "character": 4}},
        }

    data = {
        "generalDiagnostics": [
            diagnostic("b.py", 9, "後面"),
            diagnostic("b.py", 1, "前面"),
            diagnostic("a.py", 0, "只是提醒", severity="warning"),
        ]
    }
    (annotation,) = tool.from_pyright(data)

    assert (annotation.file, annotation.line, annotation.col) == ("b.py", 2, 5)
    assert annotation.message == "L2:5 前面 [reportX]\nL10:5 後面 [reportX]"


def test_too_many_annotations_are_merged() -> None:
    many = [tool.Annotation(f"t{i}", f"第 {i} 則\n細節") for i in range(15)]

    kept = tool.limit(many, "pytest")

    assert len(kept) == tool.LIMIT
    assert kept[-1].title == "pytest（另外 6 則）"
    assert kept[-1].message.splitlines() == [f"t{i}: 第 {i} 則" for i in range(9, 15)]


def test_missing_report_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert tool.main(["junit", str(tmp_path / "missing.xml")]) == 0
    assert capsys.readouterr().out.startswith("::warning")


def test_passing_report_is_a_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite><testcase classname="a" name="b"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    assert tool.main(["junit", str(report)]) == 0
    assert capsys.readouterr().out == "::notice title=pytest::report.xml 沒有失敗的測試（1 個）\n"
