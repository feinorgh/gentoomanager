"""Tests for GIMP benchmark task compatibility logic."""

from __future__ import annotations

import os


def test_gimp_task_supports_v2_and_v3_cli_modes() -> None:
    task_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "roles",
        "run_benchmarks",
        "tasks",
        "gimp.yml",
    )

    with open(task_file, encoding="utf-8") as file_handle:
        content = file_handle.read()

    assert "Select GIMP startup command for detected major version" in content
    assert "--no-data --no-fonts --quit" in content
    assert "--batch='(gimp-quit 0)' --batch-interpreter=plug-in-script-fu-eval" in content
