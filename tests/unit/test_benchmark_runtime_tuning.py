"""Tests for benchmark runtime tuning defaults and task wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS_FILE = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "defaults" / "main.yml"
)
CRYPTO_TASK = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "crypto.yml"
)
COMPILER_TASK = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"
)


def _extract_section(content: str, start_anchor: str, end_anchor: str) -> str:
    start = content.find(start_anchor)
    assert start != -1, f"Missing section start anchor: {start_anchor}"

    end = content.find(end_anchor, start)
    assert end != -1, f"Missing section end anchor: {end_anchor}"

    return content[start:end]


def test_runtime_tuning_defaults_are_defined() -> None:
    defaults = yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8"))

    assert defaults["run_benchmarks_crypto_asymmetric_runs"] == 3
    assert defaults["run_benchmarks_crypto_asymmetric_warmup"] == 1
    assert defaults["run_benchmarks_crypto_asymmetric_iterations"] == 500
    assert defaults["run_benchmarks_crypto_ssh_sign_runs"] == 3
    assert defaults["run_benchmarks_crypto_ssh_sign_warmup"] == 1
    assert defaults["run_benchmarks_crypto_ssh_sign_iterations"] == 500
    assert defaults["run_benchmarks_compression_runs"] == 2
    assert defaults["run_benchmarks_compression_warmup"] == 1
    assert defaults["run_benchmarks_ffmpeg_video_runs"] == 2
    assert defaults["run_benchmarks_ffmpeg_video_warmup"] == 1
    assert defaults["run_benchmarks_compiler_sqlite_opt_levels"] == ["-O2", "-O3"]


def test_crypto_task_uses_runtime_tuning_variables() -> None:
    content = CRYPTO_TASK.read_text(encoding="utf-8")
    asymmetric_section = _extract_section(
        content,
        "- name: Run OpenSSL asymmetric benchmarks",
        "- name: Warn on crypto_asymmetric benchmark failure",
    )
    ssh_sign_section = _extract_section(
        content,
        "- name: Run SSH signing benchmarks",
        "- name: Warn on crypto_ssh_sign benchmark failure",
    )

    assert "N={{ run_benchmarks_crypto_asymmetric_iterations }}" in asymmetric_section
    assert "--runs {{ run_benchmarks_crypto_asymmetric_runs }}" in asymmetric_section
    assert "--warmup {{ run_benchmarks_crypto_asymmetric_warmup }}" in asymmetric_section

    assert "N={{ run_benchmarks_crypto_ssh_sign_iterations }}" in ssh_sign_section
    assert "--runs {{ run_benchmarks_crypto_ssh_sign_runs }}" in ssh_sign_section
    assert "--warmup {{ run_benchmarks_crypto_ssh_sign_warmup }}" in ssh_sign_section


def test_compiler_task_uses_sqlite_opt_level_tuning_variable() -> None:
    content = COMPILER_TASK.read_text(encoding="utf-8")
    sqlite_section = _extract_section(
        content,
        "- name: Run SQLite amalgamation compile benchmarks",
        "- name: Warn on compiler_sqlite benchmark failure",
    )

    assert "{% for opt in run_benchmarks_compiler_sqlite_opt_levels %}" in sqlite_section
    assert (
        'CMDS+=(--command-name "{{ cc_label }}-{{ opt | replace(\' \', \'_\') }}"'
        in sqlite_section
    )
    assert '"{{ cc_exe }} {{ opt }} -o /dev/null -c sqlite3.c")' in sqlite_section
