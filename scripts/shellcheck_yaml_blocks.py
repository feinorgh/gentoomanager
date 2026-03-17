#!/usr/bin/env python3
"""Run shellcheck on inline shell blocks embedded in Ansible YAML task files.

Jinja2 expressions are replaced with shell-safe placeholders so that
shellcheck can parse the scripts without false syntax errors.

Usage:
    python3 scripts/shellcheck_yaml_blocks.py [paths ...]

    Paths can be YAML files or directories (searched recursively).
    Defaults to roles/ and playbooks/ in the collection root.

Exit codes:
    0 — no shellcheck findings
    1 — one or more shellcheck findings
    2 — fatal error (shellcheck not found, etc.)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Jinja2 preprocessing
# ---------------------------------------------------------------------------

# Order matters: strip comments before blocks before variables.
_J2_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_J2_BLOCK = re.compile(r"\{%-?.*?-?%\}", re.DOTALL)
_J2_VAR = re.compile(r"\{\{.*?\}\}", re.DOTALL)

# Placeholder that is valid in any shell context (bare word, no quotes).
_PLACEHOLDER = "ANSIBLE_PLACEHOLDER"

# The same pattern used *before* YAML parsing to avoid flow-mapping errors
# when {{ expr }} appears as a bare YAML value (not inside a block scalar).
_J2_VAR_BARE = re.compile(r"\{\{[^}]*\}\}")


def _preprocess_for_yaml(content: str) -> str:
    """Replace Jinja2 constructs that would confuse the YAML parser."""
    content = re.sub(r"\{#[^#]*#\}", "", content)
    content = re.sub(r"\{%-?[^%]*-?%\}", "", content)
    # Bare {{ expr }} values make PyYAML treat them as flow mappings.
    content = _J2_VAR_BARE.sub(_PLACEHOLDER, content)
    return content


def _strip_jinja2(text: str) -> str:
    """Replace Jinja2 constructs in extracted shell text with shell-safe stubs."""
    text = _J2_COMMENT.sub("# j2:comment", text)
    # Control-flow tags: replace with a comment so surrounding shell is still
    # structurally valid (if/fi, for/done etc. are unaffected).
    text = _J2_BLOCK.sub("# j2:block", text)
    # Variable expressions: replace with a bare word placeholder.
    text = _J2_VAR.sub(_PLACEHOLDER, text)
    return text


# ---------------------------------------------------------------------------
# Shell block extraction
# ---------------------------------------------------------------------------

_SHELL_KEYS = {"shell", "ansible.builtin.shell"}
# Windows shell uses PowerShell syntax — skip it.
_SKIP_KEYS = {"ansible.windows.win_shell", "win_shell"}


def _extract_shell_content(task: dict) -> str | None:
    """Return the shell script string from a task dict, or None."""
    for key in _SKIP_KEYS:
        if key in task:
            return None
    for key in _SHELL_KEYS:
        if key not in task:
            continue
        val = task[key]
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            cmd = val.get("cmd") or val.get("_raw_params")
            if isinstance(cmd, str):
                return cmd
    return None


def extract_blocks(yaml_file: Path) -> list[tuple[str, str]]:
    """Return [(task_name, shell_script)] for every shell task in *yaml_file*."""
    try:
        raw = yaml_file.read_text(encoding="utf-8")
    except OSError:
        return []

    safe = _preprocess_for_yaml(raw)
    try:
        doc = yaml.safe_load(safe)
    except yaml.YAMLError:
        return []

    if not isinstance(doc, list):
        return []

    blocks: list[tuple[str, str]] = []
    for task in doc:
        if not isinstance(task, dict):
            continue
        content = _extract_shell_content(task)
        if content is None:
            continue
        name = str(task.get("name", "(unnamed task)"))
        blocks.append((name, _strip_jinja2(content)))
    return blocks


# ---------------------------------------------------------------------------
# shellcheck runner
# ---------------------------------------------------------------------------

# Checks that are always spurious for Jinja2-substituted scripts:
#   SC2154 — variable referenced but not assigned (our placeholder is undefined)
_SUPPRESS = ["SC2154"]


def run_shellcheck(script: str, shell: str = "bash") -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", encoding="utf-8", delete=False) as tmp:
        tmp.write(f"#!/usr/{shell}\n")
        tmp.write(script)
        tmp_path = tmp.name

    return subprocess.run(
        [
            "shellcheck",
            f"--shell={shell}",
            "--color=always",
            *[f"-e{code}" for code in _SUPPRESS],
            tmp_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def collect_yaml_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix in {".yml", ".yaml"}:
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.yml")) + sorted(p.rglob("*.yaml")))
    return [f for f in files if ".venv" not in f.parts and ".ansible" not in f.parts]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="YAML files or directories to scan (default: roles/ playbooks/)",
    )
    parser.add_argument(
        "--shell",
        default="bash",
        help="Shell dialect passed to shellcheck (default: bash)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colour in shellcheck output",
    )
    args = parser.parse_args(argv)

    # Verify shellcheck is available.
    try:
        subprocess.run(["shellcheck", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("ERROR: shellcheck not found on PATH", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    search_paths = args.paths or [repo_root / "roles", repo_root / "playbooks"]
    yaml_files = collect_yaml_files(search_paths)

    if not yaml_files:
        print("No YAML files found.", file=sys.stderr)
        return 0

    total_blocks = 0
    failed_blocks = 0

    for yaml_file in yaml_files:
        blocks = extract_blocks(yaml_file)
        if not blocks:
            continue
        total_blocks += len(blocks)
        for task_name, script in blocks:
            result = run_shellcheck(script, shell=args.shell)
            if result.returncode != 0:
                failed_blocks += 1
                rel = yaml_file.relative_to(repo_root)
                print(f"\n{'=' * 72}")
                print(f"  File : {rel}")
                print(f"  Task : {task_name}")
                print(f"{'=' * 72}")
                # Scrub the temp path from shellcheck output
                output = re.sub(r"/tmp/tmp\S+\.sh", f"{rel}:<task>", result.stdout)
                print(output, end="")

    print(f"\nshellcheck-yaml: {total_blocks} blocks checked, {failed_blocks} with findings.")
    return 1 if failed_blocks else 0


if __name__ == "__main__":
    sys.exit(main())
