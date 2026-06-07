"""Policy checks for tox-ansible matrix compatibility."""

from __future__ import annotations

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def _read_skip_entries() -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(REPO_ROOT / "tox-ansible.ini")
    raw = parser.get("ansible", "skip")
    return {line.strip() for line in raw.splitlines() if line.strip()}


def test_tox_skip_list_blocks_unsupported_python_ansible_pairs() -> None:
    """Skip list should encode unsupported pairs from current Ansible support windows."""
    skip_entries = _read_skip_entries()

    expected = {
        "py3.12-devel",
        "py3.11-devel",
        "py3.10-devel",
        "py3.14-devel",
        "py3.14-milestone",
        "py3.11-milestone",
        "py3.10-milestone",
    }

    assert expected.issubset(skip_entries)
