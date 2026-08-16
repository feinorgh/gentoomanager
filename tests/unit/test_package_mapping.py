"""Unit tests for package mapping merge logic."""


def merge_mappings(defaults, overrides, platform):
    """
    Merge canonical defaults with OS-specific overrides.

    Args:
        defaults: package_mappings_defaults dict
        overrides: provision_benchmarks_mappings_overrides dict with per-platform mappings
        platform: target OS platform (e.g., 'freebsd', 'debian')

    Returns:
        dict: Merged mapping for the given platform
    """
    result = defaults.copy()
    if platform in overrides:
        result.update(overrides[platform])
    return result


# Test data
DEFAULTS = {
    "botan": {"executable": "botan", "package": "botan"},
    "xz": {"executable": "xz", "package": "xz"},
    "gcc": {"executable": "gcc", "package": "gcc"},
}

OVERRIDES = {
    "freebsd": {
        "botan": {"executable": "botan3", "package": "security/botan3"},
    },
    "debian": {
        "gcc": {"executable": "gcc", "package": "build-essential"},
    },
}


def test_defaults_applied_to_unknown_platform():
    """When platform has no overrides, return defaults unchanged."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "alpine")
    assert result["botan"]["executable"] == "botan"
    assert result["botan"]["package"] == "botan"
    assert result["xz"]["executable"] == "xz"
    assert result["gcc"]["executable"] == "gcc"


def test_platform_specific_override_applied():
    """When platform has overrides, they replace defaults for that tool."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    assert result["botan"]["executable"] == "botan3"
    assert result["botan"]["package"] == "security/botan3"
    assert result["xz"]["executable"] == "xz"
    assert result["gcc"]["executable"] == "gcc"


def test_partial_overrides_preserved():
    """Platform overrides do not affect tools without overrides."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "debian")
    assert result["gcc"]["package"] == "build-essential"
    assert result["botan"]["executable"] == "botan"
    assert result["xz"]["executable"] == "xz"


def test_multiple_platforms_isolated():
    """Merging for one platform does not affect others."""
    freebsd_result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    debian_result = merge_mappings(DEFAULTS, OVERRIDES, "debian")

    assert freebsd_result["botan"]["executable"] == "botan3"
    assert debian_result["botan"]["executable"] == "botan"


def test_empty_overrides_for_platform():
    """Platform with no entries in overrides falls back to defaults completely."""
    minimal_overrides = {
        "freebsd": {
            "botan": {
                "executable": "botan3",
                "package": "security/botan3",
            }
        }
    }
    result = merge_mappings(DEFAULTS, minimal_overrides, "redhat")
    assert result == DEFAULTS


def test_all_tools_present_after_merge():
    """After merge, all default tools are present even if only some are overridden."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    assert "botan" in result
    assert "xz" in result
    assert "gcc" in result
    assert len(result) == len(DEFAULTS)
