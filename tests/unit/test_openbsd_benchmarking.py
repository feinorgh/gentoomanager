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
    assert "cc" in cmd, "verify.yml should treat cc as an acceptable compiler on OpenBSD"

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

    bash_resolve_task = None
    for task in setup_tasks:
        task_name = task.get("name", "").lower()
        if "bash executable" in task_name:
            bash_resolve_task = task
            break

    assert bash_resolve_task is not None, "setup.yml should detect a runtime bash executable"
    bash_probe = bash_resolve_task.get("ansible.builtin.raw", "")
    assert "command -v bash" in bash_probe, "setup.yml should probe PATH for bash first"
    assert "/usr/local/bin/bash" in bash_probe, (
        "setup.yml should fall back to /usr/local/bin/bash for OpenBSD runtime support"
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


# ========================================================================
# Task 3: OpenBSD setup metadata and safe-subset normalization tests
# ========================================================================


def test_setup_yml_openbsd_metadata_branch(worktree_root):
    """Test that setup.yml has an OpenBSD metadata gathering branch."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        setup_tasks = yaml.safe_load(content)

    # Check for OpenBSD CPU max clock speed collection via sysctl -n hw.cpuspeed
    cpu_freq_openbsd_task = None
    for task in setup_tasks:
        task_name = task.get("name", "").lower()
        if (
            "openbsd" in task_name
            and "cpu" in task_name
            and ("clock" in task_name or "freq" in task_name)
        ):
            cpu_freq_openbsd_task = task
            break

    assert cpu_freq_openbsd_task is not None, (
        "setup.yml should have an OpenBSD CPU max clock speed gathering task"
    )

    # Verify it uses sysctl -n hw.cpuspeed
    cmd_module = None
    if "ansible.builtin.command" in cpu_freq_openbsd_task:
        cmd_module = cpu_freq_openbsd_task["ansible.builtin.command"]
    elif "ansible.builtin.shell" in cpu_freq_openbsd_task:
        cmd_module = cpu_freq_openbsd_task["ansible.builtin.shell"]

    assert cmd_module is not None, "OpenBSD CPU freq task should use command or shell module"

    cmd = cmd_module.get("cmd", "")
    assert "sysctl" in cmd and "hw.cpuspeed" in cmd, (
        "OpenBSD CPU freq task should use 'sysctl -n hw.cpuspeed'"
    )

    # Verify the task is conditional on ansible_system == 'OpenBSD'
    when_clause = cpu_freq_openbsd_task.get("when", "")
    assert "OpenBSD" in str(when_clause), (
        "OpenBSD CPU freq task should be conditional on ansible_system == 'OpenBSD'"
    )


def test_setup_yml_openbsd_normalization_capability_fact(worktree_root):
    """Test that setup.yml defines run_benchmarks_openbsd_safe_normalization fact."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    # Check for OpenBSD safe normalization capability fact
    assert "run_benchmarks_openbsd_safe_normalization" in content, (
        "setup.yml should define run_benchmarks_openbsd_safe_normalization fact "
        "to indicate safe OpenBSD normalization support"
    )

    # Verify it's set in a set_fact task
    setup_tasks = yaml.safe_load(content)
    openbsd_fact_task = None
    for task in setup_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_openbsd_safe_normalization" in facts:
                openbsd_fact_task = task
                break

    assert openbsd_fact_task is not None, (
        "setup.yml should have a set_fact task that defines "
        "run_benchmarks_openbsd_safe_normalization"
    )


def test_setup_yml_category_prepare_cmd_fact(worktree_root):
    """Test that setup.yml defines run_benchmarks_category_prepare_cmd fact."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    # Check for category prepare command fact
    assert "run_benchmarks_category_prepare_cmd" in content, (
        "setup.yml should define run_benchmarks_category_prepare_cmd fact "
        "for OS-specific per-category preparation commands"
    )

    # Verify it's set in a set_fact task
    setup_tasks = yaml.safe_load(content)
    prepare_cmd_fact_task = None
    for task in setup_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_category_prepare_cmd" in facts:
                prepare_cmd_fact_task = task
                break

    assert prepare_cmd_fact_task is not None, (
        "setup.yml should have a set_fact task that defines run_benchmarks_category_prepare_cmd"
    )


def test_setup_yml_metadata_cpu_frequency_includes_openbsd(worktree_root):
    """Test that metadata shaping uses OpenBSD CPU freq when on OpenBSD."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    # Find the metadata parsing task
    setup_tasks = yaml.safe_load(content)
    metadata_task = None
    for task in setup_tasks:
        if task.get("name") == "Parse host metadata":
            metadata_task = task
            break

    assert metadata_task is not None, "Parse host metadata task not found"

    # Check that cpu_mhz includes OpenBSD branch
    metadata_dict = metadata_task.get("ansible.builtin.set_fact", {}).get(
        "run_benchmarks_metadata", {}
    )
    cpu_mhz_expr = str(metadata_dict.get("cpu_mhz", ""))

    assert "OpenBSD" in cpu_mhz_expr, (
        "metadata cpu_mhz should include OpenBSD-specific branch for hw.cpuspeed"
    )


def test_normalize_yml_openbsd_safe_subset_branch(worktree_root):
    """Test that normalize.yml has an OpenBSD safe-subset normalization branch."""
    normalize_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "normalize.yml"
    )
    with open(normalize_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        normalize_tasks = yaml.safe_load(content)

    # Look for OpenBSD sync task (safe subset: sync only, no Linux/FreeBSD-only tuning)
    openbsd_sync_task = None
    for task in normalize_tasks:
        task_name = task.get("name", "").lower()
        when_clause = str(task.get("when", ""))
        if "sync" in task_name and "OpenBSD" in when_clause:
            openbsd_sync_task = task
            break

    assert openbsd_sync_task is not None, (
        "normalize.yml should have an OpenBSD-specific sync task (safe subset)"
    )

    # Verify it's conditional on ansible_system == 'OpenBSD'
    when_clause = str(openbsd_sync_task.get("when", ""))
    assert "OpenBSD" in when_clause, (
        "OpenBSD sync task should be conditional on ansible_system == 'OpenBSD'"
    )

    # Verify it's a simple sync command
    cmd_module = None
    if "ansible.builtin.command" in openbsd_sync_task:
        cmd_module = openbsd_sync_task["ansible.builtin.command"]
    elif "ansible.builtin.shell" in openbsd_sync_task:
        cmd_module = openbsd_sync_task["ansible.builtin.shell"]

    assert cmd_module is not None, "OpenBSD sync task should use command or shell module"

    cmd = cmd_module.get("cmd", "")
    assert "sync" in cmd, "OpenBSD normalization should sync filesystems"


def test_denormalize_yml_openbsd_safe_subset_branch(worktree_root):
    """Test that denormalize.yml has an OpenBSD safe-subset branch (no-op restore marker)."""
    denormalize_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "denormalize.yml"
    )
    with open(denormalize_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        denormalize_tasks = yaml.safe_load(content)

    # Look for OpenBSD restore marker (no-op since we don't change anything risky)
    openbsd_restore_task = None
    for task in denormalize_tasks:
        task_name = task.get("name", "").lower()
        when_clause = str(task.get("when", ""))
        if "openbsd" in task_name and "OpenBSD" in when_clause:
            openbsd_restore_task = task
            break

    assert openbsd_restore_task is not None, (
        "denormalize.yml should have an OpenBSD restore marker task (safe subset, likely no-op)"
    )

    # Verify it's conditional on ansible_system == 'OpenBSD'
    when_clause = str(openbsd_restore_task.get("when", ""))
    assert "OpenBSD" in when_clause, (
        "OpenBSD restore task should be conditional on ansible_system == 'OpenBSD'"
    )


def test_setup_yml_category_prepare_cmd_only_linux_openbsd(worktree_root):
    """Test that category_prepare_cmd is ONLY set for Linux and OpenBSD, not other platforms."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        setup_tasks = yaml.safe_load(content)

    # Find the task that sets run_benchmarks_category_prepare_cmd
    prepare_cmd_task = None
    for task in setup_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_category_prepare_cmd" in facts:
                prepare_cmd_task = task
                break

    assert prepare_cmd_task is not None, (
        "setup.yml should define run_benchmarks_category_prepare_cmd"
    )

    # The task should be conditional on Linux or OpenBSD ONLY
    # It should NOT set the variable for FreeBSD or other platforms
    when_clause = str(prepare_cmd_task.get("when", ""))

    assert "in ['Linux', 'OpenBSD']" in when_clause, (
        "run_benchmarks_category_prepare_cmd should only be set for Linux and OpenBSD"
    )
    assert "FreeBSD" not in when_clause, (
        "run_benchmarks_category_prepare_cmd should not be set for FreeBSD"
    )


def test_setup_yml_category_prepare_cmd_linux_has_cache_drop(worktree_root):
    """Test that Linux category_prepare_cmd includes cache drop (preserve existing behavior)."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        setup_tasks = yaml.safe_load(content)

    prepare_cmd_task = None
    for task in setup_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_category_prepare_cmd" in facts:
                prepare_cmd_task = task
                break

    assert prepare_cmd_task is not None, (
        "setup.yml should define run_benchmarks_category_prepare_cmd"
    )

    prepare_cmd_template = prepare_cmd_task["ansible.builtin.set_fact"][
        "run_benchmarks_category_prepare_cmd"
    ]
    linux_section = prepare_cmd_template.split("== 'Linux'", 1)[1].split("elif", 1)[0]

    assert "drop_caches" in linux_section, (
        "Linux category_prepare_cmd should include cache drop command "
        "(preserve existing Linux per-category prep behavior)"
    )


def test_setup_yml_category_prepare_cmd_openbsd_sync_only(worktree_root):
    """Test that OpenBSD category_prepare_cmd is sync only (safe subset)."""
    setup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "setup.yml")
    with open(setup_path, encoding="utf-8") as file_handle:
        content = file_handle.read()

    setup_tasks = yaml.safe_load(content)

    prepare_cmd_task = None
    for task in setup_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_category_prepare_cmd" in facts:
                prepare_cmd_task = task
                break

    assert prepare_cmd_task is not None, (
        "setup.yml should define run_benchmarks_category_prepare_cmd"
    )

    prepare_cmd_template = prepare_cmd_task["ansible.builtin.set_fact"][
        "run_benchmarks_category_prepare_cmd"
    ]
    assert "OpenBSD" in prepare_cmd_template and "sync" in prepare_cmd_template, (
        "OpenBSD category_prepare_cmd should include a sync-only branch"
    )

    openbsd_section = prepare_cmd_template.split("OpenBSD", 1)[1]
    assert "drop_caches" not in openbsd_section.lower(), (
        "OpenBSD category_prepare_cmd should NOT include cache drop (safe subset)"
    )


