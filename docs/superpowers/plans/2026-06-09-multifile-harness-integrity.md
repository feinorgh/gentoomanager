# Multifile Harness Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent `compiler_multifile` from producing deceptive near-zero results by enforcing required-tool preflight checks, hard-failing non-zero runs, and provisioning `make` correctly on affected OS families.

**Architecture:** Add guardrails directly in the multifile harness path (`roles/run_benchmarks/tasks/compiler.yml`) so failures are surfaced at runtime, not silently accepted. Back this with provisioning updates for NixOS and SUSE package sets to guarantee `make` availability. Add targeted unit tests that lock in the new behavior and prevent regressions.

**Tech Stack:** Ansible playbooks/roles (YAML + Jinja2), Python/pytest, ruff, jq.

---

## File Structure

- Modify: `roles/run_benchmarks/tasks/compiler.yml`
  - Add preflight checks and post-run exit-code validation for `compiler_multifile`.
- Modify: `roles/provision_benchmarks/tasks/os/nixos.yml`
  - Ensure NixOS provisioning installs `gnumake`.
- Modify: `roles/provision_benchmarks/defaults/main.yml`
  - Ensure SUSE package map includes `make`.
- Create: `tests/unit/test_multifile_harness_integrity.py`
  - Verify multifile harness no longer allows silent failure and OS package requirements are present.
- Create: `changelogs/fragments/multifile-harness-integrity.yml`
  - Document user-visible benchmark integrity/provisioning change.

### Task 1: Add failing integrity tests first (TDD)

**Files:**
- Create: `tests/unit/test_multifile_harness_integrity.py`
- Reference: `roles/run_benchmarks/tasks/compiler.yml`
- Reference: `roles/provision_benchmarks/tasks/os/nixos.yml`
- Reference: `roles/provision_benchmarks/defaults/main.yml`

- [ ] **Step 1: Write failing tests for multifile hardening**

```python
"""Tests for compiler_multifile harness integrity guarantees."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_suse_packages_include_make() -> None:
    defaults = yaml.safe_load(_read("roles/provision_benchmarks/defaults/main.yml"))
    assert "make" in defaults["provision_benchmarks_packages"]["Suse"]


def test_nixos_packages_include_gnumake() -> None:
    content = _read("roles/provision_benchmarks/tasks/os/nixos.yml")
    assert "gnumake" in content


def test_compiler_multifile_block_has_no_ignore_failure() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    multifile_section = content.split("# Multi-file C project compile benchmark", maxsplit=1)[1]
    assert "--ignore-failure" not in multifile_section


def test_compiler_multifile_has_preflight_and_exitcode_validation() -> None:
    content = _read("roles/run_benchmarks/tasks/compiler.yml")
    assert "Check make availability for compiler_multifile" in content
    assert "Validate compiler_multifile exit codes" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest -q tests/unit/test_multifile_harness_integrity.py
```

Expected: FAIL (missing `make`/`gnumake` assertions and missing multifile validation task names).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/unit/test_multifile_harness_integrity.py
git commit -m "tests: add failing multifile harness integrity tests"
```

### Task 2: Implement multifile hardening and provisioning fixes

**Files:**
- Modify: `roles/run_benchmarks/tasks/compiler.yml:731-787`
- Modify: `roles/provision_benchmarks/tasks/os/nixos.yml:4-32`
- Modify: `roles/provision_benchmarks/defaults/main.yml:83-102`
- Test: `tests/unit/test_multifile_harness_integrity.py`

- [ ] **Step 1: Add NixOS and SUSE package fixes**

In `roles/provision_benchmarks/tasks/os/nixos.yml` add `gnumake` in the dependency loop:

```yaml
  loop:
    - hyperfine
    - gcc
    - clang
    - gnumake
    - openssl
```

In `roles/provision_benchmarks/defaults/main.yml` add `make` for `Suse`:

```yaml
  Suse:
    - gcc
    - clang
    - make
    - openssl
```

- [ ] **Step 2: Add multifile preflight checks**

Insert before “Run multi-file C project compile benchmarks”:

```yaml
- name: Check make availability for compiler_multifile
  ansible.builtin.shell:
    cmd: command -v make >/dev/null 2>&1
    executable: "{{ _run_benchmarks_bash | default('/bin/bash') }}"
  register: run_benchmarks_compiler_multifile_make_check
  changed_when: false
  failed_when: run_benchmarks_compiler_multifile_make_check.rc != 0

- name: Check resolved compiler command list for compiler_multifile
  ansible.builtin.assert:
    that:
      - run_benchmarks_cc_resolved.stdout_lines | default([]) | length > 0
    fail_msg: >-
      {{ inventory_hostname }}: compiler_multifile requires at least one resolved C compiler.
