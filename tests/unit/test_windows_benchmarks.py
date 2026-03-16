"""Tests for Windows benchmark task files and supporting configuration."""
import os
import yaml
import pytest

TASKS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "roles", "run_benchmarks", "tasks"
)
DEFAULTS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "roles", "run_benchmarks", "defaults", "main.yml"
)

WINDOWS_TASK_FILES = [
    "compression_win.yml",
    "crypto_win.yml",
    "compiler_win.yml",
    "python_win.yml",
    "coreutils_win.yml",
    "sqlite_win.yml",
    "numeric_win.yml",
    "process_win.yml",
    "linker_win.yml",
    "startup_win.yml",
    "setup_win.yml",
    "normalize_win.yml",
    "denormalize_win.yml",
]

EXPECTED_WINDOWS_CATEGORIES = [
    "compression",
    "crypto",
    "compiler",
    "python",
    "coreutils",
    "sqlite",
    "numeric",
    "process",
    "linker",
    "startup",
]


class TestWindowsTaskFilesExist:
    @pytest.mark.parametrize("filename", WINDOWS_TASK_FILES)
    def test_task_file_exists(self, filename: str) -> None:
        path = os.path.join(TASKS_DIR, filename)
        assert os.path.isfile(path), f"Windows task file missing: {filename}"

    @pytest.mark.parametrize("filename", WINDOWS_TASK_FILES)
    def test_task_file_is_valid_yaml(self, filename: str) -> None:
        path = os.path.join(TASKS_DIR, filename)
        with open(path) as f:
            content = yaml.safe_load(f)
        assert isinstance(content, list), f"{filename} should be a YAML list of tasks"
        assert len(content) > 0, f"{filename} should contain at least one task"


class TestWindowsCategoriesInDefaults:
    def _load_defaults(self) -> dict:
        with open(DEFAULTS_FILE) as f:
            return yaml.safe_load(f)

    def test_windows_categories_key_exists(self) -> None:
        defaults = self._load_defaults()
        assert "run_benchmarks_windows_categories" in defaults

    @pytest.mark.parametrize("category", EXPECTED_WINDOWS_CATEGORIES)
    def test_category_in_defaults(self, category: str) -> None:
        defaults = self._load_defaults()
        categories = defaults.get("run_benchmarks_windows_categories", [])
        assert category in categories, (
            f"Category '{category}' missing from run_benchmarks_windows_categories"
        )


class TestNewWindowsTaskFileContent:
    @pytest.mark.parametrize("filename", [
        "sqlite_win.yml",
        "numeric_win.yml",
        "process_win.yml",
        "linker_win.yml",
        "startup_win.yml",
    ])
    def test_task_file_uses_win_modules(self, filename: str) -> None:
        path = os.path.join(TASKS_DIR, filename)
        with open(path) as f:
            content = f.read()
        assert "ansible.windows.win_shell" in content or "ansible.windows.win_copy" in content, (
            f"{filename} should use ansible.windows modules"
        )

    @pytest.mark.parametrize("filename", [
        "sqlite_win.yml",
        "numeric_win.yml",
        "process_win.yml",
        "linker_win.yml",
        "startup_win.yml",
    ])
    def test_task_file_exports_json(self, filename: str) -> None:
        path = os.path.join(TASKS_DIR, filename)
        with open(path) as f:
            content = f.read()
        assert "--export-json" in content, (
            f"{filename} should export results to JSON via hyperfine"
        )

    @pytest.mark.parametrize("filename", [
        "sqlite_win.yml",
        "numeric_win.yml",
        "process_win.yml",
        "linker_win.yml",
        "startup_win.yml",
    ])
    def test_task_file_has_warn_on_failure(self, filename: str) -> None:
        path = os.path.join(TASKS_DIR, filename)
        with open(path) as f:
            content = f.read()
        assert "[WARN]" in content, (
            f"{filename} should have a warning task for benchmark failure"
        )
