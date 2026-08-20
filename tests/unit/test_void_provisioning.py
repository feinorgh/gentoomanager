"""Tests for Void Linux benchmark provisioning support."""

from __future__ import annotations

import os

import pytest
import yaml


@pytest.fixture
def worktree_root() -> str:
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_void_provisioning_installs_make(worktree_root: str) -> None:
    """Void provisioning should install make for compiler_multifile benchmarks."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "void.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = yaml.safe_load(file_handle)

    install_task = next(
        task
        for task in task_content
        if task.get("name") == "Install benchmark dependencies (Void Linux)"
    )
    assert "make" in install_task["loop"]
