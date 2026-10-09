# setup-graphcal

A GitHub Action that installs a prebuilt [Graphcal](https://github.com/graphcal-lang/graphcal) CLI (`graphcal`) from GitHub Releases and adds it to `PATH`. No Rust toolchain is needed, so setup takes seconds.

## Usage

Check and evaluate the `.gcl` files of a repository on every push and pull request:

```yaml
name: Graphcal

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: graphcal-lang/setup-graphcal@v1
      - run: graphcal check
      - run: graphcal eval model.gcl
```

`graphcal eval` exits with a non-zero status when an assertion fails, so the job fails too.

### Pin the version

Graphcal is in alpha and its language still changes between releases. Pin the version to keep CI reproducible:

```yaml
- uses: graphcal-lang/setup-graphcal@v1
  with:
    version: 0.0.1-alpha.35
```

To also pin the archive itself, pass its SHA-256 as `checksum`. The value depends on the runner's target, so set it per runner (for example, from a matrix). The digests are listed in `sha256.sum` of each release.

```yaml
- uses: graphcal-lang/setup-graphcal@v1
  with:
    version: 0.0.1-alpha.35
    checksum: ed8ae8439bd6fa14b31363dae0649b649a02946a2ec8b257c8794f9dfdc79350 # x86_64-unknown-linux-musl
```

## Inputs

| Name | Default | Description |
| --- | --- | --- |
| `version` | `latest` | `latest`, or a full version such as `0.0.1-alpha.35`, written without the leading `v` of the release tag (`v0.0.1-alpha.35` is rejected). Version ranges are not supported. |
| `checksum` | (empty) | Expected SHA-256 of the release archive for this runner, optionally prefixed with `sha256:`. When empty, the archive is verified against the `.sha256` file published with it. |
| `github-token` | `${{ github.token }}` | Token used to resolve `latest` through the GitHub API, which avoids the rate limit for unauthenticated requests. It is sent only to `api.github.com`, and only when the workflow runs on github.com. |

## Outputs

| Name | Description |
| --- | --- |
| `version` | The installed version, without a leading `v` (e.g. `0.0.1-alpha.35`). |
| `path` | Absolute path of the installed `graphcal` executable. |

## Supported runners

| `runner.os` | `runner.arch` | Release target |
| --- | --- | --- |
| Linux | X64 | `x86_64-unknown-linux-musl` |
| Linux | ARM64 | `aarch64-unknown-linux-musl` |
| macOS | X64 | `x86_64-apple-darwin` |
| macOS | ARM64 | `aarch64-apple-darwin` |
| Windows | X64 | `x86_64-pc-windows-msvc` |

The Linux binaries are statically linked, so they also run in Alpine and other musl-based containers. On other runners the action fails; install Graphcal with `cargo install graphcal --locked` instead.

Prebuilt binaries are published from Graphcal 0.0.1-alpha.35 onward. Earlier versions cannot be installed with this action.

## How it works

1. Resolve `version`. `latest` is looked up through the GitHub API.
2. Pick the release target from `runner.os` and `runner.arch`.
3. Download `graphcal-{target}.tar.gz` (`.zip` on Windows) from the release.
4. Verify its SHA-256 against the `checksum` input or the published `.sha256` file.
5. Extract only the `graphcal` executable into `$RUNNER_TEMP` and add its directory to `PATH`.
6. Run `graphcal --version` and check that it reports the resolved version.

The action is a composite action that runs a Python script (standard library only) with the runner's own `python`. It needs Python 3.10 or later, which every GitHub-hosted runner provides. On self-hosted runners and in container jobs, make sure `python` 3.10+ is on `PATH`.

## Development

- `setup_graphcal/core.py` holds the pure logic and `setup_graphcal/install.py` the IO (network, files, processes). Both must stay standard-library only and run on Python 3.10.
- Run the unit tests with `uv run pytest`, and check with `uv run ruff format .`, `uv run ruff check .`, and `uv run ty check .`.
- The `Test` workflow also installs the action on every supported runner and checks its outputs and failure modes.
- Lint everything with `pre-commit run --all-files` (ruff, actionlint, zizmor, rumdl, typos).

### Release

Push an immutable version tag and move the major tag to it:

```sh
git tag v1.0.0
git tag -f v1 v1.0.0
git push origin v1.0.0
git push -f origin v1
```

## License

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or [MIT license](LICENSE-MIT) at your option.
