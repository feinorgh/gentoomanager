"""Scaffold for host detail helper functions used by benchmark article tests."""

from __future__ import annotations

from typing import Any


def host_link_markdown(host: str) -> str:
    """Render a markdown link to a host detail page."""
    raise NotImplementedError


def parse_versions(values: list[str]) -> dict[str, str]:
    """Parse version entries formatted as key=value."""
    raise NotImplementedError


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize host metadata with default placeholders for optional fields."""
    raise NotImplementedError
