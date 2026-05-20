"""Tool dispatcher tests."""
from __future__ import annotations

from pathlib import Path

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
