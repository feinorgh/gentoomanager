"""Tests for OpenBSD benchmark command resolution support."""

import os

import pytest
import yaml


@pytest.fixture
def worktree_root():
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_verify_yml_openbsd_friendly_commands(worktree_root):
    """Test that verify.yml supports OpenBSD-friendly command detection."""
    verify_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "verify.yml"
    )
    with open(verify_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        verify_tasks = yaml.safe_load(content)

    # Find the tool availability task
    tool_check_task = None
    for task in verify_tasks:
        if task.get("name") == "Verify essential tools are available":
            tool_check_task = task
            break

    assert tool_check_task is not None, "Tool verification task not found"

    # Verify that the command checks for both python and python3
    # OpenBSD typically has 'python' or 'python3' depending on version
    cmd = tool_check_task.get("ansible.builtin.shell", {}).get("cmd", "")
    assert "python3" in cmd and "python" in cmd, (
        "verify.yml should check for both python3 and python availability"
    )

    # It should NOT hardcode python3 in the essential tools loop
    assert "for tool in hyperfine gcc python3 openssl git" not in cmd, (
        "verify.yml should not hardcode python3 in the essential tools list; "
        "it should handle python/python3 separately for OpenBSD compatibility"
    )

    # Verify executable is /bin/sh (POSIX-compatible, works on OpenBSD)
    executable = tool_check_task.get("ansible.builtin.shell", {}).get("executable", "")
    assert executable == "/bin/sh", (
        "verify.yml should use /bin/sh for OpenBSD compatibility"
    )


def test_setup_yml_defines_resolved_command_facts(worktree_root):
    """Test that setup.yml defines resolved command facts for OpenBSD."""
    setup_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml"
    )
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    # Check for command resolution facts
    # Should define facts for python, gcc, and privilege escalation
    assert "run_benchmarks_python_cmd" in content or "_python_cmd" in content, (
        "setup.yml should define a Python command resolution fact"
    )
    assert "run_benchmarks_gcc_cmd" in content or "_gcc_cmd" in content, (
        "setup.yml should define a GCC command resolution fact"
    )
    assert "run_benchmarks_priv_cmd" in content or "_priv_cmd" in content, (
        "setup.yml should define a privilege escalation command resolution fact"
    )

    # Verify there are tasks that detect these commands
    setup_tasks = yaml.safe_load(content)

    # Look for tasks that resolve python command
    python_resolve_task = None
    for task in setup_tasks:
        task_name = task.get("name", "").lower()
        if "python" in task_name and ("detect" in task_name or "resolve" in task_name):
            python_resolve_task = task
            break

    assert python_resolve_task is not None, (
        "setup.yml should have a task to detect/resolve Python command"
    )

    # Look for tasks that resolve privilege escalation command
    priv_resolve_task = None
    for task in setup_tasks:
        task_name = task.get("name", "").lower()
        if ("sudo" in task_name or "doas" in task_name or "priv" in task_name) and (
            "detect" in task_name or "resolve" in task_name
        ):
            priv_resolve_task = task
            break

    assert priv_resolve_task is not None, (
        "setup.yml should have a task to detect/resolve privilege escalation command (sudo/doas)"
    )


def test_sanity_check_yml_uses_resolved_privilege_command(worktree_root):
    """Test that sanity_check.yml uses resolved privilege command instead of hardcoded sudo."""
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )
    with open(sanity_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        sanity_tasks = yaml.safe_load(content)

    # Find the sudo/privilege escalation probe task
    priv_probe_task = None
    for task in sanity_tasks:
        task_name = task.get("name", "").lower()
        if "sudo" in task_name or "priv" in task_name:
            priv_probe_task = task
            break

    assert priv_probe_task is not None, "Privilege escalation probe task not found"

    # The task should NOT hardcode 'sudo' directly but use a variable
    # or be conditional based on OS
    task_cmd_module = None
    if "ansible.builtin.command" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.command"]
    elif "ansible.builtin.shell" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.shell"]

    if task_cmd_module:
        cmd = task_cmd_module.get("cmd", "")
        # The command should either:
        # 1. Use a variable like {{ run_benchmarks_priv_cmd }}
        # 2. Not hardcode just 'sudo'
        # Check that if 'sudo' appears, it's part of a variable or conditional
        if "sudo" in cmd and "{{" not in cmd:
            pytest.fail(
                "sanity_check.yml should use resolved privilege command variable, "
                "not hardcode 'sudo'"
            )

    # Additional check: the task name should be more generic
    task_name = priv_probe_task.get("name", "")
    # If it's still called "Probe passwordless sudo access", it should be updated
    # to be more generic like "Probe passwordless privilege escalation"
    if "passwordless sudo" in task_name.lower():
        pytest.fail(
            "sanity_check.yml task name should be generic (e.g., 'privilege escalation') "
            "not sudo-specific"
        )


def test_setup_yml_version_gathering_uses_resolved_commands(worktree_root):
    """Test that setup.yml version gathering uses resolved commands where relevant."""
    setup_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml"
    )
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        setup_tasks = yaml.safe_load(content)

    # Find the version gathering task
    version_task = None
    for task in setup_tasks:
        if "compiler and tool versions" in task.get("name", "").lower():
            version_task = task
            break

    assert version_task is not None, "Version gathering task not found"

    # The version gathering should use resolved commands
    cmd_module = None
    if "ansible.builtin.shell" in version_task:
        cmd_module = version_task["ansible.builtin.shell"]

    assert cmd_module is not None, "Version gathering should use shell module"

    # The command should use resolved variables for gcc, python, and numpy
    cmd = cmd_module.get("cmd", "")
    assert "python" in cmd.lower(), (
        "Version gathering should check Python version"
    )

    # Verify it uses the resolved variable, not hardcoded commands
    assert "{{ run_benchmarks_gcc_cmd }}" in cmd, (
        "Version gathering should use {{ run_benchmarks_gcc_cmd }} for gcc version"
    )
    assert "{{ run_benchmarks_python_cmd }}" in cmd, (
        "Version gathering should use {{ run_benchmarks_python_cmd }} for python version"
    )

    # Count occurrences - should use the variable twice (python version + numpy)
    python_var_count = cmd.count("{{ run_benchmarks_python_cmd }}")
    assert python_var_count >= 2, (
        f"Version gathering should use {{{{ run_benchmarks_python_cmd }}}} at least twice "
        f"(python version + numpy), found {python_var_count} uses"
    )

    # Verify it does NOT hardcode python3 anymore
    assert "$(python3 --version" not in cmd, (
        "Version gathering should not hardcode 'python3', use resolved variable instead"
    )
    assert "$(python3 -c 'import numpy" not in cmd, (
        "Numpy check should not hardcode 'python3', use resolved variable instead"
    )

    # The command should have python3 version gathering
    cmd = cmd_module.get("cmd", "")
    assert "python" in cmd.lower(), (
        "Version gathering should check Python version"
    )
