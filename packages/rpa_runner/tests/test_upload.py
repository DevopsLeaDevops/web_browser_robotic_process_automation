"""上傳檔案（M7c）：檔案入參的三種來源、upload 的三種方式、選擇檔案視窗的提醒與錯誤訊息。

用測試網站的 /upload（收到檔案後在頁面顯示檔名、大小與 sha256）。每個情境在 Chromium 與
Firefox 各跑一次；本機沒有某種瀏覽器時略過，CI 設定 RPA_REQUIRE_BROWSER=1 時缺瀏覽器直接失敗。
"""

import hashlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.files import INPUT, STEPS
from rpa_runner.run import execute
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "scenarios" / "examples" / "upload-form"
FILE_ID = "0123456789abcdef0123456789abcdef"
HEADER = """\
schemaVersion: 1
id: upload-cases
name: 上傳的各種情況
browser: { baseUrl: http://127.0.0.1:8765 }
defaults: { timeout: 8000 }
"""


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scene(folder: Path, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "scenario.yaml"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def steps_json(directory: Path) -> list[dict[str, object]]:
    return json.loads((directory / STEPS).read_text(encoding="utf-8"))


def test_example_with_attachments_as_defaults(site: str, engine: str, tmp_path: Path) -> None:
    result = execute(EXAMPLE / "scenario.yaml", {}, out_root=tmp_path, base_url=site, engine=engine)

    assert result.status == "passed", (result.error, result.problems, result.steps)
    orders = EXAMPLE / "files" / "orders.csv"
    # 網頁看到的是 name 指定的中文檔名，內容是附件
    assert result.output == {"importedName": "訂單匯入.csv"}
    saved = json.loads((result.directory / INPUT).read_text(encoding="utf-8"))
    assert saved["orderFile"] == {"name": "訂單匯入.csv", "size": 73, "sha256": sha(orders)}
    assert saved["photos"][0]["name"] == "product.png"
    # 執行目錄沒有本機路徑、沒有附件的複本，暫存資料夾已刪掉
    text = json.dumps(saved) + (result.directory / STEPS).read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    assert not (result.directory / "scenario" / "files").exists()
    assert not list(tmp_path.glob(".files-*"))
    uploads = [step for step in steps_json(result.directory) if step["action"] == "upload"]
    assert [step["files"] for step in uploads] == [
        ["訂單匯入.csv"],
        ["product.png"],
        ["訂單匯入.csv"],
    ]


def test_uploaded_files_and_paths(site: str, engine: str, tmp_path: Path) -> None:
    shutil.copytree(EXAMPLE, tmp_path / "scene")
    uploaded = tmp_path / "worker" / FILE_ID
    uploaded.parent.mkdir()
    uploaded.write_bytes("編號,數量\nA-1,2\n".encode())
    share = tmp_path / "share"
    share.mkdir()
    photo = share / "新品.png"
    shutil.copyfile(EXAMPLE / "files" / "product.png", photo)
    inputs: dict[str, object] = {
        "orderFile": {"file": FILE_ID, "name": "十月訂單.csv"},
        "photos": [{"path": str(photo)}, "files/product.png"],
    }

    result = execute(
        tmp_path / "scene" / "scenario.yaml",
        inputs,
        out_root=tmp_path / "runs",
        base_url=site,
        engine=engine,
        uploads={FILE_ID: uploaded},
        input_folders=[share],
    )

    assert result.status == "passed", (result.error, result.problems, result.steps)
    assert result.output == {"importedName": "十月訂單.csv"}
    assert result.input["orderFile"] == {
        "name": "十月訂單.csv",
        "size": uploaded.stat().st_size,
        "sha256": sha(uploaded),
    }
    names = [item["name"] for item in result.input["photos"]]  # type: ignore[union-attr]
    assert names == ["新品.png", "product.png"]


@pytest.mark.parametrize(
    ("inputs", "folders", "expected"),
    [
        ({"orderFile": {"file": FILE_ID, "name": "a.csv"}}, None, "沒有送到這台電腦"),
        ({"orderFile": "files/missing.csv"}, None, "不在這個版本裡"),
        ({"orderFile": {"path": "/etc/hostname"}}, [], "不在允許讀取的資料夾裡"),
        ({"photos": ["files/orders.csv"]}, None, "不是接受的類型"),
    ],
)
def test_file_problems_stop_before_the_browser(
    tmp_path: Path, inputs: dict[str, object], folders: list[Path] | None, expected: str
) -> None:
    result = execute(
        EXAMPLE / "scenario.yaml",
        inputs,
        out_root=tmp_path,
        input_folders=folders,
    )

    assert result.status == "failed"
    assert result.stage("input").status == "failed"
    assert result.stage("automation").status == "skipped"
    assert any(expected in problem for problem in result.problems), result.problems


def test_max_size_and_total(tmp_path: Path) -> None:
    folder = tmp_path / "scene"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "big.bin").write_bytes(b"x" * 2048)
    path = scene(
        folder,
        "inputs:\n  f: { type: file, maxSize: 1KB, default: files/big.bin }\n"
        "steps:\n  - { id: open, action: goto, url: about:blank }\n",
    )
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert any("太大：2 KB，上限是 1 KB" in problem for problem in result.problems)

    path.write_text(
        HEADER + "inputs:\n  f: { type: file, default: files/big.bin }\n"
        "steps:\n  - { id: open, action: goto, url: about:blank }\n",
        encoding="utf-8",
    )
    result = execute(path, {}, out_root=tmp_path / "runs", max_run_bytes=1000)
    assert any("檔案合計太大" in problem for problem in result.problems)


