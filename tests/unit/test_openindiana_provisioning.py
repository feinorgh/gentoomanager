"""Tests for OpenIndiana benchmark provisioning support."""

import os

import pytest
import yaml


@pytest.fixture
def worktree_root():
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_openindiana_defaults_exist(worktree_root):
    """Test that OpenIndiana package defaults exist in main.yml."""
    defaults_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "defaults", "main.yml"
    )
    with open(defaults_path, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    assert "OpenIndiana" in defaults["provision_benchmarks_packages"], (
        "OpenIndiana not in provision_benchmarks_packages"
    )
    assert isinstance(defaults["provision_benchmarks_packages"]["OpenIndiana"], list), (
        "OpenIndiana packages should be a list"
    )
    assert len(defaults["provision_benchmarks_packages"]["OpenIndiana"]) > 0, (
        "OpenIndiana packages list should not be empty"
    )

    assert "OpenIndiana" in defaults["provision_benchmarks_numpy_packages"], (
        "OpenIndiana not in provision_benchmarks_numpy_packages"
    )
    assert "OpenIndiana" in defaults["provision_benchmarks_opencv_packages"], (
        "OpenIndiana not in provision_benchmarks_opencv_packages"
    )
    assert "OpenIndiana" in defaults["provision_benchmarks_botan_packages"], (
        "OpenIndiana not in provision_benchmarks_botan_packages"
    )
    assert "OpenIndiana" in defaults["provision_benchmarks_mold_packages"], (
        "OpenIndiana not in provision_benchmarks_mold_packages"
    )
    assert "OpenIndiana" in defaults["provision_benchmarks_octave_packages"], (
        "OpenIndiana not in provision_benchmarks_octave_packages"
    )


def test_openindiana_task_file_exists(worktree_root):
    """Test that OpenIndiana OS task file exists."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    assert os.path.exists(task_path), f"OpenIndiana task file should exist at {task_path}"

    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "verify.yml" in task_content, "OpenIndiana provisioning should include verify.yml"
    assert "hyperfine_fallback.yml" not in task_content, (
        "OpenIndiana provisioning must not rely on Linux-only hyperfine fallback tarball"
    )


def test_openindiana_playbook_integration(worktree_root):
    """Test that playbooks/provision_benchmarks.yml contains OpenIndiana support."""
    playbook_path = os.path.join(worktree_root, "playbooks", "provision_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook_yaml = yaml.safe_load_all(file_handle.read())
        plays = []
        for item in playbook_yaml:
            if isinstance(item, list):
                plays.extend(item)
            else:
                plays.append(item)

    grouping_play = None
    for play in plays:
        if (
            isinstance(play, dict)
            and play.get("name") == "Gather facts and group hosts by OS family"
        ):
            grouping_play = play
            break

    assert grouping_play is not None, "Gather facts play not found"
    tasks = grouping_play.get("tasks", [])
    distribution_group_task = None
    for task in tasks:
        if task.get("name") == "Group by distribution (non-standard OS families)":
            distribution_group_task = task
            break

    assert distribution_group_task is not None, (
        "Distribution grouping task should exist for non-standard OS families like OpenIndiana"
    )

    openindiana_play = None
    for play in plays:
        if isinstance(play, dict) and play.get("hosts") == "provision_os_openindiana":
            openindiana_play = play
            break

    assert openindiana_play is not None, "provision_os_openindiana play not found"
    assert openindiana_play.get("name") == "Provision OpenIndiana hosts", (
        "OpenIndiana play should be named 'Provision OpenIndiana hosts'"
    )

    openindiana_tasks = openindiana_play.get("tasks", [])
    assert len(openindiana_tasks) > 0, "OpenIndiana play should have tasks"
    role_task = openindiana_tasks[0]
    assert "ansible.builtin.include_role" in role_task, "First task should include_role"
    assert role_task["ansible.builtin.include_role"]["name"] == "provision_benchmarks", (
        "Should include provision_benchmarks role"
    )
    assert role_task["ansible.builtin.include_role"]["tasks_from"] == "os/openindiana.yml", (
        "Should use tasks_from: os/openindiana.yml"
    )
