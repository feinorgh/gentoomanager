"""Generate Quarto host-detail pages from benchmark metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NA_VALUE = "n/a"
OPTIONAL_METADATA_FIELDS = (
    "os",
    "os_version",
    "os_family",
    "cpu_model",
    "march_native",
    "gentoo_profile",
    "common_flags",
    "cflags",
    "ldflags",
)

# Greek mythology names for host anonymization (deterministic order)
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


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_host_filename(hostname: str) -> str:
    return hostname.replace("/", "_").replace("\\", "_")


def canonical_host_slug(hostname: Any, fallback: str = "") -> str:
    """Build the canonical host slug used for page filenames and links."""
    preferred = _stringify(hostname)
    if preferred:
        return _safe_host_filename(preferred)
    fallback_label = _stringify(fallback)
    if fallback_label:
        return _safe_host_filename(fallback_label)
    return _safe_host_filename(NA_VALUE)


def _yaml_quoted(value: str) -> str:
    return json.dumps(value)


def _md_escape(value: str) -> str:
    return value.replace("|", r"\|")


def _anonymize_hostname(hostname: str, index: int) -> str:
    """Map hostname to a deterministic Greek mythology name."""
    return _GREEK_NAMES[index % len(_GREEK_NAMES)]


def host_link_markdown(hostname: str) -> str:
    """Render a markdown link to a host detail page."""
    label = _stringify(hostname)
    if not label:
        label = NA_VALUE
    file_stem = canonical_host_slug(label)
    return f"[{label}](hosts/{file_stem}.html)"


def parse_versions(values: list[str]) -> dict[str, str]:
    """Parse version entries formatted as ``key=value``."""
    parsed_versions: dict[str, str] = {}
    for raw_value in values:
        value = _stringify(raw_value)
        if "=" not in value:
            continue
        key, parsed = value.split("=", 1)
        clean_key = key.strip()
        clean_value = parsed.strip()
        if not clean_key:
            continue
        parsed_versions[clean_key] = clean_value or NA_VALUE
    return parsed_versions


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize host metadata and default missing optional values to ``"n/a"``."""
    normalized: dict[str, Any] = dict(metadata)

    hostname = _stringify(normalized.get("hostname", ""))
    normalized["hostname"] = hostname or NA_VALUE

    for field_name in OPTIONAL_METADATA_FIELDS:
        normalized_value = _stringify(normalized.get(field_name, ""))
        normalized[field_name] = normalized_value or NA_VALUE

    versions = normalized.get("versions", [])
    if isinstance(versions, list):
        normalized["versions"] = [str(value) for value in versions]
    else:
        normalized["versions"] = []

    normalized["parsed_versions"] = parse_versions(normalized["versions"])
    return normalized


