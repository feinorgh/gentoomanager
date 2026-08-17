# Binary Resolution via Package Manager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate tool verification false negatives by (a) making verify.yml use mapped executable names, and (b) auto-discovering correct binary names via package manager queries, writing stable discoveries back to `package_mappings.yml`.

**Architecture:** verify.yml is fixed to look up executables from `_provision_benchmarks_package_mappings` instead of using raw tool names. A new Ansible task queries the package manager for any still-missing tool, writes per-host discovery YAML to localhost. A Python post-processor runs after the playbook, detects consensus vs. flapping across OS family versions, and updates `package_mappings.yml` and `package_mappings_variants.yml` accordingly.

**Tech Stack:** Ansible (YAML/Jinja2), Python 3 (PyYAML, pathlib, collections), pytest, bash

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `roles/provision_benchmarks/tasks/verify.yml` | Modify | Use mapped executable names; call query task for still-missing tools |
| `roles/provision_benchmarks/tasks/query_package_binaries.yml` | **Create** | Per-host package manager query; write discovery YAML to localhost |
| `roles/provision_benchmarks/vars/package_mappings_variants.yml` | **Create** | Auto-generated OS-version-specific overrides (initially empty) |
| `scripts/resolve_package_binaries.py` | **Create** | Consensus/flap logic; updates the two mapping YAML files |
| `scripts/provision_benchmarks.sh` | Modify | Call post-processor after playbook |
| `tests/unit/test_resolve_package_binaries.py` | **Create** | Unit tests for consensus logic |
| `.gitignore` | Modify | Ignore `benchmarks/package_discoveries/` |

---

## Task 1: Fix verify.yml to Use Mapped Executable Names

**Files:**
- Modify: `roles/provision_benchmarks/tasks/verify.yml:16-58`

The shell script currently checks `command -v {{ tool }}` using the raw category key (e.g., `diffutils`). It should use `_provision_benchmarks_package_mappings[tool].executable` and fall back to `tool` if no mapping exists.

- [ ] **Step 1.1: Open verify.yml and find the Linux verification shell block**

Run: `grep -n "command -v" roles/provision_benchmarks/tasks/verify.yml`

You will see lines like:
```
if ! command -v {{ tool }} >/dev/null 2>&1; then
```

- [ ] **Step 1.2: Replace the Linux shell block to use mapped executable names**

In `roles/provision_benchmarks/tasks/verify.yml`, find the "Verify essential tools are available" task's `cmd:` block. Replace each occurrence of the tool check pattern. The `cmd:` section that checks tools should change from:

```yaml
      {% for tool in cat_data.tools %}
      if ! command -v {{ tool }} >/dev/null 2>&1; then
        if [ -z "$missing_{{ cat_name }}" ]; then
          missing_{{ cat_name }}="{{ tool }}"
        else
          missing_{{ cat_name }}="$missing_{{ cat_name }},{{ tool }}"
        fi
      fi
      {% endfor %}
```

To:

```yaml
      {% for tool in cat_data.tools %}
      {% set exe = _provision_benchmarks_package_mappings.get(tool, {}).get('executable', tool) %}
      if ! command -v {{ exe }} >/dev/null 2>&1; then
        if [ -z "$missing_{{ cat_name }}" ]; then
          missing_{{ cat_name }}="{{ tool }}"
        else
          missing_{{ cat_name }}="$missing_{{ cat_name }},{{ tool }}"
        fi
      fi
      {% endfor %}
```

Note: the missing list still uses `{{ tool }}` (the canonical key) — only the `command -v` check uses the mapped executable name.

- [ ] **Step 1.3: Verify lint**

Run: `uv run ansible-lint roles/provision_benchmarks/tasks/verify.yml -q`
Expected: no output, exit 0.

- [ ] **Step 1.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/verify.yml
git commit -m "fix: use mapped executable name in verify.yml command -v checks

Look up each tool's executable in _provision_benchmarks_package_mappings
(with fallback to the tool name) so that e.g. 'diffutils' checks for
'diff', not for the non-existent 'diffutils' binary.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Write Unit Tests for the Python Post-Processor

