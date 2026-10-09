from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"


def test_python_m_runs_the_action(tmp_path: Path):
    # Run as action.yaml does, with an input that fails before any network access.
    # -S skips site-packages, so the package is imported through PYTHONPATH only.
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC),
        "INPUT_VERSION": "v0.0.1-alpha.35",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_PATH": str(tmp_path / "path"),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }
    result = subprocess.run(
        [sys.executable, "-S", "-m", "setup_graphcal"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 1
    assert result.stdout.startswith("::error title=setup-graphcal::invalid version")
