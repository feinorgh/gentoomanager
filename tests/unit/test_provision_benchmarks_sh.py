"""Tests for scripts/provision_benchmarks.sh preflight behavior."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SOURCE_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def wrapper_repo_copy(tmp_path: Path) -> Path:
    """Create a temporary repository copy for wrapper-script execution tests."""
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "playbooks").mkdir(parents=True)

    shutil.copy2(
        SOURCE_REPO_ROOT / "scripts" / "provision_benchmarks.sh",
        repo_root / "scripts" / "provision_benchmarks.sh",
    )
    shutil.copy2(
        SOURCE_REPO_ROOT / "playbooks" / "provision_benchmarks.yml",
        repo_root / "playbooks" / "provision_benchmarks.yml",
    )
    shutil.copy2(
        SOURCE_REPO_ROOT / "inventory_generator.py",
        repo_root / "inventory_generator.py",
    )

    script_path = repo_root / "scripts" / "provision_benchmarks.sh"
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    inventory_path = repo_root / "inventory_generator.py"
    inventory_path.chmod(
        inventory_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    )

    hypervisors_file = repo_root / "hypervisors.txt"
    if hypervisors_file.exists():
        hypervisors_file.unlink()

    return repo_root


@pytest.fixture()
def mock_bin(tmp_path: Path) -> tuple[Path, Path]:
    """Provide mock ansible-playbook and args capture path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)

    args_file = tmp_path / "ansible_args.txt"
    mock_ap = bin_dir / "ansible-playbook"
    mock_ap.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{args_file}"\nexit 0\n')
    mock_ap.chmod(mock_ap.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return bin_dir, args_file


def _run_wrapper(
    repo_root: Path,
    mock_bin_dir: Path,
    args_file: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env = {**os.environ, "PATH": f"{mock_bin_dir}:{os.environ['PATH']}"}
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "provision_benchmarks.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    recorded = args_file.read_text().splitlines() if args_file.exists() else []
    return result, recorded


class TestMissingHypervisorsFile:
    def test_missing_hypervisors_file_warns_and_exits_nonzero(
        self,
        wrapper_repo_copy: Path,
        mock_bin: tuple[Path, Path],
    ) -> None:
        mock_bin_dir, args_file = mock_bin

        result, recorded = _run_wrapper(wrapper_repo_copy, mock_bin_dir, args_file)

        assert result.returncode != 0
        assert recorded == []
        assert "hypervisors.txt" in result.stderr
        assert "hypervisors.txt.example" in result.stderr
        assert "warn" in result.stderr.lower()

    def test_env_override_bypasses_missing_hypervisors_file_check(
        self,
        wrapper_repo_copy: Path,
        mock_bin: tuple[Path, Path],
    ) -> None:
        mock_bin_dir, args_file = mock_bin

        result, recorded = _run_wrapper(
            wrapper_repo_copy,
            mock_bin_dir,
            args_file,
            extra_env={"HYPERVISOR_HOSTS": "hv-a,hv-b"},
        )

        assert result.returncode == 0
        assert recorded != []
