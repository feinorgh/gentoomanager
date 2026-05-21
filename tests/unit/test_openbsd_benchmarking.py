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
    assert executable == "/bin/sh", "verify.yml should use /bin/sh for OpenBSD compatibility"


def test_setup_yml_defines_resolved_command_facts(worktree_root):
    """Test that setup.yml defines resolved command facts for OpenBSD."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
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
    """Test sanity_check.yml privilege probe handles sudo AND doas (not just hardcoded sudo)."""
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

    # The task should handle both sudo and doas, not just hardcode sudo
    task_cmd_module = None
    if "ansible.builtin.command" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.command"]
    elif "ansible.builtin.shell" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.shell"]

    if task_cmd_module:
        cmd = task_cmd_module.get("cmd", "")
        # The command should check for both sudo AND doas to be OpenBSD-friendly
        # It can either:
        # 1. Use a variable like {{ run_benchmarks_priv_cmd }}
        # 2. Use inline detection that checks for both commands
        has_sudo = "sudo" in cmd
        has_doas = "doas" in cmd

        if has_sudo and not has_doas:
            pytest.fail(
                "sanity_check.yml privilege probe should handle both sudo and doas "
                "for OpenBSD compatibility, not just sudo"
            )

    # Additional check: the task name should be generic
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
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
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
    assert "python" in cmd.lower(), "Version gathering should check Python version"

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


def test_sanity_check_yml_python_detection_openbsd_friendly(worktree_root):
    """Test that sanity_check.yml probe checks for python3 OR python (OpenBSD-friendly)."""
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )
    with open(sanity_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        sanity_tasks = yaml.safe_load(content)

    # Find the tool availability probe task
    tool_probe_task = None
    for task in sanity_tasks:
        if task.get("name") == "Probe benchmark tool availability":
            tool_probe_task = task
            break

    assert tool_probe_task is not None, "Tool availability probe task not found"

    # Get the shell command
    cmd = tool_probe_task.get("ansible.builtin.shell", {}).get("cmd", "")

    # Should check for both python3 and python
    assert "python3" in cmd and "python" in cmd, (
        "sanity_check.yml probe should check for both python3 and python"
    )

    # Should NOT hardcode python3 in the required tools loop
    assert "for tool in hyperfine gcc python3 openssl" not in cmd, (
        "sanity_check.yml should not hardcode python3 in required tools list; "
        "it should handle python/python3 separately for OpenBSD compatibility"
    )

    # Should handle python separately like imagemagick
    assert "command -v python3" in cmd or "command -v python" in cmd, (
        "sanity_check.yml should explicitly check for python3 or python availability"
    )

    # Verify it uses /bin/sh for POSIX compatibility
    executable = tool_probe_task.get("ansible.builtin.shell", {}).get("executable", "")
    assert executable == "/bin/sh", "sanity_check.yml should use /bin/sh for OpenBSD compatibility"


def test_sanity_check_yml_privilege_probe_detects_inline(worktree_root):
    """Test sanity_check.yml privilege probe detects sudo/doas inline (not late-bound var)."""
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )
    with open(sanity_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        sanity_tasks = yaml.safe_load(content)

    # Find the privilege escalation probe task
    priv_probe_task = None
    for task in sanity_tasks:
        task_name = task.get("name", "").lower()
        if "priv" in task_name or "sudo" in task_name or "doas" in task_name:
            priv_probe_task = task
            break

    assert priv_probe_task is not None, "Privilege escalation probe task not found"

    # The task should NOT rely on run_benchmarks_priv_cmd being defined by setup.yml
    # because sanity_check runs BEFORE setup.yml in the playbook workflow.
    # It must detect sudo/doas inline to work on OpenBSD before setup runs.
    task_cmd_module = None
    if "ansible.builtin.command" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.command"]
    elif "ansible.builtin.shell" in priv_probe_task:
        task_cmd_module = priv_probe_task["ansible.builtin.shell"]

    assert task_cmd_module is not None, "Privilege probe should use command or shell module"

    cmd = task_cmd_module.get("cmd", "")

    # The command should detect sudo/doas inline, not rely on run_benchmarks_priv_cmd
    # which doesn't exist yet when sanity_check runs in the playbook.
    # It should either:
    # 1. Use a shell command that checks for both (e.g., command -v sudo || command -v doas)
    # 2. Be a multi-command script that tries both
    # It should NOT just use {{ run_benchmarks_priv_cmd | default('sudo') }}
    # because that defaults to sudo and fails on OpenBSD-only-doas systems.

    # Check for Jinja2 variable usage (not in comments)
    cmd_lines = [line for line in cmd.split("\n") if not line.strip().startswith("#")]
    cmd_without_comments = "\n".join(cmd_lines)

    if "run_benchmarks_priv_cmd" in cmd_without_comments and "{{" in cmd_without_comments:
        # If it uses the variable in actual code (not comment), it must not be the primary method
        pytest.fail(
            "sanity_check.yml privilege probe should not rely on run_benchmarks_priv_cmd "
            "which is defined later by setup.yml. The probe runs BEFORE setup.yml in the "
            "playbook workflow, so it must detect sudo/doas inline to work on OpenBSD."
        )

    # The command should check for both sudo and doas
    has_sudo_check = "sudo" in cmd
    has_doas_check = "doas" in cmd

    assert has_sudo_check and has_doas_check, (
        "Privilege probe should check for sudo or doas availability"
    )


def test_setup_yml_gcc_probes_use_resolved_command(worktree_root):
    """Test that all GCC-related probes in setup.yml use resolved command variable."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    # Find lines that should use resolved GCC command but might hardcode gcc
    problematic_patterns = [
        r"command -v gcc\s",  # command -v gcc (not in the resolution itself)
        r"\$\(gcc ",  # $(gcc with space after - command substitution
        r"\bgcc\s+-",  # gcc followed by space and dash (flags)
    ]

    issues = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Skip the resolution line itself
        if (
            "run_benchmarks_gcc_cmd_probe" in line
            or "command -v gcc 2>/dev/null || command -v cc" in line
        ):
            continue
        # Skip comments
        if line.strip().startswith("#"):
            continue
        # Skip lines that properly use the variable
        if "run_benchmarks_gcc_cmd" in line:
            continue

        # Check for problematic patterns
        import re

        for pattern in problematic_patterns:
            if re.search(pattern, line):
                issues.append(f"Line {i}: {line.strip()}")
                break

    # We specifically check for hardcoded gcc in these contexts:
    # - distro build flag fallback detection
    # - march=native expansion
    # - configured-with parsing
    critical_hardcoded = []
    for issue in issues:
        if any(
            keyword in issue.lower() for keyword in ["dumpspecs", "march=native", "configured with"]
        ):
            critical_hardcoded.append(issue)

    if critical_hardcoded:
        pytest.fail(
            f"setup.yml should use {{{{ run_benchmarks_gcc_cmd }}}} for GCC probes, "
            f"not hardcoded 'gcc'. Found {len(critical_hardcoded)} issue(s):\n"
            + "\n".join(critical_hardcoded[:5])
        )


