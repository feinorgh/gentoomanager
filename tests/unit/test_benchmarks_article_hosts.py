"""Unit tests for planned scripts/benchmarks_article_hosts.py helpers."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _require_hosts_module():
    try:
        return importlib.import_module("benchmarks_article_hosts")
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "scripts/benchmarks_article_hosts.py is required for host-detail helper implementation"
        ) from exc


def test_host_link_markdown_wraps_label_and_href() -> None:
    bah = _require_hosts_module()
    assert bah.host_link_markdown("Zeus") == "[Zeus](hosts/Zeus.html)"


def test_host_link_markdown_trims_surrounding_whitespace() -> None:
    bah = _require_hosts_module()
    assert bah.host_link_markdown("  Hera  ") == "[Hera](hosts/Hera.html)"


def test_parse_versions_ignores_entries_without_equals() -> None:
    bah = _require_hosts_module()
    parsed = bah.parse_versions([
        "gcc=gcc (Gentoo) 15.2.1",
        "invalid-entry",
        "python=Python 3.14.0",
    ])

    assert parsed == {
        "gcc": "gcc (Gentoo) 15.2.1",
        "python": "Python 3.14.0",
    }


def test_normalize_metadata_defaults_optional_fields_to_na() -> None:
    bah = _require_hosts_module()
    normalized = bah.normalize_metadata({"hostname": "hera"})

    assert normalized["hostname"] == "hera"
    assert normalized["os"] == "n/a"
    assert normalized["os_version"] == "n/a"
    assert normalized["os_family"] == "n/a"
    assert normalized["cpu_model"] == "n/a"
    assert normalized["gentoo_profile"] == "n/a"
    assert normalized["common_flags"] == "n/a"
    assert normalized["cflags"] == "n/a"
    assert normalized["ldflags"] == "n/a"


def test_render_host_qmd_escapes_front_matter_title() -> None:
    bah = _require_hosts_module()
    title_host = 'hera"\nformat: pdf'
    rendered = bah.render_host_qmd(title_host, {"hostname": "hera"})

    lines = rendered.splitlines()
    assert lines[0] == "---"
    assert lines[1] == 'title: "Host details: hera\\"\\nformat: pdf"'
    assert lines[2] == "format: html"
    assert lines[3] == "---"


def test_generate_host_pages_raises_on_filename_collision(tmp_path: Path) -> None:
    bah = _require_hosts_module()
    results_dir = tmp_path / "results"
    output_dir = tmp_path / "hosts"
    first_host = results_dir / "first"
    second_host = results_dir / "second"
    first_host.mkdir(parents=True)
    second_host.mkdir(parents=True)

    (first_host / "metadata.json").write_text('{"hostname": "hera/01"}')
    (second_host / "metadata.json").write_text('{"hostname": "hera\\\\01"}')

    try:
        bah.generate_host_pages(results_dir, output_dir)
    except ValueError as exc:
        assert "Filename collision for host detail page" in str(exc)
        assert "hera_01.qmd" in str(exc)
    else:
        raise AssertionError("Expected explicit filename collision error")


def _run_hosts_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    script_path = REPO_ROOT / "scripts" / "benchmarks_article_hosts.py"
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_hosts_script_reports_missing_results_dir_without_traceback(tmp_path: Path) -> None:
    output_dir = tmp_path / "hosts"
    missing_dir = tmp_path / "does-not-exist"

    completed = _run_hosts_script(["--results", str(missing_dir), "--output", str(output_dir)])

    assert completed.returncode != 0
    assert "Unable to read results directory" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_hosts_script_reports_unreadable_results_dir_without_traceback(tmp_path: Path) -> None:
    output_dir = tmp_path / "hosts"
    unreadable_dir = tmp_path / "unreadable-results"
    unreadable_dir.mkdir()
    unreadable_dir.chmod(0)
    try:
        completed = _run_hosts_script(
            ["--results", str(unreadable_dir), "--output", str(output_dir)]
        )
    finally:
        unreadable_dir.chmod(0o755)

    assert completed.returncode != 0
    assert "Unable to read results directory" in completed.stderr
    assert "Traceback" not in completed.stderr
