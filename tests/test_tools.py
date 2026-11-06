"""Tool dispatcher tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from code_fix_agent.tools import execute, tool_schemas
from code_fix_agent.workspace import Workspace


def _bug_dir(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "bugs" / name


class TestToolSchemas:
    def test_all_required_tools_listed(self):
        names = {s["name"] for s in tool_schemas()}
        assert names == {"list_dir", "read_file", "edit_file", "search_code", "run_tests"}

    def test_edit_file_requires_three_fields(self):
        schemas = {s["name"]: s for s in tool_schemas()}
        required = schemas["edit_file"]["input_schema"]["required"]
        assert sorted(required) == ["new", "old", "path"]


class TestExecute:
    def test_list_dir(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, "list_dir", {"path": "."})
            assert "buggy.py" in out
            assert "test_buggy.py" in out

    def test_read_file(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, "read_file", {"path": "buggy.py"})
            assert "def sum_first_n" in out

    def test_edit_file_then_run_tests_pass(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            execute(ws, "edit_file", {"path": "buggy.py", "old": "range(n)", "new": "range(n + 1)"})
            out = execute(ws, "run_tests", {"test_file": "test_buggy.py"})
            assert out.startswith("PASS")

    def test_edit_file_error_surfaces(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, "edit_file", {"path": "buggy.py", "old": "missing", "new": "x"})
            assert out.startswith("error:")

    def test_unknown_tool(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, "ghost", {})
            assert out.startswith("unknown tool")

    def test_search_code(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, "search_code", {"pattern": "sum_first_n"})
            assert "buggy.py" in out


class TestPathConfinement:
    """Every tool refuses paths that resolve outside the workspace root."""

    @pytest.mark.parametrize(
        ("tool", "tool_input"),
        [
            ("list_dir", {"path": ".."}),
            ("list_dir", {"path": "../.."}),
            ("read_file", {"path": "../buggy.py"}),
            ("edit_file", {"path": "../buggy.py", "old": "a", "new": "b"}),
            ("search_code", {"pattern": "def ", "path": ".."}),
            ("run_tests", {"test_file": "../test_buggy.py"}),
            ("run_tests", {"test_file": "../test_buggy.py::test_one"}),
        ],
    )
    def test_relative_escape_is_refused(self, tool, tool_input):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            out = execute(ws, tool, tool_input)
        assert out.startswith("error: path escapes workspace"), out

    @pytest.mark.parametrize(
        ("tool", "key"),
        [("list_dir", "path"), ("read_file", "path"), ("search_code", "path"), ("run_tests", "test_file")],
    )
    def test_absolute_path_outside_is_refused(self, tool, key):
        outside = _bug_dir("01_off_by_one")
        target = outside if tool in ("list_dir", "search_code") else outside / "test_buggy.py"
        tool_input = {key: str(target)}
        if tool == "search_code":
            tool_input["pattern"] = "def "
        with Workspace.from_bug_dir(outside) as ws:
            out = execute(ws, tool, tool_input)
        assert out.startswith("error: path escapes workspace"), out
        assert "buggy.py" not in out.replace(str(target), "")

    def test_outside_files_are_not_distinguishable_from_missing_ones(self, tmp_path):
        real = tmp_path / "real.py"
        real.write_text("x = 1\n", encoding="utf-8")
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            exists = execute(ws, "read_file", {"path": os.path.relpath(real, ws.root)})
            missing = execute(ws, "read_file", {"path": os.path.relpath(tmp_path / "nope.py", ws.root)})
        assert exists.startswith("error: path escapes workspace"), exists
        assert missing.startswith("error: path escapes workspace"), missing

    def test_symlink_pointing_outside_is_refused(self, tmp_path):
        secret = tmp_path / "secret.py"
        secret.write_text("TOKEN = 'outside'\n", encoding="utf-8")
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            link = ws.root / "link.py"
            try:
                link.symlink_to(secret)
            except OSError:
                pytest.skip("creating symlinks is not permitted here")
            assert execute(ws, "read_file", {"path": "link.py"}).startswith("error: path escapes")
            assert "outside" not in execute(ws, "search_code", {"pattern": "TOKEN"})

    def test_paths_inside_the_workspace_still_work(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            assert "buggy.py" in execute(ws, "list_dir", {"path": "./"})
            assert "def sum_first_n" in execute(ws, "read_file", {"path": "./buggy.py"})
            out = execute(ws, "run_tests", {"test_file": "test_buggy.py::test_zero"})
            assert out.startswith("PASS"), out
