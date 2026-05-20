"""CLI entry point.

Usage:
    code-fix-agent run bugs/01_off_by_one
    code-fix-agent run-all bugs/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from code_fix_agent.agent import Agent
from code_fix_agent.llm import AnthropicLLM
from code_fix_agent.workspace import Workspace


def _cmd_run(args: argparse.Namespace) -> int:
    llm = AnthropicLLM(model=args.model)
    agent = Agent(llm=llm, max_iterations=args.max_iterations)
    with Workspace.from_bug_dir(Path(args.bug_dir)) as ws:
        result = agent.fix(ws)
    payload = {
        "bug_id": result.bug_id,
        "passed": result.passed,
        "iterations": result.iterations,
        "tool_calls": result.tool_calls,
        "elapsed_seconds": result.elapsed_seconds,
        "total_input_tokens": result.total_input_tokens,
        "total_output_tokens": result.total_output_tokens,
        "final_summary": result.final_summary,
        "error": result.error,
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous Python bug-fix agent.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Fix one bug.")
    p_run.add_argument("bug_dir", type=str, help="Path to a bug subdirectory.")
    p_run.add_argument("--model", default="claude-haiku-4-5-20251001")
    p_run.add_argument("--max-iterations", type=int, default=8)
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
