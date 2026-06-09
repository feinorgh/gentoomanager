"""Tests for compiler_multifile harness integrity guarantees."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_suse_packages_include_make() -> None:
    defaults = yaml.safe_load(_read("roles/provision_benchmarks/defaults/main.yml"))
    assert "make" in defaults["provision_benchmarks_packages"]["Suse"]


def test_nixos_packages_include_gnumake() -> None:
    content = _read("roles/provision_benchmarks/tasks/os/nixos.yml")
    assert "gnumake" in content


def test_compiler_multifile_block_has_no_ignore_failure() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    multifile_section = content.split("# Multi-file C project compile benchmark", maxsplit=1)[1]
    assert "--ignore-failure" not in multifile_section


def test_compiler_multifile_has_preflight_and_exitcode_validation() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    assert "Check make availability for compiler_multifile" in content
    assert "Validate compiler_multifile exit codes" in content