def test_setup_yml_privilege_probes_use_inline_detection(worktree_root):
    """
    Test that privilege-sensitive probes in setup.yml do not hardcode sudo.

    Task 2 resolves privilege-escalation commands explicitly. Any setup probe that
    still hardcodes ``sudo -n`` bypasses that resolution and can drift back toward
    Linux-only assumptions.
    """
    setup_yml = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_yml, encoding="utf-8") as file:
        content = file.read()

    # Check the dmidecode task specifically
    # It should either:
    # 1. Use inline sudo||doas detection
    # 2. Or be conditional on ansible_system == 'Linux' (where sudo is standard)
    #    AND be documented as Linux-only

    # Look for hardcoded sudo in privilege-requiring commands (dmidecode)
    # Pattern: detect 'sudo' that's not part of variable names or comments
    import re

    # Find the dmidecode task
    dmidecode_match = re.search(
        r"- name:.*dmidecode.*?\n(.*?)(?=\n- name:|\Z)", content, re.DOTALL | re.IGNORECASE
    )

    if not dmidecode_match:
        pytest.skip("dmidecode task not found in setup.yml")

    dmidecode_block = dmidecode_match.group(0)

    # Check for hardcoded sudo (not in a variable reference or inline detection)
    has_hardcoded_sudo = bool(re.search(r"\bsudo\s+-n\s+dmidecode", dmidecode_block))

    if has_hardcoded_sudo:
        pytest.fail(
            "dmidecode task in setup.yml should not hardcode 'sudo -n'. "
            "It should use the resolved privilege command or equivalent "
            "non-interactive privilege handling."
        )


def test_sanity_check_yml_doas_probe_explicit_noninteractive(worktree_root):
    """
    Test that doas pre-flight check in sanity_check.yml is explicitly non-interactive.

    Background: The privilege probe checks both sudo and doas. The sudo branch uses
    'sudo -n true' where -n means non-interactive/passwordless. The doas branch
    should be similarly explicit that it's testing passwordless access.
    """
    sanity_check_yml = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )

    with open(sanity_check_yml, encoding="utf-8") as file:
        content = file.read()

    import re

    # Find the privilege probe task
    priv_probe_match = re.search(
        r"- name:.*[Pp]rivilege.*(?:escalation|sudo).*?\n(.*?)(?=\n- name:|\Z)", content, re.DOTALL
    )

    if not priv_probe_match:
        pytest.fail("Privilege probe task not found in sanity_check.yml")

    priv_probe_block = priv_probe_match.group(0)

    # Look for the doas branch
    doas_branch_match = re.search(
        r"elif command -v doas.*?then\s+(.*?)(?:else|fi)", priv_probe_block, re.DOTALL
    )

    if not doas_branch_match:
        pytest.skip("doas branch not found in privilege probe")

    doas_command = doas_branch_match.group(1).strip()

    assert "doas -n true" in doas_command, (
        "doas branch in sanity_check.yml should use 'doas -n true' so the "
        "passwordless probe is explicitly non-interactive."
    )
