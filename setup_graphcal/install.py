"""IO of setup-graphcal: downloads, files, and processes. The logic is in core.

Reads the action inputs (INPUT_VERSION, INPUT_CHECKSUM, INPUT_GITHUB_TOKEN)
and the runner's environment from os.environ.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from setup_graphcal import core
from setup_graphcal.core import SetupError

_ATTEMPTS = 4
_TIMEOUT_SECONDS = 60


def log(message: str) -> None:
    print(f"setup-graphcal: {message}", flush=True)


def fetch(url: str, *, headers: Mapping[str, str] | None = None, token: str = "") -> bytes:
    """GET a URL, retrying network errors and 5xx responses."""
    if not url.startswith("https://"):
        msg = f"refusing to fetch a non-HTTPS URL: {url}"
        raise SetupError(msg)
    # S310: the scheme is checked above.
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "setup-graphcal", **(headers or {})}
    )
    if token:
        # Unlike add_header, this is not forwarded when the server redirects.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == _ATTEMPTS:
                msg = f"GET {url}: HTTP {e.code} {e.reason}"
                raise SetupError(msg) from e
            error: Exception = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == _ATTEMPTS:
                msg = f"GET {url}: {e}"
                raise SetupError(msg) from e
            error = e
        log(f"retrying GET {url} after error: {error}")
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def resolve_latest(env: Mapping[str, str]) -> str:
    # The workflow token belongs to the GitHub instance running the job; only
    # send it to the github.com API.
    on_github_com = env.get("GITHUB_SERVER_URL", "https://github.com") == "https://github.com"
    token = env.get("INPUT_GITHUB_TOKEN", "") if on_github_com else ""
    body = fetch(
        core.LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        token=token,
    )
    return core.parse_release_version(body.decode("utf-8"))


def download_archive(version: str, asset: core.Asset) -> bytes:
    url = core.download_url(version, asset.archive)
    log(f"downloading {url}")
    try:
        return fetch(url)
    except SetupError as e:
        msg = (
            f"could not download {asset.archive} for v{version} "
            f"(prebuilt binaries are available from v{core.FIRST_BINARY_RELEASE}): {e}"
        )
        raise SetupError(msg) from e


def expected_sha256(version: str, asset: core.Asset, checksum_input: str) -> str:
    if checksum_input:
        return core.normalize_sha256(checksum_input)
    text = fetch(core.download_url(version, f"{asset.archive}.sha256")).decode("utf-8")
    return core.parse_sha256_file(text)


def installed_version(binary: Path) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        msg = f"could not run {binary} --version: {e}"
        raise SetupError(msg) from e
    return core.parse_version_output(result.stdout)


def append_line(path: str, line: str) -> None:
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(f"{line}\n")


def install(env: Mapping[str, str]) -> None:
    version = core.normalize_version(env.get("INPUT_VERSION", core.LATEST))
    if version == core.LATEST:
        version = resolve_latest(env)
        log(f"resolved latest to {version}")
    asset = core.asset_for(env["RUNNER_OS"], env["RUNNER_ARCH"])

    archive = download_archive(version, asset)
    expected = expected_sha256(version, asset, env.get("INPUT_CHECKSUM", ""))
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        msg = f"checksum mismatch for {asset.archive}: expected {expected}, got {actual}"
        raise SetupError(msg)
    log(f"verified sha256 {actual}")

    install_dir = Path(env["RUNNER_TEMP"]) / "setup-graphcal" / version / asset.target
    shutil.rmtree(install_dir, ignore_errors=True)
    install_dir.mkdir(parents=True)
    binary = install_dir / asset.binary
    binary.write_bytes(core.read_executable(archive, asset))
    binary.chmod(0o755)

    reported = installed_version(binary)
    if reported != version:
        msg = f"installed graphcal reports version {reported}, expected {version}"
        raise SetupError(msg)
    log(f"installed graphcal {reported} to {install_dir}")

    append_line(env["GITHUB_PATH"], str(install_dir))
    append_line(env["GITHUB_OUTPUT"], f"version={version}")
    append_line(env["GITHUB_OUTPUT"], f"path={binary}")


def main() -> int:
    try:
        install(os.environ)
    except SetupError as e:
        print(core.error_command(str(e)), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
