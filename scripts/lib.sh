# shellcheck shell=bash
# Pure helpers for setup-graphcal. They do no IO beyond stdout/stderr so that
# tests/lib.test.sh can exercise them directly. Keep them compatible with the
# bash 3.2 that ships with macOS.

# Print the Rust target triple of the release asset for a runner.
# Arguments: RUNNER_OS (Linux, macOS, Windows) and RUNNER_ARCH (X64, ARM64).
graphcal_target() {
  case "$1/$2" in
    Linux/X64) echo "x86_64-unknown-linux-musl" ;;
    Linux/ARM64) echo "aarch64-unknown-linux-musl" ;;
    macOS/X64) echo "x86_64-apple-darwin" ;;
    macOS/ARM64) echo "aarch64-apple-darwin" ;;
    Windows/X64) echo "x86_64-pc-windows-msvc" ;;
    *)
      echo "unsupported runner: os=$1 arch=$2" >&2
      return 1
      ;;
  esac
}

# Print the archive file name of the release asset for a target.
archive_name() {
  case "$1" in
    *-windows-*) echo "graphcal-$1.zip" ;;
    *) echo "graphcal-$1.tar.gz" ;;
  esac
}

# Print the executable file name for a target.
binary_name() {
  case "$1" in
    *-windows-*) echo "graphcal.exe" ;;
    *) echo "graphcal" ;;
  esac
}

# Print the archive's top-level directory, or nothing when the binary sits at
# the archive root (dist does not nest Windows zip archives).
archive_root() {
  case "$1" in
    *-windows-*) echo "" ;;
    *) echo "graphcal-$1" ;;
  esac
}

# Normalize the `version` input. Prints `latest`, or the version without a
# leading `v` (e.g. `0.0.1-alpha.35`). Rejects anything that is not a full
# semantic version so that the value is safe to put in a URL.
normalize_version() {
  local input="$1"
  case "$input" in
    "" | latest)
      echo "latest"
      return 0
      ;;
  esac
  local version="${input#v}"
  if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
    echo "invalid version: '$input' (expected 'latest' or a full version such as '0.0.1-alpha.35')" >&2
    return 1
  fi
  echo "$version"
}

# Extract the version from a GitHub "get a release" API response by reading
# its `tag_name` field (e.g. `"tag_name": "v0.0.1-alpha.35"` -> `0.0.1-alpha.35`).
parse_release_version() {
  local tag
  tag="$(printf '%s\n' "$1" | grep -o '"tag_name": *"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')"
  if [ -z "$tag" ]; then
    echo "no tag_name in the release response" >&2
    return 1
  fi
  normalize_version "$tag"
}

# Normalize a SHA-256 digest: accept an optional `sha256:` prefix and any
# case, print 64 lowercase hex characters.
normalize_sha256() {
  local digest
  digest="$(printf '%s' "${1#sha256:}" | tr 'A-F' 'a-f')"
  if ! [[ "$digest" =~ ^[0-9a-f]{64}$ ]]; then
    echo "invalid SHA-256 checksum: '$1'" >&2
    return 1
  fi
  echo "$digest"
}

# Extract the digest from the contents of a `<archive>.sha256` asset, whose
# first line is `<hex digest> *<file name>`.
parse_sha256_file() {
  normalize_sha256 "$(printf '%s\n' "$1" | head -n 1 | awk '{print $1}')"
}

# Extract the version from `graphcal --version` output, e.g.
# `graphcal 0.0.1-alpha.35 (commit: 106312a)` -> `0.0.1-alpha.35`.
parse_version_output() {
  local version
  version="$(printf '%s\n' "$1" | head -n 1 | awk '$1 == "graphcal" {print $2}')"
  if [ -z "$version" ]; then
    echo "unexpected 'graphcal --version' output: '$1'" >&2
    return 1
  fi
  echo "$version"
}
