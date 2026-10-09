"""IO of setup-graphcal: downloads, files, and processes. The logic is in core.

Reads the action inputs (INPUT_VERSION, INPUT_CHECKSUM, INPUT_GITHUB_TOKEN)
and the runner's environment from os.environ.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from setup_graphcal import core
from setup_graphcal.core import SetupError

if TYPE_CHECKING:
    from collections.abc import Mapping

_RETRY_DELAYS_SECONDS = (2, 4, 8)
_TIMEOUT_SECONDS = 60


class _RetryableError(SetupError):
    """A network error or a 5xx response that may succeed when retried."""


def emit(line: str) -> None:
    """Write a line to stdout, where the runner reads workflow commands from."""
    print(line, flush=True)  # noqa: T201


def log(message: str) -> None:
    """Log a progress message."""
    emit(f"setup-graphcal: {message}")


def _get(request: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (fetch checks the scheme)
            return response.read()
    except urllib.error.HTTPError as e:
        msg = f"GET {request.full_url}: HTTP {e.code} {e.reason}"
        if e.code >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise _RetryableError(msg) from e
        raise SetupError(msg) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        msg = f"GET {request.full_url}: {e}"
        raise _RetryableError(msg) from e


def fetch(url: str, *, headers: Mapping[str, str] | None = None, token: str = "") -> bytes:
    """GET a URL, retrying network errors and 5xx responses."""
    if not url.startswith("https://"):
        msg = f"refusing to fetch a non-HTTPS URL: {url}"
        raise SetupError(msg)
    request = urllib.request.Request(url, headers={"User-Agent": "setup-graphcal", **(headers or {})})  # noqa: S310 (scheme checked above)
    if token:
        # Unlike add_header, this is not forwarded when the server redirects.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    for delay in _RETRY_DELAYS_SECONDS:
        try:
            return _get(request)
        except _RetryableError as e:  # noqa: PERF203 (retry loop; network time dominates)
            log(f"retrying in {delay}s after error: {e}")
            time.sleep(delay)
    return _get(request)


def resolve_latest(env: Mapping[str, str]) -> str:
    """Return the version of the latest release through the GitHub API."""
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
    """Download the release archive into memory."""
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
    """Return the expected digest: the `checksum` input, or the published `.sha256` file."""
    if checksum_input:
        return core.normalize_sha256(checksum_input)
    text = fetch(core.download_url(version, f"{asset.archive}.sha256")).decode("utf-8")
    return core.parse_sha256_file(text)


def installed_version(binary: Path) -> str:
    """Return the version reported by `graphcal --version`."""
    try:
        result = subprocess.run(  # noqa: S603 (runs the binary just installed)
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
    """Append a line to a runner file such as GITHUB_PATH or GITHUB_OUTPUT."""
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(f"{line}\n")


def install(env: Mapping[str, str]) -> None:
    """Install graphcal as the action inputs in `env` request."""
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
    """Run the action and return the exit status."""
    try:
        install(os.environ)
    except SetupError as e:
        emit(core.error_command(str(e)))
        return 1
    return 0
