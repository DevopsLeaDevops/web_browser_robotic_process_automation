# ruff: noqa: E501 - HTML 樣板以整行呈現比較好讀
"""執行報告 report.html：單一檔案、不需要網路，放在執行目錄裡直接用瀏覽器開啟。

版面參考 MVP 原型的 sample-run 報告；顏色取自介面設計系統 v1.0。
Python 節點與會下載的場景（ADR 0020）另有產出檔案（``outputs/``，可以下載）、檔案變化
（``files.json``）與資料預覽（``previews/``）；步驟多了原始碼行號、第幾次與那一步的檔案變化。
"""

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import quote

from rpa_core.dsl.files import format_size
from rpa_core.i18n import get_locale
from rpa_runner.files import OUTPUTS_DIR, PREVIEWS_DIR, STEP_SHOTS, read_json_or
from rpa_runner.i18n import t

if TYPE_CHECKING:
    from rpa_runner.run import RunResult

__all__ = ["render_report"]

_STYLE: Final = """
:root{--bg:#f5f7fb;--panel:#fff;--line:#e9edf3;--text:#24334a;--muted:#64758b;--blue:#0b69c4;
--green:#18794e;--green-bg:#e6f4ea;--red:#c0362c;--red-bg:#fdecea;--amber:#9a6700;--amber-bg:#fff5db}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:13px/1.6 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif}
main{max-width:1040px;margin:0 auto;padding:20px 16px 40px}h1{font-size:21px;margin:0 0 4px}
h2{font-size:15px;margin:0 0 10px}section{background:var(--panel);border:1px solid var(--line);
border-radius:9px;padding:16px;margin:12px 0}.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:10px;border-radius:6px;margin:0}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;
background:var(--line);color:var(--muted)}.passed{background:var(--green-bg);color:var(--green)}
.failed,.timed_out{background:var(--red-bg);color:var(--red)}.cancelled{background:var(--amber-bg);color:var(--amber)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:640px){.pair{grid-template-columns:1fr}}
img{max-width:100%;border:1px solid var(--line);border-radius:6px}a{color:var(--blue)}
td img.shot{display:block;width:112px;max-width:none;aspect-ratio:16/9;object-fit:cover;object-position:left top}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.preview{overflow-x:auto;margin:8px 0 16px}.preview td,.preview th{white-space:nowrap}
"""
_PREVIEW_ROWS: Final = 20
"""報告裡每份資料預覽最多顯示幾列（完整的在 previews/ 的 JSON）。"""


def _e(value: object) -> str:
    return html.escape(str(value))


def _badge(status: str) -> str:
    return f'<span class="badge {_e(status)}">{_e(t(f"status.{status}"))}</span>'


def _json(value: object) -> str:
    return f"<pre>{_e(json.dumps(value, ensure_ascii=False, indent=2))}</pre>"


def _step_detail(step: dict[str, object]) -> str:
    """步驟的錯誤，加上 upload 交出、download 下載的檔案與提醒（M7c）；Python 節點的步驟另有
    原始碼行號、第幾次與這一步的檔案變化（ADR 0020）。"""
    parts = [_e(step.get("error") or "")]
    files = step.get("files")
    if isinstance(files, list) and files:
        names = ", ".join(str(name) for name in cast("list[object]", files))
        key = "report.step_downloaded" if step.get("action") == "download" else "report.step_files"
        parts.append(f"<div class='muted'>{_e(t(key, files=names))}</div>")
    elif isinstance(files, dict) and files:
        changed = cast("dict[str, object]", files)
        counts = {
            kind: len(cast("list[object]", items)) if isinstance(items, list) else 0
            for kind, items in changed.items()
        }
        parts.append(
            f"<div class='muted'>{_e(t('report.step_changes', added=counts.get('added', 0), changed=counts.get('changed', 0), removed=counts.get('removed', 0)))}</div>"
        )
    source = step.get("source")
    if isinstance(source, str) and source:
        occurrence = step.get("occurrence")
        text = (
            t("report.step_source_again", source=source, number=occurrence)
            if isinstance(occurrence, int) and occurrence > 1
            else source
        )
        parts.append(f"<div class='muted mono'>{_e(text)}</div>")
    notes = step.get("notes")
    for note in cast("list[object]", notes) if isinstance(notes, list) else []:
        parts.append(f"<div class='badge cancelled'>{_e(note)}</div>")
    return "".join(part for part in parts if part)


