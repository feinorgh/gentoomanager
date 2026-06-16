"""Tests for benchmark failure logging in run_benchmarks playbook flow."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_run_playbook_records_and_fetches_failure_artifacts() -> None:
    content = _read("playbooks/run_benchmarks.yml")
    assert "Record benchmark suite failure artifact" in content
    assert "Find partial benchmark result files after failure (Unix)" in content
    assert "Fetch partial benchmark results to controller after failure" in content


def test_sanity_notes_include_benchmark_failures_key() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "benchmark_failures" in content
