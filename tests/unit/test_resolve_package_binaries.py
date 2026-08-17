"""Unit tests for scripts/resolve_package_binaries.py consensus logic."""

import sys
from pathlib import Path

# Allow importing from scripts/
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from resolve_package_binaries import compute_consensus, merge_into_mappings

DISCOVERIES_CONSENSUS = [
    {
        "hostname": "debian-debbie",
        "os_family": "debian",
        "os_major_version": "12",
        "discoveries": {
            "diffutils": {
                "package": "diffutils",
                "executable": "diff",
                "all_candidates": ["diff", "diff3"],
            },
        },
    },
    {
        "hostname": "ubuntu-faith",
        "os_family": "debian",
        "os_major_version": "22",
        "discoveries": {
            "diffutils": {
                "package": "diffutils",
                "executable": "diff",
                "all_candidates": ["diff", "diff3"],
            },
        },
    },
]

DISCOVERIES_FLAPPING = [
    {
        "hostname": "rhel8-nicole",
        "os_family": "redhat",
        "os_major_version": "8",
        "discoveries": {
            "somepackage": {
                "package": "somepackage",
                "executable": "tool-8",
                "all_candidates": ["tool-8"],
            },
        },
    },
    {
        "hostname": "rhel9-molly",
        "os_family": "redhat",
        "os_major_version": "9",
        "discoveries": {
            "somepackage": {
                "package": "somepackage",
                "executable": "tool-9",
                "all_candidates": ["tool-9"],
            },
        },
    },
]

DISCOVERIES_NULL = [
    {
        "hostname": "gentoo-gianna",
        "os_family": "gentoo",
        "os_major_version": "2",
        "discoveries": {
            "botan": {"package": "dev-libs/botan", "executable": None, "all_candidates": []},
        },
    },
]


def test_consensus_all_agree_promoted_to_stable():
    stable, variants = compute_consensus(DISCOVERIES_CONSENSUS)
    assert "debian" in stable
    assert stable["debian"]["diffutils"]["executable"] == "diff"
    assert stable["debian"]["diffutils"]["package"] == "diffutils"


def test_consensus_no_variant_when_all_agree():
    _ignored_stable, variants = compute_consensus(DISCOVERIES_CONSENSUS)
    # No flapping, so variants should be empty for debian
    for key in variants:
        assert not key.startswith("debian"), f"Unexpected debian variant: {key}"


def test_flapping_goes_to_variants_not_stable():
    stable, variants = compute_consensus(DISCOVERIES_FLAPPING)
    assert "redhat" not in stable
    assert "redhat_8" in variants
    assert "redhat_9" in variants
    assert variants["redhat_8"]["somepackage"]["executable"] == "tool-8"
    assert variants["redhat_9"]["somepackage"]["executable"] == "tool-9"


def test_null_executable_skipped():
    stable, variants = compute_consensus(DISCOVERIES_NULL)
    assert "gentoo" not in stable
    assert not any("gentoo" in k for k in variants)


def test_merge_stable_into_existing_mappings():
    existing = {
        "provision_benchmarks_mappings_overrides": {
            "debian": {
                "botan": {"executable": "botan", "package": "libbotan-3-dev"},
            }
        }
    }
    stable = {"debian": {"diffutils": {"executable": "diff", "package": "diffutils"}}}
    result = merge_into_mappings(existing, stable)
    overrides = result["provision_benchmarks_mappings_overrides"]
    # New mapping added
    assert overrides["debian"]["diffutils"]["executable"] == "diff"
    # Existing mapping preserved
    assert overrides["debian"]["botan"]["executable"] == "botan"


def test_merge_stable_does_not_overwrite_existing_with_same_value():
    existing = {
        "provision_benchmarks_mappings_overrides": {
            "debian": {
                "diffutils": {"executable": "diff", "package": "diffutils"},
            }
        }
    }
    stable = {"debian": {"diffutils": {"executable": "diff", "package": "diffutils"}}}
    result = merge_into_mappings(existing, stable)
    # Should not change anything
    assert result == existing


def test_single_host_counts_as_consensus():
    """One host with a successful discovery is enough to be stable (no contradiction)."""
    single = [
        {
            "hostname": "gentoo-gianna",
            "os_family": "gentoo",
            "os_major_version": "2",
            "discoveries": {
                "diffutils": {
                    "package": "sys-apps/diffutils",
                    "executable": "diff",
                    "all_candidates": ["diff"],
                },
            },
        }
    ]
    stable, _ignored_variants = compute_consensus(single)
    assert "gentoo" in stable
    assert stable["gentoo"]["diffutils"]["executable"] == "diff"
