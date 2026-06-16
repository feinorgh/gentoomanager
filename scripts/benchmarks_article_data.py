"""Helpers for loading benchmark JSON into article-friendly row data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_GREEK_NAMES = [
    "Zeus",
    "Hera",
    "Poseidon",
    "Demeter",
    "Athena",
    "Apollo",
    "Artemis",
    "Ares",
    "Aphrodite",
    "Hephaestus",
    "Hermes",
    "Hestia",
    "Dionysus",
    "Persephone",
    "Hades",
    "Prometheus",
    "Achilles",
    "Odysseus",
    "Heracles",
    "Perseus",
    "Theseus",
    "Orpheus",
    "Icarus",
    "Minos",
    "Medea",
    "Cassandra",
    "Electra",
    "Antigone",
    "Andromeda",
    "Atalanta",
    "Calypso",
    "Circe",
    "Daphne",
    "Echo",
    "Eurydice",
    "Galatea",
    "Hecate",
    "Iris",
    "Penelope",
    "Selene",
    "Pandora",
    "Psyche",
    "Ariadne",
    "Phaedra",
    "Niobe",
    "Io",
    "Thetis",
    "Nemesis",
    "Tyche",
    "Nike",
]

_MARCH_TO_CODENAME = {
    "skylake": "Coffee Lake",
    "skylake-avx512": "Skylake-X",
    "cascadelake": "Cascade Lake",
    "icelake-client": "Ice Lake",
    "icelake-server": "Ice Lake",
    "tigerlake": "Tiger Lake",
    "alderlake": "Alder Lake",
    "znver1": "Zen 1",
    "znver2": "Zen 2",
    "znver3": "Zen 3",
    "znver4": "Zen 4",
}


def _translate_march_to_codename(march: str) -> str:
    """Translate GCC march value to human-readable CPU codename."""
    if not march:
        return "—"
    return _MARCH_TO_CODENAME.get(march.lower(), march)


def _build_os_label(os_name: str, os_version: str) -> str:
    if not os_name:
        return "unknown"
    if not os_version:
        return os_name
    return f"{os_name} {os_version}".strip()


def _parse_versions(values: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        key, parsed = value.split("=", 1)
        versions[key.strip()] = parsed.strip()
    return versions


def _safe_host_slug(hostname: str) -> str:
    return hostname.replace("/", "_").replace("\\", "_")


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
        "pgo_enabled": (
            metadata.get("pgo_enabled", False)
            or ("-fprofile-use" in flag_text)
            or ("-fprofile-generate" in flag_text)
        ),
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


def _build_host_alias_map(hostnames: list[str], anonymize_hosts: bool) -> dict[str, str]:
    if not anonymize_hosts:
        return {hostname: hostname for hostname in hostnames}
    return {
        hostname: _GREEK_NAMES[index % len(_GREEK_NAMES)]
        for index, hostname in enumerate(sorted(set(hostnames)))
    }


def load_benchmark_rows(results_dir: Path, anonymize_hosts: bool = True) -> list[dict[str, Any]]:
    """Load long-form benchmark rows from benchmarks/results/<host>/*.json."""
    rows: list[dict[str, Any]] = []
    hosts_with_metadata: list[tuple[Path, dict[str, Any]]] = []
    hostnames: list[str] = []
    for host_dir in sorted(path for path in results_dir.iterdir() if path.is_dir()):
        metadata_file = host_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            metadata = json.loads(metadata_file.read_text())
        except json.JSONDecodeError:
            continue
        hosts_with_metadata.append((host_dir, metadata))
        hostnames.append(str(metadata.get("hostname", host_dir.name)))

    host_alias_map = _build_host_alias_map(hostnames, anonymize_hosts)
    for host_dir, metadata in hosts_with_metadata:
        versions = _parse_versions(list(metadata.get("versions", [])))
        tuning = extract_gentoo_tuning(metadata)
        host_name = str(metadata.get("hostname", host_dir.name))
        host_slug = _safe_host_slug(host_name)
        host_alias = host_alias_map.get(host_name, host_name)
        os_name = str(metadata.get("os", "unknown"))
        os_version = str(metadata.get("os_version", ""))
        distro_label = metadata.get("distro_label", _build_os_label(os_name, os_version))

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
                        "host": host_alias,
                        "host_slug": host_slug,
                        "os": os_name,
                        "os_version": os_version,
                        "os_label": _build_os_label(os_name, os_version),
                        "distro_label": distro_label,
                        "os_family": metadata.get("os_family", "unknown"),
                        "gentoo_profile": metadata.get("gentoo_profile", ""),
                        "common_flags": metadata.get("common_flags", ""),
                        "cflags": metadata.get("cflags", ""),
                        "ldflags": metadata.get("ldflags", ""),
                        "cpu_model": metadata.get("cpu_model", "unknown"),
                        "march_native": metadata.get("march_native", ""),
                        "pgo_enabled": metadata.get("pgo_enabled", False),
                        "tool_versions": versions,
                        **tuning,
                        **bench_row,
                    }
                )

    return rows
