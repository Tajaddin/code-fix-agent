"""Benchmark driver.

Iterates the 12-bug dataset and runs the bug-fix agent on each. Reports:
- pass rate
- mean iterations to fix
- mean tool calls per bug
- total tokens (input/output) and estimated cost (Haiku 4.5 default rates)
- per-bug detail table

Two modes:
- live:   uses real Anthropic API (needs ANTHROPIC_API_KEY)
- mock:   uses a MockLLM that pre-scripts the obvious fix for each bug.
          Useful as a smoke test of the whole pipeline without spending tokens.

Usage:
    python -m benchmarks.run_benchmark --mode mock
    python -m benchmarks.run_benchmark --mode live --max-iterations 8
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from code_fix_agent.agent import Agent
from code_fix_agent.llm import AnthropicLLM, LLMClient, MockLLM
from code_fix_agent.workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent
BUGS_DIR = ROOT / "bugs"
RESULTS_DIR = Path(__file__).parent / "results"


def _load_manifest() -> list[dict]:
    manifest_path = BUGS_DIR / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data["bugs"]


# Hard-coded fixes for the mock smoke run. Each entry is the (old, new) pair
# that the agent would emit in a perfect world. The mock walks through:
#   1. read_file("buggy.py")
#   2. edit_file("buggy.py", old, new)
#   3. run_tests("test_buggy.py")
#   4. final text "done"
_MOCK_FIXES: dict[str, tuple[str, str]] = {
    "01_off_by_one": ("range(n)", "range(n + 1)"),
    "02_wrong_operator": ("sum(values) * len(values)", "sum(values) / len(values)"),
    "03_missing_return": ("result = x * 2", "result = x * 2\n    return result"),
    "04_mutable_default": ("def append_id(item, log=[]):", "def append_id(item, log=None):\n    if log is None:\n        log = []"),
    "05_wrong_comparison": ('return role != "admin"', 'return role == "admin"'),
    "06_index_error": (
        "    return items[len(items)]",
        "    if not items:\n        return None\n    return items[len(items) - 1]",
    ),
    "07_type_coercion": (
        'return "#" + index + " " + name',
        'return "#" + str(index) + " " + name',
    ),
    "08_inverted_condition": ("    if b:", "    if not b:"),
    "09_early_return": (
        "        if n % 2 == 0:\n            return n\n        return None\n",
        "        if n % 2 == 0:\n            return n\n    return None\n",
    ),
    "10_shallow_copy": ("    result = grids", "    result = [list(g) for g in grids]"),
    "11_missing_init": ("    def __init__(self):\n        pass", "    def __init__(self):\n        self.value = 0"),
    "12_unused_state": (
        "        new_total = self.total + price\n        return new_total",
        "        self.total = self.total + price\n        return self.total",
    ),
}


def _build_mock_llm(bug_id: str) -> MockLLM:
    """Script a MockLLM to perform read -> edit -> test for one bug."""
    old, new = _MOCK_FIXES[bug_id]
    script = [
        # 1. The agent first reads the buggy file.
        (
            [
                {
                    "type": "tool_use",
                    "id": "tu_read",
                    "name": "read_file",
                    "input": {"path": "buggy.py"},
                }
            ],
            "tool_use",
        ),
        # 2. The agent issues the canonical edit.
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
        # 3. The agent runs the tests.
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
        # 4. The agent confirms.
        ([{"type": "text", "text": "Fixed."}], "end_turn"),
    ]
    return MockLLM(script=script)


def _run_one(bug: dict, llm: LLMClient, max_iterations: int) -> dict:
    bug_dir = BUGS_DIR / bug["id"]
    with Workspace.from_bug_dir(bug_dir) as ws:
        agent = Agent(llm=llm, max_iterations=max_iterations)
        result = agent.fix(ws)
    return {
        "id": bug["id"],
        "kind": bug.get("kind", ""),
        "passed": result.passed,
        "iterations": result.iterations,
        "tool_calls": result.tool_calls,
        "elapsed_seconds": result.elapsed_seconds,
        "input_tokens": result.total_input_tokens,
        "output_tokens": result.total_output_tokens,
        "final_summary": result.final_summary,
        "error": result.error,
    }


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Default to Claude Haiku 4.5 list pricing: $1/MTok input, $5/MTok output."""
    return round(input_tokens / 1_000_000 * 1.0 + output_tokens / 1_000_000 * 5.0, 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="code-fix-agent benchmark driver.")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "benchmark.json")
    args = parser.parse_args(argv)

    bugs = _load_manifest()
    records: list[dict] = []
    for bug in bugs:
        if args.mode == "live":
            llm: LLMClient = AnthropicLLM(model=args.model)
        else:
            llm = _build_mock_llm(bug["id"])
        print(f"  [{args.mode}] {bug['id']}", file=sys.stderr)
        records.append(_run_one(bug, llm, args.max_iterations))

    n = len(records)
    passed = sum(1 for r in records if r["passed"])
    summary = {
        "mode": args.mode,
        "n_bugs": n,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / n, 1) if n else 0,
        "mean_iterations": round(sum(r["iterations"] for r in records) / n, 2) if n else 0,
        "mean_tool_calls": round(sum(r["tool_calls"] for r in records) / n, 2) if n else 0,
        "total_input_tokens": sum(r["input_tokens"] for r in records),
        "total_output_tokens": sum(r["output_tokens"] for r in records),
    }
    summary["estimated_cost_usd"] = _estimate_cost(
        summary["total_input_tokens"], summary["total_output_tokens"]
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "records": records}, indent=2), encoding="utf-8"
    )

    print("\n=== code-fix-agent benchmark summary ===")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {args.out}", file=sys.stderr)
    return 0 if summary["pass_rate_pct"] >= 75 else 0  # benchmark never fails CI; readme calls out target


if __name__ == "__main__":
    sys.exit(main())
