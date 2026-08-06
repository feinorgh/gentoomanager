"""Tests for benchmark work directory auto-selection wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _read_yaml(path: str):
    with (REPO_ROOT / path).open(encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle)


def test_defaults_define_workdir_autoselect_variables() -> None:
    defaults = _read_yaml("roles/run_benchmarks/defaults/main.yml")

    assert "run_benchmarks_auto_select_work_dir" in defaults
    assert defaults["run_benchmarks_auto_select_work_dir"] is True
    assert "run_benchmarks_work_dir_candidates" in defaults
    assert "run_benchmarks_work_dir_required_mb" in defaults


def test_selector_task_sets_effective_workdir_facts() -> None:
    content = _read_text("roles/run_benchmarks/tasks/select_work_dir.yml")

    assert "Select benchmark work directory candidate (Unix)" in content
    assert "run_benchmarks_selected_work_dir" in content
    assert "run_benchmarks_effective_work_dir" in content
    assert "No suitable benchmark work directory found" in content


def test_playbook_runs_selector_before_sanity_check() -> None:
    content = _read_text("playbooks/run_benchmarks.yml")

    selector_idx = content.index("roles/run_benchmarks/tasks/select_work_dir.yml")
    sanity_idx = content.index("roles/run_benchmarks/tasks/sanity_check.yml")
    assert selector_idx < sanity_idx


def test_role_main_includes_selector_for_direct_role_usage() -> None:
    content = _read_text("roles/run_benchmarks/tasks/main.yml")

    assert "Resolve benchmark work directory" in content
    assert "file: select_work_dir.yml" in content
