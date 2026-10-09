from __future__ import annotations

import io
import json
import tarfile
import zipfile

import pytest

from setup_graphcal import core
from setup_graphcal.core import SetupError

DIGEST = "1d2df28f885bbd88ea3a07725b36f573f5ed90c2c969c3e7ab30ffae4cc56619"


@pytest.mark.parametrize(
    ("runner_os", "runner_arch", "archive", "member", "binary"),
    [
        (
            "Linux",
            "X64",
            "graphcal-x86_64-unknown-linux-musl.tar.gz",
            "graphcal-x86_64-unknown-linux-musl/graphcal",
            "graphcal",
        ),
        (
            "Linux",
            "ARM64",
            "graphcal-aarch64-unknown-linux-musl.tar.gz",
            "graphcal-aarch64-unknown-linux-musl/graphcal",
            "graphcal",
        ),
        (
            "macOS",
            "X64",
            "graphcal-x86_64-apple-darwin.tar.gz",
            "graphcal-x86_64-apple-darwin/graphcal",
            "graphcal",
        ),
        (
            "macOS",
            "ARM64",
            "graphcal-aarch64-apple-darwin.tar.gz",
            "graphcal-aarch64-apple-darwin/graphcal",
            "graphcal",
        ),
        (
            "Windows",
            "X64",
            "graphcal-x86_64-pc-windows-msvc.zip",
            "graphcal.exe",
            "graphcal.exe",
        ),
    ],
)
def test_asset_for(runner_os: str, runner_arch: str, archive: str, member: str, binary: str):
    asset = core.asset_for(runner_os, runner_arch)
    assert (asset.archive, asset.member, asset.binary) == (archive, member, binary)


@pytest.mark.parametrize(
    ("runner_os", "runner_arch"),
    [("Windows", "ARM64"), ("Linux", "X86"), ("Linux", "ARM"), ("FreeBSD", "X64")],
)
def test_asset_for_unsupported(runner_os: str, runner_arch: str):
    with pytest.raises(SetupError, match="no prebuilt graphcal"):
        core.asset_for(runner_os, runner_arch)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("latest", "latest"),
        ("", "latest"),
        ("0.0.1-alpha.35", "0.0.1-alpha.35"),
        ("v0.0.1-alpha.35", "0.0.1-alpha.35"),
        ("1.2.3", "1.2.3"),
        ("1.2.3+build.5", "1.2.3+build.5"),
    ],
)
def test_normalize_version(value: str, expected: str):
    assert core.normalize_version(value) == expected


@pytest.mark.parametrize(
    "value",
    ["0.0", "1", "vv1.2.3", "Latest", "1.2.3; rm -rf /", "1.2.3/../../x", "1.2.3\n", " 1.2.3"],
)
def test_normalize_version_invalid(value: str):
    with pytest.raises(SetupError, match="invalid version"):
        core.normalize_version(value)


def test_download_url():
    assert core.download_url("0.0.1-alpha.35", "graphcal-x86_64-pc-windows-msvc.zip") == (
        "https://github.com/graphcal-lang/graphcal/releases/download/"
        "v0.0.1-alpha.35/graphcal-x86_64-pc-windows-msvc.zip"
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"tag_name":"v0.0.1-alpha.35","name":"0.0.1-alpha.35"}', "0.0.1-alpha.35"),
        (json.dumps({"tag_name": "v1.0.0", "assets": []}, indent=2), "1.0.0"),
    ],
)
def test_parse_release_version(body: str, expected: str):
    assert core.parse_release_version(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        '{"message":"Not Found"}',
        '{"tag_name":"nightly"}',
        '{"tag_name":"latest"}',
        '{"tag_name":1}',
        "[]",
        "<html>",
    ],
)
def test_parse_release_version_invalid(body: str):
    with pytest.raises(SetupError):
        core.parse_release_version(body)


@pytest.mark.parametrize("value", [DIGEST, f"sha256:{DIGEST}", DIGEST.upper(), f" {DIGEST}\n"])
def test_normalize_sha256(value: str):
    assert core.normalize_sha256(value) == DIGEST


@pytest.mark.parametrize("value", ["", DIGEST[1:], f"{DIGEST}0", "z" * 64, f"md5:{DIGEST}"])
def test_normalize_sha256_invalid(value: str):
    with pytest.raises(SetupError, match="invalid SHA-256"):
        core.normalize_sha256(value)


@pytest.mark.parametrize(
    "text",
    [
        # dist writes `<digest> *<file>` followed by a blank line.
        f"{DIGEST} *graphcal-aarch64-apple-darwin.tar.gz\n\n",
        f"{DIGEST}  graphcal-aarch64-apple-darwin.tar.gz",
        DIGEST,
    ],
)
def test_parse_sha256_file(text: str):
    assert core.parse_sha256_file(text) == DIGEST


@pytest.mark.parametrize("text", ["", "\n", "<html>Not Found</html>"])
def test_parse_sha256_file_invalid(text: str):
    with pytest.raises(SetupError):
        core.parse_sha256_file(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("graphcal 0.0.1-alpha.35 (commit: 106312a)\n", "0.0.1-alpha.35"),
        ("graphcal 1.0.0", "1.0.0"),
    ],
)
def test_parse_version_output(text: str, expected: str):
    assert core.parse_version_output(text) == expected


@pytest.mark.parametrize("text", ["", "graphcal", "error: unknown option", "other 1.0.0"])
def test_parse_version_output_invalid(text: str):
    with pytest.raises(SetupError, match="unexpected"):
        core.parse_version_output(text)


def make_tar_gz(files: dict[str, bytes], directories: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name in directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            tf.addfile(info)
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


LINUX = core.asset_for("Linux", "X64")
WINDOWS = core.asset_for("Windows", "X64")


def test_read_executable_tar_gz():
    archive = make_tar_gz(
        {f"{LINUX.member}": b"ELF", "graphcal-x86_64-unknown-linux-musl/README.md": b"readme"},
        directories=("graphcal-x86_64-unknown-linux-musl",),
    )
    assert core.read_executable(archive, LINUX) == b"ELF"


def test_read_executable_zip():
    archive = make_zip({"graphcal.exe": b"MZ", "README.md": b"readme"})
    assert core.read_executable(archive, WINDOWS) == b"MZ"


@pytest.mark.parametrize(
    ("archive", "asset", "match"),
    [
        (make_tar_gz({"graphcal": b"ELF"}), LINUX, "not found"),
        (make_tar_gz({}, directories=(LINUX.member,)), LINUX, "not a regular file"),
        (make_zip({"bin/graphcal.exe": b"MZ"}), WINDOWS, "not found"),
        (b"not an archive", LINUX, "could not read"),
        (b"not an archive", WINDOWS, "could not read"),
    ],
)
def test_read_executable_invalid(archive: bytes, asset: core.Asset, match: str):
    with pytest.raises(SetupError, match=match):
        core.read_executable(archive, asset)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("checksum mismatch", "::error title=setup-graphcal::checksum mismatch"),
        ("100% done\nnext\r", "::error title=setup-graphcal::100%25 done%0Anext%0D"),
    ],
)
def test_error_command(message: str, expected: str):
    assert core.error_command(message) == expected