```

- [ ] **Step 3: Remove silent multifile failure path**

In the multifile hyperfine command block, remove:

```yaml
--ignore-failure \
```

And make task fail on rc != 0:

```yaml
  failed_when: run_benchmarks_compiler_multifile_result.rc | default(1) != 0
```

- [ ] **Step 4: Add post-run exit-code validation for multifile JSON**

Add directly after multifile run task:

```yaml
- name: Validate compiler_multifile exit codes
  ansible.builtin.shell:
    cmd: |
      python3 - <<'PY'
      import json
      from pathlib import Path
      p = Path("{{ run_benchmarks_work_dir }}/compiler_multifile.json")
      data = json.loads(p.read_text())
      bad = []
      for entry in data.get("results", []):
          for code in entry.get("exit_codes", []):
              if code != 0:
                  bad.append((entry.get("command", "unknown"), code))
      if bad:
          raise SystemExit("non-zero exit codes in compiler_multifile: " + ", ".join(f"{c}:{rc}" for c, rc in bad))
      PY
    executable: "{{ _run_benchmarks_bash | default('/bin/bash') }}"
  changed_when: false
```

- [ ] **Step 5: Run targeted tests to verify pass**

Run:
```bash
uv run pytest -q tests/unit/test_multifile_harness_integrity.py
```

Expected: PASS.

- [ ] **Step 6: Run related regression tests**

Run:
```bash
uv run pytest -q tests/unit/test_benchmarks_article_data.py tests/unit/test_openbsd_provisioning.py
```

Expected: PASS.

- [ ] **Step 7: Commit implementation**

```bash
git add \
  roles/run_benchmarks/tasks/compiler.yml \
  roles/provision_benchmarks/tasks/os/nixos.yml \
  roles/provision_benchmarks/defaults/main.yml \
  tests/unit/test_multifile_harness_integrity.py
git commit -m "fix: harden compiler multifile benchmark integrity"
```

### Task 3: End-to-end verification on affected hosts and changelog

**Files:**
- Create: `changelogs/fragments/multifile-harness-integrity.yml`
- Verify runtime results: `benchmarks/results/nixos-gabrielle/compiler_multifile.json`, `benchmarks/results/opensuse-susan/compiler_multifile.json`

- [ ] **Step 1: Add changelog fragment**

Create `changelogs/fragments/multifile-harness-integrity.yml`:

```yaml
bugfixes:
  - "roles/run_benchmarks: compiler_multifile now fails hard on missing prerequisites and on non-zero command exit codes, preventing invalid near-zero benchmark timings."
  - "roles/provision_benchmarks: added make/gnumake provisioning for SUSE and NixOS to ensure multifile harness prerequisites are installed."
```

- [ ] **Step 2: Provision affected hosts**

Run:
```bash
ansible-playbook playbooks/provision_benchmarks.yml -i inventory_generator.py \
  --limit 'nixos-gabrielle,opensuse-susan' \
  -e provision_manage_power=true
```

Expected: hosts provision successfully with make implementation installed.

- [ ] **Step 3: Re-run benchmarks with power management**

Run:
```bash
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  --limit 'nixos-gabrielle,opensuse-susan' \
  -e run_benchmarks_manage_power=true
```

Expected: run completes; no multifile silent failures.

- [ ] **Step 4: Verify multifile result exit codes are all zero**

Run:
```bash
jq '[.results[].exit_codes[]] | unique' benchmarks/results/nixos-gabrielle/compiler_multifile.json
jq '[.results[].exit_codes[]] | unique' benchmarks/results/opensuse-susan/compiler_multifile.json
```

Expected output for each host:
```json
[0]
```

- [ ] **Step 5: Run repository verification commands**

Run:
```bash
uv run pytest tests/unit/
uv run ruff check scripts/ tests/
uv run ruff format --check scripts/ tests/
uv run ansible-lint
uv run python scripts/shellcheck_yaml_blocks.py
shellcheck scripts/*.sh
```

Expected: PASS.

- [ ] **Step 6: Commit verification/changelog**

```bash
git add changelogs/fragments/multifile-harness-integrity.yml
git commit -m "docs: record multifile harness integrity fixes"
```

## Spec Coverage Check

- Hard-fail preflight on missing `make` / compiler availability: Task 2 Step 2.
- Post-run validation of non-zero `exit_codes`: Task 2 Step 4.
- Provisioning consistency for NixOS/SUSE: Task 2 Step 1.
- Runtime re-validation on affected hosts: Task 3 Steps 2-4.
- User-visible change note: Task 3 Step 1.

## Placeholder / Consistency Check

- No placeholders (`TODO`, `TBD`, “later”) remain.
- Functionality names and file paths are consistent with the approved spec.
- Scope stays focused on multifile harness integrity and provisioning prerequisites only.
