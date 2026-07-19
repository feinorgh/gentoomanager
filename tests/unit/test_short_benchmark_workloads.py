"""Tests for short benchmark workload defaults, wiring, and validation hook."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "defaults" / "main.yml"
BASH_TASK_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "bash.yml"
COREUTILS_TASK_FILE = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "coreutils.yml"
RUN_BENCHMARKS_PLAYBOOK = REPO_ROOT / "playbooks" / "run_benchmarks.yml"


def _load_yaml_list(path: Path) -> list[dict[str, object]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise AssertionError(f"expected YAML list in {path}")
    return loaded


def _get_task_by_name(tasks: list[dict[str, object]], task_name: str, *, source: str) -> dict[str, object]:
    for task in tasks:
        if isinstance(task, dict) and task.get("name") == task_name:
            return task
    raise AssertionError(f"missing task '{task_name}' in {source}")


def _shell_cmd_for_task(task: dict[str, object], *, source: str) -> str:
    shell_task = task.get("ansible.builtin.shell")
    if not isinstance(shell_task, dict):
        raise AssertionError(f"task '{task.get('name')}' in {source} must use ansible.builtin.shell")
    cmd = shell_task.get("cmd")
    if not isinstance(cmd, str):
        raise AssertionError(f"task '{task.get('name')}' in {source} must define a shell cmd string")
    return cmd


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
    bash_tasks = _load_yaml_list(BASH_TASK_FILE)
    coreutils_tasks = _load_yaml_list(COREUTILS_TASK_FILE)

    bash_benchmark_cmd = _shell_cmd_for_task(
        _get_task_by_name(bash_tasks, "Run bash benchmarks", source="bash.yml"),
        source="bash.yml",
    )
    coreutils_benchmark_cmd = _shell_cmd_for_task(
        _get_task_by_name(coreutils_tasks, "Run coreutils benchmarks", source="coreutils.yml"),
        source="coreutils.yml",
    )
    create_git_repo_cmd = _shell_cmd_for_task(
        _get_task_by_name(coreutils_tasks, "Create git test repo", source="coreutils.yml"),
        source="coreutils.yml",
    )

    if "run_benchmarks_bash_startup_iterations" not in bash_benchmark_cmd:
        raise AssertionError("bash task must reference run_benchmarks_bash_startup_iterations")
    if "run_benchmarks_coreutils_wc_repeat" not in coreutils_benchmark_cmd:
        raise AssertionError("coreutils task must reference run_benchmarks_coreutils_wc_repeat")
    if "run_benchmarks_coreutils_find_repeat" not in coreutils_benchmark_cmd:
        raise AssertionError("coreutils task must reference run_benchmarks_coreutils_find_repeat")
    if "run_benchmarks_git_repo_commits" not in create_git_repo_cmd:
        raise AssertionError("coreutils task must reference run_benchmarks_git_repo_commits")
    if "run_benchmarks_git_feature_commits" not in create_git_repo_cmd:
        raise AssertionError("coreutils task must reference run_benchmarks_git_feature_commits")


def test_run_benchmarks_playbook_has_short_results_validation_hook() -> None:
    plays = _load_yaml_list(RUN_BENCHMARKS_PLAYBOOK)
    validate_task_name = "Validate short benchmark results (controller-side)"

    for play in plays:
        if not isinstance(play, dict):
            continue
        tasks = play.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if isinstance(task, dict) and task.get("name") == validate_task_name:
                cmd = _shell_cmd_for_task(task, source="run_benchmarks.yml")
                assert "scripts/validate_short_benchmark_results.py" in cmd
                return

    raise AssertionError(f"missing task '{validate_task_name}' in run_benchmarks.yml")
