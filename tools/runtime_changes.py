"""和上一次發布比較環境代號（ADR 0018；2026-10-26 起）。

    uv run python -m tools.runtime_changes --runtime-file runtime-worker-windows-x64.json [...]
        (--previous RPA-Update-0.6.1.zip | --latest) [--notes 說明.md]

環境代號和上一版不同的目標，已經裝好的伺服器與裝置不能只用更新檔升級，要用完整的安裝包
（裝置頁顯示「要用完整的安裝包更新」）。0.6.1 的桌面 App 就是這樣：建置時算進了帶版本號與時間的
套件資訊，每一版的代號都不同，發布時沒有人發現。這個工具讓它在 PR 與發布時就看得到：

- 每個目標印一行：相同（可以用更新檔）、不同（要用完整的安裝包），或上一版沒有這個目標；
- 在 GitHub Actions 裡同時寫成 annotation（不同是 warning）；
- ``--notes``：把「從上一版怎麼升級」附加到 Release 說明用的檔案。

``--previous`` 是上一版的更新檔（或它的 manifest.json）；``--latest`` 用 ``gh api`` 從最新的
已發布 Release 下載（要有 GH_TOKEN，倉庫取 GH_REPO 或 GITHUB_REPOSITORY）。只是提示：找不到
上一版時印出原因，結束碼仍是 0。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from rpa_update.errors import UpdateError
from rpa_update.manifest import MANIFEST, Manifest
from tools.build_update import read_runtime_files

LABELS: Final = {
    "server-linux-x64": ("RPA 伺服器（Linux x64）", "RPA Server (Linux x64)"),
    "server-linux-arm64": ("RPA 伺服器（Linux arm64）", "RPA Server (Linux arm64)"),
    "worker-windows-x64": ("RPA Worker（Windows）", "RPA Worker (Windows)"),
    "worker-macos-arm64": ("RPA Worker（macOS）", "RPA Worker (macOS)"),
    "recorder-macos-arm64": ("RPA 錄製端（macOS）", "RPA Recorder (macOS)"),
}
"""目標在說明裡的名稱（繁中、英文）。"""
UPDATE_NAME: Final = re.compile(r"^RPA-Update-[0-9][0-9A-Za-z.+-]*\.zip$")

type Change = Literal["same", "changed", "new"]


@dataclass(frozen=True, slots=True)
class Result:
    target: str
    change: Change
    current: str
    previous: str | None


def label(target: str, english: bool = False) -> str:
    names = LABELS.get(target)
    return target if names is None else names[1 if english else 0]


def read_previous(path: Path) -> Manifest:
    """上一版的清單：更新檔（zip）或 manifest.json。只讀內容，不驗證簽章（只是提示）。"""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                data = archive.read(MANIFEST)
        else:
            data = path.read_bytes()
        return Manifest.from_bytes(data)
    except (OSError, KeyError, zipfile.BadZipFile, UpdateError) as error:
        raise SystemExit(f"{path} 讀不到更新檔的清單：{error}") from None


def compare(current: Mapping[str, str], previous: Mapping[str, str]) -> list[Result]:
    """每個目標的環境代號和上一版比較。"""
    results: list[Result] = []
    for target, ident in sorted(current.items()):
        before = previous.get(target)
        change: Change = "new" if before is None else "same" if before == ident else "changed"
        results.append(Result(target, change, ident, before))
    return results


def report(results: Sequence[Result], version: str, *, github: bool = False) -> list[str]:
    """每個目標一行；``github`` 時另外寫成 annotation（::notice、::warning）。"""
    lines: list[str] = []
    for item in results:
        name = label(item.target)
        if item.change == "same":
            text = f"和 v{version} 相同（{item.current}）：已經裝好的{name}可以用更新檔升級"
            level = "notice"
        elif item.change == "changed":
            text = (
                f"和 v{version} 不同（{item.previous} → {item.current}）："
                f"已經裝好的{name}要用這一版的完整安裝包更新"
            )
            level = "warning"
        else:
            text = f"v{version} 沒有這個目標（{item.current}）：第一次發布，用完整的安裝包安裝"
            level = "notice"
        lines.append(f"{item.target}: {text}")
        if github:
            lines.append(f"::{level} title=環境代號（{item.target}）::{text}")
    return lines


def notes(results: Sequence[Result], version: str) -> str:
    """Release 說明的「從上一版怎麼升級」。"""
    same = [item.target for item in results if item.change == "same"]
    full = [item.target for item in results if item.change != "same"]

    def names(targets: Sequence[str], english: bool = False) -> str:
        return ("、" if not english else ", ").join(label(target, english) for target in targets)

    lines = [f"## 從 v{version} 升級", ""]
    if same:
        lines.append(
            f"- **用更新檔就好**：{names(same)}。伺服器執行 `bin/rpa update`，"
            "裝置連上伺服器後自動跟著更新。"
        )
    if full:
        lines.append(
            f"- **要用完整的安裝包**：{names(full)}。執行環境（Python、內建的套件或打包工具）"
            f"和 v{version} 不同，更新檔換不了，請下載這一版的安裝包重新安裝；之後環境沒變的版本"
            "就能用更新檔。"
        )
    english: list[str] = []
    if same:
        english.append(f"the update file is enough for {names(same, True)}")
    if full:
        english.append(
            f"{names(full, True)} need the full installer (their runtime changed since v{version})"
        )
    lines += ["", f"Upgrading from v{version}: " + "; ".join(english) + ".", ""]
    return "\n".join(lines)


def download_latest(folder: Path, environ: Mapping[str, str] | None = None) -> Path | None:
    """最新的已發布 Release 的更新檔；沒有 gh、倉庫或那個檔案時印出原因，回傳 None。"""
    env = os.environ if environ is None else environ
    repo = env.get("GH_REPO") or env.get("GITHUB_REPOSITORY")
    gh = shutil.which("gh")
    if not repo or gh is None:
        print("沒有 gh 或倉庫名稱（GH_REPO、GITHUB_REPOSITORY），不比較上一次發布")
        return None
    try:
        completed = subprocess.run(
            [gh, "api", f"repos/{repo}/releases/latest"],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(completed.stdout)
        asset = next(
            (
                item
                for item in info.get("assets", [])
                if UPDATE_NAME.fullmatch(item.get("name", ""))
            ),
            None,
        )
        if asset is None:
            print(f"{info.get('tag_name', '最新的 Release')} 沒有更新檔，不比較")
            return None
        target = folder / str(asset["name"])
        with target.open("wb") as stream:
            subprocess.run(
                [
                    gh,
                    "api",
                    "-H",
                    "Accept: application/octet-stream",
                    f"repos/{repo}/releases/assets/{asset['id']}",
                ],
                stdout=stream,
                check=True,
            )
    except (subprocess.CalledProcessError, ValueError, OSError) as error:
        print(f"下載不到最新 Release 的更新檔，不比較：{error}")
        return None
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="和上一次發布比較環境代號")
    parser.add_argument(
        "--runtime-file",
        action="append",
        default=[],
        type=Path,
        required=True,
        help="這次建置留下的 runtime.json 副本（runtime-<目標>.json）",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--previous", type=Path, help="上一版的更新檔或它的 manifest.json")
    source.add_argument("--latest", action="store_true", help="從最新的已發布 Release 下載")
    parser.add_argument("--notes", type=Path, help="把「從上一版怎麼升級」附加到這個檔案")
    args = parser.parse_args(argv)
    current = {runtime.target: runtime.id for runtime in read_runtime_files(args.runtime_file)}
    with tempfile.TemporaryDirectory() as folder:
        path = args.previous or download_latest(Path(folder))
        if path is None:
            return 0
        previous = read_previous(path)
    results = compare(current, previous.runtimes)
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    for line in report(results, previous.version, github=github):
        print(line)
    if args.notes is not None:
        with args.notes.open("a", encoding="utf-8") as stream:
            stream.write(notes(results, previous.version))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
