"""Workspace tests."""
from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

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
        with Workspace.from_bug_dir(bug) as ws:
            result = ws.run_tests()
        assert result["passed"] is True, result["stdout"]

    def test_timeout_kills_processes_the_tests_started(self, tmp_path):
        started = tmp_path / "started"
        late = tmp_path / "late"
        child = (
            "import pathlib, time; "
            f"pathlib.Path({str(started)!r}).write_text('x'); "
            "time.sleep(6); "
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
        with Workspace.from_bug_dir(bug) as ws:
            result = ws.run_tests(timeout=6)
        time.sleep(5)
        assert result["summary"] == "timeout"
        assert started.exists(), "the test never started its child process"
        assert not late.exists(), "a process started by the tests outlived the timeout"
