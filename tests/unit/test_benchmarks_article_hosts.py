"""Unit tests for scripts/benchmarks_article_hosts.py."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmarks_article_hosts as bah  # noqa: E402


def test_build_host_detail_href_uses_hosts_relative_path() -> None:
    assert bah.build_host_detail_href("Zeus") == "hosts/Zeus.html"


def test_render_host_markdown_link_wraps_label_and_href() -> None:
    assert bah.render_host_markdown_link("Zeus") == "[Zeus](hosts/Zeus.html)"


def test_render_host_markdown_link_trims_surrounding_whitespace() -> None:
    assert bah.render_host_markdown_link("  Hera  ") == "[Hera](hosts/Hera.html)"


def test_benchmarks_article_hosts_has_no_shebang() -> None:
    script_path = REPO_ROOT / "scripts" / "benchmarks_article_hosts.py"
    first_line = script_path.read_text(encoding="utf-8").splitlines()[0]
    assert not first_line.startswith("#!"), (
        "scripts/benchmarks_article_hosts.py must not have a shebang "
        "to satisfy ansible-test sanity for non-module files"
    )
