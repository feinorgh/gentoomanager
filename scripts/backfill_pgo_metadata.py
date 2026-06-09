#!/usr/bin/env python3
"""Backfill pgo_enabled field in existing metadata.json files using host_vars."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def _check_pgo_in_host_vars(hostname: str, host_vars_dir: Path) -> bool:
    """Check if PGO is enabled for a host by reading its use_flags.yml."""
    host_use_flags = host_vars_dir / hostname / "use_flags.yml"
    if not host_use_flags.exists():
        return False

    try:
        data = yaml.safe_load(host_use_flags.read_text())
    except (yaml.YAMLError, OSError):
        return False

    if not data:
        return False

    # Check global_use_flags
    global_flags = data.get("global_use_flags", [])
    if isinstance(global_flags, list) and any("pgo" in str(flag) for flag in global_flags):
        return True

    # Check package_use
    package_use = data.get("package_use", {})
    if isinstance(package_use, dict):
        for _package, flags in package_use.items():
            if isinstance(flags, list) and any("pgo" in str(flag) for flag in flags):
                return True

    return False


def backfill_pgo(results_dir: Path, host_vars_dir: Path) -> int:
    """Backfill pgo_enabled in metadata.json files."""
    updated = 0
    errors = 0

    for host_dir in sorted(results_dir.iterdir()):
        if not host_dir.is_dir():
            continue

        metadata_file = host_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            metadata = json.loads(metadata_file.read_text())
        except json.JSONDecodeError:
            print(f"Error reading {metadata_file}", file=sys.stderr)
            errors += 1
            continue

        # Skip if pgo_enabled is already set
        if "pgo_enabled" in metadata:
            continue

        hostname = metadata.get("hostname", host_dir.name)
        pgo_enabled = _check_pgo_in_host_vars(hostname, host_vars_dir)

        metadata["pgo_enabled"] = pgo_enabled
        try:
            metadata_file.write_text(json.dumps(metadata, indent=2) + "\n")
            updated += 1
            status = "✓ PGO" if pgo_enabled else "  —"
            print(f"{status} {hostname}")
        except OSError as e:
            print(f"Error writing {metadata_file}: {e}", file=sys.stderr)
            errors += 1

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill pgo_enabled in metadata.json files")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("benchmarks/results"),
        help="Path to benchmarks/results directory",
    )
    parser.add_argument(
        "--host-vars-dir",
        type=Path,
        default=Path("host_vars"),
        help="Path to host_vars directory",
    )

    args = parser.parse_args()

    if not args.results_dir.exists():
        print(f"Error: {args.results_dir} not found", file=sys.stderr)
        sys.exit(1)

    if not args.host_vars_dir.exists():
        print(f"Error: {args.host_vars_dir} not found", file=sys.stderr)
        sys.exit(1)

    sys.exit(backfill_pgo(args.results_dir, args.host_vars_dir))
