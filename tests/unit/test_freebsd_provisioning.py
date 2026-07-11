"""Tests for FreeBSD benchmark provisioning backend selection."""

import os

import pytest
import yaml


@pytest.fixture
def worktree_root():
    """Return the worktree root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_freebsd_backend_defaults_exist(worktree_root):
    """FreeBSD backend selection defaults should be present."""
    defaults_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "defaults", "main.yml"
    )
    with open(defaults_path, encoding="utf-8") as file_handle:
        defaults = yaml.safe_load(file_handle)

    assert defaults["provision_benchmarks_freebsd_backend"] in ["ports", "poudriere", "auto"]
    assert defaults["provision_benchmarks_freebsd_poudriere_jail"] != ""
    assert defaults["provision_benchmarks_freebsd_poudriere_ports_tree"] != ""
    assert defaults["provision_benchmarks_freebsd_poudriere_set"] != ""


def test_freebsd_task_file_supports_backend_auto_detection(worktree_root):
    """FreeBSD task file should resolve backend and auto-fallback."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "freebsd.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "provision_benchmarks_freebsd_backend" in task_content
    assert "Set effective FreeBSD provisioning backend" in task_content
    assert "auto" in task_content


def test_freebsd_task_file_includes_ports_and_poudriere_paths(worktree_root):
    """FreeBSD task file should branch between ports and poudriere backends."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "freebsd.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "Include FreeBSD ports provisioning tasks" in task_content
    assert "Include FreeBSD poudriere provisioning tasks" in task_content


def test_freebsd_poudriere_task_has_preflight_and_bulk_checks(worktree_root):
    """Poudriere provisioning should validate setup and run dry-run bulk first."""
    task_path = os.path.join(
        worktree_root, "roles", "provision_benchmarks", "tasks", "os", "freebsd_poudriere.yml"
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "Validate poudriere repository configuration for selected set" in task_content
    assert "poudriere bulk -n" in task_content
    assert "Build benchmark dependency set with poudriere" in task_content


def test_freebsd_capability_verification_is_present(worktree_root):
    """FreeBSD provisioning should verify benchmark-critical capabilities."""
    task_path = os.path.join(
        worktree_root,
        "roles",
        "provision_benchmarks",
        "tasks",
        "verify_freebsd_capabilities.yml",
    )
    with open(task_path, encoding="utf-8") as file_handle:
        task_content = file_handle.read()

    assert "Verify FFmpeg has H.264 codec support (FreeBSD)" in task_content
    assert "Verify FFmpeg has H.265/HEVC codec support (FreeBSD)" in task_content
    assert "Verify NumPy import works (FreeBSD)" in task_content
