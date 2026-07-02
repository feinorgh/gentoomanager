"""Tests for OpenIndiana benchmark runtime support boundaries."""

import os

import pytest


@pytest.fixture
def worktree_root():
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(path):
    with open(path, encoding="utf-8") as file_handle:
        return file_handle.read()


def test_disk_yml_gates_openindiana_explicitly(worktree_root):
    """Disk benchmark should be explicitly gated on SunOS/OpenIndiana."""
    disk_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "disk.yml")
    content = _read(disk_path)

    assert "Skip disk benchmark on OpenBSD/OpenIndiana" in content
    assert "ansible_system | default('Linux') in ['OpenBSD', 'SunOS']" in content


def test_boot_time_yml_has_openindiana_unsupported_marker(worktree_root):
    """Boot-time benchmark should write unsupported artifact for OpenIndiana."""
    boot_path = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "boot_time.yml")
    content = _read(boot_path)

    assert "Write boot_times unsupported result for OpenBSD/OpenIndiana" in content
    assert "ansible_system | default('Linux') in ['OpenBSD', 'SunOS']" in content


def test_sanity_check_writes_openindiana_skip_artifact(worktree_root):
    """Sanity-check should set OpenIndiana skip reasons before artifact write."""
    sanity_path = os.path.join(
        worktree_root, "roles", "run_benchmarks", "tasks", "sanity_check.yml"
    )
    content = _read(sanity_path)

    assert "Set OpenIndiana tier 3 category skip reasons (disk)" in content
    assert "when: ansible_system | default('Linux') == 'SunOS'" in content
    assert "Write OpenBSD/OpenIndiana disk skip artifact" in content


def test_skip_complete_logic_excludes_openindiana_unsupported_categories(worktree_root):
    """Completeness logic should exclude OpenIndiana unsupported categories."""
    role_main = os.path.join(worktree_root, "roles", "run_benchmarks", "tasks", "main.yml")
    playbook = os.path.join(worktree_root, "playbooks", "run_benchmarks.yml")

    role_content = _read(role_main)
    playbook_content = _read(playbook)
    unsupported_check = (
        "{%- if cat in unsupported_on_openbsd or cat in unsupported_on_openindiana -%}"
    )

    assert "{%- set unsupported_on_openindiana = ['disk', 'boot_time'] -%}" in role_content
    assert unsupported_check in role_content
    assert "{%- set unsupported_on_openindiana = ['disk', 'boot_time'] -%}" in playbook_content
    assert unsupported_check in playbook_content
