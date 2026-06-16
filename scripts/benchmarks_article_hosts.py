"""Helpers for generating benchmark article host detail links/pages."""

from __future__ import annotations


def build_host_detail_href(host: str) -> str:
    """Build a relative host detail href for the benchmarks article."""
    raise NotImplementedError


def render_host_markdown_link(host: str) -> str:
    """Render a markdown link pointing at the host detail page."""
    raise NotImplementedError
