"""Tests for run_benchmarks defaults needed by isolated task includes."""

from __future__ import annotations

import os

import yaml

DEFAULTS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "roles", "run_benchmarks", "defaults", "main.yml"
)


def test_defaults_define_python_command_fact() -> None:
    with open(DEFAULTS_FILE, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    assert "run_benchmarks_python_cmd" in defaults, (
        "defaults/main.yml must define run_benchmarks_python_cmd so isolated task "
        "includes (for example boot_time.yml in integration tests) do not fail "
        "with an undefined variable"
    )
    assert defaults["run_benchmarks_python_cmd"] == "python3"
