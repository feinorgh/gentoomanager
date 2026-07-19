"""Tests for short benchmark workload defaults, wiring, and validation hook."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "defaults" / "main.yml"
BASH_TASK_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "bash.yml"
COREUTILS_TASK_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "coreutils.yml"
RUN_BENCHMARKS_PLAYBOOK = REPO_ROOT / "playbooks" / "run_benchmarks.yml"


def test_short_benchmark_defaults_are_defined() -> None:
    defaults = yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8"))

    assert defaults["run_benchmarks_bash_startup_iterations"] == 200
    assert defaults["run_benchmarks_coreutils_wc_repeat"] == 50
    assert defaults["run_benchmarks_coreutils_find_repeat"] == 20
    assert defaults["run_benchmarks_git_repo_commits"] == 500
    assert defaults["run_benchmarks_git_feature_commits"] == 100
    assert defaults["run_benchmarks_rust_runtime_iterations"] == 50000000
    assert defaults["run_benchmarks_short_results_require_exit_code_zero"] is True


def test_short_benchmark_wiring_is_present_in_task_files() -> None:
    bash_task = BASH_TASK_FILE.read_text(encoding="utf-8")
    coreutils_task = COREUTILS_TASK_FILE.read_text(encoding="utf-8")

    if "run_benchmarks_bash_startup_iterations" not in bash_task:
        raise AssertionError("bash task must reference run_benchmarks_bash_startup_iterations")
    if "run_benchmarks_coreutils_wc_repeat" not in coreutils_task:
        raise AssertionError("coreutils task must reference run_benchmarks_coreutils_wc_repeat")
    if "run_benchmarks_coreutils_find_repeat" not in coreutils_task:
        raise AssertionError("coreutils task must reference run_benchmarks_coreutils_find_repeat")
    if "run_benchmarks_git_repo_commits" not in coreutils_task:
        raise AssertionError("coreutils task must reference run_benchmarks_git_repo_commits")
    if "run_benchmarks_git_feature_commits" not in coreutils_task:
        raise AssertionError("coreutils task must reference run_benchmarks_git_feature_commits")


def test_run_benchmarks_playbook_has_short_results_validation_hook() -> None:
    content = RUN_BENCHMARKS_PLAYBOOK.read_text(encoding="utf-8")

    assert "Validate short benchmark results (controller-side)" in content
    assert "scripts/validate_short_benchmark_results.py" in content