def test_run_category_yml_prep_guard_matches_setup_intent(worktree_root):
    """Test that run_category.yml prep task guard aligns with setup.yml variable setting."""
    run_category_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "run_category.yml"
    )
    with open(run_category_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        run_category_tasks = yaml.safe_load(content)

    # Find the system state preparation task
    prep_task = None
    for task in run_category_tasks:
        task_name = task.get("name", "").lower()
        if "prepare" in task_name or "state" in task_name:
            # Check if it uses run_benchmarks_category_prepare_cmd
            task_str = str(task)
            if "run_benchmarks_category_prepare_cmd" in task_str:
                prep_task = task
                break

    assert prep_task is not None, (
        "run_category.yml should have a preparation task using run_benchmarks_category_prepare_cmd"
    )

    # The guard should ensure it only runs when the variable is defined
    # This is correct - the key is that setup.yml should only define it for Linux/OpenBSD
    when_clause = str(prep_task.get("when", ""))
    assert "run_benchmarks_category_prepare_cmd is defined" in when_clause, (
        "Preparation task should guard with 'run_benchmarks_category_prepare_cmd is defined'"
    )


# ========================================================================
# Task 4: Gate unsupported categories and preserve skip reasons
# ========================================================================


def test_disk_yml_gates_openbsd_explicitly(worktree_root):
    """Test that disk category skip reason is available before disk.yml runs.

    Critical timing check: sanity_check.yml runs BEFORE category task files in
    the playbook flow, so the disk skip reason must be set earlier (e.g., in
    sanity_check.yml itself when detecting OpenBSD) to be captured in
    benchmark_notes.json. This test ensures the skip reason is NOT set late in
    disk.yml where it would miss the notes write.
    """
    disk_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "disk.yml")
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )

    with open(disk_path, encoding="utf-8") as file_handle:
        disk_content = file_handle.read()
        disk_tasks = yaml.safe_load(disk_content)

    with open(sanity_path, encoding="utf-8") as file_handle:
        sanity_content = file_handle.read()
        sanity_tasks = yaml.safe_load(sanity_content)

    # The disk skip reason must be set BEFORE sanity_check writes benchmark_notes.json
    # Since sanity_check runs before disk.yml, the skip reason must be in sanity_check.yml

    # Find where benchmark_notes.json is written in sanity_check.yml
    notes_write_task = None
    notes_task_index = None
    for idx, task in enumerate(sanity_tasks):
        if "ansible.builtin.copy" in task:
            copy_module = task["ansible.builtin.copy"]
            if "benchmark_notes.json" in str(copy_module.get("dest", "")):
                notes_write_task = task
                notes_task_index = idx
                break

    assert notes_write_task is not None, "sanity_check.yml should write benchmark_notes.json"

    # Find where disk skip reason is set in sanity_check.yml (must be BEFORE notes write)
    disk_skip_set_task = None
    disk_skip_task_index = None
    for idx, task in enumerate(sanity_tasks):
        if idx < notes_task_index and "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_disk_skip_reason" in facts:
                disk_skip_set_task = task
                disk_skip_task_index = idx
                break

    assert disk_skip_set_task is not None, (
        "sanity_check.yml must set run_benchmarks_disk_skip_reason BEFORE writing "
        "benchmark_notes.json (playbook runs sanity_check.yml before disk.yml)"
    )

    assert disk_skip_task_index < notes_task_index, (
        f"Disk skip reason must be set (task {disk_skip_task_index}) BEFORE "
        f"benchmark_notes.json is written (task {notes_task_index})"
    )

    # The skip reason should be conditional on OpenBSD
    when_clause = str(disk_skip_set_task.get("when", ""))
    assert "OpenBSD" in when_clause, "Disk skip reason setting should be conditional on OpenBSD"

    # Verify the reason is descriptive
    facts = disk_skip_set_task["ansible.builtin.set_fact"]
    skip_reason = str(facts["run_benchmarks_disk_skip_reason"])
    assert len(skip_reason) > 10, "Disk skip reason should be a descriptive message"

    # disk.yml should NOT set run_benchmarks_disk_skip_reason (would be too late)
    disk_sets_skip_reason = False
    for task in disk_tasks:
        if "ansible.builtin.set_fact" in task:
            facts = task["ansible.builtin.set_fact"]
            if "run_benchmarks_disk_skip_reason" in facts:
                disk_sets_skip_reason = True
                break

    assert not disk_sets_skip_reason, (
        "disk.yml should NOT set run_benchmarks_disk_skip_reason (too late in playbook "
        "flow - sanity_check.yml already wrote benchmark_notes.json)"
    )


