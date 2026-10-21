"""開發環境安裝瀏覽器：實測目前版本的下載檔，當次使用最快來源。

由 setup.sh／setup.ps1 在 uv sync 後執行；不新增依賴、不修改全域環境或 Playwright。
測速子程序限制時間與讀取量，避免 DNS／慢速回應讓安裝一直等候。
"""

import argparse
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from http.client import HTTPResponse
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

MIRROR = "https://cdn.npmmirror.com/binaries/playwright"
SAMPLE_BYTES = 2 * 1024 * 1024
PROBE_SECONDS = 5.0
BUDGET_SECONDS = 30.0
HOST_KEYS = (
    "PLAYWRIGHT_DOWNLOAD_HOST",
    "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
    "PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST",
)
COMMAND = [sys.executable, "-m", "playwright", "install", "chromium", "firefox"]


@dataclass(frozen=True)
class Artifact:
    name: str
    location: Path
    urls: tuple[str, ...]

    @property
    def host_key(self) -> str:
        if self.name.startswith("chromium"):
            return "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"
        if self.name.startswith("firefox"):
            return "PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST"
        return "PLAYWRIGHT_DOWNLOAD_HOST"

    @property
    def relative_url(self) -> str:
        return "builds/" + self.urls[0].split("/builds/", 1)[1]

    @property
    def installed(self) -> bool:
        # Playwright 安裝完成後寫入的標記；只有目錄但下載未完成仍要安裝。
        return (self.location / "INSTALLATION_COMPLETE").is_file()


@dataclass(frozen=True)
class Sample:
    size: int
    elapsed: float
    digest: str
    total: int


def parse_plan(output: str) -> list[Artifact]:
    """使用已安裝 Playwright 的 dry-run，版本、CPU、平台及快取路徑都由它決定。"""
    artifacts: list[Artifact] = []
    for block in re.split(r"\n\s*\n", output.strip()):
        name = re.search(r"\(playwright ([\w-]+) v\d+\)", block)
        location = re.search(r"^\s*Install location:\s+(.+)$", block, re.M)
        urls = tuple(
            match[1]
            for match in re.finditer(r"^\s*Download (?:url|fallback \d+):\s+(\S+)$", block, re.M)
        )
        if not name or not location or not urls:
            raise ValueError("無法辨識 Playwright 下載清單")
        if any(urlsplit(url).scheme != "https" or "/builds/" not in url for url in urls):
            raise ValueError("Playwright 下載網址格式已變更")
        artifacts.append(Artifact(name[1], Path(location[1].strip()), urls))
    if not artifacts:
        raise ValueError("Playwright 沒有傳回下載清單")
    return artifacts


def explicit_host(env: Mapping[str, str]) -> bool:
    # 與 Playwright 的 getFromENV 相同，也尊重 npm 的設定入口。
    return any(
        env.get(name)
        for key in HOST_KEYS
        for name in (key, "npm_config_" + key.lower(), "npm_package_config_" + key.lower())
    )


