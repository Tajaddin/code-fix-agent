"""Workspace tests."""
from __future__ import annotations

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
