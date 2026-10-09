#!/usr/bin/env bash
# Unit tests for scripts/lib.sh. Run: ./tests/lib.test.sh
set -uo pipefail

# shellcheck source=scripts/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib.sh"

failures=0

# Assert that running the command prints `expected` and succeeds.
assert_eq() {
  local expected="$1"
  shift
  local actual
  if ! actual="$("$@" 2>/dev/null)"; then
    echo "FAIL: $* exited with an error (expected '$expected')"
    failures=$((failures + 1))
  elif [ "$actual" != "$expected" ]; then
    echo "FAIL: $*: expected '$expected', got '$actual'"
    failures=$((failures + 1))
  fi
}

# Assert that the command fails.
assert_fails() {
  local actual
  if actual="$("$@" 2>/dev/null)"; then
    echo "FAIL: $* should fail, got '$actual'"
    failures=$((failures + 1))
  fi
}

assert_eq x86_64-unknown-linux-musl graphcal_target Linux X64
assert_eq aarch64-unknown-linux-musl graphcal_target Linux ARM64
assert_eq x86_64-apple-darwin graphcal_target macOS X64
assert_eq aarch64-apple-darwin graphcal_target macOS ARM64
assert_eq x86_64-pc-windows-msvc graphcal_target Windows X64
assert_fails graphcal_target Windows ARM64
assert_fails graphcal_target Linux X86
assert_fails graphcal_target FreeBSD X64

assert_eq graphcal-x86_64-unknown-linux-musl.tar.gz archive_name x86_64-unknown-linux-musl
assert_eq graphcal-aarch64-apple-darwin.tar.gz archive_name aarch64-apple-darwin
assert_eq graphcal-x86_64-pc-windows-msvc.zip archive_name x86_64-pc-windows-msvc

assert_eq graphcal binary_name aarch64-apple-darwin
assert_eq graphcal.exe binary_name x86_64-pc-windows-msvc

assert_eq graphcal-aarch64-unknown-linux-musl archive_root aarch64-unknown-linux-musl
assert_eq "" archive_root x86_64-pc-windows-msvc

assert_eq latest normalize_version latest
assert_eq latest normalize_version ""
assert_eq 0.0.1-alpha.35 normalize_version 0.0.1-alpha.35
assert_eq 0.0.1-alpha.35 normalize_version v0.0.1-alpha.35
assert_eq 1.2.3 normalize_version 1.2.3
assert_eq 1.2.3+build.5 normalize_version 1.2.3+build.5
assert_fails normalize_version 1.2
assert_fails normalize_version vv1.2.3
assert_fails normalize_version "1.2.3; rm -rf /"
assert_fails normalize_version "1.2.3/../../x"
assert_fails normalize_version Latest

assert_eq 0.0.1-alpha.35 parse_release_version '{"url":"x","tag_name":"v0.0.1-alpha.35","name":"0.0.1-alpha.35"}'
assert_eq 1.0.0 parse_release_version '{
  "tag_name": "v1.0.0",
  "target_commitish": "main"
}'
assert_fails parse_release_version '{"message":"Not Found"}'
assert_fails parse_release_version '{"tag_name":"nightly"}'

digest=1d2df28f885bbd88ea3a07725b36f573f5ed90c2c969c3e7ab30ffae4cc56619
assert_eq "$digest" normalize_sha256 "$digest"
assert_eq "$digest" normalize_sha256 "sha256:$digest"
assert_eq "$digest" normalize_sha256 "$(printf '%s' "$digest" | tr 'a-f' 'A-F')"
assert_fails normalize_sha256 "${digest:1}"
assert_fails normalize_sha256 "${digest}0"
assert_fails normalize_sha256 ""

# dist writes `<digest> *<file>` followed by a blank line.
assert_eq "$digest" parse_sha256_file "$digest *graphcal-aarch64-apple-darwin.tar.gz
"
assert_eq "$digest" parse_sha256_file "$digest  graphcal-aarch64-apple-darwin.tar.gz"
assert_fails parse_sha256_file "<html>Not Found</html>"

assert_eq 0.0.1-alpha.35 parse_version_output "graphcal 0.0.1-alpha.35 (commit: 106312a)"
assert_eq 1.0.0 parse_version_output "graphcal 1.0.0"
assert_fails parse_version_output "error: unknown option"
assert_fails parse_version_output ""

if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