def test_dropzone_clear_and_frame(site: str, engine: str, tmp_path: Path) -> None:
    folder = tmp_path / "scene"
    shutil.copytree(EXAMPLE / "files", folder / "files")
    path = scene(
        folder,
        "inputs:\n"
        "  f: { type: file, default: { attachment: files/orders.csv, name: 拖進來.csv } }\n"
        "steps:\n"
        "  - { id: open, action: goto, url: /upload }\n"
        "  - { id: drop, action: upload, dropzone: { text: 把檔案拖到這裡 },"
        ' files: "{{ inputs.f }}" }\n'
        "  - { id: dropped, action: extract, target: { css: '#drop-result .name' }, as: dropped }\n"
        '  - { id: pick, action: upload, target: { label: 匯入檔案 }, files: "{{ inputs.f }}" }\n'
        "  - { id: clear, action: upload, target: { label: 匯入檔案 }, files: [] }\n"
        "  - { id: none, action: extract, target: { label: 匯入檔案 }, get: value, as: cleared }\n"
        "  - id: cert\n"
        "    action: upload\n"
        "    target: { label: 憑證檔案, frame: { css: '#cert-frame' } }\n"
        '    files: "{{ inputs.f }}"\n'
        "  - id: send-cert\n"
        "    action: click\n"
        "    target: { role: button, name: 送出憑證, frame: { css: '#cert-frame' } }\n"
        "  - id: cert-sha\n"
        "    action: extract\n"
        "    target: { css: '#cert-result .sha', frame: { css: '#cert-frame' } }\n"
        "    as: certSha\n"
        "verify:\n"
        "  - { value: '{{ facts.dropped }}', equals: 拖進來.csv }\n"
        "  - { value: '[{{ facts.cleared }}]', equals: '[]' }\n"
        "  - { value: '{{ facts.certSha }}', equals: '{{ inputs.f.sha256 }}' }\n",
    )

    result = execute(path, {}, out_root=tmp_path / "runs", base_url=site, engine=engine)

    assert result.status == "passed", (result.error, result.problems, result.steps)


def test_file_chooser_without_upload_is_closed_with_a_note(
    site: str, engine: str, tmp_path: Path
) -> None:
    """點擊時才建立的上傳框錄成 click（錄製稿看不出選了檔案）：攔下視窗，步驟照常、記一條提醒。"""
    path = scene(
        tmp_path / "scene",
        "steps:\n"
        "  - { id: open, action: goto, url: /upload }\n"
        "  - { id: attach, action: click, target: { role: button, name: 選擇附件 } }\n"
        "  - { id: after, action: expect, target: { role: heading, name: 附件 },"
        " state: visible }\n",
    )

    result = execute(path, {}, out_root=tmp_path / "runs", base_url=site, engine=engine)

    assert result.status == "passed", (result.error, result.problems, result.steps)
    steps = steps_json(result.directory)
    assert steps[1]["notes"] == [
        "這一步開出了選擇檔案的視窗，沒有指定檔案（已自動關掉）；如果這裡要上傳，"
        "把這一步改成 upload，用 trigger 指定這個元素"
    ]
    assert steps[0]["notes"] == steps[2]["notes"] == []
    log = (result.directory / "automation.log").read_text(encoding="utf-8")
    assert "提醒 這一步開出了選擇檔案的視窗" in log


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            '{ id: up, action: upload, target: { label: 匯入檔案 }, files: "{{ inputs.many }}" }',
            "這個上傳框一次只能選一個檔案",
        ),
        (
            '{ id: up, action: upload, target: { css: "#photo-upload" },'
            ' files: "{{ inputs.one }}" }',
            "這個元素不是上傳框",
        ),
    ],
)
def test_upload_errors_are_explained(
    site: str, engine: str, tmp_path: Path, step: str, expected: str
) -> None:
    folder = tmp_path / "scene"
    shutil.copytree(EXAMPLE / "files", folder / "files")
    path = scene(
        folder,
        "inputs:\n"
        "  one: { type: file, default: files/orders.csv }\n"
        "  many: { type: file, multiple: true, default: [files/orders.csv, files/product.png] }\n"
        "steps:\n"
        "  - { id: open, action: goto, url: /upload }\n"
        f"  - {step}\n",
    )

    result = execute(path, {}, out_root=tmp_path / "runs", base_url=site, engine=engine)

    assert result.status == "failed"
    assert result.error is not None
    assert expected in result.error, result.error
