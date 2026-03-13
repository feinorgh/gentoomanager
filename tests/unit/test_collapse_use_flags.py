"""Unit tests for scripts/collapse_use_flags.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the scripts/ directory importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from collapse_use_flags import (  # noqa: E402
    _collapse_flag_sets,
    _flags_to_set,
    _set_to_list,
    build_group_map,
    collapse_build_profile,
    collapse_global_use,
    collapse_make_conf,
    collapse_package_use,
    collapse_use_expand,
    collapse_use_flag_types,
    load_facts,
    parse_make_conf,
    preprocess_facts,
    promote_wildcard_package_use,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_facts(tmp_path: Path, facts_list: list[dict]) -> Path:
    """Write a list of host-fact dicts to per-host JSON files in tmp_path."""
    for facts in facts_list:
        (tmp_path / f"{facts['hostname']}.json").write_text(json.dumps(facts))
    return tmp_path


def _make_host(
    name: str,
    groups: list[str],
    global_use: list[str] | None = None,
    use_expand: dict | None = None,
    build_profile: dict | None = None,
    package_use: dict | None = None,
    make_conf_raw: str = "",
    profile_global_flags: list[str] | None = None,
    profile_local_flags: list[str] | None = None,
) -> dict:
    return {
        "hostname": name,
        "groups": groups,
        "global_use_flags": global_use or [],
        "use_expand": use_expand or {},
        "build_profile": build_profile or {},
        "package_use": package_use or {},
        "make_conf_raw": make_conf_raw,
        "profile_global_flags": profile_global_flags or [],
        "profile_local_flags": profile_local_flags or [],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestFlagsToSet:
    def test_bare_flag_becomes_plus(self):
        assert _flags_to_set(["foo"]) == frozenset({"+foo"})

    def test_explicit_plus_kept(self):
        assert _flags_to_set(["+foo"]) == frozenset({"+foo"})

    def test_minus_kept(self):
        assert _flags_to_set(["-foo"]) == frozenset({"-foo"})

    def test_mixed(self):
        assert _flags_to_set(["a", "+b", "-c"]) == frozenset({"+a", "+b", "-c"})

    def test_empty(self):
        assert _flags_to_set([]) == frozenset()


class TestSetToList:
    def test_enabled_before_disabled(self):
        result = _set_to_list(frozenset({"-z", "+a", "+b"}))
        assert result == ["+a", "+b", "-z"]


class TestCollapseFlagSets:
    def test_common_extracted(self):
        per_host = {"h1": frozenset({"+a", "+b"}), "h2": frozenset({"+a", "+c"})}
        common, grp, remainder = _collapse_flag_sets(per_host, {}, ["h1", "h2"])
        assert common == frozenset({"+a"})
        assert remainder["h1"] == frozenset({"+b"})
        assert remainder["h2"] == frozenset({"+c"})

    def test_group_collapse(self):
        per_host = {
            "h1": frozenset({"+a", "+b"}),
            "h2": frozenset({"+a", "+b"}),
            "h3": frozenset({"+a"}),
        }
        group_map = {"grp1": ["h1", "h2"]}
        common, grp, remainder = _collapse_flag_sets(per_host, group_map, ["h1", "h2", "h3"])
        assert common == frozenset({"+a"})
        assert grp["grp1"] == frozenset({"+b"})
        assert not remainder["h1"]
        assert not remainder["h2"]
        assert not remainder["h3"]


# ---------------------------------------------------------------------------
# load_facts / build_group_map
# ---------------------------------------------------------------------------


class TestLoadFacts:
    def test_loads_all_json_files(self, tmp_path):
        h1 = _make_host("host1", ["gentoo"])
        h2 = _make_host("host2", ["gentoo"])
        _write_facts(tmp_path, [h1, h2])
        facts = load_facts(tmp_path)
        assert set(facts.keys()) == {"host1", "host2"}

    def test_empty_dir_warns(self, tmp_path, capsys):
        load_facts(tmp_path)
        assert "WARNING" in capsys.readouterr().err


class TestBuildGroupMap:
    def test_extracts_groups(self):
        facts = {
            "h1": {"groups": ["gentoo", "lto_enabled"]},
            "h2": {"groups": ["gentoo"]},
        }
        gm = build_group_map(facts)
        assert set(gm["gentoo"]) == {"h1", "h2"}
        assert gm["lto_enabled"] == ["h1"]

    def test_all_group_excluded(self):
        facts = {"h1": {"groups": ["all", "gentoo"]}}
        gm = build_group_map(facts)
        assert "all" not in gm


# ---------------------------------------------------------------------------
# parse_make_conf / preprocess_facts
# ---------------------------------------------------------------------------


class TestParseMakeConf:
    def test_double_quoted(self):
        result = parse_make_conf('CFLAGS="-O2 -pipe"')
        assert result["CFLAGS"] == "-O2 -pipe"

    def test_single_quoted(self):
        result = parse_make_conf("ACCEPT_LICENSE='@FREE'")
        assert result["ACCEPT_LICENSE"] == "@FREE"

    def test_unquoted(self):
        result = parse_make_conf("MAKEOPTS=-j8")
        assert result["MAKEOPTS"] == "-j8"

    def test_multiple_vars(self):
        text = 'USE="X alsa"\nCFLAGS="-O2"\nMAKEOPTS="-j8"'
        result = parse_make_conf(text)
        assert result["USE"] == "X alsa"
        assert result["CFLAGS"] == "-O2"
        assert result["MAKEOPTS"] == "-j8"

    def test_empty(self):
        assert parse_make_conf("") == {}


class TestPreprocessFacts:
    def test_derives_fields_from_make_conf_raw(self):
        facts = {
            "h1": {
                "make_conf_raw": 'USE="X alsa"\nVIDEO_CARDS="amdgpu"\nCFLAGS="-O2"',
                "package_use": {},
                "groups": [],
            },
        }
        preprocess_facts(facts)
        assert facts["h1"]["global_use_flags"] == ["X", "alsa"]
        assert facts["h1"]["use_expand"]["VIDEO_CARDS"] == ["amdgpu"]
        assert facts["h1"]["build_profile"]["CFLAGS"] == "-O2"

    def test_does_not_overwrite_existing_fields(self):
        facts = {
            "h1": {
                "make_conf_raw": 'USE="X alsa"',
                "global_use_flags": ["+custom"],
                "use_expand": {"CUSTOM": ["val"]},
                "build_profile": {"CUSTOM": "val"},
                "package_use": {},
                "groups": [],
            },
        }
        preprocess_facts(facts)
        assert facts["h1"]["global_use_flags"] == ["+custom"]
        assert facts["h1"]["use_expand"] == {"CUSTOM": ["val"]}


# ---------------------------------------------------------------------------
# collapse_global_use
# ---------------------------------------------------------------------------


class TestCollapseGlobalUse:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_global_use(facts, group_map, all_hosts)

    def test_common_flag_goes_to_all(self):
        hosts = [
            _make_host("h1", ["gentoo"], global_use=["nls", "X"]),
            _make_host("h2", ["gentoo"], global_use=["nls", "X"]),
        ]
        all_data, group_data, host_data = self._run(hosts)
        assert "+nls" in all_data["global_use_flags"]
        assert "+X" in all_data["global_use_flags"]
        assert not any(host_data.values())

    def test_unique_flag_goes_to_host(self):
        hosts = [
            _make_host("h1", ["gentoo"], global_use=["nls", "lto"]),
            _make_host("h2", ["gentoo"], global_use=["nls"]),
        ]
        all_data, group_data, host_data = self._run(hosts)
        assert "+nls" in all_data.get("global_use_flags", [])
        assert "+lto" not in all_data.get("global_use_flags", [])
        assert "+lto" in host_data.get("h1", {}).get("global_use_flags", [])

    def test_group_flag_goes_to_group(self):
        hosts = [
            _make_host("h1", ["gentoo", "lto_enabled"], global_use=["nls", "lto"]),
            _make_host("h2", ["gentoo", "lto_enabled"], global_use=["nls", "lto"]),
            _make_host("h3", ["gentoo"], global_use=["nls"]),
        ]
        all_data, group_data, host_data = self._run(hosts)
        assert "+nls" in all_data.get("global_use_flags", [])
        assert "+lto" in group_data.get("lto_enabled", {}).get("global_use_flags", [])
        assert not host_data.get("h3", {}).get("global_use_flags")

    def test_disabled_flag_propagates(self):
        hosts = [
            _make_host("h1", ["gentoo"], global_use=["-pulseaudio"]),
            _make_host("h2", ["gentoo"], global_use=["-pulseaudio"]),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        assert "-pulseaudio" in all_data["global_use_flags"]


# ---------------------------------------------------------------------------
# collapse_use_expand
# ---------------------------------------------------------------------------


class TestCollapseUseExpand:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_use_expand(facts, group_map, all_hosts)

    def test_common_use_expand_var_to_all(self):
        hosts = [
            _make_host("h1", ["gentoo"], use_expand={"VIDEO_CARDS": ["amdgpu"]}),
            _make_host("h2", ["gentoo"], use_expand={"VIDEO_CARDS": ["amdgpu"]}),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        assert "+amdgpu" in all_data["use_expand"]["VIDEO_CARDS"]

    def test_different_video_cards_go_to_host(self):
        hosts = [
            _make_host("h1", ["gentoo"], use_expand={"VIDEO_CARDS": ["amdgpu"]}),
            _make_host("h2", ["gentoo"], use_expand={"VIDEO_CARDS": ["nouveau"]}),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "VIDEO_CARDS" not in all_data.get("use_expand", {})
        assert "+amdgpu" in host_data["h1"]["use_expand"]["VIDEO_CARDS"]
        assert "+nouveau" in host_data["h2"]["use_expand"]["VIDEO_CARDS"]


# ---------------------------------------------------------------------------
# collapse_build_profile
# ---------------------------------------------------------------------------


class TestCollapseBuildProfile:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_build_profile(facts, group_map, all_hosts)

    def test_identical_cflags_to_all(self):
        cflags = "-O2 -pipe -march=native"
        hosts = [
            _make_host("h1", ["gentoo"], build_profile={"CFLAGS": cflags}),
            _make_host("h2", ["gentoo"], build_profile={"CFLAGS": cflags}),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        assert all_data["build_profile"]["CFLAGS"] == cflags

    def test_different_cflags_go_to_host(self):
        hosts = [
            _make_host("h1", ["gentoo"], build_profile={"CFLAGS": "-O2"}),
            _make_host("h2", ["gentoo"], build_profile={"CFLAGS": "-O3"}),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "CFLAGS" not in all_data.get("build_profile", {})
        assert host_data["h1"]["build_profile"]["CFLAGS"] == "-O2"


# ---------------------------------------------------------------------------
# collapse_package_use
# ---------------------------------------------------------------------------


class TestCollapsePackageUse:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_package_use(facts, group_map, all_hosts)

    def test_identical_package_entry_to_all(self):
        pkg = {"app-editors/vim": ["python"]}
        hosts = [
            _make_host("h1", ["gentoo"], package_use=pkg),
            _make_host("h2", ["gentoo"], package_use=pkg),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        assert "+python" in all_data["package_use"]["app-editors/vim"]

    def test_host_unique_package_entry(self):
        hosts = [
            _make_host("h1", ["gentoo"], package_use={"app-foo/bar": ["foo"]}),
            _make_host("h2", ["gentoo"], package_use={}),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "app-foo/bar" not in all_data.get("package_use", {})
        assert "+foo" in host_data["h1"]["package_use"]["app-foo/bar"]

    def test_group_package_entry(self):
        hosts = [
            _make_host("h1", ["gentoo", "lto_enabled"], package_use={"dev-libs/openssl": ["lto"]}),
            _make_host("h2", ["gentoo", "lto_enabled"], package_use={"dev-libs/openssl": ["lto"]}),
            _make_host("h3", ["gentoo"], package_use={}),
        ]
        all_data, group_data, _unused = self._run(hosts)
        assert "dev-libs/openssl" not in all_data.get("package_use", {})
        assert "+lto" in group_data["lto_enabled"]["package_use"]["dev-libs/openssl"]


# ---------------------------------------------------------------------------
# collapse_make_conf
# ---------------------------------------------------------------------------


class TestCollapseMakeConf:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_make_conf(facts, group_map, all_hosts)

    def test_common_var_to_all(self):
        hosts = [
            _make_host("h1", ["gentoo"], make_conf_raw='ACCEPT_LICENSE="@FREE"'),
            _make_host("h2", ["gentoo"], make_conf_raw='ACCEPT_LICENSE="@FREE"'),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        assert all_data["make_conf"]["ACCEPT_LICENSE"] == "@FREE"

    def test_different_var_to_host(self):
        hosts = [
            _make_host("h1", ["gentoo"], make_conf_raw='PORTDIR="/var/db/repos/gentoo"'),
            _make_host("h2", ["gentoo"], make_conf_raw='PORTDIR="/var/db/repos/custom"'),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "PORTDIR" not in all_data.get("make_conf", {})
        assert host_data["h1"]["make_conf"]["PORTDIR"] == "/var/db/repos/gentoo"

    def test_skips_use_and_use_expand_and_build_vars(self):
        hosts = [
            _make_host(
                "h1",
                ["gentoo"],
                make_conf_raw='USE="X"\nVIDEO_CARDS="amdgpu"\nCFLAGS="-O2"\nACCEPT_LICENSE="@FREE"',
            ),
            _make_host(
                "h2",
                ["gentoo"],
                make_conf_raw='USE="X"\nVIDEO_CARDS="amdgpu"\nCFLAGS="-O2"\nACCEPT_LICENSE="@FREE"',
            ),
        ]
        all_data, _unused, _unused2 = self._run(hosts)
        mc = all_data.get("make_conf", {})
        assert "USE" not in mc
        assert "VIDEO_CARDS" not in mc
        assert "CFLAGS" not in mc
        assert "ACCEPT_LICENSE" in mc


# ---------------------------------------------------------------------------
# collapse_use_flag_types
# ---------------------------------------------------------------------------


class TestCollapseUseFlagTypes:
    def _run(self, hosts: list[dict]):
        facts = {h["hostname"]: h for h in hosts}
        all_hosts = sorted(facts.keys())
        group_map = build_group_map(facts)
        return collapse_use_flag_types(facts, group_map, all_hosts)

    def test_identical_classification_to_all(self):
        profile_global = ["X", "alsa"]
        profile_local = ["gnome-shell"]
        hosts = [
            _make_host(
                "h1",
                ["gentoo"],
                global_use=["+X", "+gnome-shell", "+custom"],
                profile_global_flags=profile_global,
                profile_local_flags=profile_local,
            ),
            _make_host(
                "h2",
                ["gentoo"],
                global_use=["+X", "+gnome-shell", "+custom"],
                profile_global_flags=profile_global,
                profile_local_flags=profile_local,
            ),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "+X" in all_data["use_flag_types"]["global"]
        assert "+gnome-shell" in all_data["use_flag_types"]["local"]
        assert "+custom" in all_data["use_flag_types"]["unknown"]
        assert not host_data

    def test_different_flags_merged_to_all(self):
        hosts = [
            _make_host(
                "h1",
                ["gentoo"],
                global_use=["+X"],
                profile_global_flags=["X"],
                profile_local_flags=[],
            ),
            _make_host(
                "h2",
                ["gentoo"],
                global_use=["+X", "+extra"],
                profile_global_flags=["X"],
                profile_local_flags=[],
            ),
        ]
        all_data, _unused, host_data = self._run(hosts)
        assert "+X" in all_data["use_flag_types"]["global"]
        assert "+extra" in all_data["use_flag_types"]["unknown"]
        assert not host_data


# ---------------------------------------------------------------------------
# Promote */* package.use entries
# ---------------------------------------------------------------------------


class TestPromoteWildcardPackageUse:
    def test_plain_flags_go_to_global_use(self):
        facts = {
            "h1": _make_host(
                "h1",
                ["gentoo"],
                global_use=["+X"],
                package_use={"*/*": ["lto", "-wayland"]},
            ),
        }
        promote_wildcard_package_use(facts)
        flags = facts["h1"]["global_use_flags"]
        assert "+lto" in flags
        assert "-wayland" in flags
        assert "+X" in flags
        assert "*/*" not in facts["h1"]["package_use"]

    def test_use_expand_tokens_go_to_use_expand(self):
        facts = {
            "h1": _make_host(
                "h1",
                ["gentoo"],
                use_expand={"L10N": ["en"]},
                package_use={"*/*": ["VIDEO_CARDS:", "-*", "dummy", "intel"]},
            ),
        }
        promote_wildcard_package_use(facts)
        assert facts["h1"]["use_expand"]["VIDEO_CARDS"] == ["-*", "dummy", "intel"]
        # Existing use_expand values preserved
        assert facts["h1"]["use_expand"]["L10N"] == ["en"]
        # No plain flags leaked into global_use_flags
        assert "+VIDEO_CARDS:" not in facts["h1"].get("global_use_flags", [])
        assert "+dummy" not in facts["h1"].get("global_use_flags", [])

    def test_mixed_plain_and_use_expand(self):
        facts = {
            "h1": _make_host(
                "h1",
                ["gentoo"],
                package_use={"*/*": ["lto", "VIDEO_CARDS:", "dummy", "intel"]},
            ),
        }
        promote_wildcard_package_use(facts)
        assert "+lto" in facts["h1"]["global_use_flags"]
        assert facts["h1"]["use_expand"]["VIDEO_CARDS"] == ["dummy", "intel"]

    def test_no_wildcard_is_noop(self):
        facts = {
            "h1": _make_host("h1", ["gentoo"], global_use=["+X"]),
        }
        promote_wildcard_package_use(facts)
        assert facts["h1"]["global_use_flags"] == ["+X"]


# ---------------------------------------------------------------------------
# Integration: dry-run does not write files
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_writes_nothing(self, tmp_path, capsys):
        facts_dir = tmp_path / "facts"
        facts_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        hosts = [
            _make_host("h1", ["gentoo"], global_use=["nls"]),
            _make_host("h2", ["gentoo"], global_use=["nls"]),
        ]
        _write_facts(facts_dir, hosts)

        import collapse_use_flags as cuf

        facts = cuf.load_facts(facts_dir)
        all_hosts = sorted(facts.keys())
        group_map = cuf.build_group_map(facts)

        accumulator: dict = {}
        for fn in (
            cuf.collapse_global_use,
            cuf.collapse_use_expand,
            cuf.collapse_build_profile,
            cuf.collapse_package_use,
            cuf.collapse_make_conf,
            cuf.collapse_use_flag_types,
        ):
            a, _g, _h = fn(facts, group_map, all_hosts)
            accumulator = cuf._deep_merge(accumulator, a)

        out = output_dir / "group_vars" / "all" / "use_flags.yml"
        cuf._write_yaml(out, accumulator, dry_run=True, update=False)

        assert not out.exists()
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
