#!/usr/bin/env bash
# Install a prebuilt graphcal binary from GitHub Releases.
#
# Inputs (environment): INPUT_VERSION, INPUT_CHECKSUM, INPUT_GITHUB_TOKEN, and
# the runner's RUNNER_OS, RUNNER_ARCH, RUNNER_TEMP, GITHUB_PATH, GITHUB_OUTPUT.
set -euo pipefail

# shellcheck source=scripts/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

REPO="graphcal-lang/graphcal"

log() { echo "setup-graphcal: $*"; }
fail() {
  echo "::error title=setup-graphcal::$*"
  exit 1
}

# Convert a POSIX path to the native form of the runner's OS (GITHUB_PATH and the
# `path` output must be Windows paths on Windows).
native_path() {
  if [ "$RUNNER_OS" = "Windows" ]; then cygpath -w "$1"; else echo "$1"; fi
}

download() {
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    --retry 3 --output "$2" "$1"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

resolve_latest() {
  local headers=(-H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")
  # The workflow token belongs to the GitHub instance running the job; only
  # send it to the github.com API.
  if [ -n "${INPUT_GITHUB_TOKEN:-}" ] && [ "${GITHUB_SERVER_URL:-https://github.com}" = "https://github.com" ]; then
    headers+=(-H "Authorization: Bearer $INPUT_GITHUB_TOKEN")
  fi
  local response
  response="$(curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    --retry 3 "${headers[@]}" \
    "https://api.github.com/repos/$REPO/releases/latest")" || return 1
  parse_release_version "$response"
}

main() {
  local version target archive expected actual
  version="$(normalize_version "${INPUT_VERSION:-latest}")" || fail "invalid version input: '${INPUT_VERSION:-}'"
  if [ "$version" = "latest" ]; then
    version="$(resolve_latest)" || fail "could not resolve the latest release of $REPO"
    log "resolved latest to $version"
  fi
  target="$(graphcal_target "$RUNNER_OS" "$RUNNER_ARCH")" ||
    fail "no prebuilt graphcal for $RUNNER_OS/$RUNNER_ARCH; install it with 'cargo install graphcal --locked' instead"
  archive="$(archive_name "$target")"

  local base_url="https://github.com/$REPO/releases/download/v$version"
  local temp_root="${RUNNER_TEMP:?}"
  if [ "$RUNNER_OS" = "Windows" ]; then
    temp_root="$(cygpath -u "$temp_root")"
  fi
  local temp_dir
  temp_dir="$(mktemp -d "$temp_root/setup-graphcal.XXXXXX")"
  # shellcheck disable=SC2064 # expand now: temp_dir is local to main
  trap "rm -rf '$temp_dir'" EXIT

  log "downloading $base_url/$archive"
  download "$base_url/$archive" "$temp_dir/$archive" ||
    fail "could not download $archive for v$version (prebuilt binaries are available from v0.0.1-alpha.35)"

  if [ -n "${INPUT_CHECKSUM:-}" ]; then
    expected="$(normalize_sha256 "$INPUT_CHECKSUM")" || fail "invalid checksum input"
  else
    download "$base_url/$archive.sha256" "$temp_dir/$archive.sha256" ||
      fail "could not download $archive.sha256 for v$version"
    expected="$(parse_sha256_file "$(cat "$temp_dir/$archive.sha256")")" ||
      fail "could not parse $archive.sha256"
  fi
  actual="$(sha256_of "$temp_dir/$archive")"
  if [ "$actual" != "$expected" ]; then
    fail "checksum mismatch for $archive: expected $expected, got $actual"
  fi
  log "verified sha256 $actual"

  local install_dir="$temp_root/setup-graphcal/$version/$target"
  rm -rf "$install_dir"
  mkdir -p "$install_dir"
  local extract_dir="$temp_dir/extract"
  mkdir -p "$extract_dir"
  case "$archive" in
    *.zip)
      # shellcheck disable=SC2016 # expanded by PowerShell, not bash
      ARCHIVE="$(native_path "$temp_dir/$archive")" DEST="$(native_path "$extract_dir")" \
        pwsh -NoProfile -NonInteractive -Command \
        'Expand-Archive -LiteralPath $env:ARCHIVE -DestinationPath $env:DEST -Force'
      ;;
    *) tar -xzf "$temp_dir/$archive" -C "$extract_dir" ;;
  esac

  local root binary
  root="$(archive_root "$target")"
  binary="$(binary_name "$target")"
  local extracted="$extract_dir${root:+/$root}/$binary"
  [ -f "$extracted" ] || fail "$binary not found in $archive"
  mv "$extracted" "$install_dir/$binary"
  chmod +x "$install_dir/$binary"

  local installed_version
  installed_version="$(parse_version_output "$("$install_dir/$binary" --version)")" ||
    fail "could not run the installed graphcal"
  if [ "$installed_version" != "$version" ]; then
    fail "installed graphcal reports version $installed_version, expected $version"
  fi
  log "installed graphcal $installed_version to $install_dir"

  native_path "$install_dir" >>"$GITHUB_PATH"
  {
    echo "version=$version"
    echo "path=$(native_path "$install_dir/$binary")"
  } >>"$GITHUB_OUTPUT"
}

main "$@"
