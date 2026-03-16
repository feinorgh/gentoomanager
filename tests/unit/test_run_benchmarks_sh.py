"""Tests for scripts/run_benchmarks.sh argument parsing.

Uses a mock ansible-playbook that records its arguments to a file instead of
running a real playbook, so we can assert the correct flags are passed.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_benchmarks.sh"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bin(tmp_path: Path):
    """Return a (bin_dir, args_file) tuple.

    bin_dir contains a mock ``ansible-playbook`` that writes one arg per line
    to args_file and exits 0.  Prepend bin_dir to PATH before calling the
    script.
    """
    args_file = tmp_path / "ansible_args.txt"
    mock_ap = tmp_path / "ansible-playbook"
    mock_ap.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{args_file}"\n'
        "exit 0\n"
    )
    mock_ap.chmod(mock_ap.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmp_path, args_file


def _run(
    mock_bin_dir: Path,
    args_file: Path,
    extra_args: list[str],
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run run_benchmarks.sh with mocked ansible-playbook; return (result, recorded_args)."""
    env = {**os.environ, "PATH": f"{mock_bin_dir}:{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", str(SCRIPT)] + extra_args,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    recorded = args_file.read_text().splitlines() if args_file.exists() else []
    return result, recorded


def _evars_from_args(recorded: list[str]) -> str:
    """Return the -e JSON string from the recorded argument list, or ''."""
    try:
        idx = recorded.index("-e")
        return recorded[idx + 1]
    except (ValueError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHelpFlag:
    def test_help_exits_zero(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["--help"])
        assert result.returncode == 0

    def test_help_shows_usage(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["--help"])
        assert "Usage:" in result.stdout

    def test_short_help_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["-h"])
        assert result.returncode == 0


class TestUnknownFlag:
    def test_unknown_flag_exits_nonzero(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["--totally-unknown-flag"])
        assert result.returncode != 0


class TestRunsAndWarmup:
    def test_runs_passed_as_extra_var(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--runs", "10"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_runs" in evars
        assert "10" in evars

    def test_warmup_passed_as_extra_var(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--warmup", "5"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_warmup" in evars
        assert "5" in evars

    def test_runs_non_integer_exits_nonzero(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["--runs", "notanumber"])
        assert result.returncode != 0

    def test_warmup_non_integer_exits_nonzero(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, _args = _run(bin_dir, args_file, ["--warmup", "abc"])
        assert result.returncode != 0


class TestCategoryFlag:
    def test_single_category_becomes_json_array(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--category", "compression"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_categories" in evars
        assert '"compression"' in evars

    def test_multiple_categories_become_json_array(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--category", "compression,crypto"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert '"compression"' in evars
        assert '"crypto"' in evars
        # Verify it's actually a JSON array
        assert "[" in evars and "]" in evars


class TestExtendedCodecs:
    def test_extended_codecs_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--extended-codecs"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_ffmpeg_extended_codecs" in evars
        assert "true" in evars


class TestNoRamScale:
    def test_no_ram_scale_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--no-ram-scale"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_scale_ram" in evars
        assert "false" in evars


class TestSkipComplete:
    def test_skip_complete_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--skip-complete"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_skip_complete" in evars
        assert "true" in evars


class TestSkipExisting:
    def test_skip_existing_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--skip-existing"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_skip_existing" in evars
        assert "true" in evars

    def test_skip_existing_combined_with_skip_complete(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--skip-existing", "--skip-complete"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_skip_existing" in evars
        assert "run_benchmarks_skip_complete" in evars


class TestManagePower:
    def test_manage_power_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--manage-power"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_manage_power" in evars
        assert "true" in evars

    def test_manage_power_combined_with_skip_existing(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--manage-power", "--skip-existing"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_manage_power" in evars
        assert "run_benchmarks_skip_existing" in evars

    def test_manage_power_not_set_by_default(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, [])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_manage_power" not in evars


class TestCombinedFlags:
    def test_runs_warmup_category_combined(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(
            bin_dir, args_file,
            ["--runs", "3", "--warmup", "1", "--category", "bash,compression"],
        )
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_runs" in evars
        assert "run_benchmarks_warmup" in evars
        assert "run_benchmarks_categories" in evars
        assert '"bash"' in evars
        assert '"compression"' in evars


class TestPlaybookInvocation:
    def test_playbook_path_in_args(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, [])
        assert result.returncode == 0
        # The playbook path should be among the recorded args
        assert any("run_benchmarks.yml" in arg for arg in recorded)

    def test_inventory_flag_in_args(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, [])
        assert result.returncode == 0
        assert "-i" in recorded


class TestIncludeWindows:
    def test_include_windows_sets_flag(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--include-windows"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_include_windows" in evars
        assert "true" in evars

    def test_include_windows_not_set_by_default(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, [])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_include_windows" not in evars

    def test_include_windows_combined_with_manage_power(self, mock_bin) -> None:
        bin_dir, args_file = mock_bin
        result, recorded = _run(bin_dir, args_file, ["--include-windows", "--manage-power"])
        assert result.returncode == 0
        evars = _evars_from_args(recorded)
        assert "run_benchmarks_include_windows" in evars
        assert "run_benchmarks_manage_power" in evars
