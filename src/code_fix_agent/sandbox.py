"""Run pytest on model-edited code.

The code under test is written by the model, so it is treated as untrusted.
Two runners:

- docker: a throwaway container with no network, a read-only file system and
  workspace mount, no capabilities, and memory/CPU/process limits. Nothing
  from the caller's environment is passed in.
- local: a subprocess with a minimal environment, in its own session
  (POSIX) or process group (Windows); a timeout kills that group or tree,
  which misses a process that left the group (setsid) or, on Windows, one
  whose parent already exited. The clean environment only stops accidental
  inheritance of secrets: the tests run as the caller's user, next to the
  agent process that holds ANTHROPIC_API_KEY, and can read it from there
  (on Linux, from /proc/<parent pid>/environ). They also have the caller's
  file-system and network access. It is a fallback, not a sandbox.

"auto" picks docker when the `docker` CLI can see the sandbox image. Live
runs, where the model writes the code, turn off auto's local fallback, so
running them without the image takes an explicit "local".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PYTEST_ARGS = ["-q", "--no-header", "--tb=short", "-p", "no:cacheprovider"]
SANDBOX_IMAGE = os.environ.get("CFA_SANDBOX_IMAGE", "code-fix-agent:latest")
SANDBOX_MODES = ("auto", "docker", "local")

# Python on Windows cannot start without SYSTEMROOT; the temp variables only
# say where scratch files go. Nothing else is passed through.
_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR")


@dataclass
class RunResult:
    exit_code: int | None  # None when the run hit the timeout
    stdout: str
    stderr: str


@cache
def docker_available(image: str = SANDBOX_IMAGE) -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def resolve_sandbox(
    mode: str, image: str = SANDBOX_IMAGE, *, allow_local_fallback: bool = True
) -> str:
    """Map a requested mode to the runner that will be used: "docker" or "local".

    With allow_local_fallback=False, "auto" fails instead of falling back to
    the local runner when the image is missing.
    """
    if mode not in SANDBOX_MODES:
        raise ValueError(f"sandbox must be one of {SANDBOX_MODES}, got {mode!r}")
    if mode == "local":
        return "local"
    if docker_available(image):
        return "docker"
    if mode == "docker":
        raise RuntimeError(
            f"docker sandbox requested but image {image!r} is not available "
            f"(build it with `docker build -t {image} .`)"
        )
    if not allow_local_fallback:
        raise RuntimeError(
            f"sandbox image {image!r} is not available. Under the local runner, "
            "model-written code runs as your user and can read ANTHROPIC_API_KEY "
            f"from the agent process. Build the image with `docker build -t {image} .`, "
            "or pass --sandbox local to run without it."
        )
    return "local"


def minimal_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def docker_command(cwd: Path, args: list[str], *, name: str, image: str = SANDBOX_IMAGE) -> list[str]:
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp",
        "--memory", "512m", "--pids-limit", "128", "--cpus", "1",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--mount", f"type=bind,source={cwd},target=/work,readonly",
        "--workdir", "/work",
        "--entrypoint", "python",
    ]
    if hasattr(os, "getuid"):
        # The temp workspace is private to the caller's uid on POSIX.
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return [*cmd, image, "-B", "-m", "pytest", *PYTEST_ARGS, *args]


def run_pytest(
    cwd: Path, args: list[str], *, timeout: float, sandbox: str = "local", image: str = SANDBOX_IMAGE
) -> RunResult:
    """Run pytest on `cwd` with the given runner ("docker" or "local")."""
    if sandbox == "docker":
        name = f"cfa-{uuid.uuid4().hex[:12]}"
        # The docker client needs the caller's environment to reach the
        # daemon; none of it is forwarded into the container.
        return _run(
            docker_command(cwd, args, name=name, image=image),
            cwd=None,
            env=None,
            timeout=timeout,
            on_timeout=lambda: _docker_kill(name),
        )
    if sandbox != "local":
        raise ValueError(f"unknown runner: {sandbox!r}")
    return _run(
        [sys.executable, "-B", "-m", "pytest", *PYTEST_ARGS, *args],
        cwd=cwd,
        env=minimal_env(),
        timeout=timeout,
    )


def _run(
    cmd: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str] | None,
    timeout: float,
    on_timeout: Callable[[], object] | None = None,
) -> RunResult:
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
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
        if on_timeout is not None:
            on_timeout()
        _kill_tree(proc)
        try:
            stdout, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout = ""
        return RunResult(None, stdout or "", "timeout")
    return RunResult(proc.returncode, stdout, stderr)


def _docker_kill(name: str) -> None:
    # Killing the docker client does not stop the container.
    try:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


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
