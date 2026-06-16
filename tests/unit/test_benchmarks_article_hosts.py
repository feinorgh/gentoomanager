"""Unit tests for planned scripts/benchmarks_article_hosts.py helpers."""

from __future__ import annotations

import importlib
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


def test_build_host_detail_href_uses_hosts_relative_path() -> None:
    bah = _require_hosts_module()
    assert bah.build_host_detail_href("Zeus") == "hosts/Zeus.html"


def test_render_host_markdown_link_wraps_label_and_href() -> None:
    bah = _require_hosts_module()
    assert bah.render_host_markdown_link("Zeus") == "[Zeus](hosts/Zeus.html)"


def test_render_host_markdown_link_trims_surrounding_whitespace() -> None:
    bah = _require_hosts_module()
    assert bah.render_host_markdown_link("  Hera  ") == "[Hera](hosts/Hera.html)"


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
