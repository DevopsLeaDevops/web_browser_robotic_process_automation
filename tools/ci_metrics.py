"""CI 運行耗時紀錄：每次運行結束後追加到倉庫的 ci-metrics 分支，方便之後回顧與復盤。

由 .github/workflows/ci-metrics.yml 執行（workflow_run：CI、桌面端建置、一鍵安裝腳本、每晚完整測試、
發布結束時）。資料放在 ci-metrics 分支（不碰 main，不觸發其他流程）：

- ``data/runs.jsonl``：每次運行（每次重跑各一行）：觸發方式、分支、結果、耗時、最長排隊、
  各系統的機器時間。
- ``data/jobs.jsonl``：每個工作的排隊與執行時間。
- ``data/test-files.jsonl``：JUnit 報告裡每個測試檔案的時間（CI 與每晚完整測試上傳的報告）。
- ``README.md``：由上面三份產生的總覽（近 7 天與前 7 天的比較、每天的機器時間、
  最慢的測試檔案、最近的運行）。

用法::

    python3 tools/ci_metrics.py record --event "$GITHUB_EVENT_PATH" --data metrics/data
    python3 tools/ci_metrics.py backfill --since 2026-10-09 --data metrics/data
    python3 tools/ci_metrics.py report --data metrics/data --out metrics/README.md

只用標準函式庫；GitHub 的資料用 ``gh``（GH_TOKEN 要能讀 Actions）。時間依專案規則以
America/Los_Angeles 顯示並標示 PDT／PST；這裡自己算夏令時間，Windows 上沒有時區資料庫也能用。
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, cast

TRACKED: Final = ("CI", "桌面端建置", "一鍵安裝腳本", "每晚完整測試", "發布")
"""要記錄的 workflow（name）；ci-metrics.yml 的 workflow_run 也列同一份。"""

REPORTS: Final = ("pytest-report-", "test-results-")
"""含 JUnit 報告的 artifact 名稱前綴。"""

RUNS: Final = "runs.jsonl"
JOBS: Final = "jobs.jsonl"
FILES: Final = "test-files.jsonl"

EVENTS: Final[Mapping[str, str]] = {
    "pull_request": "PR",
    "push": "推送",
    "schedule": "排程",
    "workflow_dispatch": "手動",
    "workflow_call": "呼叫",
}

type Json = dict[str, object]
type Runner = Callable[[Sequence[str]], str | None]


# ------------------------------------------------------------------ 時間


def parse_time(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def la_offset(moment: datetime) -> int:
    """America/Los_Angeles 的 UTC 偏移（小時）：3 月第二個週日到 11 月第一個週日是 −7，其他 −8。"""
    year = moment.year
    march = datetime(year, 3, 8, tzinfo=UTC)
    start = march + timedelta(days=(6 - march.weekday()) % 7, hours=10)  # 02:00 PST
    november = datetime(year, 11, 1, tzinfo=UTC)
    end = november + timedelta(days=(6 - november.weekday()) % 7, hours=9)  # 02:00 PDT
    return -7 if start <= moment.astimezone(UTC) < end else -8


def la_time(moment: datetime) -> tuple[datetime, str]:
    """換算成洛杉磯時間，回傳（時間，「PDT，UTC−07:00」這樣的標示）。"""
    offset = la_offset(moment)
    local = moment.astimezone(UTC) + timedelta(hours=offset)
    name = "PDT" if offset == -7 else "PST"
    return local.replace(tzinfo=None), f"{name}，UTC−0{-offset}:00"


def la_text(moment: datetime) -> str:
    local, zone = la_time(moment)
    return f"{local:%Y-%m-%d %H:%M} America/Los_Angeles（{zone}）"


def seconds_between(start: object, end: object) -> float:
    a, b = parse_time(start), parse_time(end)
    return max(0.0, (b - a).total_seconds()) if a and b else 0.0


def runner_os(labels: object) -> str:
    text = " ".join(str(label) for label in cast("list[object]", labels or []))
    if "macos" in text:
        return "macos"
    if "windows" in text:
        return "windows"
    return "linux"


# ------------------------------------------------------------------ 讀寫資料


def read_jsonl(path: Path) -> list[Json]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [cast("Json", json.loads(line)) for line in lines if line.strip()]


def append_jsonl(path: Path, rows: Iterable[Json]) -> int:
    rows = list(rows)
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


# ------------------------------------------------------------------ 整理一次運行


def summarize(run: Json, jobs: Sequence[Json]) -> tuple[list[Json], list[Json]]:
    """一次運行的工作（含重跑）整理成每次嘗試一行的 runs 與每個工作一行的 jobs。"""
    by_attempt: dict[int, list[Json]] = defaultdict(list)
    latest = int(cast("int", run.get("run_attempt") or 1))
    for job in jobs:
        by_attempt[int(cast("int", job.get("run_attempt") or latest))].append(job)
    runs: list[Json] = []
    job_rows: list[Json] = []
    for attempt, items in sorted(by_attempt.items()):
        runner_s = {"linux": 0.0, "windows": 0.0, "macos": 0.0}
        queue_max = 0.0
        starts = [t for job in items if (t := parse_time(job.get("created_at")))]
        ends = [t for job in items if (t := parse_time(job.get("completed_at")))]
        for job in items:
            queue = seconds_between(job.get("created_at"), job.get("started_at"))
            ran = bool(job.get("runner_name"))
            duration = seconds_between(job.get("started_at"), job.get("completed_at")) if ran else 0
            system = runner_os(job.get("labels"))
            if ran:
                runner_s[system] += duration
                queue_max = max(queue_max, queue)
            job_rows.append(
                {
                    "run_id": run["id"],
                    "attempt": attempt,
                    "workflow": run.get("name"),
                    "job": job.get("name"),
                    "os": system,
                    "conclusion": job.get("conclusion"),
                    "queue_s": round(queue if ran else 0.0, 1),
                    "duration_s": round(duration, 1),
                }
            )
        is_latest = attempt == latest
        runs.append(
            {
                "run_id": run["id"],
                "attempt": attempt,
                "workflow": run.get("name"),
                "event": run.get("event"),
                "branch": run.get("head_branch"),
                "sha": run.get("head_sha"),
                "started_at": min(starts).isoformat() if starts else run.get("run_started_at"),
                "completed_at": max(ends).isoformat() if ends else run.get("updated_at"),
                "conclusion": run.get("conclusion") if is_latest else _worst(items),
                "wall_s": round((max(ends) - min(starts)).total_seconds(), 1)
                if starts and ends
                else 0.0,
                "queue_max_s": round(queue_max, 1),
                "runner_s": {key: round(value, 1) for key, value in runner_s.items()},
                "url": f"{run.get('html_url')}/attempts/{attempt}",
            }
        )
    return runs, job_rows


def _worst(jobs: Sequence[Json]) -> str:
    results = {str(job.get("conclusion")) for job in jobs}
    for result in ("failure", "cancelled", "timed_out"):
        if result in results:
            return result
    return "success"


def file_times(report: Path) -> list[tuple[str, float, int]]:
    """JUnit 報告裡每個測試檔案的（檔案，秒數，測試數），按秒數由大到小。"""
    seconds: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for case in ET.parse(report).getroot().iter("testcase"):
        file = case.get("file") or (case.get("classname") or "?").replace(".", "/")
        try:
            seconds[file] += float(case.get("time") or 0)
        except ValueError:
            continue
        counts[file] += 1
    ranked = sorted(seconds.items(), key=lambda item: item[1], reverse=True)
    return [(file, round(total, 1), counts[file]) for file, total in ranked]


# ------------------------------------------------------------------ 從 GitHub 取得


def gh(command: Sequence[str]) -> str | None:
    done = subprocess.run(["gh", *command], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        print(f"::warning title=ci_metrics::gh {' '.join(command)} 失敗：{done.stderr.strip()}")
        return None
    return done.stdout


class Recorder:
    def __init__(self, data: Path, repo: str, runner: Runner = gh) -> None:
        self.data = data
        self.repo = repo
        self.runner = runner
        self.seen = {(row["run_id"], row["attempt"]) for row in read_jsonl(data / RUNS)}

    def api(self, path: str) -> Json | None:
        out = self.runner(["api", f"repos/{self.repo}/{path}"])
        return cast("Json", json.loads(out)) if out else None

    def record(self, run: Json) -> int:
        """記錄一次運行還沒記過的嘗試；回傳新增的 runs 行數。"""
        if run.get("name") not in TRACKED or run.get("status") != "completed":
            return 0
        latest = int(cast("int", run.get("run_attempt") or 1))
        if all((run["id"], attempt) in self.seen for attempt in range(1, latest + 1)):
            return 0
        listing = self.api(f"actions/runs/{run['id']}/jobs?filter=all&per_page=100") or {}
        jobs = cast("list[Json]", listing.get("jobs", []))
        runs, job_rows = summarize(run, jobs)
        new = [row for row in runs if (row["run_id"], row["attempt"]) not in self.seen]
        new_keys = {(row["run_id"], row["attempt"]) for row in new}
        append_jsonl(self.data / RUNS, new)
        fresh = [row for row in job_rows if (row["run_id"], row["attempt"]) in new_keys]
        append_jsonl(self.data / JOBS, fresh)
        if (run["id"], latest) in new_keys:
            append_jsonl(self.data / FILES, self.reports(run, latest))
        self.seen |= new_keys
        return len(new)

    def reports(self, run: Json, attempt: int) -> list[Json]:
        listing = self.api(f"actions/runs/{run['id']}/artifacts?per_page=100") or {}
        rows: list[Json] = []
        for artifact in cast("list[Json]", listing.get("artifacts", [])):
            name = str(artifact.get("name", ""))
            if artifact.get("expired") or not name.startswith(REPORTS):
                continue
            with tempfile.TemporaryDirectory() as folder:
                command = ["run", "download", str(run["id"]), "-R", self.repo]
                if self.runner([*command, "-n", name, "-D", folder]) is None:
                    continue
                for report in sorted(Path(folder).rglob("*.xml")):
                    try:
                        files = file_times(report)
                    except ET.ParseError:
                        continue
                    label = f"{name}/{report.name}"
                    rows += [
                        {
                            "run_id": run["id"],
                            "attempt": attempt,
                            "workflow": run.get("name"),
                            "report": label,
                            "file": file,
                            "seconds": seconds,
                            "tests": count,
                        }
                        for file, seconds, count in files
                    ]
        return rows

    def backfill(self, since: str) -> int:
        added = 0
        page = 1
        while True:
            listing = self.api(f"actions/runs?per_page=100&page={page}&created=%3E%3D{since}") or {}
            runs = cast("list[Json]", listing.get("workflow_runs", []))
            for run in runs:
                added += self.record(run)
            if len(runs) < 100:
                return added
            page += 1


# ------------------------------------------------------------------ 總覽


def minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f} 分"


def median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def p90(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]


SYSTEMS: Final = ("linux", "windows", "macos")


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    return float(value) if isinstance(value, int | float) else 0.0


def _runner(row: Json) -> Mapping[str, float]:
    return cast("Mapping[str, float]", row.get("runner_s") or {})


def _when(row: Json) -> datetime:
    return parse_time(row.get("started_at")) or datetime.min.replace(tzinfo=UTC)


def report(data: Path, now: datetime) -> str:
    runs = read_jsonl(data / RUNS)
    files = read_jsonl(data / FILES)
    lines = [
        "# CI 運行耗時紀錄",
        "",
        f"更新：{la_text(now)}。共 {len(runs)} 次運行。",
        "",
        "每次 CI、桌面端建置、一鍵安裝腳本、每晚完整測試、發布結束後，"
        "由 `.github/workflows/ci-metrics.yml` 追加到 `data/`；"
        "本頁由 `tools/ci_metrics.py report` 產生，不要手改。"
        "耗時＝第一個工作建立到最後一個工作結束（含排隊）；"
        "機器時間＝各工作實際執行的時間總和。",
        "規則與背景見 main 的 `docs/develop/ci.html`。",
        "",
    ]
    lines += _compare(runs, now)
    lines += _daily(runs, now)
    lines += _slowest(files, runs)
    lines += _recent(runs)
    return "\n".join(lines) + "\n"


def _compare(runs: Sequence[Json], now: datetime) -> list[str]:
    week = timedelta(days=7)
    lines = [
        "## 各流程：近 7 天（前 7 天）",
        "",
        "| 流程 | 次數 | 通過 | 耗時中位數 | 耗時 P90 | 最長排隊中位數 "
        "| 機器時間（Linux／Windows／macOS） |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in TRACKED:
        cells: list[list[str]] = []
        for start, end in ((now - week, now), (now - 2 * week, now - week)):
            rows = [r for r in runs if r.get("workflow") == name and start <= _when(r) < end]
            walls = [_number(r, "wall_s") for r in rows]
            queues = [_number(r, "queue_max_s") for r in rows]
            passed = sum(1 for r in rows if r.get("conclusion") == "success")
            used = {key: sum(_runner(r).get(key, 0.0) for r in rows) for key in SYSTEMS}
            cells.append(
                [
                    str(len(rows)),
                    str(passed),
                    minutes(median(walls)),
                    minutes(p90(walls)),
                    minutes(median(queues)),
                    "／".join(f"{used[key] / 60:.0f}" for key in SYSTEMS) + " 分",
                ]
            )
        merged = [f"{now_cell}（{before}）" for now_cell, before in zip(*cells, strict=True)]
        lines.append(f"| {name} | " + " | ".join(merged) + " |")
    return [*lines, ""]


def _daily(runs: Sequence[Json], now: datetime) -> list[str]:
    lines = [
        "## 每天的機器時間（分鐘，洛杉磯日期，最近 14 天）",
        "",
        "| 日期 | 運行次數 | Linux | Windows | macOS | 合計 |",
        "|---|---|---|---|---|---|",
    ]
    days: dict[str, list[Json]] = defaultdict(list)
    for row in runs:
        when = _when(row)
        if now - when <= timedelta(days=14):
            days[f"{la_time(when)[0]:%Y-%m-%d}"].append(row)
    for day in sorted(days, reverse=True):
        used = [sum(_runner(r).get(key, 0.0) for r in days[day]) / 60 for key in SYSTEMS]
        cells = [f"{value:.0f}" for value in used]
        lines.append(f"| {day} | {len(days[day])} | " + " | ".join(cells) + f" | {sum(used):.0f} |")
    return [*lines, ""]


def _slowest(files: Sequence[Json], runs: Sequence[Json], top: int = 10) -> list[str]:
    started = {row["run_id"]: _when(row) for row in runs}
    groups: dict[str, list[Json]] = defaultdict(list)
    for row in files:
        groups[f"{row.get('workflow')} · {row.get('report')}"].append(row)
    lines = ["## 最慢的測試檔案（每份報告最近一次，括號是近 7 次的中位數）", ""]
    if not groups:
        return [*lines, "還沒有測試報告的資料。", ""]
    epoch = datetime.min.replace(tzinfo=UTC)
    for name in sorted(groups):
        rows = groups[name]
        order = sorted({r["run_id"] for r in rows}, key=lambda run: started.get(run, epoch))
        latest = order[-1]
        recent = set(order[-7:])
        history: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row["run_id"] in recent:
                history[str(row.get("file"))].append(_number(row, "seconds"))
        current = sorted(
            (r for r in rows if r["run_id"] == latest),
            key=lambda r: _number(r, "seconds"),
            reverse=True,
        )
        total = sum(_number(r, "seconds") for r in current)
        when = started.get(latest)
        latest_text = la_text(when) if when else "時間不明"
        lines += [f"### {name}", "", f"最近一次：{latest_text}，合計 {total:.0f} 秒。", ""]
        lines += ["| 秒 | 測試數 | 檔案 |", "|---|---|---|"]
        for row in current[:top]:
            file = str(row.get("file"))
            seconds = _number(row, "seconds")
            lines.append(
                f"| {seconds:.1f}（{median(history[file]):.1f}） | {row.get('tests')} | `{file}` |"
            )
        lines.append("")
    return lines


def _recent(runs: Sequence[Json], count: int = 40) -> list[str]:
    lines = [
        f"## 最近 {count} 次運行",
        "",
        "| 開始（洛杉磯） | 流程 | 觸發 | 分支 | 結果 | 耗時 | 最長排隊 | 運行 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(runs, key=_when, reverse=True)[:count]:
        local = f"{la_time(_when(row))[0]:%m-%d %H:%M}"
        event = EVENTS.get(str(row.get("event")), str(row.get("event")))
        attempt = int(cast("int", row.get("attempt") or 1))
        label = f"#{row.get('run_id')}" + (f" 第 {attempt} 次" if attempt > 1 else "")
        cells = [
            local,
            str(row.get("workflow")),
            event,
            str(row.get("branch")),
            str(row.get("conclusion")),
            minutes(_number(row, "wall_s")),
            minutes(_number(row, "queue_max_s")),
            f"[{label}]({row.get('url')})",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return [*lines, ""]


# ------------------------------------------------------------------ 命令列


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI 運行耗時紀錄")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="記錄 workflow_run 事件的那次運行")
    record.add_argument("--event", required=True, type=Path)
    backfill = sub.add_parser("backfill", help="補記某天（UTC）之後的運行")
    backfill.add_argument("--since", required=True)
    summary = sub.add_parser("report", help="重新產生總覽")
    summary.add_argument("--out", required=True, type=Path)
    for item in (record, backfill, summary):
        item.add_argument("--data", required=True, type=Path)
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if args.command == "record":
        event = cast("Json", json.loads(Path(args.event).read_text(encoding="utf-8")))
        added = Recorder(args.data, repo).record(cast("Json", event.get("workflow_run", {})))
        print(f"新增 {added} 次運行")
    elif args.command == "backfill":
        added = Recorder(args.data, repo).backfill(args.since)
        print(f"補記 {added} 次運行")
    else:
        Path(args.out).write_text(report(args.data, datetime.now(UTC)), encoding="utf-8")
        print(f"已產生 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
