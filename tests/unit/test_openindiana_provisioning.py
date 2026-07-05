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


def test_openindiana_uses_ips_fmri_names_for_git_and_compiler(worktree_root):
    """OpenIndiana package list should use IPS FMRI names for core tools."""
    defaults_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "defaults", "main.yml"
    )
    with open(defaults_path, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    packages = defaults["provision_benchmarks_packages"]["OpenIndiana"]
    assert "developer/versioning/git" in packages
    assert "developer/gcc-14" in packages


def test_openindiana_maps_generic_unmatched_packages_to_ips_names(worktree_root):
    """OpenIndiana defaults should avoid generic names that IPS cannot resolve."""
    defaults_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "defaults", "main.yml"
    )
    with open(defaults_path, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    packages = defaults["provision_benchmarks_packages"]["OpenIndiana"]

    assert "runtime/python" in packages
    assert "text/gnu-diffutils" in packages
    assert "developer/golang" in packages
    assert "developer/lang/rustc" in packages
    assert "developer/clang-18" in packages

    assert "python3" not in packages
    assert "diffutils" not in packages
    assert "go" not in packages
    assert "rust" not in packages
    assert "clang" not in packages


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


def test_openindiana_task_attempts_hyperfine_install_via_cargo(worktree_root):
    """OpenIndiana provisioning should attempt hyperfine build when pkg lacks it."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "cargo install --locked hyperfine --root /usr" in task_content
    assert "developer/lang/rustc" in task_content


def test_openindiana_fallback_installs_individual_packages_on_nonzero_rc(worktree_root):
    """Partial fallback must trigger when pkg task returns rc != 0 under failed_when:false."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "provision_benchmarks_pkg_result.rc | default(0) != 0" in task_content


def test_openindiana_task_enables_hipster_encumbered_repo(worktree_root):
    """OpenIndiana provisioning should add hipster-encumbered package origin."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "pkg set-publisher" in task_content
    assert "hipster-encumbered" in task_content


def test_openindiana_uses_correct_hipster_encumbered_publisher_name(worktree_root):
    """Repository URL and publisher name must both be hipster-encumbered."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert (
        "pkg set-publisher -g https://pkg.openindiana.org/hipster-encumbered hipster-encumbered"
        in task_content
    )
    assert (
        "pkg set-publisher -g https://pkg.openindiana.org/hipster-encumbered openindiana.org"
        not in task_content
    )


def test_openindiana_warns_when_octave_install_fails(worktree_root):
    """OpenIndiana provisioning should emit explicit warning when octave is unavailable."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "register: provision_benchmarks_openindiana_octave_install" in task_content
    assert "Warn when Octave package is unavailable (OpenIndiana)" in task_content
    assert "provision_benchmarks_openindiana_octave_install.rc | default(0) != 0" in task_content


def test_openindiana_sets_openssl_mediator_to_latest_available(worktree_root):
    """OpenIndiana provisioning should select the newest available OpenSSL mediator."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "openindiana.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "pkg mediator -H openssl" in task_content
    assert "pkg mediator -a openssl" in task_content
    assert "pkg set-mediator -V" in task_content
    assert "provision_benchmarks_openindiana_openssl_latest_mediator_version.stdout | trim" in (
        task_content
    )


def test_benchmarks_doc_mentions_hipster_encumbered_repo_for_openindiana(worktree_root):
    """OpenIndiana docs should explain non-default encumbered repo usage."""
    docs_path = os.path.join(worktree_root, "docs", "benchmarks.md")
    with open(docs_path, encoding="utf-8") as file_handle:
        docs_content = file_handle.read()

    assert "hipster-encumbered" in docs_content
    assert "not enabled by default" in docs_content.lower()


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


def test_openindiana_play_sets_pfexec_compatible_become_vars(worktree_root):
    """Ensure OpenIndiana play config matches pfexec behavior on this platform."""
    playbook_path = os.path.join(worktree_root, "playbooks", "provision_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook_yaml = yaml.safe_load_all(file_handle.read())
        plays = []
        for item in playbook_yaml:
            if isinstance(item, list):
                plays.extend(item)
            else:
                plays.append(item)

    openindiana_play = None
    for play in plays:
        if isinstance(play, dict) and play.get("hosts") == "provision_os_openindiana":
            openindiana_play = play
            break

    assert openindiana_play is not None, "provision_os_openindiana play not found"

    play_vars = openindiana_play.get("vars", {})
    assert play_vars.get("ansible_become_method") == "pfexec"
    assert play_vars.get("ansible_pfexec_flags") == ""
    assert play_vars.get("ansible_pfexec_wrap_execution") is True


def test_gather_facts_play_sets_pfexec_plugin_overrides(worktree_root):
    """Ensure early gather_facts phase can execute when pfexec is selected on a host."""
    playbook_path = os.path.join(worktree_root, "playbooks", "provision_benchmarks.yml")
    with open(playbook_path, encoding="utf-8") as file_handle:
        playbook_yaml = yaml.safe_load_all(file_handle.read())
        plays = []
        for item in playbook_yaml:
            if isinstance(item, list):
                plays.extend(item)
            else:
                plays.append(item)

    gather_play = None
    for play in plays:
        if (
            isinstance(play, dict)
            and play.get("name") == "Gather facts and group hosts by OS family"
        ):
            gather_play = play
            break

    assert gather_play is not None, "Gather facts play not found"

    play_vars = gather_play.get("vars", {})
    assert play_vars.get("ansible_pfexec_flags") == ""
    assert play_vars.get("ansible_pfexec_wrap_execution") is True
