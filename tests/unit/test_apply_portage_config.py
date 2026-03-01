"""Unit tests for the apply_portage_config role template."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _make_env() -> Environment:
    """Set up a Jinja2 environment with Ansible-compatible filters."""
    tmpl_dir = Path(__file__).parent.parent.parent / "roles" / "apply_portage_config" / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))

    def regex_replace(value: str, pattern: str, replacement: str) -> str:
        return re.sub(pattern, replacement, value)

    env.filters["regex_replace"] = regex_replace
    return env


def _render(
    build_profile: dict | None = None,
    make_conf: dict | None = None,
    use_expand: dict | None = None,
    use: list[str] | None = None,
) -> str:
    env = _make_env()
    tmpl = env.get_template("make.conf.j2")
    return tmpl.render(
        inventory_hostname="test-host",
        apply_portage_config_merged_build_profile=build_profile or {},
        apply_portage_config_merged_make_conf=make_conf or {},
        apply_portage_config_merged_use_expand=use_expand or {},
        apply_portage_config_merged_use=use or [],
    )


class TestMakeConfTemplate:
    def test_common_flags_comes_first(self):
        result = _render(
            make_conf={"COMMON_FLAGS": "-O2 -pipe", "ACCEPT_LICENSE": "@FREE"},
            build_profile={"CFLAGS": "${COMMON_FLAGS}"},
        )
        lines = [l for l in result.splitlines() if l and not l.startswith("#")]
        assert lines[0] == 'COMMON_FLAGS="-O2 -pipe"'
        assert lines[1] == 'CFLAGS="${COMMON_FLAGS}"'

    def test_build_profile_overrides_make_conf(self):
        result = _render(
            make_conf={"CFLAGS": "-O1"},
            build_profile={"CFLAGS": "-O2"},
        )
        assert 'CFLAGS="-O2"' in result
        assert "-O1" not in result

    def test_use_flags_rendered(self):
        result = _render(use=["X", "alsa", "-wayland"])
        assert 'USE="X alsa -wayland"' in result

    def test_use_expand_strips_plus(self):
        result = _render(use_expand={"VIDEO_CARDS": ["+intel", "+vesa", "-*"]})
        assert 'VIDEO_CARDS="intel vesa -*"' in result

    def test_empty_ldflags_omitted(self):
        result = _render(build_profile={"LDFLAGS": ""})
        assert "LDFLAGS" not in result

    def test_remaining_make_conf_alphabetical(self):
        result = _render(
            make_conf={"PORTDIR": "/var/db/repos/gentoo", "ACCEPT_LICENSE": "@FREE"},
        )
        lines = [l for l in result.splitlines() if l and not l.startswith("#")]
        accept_idx = next(i for i, l in enumerate(lines) if "ACCEPT_LICENSE" in l)
        portdir_idx = next(i for i, l in enumerate(lines) if "PORTDIR" in l)
        assert accept_idx < portdir_idx

    def test_managed_header_present(self):
        result = _render()
        assert "Managed by Ansible" in result
        assert "test-host" in result
