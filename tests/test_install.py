from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from setup_graphcal import core, install
from setup_graphcal.core import SetupError

from .test_core import make_tar_gz

VERSION = "0.0.1-alpha.35"
ASSET = core.asset_for("Linux", "X64")
ARCHIVE = make_tar_gz({ASSET.member: b"ELF"})
DIGEST = hashlib.sha256(ARCHIVE).hexdigest()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "path").touch()
    (tmp_path / "output").touch()
    return {
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "RUNNER_TEMP": str(tmp_path / "temp"),
        "GITHUB_PATH": str(tmp_path / "path"),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "GITHUB_SERVER_URL": "https://github.com",
        "INPUT_VERSION": "latest",
        "INPUT_CHECKSUM": "",
        "INPUT_GITHUB_TOKEN": "token",
    }


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Fake the network and `graphcal --version`; record (url, token) of each request."""
    responses = {
        core.LATEST_RELEASE_API: json.dumps({"tag_name": f"v{VERSION}"}).encode(),
        core.download_url(VERSION, ASSET.archive): ARCHIVE,
        core.download_url(
            VERSION, f"{ASSET.archive}.sha256"
        ): f"{DIGEST} *{ASSET.archive}\n\n".encode(),
    }
    seen: list[tuple[str, str]] = []

    def fake_fetch(url: str, *, headers: object = None, token: str = "") -> bytes:
        seen.append((url, token))
        if url not in responses:
            msg = f"GET {url}: HTTP 404 Not Found"
            raise SetupError(msg)
        return responses[url]

    monkeypatch.setattr(install, "fetch", fake_fetch)
    monkeypatch.setattr(install, "installed_version", lambda _binary: VERSION)
    return seen


def test_install_latest(env: dict[str, str], requests: list[tuple[str, str]]):
    install.install(env)

    install_dir = Path(env["RUNNER_TEMP"]) / "setup-graphcal" / VERSION / ASSET.target
    binary = install_dir / "graphcal"
    assert binary.read_bytes() == b"ELF"
    assert Path(env["GITHUB_PATH"]).read_text() == f"{install_dir}\n"
    assert Path(env["GITHUB_OUTPUT"]).read_text() == f"version={VERSION}\npath={binary}\n"
    # The token is sent to the API only.
    assert requests == [
        (core.LATEST_RELEASE_API, "token"),
        (core.download_url(VERSION, ASSET.archive), ""),
        (core.download_url(VERSION, f"{ASSET.archive}.sha256"), ""),
    ]


def test_install_does_not_send_token_off_github_com(
    env: dict[str, str], requests: list[tuple[str, str]]
):
    env["GITHUB_SERVER_URL"] = "https://ghe.example.com"
    install.install(env)
    assert requests[0] == (core.LATEST_RELEASE_API, "")


def test_install_pinned_with_checksum(env: dict[str, str], requests: list[tuple[str, str]]):
    env["INPUT_VERSION"] = VERSION
    env["INPUT_CHECKSUM"] = f"sha256:{DIGEST.upper()}"
    install.install(env)
    assert [url for url, _ in requests] == [core.download_url(VERSION, ASSET.archive)]


def test_install_checksum_mismatch(env: dict[str, str], requests: list[tuple[str, str]]):
    env["INPUT_CHECKSUM"] = "0" * 64
    with pytest.raises(SetupError, match="checksum mismatch"):
        install.install(env)
    assert not (Path(env["RUNNER_TEMP"]) / "setup-graphcal").exists()
    assert Path(env["GITHUB_PATH"]).read_text() == ""


def test_install_release_without_binaries(env: dict[str, str], requests: list[tuple[str, str]]):
    env["INPUT_VERSION"] = "0.0.1-alpha.34"
    with pytest.raises(SetupError, match="prebuilt binaries are available from"):
        install.install(env)


def test_install_version_mismatch(
    env: dict[str, str],
    requests: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(install, "installed_version", lambda _binary: "0.0.1-alpha.36")
    with pytest.raises(SetupError, match=r"reports version 0\.0\.1-alpha\.36"):
        install.install(env)
    assert Path(env["GITHUB_PATH"]).read_text() == ""


def test_main_reports_error(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    env["INPUT_VERSION"] = "0.0"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert install.main() == 1
    assert capsys.readouterr().out.startswith(
        "::error title=setup-graphcal::invalid version: '0.0'"
    )
