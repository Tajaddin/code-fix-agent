"""Bench smoke test: run the mock benchmark and assert a perfect mock-pass-rate.

The mock benchmark scripts the canonical fix per bug, so 12/12 should pass
on a healthy pipeline. If this drops, either a fixture changed or the
workspace/tool layer regressed.
"""
from __future__ import annotations

from benchmarks.run_benchmark import _MOCK_FIXES, _build_mock_llm, _load_manifest, _run_one


class TestMockBenchmark:
    def test_all_12_bugs_pass_in_mock_mode(self):
        bugs = _load_manifest()
        assert len(bugs) == 12, "manifest must declare exactly 12 bugs"

        records = []
        for bug in bugs:
            llm = _build_mock_llm(bug["id"])
            records.append(_run_one(bug, llm, max_iterations=8))

        n_passed = sum(1 for r in records if r["passed"])
        assert n_passed == 12, (
            f"expected 12/12 mock passes, got {n_passed}/12. "
            f"failures: {[r['id'] for r in records if not r['passed']]}"
        )

    def test_manifest_has_a_canonical_fix_for_every_bug(self):
        bugs = _load_manifest()
        for bug in bugs:
            assert bug["id"] in _MOCK_FIXES, f"missing canonical fix for {bug['id']}"
