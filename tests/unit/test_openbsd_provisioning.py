"""Tests for OpenBSD benchmark provisioning support."""

import os

import pytest
import yaml


@pytest.fixture
def worktree_root():
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_openbsd_defaults_exist(worktree_root):
    """Test that OpenBSD package defaults exist in main.yml."""
    defaults_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "defaults", "main.yml"
    )
    with open(defaults_path, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    # Check base packages
    assert "OpenBSD" in defaults["provision_benchmarks_packages"], (
        "OpenBSD not in provision_benchmarks_packages"
    )
    assert isinstance(defaults["provision_benchmarks_packages"]["OpenBSD"], list), (
        "OpenBSD packages should be a list"
    )
    assert len(defaults["provision_benchmarks_packages"]["OpenBSD"]) > 0, (
        "OpenBSD packages list should not be empty"
    )

    # Check numpy packages
    assert "OpenBSD" in defaults["provision_benchmarks_numpy_packages"], (
        "OpenBSD not in provision_benchmarks_numpy_packages"
    )

    # Check opencv packages
    assert "OpenBSD" in defaults["provision_benchmarks_opencv_packages"], (
        "OpenBSD not in provision_benchmarks_opencv_packages"
    )

    # Check botan packages
    assert "OpenBSD" in defaults["provision_benchmarks_botan_packages"], (
        "OpenBSD not in provision_benchmarks_botan_packages"
    )

    # Check mold packages
    assert "OpenBSD" in defaults["provision_benchmarks_mold_packages"], (
        "OpenBSD not in provision_benchmarks_mold_packages"
    )

    # Check octave packages
    assert "OpenBSD" in defaults["provision_benchmarks_octave_packages"], (
        "OpenBSD not in provision_benchmarks_octave_packages"
    )


def test_openbsd_task_file_exists(worktree_root):
    """Test that OpenBSD OS task file exists."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openbsd.yml"
    )
    assert os.path.exists(task_path), f"OpenBSD task file should exist at {task_path}"


def test_openbsd_main_yml_mapping(worktree_root):
    """Test that main.yml maps OpenBSD correctly."""
    main_path = os.path.join(worktree_root, "roles", "provision_benchmarks", "tasks", "main.yml")
    with open(main_path, encoding="utf-8") as file_handle:
        main_content = file_handle.read()
        main_yaml = yaml.safe_load(main_content)

    # Find the include_tasks task with _os_family_map
    include_task = None
    for task in main_yaml:
        if "ansible.builtin.include_tasks" in task:
            include_task = task
            break

    assert include_task is not None, "include_tasks task not found"
    assert "vars" in include_task, "vars not in include_tasks"
    assert "_os_family_map" in include_task["vars"], "_os_family_map not in vars"

    os_family_map = include_task["vars"]["_os_family_map"]
    assert "OpenBSD" in os_family_map, "OpenBSD not in _os_family_map"
    assert os_family_map["OpenBSD"] == "openbsd", "OpenBSD should map to 'openbsd'"


def test_openbsd_playbook_integration(worktree_root):
    """Test that playbooks/provision_benchmarks.yml contains OpenBSD support."""
    playbook_path = os.path.join(worktree_root, "playbooks", "provision_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook_content = file_handle.read()
        playbook_yaml = yaml.safe_load_all(playbook_content)
        plays = []
        for item in playbook_yaml:
            if isinstance(item, list):
                plays.extend(item)
            else:
                plays.append(item)

    # Check that there's a grouping task for OpenBSD
    grouping_play = None
    for play in plays:
        if (
            isinstance(play, dict)
            and play.get("name") == "Gather facts and group hosts by OS family"
        ):
            grouping_play = play
            break

    assert grouping_play is not None, "Gather facts play not found"

    # Check for group_by task that includes OpenBSD
    tasks = grouping_play.get("tasks", [])
    group_by_task = None
    for task in tasks:
        if "ansible.builtin.group_by" in task:
            if "when" in task and "OpenBSD" in str(task["when"]):
                group_by_task = task
                break

    assert group_by_task is not None, "OpenBSD should be in grouping task"

    # Check that there's a play for provision_os_openbsd
    openbsd_play = None
    for play in plays:
        if isinstance(play, dict) and play.get("hosts") == "provision_os_openbsd":
            openbsd_play = play
            break

    assert openbsd_play is not None, "provision_os_openbsd play not found"
    assert openbsd_play.get("name") == "Provision OpenBSD hosts", (
        "OpenBSD play should be named 'Provision OpenBSD hosts'"
    )

    # Check that the play includes the role with tasks_from
    openbsd_tasks = openbsd_play.get("tasks", [])
    assert len(openbsd_tasks) > 0, "OpenBSD play should have tasks"

    role_task = openbsd_tasks[0]
    assert "ansible.builtin.include_role" in role_task, "First task should include_role"
    assert role_task["ansible.builtin.include_role"]["name"] == "provision_benchmarks", (
        "Should include provision_benchmarks role"
    )
    assert role_task["ansible.builtin.include_role"]["tasks_from"] == "os/openbsd.yml", (
        "Should use tasks_from: os/openbsd.yml"
    )
