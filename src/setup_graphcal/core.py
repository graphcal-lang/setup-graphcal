"""Pure logic of setup-graphcal: no network, filesystem, or process access.

Standard library only, Python 3.10+ (see pyproject.toml).
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import zipfile
from dataclasses import dataclass

REPO = "graphcal-lang/graphcal"
LATEST = "latest"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
# Releases before this one have no prebuilt binaries.
FIRST_BINARY_RELEASE = "0.0.1-alpha.35"

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")

# (runner.os, runner.arch) -> Rust target of the release asset built by dist.
_TARGETS = {
    ("Linux", "X64"): "x86_64-unknown-linux-musl",
    ("Linux", "ARM64"): "aarch64-unknown-linux-musl",
    ("macOS", "X64"): "x86_64-apple-darwin",
    ("macOS", "ARM64"): "aarch64-apple-darwin",
    ("Windows", "X64"): "x86_64-pc-windows-msvc",
}


class SetupError(Exception):
    """An error reported to the user as the action's failure message."""


@dataclass(frozen=True)
class Asset:
    """Layout of the release archive for one target."""

    target: str
    archive: str
    """File name of the release asset."""
    member: str
    """Path of the executable inside the archive."""
    binary: str
    """File name of the executable."""

    @property
    def is_zip(self) -> bool:
        """Whether the archive is a zip file (Windows) rather than a gzipped tarball."""
        return self.archive.endswith(".zip")


def asset_for(runner_os: str, runner_arch: str) -> Asset:
    """Return the release asset for a runner (`runner.os`, `runner.arch`)."""
    target = _TARGETS.get((runner_os, runner_arch))
    if target is None:
        msg = (
            f"no prebuilt graphcal for {runner_os}/{runner_arch}; "
            "install it with 'cargo install graphcal --locked' instead"
        )
        raise SetupError(msg)
    if runner_os == "Windows":
        # dist does not nest the files of Windows zip archives in a directory.
        return Asset(target, f"graphcal-{target}.zip", "graphcal.exe", "graphcal.exe")
    return Asset(target, f"graphcal-{target}.tar.gz", f"graphcal-{target}/graphcal", "graphcal")


def normalize_version(value: str) -> str:
    """Validate the `version` input: `latest` (or empty) or a full version.

    The version is written without the leading `v` of the release tags, like
    the `version` output and `graphcal --version`. Only full semantic versions
    are accepted, which also keeps the value safe to put in a URL.
    """
    if value in ("", LATEST):
        return LATEST
    if _VERSION.fullmatch(value) is not None:
        return value
    if value.startswith("v") and _VERSION.fullmatch(value[1:]) is not None:
        msg = f"invalid version: {value!r} (drop the leading 'v': {value[1:]!r})"
    else:
        msg = f"invalid version: {value!r} (expected 'latest' or a full version such as '{FIRST_BINARY_RELEASE}')"
    raise SetupError(msg)


def download_url(version: str, file_name: str) -> str:
    """Return the download URL of a release asset."""
    return f"https://github.com/{REPO}/releases/download/v{version}/{file_name}"


def parse_release_version(body: str) -> str:
    """Extract the version from a GitHub "get a release" API response.

    Release tags are `v` followed by the version, e.g. `v0.0.1-alpha.35`.
    """
    try:
        tag = json.loads(body)["tag_name"]
    except (ValueError, TypeError, KeyError) as e:
        msg = "no tag_name in the release response"
        raise SetupError(msg) from e
    if not (isinstance(tag, str) and tag.startswith("v") and _VERSION.fullmatch(tag[1:])):
        msg = f"unexpected tag_name in the release response: {tag!r}"
        raise SetupError(msg)
    return tag[1:]


def normalize_sha256(value: str) -> str:
    """Normalize a SHA-256 digest to 64 lowercase hex characters.

    Accepts an optional `sha256:` prefix and any case.
    """
    digest = value.strip().removeprefix("sha256:").lower()
    if _SHA256.fullmatch(digest) is None:
        msg = f"invalid SHA-256 checksum: {value!r}"
        raise SetupError(msg)
    return digest


def parse_sha256_file(text: str) -> str:
    """Extract the digest from a `<archive>.sha256` asset (`<digest> *<file name>`)."""
    fields = text.split()
    if not fields:
        msg = "empty checksum file"
        raise SetupError(msg)
    return normalize_sha256(fields[0])


def parse_version_output(text: str) -> str:
    """Extract the version from `graphcal --version` output.

    For example, `graphcal 0.0.1-alpha.35 (commit: 106312a)` -> `0.0.1-alpha.35`.
    """
    match text.split():
        case ["graphcal", version, *_]:
            return version
        case _:
            msg = f"unexpected 'graphcal --version' output: {text!r}"
            raise SetupError(msg)


def read_executable(archive: bytes, asset: Asset) -> bytes:
    """Return the executable from a release archive held in memory.

    Only the executable is read; nothing else in the archive is extracted.
    """
    try:
        if asset.is_zip:
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                return zf.read(asset.member)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            member = tf.getmember(asset.member)
            f = tf.extractfile(member) if member.isfile() else None
            if f is None:
                msg = f"{asset.member} in {asset.archive} is not a regular file"
                raise SetupError(msg)
            with f:
                return f.read()
    except KeyError as e:
        msg = f"{asset.member} not found in {asset.archive}"
        raise SetupError(msg) from e
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError) as e:
        msg = f"could not read {asset.archive}: {e}"
        raise SetupError(msg) from e


def error_command(message: str) -> str:
    """Format a GitHub Actions `::error` workflow command."""
    data = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::error title=setup-graphcal::{data}"
