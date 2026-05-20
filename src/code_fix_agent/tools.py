"""Tool definitions for the bug-fix agent.

Each tool is a thin wrapper around a Workspace method. The descriptions
matter: they tell Claude when to call which tool.
"""
from __future__ import annotations

from typing import Any

from code_fix_agent.workspace import Workspace


def tool_schemas() -> list[dict[str, Any]]:
    """Return the Anthropic-shaped tool definitions."""
    return [
        {
            "name": "list_dir",
            "description": (
                "List file and directory names under a path relative to the workspace root. "
                "Use this first to see what files exist before reading them."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the workspace root. Use '.' for the root.",
                        "default": ".",
                    }
                },
            },
        },
        {
            "name": "read_file",
            "description": (
                "Read a text file from the workspace. Returns the full file contents. "
                "Use this to inspect buggy.py and the test file."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root."}
                },
                "required": ["path"],
            },
        },
        {
            "name": "edit_file",
            "description": (
                "Replace the unique occurrence of `old` with `new` inside `path`. The `old` "
                "string MUST appear exactly once. If it appears multiple times or not at all, "
                "the call errors out. Include enough surrounding context to make `old` unique."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string", "description": "Exact substring to replace."},
                    "new": {"type": "string", "description": "Replacement substring."},
                },
                "required": ["path", "old", "new"],
            },
        },
        {
            "name": "search_code",
            "description": (
                "Substring search across all .py files in the workspace. Returns each match "
                "as 'path:line: text'. Useful to find where a function is defined or called."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "run_tests",
            "description": (
                "Run pytest on the workspace's test file. Returns whether tests passed and "
                "the captured stdout/stderr. Call this after every edit to check if the bug is fixed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "test_file": {"type": "string", "default": "test_buggy.py"}
                },
            },
        },
    ]


def execute(ws: Workspace, tool_name: str, tool_input: dict[str, Any]) -> str:
    """Dispatch one tool call against the workspace. Returns a string result."""
    try:
        if tool_name == "list_dir":
            entries = ws.list_dir(tool_input.get("path", "."))
            return "\n".join(entries) if entries else "(empty)"

        if tool_name == "read_file":
            return ws.read(tool_input["path"])

        if tool_name == "edit_file":
            return ws.edit(
                tool_input["path"],
                tool_input["old"],
                tool_input["new"],
            )

        if tool_name == "search_code":
            hits = ws.search(tool_input["pattern"], tool_input.get("path", "."))
            if not hits:
                return "no matches"
            return "\n".join(f"{p}:{ln}: {text}" for p, ln, text in hits)

        if tool_name == "run_tests":
            result = ws.run_tests(tool_input.get("test_file", "test_buggy.py"))
            status = "PASS" if result["passed"] else "FAIL"
            body = result["stdout"] or result["stderr"]
            return f"{status} (exit {result['exit_code']}) summary={result['summary']!r}\n{body}"

        return f"unknown tool: {tool_name}"
    except FileNotFoundError as exc:
        return f"error: {exc}"
    except (PermissionError, ValueError) as exc:
        return f"error: {exc}"
