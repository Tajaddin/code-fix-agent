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


class TestIndependentScoring:
    """The verdict comes from the original tests, not from the model's own run."""

    def test_running_only_an_already_passing_test_is_not_a_fix(self):
        llm = MockLLM(
            script=[
                (
                    [
                        {
                            "type": "tool_use",
                            "id": "tu_test",
                            "name": "run_tests",
                            "input": {"test_file": "test_buggy.py::test_zero"},
                        }
                    ],
                    "tool_use",
                )
            ]
        )
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, llm)
        assert result.self_reported_pass is True
        assert result.passed is False
        assert "3 failed, 1 passed" in result.final_summary

    def test_editing_the_tests_is_not_a_fix(self):
        rewrite = {
            "path": "test_buggy.py",
            "old": "from buggy import sum_first_n",
            "new": "def sum_first_n(n):\n    return n * (n + 1) // 2",
        }
        llm = MockLLM(
            script=[
                ([{"type": "tool_use", "id": "tu_edit", "name": "edit_file", "input": rewrite}], "tool_use"),
                ([{"type": "tool_use", "id": "tu_test", "name": "run_tests", "input": {}}], "tool_use"),
            ]
        )
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, llm)
        assert result.self_reported_pass is True
        assert result.tests_modified is True
        assert result.passed is False

    def test_a_real_fix_scores_as_passed_with_tests_untouched(self):
        script = _build_canonical_script("01_off_by_one", "range(n)", "range(n + 1)")
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, MockLLM(script=script))
        assert result.passed is True
        assert result.self_reported_pass is True
        assert result.tests_modified is False
        assert result.final_summary.startswith("PASS (exit 0) summary='4 passed")

    def test_score_ignores_files_created_during_the_run(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one"), sandbox="local") as ws:
            (ws.root / "conftest.py").write_text(
                "import buggy\nbuggy.sum_first_n = lambda n: n * (n + 1) // 2\n", encoding="utf-8"
            )
            assert ws.run_tests()["passed"] is True
            verdict = ws.score()
        assert verdict["passed"] is False
        assert verdict["summary"].startswith("3 failed, 1 passed")


class TestNoBenchmarkHints:
    def test_prompt_and_paths_do_not_name_the_bug(self):
        llm = MockLLM(script=[([{"type": "tool_use", "id": "tu_ls", "name": "list_dir", "input": {}}], "tool_use")])
        with Workspace.from_bug_dir(_bug_dir("04_mutable_default")) as ws:
            run_agent(ws, llm)
            root_name = ws.root.name
        first_prompt = llm.last_messages[0][0]["content"]
        for hint in ("04_mutable_default", "mutable", "default"):
            assert hint not in first_prompt
            assert hint not in root_name


class TestAuditTrail:
    def test_result_records_tool_inputs_and_the_final_diff(self):
        script = _build_canonical_script("01_off_by_one", "range(n)", "range(n + 1)")
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, MockLLM(script=script))
        assert [step["tool"] for step in result.tool_trail] == ["read_file", "edit_file", "run_tests"]
        assert result.tool_trail[1]["input"] == {"path": "buggy.py", "old": "range(n)", "new": "range(n + 1)"}
        assert "--- a/buggy.py" in result.final_diff
        assert "-    for i in range(n):" in result.final_diff
        assert "+    for i in range(n + 1):" in result.final_diff
        assert "test_buggy.py" not in result.final_diff

    def test_no_edit_means_an_empty_diff(self):
        with Workspace.from_bug_dir(_bug_dir("01_off_by_one")) as ws:
            result = run_agent(ws, MockLLM(script=[]))
        assert result.final_diff == ""


class TestAnthropicClient:
    def test_requests_have_an_explicit_timeout(self):
        from code_fix_agent.llm import AnthropicLLM

        assert AnthropicLLM(api_key="sk-ant-test")._client.timeout == 60.0
        assert AnthropicLLM(api_key="sk-ant-test", timeout=5.0)._client.timeout == 5.0
