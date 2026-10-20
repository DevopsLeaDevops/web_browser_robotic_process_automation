"""tools/ci_metrics.py：運行耗時整理成 jsonl，並產生總覽。"""

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.ci_metrics import (
    FILES,
    JOBS,
    RUNS,
    Json,
    Recorder,
    file_times,
    la_text,
    read_jsonl,
    report,
    summarize,
)

JUNIT = """\
<testsuites><testsuite>
  <testcase classname="a.test_x" name="t1" file="apps/a/test_x.py" time="2.0"/>
  <testcase classname="a.test_x" name="t2" file="apps/a/test_x.py" time="3.0"/>
  <testcase classname="b.test_y" name="t3" file="apps/b/test_y.py" time="1.5"/>
</testsuite></testsuites>
"""

type Runner = Callable[[Sequence[str]], str | None]


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ("2026-10-20T03:00:00Z", "2026-10-19 20:00 America/Los_Angeles（PDT，UTC−07:00）"),
        # 11 月第一個週日 02:00 PDT 換成 01:00 PST
        ("2026-11-01T08:59:00Z", "2026-11-01 01:59 America/Los_Angeles（PDT，UTC−07:00）"),
        ("2026-11-01T09:00:00Z", "2026-11-01 01:00 America/Los_Angeles（PST，UTC−08:00）"),
        # 3 月第二個週日 02:00 PST 換成 03:00 PDT
        ("2027-03-14T09:59:00Z", "2027-03-14 01:59 America/Los_Angeles（PST，UTC−08:00）"),
        ("2027-03-14T10:00:00Z", "2027-03-14 03:00 America/Los_Angeles（PDT，UTC−07:00）"),
    ],
)
def test_los_angeles_time(utc: str, expected: str) -> None:
    assert la_text(datetime.fromisoformat(utc.replace("Z", "+00:00"))) == expected


def job(attempt: int, name: str, label: str, times: Sequence[str], result: str = "success") -> Json:
    created, started, completed = (f"2026-10-20T01:{value}Z" for value in times)
    return {
        "run_attempt": attempt,
        "name": name,
        "labels": [label],
        "runner_name": "GitHub Actions 1",
        "created_at": created,
        "started_at": started,
        "completed_at": completed,
        "conclusion": result,
    }


RUN: Json = {
    "id": 7,
    "name": "CI",
    "status": "completed",
    "conclusion": "success",
    "event": "pull_request",
    "head_branch": "feature",
    "head_sha": "abc",
    "run_attempt": 2,
    "html_url": "https://github.com/o/r/actions/runs/7",
}
JOBS_OF_RUN = [
    job(1, "測試", "ubuntu-latest", ["00:00", "00:10", "04:10"], "failure"),
    job(2, "測試", "ubuntu-latest", ["10:00", "10:05", "13:05"]),
    job(2, "Worker", "windows-latest", ["10:00", "11:00", "14:00"]),
]


def test_summarize_one_row_per_attempt() -> None:
    runs, jobs = summarize(RUN, JOBS_OF_RUN)

    first, second = runs
    assert (first["attempt"], first["conclusion"], first["wall_s"]) == (1, "failure", 250.0)
    assert (second["attempt"], second["conclusion"], second["wall_s"]) == (2, "success", 240.0)
    assert second["queue_max_s"] == 60.0
    assert second["runner_s"] == {"linux": 180.0, "windows": 180.0, "macos": 0.0}
    assert str(second["url"]).endswith("/attempts/2")
    assert [(row["attempt"], row["os"]) for row in jobs] == [
        (1, "linux"),
        (2, "linux"),
        (2, "windows"),
    ]


def test_file_times(tmp_path: Path) -> None:
    report_file = tmp_path / "r.xml"
    report_file.write_text(JUNIT, encoding="utf-8")
    assert file_times(report_file) == [("apps/a/test_x.py", 5.0, 2), ("apps/b/test_y.py", 1.5, 1)]


def fake_github() -> tuple[list[list[str]], Runner]:
    calls: list[list[str]] = []

    def runner(command: Sequence[str]) -> str | None:
        calls.append(list(command))
        match list(command):
            case ["api", url] if "/jobs" in url:
                return json.dumps({"jobs": JOBS_OF_RUN})
            case ["api", url] if "/artifacts" in url:
                artifacts = [
                    {"name": "pytest-report-3.13", "expired": False},
                    {"name": "portal-traces", "expired": False},
                ]
                return json.dumps({"artifacts": artifacts})
            case ["run", "download", *rest]:
                folder = Path(rest[rest.index("-D") + 1])
                (folder / "pytest-report.xml").write_text(JUNIT, encoding="utf-8")
                return ""
            case _:
                return None

    return calls, runner


def test_record_appends_new_attempts_once(tmp_path: Path) -> None:
    calls, runner = fake_github()
    data = tmp_path / "data"

    assert Recorder(data, "o/r", runner).record(RUN) == 2
    assert Recorder(data, "o/r", runner).record(RUN) == 0  # 已經記過，不再呼叫 API

    assert [row["attempt"] for row in read_jsonl(data / RUNS)] == [1, 2]
    assert len(read_jsonl(data / JOBS)) == 3
    files = read_jsonl(data / FILES)
    assert {(row["report"], row["file"], row["seconds"]) for row in files} == {
        ("pytest-report-3.13/pytest-report.xml", "apps/a/test_x.py", 5.0),
        ("pytest-report-3.13/pytest-report.xml", "apps/b/test_y.py", 1.5),
    }
    downloads = [call for call in calls if call[:2] == ["run", "download"]]
    assert len(downloads) == 1  # 只下載含 JUnit 報告的 artifact


def test_untracked_or_unfinished_runs_are_ignored(tmp_path: Path) -> None:
    _, runner = fake_github()
    recorder = Recorder(tmp_path / "data", "o/r", runner)
    assert recorder.record({**RUN, "name": "bootstrap"}) == 0
    assert recorder.record({**RUN, "status": "in_progress"}) == 0


def test_report_lists_workflows_files_and_recent_runs(tmp_path: Path) -> None:
    _, runner = fake_github()
    data = tmp_path / "data"
    Recorder(data, "o/r", runner).record(RUN)

    text = report(data, datetime(2026, 10, 20, 2, 0, tzinfo=UTC))

    assert text.startswith("# CI 運行耗時紀錄\n")
    assert "更新：2026-10-19 19:00 America/Los_Angeles（PDT，UTC−07:00）。共 2 次運行。" in text
    assert "| CI | 2（0） | 1（0） | 4.1 分（0.0 分）" in text
    assert "| 2026-10-19 | 2 | 7 | 3 | 0 | 10 |" in text
    assert "### CI · pytest-report-3.13/pytest-report.xml" in text
    assert "| 5.0（5.0） | 2 | `apps/a/test_x.py` |" in text
    assert "[#7 第 2 次](https://github.com/o/r/actions/runs/7/attempts/2)" in text