**Files:**
- Create: `tests/unit/test_resolve_package_binaries.py`

Write tests BEFORE writing the implementation (TDD).

- [ ] **Step 2.1: Create the test file**

Create `tests/unit/test_resolve_package_binaries.py`:

```python
"""Unit tests for scripts/resolve_package_binaries.py consensus logic."""

import sys
from pathlib import Path
import pytest

# Allow importing from scripts/
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from resolve_package_binaries import compute_consensus, merge_into_mappings


DISCOVERIES_CONSENSUS = [
    {
        "hostname": "debian-debbie",
        "os_family": "debian",
        "os_major_version": "12",
        "discoveries": {
            "diffutils": {"package": "diffutils", "executable": "diff", "all_candidates": ["diff", "diff3"]},
        },
    },
    {
        "hostname": "ubuntu-faith",
        "os_family": "debian",
        "os_major_version": "22",
        "discoveries": {
            "diffutils": {"package": "diffutils", "executable": "diff", "all_candidates": ["diff", "diff3"]},
        },
    },
]

DISCOVERIES_FLAPPING = [
    {
        "hostname": "rhel8-nicole",
        "os_family": "redhat",
        "os_major_version": "8",
        "discoveries": {
            "somepackage": {"package": "somepackage", "executable": "tool-8", "all_candidates": ["tool-8"]},
        },
    },
    {
        "hostname": "rhel9-molly",
        "os_family": "redhat",
        "os_major_version": "9",
        "discoveries": {
            "somepackage": {"package": "somepackage", "executable": "tool-9", "all_candidates": ["tool-9"]},
        },
    },
]

DISCOVERIES_NULL = [
    {
        "hostname": "gentoo-gianna",
        "os_family": "gentoo",
        "os_major_version": "2",
        "discoveries": {
            "botan": {"package": "dev-libs/botan", "executable": None, "all_candidates": []},
        },
    },
]


def test_consensus_all_agree_promoted_to_stable():
    stable, variants = compute_consensus(DISCOVERIES_CONSENSUS)
    assert "debian" in stable
    assert stable["debian"]["diffutils"]["executable"] == "diff"
    assert stable["debian"]["diffutils"]["package"] == "diffutils"


def test_consensus_no_variant_when_all_agree():
    _ignored_stable, variants = compute_consensus(DISCOVERIES_CONSENSUS)
    # No flapping, so variants should be empty for debian
    for key in variants:
        assert not key.startswith("debian"), f"Unexpected debian variant: {key}"


def test_flapping_goes_to_variants_not_stable():
    stable, variants = compute_consensus(DISCOVERIES_FLAPPING)
    assert "redhat" not in stable
    assert "redhat_8" in variants
    assert "redhat_9" in variants
    assert variants["redhat_8"]["somepackage"]["executable"] == "tool-8"
    assert variants["redhat_9"]["somepackage"]["executable"] == "tool-9"


def test_null_executable_skipped():
    stable, variants = compute_consensus(DISCOVERIES_NULL)
    assert "gentoo" not in stable
    assert not any("gentoo" in k for k in variants)


def test_merge_stable_into_existing_mappings():
    existing = {
        "provision_benchmarks_mappings_overrides": {
            "debian": {
                "botan": {"executable": "botan", "package": "libbotan-3-dev"},
            }
        }
    }
    stable = {"debian": {"diffutils": {"executable": "diff", "package": "diffutils"}}}
    result = merge_into_mappings(existing, stable)
    overrides = result["provision_benchmarks_mappings_overrides"]
    # New mapping added
    assert overrides["debian"]["diffutils"]["executable"] == "diff"
    # Existing mapping preserved
    assert overrides["debian"]["botan"]["executable"] == "botan"


def test_merge_stable_does_not_overwrite_existing_with_same_value():
    existing = {
        "provision_benchmarks_mappings_overrides": {
            "debian": {
                "diffutils": {"executable": "diff", "package": "diffutils"},
            }
        }
    }
    stable = {"debian": {"diffutils": {"executable": "diff", "package": "diffutils"}}}
    result = merge_into_mappings(existing, stable)
    # Should not change anything
    assert result == existing


def test_single_host_counts_as_consensus():
    """One host with a successful discovery is enough to be stable (no contradiction)."""
    single = [
        {
            "hostname": "gentoo-gianna",
            "os_family": "gentoo",
            "os_major_version": "2",
            "discoveries": {
                "diffutils": {"package": "sys-apps/diffutils", "executable": "diff", "all_candidates": ["diff"]},
            },
        }
    ]
    stable, _ignored_variants = compute_consensus(single)
    assert "gentoo" in stable
    assert stable["gentoo"]["diffutils"]["executable"] == "diff"
```