def test_boot_time_yml_openbsd_unsupported_policy(worktree_root):
    """Test that boot_time.yml short-circuits OpenBSD before probing.

    Critical path check: OpenBSD should take the explicit unsupported path
    BEFORE systemd-analyze/dmesg probing runs. The unsupported result write
    must come first and the probe tasks must have when guards to skip OpenBSD.
    """
    boot_time_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "boot_time.yml"
    )
    with open(boot_time_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        boot_time_tasks = yaml.safe_load(content)

    # Find the OpenBSD unsupported result writing task
    openbsd_unsupported_task = None
    openbsd_task_index = None
    for idx, task in enumerate(boot_time_tasks):
        task_name = task.get("name", "").lower()
        when_clause = str(task.get("when", ""))
        if (
            "openbsd" in task_name
            and ("unsupported" in task_name or "write" in task_name)
            and "OpenBSD" in when_clause
        ):
            openbsd_unsupported_task = task
            openbsd_task_index = idx
            break

    assert openbsd_unsupported_task is not None, (
        "boot_time.yml should have an OpenBSD unsupported result writing task"
    )

    # The task should write boot_times.json with method='unsupported'
    assert "ansible.builtin.copy" in openbsd_unsupported_task, (
        "OpenBSD unsupported task should use ansible.builtin.copy"
    )

    copy_module = openbsd_unsupported_task["ansible.builtin.copy"]
    assert "boot_times.json" in str(copy_module.get("dest", "")), (
        "OpenBSD unsupported task should write to boot_times.json"
    )

    # Check content structure
    content_str = str(copy_module.get("content", ""))
    assert "unsupported" in content_str.lower(), (
        "OpenBSD boot result should indicate method=unsupported"
    )
    assert "error" in content_str.lower(), (
        "OpenBSD boot result should include an error/reason message"
    )

    # CRITICAL: The OpenBSD task must come BEFORE the systemd-analyze check
    # Find the systemd-analyze check task
    systemd_check_task_index = None
    for idx, task in enumerate(boot_time_tasks):
        task_name = task.get("name", "").lower()
        if "systemd-analyze" in task_name and "check" in task_name:
            systemd_check_task_index = idx
            break

    assert systemd_check_task_index is not None, (
        "boot_time.yml should have a systemd-analyze check task"
    )

    assert openbsd_task_index < systemd_check_task_index, (
        f"OpenBSD unsupported task (index {openbsd_task_index}) must come BEFORE "
        f"systemd-analyze check (index {systemd_check_task_index}) to short-circuit probe"
    )

    # The systemd-analyze check and subsequent probe tasks must exclude OpenBSD
    systemd_check_task = boot_time_tasks[systemd_check_task_index]
    systemd_when = str(systemd_check_task.get("when", ""))

    # Should explicitly exclude OpenBSD or be Linux-only
    assert "!= 'OpenBSD'" in systemd_when or "== 'Linux'" in systemd_when, (
        "systemd-analyze check should exclude OpenBSD (use != 'OpenBSD' or == 'Linux')"
    )

    # All later probe tasks must still exclude OpenBSD explicitly.
    for idx in range(systemd_check_task_index, len(boot_time_tasks)):
        task = boot_time_tasks[idx]
        task_name = task.get("name", "").lower()

        # If it's a systemd or dmesg related task, it must exclude OpenBSD
        if "systemd" in task_name or "dmesg" in task_name or "boot" in task_name:
            when_clause = str(task.get("when", ""))
            if "OpenBSD" not in when_clause:
                # This probe task might run on OpenBSD - that's wrong
                pytest.fail(
                    f"Probe task '{task.get('name', '')}' at index {idx} may run on OpenBSD. "
                    f"All probe tasks after systemd-analyze check should exclude OpenBSD or "
                    f"the OpenBSD unsupported task should come first."
                )


def test_sanity_check_yml_preserves_openbsd_skip_reasons(worktree_root):
    """Test that sanity_check.yml preserves OpenBSD category skip reasons in notes."""
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )
    with open(sanity_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
        sanity_tasks = yaml.safe_load(content)

    # Find the task that writes benchmark_notes.json
    notes_task = None
    for task in sanity_tasks:
        if "ansible.builtin.copy" in task:
            copy_module = task["ansible.builtin.copy"]
            if "benchmark_notes.json" in str(copy_module.get("dest", "")):
                notes_task = task
                break

    assert notes_task is not None, "sanity_check.yml should write benchmark_notes.json"

    # Check that the notes structure includes category skip reasons
    # Look at the vars section to see what's being captured
    vars_section = notes_task.get("vars", {})
    notes_structure = vars_section.get("_notes", {})

    # The notes should preserve category-level skip information
    assert "category_skip_reasons" in notes_structure, (
        "benchmark_notes.json should have a category_skip_reasons section"
    )

    # The disk skip reason should be captured
    category_skip_reasons = notes_structure.get("category_skip_reasons", {})
    assert "disk" in category_skip_reasons, "category_skip_reasons should include disk skip reason"
    assert "normalization_notes" in notes_structure, (
        "benchmark_notes.json should record reduced normalization details"
    )
    assert "platform_notes" in notes_structure, (
        "benchmark_notes.json should record platform-specific preflight limitations"
    )


def test_runtime_category_tasks_use_resolved_command_facts(worktree_root):
    """Task 2 resolution facts must be used by the actual benchmark category tasks."""
    file_expectations = {
        "python.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "cmd: python3 --version",
                "python3 - << 'PYEOF'",
            ],
        },
        "bash.yml": {
            "must_contain": ["_run_benchmarks_bash"],
            "must_not_contain": [
                "bash --version",
                '"startup-bare" "bash --norc --noprofile -c true"',
                '"bash --norc --noprofile $BENCH/${bench}.sh"',
                "$(seq 1 3000)",
            ],
        },
        "numeric.yml": {
            "must_contain": ["run_benchmarks_gcc_cmd", "run_benchmarks_python_cmd"],
            "must_not_contain": [
                "cmd: gcc --version",
                'cmd: python3 -c "import numpy"',
                '"python3 -c \\"import numpy',
            ],
        },
        "process.yml": {
            "must_contain": ["run_benchmarks_gcc_cmd", "run_benchmarks_python_cmd"],
            "must_not_contain": [
                "cmd: gcc --version",
                "\"python3 -c 'import os, sys, json, re, hashlib",
            ],
        },
        "disk.yml": {
            "must_contain": ["run_benchmarks_priv_cmd"],
            "must_not_contain": [
                "sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches'",
            ],
        },
        "memory.yml": {
            "must_contain": ["run_benchmarks_gcc_cmd"],
            "must_not_contain": [
                "cmd: gcc --version",
                "gcc -O2",
            ],
        },
        "compiler.yml": {
            "must_contain": ["run_benchmarks_python_cmd", "run_benchmarks_gcc_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
                "label == 'cc'",
            ],
        },
        "coreutils.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
            ],
        },
        "crypto.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
            ],
        },
        "linker.yml": {
            "must_contain": ["run_benchmarks_gcc_cmd", "run_benchmarks_python_cmd"],
            "must_not_contain": [
                "cmd: gcc --version",
                "python3 - <<'PYEOF'",
                '[ -f "$obj" ] || gcc -O2 -c -o "$obj" "$src"',
                '"gcc -fuse-ld=bfd -o /dev/null $OBJS -lm 2>/dev/null"',
            ],
        },
        "sqlite.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
                '"python3 -c \\"import sqlite3,random;',
            ],
        },
        "startup.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "command -v python3",
                '"python3 -c pass"',
            ],
        },
        "boot_time.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
            ],
        },
        "inkscape.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                "python3 - << 'PYEOF'",
            ],
        },
        "opencv.yml": {
            "must_contain": ["run_benchmarks_python_cmd"],
            "must_not_contain": [
                'cmd: python3 -c "import cv2"',
                "'python3 opencv_bench.py resize'",
                "'python3 opencv_bench.py kodak_load ./kodak'",
            ],
        },
    }

    tasks_dir = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks")
    for file_name, rules in file_expectations.items():
        path = os.path.join(tasks_dir, file_name)
        with open(path, encoding="utf-8") as file_handle:
            content = file_handle.read()

        for needle in rules["must_contain"]:
            assert needle in content, f"{file_name} should use {needle}"

        for needle in rules["must_not_contain"]:
            assert needle not in content, f"{file_name} should not hardcode {needle!r}"


