"""Tests for general RAM-pressure pre-flight warnings."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_sanity_check_probes_memavailable_and_swap_usage() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "MemAvailable" in content
    assert "SwapTotal" in content
    assert "SwapFree" in content
    assert "run_benchmarks_sanity_memavail_raw" in content
    assert "run_benchmarks_sanity_swap_raw" in content


def test_sanity_check_has_general_ram_pressure_warning_logic() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "run_benchmarks_sanity_ram_pressure_warn" in content
    assert "run_benchmarks_sanity_ram_pressure_required_mb" in content
    assert "Low available RAM for selected benchmark categories" in content
    assert "_cats_yaml.split(',')" in content
    assert "cfg.get(category_name, 0)" in content


def test_sanity_check_guards_ram_threshold_vars_before_role_defaults() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "run_benchmarks_min_available_ram_mb | default(1024)" in content
    assert "run_benchmarks_warn_swap_used_pct | default(25)" in content


def test_sanity_notes_include_ram_pressure_context() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "ram_pressure" in content
    assert "available_mb" in content
    assert "swap_used_pct" in content
    assert "warning:" in content


def test_defaults_define_general_ram_warning_variables() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "roles/run_benchmarks/defaults/main.yml").read_text(encoding="utf-8")
    )
    assert "run_benchmarks_min_available_ram_mb" in defaults
    assert "run_benchmarks_warn_swap_used_pct" in defaults
    assert "run_benchmarks_ram_pressure_category_add_mb" in defaults


def test_sanity_ram_required_mb_not_derived_from_same_task_fact() -> None:
    tasks = yaml.safe_load(
        (REPO_ROOT / "roles/run_benchmarks/tasks/sanity_check.yml").read_text(encoding="utf-8")
    )
    for task in tasks:
        facts = task.get("ansible.builtin.set_fact")
        if not isinstance(facts, dict):
            continue
        assert not (
            "run_benchmarks_sanity_ram_pressure_add_mb" in facts
            and "run_benchmarks_sanity_ram_pressure_required_mb" in facts
        ), (
            "set_fact must not define run_benchmarks_sanity_ram_pressure_add_mb and "
            "run_benchmarks_sanity_ram_pressure_required_mb in the same task."
        )