def render_host_qmd(hostname: str, metadata: dict[str, Any]) -> str:
    """Render a deterministic Quarto document for a single host."""
    normalized = normalize_metadata(metadata)
    versions = normalized["parsed_versions"]

    identity_rows = [
        ("Hostname", normalized["hostname"]),
        ("Operating system", normalized["os"]),
        ("OS version", normalized["os_version"]),
        ("OS family", normalized["os_family"]),
    ]
    runtime_rows = [
        ("CPU model", normalized["cpu_model"]),
        ("-march=native", normalized["march_native"]),
    ]
    tuning_rows = [
        ("Gentoo profile", normalized["gentoo_profile"]),
        ("Common flags", normalized["common_flags"]),
        ("CFLAGS", normalized["cflags"]),
        ("LDFLAGS", normalized["ldflags"]),
    ]

    metadata_rows = []
    for key_name in sorted(normalized):
        if key_name == "parsed_versions":
            continue
        value = normalized[key_name]
        if isinstance(value, list):
            rendered_value = ", ".join(str(entry) for entry in value) if value else NA_VALUE
        elif isinstance(value, dict):
            rendered_value = json.dumps(value, sort_keys=True)
        else:
            rendered_value = _stringify(value) or NA_VALUE
        metadata_rows.append((key_name, rendered_value))

    lines = [
        "---",
        f"title: {_yaml_quoted(f'Host details: {hostname}')}",
        "format: html",
        "---",
        "",
        "## Identity and platform",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| {field} | {_md_escape(_stringify(value) or NA_VALUE)} |"
        for field, value in identity_rows
    )

    lines.extend(
        [
            "",
            "## Hardware and runtime",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    lines.extend(
        f"| {field} | {_md_escape(_stringify(value) or NA_VALUE)} |"
        for field, value in runtime_rows
    )

    lines.extend(
        [
            "",
            "## Build and tuning",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    lines.extend(
        f"| {field} | {_md_escape(_stringify(value) or NA_VALUE)} |" for field, value in tuning_rows
    )

    lines.extend(["", "## Tool versions", ""])
    if versions:
        lines.extend(["| Tool | Version |", "| --- | --- |"])
        for tool_name, tool_version in sorted(versions.items()):
            lines.append(
                f"| {_md_escape(tool_name)} | {_md_escape(_stringify(tool_version) or NA_VALUE)} |"
            )
    else:
        lines.append("No tool versions captured.")

    lines.extend(["", "## Full metadata dump", "", "| Key | Value |", "| --- | --- |"])
    lines.extend(
        f"| {_md_escape(key_name)} | {_md_escape(_stringify(value) or NA_VALUE)} |"
        for key_name, value in metadata_rows
    )
    lines.append("")

    return "\n".join(lines)


def generate_host_pages(
    results_dir: Path, output_dir: Path, anonymize_hosts: bool = True
) -> list[Path]:
    """Generate host detail ``.qmd`` pages from ``metadata.json`` files.
    
    Args:
        results_dir: Path to benchmarks/results directory
        output_dir: Path to docs/benchmarks-article/hosts output dir
        anonymize_hosts: If True, replace hostnames with Greek mythology names
    """
    results_root = Path(results_dir)
    output_root = Path(output_dir)
    if not results_root.exists():
        raise FileNotFoundError(f"'{results_root}' does not exist")
    if not results_root.is_dir():
        raise NotADirectoryError(f"'{results_root}' is not a directory")

    output_root.mkdir(parents=True, exist_ok=True)

    generated_pages: list[Path] = []
    generated_names: set[str] = set()
    output_to_host_map: dict[str, str] = {}
    
    # Build anonymization mapping if requested
    host_dirs = sorted(path for path in results_root.iterdir() if path.is_dir())
    anon_mapping: dict[str, str] = {}
    if anonymize_hosts:
        for idx, host_dir in enumerate(host_dirs):
            metadata_path = host_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(metadata, dict):
                continue
            host_name = _stringify(metadata.get("hostname", "")) or host_dir.name
            anon_mapping[host_name] = _anonymize_hostname(host_name, idx)

    for idx, host_dir in enumerate(host_dirs):
        metadata_path = host_dir / "metadata.json"
        if not metadata_path.exists():
            continue

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(metadata, dict):
            continue

        host_name = _stringify(metadata.get("hostname", "")) or host_dir.name
        
        # Apply anonymization if requested
        display_name = host_name
        if anonymize_hosts and host_name in anon_mapping:
            display_name = anon_mapping[host_name]
            metadata = {**metadata, "hostname": display_name}
        
        normalized = normalize_metadata({**metadata, "hostname": display_name})
        safe_name = canonical_host_slug(display_name, fallback=host_dir.name)
        output_path = output_root / f"{safe_name}.qmd"

        previous_host = output_to_host_map.get(output_path.name)
        if previous_host is not None and previous_host != display_name:
            raise ValueError(
                "Filename collision for host detail page "
                f"'{output_path.name}' between '{previous_host}' and '{display_name}'"
            )

        output_text = render_host_qmd(display_name, normalized)
        output_path.write_text(output_text, encoding="utf-8")
        generated_pages.append(output_path)
        generated_names.add(output_path.name)
        output_to_host_map[output_path.name] = display_name

    for existing_page in sorted(output_root.glob("*.qmd")):
        if existing_page.name not in generated_names:
            existing_page.unlink()

    return generated_pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate host detail Quarto pages from benchmark metadata"
    )
    parser.add_argument(
        "--results",
        dest="results_dir_opt",
        type=Path,
        help="Path to benchmarks/results directory",
    )
    parser.add_argument(
        "--output",
        dest="output_dir_opt",
        type=Path,
        help="Path to docs/benchmarks-article/hosts output dir",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        default=True,
        help="Replace hostnames with Greek mythology names (default: true)",
    )
    parser.add_argument(
        "--no-anonymize",
        dest="anonymize",
        action="store_false",
        help="Use real hostnames (development only)",
    )
    parser.add_argument("results_dir", type=Path, nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("output_dir", type=Path, nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()

    results_dir = args.results_dir_opt or args.results_dir
    output_dir = args.output_dir_opt or args.output_dir
    if results_dir is None or output_dir is None:
        parser.error("provide both --results and --output (or two positional paths)")

    try:
        pages = generate_host_pages(results_dir, output_dir, anonymize_hosts=args.anonymize)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError) as exc:
        print(
            "Error: Unable to read results directory "
            f"'{results_dir}': {exc}. "
            "Use --results with a readable benchmarks results directory.",
            file=sys.stderr,
        )
        return 1

    anon_status = " (anonymized)" if args.anonymize else " (real hostnames)"
    print(f"Generated {len(pages)} host detail page(s){anon_status} in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
