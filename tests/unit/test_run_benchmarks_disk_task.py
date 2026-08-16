"""Tests for cross-platform disk benchmark task behavior."""

from __future__ import annotations

import os


def test_disk_task_supports_freebsd_execution() -> None:
    task_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "roles",
        "run_benchmarks",
        "tasks",
        "disk.yml",
    )

    with open(task_file, encoding="utf-8") as file_handle:
        content = file_handle.read()

    assert "ansible_system | default('Linux') in ['Linux', 'FreeBSD']" in content
    assert "Detect work directory device (FreeBSD)" in content
    assert 'DROP_CMD="sync; purge 2>/dev/null || sync"' in content
