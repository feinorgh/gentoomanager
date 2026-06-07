#!/usr/bin/env python3
"""Helpers for loading benchmark JSON into article-friendly row data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _parse_versions(values: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        key, parsed = value.split("=", 1)
        versions[key.strip()] = parsed.strip()
    return versions


def extract_gentoo_tuning(metadata: dict[str, Any]) -> dict[str, bool]:
    """Extract booleans describing Gentoo tuning choices from metadata flags."""
    flag_text = " ".join(
        [
            str(metadata.get("common_flags", "")),
            str(metadata.get("cflags", "")),
            str(metadata.get("ldflags", "")),
        ]
    ).lower()
    return {
        "lto_enabled": ("-flto" in flag_text) or ("lto" in flag_text),
        "pgo_enabled": ("-fprofile-use" in flag_text) or ("-fprofile-generate" in flag_text),
        "graphite_enabled": "-fgraphite" in flag_text,
    }


def _iter_hyperfine_rows(category: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bench in payload.get("results", []):
        command = str(bench.get("command", "")).strip()
        if not command:
            continue
        rows.append(
            {
                "category": category,
                "benchmark": command,
                "mean_s": float(bench.get("mean", 0.0)),
                "stddev_s": float(bench.get("stddev", 0.0)),
            }
        )
    return rows


def load_benchmark_rows(results_dir: Path) -> list[dict[str, Any]]:
    """Load long-form benchmark rows from benchmarks/results/<host>/*.json."""
    rows: list[dict[str, Any]] = []
    for host_dir in sorted(path for path in results_dir.iterdir() if path.is_dir()):
        metadata_file = host_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            metadata = json.loads(metadata_file.read_text())
        except json.JSONDecodeError:
            continue
        versions = _parse_versions(list(metadata.get("versions", [])))
        tuning = extract_gentoo_tuning(metadata)
        host_name = str(metadata.get("hostname", host_dir.name))

        for result_file in sorted(host_dir.glob("*.json")):
            if result_file.name in {"metadata.json", "benchmark_notes.json"}:
                continue
            try:
                payload = json.loads(result_file.read_text())
            except json.JSONDecodeError:
                continue
            category = result_file.stem
            if "results" not in payload:
                continue

            for bench_row in _iter_hyperfine_rows(category, payload):
                rows.append(
                    {
                        "host": host_name,
                        "os": metadata.get("os", "unknown"),
                        "os_family": metadata.get("os_family", "unknown"),
                        "gentoo_profile": metadata.get("gentoo_profile", ""),
                        "common_flags": metadata.get("common_flags", ""),
                        "cflags": metadata.get("cflags", ""),
                        "ldflags": metadata.get("ldflags", ""),
                        "tool_versions": versions,
                        **tuning,
                        **bench_row,
                    }
                )

    return rows
