"""tools/ci_annotations.py：pytest 與 pyright 的錯誤轉成 GitHub annotations。"""

import json
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


TIMED = """\
<testsuites><testsuite>
  <testcase classname="t.test_a" name="test_1" file="t/test_a.py" time="1.0"/>
  <testcase classname="t.test_a" name="test_2" file="t/test_a.py" time="3.0"/>
  <testcase classname="t.test_b" name="test_3" time="2.0"/>
</testsuite></testsuites>
"""


def test_slowest_files_and_tests(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(TIMED, encoding="utf-8")

    summary = tool.slowest(report, count=2)

    assert summary is not None
    assert summary.splitlines() == [
        "測試時間總和 6 秒（3 個）",
        "",
        "最慢的檔案：",
        "4.0s  t/test_a.py",
        "2.0s  t/test_b",  # 沒有 file 屬性時用 classname
        "",
        "最慢的測試：",
        "3.0s  t/test_a.py::test_2",
        "2.0s  t/test_b::test_3",
    ]


def test_timing_summary_is_a_separate_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.xml"
    report.write_text(TIMED, encoding="utf-8")

    assert tool.main(["junit", str(report)]) == 0

    passing, timing = capsys.readouterr().out.splitlines()
    assert passing == "::notice title=pytest::report.xml 沒有失敗的測試（3 個）"
    title, summary = timing.split("::", 2)[1:]
    assert title == "notice title=pytest 耗時（report.xml）"
    assert summary.startswith("測試時間總和 6 秒（3 個）%0A%0A最慢的檔案：%0A")


def test_self_test_failures_one_per_step(tmp_path: Path) -> None:
    report = tmp_path / "self-test.json"
    report.write_text(
        json.dumps(
            {
                "ok": False,
                "steps": [
                    {"step": "install", "engine": "chromium", "ok": True, "output": "done"},
                    {
                        "step": "run",
                        "scenario": "ba-001",
                        "ok": False,
                        "status": "failed",
                        "error": "TimeoutError: 逾時",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    (annotation,) = tool.from_self_test(report)

    assert annotation.title == "self-test run: ba-001"
    assert annotation.message == "status: failed\nerror: TimeoutError: 逾時"


def test_self_test_keeps_the_error_when_the_output_is_long(tmp_path: Path) -> None:
    """端到端附上的日誌很長（安裝檔的 /LOG）：錯誤在最前面，一定要留著；日誌只留結尾。"""
    report = tmp_path / "e2e.json"
    output = "開頭的日誌\n" + "x" * (tool.DETAIL_CHARS * 2) + "\n最後一行"
    error = "StepFailedError: 資料夾還在"
    step = {"step": "remove-data", "ok": False, "error": error, "output": output}
    report.write_text(json.dumps({"ok": False, "steps": [step]}), encoding="utf-8")

    (annotation,) = tool.from_self_test(report)

    assert annotation.message.startswith("error: StepFailedError: 資料夾還在\n…\n")
    assert annotation.message.endswith("最後一行")
    assert "開頭的日誌" not in annotation.message
    assert len(annotation.message) <= tool.DETAIL_CHARS + 10


def test_self_test_without_report_uses_the_log(tmp_path: Path) -> None:
    log = tmp_path / "self-test.log"
    log.write_text("Traceback ...\nUnicodeEncodeError: 'charmap'\n", encoding="utf-8")

    (annotation,) = tool.from_self_test(tmp_path / "missing.json", log)

    assert annotation.title == "self-test: 沒有產生報告"
    assert annotation.message.endswith("UnicodeEncodeError: 'charmap'")


def test_self_test_passing_is_a_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "self-test.json"
    report.write_text(json.dumps({"ok": True, "steps": [{"step": "run", "ok": True}]}), "utf-8")
    assert tool.main(["self-test", str(report), str(tmp_path / "self-test.log")]) == 0
    assert capsys.readouterr().out == "::notice title=self-test::全部通過\n"


def test_self_test_passing_lists_step_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "smoke.json"
    steps = [
        {"step": "webview2", "ok": True, "detail": "141.0"},
        {"step": "window", "ok": True, "detail": "Mozilla/5.0 Edg/141"},
        {"step": "tray", "ok": True},
    ]
    report.write_text(json.dumps({"ok": True, "steps": steps}), "utf-8")
    assert tool.main(["self-test", str(report)]) == 0
    expected = (
        "::notice title=self-test::全部通過%0Awebview2: 141.0%0Awindow: Mozilla/5.0 Edg/141\n"
    )
    assert capsys.readouterr().out == expected
