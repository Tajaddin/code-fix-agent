"""Run pytest on model-edited code.

The code under test is written by the model, so it is treated as untrusted:
it gets none of the caller's environment (no API keys), and a timeout kills
every process the tests started, not only pytest.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PYTEST_ARGS = ["-q", "--no-header", "--no-summary", "-p", "no:cacheprovider"]

# Python on Windows cannot start without SYSTEMROOT; the temp variables only
# say where scratch files go. Nothing else is passed through.
_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR")


@dataclass
class RunResult:
    exit_code: int | None  # None when the run hit the timeout
    stdout: str
    stderr: str


def minimal_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_pytest(cwd: Path, args: list[str], *, timeout: float) -> RunResult:
    """Run pytest in `cwd` in its own process group with a minimal environment."""
    cmd = [sys.executable, "-B", "-m", "pytest", *PYTEST_ARGS, *args]
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=minimal_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **group,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            stdout, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout = ""
        return RunResult(None, stdout or "", "timeout")
    return RunResult(proc.returncode, stdout, stderr)


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()
