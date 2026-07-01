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


def test_compiler_task_labels_new_rust_commands() -> None:
    text = _content()
    assert '--command-name "{{ tc_label }}-runtime"' in text
    assert '--command-name "{{ tc_label }}-external"' in text


def test_compiler_task_uses_toolchain_specific_rust_runtime_and_external_binaries() -> None:
    text = _content()
    assert 'runtime_bin="./target/release/rust_runtime_{{ tc_label }}"' in text
    assert 'external_bin="./target/release/rust_external_{{ tc_label }}"' in text


def test_compiler_task_refreshes_rust_benchmark_project_files() -> None:
    text = _content()
    assert "[ ! -d {{ run_benchmarks_work_dir }}/rust_bench ]" not in text
    assert 'creates: "{{ run_benchmarks_work_dir }}/rust_bench/Cargo.toml"' not in text


def test_compiler_task_disables_rust_cargo_autobins_and_cleans_legacy_main() -> None:
    text = _content()
    assert "autobins = false" in text
    assert "rm -f {{ run_benchmarks_work_dir }}/rust_bench/src/main.rs" in text


def test_compiler_task_keeps_compile_benchmark_in_separate_compile_project() -> None:
    text = _content()
    assert "{{ run_benchmarks_work_dir }}/rust_bench/compile_bench/src" in text
    assert "{{ run_benchmarks_work_dir }}/rust_bench/compile_bench/Cargo.toml" in text
    assert "cd {{ run_benchmarks_work_dir }}/rust_bench/compile_bench" in text
    assert '{{ tc_cargo }} build 2>&1' in text
    assert '{{ tc_cargo }} build --release 2>&1' in text


def test_compiler_task_pins_external_rust_dependencies_exactly() -> None:
    text = _content()
    assert 'regex = "=1.11.1"' in text
    assert 'serde_json = "=1.0.140"' in text


def test_compiler_task_reports_failed_runtime_and_external_toolchain_builds() -> None:
    text = _content()
    assert 'FAILED_TOOLCHAINS=()' in text
    assert 'failed Rust runtime builds for:' in text
    assert 'failed Rust external builds for:' in text
    assert text.index('if [ "${#FAILED_TOOLCHAINS[@]}" -gt 0 ] && [ -z "${CMDS[*]}" ]; then') < text.index(
        '[ -z "${CMDS[*]}" ] && exit 0'
    )