def download_sample(url: str) -> Sample:
    context = ssl.create_default_context()
    if extra_ca := os.environ.get("NODE_EXTRA_CA_CERTS"):
        context.load_verify_locations(extra_ca)
    request = urllib.request.Request(
        url, headers={"Range": f"bytes=0-{SAMPLE_BYTES - 1}", "Accept-Encoding": "identity"}
    )
    start = time.monotonic()
    with cast(
        HTTPResponse, urllib.request.urlopen(request, timeout=4, context=context)
    ) as response:
        if response.status == 206:
            match = re.fullmatch(r"bytes 0-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
            if not match or int(match[1]) + 1 != min(SAMPLE_BYTES, int(match[2])):
                raise ValueError("無效的分段回應")
            total = int(match[2])
        elif response.status == 200:
            # 不支援 Range 的來源只讀取開頭，不下載整包來測速。
            total = int(response.headers.get("Content-Length", "0"))
        else:
            raise ValueError("來源沒有傳回下載檔")
        expected = min(SAMPLE_BYTES, total)
        if expected < 4:
            raise ValueError("來源沒有傳回有效檔案大小")
        data = response.read(expected)
        if len(data) != expected or not data.startswith(b"PK\x03\x04"):
            raise ValueError("來源傳回錯誤頁或不完整的 ZIP 片段")
    return Sample(
        len(data), max(time.monotonic() - start, 0.001), hashlib.sha256(data).hexdigest(), total
    )


def probe(url: str, timeout: float) -> Sample | None:
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--probe", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            return None
        value = cast(dict[str, object], json.loads(result.stdout))
        return Sample(
            int(str(value["size"])),
            float(str(value["elapsed"])),
            str(value["digest"]),
            int(str(value["total"])),
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        return None


def candidates(artifacts: Sequence[Artifact]) -> list[str]:
    # 同一 HOST 變數作用的每個檔案都測；包含 Chromium 的 headless shell。
    hosts = list(
        dict.fromkeys(url.split("/builds/", 1)[0] for item in artifacts for url in item.urls)
    )
    return [*hosts, MIRROR]


def choose_host(artifacts: Sequence[Artifact], deadline: float) -> str | None:
    results: list[tuple[str, list[Sample]]] = []
    label = ", ".join(item.name for item in artifacts)
    print(f"  · 測速：{label}（每個檔案最多 2 MiB）", flush=True)
    for host in candidates(artifacts):
        samples: list[Sample] = []
        for item in artifacts:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sample = probe(f"{host}/{item.relative_url}", min(PROBE_SECONDS, remaining))
            if sample is None:
                break
            samples.append(sample)
        if len(samples) == len(artifacts):
            results.append((host, samples))
        else:
            print(f"    {host}：無法完成測速（不可用、逾時或測速預算已用完）", flush=True)
    baseline = next((samples for host, samples in results if host != MIRROR), None)
    ranked: list[tuple[float, str]] = []
    for host, samples in results:
        if baseline is not None and any(
            (sample.digest, sample.total) != (reference.digest, reference.total)
            for sample, reference in zip(samples, baseline, strict=True)
        ):
            print(f"    {host}：檔案大小或片段內容與官方來源不同，略過", flush=True)
            continue
        speed = sum(sample.size for sample in samples) / sum(sample.elapsed for sample in samples)
        print(f"    {host}：{speed / 1024 / 1024:.2f} MiB/s", flush=True)
        ranked.append((speed, host))
    if not ranked:
        print(f"  · {label} 沒有可用測速結果，使用 Playwright 原始來源。", flush=True)
        return None
    chosen = max(ranked, key=lambda item: item[0])[1]
    print(f"  ✓ {label} 使用測速最快的來源：{chosen}", flush=True)
    return chosen


def select_hosts(artifacts: Sequence[Artifact]) -> dict[str, str]:
    selected: dict[str, str] = {}
    deadline = time.monotonic() + BUDGET_SECONDS
    # 先測瀏覽器本身，最後測 FFmpeg／Windows 的 winldd；全部合計最多 30 秒。
    for key in (*HOST_KEYS[1:], HOST_KEYS[0]):
        pending = [item for item in artifacts if item.host_key == key and not item.installed]
        if key == HOST_KEYS[0] and any(
            item.host_key != key and not item.installed and item.host_key not in selected
            for item in artifacts
        ):
            # 通用 HOST 也會套用到瀏覽器，不能覆蓋沒有測速結果的官方 fallback 清單。
            continue
        if pending and (host := choose_host(pending, deadline)):
            selected[key] = host
    return selected


def install() -> int:
    env = dict(os.environ)
    if explicit_host(env):
        print("  · 已指定 Playwright 下載來源，略過自動測速並沿用設定。", flush=True)
        return subprocess.call(COMMAND, env=env)
    try:
        plan = subprocess.run(
            [*COMMAND, "--dry-run"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=True,
        )
        artifacts = parse_plan(plan.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        print("  · 無法取得下載清單，改用 Playwright 原始安裝流程。", flush=True)
        return subprocess.call(COMMAND, env=env)
    if all(item.installed for item in artifacts):
        print("  ✓ 瀏覽器與輔助元件已下載，略過測速。", flush=True)
    selected = select_hosts(artifacts)
    code = subprocess.call(COMMAND, env={**env, **selected})
    if code and selected:
        print("  · 自動選擇的來源安裝失敗，改用 Playwright 原始來源重試。", flush=True)
        return subprocess.call(COMMAND, env=env)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        try:
            print(json.dumps(asdict(download_sample(args.probe))))
            return 0
        except (OSError, ValueError):
            return 1
    return install()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
