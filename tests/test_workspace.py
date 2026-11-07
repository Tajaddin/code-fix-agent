"""Workspace tests."""
from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from benchmarks import run_benchmark
from code_fix_agent import cli, sandbox
from code_fix_agent.workspace import Workspace


def _bug_dir(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "bugs" / name


class TestWorkspace:
    def test_copies_bug_files_into_tempdir(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            entries = ws.list_dir()
            assert "buggy.py" in entries
            assert "test_buggy.py" in entries

    def test_read_returns_file_contents(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            text = ws.read("buggy.py")
            assert "def sum_first_n" in text

    def test_edit_replaces_unique_substring(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = ws.edit("buggy.py", "range(n)", "range(n + 1)")
            assert "1 replacement" in result
            assert "range(n + 1)" in ws.read("buggy.py")

    def test_edit_rejects_missing_substring(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            with pytest.raises(ValueError):
                ws.edit("buggy.py", "not in file", "anything")

    def test_run_tests_fails_on_unfixed_bug(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = ws.run_tests()
            assert result["passed"] is False

    def test_run_tests_passes_after_fix(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            ws.edit("buggy.py", "range(n)", "range(n + 1)")
            result = ws.run_tests()
            assert result["passed"] is True, result["stdout"]

    def test_search_finds_pattern(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            hits = ws.search("range")
            assert any(h[2].strip().startswith("for i in range") for h in hits)


def _write_bug(dir_: Path, test_source: str) -> Path:
    (dir_ / "buggy.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (dir_ / "test_buggy.py").write_text(textwrap.dedent(test_source), encoding="utf-8")
    return dir_


class TestTestRunIsolation:
    def test_tests_do_not_inherit_secrets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-key")
        monkeypatch.setenv("CFA_PROBE_SECRET", "visible")
        bug = _write_bug(
            tmp_path,
            """
            import os

            def test_no_secrets():
                assert os.environ.get("ANTHROPIC_API_KEY") is None
                assert os.environ.get("CFA_PROBE_SECRET") is None
            """,
        )
        with Workspace.from_bug_dir(bug, sandbox="local") as ws:
            result = ws.run_tests()
        assert result["passed"] is True, result["stdout"]

    def test_timeout_kills_processes_the_tests_started(self, tmp_path):
        started = tmp_path / "started"
        late = tmp_path / "late"
        timeout = 20
        # Leave pytest plenty of time to start, and have the child write
        # `late` at a fixed time after the deadline, however late it began.
        late_at = time.time() + timeout + 2
        child = (
            "import pathlib, time; "
            f"pathlib.Path({str(started)!r}).write_text('x'); "
            f"time.sleep(max(0, {late_at} - time.time())); "
            f"pathlib.Path({str(late)!r}).write_text('x')"
        )
        (tmp_path / "bug").mkdir()
        bug = _write_bug(
            tmp_path / "bug",
            f"""
            import subprocess, sys, time

            def test_hangs():
                subprocess.Popen([sys.executable, "-c", {child!r}])
                time.sleep(60)
            """,
        )
        with Workspace.from_bug_dir(bug, sandbox="local") as ws:
            result = ws.run_tests(timeout=timeout)
        time.sleep(max(0, late_at + 2 - time.time()))
        assert result["summary"] == "timeout"
        assert started.exists(), "the test never started its child process"
        assert not late.exists(), "a process started by the tests outlived the timeout"


def _no_model(*args, **kwargs):
    raise AssertionError("the run reached the model before checking the sandbox")


class TestSandboxSelection:
    def test_auto_falls_back_to_local_without_the_image(self, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
        assert sandbox.resolve_sandbox("auto") == "local"

    def test_auto_uses_docker_when_the_image_exists(self, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: True)
        assert sandbox.resolve_sandbox("auto") == "docker"

    def test_explicit_docker_fails_before_creating_a_workspace(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        with pytest.raises(RuntimeError, match="not available"):
            Workspace.from_bug_dir(_bug_dir("01_off_by_one"), sandbox="docker")
        assert list(tmp_path.iterdir()) == []

    def test_unknown_mode_is_rejected(self):
        with pytest.raises(ValueError):
            sandbox.resolve_sandbox("chroot")

    def test_auto_without_the_image_refuses_when_local_fallback_is_off(self, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
        with pytest.raises(RuntimeError, match="--sandbox local"):
            sandbox.resolve_sandbox("auto", allow_local_fallback=False)
        assert sandbox.resolve_sandbox("local", allow_local_fallback=False) == "local"

    def test_live_cli_run_does_not_fall_back_to_local(self, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
        monkeypatch.setattr(cli, "AnthropicLLM", _no_model)
        with pytest.raises(RuntimeError, match="--sandbox local"):
            cli.main(["run", str(_bug_dir("01_off_by_one"))])

    def test_live_benchmark_does_not_fall_back_to_local(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
        monkeypatch.setattr(run_benchmark, "AnthropicLLM", _no_model)
        with pytest.raises(RuntimeError, match="--sandbox local"):
            run_benchmark.main(["--mode", "live", "--out", str(tmp_path / "b.json")])
        assert not (tmp_path / "b.json").exists()

    def test_docker_command_shuts_off_network_env_and_writes(self, tmp_path):
        cmd = sandbox.docker_command(tmp_path, ["test_buggy.py"], name="cfa-test")
        pairs = set(zip(cmd, cmd[1:]))
        assert ("--network", "none") in pairs
        assert ("--cap-drop", "ALL") in pairs
        assert ("--security-opt", "no-new-privileges") in pairs
        assert "--read-only" in cmd
        assert f"type=bind,source={tmp_path},target=/work,readonly" in cmd
        assert not {"-e", "--env", "--env-file", "--privileged"} & set(cmd)
        image_at = cmd.index(sandbox.SANDBOX_IMAGE)
        assert cmd[image_at + 1 :] == ["-B", "-m", "pytest", *sandbox.PYTEST_ARGS, "test_buggy.py"]


@pytest.mark.skipif(not sandbox.docker_available(), reason="sandbox image not built")
class TestDockerSandbox:
    def test_container_has_no_network_and_no_secrets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-key")
        bug = _write_bug(
            tmp_path,
            """
            import os, socket

            import pytest

            def test_isolated():
                assert os.environ.get("ANTHROPIC_API_KEY") is None
                with pytest.raises(OSError):
                    socket.create_connection(("1.1.1.1", 53), timeout=3)
                with pytest.raises(OSError):
                    open("written.txt", "w")
            """,
        )
        with Workspace.from_bug_dir(bug, sandbox="docker") as ws:
            result = ws.run_tests()
        assert result["passed"] is True, result["stdout"]