- [ ] **Step 2.2: Run tests to confirm they fail (function not defined yet)**

Run: `uv run pytest tests/unit/test_resolve_package_binaries.py -v 2>&1 | head -20`

Expected: `ModuleNotFoundError: No module named 'resolve_package_binaries'`

- [ ] **Step 2.3: Commit failing tests**

```bash
git add tests/unit/test_resolve_package_binaries.py
git commit -m "tests: add unit tests for binary resolution post-processor

TDD: tests written before implementation. Covers:
- Consensus detection (all hosts agree → stable)
- Flapping detection (hosts disagree → variants per version)
- Null executable skipped (package installed but no binary found)
- Merge into existing mappings (additive, no overwrites)
- Single host counts as consensus

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Write the Python Post-Processor

**Files:**
- Create: `scripts/resolve_package_binaries.py`

- [ ] **Step 3.1: Create the script**

Create `scripts/resolve_package_binaries.py`:

```python
"""
resolve_package_binaries.py — Post-processor for Ansible binary discovery runs.

Reads per-host discovery YAML files from benchmarks/package_discoveries/,
applies consensus/flap detection, and updates:
  - roles/provision_benchmarks/vars/package_mappings.yml  (stable, family-level)
  - roles/provision_benchmarks/vars/package_mappings_variants.yml  (flapping, version-level)

Usage:
    uv run python scripts/resolve_package_binaries.py \\
        benchmarks/package_discoveries/ \\
        roles/provision_benchmarks/vars/package_mappings.yml \\
        roles/provision_benchmarks/vars/package_mappings_variants.yml
"""

