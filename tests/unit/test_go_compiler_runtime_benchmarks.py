from __future__ import annotations

from pathlib import Path

COMPILER_TASK_FILE = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"
)
MAIN_TASK_FILE = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "main.yml"
)
PLAYBOOK_FILE = Path(__file__).resolve().parents[2] / "playbooks" / "run_benchmarks.yml"


def _compiler_task_text() -> str:
    return COMPILER_TASK_FILE.read_text(encoding="utf-8")


def _main_task_text() -> str:
    return MAIN_TASK_FILE.read_text(encoding="utf-8")


def _playbook_text() -> str:
    return PLAYBOOK_FILE.read_text(encoding="utf-8")


def test_compiler_task_exports_split_go_and_gccgo_results() -> None:
    text = _compiler_task_text()
    assert "compiler_go.json" in text
    assert "compiler_go_runtime.json" in text
    assert "compiler_gccgo.json" in text
    assert "compiler_gccgo_runtime.json" in text


def test_compiler_task_labels_go_and_gccgo_runtime_workloads() -> None:
    text = _compiler_task_text()
    assert "Run Go runtime benchmark" in text
    assert "Run gccgo compile benchmark" in text
    assert "Run gccgo runtime benchmark" in text


def test_compiler_task_uses_go_and_gccgo_runtime_command_names() -> None:
    text = _compiler_task_text()
    assert '--command-name "{{ go_label }}-runtime"' in text
    assert '--command-name "{{ gccgo_label }}-compile"' in text
    assert '--command-name "{{ gccgo_label }}-runtime"' in text


def test_skip_logic_tracks_go_and_gccgo_completion_files() -> None:
    playbook = _playbook_text()
    main_tasks = _main_task_text()
    for expected in (
        "compiler_go_runtime.json",
        "compiler_gccgo.json",
        "compiler_gccgo_runtime.json",
    ):
        assert expected in playbook
        assert expected in main_tasks
    assert "run_benchmarks_skip_existing_has_gccgo" in main_tasks
