"""Bug-fix agent loop.

Given a Workspace pointing at one bug folder, the agent:
1. Reads the description (if any) plus the buggy file.
2. Iterates tool-use rounds with the LLM. Each round may inspect, edit, or
   run tests.
3. Stops when run_tests reports passed, or when the iteration budget is
   exhausted.

Returns an AgentResult capturing pass/fail, iteration count, total tokens,
and the trail of tool calls.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from code_fix_agent.llm import LLMClient
from code_fix_agent.tools import execute, tool_schemas
from code_fix_agent.workspace import Workspace

SYSTEM_PROMPT = (
    "You are a focused bug-fix engineer. The workspace contains a buggy "
    "Python file and its pytest test file. Your goal is to make all tests "
    "pass with the SMALLEST surgical edit possible.\n\n"
    "Process:\n"
    "1. Call list_dir(\".\") then read_file(\"buggy.py\") and read_file(\"test_buggy.py\").\n"
    "2. Identify the single line or expression that is wrong.\n"
    "3. Use edit_file with enough surrounding context to make `old` unique.\n"
    "4. Call run_tests. If it passes, stop. If it fails, read the traceback "
    "carefully and edit again.\n"
    "Constraints:\n"
    "- Do not rewrite the whole function unless absolutely necessary.\n"
    "- Do not change the test file.\n"
    "- Do not introduce new imports unless the fix truly requires them.\n"
    "- One change per edit_file call.\n"
)


@dataclass
class AgentResult:
    bug_id: str
    passed: bool
    iterations: int
    tool_calls: int
    elapsed_seconds: float
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tool_trail: list[dict[str, Any]] = field(default_factory=list)
    final_summary: str = ""
    error: str | None = None


def run_agent(
    ws: Workspace,
    llm: LLMClient,
    *,
    max_iterations: int = 8,
    max_tokens: int = 1024,
) -> AgentResult:
    """Run the bug-fix loop on one workspace. Returns an AgentResult."""
    start = time.perf_counter()
    schemas = tool_schemas()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Workspace contains a buggy Python file. The bug id is "
                f"{ws.bug_id!r}. Find and fix the bug so that running pytest "
                "on test_buggy.py passes all tests."
            ),
        }
    ]

    result = AgentResult(bug_id=ws.bug_id, passed=False, iterations=0, tool_calls=0, elapsed_seconds=0.0)

    for i in range(max_iterations):
        result.iterations = i + 1
        try:
            content, stop_reason, usage = llm.respond(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=schemas,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - surface in result
            result.error = f"{type(exc).__name__}: {exc}"
            break

        result.total_input_tokens += usage.get("input_tokens", 0)
        result.total_output_tokens += usage.get("output_tokens", 0)
        messages.append({"role": "assistant", "content": content})

        tool_results: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input", {}) or {}
                tool_id = block.get("id", "")
                output = execute(ws, tool_name, tool_input)
                result.tool_calls += 1
                result.tool_trail.append(
                    {
                        "iteration": result.iterations,
                        "tool": tool_name,
                        "input_keys": sorted(tool_input.keys()),
                        "output_preview": output[:160],
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": output,
                    }
                )
                if tool_name == "run_tests" and output.startswith("PASS"):
                    result.passed = True
                    result.final_summary = output.split("\n", 1)[0]

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if result.passed or stop_reason != "tool_use":
            break

    result.elapsed_seconds = round(time.perf_counter() - start, 3)
    return result


@dataclass
class Agent:
    """Stateful façade over run_agent."""

    llm: LLMClient
    max_iterations: int = 8
    max_tokens: int = 1024

    def fix(self, ws: Workspace) -> AgentResult:
        return run_agent(
            ws,
            self.llm,
            max_iterations=self.max_iterations,
            max_tokens=self.max_tokens,
        )