def _shot(step: dict[str, object]) -> str:
    """這一步做完的截圖（錄影時才有，見 stepshots.py）：縮圖，點了看原圖。"""
    shot = step.get("shot")
    if not isinstance(shot, str) or not shot:
        return ""
    return f'<a href="{_e(shot)}"><img class="shot" src="{_e(shot)}" alt="" loading="lazy"></a>'


def _href(path: str) -> str:
    return _e(quote(path))


def _produced(folder: Path) -> str:
    """outputs/ 裡的檔案（Python 節點寫的、file 出參複製進來的）：可以下載。"""
    root = folder / OUTPUTS_DIR
    if not root.is_dir():
        return ""
    rows = "".join(
        f'<tr><td><a href="{_href(path.relative_to(folder).as_posix())}">{_e(path.relative_to(root).as_posix())}</a></td>'
        f"<td class='mono'>{_e(format_size(path.stat().st_size))}</td></tr>"
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not rows:
        return ""
    return f"<section><h2>{_e(t('report.produced'))}</h2><table><tbody>{rows}</tbody></table></section>"


def _changes(folder: Path) -> str:
    """files.json：自動化前後，共用工作資料夾與 outputs/ 的檔案變化。"""
    data = read_json_or(folder / "files.json", None)
    if not isinstance(data, dict):
        return ""
    changes = cast("dict[str, object]", data)
    rows: list[str] = []
    for kind in ("added", "changed", "removed"):
        items = changes.get(kind)
        for item in cast("list[object]", items) if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            entry = cast("dict[str, object]", item)
            size, where = entry.get("size"), entry.get("where")
            rows.append(
                f"<tr><td>{_e(t(f'report.change_{kind}'))}</td>"
                f"<td>{_e(t(f'report.where_{where}'))}</td>"
                f"<td class='mono'>{_e(entry.get('path'))}</td>"
                f"<td class='mono'>{_e(format_size(size) if isinstance(size, int) else '')}</td></tr>"
            )
    body = (
        f"<table><tbody>{''.join(rows)}</tbody></table>"
        if rows
        else f"<p class='muted'>{_e(t('report.no_changes'))}</p>"
    )
    note = (
        f"<p class='muted'>{_e(t('report.changes_truncated'))}</p>"
        if changes.get("truncated")
        else ""
    )
    return f"<section><h2>{_e(t('report.file_changes'))}</h2>{body}{note}</section>"


def _previews(folder: Path) -> str:
    """previews/ 的資料預覽（rpa_script 的 run.preview()）：表格顯示前幾列，其他是文字。"""
    root = folder / PREVIEWS_DIR
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(root.glob("*.json")):
        data = read_json_or(path, None)
        if not isinstance(data, dict):
            continue
        preview = cast("dict[str, object]", data)
        name = _e(preview.get("name") or path.stem)
        link = f'<a href="{_href(path.relative_to(folder).as_posix())}">{_e(path.name)}</a>'
        columns = preview.get("columns")
        rows = preview.get("rows")
        if preview.get("kind") == "table" and isinstance(columns, list) and isinstance(rows, list):
            head = "".join(f"<th>{_e(column)}</th>" for column in cast("list[object]", columns))
            body = "".join(
                "<tr>"
                + "".join(
                    f"<td>{_e('' if cell is None else cell)}</td>"
                    for cell in cast("list[object]", row)
                )
                + "</tr>"
                for row in cast("list[object]", rows)[:_PREVIEW_ROWS]
                if isinstance(row, list)
            )
            count = preview.get("rowCount")
            shown = min(len(cast("list[object]", rows)), _PREVIEW_ROWS)
            summary = t("report.preview_rows", shown=shown, total=count)
            parts.append(
                f"<h3>{name} <span class='muted'>{_e(summary)} · {link}</span></h3>"
                f"<div class='preview'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
            )
        else:
            parts.append(
                f"<h3>{name} <span class='muted'>{link}</span></h3><pre>{_e(preview.get('text') or '')}</pre>"
            )
    if not parts:
        return ""
    return f"<section><h2>{_e(t('report.previews'))}</h2>{''.join(parts)}</section>"


def _extras(folder: Path | None) -> str:
    """產出檔案、檔案變化與資料預覽（ADR 0020）；沒有執行目錄時（測試用的結果）不顯示。"""
    if folder is None:
        return ""
    return _produced(folder) + _changes(folder) + _previews(folder)


def render_report(result: "RunResult") -> str:
    """產生 report.html 的內容（目前語言）。"""
    stages = "".join(
        f"<tr><td>{_e(t(f'stage.{s.name}'))}</td><td>{_badge(s.status)}</td>"
        f"<td class='mono'>{s.duration_ms} ms</td><td>{_e(s.message or '')}</td></tr>"
        for s in result.stages
    )
    shots = any(step.get("shot") for step in result.steps)
    steps = "".join(
        f"<tr><td class='mono'>{_e(step.get('id'))}</td><td class='mono'>{_e(step.get('action'))}</td>"
        f"<td>{_e(step.get('name') or '')}</td><td>{_badge(str(step.get('status')))}</td>"
        f"<td class='mono'>{_e(step.get('durationMs'))} ms</td><td>{_step_detail(step)}</td>"
        + (f"<td>{_shot(step)}</td>" if shots else "")
        + "</tr>"
        for step in result.steps
    )
    shot_head = f"<th>{_e(t('report.shot'))}</th>" if shots else ""
    checks = "".join(
        f"<tr><td>{_e(c.name)}</td><td class='mono'>{_e(c.comparison)}</td>"
        f"<td><pre>{_e(c.actual)}</pre></td><td><pre>{_e(c.expected if c.expected is not None else '')}</pre></td>"
        f"<td>{_badge('passed' if c.passed else 'failed')}{_e(' ' + c.error if c.error else '')}</td></tr>"
        for c in result.checks
    )
    files = result.files
    images = [name for name in files if name.endswith(".png") and "/" not in name]
    gallery = (
        "".join(
            f'<figure><img src="{_e(name)}" alt="{_e(name)}"><figcaption class="muted">{_e(name)}</figcaption></figure>'
            for name in images
        )
        or f"<p class='muted'>{_e(t('report.no_screenshot'))}</p>"
    )
    # 每一步的截圖（steps/）可能有幾百張：檔案清單只列一項，截圖在步驟表裡
    shot_files = [name for name in files if name.startswith(f"{STEP_SHOTS}/")]
    links = " · ".join(
        [f'<a href="{_e(name)}">{_e(name)}</a>' for name in files if name not in shot_files]
        + ([_e(t("report.step_shots", count=len(shot_files)))] if shot_files else [])
    )
    problems = "".join(f"<li>{_e(problem)}</li>" for problem in result.problems)
    error = result.error or t("report.no_error")
    no_rows = f"<p class='muted'>{_e(t('report.none'))}</p>"
    title = f"{result.scenario_id} {result.scenario_name}"
    return f"""<!doctype html>
<html lang="{_e(get_locale())}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} · {_e(t(f"status.{result.status}"))}</title><style>{_STYLE}</style></head>
<body><main>
<h1>{_e(title)} {_badge(result.status)}</h1>
<p class="muted">{_e(t("report.meta", run_id=result.run_id, kind=t(f"kind.{result.kind}"), engine=result.engine, started=result.started_at, seconds=result.duration_seconds))}</p>
<section><h2>{_e(t("report.stages"))}</h2><table><thead><tr><th>{_e(t("report.stage"))}</th><th>{_e(t("report.status"))}</th><th>{_e(t("report.duration"))}</th><th>{_e(t("report.message"))}</th></tr></thead><tbody>{stages}</tbody></table>
<p>{_e(error)}</p>{f"<ul>{problems}</ul>" if problems else ""}</section>
<section><h2>{_e(t("report.steps"))}</h2>{f"<table><thead><tr><th>id</th><th>action</th><th>{_e(t('report.name'))}</th><th>{_e(t('report.status'))}</th><th>{_e(t('report.duration'))}</th><th>{_e(t('report.error'))}</th>{shot_head}</tr></thead><tbody>{steps}</tbody></table>" if steps else no_rows}</section>
<section><h2>{_e(t("report.checks"))}</h2>{f"<table><thead><tr><th>{_e(t('report.name'))}</th><th>{_e(t('report.comparison'))}</th><th>{_e(t('report.actual'))}</th><th>{_e(t('report.expected'))}</th><th>{_e(t('report.status'))}</th></tr></thead><tbody>{checks}</tbody></table>" if checks else no_rows}</section>
<section class="pair"><div><h2>{_e(t("report.input"))}</h2>{_json(result.input)}</div><div><h2>{_e(t("report.output"))}</h2>{_json(result.output) if result.output is not None else f"<p class='muted'>{_e(t('report.no_output'))}</p>"}</div></section>
{_extras(getattr(result, "directory", None))}
<section><h2>{_e(t("report.evidence"))}</h2>{gallery}</section>
<section><h2>{_e(t("report.files"))}</h2><p>{links}</p><p class="muted mono">{_e(t("report.hash", hash=result.scenario_hash))}</p></section>
</main></body></html>
"""
