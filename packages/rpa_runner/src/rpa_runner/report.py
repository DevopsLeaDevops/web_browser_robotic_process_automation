# ruff: noqa: E501 - HTML 樣板以整行呈現比較好讀
"""執行報告 report.html：單一檔案、不需要網路，放在執行目錄裡直接用瀏覽器開啟。

版面參考 MVP 原型的 sample-run 報告；顏色取自介面設計系統 v1.0。
"""

import html
import json
from typing import TYPE_CHECKING, Final

from rpa_core.i18n import get_locale
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
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
"""


def _e(value: object) -> str:
    return html.escape(str(value))


def _badge(status: str) -> str:
    return f'<span class="badge {_e(status)}">{_e(t(f"status.{status}"))}</span>'


def _json(value: object) -> str:
    return f"<pre>{_e(json.dumps(value, ensure_ascii=False, indent=2))}</pre>"


def render_report(result: "RunResult") -> str:
    """產生 report.html 的內容（目前語言）。"""
    stages = "".join(
        f"<tr><td>{_e(t(f'stage.{s.name}'))}</td><td>{_badge(s.status)}</td>"
        f"<td class='mono'>{s.duration_ms} ms</td><td>{_e(s.message or '')}</td></tr>"
        for s in result.stages
    )
    steps = "".join(
        f"<tr><td class='mono'>{_e(step.get('id'))}</td><td class='mono'>{_e(step.get('action'))}</td>"
        f"<td>{_e(step.get('name') or '')}</td><td>{_badge(str(step.get('status')))}</td>"
        f"<td class='mono'>{_e(step.get('durationMs'))} ms</td><td>{_e(step.get('error') or '')}</td></tr>"
        for step in result.steps
    )
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
    links = " · ".join(f'<a href="{_e(name)}">{_e(name)}</a>' for name in files)
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
<section><h2>{_e(t("report.steps"))}</h2>{f"<table><thead><tr><th>id</th><th>action</th><th>{_e(t('report.name'))}</th><th>{_e(t('report.status'))}</th><th>{_e(t('report.duration'))}</th><th>{_e(t('report.error'))}</th></tr></thead><tbody>{steps}</tbody></table>" if steps else no_rows}</section>
<section><h2>{_e(t("report.checks"))}</h2>{f"<table><thead><tr><th>{_e(t('report.name'))}</th><th>{_e(t('report.comparison'))}</th><th>{_e(t('report.actual'))}</th><th>{_e(t('report.expected'))}</th><th>{_e(t('report.status'))}</th></tr></thead><tbody>{checks}</tbody></table>" if checks else no_rows}</section>
<section class="pair"><div><h2>{_e(t("report.input"))}</h2>{_json(result.input)}</div><div><h2>{_e(t("report.output"))}</h2>{_json(result.output) if result.output is not None else f"<p class='muted'>{_e(t('report.no_output'))}</p>"}</div></section>
<section><h2>{_e(t("report.evidence"))}</h2>{gallery}</section>
<section><h2>{_e(t("report.files"))}</h2><p>{links}</p><p class="muted mono">{_e(t("report.hash", hash=result.scenario_hash))}</p></section>
</main></body></html>
"""
