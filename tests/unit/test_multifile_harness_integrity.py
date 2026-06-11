"""Tests for compiler_multifile harness integrity guarantees."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _read_yaml(path: str) -> dict | list:
    return yaml.safe_load(_read(path))


def _load_multifile_generator():
    module_path = REPO_ROOT / "roles/run_benchmarks/files/generate_multifile_bench.py"
    spec = importlib.util.spec_from_file_location("generate_multifile_bench", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_suse_packages_include_make() -> None:
    defaults = _read_yaml("roles/provision_benchmarks/defaults/main.yml")
    assert "make" in defaults["provision_benchmarks_packages"]["Suse"]


def test_redhat_packages_include_make() -> None:
    defaults = _read_yaml("roles/provision_benchmarks/defaults/main.yml")
    assert "make" in defaults["provision_benchmarks_packages"]["RedHat"]


def test_nixos_packages_include_gnumake() -> None:
    tasks = _read_yaml("roles/provision_benchmarks/tasks/os/nixos.yml")
    install_task = next(
        (task for task in tasks if task.get("name") == "Install benchmark dependencies (NixOS)"),
        None,
    )
    assert install_task is not None, "Expected NixOS install task not found"
    assert "gnumake" in install_task.get("loop", [])


def test_compiler_multifile_block_has_no_ignore_failure() -> None:
    tasks = _read_yaml("roles/run_benchmarks/tasks/compiler.yml")
    multifile_task = next(
        (
            task
            for task in tasks
            if task.get("name") == "Run multi-file C project compile benchmarks"
        ),
        None,
    )
    assert multifile_task is not None, "Expected compiler_multifile run task not found"
    command = multifile_task.get("ansible.builtin.shell", {}).get("cmd", "")
    assert "--ignore-failure" not in command


def test_compiler_multifile_has_preflight_and_exitcode_validation() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    assert "Check make availability for compiler_multifile" in content
    assert "Validate compiler_multifile exit codes" in content


def test_multifile_makefile_template_is_portable() -> None:
    module = _load_multifile_generator()
    makefile = module._render_makefile(3)

    assert "SRCS    = mod_00.c mod_01.c mod_02.c main.c" in makefile
    assert "OBJS    = mod_00.o mod_01.o mod_02.o main.o" in makefile
    assert "$(wildcard mod_*.c)" not in makefile
    assert "$(SRCS:.c=.o)" not in makefile
    assert "$(BIN): $(OBJS)" in makefile
    assert "\t$(CC) $(CFLAGS) -o $@ $(OBJS) -lm" in makefile


def test_compiler_multifile_has_no_warning_task() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    assert "Warn on compiler_multifile benchmark failure" not in content