import sys
import argparse
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
    """Write data to a YAML file with a warning header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n")
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve package binaries from discovery files.")
    parser.add_argument("discoveries_dir", type=Path, help="Directory containing per-host discovery YAML files")
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
    existing_mappings = load_yaml_or_empty(args.mappings_file, "provision_benchmarks_mappings_overrides")
    updated_mappings = merge_into_mappings(existing_mappings, stable)
    new_entries = sum(
        1 for fam, tools in stable.items()
        for tool in tools
        if tool not in existing_mappings.get("provision_benchmarks_mappings_overrides", {}).get(fam, {})
    )
    if new_entries:
        write_yaml(args.mappings_file, updated_mappings)
        print(f"  ✅ {new_entries} new stable mapping(s) written to {args.mappings_file}")
    else:
        print(f"  ✅ No new stable mappings (all already known or no consensus reached)")

    # Update package_mappings_variants.yml
    existing_variants = load_yaml_or_empty(args.variants_file, "package_mappings_variants")
    if variants:
        updated_variants = merge_into_variants(existing_variants, variants)
        write_yaml(args.variants_file, updated_variants)
        print(f"  ⚠️  {sum(len(t) for t in variants.values())} flapping mapping(s) written to {args.variants_file}:")
        for version_key, tools in sorted(variants.items()):
            for tool, mapping in sorted(tools.items()):
                print(f"     {version_key}/{tool}: {mapping['executable']!r}")
    else:
        print("  ✅ No flapping detected")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.2: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_resolve_package_binaries.py -v`

Expected:
```
test_resolve_package_binaries.py::test_consensus_all_agree_promoted_to_stable PASSED
test_resolve_package_binaries.py::test_consensus_no_variant_when_all_agree PASSED
test_resolve_package_binaries.py::test_flapping_goes_to_variants_not_stable PASSED
test_resolve_package_binaries.py::test_null_executable_skipped PASSED
test_resolve_package_binaries.py::test_merge_stable_into_existing_mappings PASSED
test_resolve_package_binaries.py::test_merge_stable_does_not_overwrite_existing_with_same_value PASSED
test_resolve_package_binaries.py::test_single_host_counts_as_consensus PASSED

====== 7 passed in X.XXs ======
```

- [ ] **Step 3.3: Run ruff check**

Run: `uv run ruff check scripts/resolve_package_binaries.py`
Expected: `All checks passed!`

- [ ] **Step 3.4: Commit**

```bash
git add scripts/resolve_package_binaries.py
git commit -m "feat: add resolve_package_binaries.py post-processor

Reads per-host discovery YAML files, applies consensus/flap detection:
- All hosts in a family agree → promoted to package_mappings.yml
- Any host in a family disagrees → written to package_mappings_variants.yml
  keyed by {os_family}_{major_version}
- Null executables (package installed but no binary found) are skipped
- Additive only: never removes existing manual entries

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Create Ansible Query Task File

**Files:**
- Create: `roles/provision_benchmarks/tasks/query_package_binaries.yml`

This task runs on each host after installation. It queries the package manager for each still-missing tool's package, filters for executables, and writes a per-host discovery YAML to localhost.

- [ ] **Step 4.1: Create the task file**

Create `roles/provision_benchmarks/tasks/query_package_binaries.yml`:

```yaml
---
# query_package_binaries.yml — Query OS package manager to discover actual
# binary names for tools that were not found during verification.
# Writes per-host discovery YAML to benchmarks/package_discoveries/ on localhost.
# Not run on Windows or NixOS (NixOS uses a separate task).

- name: Build flat list of missing tools with package names
  ansible.builtin.set_fact:
    _provision_benchmarks_missing_flat: >-
      {{ _provision_benchmarks_verify_missing
         | dict2items
         | map(attribute='value')
         | flatten
         | map('community.general.dict_kv', 'tool')
         | list
         | map('combine', {'package': ''})
         | list }}
  changed_when: false

- name: Resolve package names for missing tools
  ansible.builtin.set_fact:
    _provision_benchmarks_missing_flat: >-
      {{ _provision_benchmarks_missing_flat | map('combine', {
           'package': _provision_benchmarks_package_mappings.get(item.tool, {}).get('package', item.tool)
         }) | list }}
  loop: "{{ _provision_benchmarks_missing_flat }}"
  loop_control:
    loop_var: item
  changed_when: false

- name: Query package manager for binary candidates
  ansible.builtin.shell:
    cmd: |
      {% set pm_cmds = {
        'Gentoo':    'qlist',
        'Debian':    'dpkg -L',
        'RedHat':    'rpm -ql',
        'Archlinux': 'pacman -Ql',
        'Suse':      'rpm -ql',
        'FreeBSD':   'pkg info -l',
        'OpenBSD':   'pkg_info -L',
        'Void':      'xbps-query -f',
        'Solus':     'eopkg list-files',
        'Alpine':    'apk info -L',
      } %}
      {% set pm_base = pm_cmds.get(ansible_os_family, '') %}
      {% if pm_base %}
      FILES=$({{ pm_base }} {{ item.package }} 2>/dev/null) || true
      {% else %}
      FILES=""
      {% endif %}
      CANDIDATES=$(printf '%s\n' "$FILES" | grep -E '/(s?bin|libexec)/' | sed 's|.*/||' | sort -u)
      WINNER=""
      for cand in $CANDIDATES; do
          if command -v "$cand" >/dev/null 2>&1; then
              WINNER="$cand"
              break
          fi
      done
      printf 'TOOL:%s\nPACKAGE:%s\nCANDIDATES:%s\nEXECUTABLE:%s\n' \
        "{{ item.tool }}" \
        "{{ item.package }}" \
        "$(printf '%s\n' "$CANDIDATES" | tr '\n' ',' | sed 's/,$//')" \
        "$WINNER"
    executable: /bin/sh
  loop: "{{ _provision_benchmarks_missing_flat }}"
  loop_control:
    label: "{{ item.tool }}"
  register: _provision_benchmarks_binary_queries
  changed_when: false
  failed_when: false
  when:
    - ansible_system != "Windows"
    - ansible_os_family != "NixOS"
    - item.package | length > 0

- name: Parse binary query results into discoveries dict
  ansible.builtin.set_fact:
    _provision_benchmarks_discoveries: >-
      {{ _provision_benchmarks_discoveries | default({}) | combine({
           (result.stdout_lines | select('match', '^TOOL:') | first | replace('TOOL:', '')): {
             'package':      (result.stdout_lines | select('match', '^PACKAGE:')    | first | replace('PACKAGE:', '')),
             'executable':   (result.stdout_lines | select('match', '^EXECUTABLE:') | first | replace('EXECUTABLE:', '')) | default(None) | replace('', None) if (result.stdout_lines | select('match', '^EXECUTABLE:') | first | replace('EXECUTABLE:', '')) == '' else (result.stdout_lines | select('match', '^EXECUTABLE:') | first | replace('EXECUTABLE:', '')),
             'all_candidates': ((result.stdout_lines | select('match', '^CANDIDATES:') | first | replace('CANDIDATES:', '')).split(',') | reject('equalto', '') | list),
           }
         }) }}
  loop: "{{ _provision_benchmarks_binary_queries.results | default([]) }}"
  loop_control:
    loop_var: result
  when:
    - result.stdout_lines is defined
    - result.stdout_lines | length > 0
  changed_when: false

- name: Write per-host discovery file to localhost
  ansible.builtin.copy:
    content: |
      ---
      hostname: {{ inventory_hostname }}
      os_family: {{ ansible_os_family | lower }}
      os_major_version: "{{ ansible_distribution_major_version }}"
      timestamp: "{{ ansible_date_time.iso8601 }}"
      discoveries:
      {{ _provision_benchmarks_discoveries | default({}) | to_nice_yaml(indent=2) | indent(2) }}
    dest: "{{ playbook_dir }}/../benchmarks/package_discoveries/{{ inventory_hostname }}_{{ ansible_date_time.iso8601_basic_short }}.yml"
    mode: '0644'
  delegate_to: localhost
  when:
    - _provision_benchmarks_discoveries is defined
    - _provision_benchmarks_discoveries | length > 0
    - ansible_system != "Windows"
    - ansible_os_family != "NixOS"
  changed_when: false
```

- [ ] **Step 4.2: Create the discoveries directory and add to .gitignore**

Run:
```bash
mkdir -p /home/pk/Devel/Ansible/local.gentoomanager/benchmarks/package_discoveries
echo "benchmarks/package_discoveries/" >> .gitignore
```

- [ ] **Step 4.3: Verify lint**

Run: `uv run ansible-lint roles/provision_benchmarks/tasks/query_package_binaries.yml -q`
Expected: no errors.

- [ ] **Step 4.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/query_package_binaries.yml .gitignore benchmarks/
git commit -m "feat: add query_package_binaries.yml Ansible task

For each tool still missing after static-mapping verification, queries
the OS package manager to discover actual binary names by filtering
package file lists for bin/sbin/libexec executables.

Supports: Gentoo (qlist), Debian (dpkg -L), RedHat (rpm -ql),
Archlinux (pacman -Ql), Suse (rpm -ql), FreeBSD (pkg info -l),
OpenBSD (pkg_info -L), Void (xbps-query -f), Solus (eopkg list-files),
Alpine (apk info -L). NixOS and Windows handled separately.

Writes per-host discovery YAML to benchmarks/package_discoveries/
(gitignored) via delegate_to: localhost.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Add NixOS Configuration Check Task

**Files:**
- Modify: `roles/provision_benchmarks/tasks/os/nixos.yml`

- [ ] **Step 5.1: View current nixos.yml**

Run: `cat roles/provision_benchmarks/tasks/os/nixos.yml`

Note the last task (should be `include_tasks: verify.yml`).

- [ ] **Step 5.2: Add NixOS config check task before verify include**

In `roles/provision_benchmarks/tasks/os/nixos.yml`, add before `include_tasks: verify.yml`:

```yaml
- name: Check NixOS configuration.nix for missing packages
  ansible.builtin.shell:
    cmd: |
      CONFIG="/etc/nixos/configuration.nix"
      if [ ! -f "$CONFIG" ]; then
        echo "NIXOS_CONFIG_MISSING:true"
        exit 0
      fi
      # Extract package names after pkgs. (simple grep; handles most patterns)
      CONFIGURED=$(grep -oE 'pkgs\.[a-zA-Z0-9_-]+' "$CONFIG" | sed 's/pkgs\.//' | sort -u)
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      {% for tool in cat_data.tools %}
      {% set pkg = _provision_benchmarks_package_mappings.get(tool, {}).get('package', tool) %}
      if printf '%s\n' "$CONFIGURED" | grep -qxF "{{ pkg }}"; then
        echo "NIXOS_CONFIGURED:{{ tool }}:{{ pkg }}"
      else
        echo "NIXOS_MISSING:{{ tool }}:{{ pkg }}"
      fi
      {% endfor %}
      {% endfor %}
    executable: /bin/sh
  register: _provision_benchmarks_nixos_check
  changed_when: false
  failed_when: false
  when: ansible_os_family == "NixOS"

- name: Warn about packages missing from NixOS configuration.nix
  ansible.builtin.debug:
    msg: >-
      NixOS: The following packages are not in environment.systemPackages in
      /etc/nixos/configuration.nix. Add them and run 'nixos-rebuild switch':
      {{ _provision_benchmarks_nixos_check.stdout_lines
         | select('match', '^NIXOS_MISSING:')
         | map('replace', 'NIXOS_MISSING:', '')
         | list | join(', ') }}
  when:
    - ansible_os_family == "NixOS"
    - _provision_benchmarks_nixos_check is defined
    - _provision_benchmarks_nixos_check.stdout_lines | select('match', '^NIXOS_MISSING:') | list | length > 0
  changed_when: false

- name: Write NixOS discovery file to localhost
  ansible.builtin.copy:
    content: |
      ---
      hostname: {{ inventory_hostname }}
      os_family: nixos
      os_major_version: "{{ ansible_distribution_major_version }}"
      timestamp: "{{ ansible_date_time.iso8601 }}"
      discoveries:
      {% for line in _provision_benchmarks_nixos_check.stdout_lines | default([]) %}
      {% if line.startswith('NIXOS_CONFIGURED:') %}
      {% set parts = line.replace('NIXOS_CONFIGURED:', '').split(':') %}
        {{ parts[0] }}:
          package: "{{ parts[1] }}"
          executable: null
          all_candidates: []
      {% endif %}
      {% endfor %}
    dest: "{{ playbook_dir }}/../benchmarks/package_discoveries/{{ inventory_hostname }}_{{ ansible_date_time.iso8601_basic_short }}.yml"
    mode: '0644'
  delegate_to: localhost
  when:
    - ansible_os_family == "NixOS"
    - _provision_benchmarks_nixos_check is defined
  changed_when: false
```

- [ ] **Step 5.3: Lint**

Run: `uv run ansible-lint roles/provision_benchmarks/tasks/os/nixos.yml -q`

- [ ] **Step 5.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/os/nixos.yml
git commit -m "feat: add NixOS configuration.nix package check

Parse /etc/nixos/configuration.nix for environment.systemPackages.
Warn about packages missing from the config with instructions to
add them and run 'nixos-rebuild switch'.

Writes a discovery file to localhost with configured packages
(executable resolution via command -v still applies normally).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Hook Query Task into verify.yml

**Files:**
- Modify: `roles/provision_benchmarks/tasks/verify.yml`

After the verification shell runs and missing tools are parsed, call `query_package_binaries.yml` to discover binary names for any still-missing tools.

- [ ] **Step 6.1: Locate the end of verify.yml before the report include**

Run: `grep -n "include_tasks\|include report" roles/provision_benchmarks/tasks/verify.yml`

You will see the final task is `include_tasks: generate_verification_report.yml`.

- [ ] **Step 6.2: Add query task include before report generation**

In `roles/provision_benchmarks/tasks/verify.yml`, just before the `Include report generation` task, add:

```yaml
- name: Query package manager for still-missing tool binary names
  ansible.builtin.include_tasks: query_package_binaries.yml
  when:
    - ansible_system != "Windows"
    - _provision_benchmarks_verify_missing | dict2items | map(attribute='value') | flatten | length > 0
```

- [ ] **Step 6.3: Lint**

Run: `uv run ansible-lint roles/provision_benchmarks/tasks/verify.yml -q`

- [ ] **Step 6.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/verify.yml
git commit -m "feat: call query_package_binaries.yml from verify.yml

After static-mapping verification, if any tools are still missing,
run the package manager query to discover their actual binary names.
Only runs on non-Windows hosts and when there are missing tools.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Load Variants File in verify.yml

**Files:**
- Create: `roles/provision_benchmarks/vars/package_mappings_variants.yml`
- Modify: `roles/provision_benchmarks/tasks/verify.yml`

- [ ] **Step 7.1: Create empty variants file**

Create `roles/provision_benchmarks/vars/package_mappings_variants.yml`:

```yaml
---
# Auto-generated by scripts/resolve_package_binaries.py
# Contains OS-version-specific package binary overrides where OS family-level
# consensus could not be reached (flapping between major versions).
# Key format: {ansible_os_family | lower}_{ansible_distribution_major_version}
# This file is managed automatically — manual edits may be overwritten.

package_mappings_variants: {}
```

- [ ] **Step 7.2: Add variants load and merge to verify.yml**

In `roles/provision_benchmarks/tasks/verify.yml`, update the "Load package mapping overrides" section to also load variants and apply version-specific overrides. Replace the first two tasks with:

```yaml
---
- name: Load package mapping overrides
  ansible.builtin.include_vars:
    file: "{{ role_path }}/vars/package_mappings.yml"

- name: Load package mapping variants
  ansible.builtin.include_vars:
    file: "{{ role_path }}/vars/package_mappings_variants.yml"

- name: Ensure package mappings are loaded with variant overrides
  ansible.builtin.set_fact:
    _provision_benchmarks_package_mappings: >-
      {{ package_mappings_defaults
         | combine(provision_benchmarks_mappings_overrides.get(ansible_os_family | lower, {}))
         | combine(package_mappings_variants.get(
             ansible_os_family | lower ~ '_' ~ ansible_distribution_major_version, {})) }}
```

This merge priority: defaults → family overrides → version-specific variants.

- [ ] **Step 7.3: Lint**

Run: `uv run ansible-lint roles/provision_benchmarks/tasks/verify.yml -q`

- [ ] **Step 7.4: Commit**

```bash
git add roles/provision_benchmarks/vars/package_mappings_variants.yml
git add roles/provision_benchmarks/tasks/verify.yml
git commit -m "feat: load package_mappings_variants.yml with higher merge priority

Load the auto-generated variants file and merge it on top of the
family-level overrides, so {os_family}_{major_version}-specific
mappings take precedence over broader family mappings.

Create empty package_mappings_variants.yml as the initial state.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Integrate Post-Processor into provision_benchmarks.sh

**Files:**
- Modify: `scripts/provision_benchmarks.sh`

- [ ] **Step 8.1: Find where runs complete in provision_benchmarks.sh**

Run: `grep -n "run_ansible_with_output_filter\|exit 0" scripts/provision_benchmarks.sh | tail -10`

You will see the final `run_ansible_with_output_filter "${CMD[@]}"` call before the script ends.

- [ ] **Step 8.2: Add post-processor call after successful runs**

The script has two exit paths: serial mode (loop exits with `exit 0`) and non-serial (falls through to the final `run_ansible_with_output_filter` call). Add a helper function at the top of the script (after the existing functions) and call it from both paths.

Add this function after the other function definitions (look for `require_cmd`, `die`, etc.):

```bash
run_binary_resolver() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "  WARNING: uv not found — skipping binary resolution post-processor" >&2
    return 0
  fi
  echo "" >&2
  echo "▶ Running binary resolution post-processor..." >&2
  uv run python "${REPO_ROOT}/scripts/resolve_package_binaries.py" \
    "${REPO_ROOT}/benchmarks/package_discoveries/" \
    "${REPO_ROOT}/roles/provision_benchmarks/vars/package_mappings.yml" \
    "${REPO_ROOT}/roles/provision_benchmarks/vars/package_mappings_variants.yml"
}
```

Then in the serial path, change:
```bash
    run_ansible_with_output_filter "${CMD[@]}" --limit "${batch_limit}"
    batch_start=$(( batch_start + SERIAL_N ))
done
exit 0
```
To:
```bash
    run_ansible_with_output_filter "${CMD[@]}" --limit "${batch_limit}"
    batch_start=$(( batch_start + SERIAL_N ))
done
run_binary_resolver
exit 0
```

And at the non-serial end, after the final `run_ansible_with_output_filter "${CMD[@]}"`, add:
```bash
run_binary_resolver
```

- [ ] **Step 8.3: Verify bash syntax and shellcheck**

Run:
```bash
bash -n scripts/provision_benchmarks.sh && echo "✅ syntax OK"
shellcheck scripts/provision_benchmarks.sh && echo "✅ shellcheck OK"
```

- [ ] **Step 8.4: Commit**

```bash
git add scripts/provision_benchmarks.sh
git commit -m "feat: run resolve_package_binaries.py after provisioning

Automatically call the binary resolution post-processor after each
ansible-playbook run completes. Runs for both serial and non-serial
modes. Skipped with a warning if uv is not available.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Full Validation

**Files:**
- Test: all unit tests
- Integration: provision a single host

- [ ] **Step 9.1: Run the full test suite**

Run: `uv run pytest tests/unit/ -q`

Expected: all tests pass, 0 failures.

- [ ] **Step 9.2: Run linting**

Run:
```bash
uv run ansible-lint roles/provision_benchmarks/ -q && echo "✅ ansible-lint"
uv run ruff check scripts/ tests/ && echo "✅ ruff"
shellcheck scripts/*.sh && echo "✅ shellcheck"
```

All should pass.

- [ ] **Step 9.3: Test provision on a single Gentoo host**

Run:
```bash
scripts/provision_benchmarks.sh --verbose --manage-power --serial -- --limit gentoo-gianna
```

Watch for:
- Binary query tasks running after verification
- Post-processor output showing new mappings
- Fresh report showing `diff` as FOUND (not `diffutils`)

- [ ] **Step 9.4: Verify discovery file written**

Run: `ls benchmarks/package_discoveries/` — should show a `.yml` file for `gentoo-gianna`.

- [ ] **Step 9.5: Verify package_mappings.yml updated**

Run:
```bash
python -c "
import yaml
with open('roles/provision_benchmarks/vars/package_mappings.yml') as f:
    d = yaml.safe_load(f)
print(d['provision_benchmarks_mappings_overrides'].get('gentoo', {}))
"
```

Should show `diffutils: {executable: diff, package: ...}` if the host provided consensus.

- [ ] **Step 9.6: Commit final state**

```bash
git add .
git commit -m "chore: validate binary resolution on gentoo-gianna

Binary resolution working end-to-end:
- verify.yml uses mapped executables (diff not diffutils)
- package manager query finds diff as the binary for diffutils
- post-processor writes stable mapping to package_mappings.yml
- verification report shows correct tool names

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-Review Against Spec

**Spec coverage:**
- ✅ Try static mapping first (Task 1: verify.yml uses `_provision_benchmarks_package_mappings[tool].executable`)
- ✅ If not found, query package manager (Task 4: `query_package_binaries.yml`)
- ✅ Write stable discoveries to `package_mappings.yml` (Task 3: post-processor)
- ✅ Flapping → `package_mappings_variants.yml` keyed by `{family}_{major_version}` (Task 3 + 7)
- ✅ Variants loaded at higher merge priority (Task 7)
- ✅ NixOS special case with config.nix parsing and warnings (Task 5)
- ✅ Wrapper auto-invokes post-processor (Task 8)
- ✅ Discoveries directory gitignored (Task 4)
- ✅ Additive only — existing manual entries never removed (Task 3: `merge_into_mappings`)
- ✅ Package not installed → omit from discovery file (Task 4: `failed_when: false`, empty output)
- ✅ Unit tests for consensus, flapping, null, merge, single-host (Task 2)

**No placeholders found** ✓
