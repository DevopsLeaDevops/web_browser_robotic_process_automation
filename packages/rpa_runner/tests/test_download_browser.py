"""「瀏覽器＋Python」組合場景（ADR 0020）：DSL 下載 → Python 節點彙總 → DSL 上傳。

用 scenarios/examples/browser-python 的三個場景，照組合運行的方式依序執行：同一個共用工作資料夾，
上游的出參直接當下游的入參。Python 節點用假的運行環境（標準函式庫的 venv），和
test_python_nodes.py 相同；要瀏覽器（Chromium）與本機測試網站。
"""

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.pyruntime import ENV_RUNTIME, MANIFEST, platform_tag
from rpa_runner.run import execute
from testsite.browsers import require_engine
from testsite.server import export_csv, running

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "scenarios" / "examples" / "browser-python"

pytestmark = pytest.mark.browser


@pytest.fixture
def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    root = tmp_path / "runtime"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root)], check=True)
    manifest = {"version": "1.0.0", "platform": platform_tag(), "python": sys.version.split()[0]}
    (root / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(ENV_RUNTIME, str(root))
    monkeypatch.setenv("RPA_CACHE_DIR", str(tmp_path / "cache"))
    with use_locale("zh-Hant"):
        yield


@pytest.mark.usefixtures("_runtime")
def test_download_summarize_upload(tmp_path: Path) -> None:
    require_engine("chromium")
    workspace = tmp_path / "workspace"
    runs = tmp_path / "runs"
    with running() as url:
        download = execute(
            EXAMPLE / "download-sales.yaml",
            {"month": "2026-11"},
            out_root=runs,
            base_url=url,
            engine="chromium",
            workspace=workspace,
        )
        assert download.status == "passed", (download.error, download.problems)
        assert download.output is not None
        report = cast("dict[str, object]", download.output["report"])
        name, body = export_csv("2026-11")
        assert report["name"] == name  # 網站給的中文檔名
        assert report["size"] == len(body)
        assert report["workspace"] == f"downloads/{name}"
        assert (workspace / "downloads" / name).read_bytes() == body
        assert (download.directory / "outputs" / name).read_bytes() == body
        steps = download.steps or []
        assert steps[-1]["files"] == [name]

        summary = execute(
            EXAMPLE / "summarize-sales" / "scenario.yaml",
            {"report": report},
            out_root=runs,
            workspace=workspace,
        )
        assert summary.status == "passed", (summary.error, summary.problems)
        assert summary.output is not None
        totals = cast("dict[str, int]", summary.output["byBranch"])
        assert set(totals) == {"台北", "高雄", "台中"}
        assert summary.output["total"] == sum(totals.values())
        produced = cast("dict[str, object]", summary.output["summary"])
        assert produced["name"] == "分店彙總.csv"

        upload = execute(
            EXAMPLE / "upload-summary.yaml",
            {"summary": produced},
            out_root=runs,
            base_url=url,
            engine="chromium",
            workspace=workspace,
        )
        assert upload.status == "passed", (upload.error, upload.problems)
        assert upload.output == {"receivedName": "分店彙總.csv"}
