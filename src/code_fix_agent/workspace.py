"""Isolated workspace for one bug-fix attempt.

Each Workspace owns:
- A temp directory
- A copy of the bug folder (buggy.py + test_buggy.py)
- A pytest runner that executes the test file from inside the workspace
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from code_fix_agent.sandbox import RunResult, resolve_sandbox, run_pytest


@dataclass
class Workspace:
    """A scratch directory containing one bug's files.

    Use the context-manager form for automatic cleanup:

        with Workspace.from_bug_dir(Path("bugs/01_off_by_one")) as ws:
            ws.read("buggy.py")
            ws.edit("buggy.py", old, new)
            result = ws.run_tests("test_buggy.py")
    """

    root: Path
    bug_id: str = ""
    _cleanup: bool = field(default=False, repr=False)
    # "auto", "docker" or "local"; resolved at construction to the runner used.
    sandbox: str = "auto"
    # Top-level files as they were at setup; score() rebuilds the bug from these.
    originals: dict[str, bytes] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.sandbox = resolve_sandbox(self.sandbox)
        self.originals = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}

    # --- creation ---------------------------------------------------------

    @classmethod
    def from_bug_dir(cls, bug_dir: Path, cleanup: bool = True, sandbox: str = "auto") -> Workspace:
        bug_dir = Path(bug_dir)
        sandbox = resolve_sandbox(sandbox)  # fail before creating the temp dir
        tmp = Path(tempfile.mkdtemp(prefix=f"cfa-{bug_dir.name}-"))
        for child in bug_dir.iterdir():
            if child.is_file():
                shutil.copy2(child, tmp / child.name)
        return cls(root=tmp, bug_id=bug_dir.name, _cleanup=cleanup, sandbox=sandbox)

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._cleanup:
            shutil.rmtree(self.root, ignore_errors=True)

    # --- tools ------------------------------------------------------------

    def resolve(self, rel: str) -> Path:
        """Resolve `rel` (symlinks included) and refuse anything outside the root.

        Every tool goes through this before touching the file system, so an
        error never reveals whether an outside path exists.
        """
        root = self.root.resolve()
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise PermissionError(f"path escapes workspace: {rel}")
        return path

    def list_dir(self, rel: str = ".") -> list[str]:
        target = self.resolve(rel)
        if not target.is_dir():
            raise FileNotFoundError(f"not a directory: {rel}")
        return sorted(p.name for p in target.iterdir())

    def read(self, rel: str) -> str:
        path = self.resolve(rel)
        if not path.is_file():
            raise FileNotFoundError(f"not a file: {rel}")
        return path.read_text(encoding="utf-8")

    def edit(self, rel: str, old: str, new: str) -> str:
        """str_replace edit. Errors if `old` is not found or not unique."""
        path = self.resolve(rel)
        if not path.is_file():
            raise FileNotFoundError(f"not a file: {rel}")
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise ValueError("old string not found in file")
        if text.count(old) > 1:
            raise ValueError(f"old string is not unique ({text.count(old)} matches); add surrounding context")
        new_text = text.replace(old, new, 1)
        path.write_text(new_text, encoding="utf-8")
        return f"edited {rel}; 1 replacement"

    def search(self, pattern: str, rel: str = ".") -> list[tuple[str, int, str]]:
        """Substring search across files in the workspace (Python files only)."""
        root = self.root.resolve()
        target = self.resolve(rel)
        out: list[tuple[str, int, str]] = []
        for path in target.rglob("*.py"):
            path = path.resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern in line:
                    out.append((path.relative_to(root).as_posix(), i, line.rstrip()))
        return out

    def run_tests(self, test_file: str = "test_buggy.py", timeout: float = 30.0) -> dict:
        """Run pytest on test_file. Returns dict with passed/failed counts and output."""
        file_part, sep, node = test_file.partition("::")
        path = self.resolve(file_part)
        if not path.is_file():
            raise FileNotFoundError(f"not a file: {file_part}")
        target = path.relative_to(self.root.resolve()).as_posix() + sep + node
        return _as_result(run_pytest(self.root, [target], timeout=timeout, sandbox=self.sandbox))

    # --- scoring ----------------------------------------------------------

    def score(self, timeout: float = 30.0) -> dict:
        """Run the original test suite against the workspace's current source.

        The model can edit the test file, run a subset of it, or (through the
        code its tests execute) drop a conftest.py into the workspace, so its
        own run_tests result is not a score. This rebuilds the bug in a fresh
        directory from the files present at setup, taking the tests from the
        setup snapshot and every other file from the workspace, and runs the
        whole suite. `tests_modified` reports whether the workspace's test
        files still match the snapshot's SHA-256.
        """
        tests = sorted(name for name in self.originals if _is_test_file(name))
        with tempfile.TemporaryDirectory(prefix="cfa-score-", ignore_cleanup_errors=True) as tmp:
            dest = Path(tmp)
            for name, data in self.originals.items():
                current = self.root / name
                if name in tests:
                    (dest / name).write_bytes(data)
                elif current.is_file():
                    shutil.copyfile(current, dest / name)
            result = _as_result(run_pytest(dest, tests, timeout=timeout, sandbox=self.sandbox))
        result["tests_modified"] = any(
            _sha256(self.root / name) != hashlib.sha256(self.originals[name]).hexdigest()
            for name in tests
        )
        return result


def _is_test_file(name: str) -> bool:
    return name == "conftest.py" or (
        name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))
    )


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _as_result(run: RunResult) -> dict:
    if run.exit_code is None:
        return {
            "passed": False,
            "exit_code": -1,
            "stdout": run.stdout[-4000:],
            "stderr": "timeout",
            "summary": "timeout",
        }
    # pytest prints "X passed in Y.YYs" or "X failed, Y passed in Z.ZZs" last.
    summary = next((line.strip() for line in reversed(run.stdout.splitlines()) if line.strip()), "")
    return {
        "passed": run.exit_code == 0,
        "exit_code": run.exit_code,
        "stdout": run.stdout[-4000:],  # truncate to keep tool result small
        "stderr": run.stderr[-2000:],
        "summary": summary,
    }


@contextmanager
def workspace_for(bug_dir: Path):
    """Convenience context manager."""
    ws = Workspace.from_bug_dir(bug_dir)
    try:
        yield ws
    finally:
        ws.__exit__(None, None, None)
