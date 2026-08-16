"""Tests for benchmark setup task file behavior."""

from __future__ import annotations

import os


def test_setup_task_recreates_work_dir_with_privilege() -> None:
    task_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "roles",
        "run_benchmarks",
        "tasks",
        "setup.yml",
    )

    with open(task_file, encoding="utf-8") as file_handle:
        content = file_handle.read()

    assert "- name: Create benchmark working directory" in content
    assert "owner: \"{{ ansible_user | default(lookup('env', 'USER')) }}\"" in content
    assert 'group: "{{ ansible_user_gid | default(omit) }}"' in content
    assert "become: true" in content
