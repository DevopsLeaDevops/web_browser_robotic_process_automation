"""產品的版本（M10.1 PR 3）：伺服器、Worker、錄製端用同一個版本，發布標籤是 ``v版本``。

    python tools/release_version.py current          印出目前的版本
    python tools/release_version.py bump 0.2.0       一次改全部套件（packages/*、apps/*）與 uv.lock
    python tools/release_version.py check v0.2.0     發布前確認：標籤格式、套件與 uv.lock 都一致

版本只用 ``主.次.修``（數字）：Inno Setup 的檔案版本與建置資訊都用它。
發布流程：在功能分支執行 bump → PR 合併 → 在 main 上打標籤並推送 → CI 建好安裝檔、建立草稿 Release →
維護者確認後按「發布」（.github/workflows/release.yml）。只用標準函式庫，不需要先安裝依賴。
"""

import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

__all__ = ["check", "current", "packages", "set_version"]

ROOT: Final = Path(__file__).resolve().parent.parent
VERSION: Final = re.compile(r"^\d+\.\d+\.\d+$")
TAG: Final = re.compile(r"^v(\d+\.\d+\.\d+)$")
_PROJECT_VERSION: Final = re.compile(r'(?m)^version = "[^"]*"$')
_LOCK_ENTRY: Final = (
    r'(\[\[package\]\]\nname = "{name}"\nversion = )"[^"]*"(\nsource = \{{ (?:editable|virtual) = )'
)


def packages(root: Path = ROOT) -> dict[str, Path]:
    """工作區的套件：{名稱: pyproject.toml}。"""
    found: dict[str, Path] = {}
    for path in sorted(
        [*root.glob("packages/*/pyproject.toml"), *root.glob("apps/*/pyproject.toml")]
    ):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project = cast("dict[str, object]", data.get("project") or {})
        name = project.get("name")
        if isinstance(name, str):
            found[name] = path
    return found


def versions(root: Path = ROOT) -> dict[str, str]:
    """每個套件的版本（pyproject.toml）。"""
    result: dict[str, str] = {}
    for name, path in packages(root).items():
        project = cast(
            "dict[str, object]", tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        )
        result[name] = str(project.get("version"))
    return result


def lock_versions(root: Path = ROOT) -> dict[str, str]:
    """uv.lock 裡工作區套件的版本。"""
    lock = root / "uv.lock"
    if not lock.is_file():
        return {}
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    entries = cast("list[dict[str, object]]", data.get("package") or [])
    names = set(packages(root))
    return {
        str(entry["name"]): str(entry.get("version"))
        for entry in entries
        if entry.get("name") in names
    }


def current(root: Path = ROOT) -> str:
    """目前的版本；套件之間不一致時拋出 ValueError。"""
    found = set(versions(root).values())
    if len(found) != 1:
        raise ValueError(f"套件的版本不一致：{versions(root)}")
    return found.pop()


def set_version(version: str, root: Path = ROOT) -> list[Path]:
    """把每個套件與 uv.lock 改成 ``version``；回傳改過的檔案。"""
    if not VERSION.fullmatch(version):
        raise ValueError(f"版本要是「主.次.修」的數字：{version}")
    changed: list[Path] = []
    for path in packages(root).values():
        text = path.read_text(encoding="utf-8")
        updated, count = _PROJECT_VERSION.subn(f'version = "{version}"', text, count=1)
        if count != 1:
            raise ValueError(f"{path} 沒有 version")
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path)
    lock = root / "uv.lock"
    if lock.is_file():
        text = lock.read_text(encoding="utf-8")
        updated = text
        for name in packages(root):
            pattern = re.compile(_LOCK_ENTRY.format(name=re.escape(name)))
            updated = pattern.sub(
                lambda match: f'{match.group(1)}"{version}"{match.group(2)}', updated
            )
        if updated != text:
            lock.write_text(updated, encoding="utf-8")
            changed.append(lock)
    return changed


def check(tag: str, root: Path = ROOT) -> list[str]:
    """發布前的檢查；回傳問題（空的代表可以發布）。"""
    match = TAG.fullmatch(tag)
    if match is None:
        return [f"標籤要是 v主.次.修，例如 v0.2.0：{tag}"]
    version = match.group(1)
    problems = [
        f"{name} 的版本是 {found}，標籤是 {version}"
        for name, found in versions(root).items()
        if found != version
    ]
    problems += [
        f"uv.lock 裡 {name} 的版本是 {found}，標籤是 {version}（執行 bump 或 uv lock）"
        for name, found in lock_versions(root).items()
        if found != version
    ]
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["current"]:
        sys.stdout.write(current() + "\n")
        return 0
    if len(args) == 2 and args[0] == "bump":
        for path in set_version(args[1]):
            sys.stdout.write(f"已更新 {path.relative_to(ROOT)}\n")
        return 0
    if len(args) == 2 and args[0] == "check":
        problems = check(args[1])
        for problem in problems:
            sys.stdout.write(f"::error title=版本::{problem}\n")
        if not problems:
            sys.stdout.write(f"版本一致：{args[1]}\n")
        return 1 if problems else 0
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
