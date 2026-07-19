#!/usr/bin/env python3
"""Validate short benchmark JSON outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHORT_RESULT_FILES = {
    "bash.json",
    "coreutils.json",
    "git.json",
    "compiler_rust_runtime.json",
    "compiler_rust_external.json",
}


def _iter_host_result_dirs(results_root: Path) -> list[Path]:
    return sorted(path for path in results_root.iterdir() if path.is_dir())


def _nonzero_exit_codes(result: dict[str, object]) -> list[int]:
    exit_codes = result.get("exit_codes")
    if not isinstance(exit_codes, list):
        return []
    return [code for code in exit_codes if isinstance(code, int) and code != 0]


def _discover_short_result_files(host_result_dir: Path) -> set[str]:
    discovered: set[str] = set()
    for path in host_result_dir.iterdir():
        if path.is_file() and path.name in SHORT_RESULT_FILES:
            discovered.add(path.name)
    return discovered


def validate(results_root: Path, required_files: set[str] | None = None) -> list[str]:
    failures: list[str] = []
    required_files = required_files or set()
    if not results_root.exists() or not results_root.is_dir():
        return [f"{results_root}: results directory does not exist"]

    host_result_dirs = _iter_host_result_dirs(results_root)
    if not host_result_dirs:
        return [f"{results_root}: no host result directories found"]

    for host_result_dir in host_result_dirs:
        result_files_to_validate = _discover_short_result_files(host_result_dir) | required_files
        for result_filename in sorted(result_files_to_validate):
            result_file = host_result_dir / result_filename
            if not result_file.is_file():
                failures.append(f"{host_result_dir}: missing expected file {result_filename}")
                continue

            try:
                payload = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                failures.append(f"{result_file}: unable to read/parse JSON ({error})")
                continue

            results = payload.get("results")
            if not isinstance(results, list):
                failures.append(f"{result_file}: missing 'results' array")
                continue
            if not results:
                failures.append(f"{result_file}: results array is empty")
                continue

            for index, bench_result in enumerate(results):
                if not isinstance(bench_result, dict):
                    failures.append(f"{result_file}: results[{index}] is not an object")
                    continue
                nonzero_exit_codes = _nonzero_exit_codes(bench_result)
                if nonzero_exit_codes:
                    command_name = bench_result.get("command", f"index {index}")
                    failures.append(
                        f"{result_file}: command {command_name!r} has non-zero exit codes "
                        f"{nonzero_exit_codes}"
                    )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--required-file", action="append", default=[])
    args = parser.parse_args()

    failures = validate(args.results_root, required_files=set(args.required_file))
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1

    print("[OK] Short benchmark exit-code validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
