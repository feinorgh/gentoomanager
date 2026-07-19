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


def _iter_short_result_files(results_root: Path) -> list[Path]:
    return sorted(
        path
        for path in results_root.glob("*/*.json")
        if path.name in SHORT_RESULT_FILES
    )


def _nonzero_exit_codes(result: dict[str, object]) -> list[int]:
    exit_codes = result.get("exit_codes")
    if not isinstance(exit_codes, list):
        return []
    return [code for code in exit_codes if isinstance(code, int) and code != 0]


def validate(results_root: Path) -> list[str]:
    failures: list[str] = []
    for result_file in _iter_short_result_files(results_root):
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            failures.append(f"{result_file}: unable to read/parse JSON ({error})")
            continue

        results = payload.get("results", [])
        if not isinstance(results, list):
            failures.append(f"{result_file}: missing 'results' array")
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
    args = parser.parse_args()

    failures = validate(args.results_root)
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1

    print("[OK] Short benchmark exit-code validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
