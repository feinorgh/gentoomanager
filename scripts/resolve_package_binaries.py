"""
resolve_package_binaries.py — Post-processor for Ansible binary discovery runs.

Reads per-host discovery YAML files from benchmarks/package_discoveries/,
applies consensus/flap detection, and updates:
  - roles/provision_benchmarks/vars/package_mappings.yml  (stable, family-level)
  - roles/provision_benchmarks/vars/package_mappings_variants.yml  (flapping, version-level)

Usage:
    uv run python scripts/resolve_package_binaries.py \
        benchmarks/package_discoveries/ \
        roles/provision_benchmarks/vars/package_mappings.yml \
        roles/provision_benchmarks/vars/package_mappings_variants.yml
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def load_discoveries(discoveries_dir: Path) -> list[dict]:
    """Load all per-host discovery YAML files from a directory."""
    results = []
    for path in sorted(discoveries_dir.glob("*.yml")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and "discoveries" in data:
                results.append(data)
        except (OSError, yaml.YAMLError) as exc:
            print(f"  WARNING: skipping {path.name}: {exc}", file=sys.stderr)
    return results


def compute_consensus(discoveries: list[dict]) -> tuple[dict, dict]:
    """
    Given a list of per-host discovery dicts, compute stable and variant mappings.

    Returns:
        stable:   {os_family: {tool: {executable, package}}}
        variants: {f"{os_family}_{major_version}": {tool: {executable, package}}}
    """
    # family_tool -> list of (major_version, executable, package) from all hosts
    family_tool_data: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)

    for disc in discoveries:
        os_family = disc.get("os_family", "")
        major_version = str(disc.get("os_major_version", ""))
        for tool, data in disc.get("discoveries", {}).items():
            exe = data.get("executable")
            pkg = data.get("package", "")
            if exe:  # skip null/empty executables
                family_tool_data[(os_family, tool)].append((major_version, exe, pkg))

    stable: dict[str, dict] = defaultdict(dict)
    variants: dict[str, dict] = defaultdict(dict)
    flapping: set[tuple[str, str]] = set()

    for (os_family, tool), entries in family_tool_data.items():
        unique_executables = {exe for (_ignored_ver, exe, _ignored_pkg) in entries}
        if len(unique_executables) == 1:
            # Consensus across all versions of this family
            _ignored_ver, exe, pkg = entries[0]
            stable[os_family][tool] = {"executable": exe, "package": pkg}
        else:
            # Flapping — record per-version
            flapping.add((os_family, tool))
            for major_version, exe, pkg in entries:
                version_key = f"{os_family}_{major_version}"
                variants[version_key][tool] = {"executable": exe, "package": pkg}

    return dict(stable), dict(variants)


def merge_into_mappings(existing: dict, stable: dict) -> dict:
    """
    Merge stable mappings into existing package_mappings structure.
    Additive only — never removes or overwrites existing entries.

    existing: content of package_mappings.yml
    stable:   {os_family: {tool: {executable, package}}}
    Returns: updated copy of existing
    """
    result = existing.copy()
    overrides = result.setdefault("provision_benchmarks_mappings_overrides", {})
    for os_family, tools in stable.items():
        family_map = overrides.setdefault(os_family, {})
        for tool, mapping in tools.items():
            if tool not in family_map:
                family_map[tool] = mapping
    return result


def merge_into_variants(existing: dict, variants: dict) -> dict:
    """
    Merge variant mappings into existing package_mappings_variants structure.
    Additive only.

    existing: content of package_mappings_variants.yml
    variants: {version_key: {tool: {executable, package}}}
    Returns: updated copy of existing
    """
    result = existing.copy()
    var_map = result.setdefault("package_mappings_variants", {})
    for version_key, tools in variants.items():
        version_map = var_map.setdefault(version_key, {})
        for tool, mapping in tools.items():
            version_map[tool] = mapping
    return result


def load_yaml_or_empty(path: Path, root_key: str) -> dict:
    """Load a YAML file, returning {root_key: {}} if absent or empty."""
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {root_key: {}}
    return {root_key: {}}


def write_yaml(path: Path, data: dict) -> None:
    """Write data to a YAML file with a leading --- separator."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n")
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve package binaries from discovery files.")
    parser.add_argument(
        "discoveries_dir", type=Path, help="Directory containing per-host discovery YAML files"
    )
    parser.add_argument("mappings_file", type=Path, help="Path to package_mappings.yml")
    parser.add_argument("variants_file", type=Path, help="Path to package_mappings_variants.yml")
    args = parser.parse_args()

    discoveries_dir: Path = args.discoveries_dir
    if not discoveries_dir.exists():
        print(f"  INFO: No discoveries directory at {discoveries_dir} — nothing to process.")
        return 0

    discoveries = load_discoveries(discoveries_dir)
    if not discoveries:
        print("  INFO: No discovery files found — nothing to process.")
        return 0

    print(f"\n📦 Processing {len(discoveries)} discovery file(s)...")

    stable, variants = compute_consensus(discoveries)

    # Update package_mappings.yml
    existing_mappings = load_yaml_or_empty(
        args.mappings_file, "provision_benchmarks_mappings_overrides"
    )
    updated_mappings = merge_into_mappings(existing_mappings, stable)
    new_entries = sum(
        1
        for fam, tools in stable.items()
        for tool in tools
        if tool
        not in existing_mappings.get("provision_benchmarks_mappings_overrides", {}).get(fam, {})
    )
    if new_entries:
        write_yaml(args.mappings_file, updated_mappings)
        print(f"  ✅ {new_entries} new stable mapping(s) written to {args.mappings_file}")
    else:
        print("  ✅ No new stable mappings (all already known or no consensus reached)")

    # Update package_mappings_variants.yml
    existing_variants = load_yaml_or_empty(args.variants_file, "package_mappings_variants")
    if variants:
        updated_variants = merge_into_variants(existing_variants, variants)
        write_yaml(args.variants_file, updated_variants)
        flap_count = sum(len(t) for t in variants.values())
        print(f"  ⚠️  {flap_count} flapping mapping(s) written to {args.variants_file}:")
        for version_key, tools in sorted(variants.items()):
            for tool, mapping in sorted(tools.items()):
                print(f"     {version_key}/{tool}: {mapping['executable']!r}")
    else:
        print("  ✅ No flapping detected")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
