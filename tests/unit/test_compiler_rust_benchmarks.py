from __future__ import annotations

from pathlib import Path

COMPILER_TASK = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"
)


def _content() -> str:
    return COMPILER_TASK.read_text(encoding="utf-8")


def test_compiler_task_exports_rust_runtime_json() -> None:
    assert "compiler_rust_runtime.json" in _content()


def test_compiler_task_exports_rust_external_json() -> None:
    assert "compiler_rust_external.json" in _content()


def test_compiler_task_has_warn_blocks_for_new_rust_benchmarks() -> None:
    text = _content()
    assert "Warn on compiler_rust_runtime benchmark failure" in text
    assert "Warn on compiler_rust_external benchmark failure" in text
