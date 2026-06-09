"""CFLAGS analysis parser for benchmark data enrichment.

This module provides functions to parse and normalize CFLAGS from Gentoo
benchmark metadata, extracting key optimization dimensions like march_class,
opt_level, lto_mode, pgo_mode, and graphite_mode.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def normalize_flag_text(
    common_flags: str | None,
    cflags: str | None,
    ldflags: str | None,
) -> str:
    """Normalize flag text by joining and lowercasing.

    Args:
        common_flags: Common compiler flags or None.
        cflags: CFLAGS or None.
        ldflags: LDFLAGS or None.

    Returns:
        Normalized (lowercased) flag text with empty strings filtered out.
    """
    parts = []
    for flags in [common_flags, cflags, ldflags]:
        if flags:
            parts.append(flags)
    return " ".join(parts).lower()


def classify_march_class(flag_text: str) -> str:
    """Classify -march architecture type.

    Args:
        flag_text: Normalized flag text to analyze.

    Returns:
        One of: "native_like", "generic_like", "unknown".
    """
    if "-march=native" in flag_text or "-mtune=native" in flag_text:
        return "native_like"
    if "-march=x86-64" in flag_text or "-march=x86-64-v" in flag_text:
        return "generic_like"
    return "unknown"


def parse_opt_level(flag_text: str) -> str:
    """Parse optimization level from flags.

    Args:
        flag_text: Normalized flag text to analyze.

    Returns:
        One of: "O0", "O1", "O2", "O3", "Os", "Oz", "Ofast", "other", "unknown".
    """
    # Normalize to lowercase for matching
    flag_text = flag_text.lower()

    # Find all -O flags that are NOT part of linker flags (-Wl,...)
    # Split by -Wl to exclude linker-passed flags
    compiler_flags = flag_text.split("-wl")[0]

    matches = re.findall(r"-o[0-3szf]|fast", compiler_flags)
    if not matches:
        return "unknown"
    if len(matches) > 1:
        return "other"

    opt = matches[0]
    # Map normalized flag to standard form
    opt_map = {
        "-o0": "O0",
        "-o1": "O1",
        "-o2": "O2",
        "-o3": "O3",
        "-os": "Os",
        "-oz": "Oz",
        "-of": "Ofast",
        "fast": "Ofast",
    }
    return opt_map.get(opt, "other")


def parse_lto_mode(flag_text: str) -> str:
    """Parse LTO mode from flags.

    Args:
        flag_text: Normalized flag text to analyze.

    Returns:
        One of: "on", "auto", "thin", "off".
    """
    if "-flto=thin" in flag_text:
        return "thin"
    if "-flto=auto" in flag_text:
        return "auto"
    if "-flto" in flag_text:
        return "on"
    return "off"


def parse_pgo_mode(flag_text: str) -> str:
    """Parse PGO mode from flags.

    Args:
        flag_text: Normalized flag text to analyze.

    Returns:
        One of: "generate", "use", "both_or_other", "off".
    """
    has_generate = "-fprofile-generate" in flag_text
    has_use = "-fprofile-use" in flag_text
    if has_generate and has_use:
        return "both_or_other"
    if has_generate:
        return "generate"
    if has_use:
        return "use"
    return "off"


def parse_graphite_mode(flag_text: str) -> str:
    """Parse Graphite optimization mode from flags.

    Args:
        flag_text: Normalized flag text to analyze.

    Returns:
        One of: "on", "off".
    """
    if "-fgraphite-identity" in flag_text or "-fgraphite" in flag_text:
        return "on"
    return "off"


def enrich_gentoo_cflags_dimensions(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich dataframe with normalized CFLAGS dimensions for Gentoo rows.

    For each Gentoo OS row, parses the CFLAGS, common_flags, and ldflags
    columns to extract normalized dimensions:
    - march_class: "native_like", "generic_like", "unknown"
    - opt_level: "O0", "O1", "O2", "O3", "Os", "Oz", "Ofast", "other", "unknown"
    - lto_mode: "on", "auto", "thin", "off"
    - pgo_mode: "generate", "use", "both_or_other", "off"
    - graphite_mode: "on", "off"

    Non-Gentoo rows get "unknown" for all dimensions.

    Args:
        df: Input dataframe with columns: os, common_flags, cflags, ldflags.

    Returns:
        Copy of input dataframe with 5 new columns added.
    """
    enriched = df.copy()

    # Initialize dimension columns with "unknown"
    enriched["march_class"] = "unknown"
    enriched["opt_level"] = "unknown"
    enriched["lto_mode"] = "unknown"
    enriched["pgo_mode"] = "unknown"
    enriched["graphite_mode"] = "unknown"

    # Process Gentoo rows only
    gentoo_mask = enriched["os"] == "Gentoo"
    if not gentoo_mask.any():
        return enriched

    gentoo_indices = enriched[gentoo_mask].index
    for idx in gentoo_indices:
        row = enriched.loc[idx]
        # Normalize flags
        flag_text = normalize_flag_text(
            row.get("common_flags", ""),
            row.get("cflags", ""),
            row.get("ldflags", ""),
        )
        # Parse dimensions
        enriched.loc[idx, "march_class"] = classify_march_class(flag_text)
        enriched.loc[idx, "opt_level"] = parse_opt_level(flag_text)
        enriched.loc[idx, "lto_mode"] = parse_lto_mode(flag_text)
        enriched.loc[idx, "pgo_mode"] = parse_pgo_mode(flag_text)
        enriched.loc[idx, "graphite_mode"] = parse_graphite_mode(flag_text)

    return enriched
