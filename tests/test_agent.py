"""Agent loop tests with MockLLM."""
from __future__ import annotations

from pathlib import Path

from code_fix_agent.agent import Agent, run_agent
from code_fix_agent.llm import MockLLM
from code_fix_agent.workspace import Workspace


def _bug_dir(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "bugs" / name


def _build_canonical_script(bug_dir: str, old: str, new: str):
    """Standard read -> edit -> test sequence."""
    return [
        (
            [{"type": "tool_use", "id": "tu_read", "name": "read_file", "input": {"path": "buggy.py"}}],
            "tool_use",
        ),
        (
            [
                {
                    "type": "tool_use",
                    "id": "tu_edit",
                    "name": "edit_file",
                    "input": {"path": "buggy.py", "old": old, "new": new},
                }
            ],
            "tool_use",
        ),
        (
            [
                {
                    "type": "tool_use",
                    "id": "tu_test",
                    "name": "run_tests",
                    "input": {"test_file": "test_buggy.py"},
                }
            ],
            "tool_use",
        ),
        ([{"type": "text", "text": "Fixed."}], "end_turn"),
    ]


class TestAgent:
    def test_fixes_off_by_one_in_three_iterations(self):
        script = _build_canonical_script("01_off_by_one", "range(n)", "range(n + 1)")
        llm = MockLLM(script=script)
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, llm)
        assert result.passed is True
        assert result.iterations == 3
        assert result.tool_calls == 3
        assert result.final_summary.startswith("PASS")

    def test_fixes_wrong_operator(self):
        script = _build_canonical_script(
            "02_wrong_operator",
            "sum(values) * len(values)",
            "sum(values) / len(values)",
        )
        llm = MockLLM(script=script)
        with Workspace.from_bug_dir(_bug_dir("02_wrong_operator")) as ws:
            result = run_agent(ws, llm)
        assert result.passed is True

    def test_stops_on_max_iterations(self):
        # Force a never-ending tool_use loop by issuing a read forever.
        looping = [{"type": "tool_use", "id": "tu_x", "name": "read_file", "input": {"path": "buggy.py"}}]
        llm = MockLLM(script=[(looping, "tool_use") for _ in range(20)])
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            agent = Agent(llm=llm, max_iterations=4)
            result = agent.fix(ws)
        assert result.iterations == 4
        assert result.passed is False

    def test_handles_llm_exception(self):
        class BoomLLM:
            def respond(self, **kwargs):
                raise RuntimeError("offline")

        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, BoomLLM())
        assert result.passed is False
        assert result.error is not None
        assert "offline" in result.error

    def test_token_counts_accumulate(self):
        script = _build_canonical_script("01_off_by_one", "range(n)", "range(n + 1)")
        llm = MockLLM(script=script)
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, llm)
        assert result.total_input_tokens > 0
        assert result.total_output_tokens > 0
