# code-fix-agent

> Autonomous Python bug-fix agent on the Anthropic API. **12/12 pass on Claude Haiku 4.5 live, 3.58 mean iterations per bug, $0.10 total cost** (May 2026 run, before the current sandbox and independent scoring; see below). Real pytest-driven fix loop, one temp workspace per attempt, a network-less Docker runner for the tests (not yet run; see [Isolation and scoring](#isolation-and-scoring)), and every fix scored against a clean copy of the original tests.

[![ci](https://github.com/Tajaddin/code-fix-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Tajaddin/code-fix-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

## Hero metrics

Reproducible:
- `python -m benchmarks.run_benchmark --mode mock` (no API key, pipeline smoke; writes `benchmarks/results/benchmark-mock.json`, not committed)
- `python -m benchmarks.run_benchmark --mode live` (needs ANTHROPIC_API_KEY, real Haiku 4.5; writes `benchmarks/results/benchmark.json`)

| Mode | Pass rate | Mean iterations / bug | Mean tool calls / bug | Total tokens | Realized cost (Haiku 4.5) |
|---|---:|---:|---:|---:|---:|
| **mock (pipeline smoke)** | **12 / 12** | 3.0 | 3.0 | 540 | $0.0013 |
| **live (Haiku 4.5), 2026-05-20** | **12 / 12** | **3.58** | **5.58** | 77,457 | **$0.1012** |

Live run logged 2026-05-20: all 12 bugs fixed, no skips, no errors. The agent average 3.58 LLM rounds and 5.58 tool calls per bug. Total spend across the 12-bug sweep was ~10 cents. Per-bug records are in `benchmarks/results/benchmark.json`.

That run predates the current harness. Its pass was the agent's own last `run_tests` call, not the independent scoring described under [Isolation and scoring](#isolation-and-scoring), its prompt included the bug id (which names the bug kind), its tests ran without a sandbox, and its records do not include tool inputs or diffs. Each record's summary shows the bug's full test count passing, so no bug passed on a subset of its tests. It has not yet been re-run on the current harness.

The mock mode scripts the canonical (read -> edit -> run_tests) for each of the 12 bugs. A perfect 12/12 in mock means the workspace, tool dispatch, and agent loop are healthy; CI runs this on every push.

Live mode hands the same 12 bugs to Claude Haiku 4.5 via the Anthropic API, with no scripted fixes. To reproduce:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
docker build -t code-fix-agent:latest .   # the test sandbox; see below
python -m benchmarks.run_benchmark --mode live --max-iterations 8
```

Live runs refuse to start without the sandbox image unless you pass `--sandbox local`, because the local runner cannot keep the API key from model-written code (see [Isolation and scoring](#isolation-and-scoring)).

## The dataset

12 hand-crafted Python bugs in `bugs/`. Each subdirectory contains `buggy.py` plus `test_buggy.py`. The fix is a 1-3 line surgical edit. The agent may read the test file but is told not to change it; scoring ignores any change it makes.

| ID | Bug kind | Expected iters |
|---|---|---:|
| 01_off_by_one | `range(n)` instead of `range(n + 1)` | 2 |
| 02_wrong_operator | `*` instead of `/` in average | 2 |
| 03_missing_return | result computed but never returned | 2 |
| 04_mutable_default | shared `[]` default arg | 3 |
| 05_wrong_comparison | `!=` instead of `==` | 2 |
| 06_index_error | `items[len(items)]` for last element | 3 |
| 07_type_coercion | concatenating int to str without `str()` | 2 |
| 08_inverted_condition | `if b:` instead of `if not b:` | 2 |
| 09_early_return | `return None` inside the loop | 3 |
| 10_shallow_copy | assigning input list reference as output | 4 |
| 11_missing_init | `__init__` does not set tracked attribute | 2 |
| 12_unused_state | local var assigned but never stored on self | 2 |

Each bug has 3-4 pytest assertions; the agent needs to satisfy all of them.

## What you get

| Path | Purpose |
|---|---|
| `src/code_fix_agent/workspace.py` | Tempdir per attempt. Read, edit (str_replace with uniqueness check), search and run_tests, all confined to the workspace root; `score()` and `diff()` for the harness. |
| `src/code_fix_agent/sandbox.py` | Runs pytest in a network-less Docker container, or in a subprocess with a minimal environment when Docker is unavailable. |
| `src/code_fix_agent/tools.py` | Five Anthropic tool definitions and their dispatcher: list_dir, read_file, edit_file, search_code, run_tests. |
| `src/code_fix_agent/agent.py` | The fix loop. Reads response content, dispatches tool_use blocks, sends tool_result back, stops when run_tests reports PASS or iteration budget is exhausted. |
| `src/code_fix_agent/llm.py` | `AnthropicLLM` + `MockLLM` (scripted tool-call sequence). Both return the same `(content, stop_reason, usage)` shape. |
| `benchmarks/run_benchmark.py` | Iterates the dataset, captures pass / iteration / token / cost stats per bug, writes JSON. |

## Why this matters for production

Recruiter signal this maps to:
- **SWE-agent / coding-agent JDs** (Mango Languages, Sekai, M3 USA, Cohere Agent Infrastructure)
- **Tool use + multi-turn loops** (any "Senior AI Engineer, Agentic Systems" role in 2026)
- **Real-pytest-driven evaluation** (not LLM-as-judge, not vibe-graded)
- **Bounded iteration budgets + token budgets** (the diff between a demo agent and a billable agent)

This is the small-bench cousin of SWE-bench-Lite. It runs in seconds on a laptop and costs cents per full sweep. Drop SWE-bench-verified in next to scale; the agent loop does not change.

## Quick start

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...

# Fix one bug, print JSON result (needs the sandbox image, or --sandbox local)
code-fix-agent run bugs/01_off_by_one

# Or run the full 12-bug benchmark
python -m benchmarks.run_benchmark --mode live
```

`run` prints one JSON object and exits 0 when the fix passes scoring, 1 otherwise. Its fields:

| Field | Meaning |
|---|---|
| `bug_id`, `sandbox` | The bug folder's name and the runner the tests used (`docker` or `local`). |
| `passed` | The verdict: the original tests on a clean copy (see [Scoring](#isolation-and-scoring)). |
| `self_reported_pass`, `tests_modified` | The agent's own last `run_tests` said PASS; a test file differs from its setup SHA-256. |
| `iterations`, `tool_calls`, `elapsed_seconds` | Model rounds, tool calls and wall time, scoring included. |
| `total_input_tokens`, `total_output_tokens` | Token usage summed over the rounds. |
| `final_summary` | Status line of the scoring run, e.g. `PASS (exit 0) summary='4 passed in ...'`. |
| `error` | The model call's error, when one ended the loop; otherwise `null`. |
| `final_diff` | Unified diff of the workspace since setup. |

## How the loop works

```
        +-----------+
        |  user msg | "fix the bug in this workspace"
        +-----+-----+
              v
+-------------+--------------+
| Claude with tool schemas:  |
|  list_dir, read_file,      |
|  edit_file, search_code,   |
|  run_tests                 |
+-------------+--------------+
              |
              v        (one or more tool_use blocks per iteration)
       +------+------+
       | dispatch    |--> workspace.read("buggy.py")
       | each tool   |--> workspace.edit("buggy.py", old, new)
       +------+------+--> workspace.run_tests("test_buggy.py")
              |
              v
       +------+------+        no
       | tests PASS? |--------+---> next iteration (up to max=8)
       +------+------+              "here are the tool results"
              |
              yes
              v
  +-----------+-----------+
  | score: full original  |  (also runs when the budget
  | suite on a clean copy |   runs out)
  +-----------------------+
```

The prompt names neither the bug nor its kind. The agent reads `buggy.py` and `test_buggy.py` with `read_file` (the system prompt tells it to) and gets a short traceback (`--tb=short`, last 4,000 characters) from every failing `run_tests` call.

## Isolation and scoring

**Files.** Each attempt runs in a fresh `tempfile.mkdtemp(prefix="cfa-")`. Every tool resolves its path, symlinks included, and refuses anything outside the workspace root with the same error whether or not the outside path exists. `run_tests` accepts only a test file inside the workspace (optionally `file::test`), never pytest options.

**Test runs.** The model writes the code that `run_tests` executes, so it is treated as untrusted. `--sandbox` on the CLI and the benchmark picks the runner:

| `--sandbox` | Runner |
|---|---|
| `docker` | Throwaway container from `code-fix-agent:latest` (override with `CFA_SANDBOX_IMAGE`): `--network none`, read-only root and workspace mount, all capabilities dropped, `no-new-privileges`, 512 MB / 1 CPU / 128 processes, non-root, no host environment. Fails if the image is missing. |
| `local` | Subprocess with only `PATH`, `SYSTEMROOT` and the temp-dir variables in its environment, in its own session (POSIX) or process group (Windows). The clean environment stops the API key from being inherited, not from being read: the tests run as your user, next to the agent process that holds the key, and can read it from there (on Linux, `/proc/<parent pid>/environ`). They also have your file-system and network access. The 30-second timeout kills the test process's group or tree; a process that calls `setsid()`, or on Windows one whose parent already exited, survives it. A fallback, not a sandbox. |
| `auto` (default) | `docker` when `docker image inspect` finds the image. Otherwise `local` for mock runs, and an error for live runs (`code-fix-agent run`, `--mode live`): pass `--sandbox local` to run those without the image. |

Build the image once with `docker build -t code-fix-agent:latest .`. Every result records the runner used.

**The Docker runner is untested so far:** it has not run on any machine yet. The CI `docker` job builds the image, runs the container test (`TestDockerSandbox`) and the mock benchmark with `--sandbox docker`, and runs the benchmark inside the image as its non-root user; until that job passes, treat the `docker` row above as a design, not a result.

**Scoring.** The agent's own `run_tests` result is not the verdict: it chooses which tests to run and can edit the test file. After the loop, the harness rebuilds the bug in a fresh directory from the files present at setup (tests from the setup snapshot, other files from the workspace, nothing the run created) and runs the whole suite with the same runner. That is `passed`, and exit code 0 is not enough: every test collected from the bug as it was at setup must be reported `PASSED` and the counts must hold nothing else, so a `pytest.skip()`, a `pytest.xfail()` or an early `os._exit(0)` in the source fails. The verdict is read from pytest's output, and under either runner the code under test runs inside that pytest process: code written to forge the output (fake result lines, patched reporting) is not caught. `self_reported_pass` keeps the agent's claim, and `tests_modified` flags test files that no longer match their SHA-256 from setup. Benchmark records also keep every tool input and the final diff.

## Testing

```bash
pytest --cov=code_fix_agent
```

66 tests (the Docker one is skipped when the image is not built, the symlink one where creating symlinks needs admin rights):
- `test_workspace.py` — copy, list, read, edit (success + missing-substring error), run_tests (fails on unfixed, passes on canonical fix), no inherited secrets, timeout kills child processes, sandbox selection (live runs do not fall back to the local runner) and the Docker command line.
- `test_tools.py` — schema completeness, dispatch, error surfacing, tracebacks in failing output, path confinement for every tool (`..`, absolute paths, symlinks).
- `test_agent.py` — full read-edit-test loop with `MockLLM` on bugs 1 and 2, max-iteration safety, LLM exception handling, token accounting, scoring against subset runs, edited tests, a planted `conftest.py` and source that skips, xfails or exits early; no bug id in the prompt, tool inputs and the diff (created and deleted files included) in the result, API timeout.
- `test_bench_smoke.py` — runs the full mock benchmark (12 bugs) and asserts 12/12 pass; the mock run exits non-zero on any failure and does not overwrite the live record.

The bench smoke test is the canary: if it ever drops below 12/12 in CI, either the dataset or the workspace layer regressed.

## Docker

```bash
docker compose run --rm bench                                # full mock benchmark
docker compose run --rm fix run --sandbox local bugs/01_off_by_one  # one bug with live API
```

The image runs as a non-root user. It is also the test sandbox image (`code-fix-agent:latest`). Inside a compose container there is no Docker CLI, so tests there use the local runner within that container, which holds the API key: the `fix` service passes `--sandbox local` to accept that.

## Project layout

```
bugs/
  01_off_by_one/
    buggy.py
    test_buggy.py
  ... (12 total)
  manifest.json

src/code_fix_agent/
  workspace.py        # tempdir + read/edit/test
  tools.py            # 5 Anthropic tool defs + dispatcher
  llm.py              # AnthropicLLM + MockLLM
  agent.py            # tool-use loop with iteration cap
  cli.py              # `code-fix-agent run <bug_dir>`

benchmarks/
  run_benchmark.py    # iterates all 12, captures stats
  results/
    benchmark.json      # the live run's record
```

## What this is NOT

- SWE-bench-Lite. The 12 bugs are hand-written and one-file. A SWE-bench harness adapter is a one-day port.
- An IDE plugin. The agent runs once per invocation; live coding flow is a thin wrapper around `code-fix-agent run`.
- Multi-file refactor capable. Each tool acts on one file at a time. Multi-file fixes work but cost more iterations.

## License

MIT