def test_openbsd_support_avoids_undeclared_helper_commands(worktree_root):
    """OpenBSD paths should not depend on undeclared seq/timeout helper behavior."""
    normalize_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "normalize.yml"
    )
    with open(normalize_path, encoding="utf-8") as file_handle:
        normalize_content = file_handle.read()

    assert "$(seq" not in normalize_content, (
        "normalize.yml should avoid seq so OpenBSD does not depend on an undeclared helper"
    )

    startup_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "startup.yml")
    with open(startup_path, encoding="utf-8") as file_handle:
        startup_content = file_handle.read()

    assert "command -v timeout" in startup_content, (
        "startup.yml should gate the Firefox timeout sub-benchmark on timeout availability"
    )


def test_openbsd_completion_logic_matches_supported_openbsd_artifacts(worktree_root):
    """OpenBSD completion logic should expect the artifact set OpenBSD can honestly produce."""
    role_main_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "main.yml")
    with open(role_main_path, encoding="utf-8") as file_handle:
        role_main = file_handle.read()

    playbook_path = os.path.join(worktree_root, "playbooks", "run_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook = file_handle.read()

    assert "run_benchmarks_preflight_system" in playbook, (
        "run_benchmarks.yml should detect a dedicated OS name for skip_complete gating"
    )

    for file_name, content in {"main.yml": role_main, "run_benchmarks.yml": playbook}.items():
        assert "OpenBSD" in content and "'disk'" in content, (
            f"{file_name} should special-case OpenBSD disk gating in completion logic"
        )
        assert "unsupported_on_openbsd" in content or "cat == 'disk'" in content, (
            f"{file_name} should explicitly treat OpenBSD disk as an intentional skip"
        )
        assert "memory_latency.json" in content, (
            f"{file_name} should use the OpenBSD-safe memory artifact in completion logic"
        )
        assert "disk_skip.json" in content, (
            f"{file_name} should require a dedicated OpenBSD disk skip artifact for completion"
        )


def test_openbsd_support_is_documented(worktree_root):
    """Test that OpenBSD support is documented in user-facing docs and playbook."""
    # Test 1: README.md should mention OpenBSD as a supported platform
    readme_path = os.path.join(worktree_root, "roles", "run_benchmarks", "README.md")
    with open(readme_path, encoding="utf-8") as file_handle:
        readme_content = file_handle.read()

    assert "OpenBSD" in readme_content, (
        "roles/run_benchmarks/README.md should mention OpenBSD as a supported platform"
    )
    assert "memory latency" in readme_content.lower(), (
        "roles/run_benchmarks/README.md should explain the OpenBSD memory category behavior"
    )
    # Check that reduced normalization is mentioned
    assert "sync" in readme_content.lower() or "normalization" in readme_content.lower(), (
        "roles/run_benchmarks/README.md should mention normalization behavior"
    )

    # README should NOT claim disk benchmarks require fio (they use dd, avoiding fio requirement)
    readme_lower = readme_content.lower()
    assert not ("disk" in readme_lower and "require fio" in readme_lower), (
        "roles/run_benchmarks/README.md should not claim disk benchmarks require fio "
        "(implementation uses dd without requiring fio per disk.yml comment)"
    )
    assert not ("disk" in readme_lower and "requires fio" in readme_lower), (
        "roles/run_benchmarks/README.md should not claim disk benchmarks require fio "
        "(implementation uses dd without requiring fio per disk.yml comment)"
    )

    # README should not overstate that all category skip reasons go to
    # benchmark_notes.json. Only disk goes there; boot-time writes to
    # boot_times.json.
    if "category skip reasons are recorded" in readme_lower and "benchmark_notes" in readme_lower:
        # This phrasing overstates where skip reasons go (plural without disk specificity)
        raise AssertionError(
            "roles/run_benchmarks/README.md should not claim all category skip reasons "
            "are recorded in benchmark_notes.json "
            "(only disk is; boot-time writes to boot_times.json)"
        )

    # Test 2: docs/benchmarks.md should document OpenBSD support and caveats
    benchmarks_doc_path = os.path.join(worktree_root, "docs", "benchmarks.md")
    with open(benchmarks_doc_path, encoding="utf-8") as file_handle:
        benchmarks_doc_content = file_handle.read()

    assert "OpenBSD" in benchmarks_doc_content, "docs/benchmarks.md should document OpenBSD support"
    assert "memory latency" in benchmarks_doc_content.lower(), (
        "docs/benchmarks.md should explain the OpenBSD memory category behavior"
    )

    # Check concrete facts about provisioning defaults (based on defaults/main.yml)
    # These packages ARE in the OpenBSD provisioning list
    assert "ffmpeg" in benchmarks_doc_content.lower(), (
        "docs/benchmarks.md should mention FFmpeg provisioning for OpenBSD"
    )
    assert "octave" in benchmarks_doc_content.lower(), (
        "docs/benchmarks.md should mention Octave for OpenBSD"
    )

    # Check that skip reasons are documented with accurate wording
    # The actual disk skip reason mentions "Tier 3" and verification requirements
    assert "tier 3" in benchmarks_doc_content.lower() or "Tier 3" in benchmarks_doc_content, (
        "docs/benchmarks.md should mention Tier 3 category classification for unsupported items"
    )

    # Docs should NOT overstate where skip reasons are recorded
    benchmarks_lower = benchmarks_doc_content.lower()
    # Find the "Category Skip Reasons" section
    skip_section_start = benchmarks_lower.find("category skip reasons")
    if skip_section_start > 0:
        # Get the next 300 chars after the section heading
        skip_section = benchmarks_lower[skip_section_start : skip_section_start + 300]
        # If it says skip reasons "are recorded in benchmark_notes.json" without
        # specifying which ones, that's an overstatement
        if "is recorded in" in skip_section or "are recorded in" in skip_section:
            if "benchmark_notes" in skip_section:
                # Check if it's specific about disk (OK) or general (overstates)
                assert "disk" in skip_section, (
                    "docs/benchmarks.md Category Skip Reasons section should be specific "
                    "that disk skip reason goes to benchmark_notes.json (boot-time writes to "
                    "boot_times.json, not benchmark_notes.json)"
                )

    # Test 3: playbooks/run_benchmarks.yml should mention OpenBSD in supported platforms
    playbook_path = os.path.join(worktree_root, "playbooks", "run_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook_content = file_handle.read()

    assert "OpenBSD" in playbook_content, (
        "playbooks/run_benchmarks.yml should mention OpenBSD in "
        "its supported platforms documentation"
    )
    # Check that the comment mentions reduced normalization
    assert "sync" in playbook_content.lower() or "normalization" in playbook_content.lower(), (
        "playbooks/run_benchmarks.yml should mention normalization behavior for OpenBSD"
    )

    # Playbook should NOT overstate where skip reasons are recorded
    playbook_lower = playbook_content.lower()
    if (
        "category skip reasons are recorded" in playbook_lower
        and "benchmark_notes" in playbook_lower
    ):
        # This phrasing overstates (plural without disk specificity)
        raise AssertionError(
            "playbooks/run_benchmarks.yml should not claim all category skip reasons "
            "are recorded in benchmark_notes.json "
            "(only disk is; boot-time writes to boot_times.json)"
        )

    # Test 4: Changelog should correctly attribute doas to run_benchmarks
    changelog_path = os.path.join(
        worktree_root, "changelogs", "fragments", "openbsd-benchmarking.yml"
    )
    with open(changelog_path, encoding="utf-8") as file_handle:
        changelog_content = file_handle.read()

    # doas auto-detection happens in run_benchmarks, not provision_benchmarks
    if "doas" in changelog_content.lower():
        # If doas is mentioned, it should be attributed to run_benchmarks
        doas_in_run_benchmarks = "roles/run_benchmarks" in changelog_content or (
            "run_benchmarks" in changelog_content
            and "provision_benchmarks" not in changelog_content
        )
        assert doas_in_run_benchmarks, (
            "Changelog should attribute doas auto-detection to roles/run_benchmarks, "
            "not roles/provision_benchmarks"
        )
