"""`rpa run` 的入參：檔案入參（M7c）在命令列寫這台電腦上的路徑或場景附件。"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_core.i18n import use_locale

SCENE = """\
schemaVersion: 1
id: cli-upload
name: 命令列上傳
inputs:
  title: { type: string }
  orders: { type: file }
  photos: { type: file, multiple: true }
steps:
  - id: open
    action: goto
    url: about:blank
"""


def test_file_inputs_from_the_command_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scene.yaml").write_text(SCENE, encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_execute(path: Path, inputs: dict[str, object], **options: object) -> object:
        seen.update(inputs=inputs, options=options)
        raise SystemExit(0)

    monkeypatch.setattr("rpa_cli.run.execute", fake_execute)
    with use_locale("zh-Hant"):
        install_click_translations()
        result = CliRunner().invoke(
            build_cli(),
            [
                "run",
                "scene.yaml",
                "-i",
                "title=一",
                "-i",
                "title=二",
                "-i",
                "orders=data/訂單.xlsx",
                "-i",
                "photos=files/a.png",
                "-i",
                "photos=b.png",
            ],
        )

    assert result.exit_code == 0, result.output
    assert seen["inputs"] == {
        "title": "二",
        "orders": {"path": str(tmp_path / "data" / "訂單.xlsx")},
        "photos": ["files/a.png", {"path": str(tmp_path / "b.png")}],
    }
    options = seen["options"]
    assert isinstance(options, dict)
    assert options["any_path"] is True
