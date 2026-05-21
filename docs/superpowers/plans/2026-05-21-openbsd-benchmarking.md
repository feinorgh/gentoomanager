# OpenBSD Benchmarking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class OpenBSD support to benchmark provisioning and execution so supported categories run safely, unsupported categories are skipped intentionally, and docs/tests reflect the supported surface.

**Architecture:** Extend the provisioning role so OpenBSD becomes a real platform in the clean committed baseline, then make `run_benchmarks` capability-driven for OpenBSD instead of assuming Linux/FreeBSD behavior. Treat OpenBSD as a safe-subset platform: run supported categories with explicit command resolution and metadata, and gate or skip categories whose current implementation depends on unsupported tools or kernel interfaces.

**Tech Stack:** Ansible roles/playbooks, YAML, pytest, ansible-lint-compatible task structure, uv/pytest, changelog fragments

---

## File map

- Create: `roles/provision_benchmarks/tasks/os/openbsd.yml`
- Create: `tests/unit/test_openbsd_provisioning.py`
- Create: `tests/unit/test_openbsd_benchmarking.py`
- Create: `changelogs/fragments/openbsd-benchmarking.yml`
- Modify: `roles/provision_benchmarks/defaults/main.yml`
- Modify: `roles/provision_benchmarks/tasks/main.yml`
- Modify: `roles/provision_benchmarks/tasks/verify.yml`
- Modify: `playbooks/provision_benchmarks.yml`
- Modify: `roles/run_benchmarks/tasks/setup.yml`
- Modify: `roles/run_benchmarks/tasks/sanity_check.yml`
- Modify: `roles/run_benchmarks/tasks/normalize.yml`
- Modify: `roles/run_benchmarks/tasks/denormalize.yml`
- Modify: `roles/run_benchmarks/tasks/run_category.yml`
- Modify: `roles/run_benchmarks/tasks/disk.yml`
- Modify: `roles/run_benchmarks/tasks/boot_time.yml`
- Modify: `roles/run_benchmarks/README.md`
- Modify: `docs/benchmarks.md`
- Modify: `playbooks/run_benchmarks.yml`

## Task 1: Add OpenBSD to provisioning and OS dispatch

**Files:**
- Create: `roles/provision_benchmarks/tasks/os/openbsd.yml`
- Modify: `roles/provision_benchmarks/defaults/main.yml`
- Modify: `roles/provision_benchmarks/tasks/main.yml`
- Modify: `playbooks/provision_benchmarks.yml`
- Test: `tests/unit/test_openbsd_provisioning.py`

- [ ] **Step 1: Write the failing provisioning tests**

```python
import os

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DEFAULTS = os.path.join(ROOT, "roles", "provision_benchmarks", "defaults", "main.yml")
TASKS_MAIN = os.path.join(ROOT, "roles", "provision_benchmarks", "tasks", "main.yml")
PLAYBOOK = os.path.join(ROOT, "playbooks", "provision_benchmarks.yml")
OPENBSD_TASKS = os.path.join(
    ROOT, "roles", "provision_benchmarks", "tasks", "os", "openbsd.yml"
)


def test_openbsd_defaults_exist() -> None:
    with open(DEFAULTS) as f:
        defaults = yaml.safe_load(f)
    assert "OpenBSD" in defaults["provision_benchmarks_packages"]
    assert "OpenBSD" in defaults["provision_benchmarks_numpy_packages"]
    assert "OpenBSD" in defaults["provision_benchmarks_opencv_packages"]


def test_openbsd_task_file_exists() -> None:
    assert os.path.isfile(OPENBSD_TASKS)


def test_dispatcher_maps_openbsd() -> None:
    with open(TASKS_MAIN) as f:
        content = f.read()
    assert "OpenBSD: openbsd" in content


def test_playbook_groups_and_runs_openbsd() -> None:
    with open(PLAYBOOK) as f:
        content = f.read()
    assert "OpenBSD" in content
    assert "hosts: provision_os_openbsd" in content
    assert "tasks_from: os/openbsd.yml" in content
```

- [ ] **Step 2: Run the provisioning test to verify it fails**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_provisioning.py -v`

Expected: FAIL because the OpenBSD defaults, dispatcher entry, playbook wiring, and OS task file do not exist on the clean baseline.

- [ ] **Step 3: Add the minimal OpenBSD provisioning implementation**

```yaml
# roles/provision_benchmarks/tasks/os/openbsd.yml
---
- name: Install benchmark dependencies via pkg_add
  community.general.openbsd_pkg:
    name: "{{ provision_benchmarks_packages['OpenBSD'] }}"
    state: present
  become: true

- name: Install OpenBSD optional benchmark dependencies
  community.general.openbsd_pkg:
    name: >-
      {{
        (['ffmpeg'] if provision_benchmarks_install_ffmpeg | bool else []) +
        (provision_benchmarks_numpy_packages['OpenBSD'] if provision_benchmarks_install_numpy | bool else []) +
        (provision_benchmarks_opencv_packages['OpenBSD'] if provision_benchmarks_install_opencv | bool else []) +
        (['gimp'] if provision_benchmarks_install_gimp | bool else []) +
        (['inkscape'] if provision_benchmarks_install_inkscape | bool else []) +
        (provision_benchmarks_botan_packages['OpenBSD'] if provision_benchmarks_install_botan | bool else []) +
        (provision_benchmarks_mold_packages['OpenBSD'] if provision_benchmarks_install_mold | bool else []) +
        (provision_benchmarks_octave_packages['OpenBSD'] if provision_benchmarks_install_octave | bool else [])
      }}
    state: present
  become: true

- name: Verify installed tools
  ansible.builtin.include_tasks: verify.yml
```

```yaml
# roles/provision_benchmarks/tasks/main.yml
    _os_family_map:
      Gentoo: gentoo
      RedHat: redhat
      Debian: debian
      Archlinux: archlinux
      Suse: suse
      FreeBSD: freebsd
      OpenBSD: openbsd
      Void: void
      NixOS: nixos
      Solus: solus
```

```yaml
# playbooks/provision_benchmarks.yml
    ansible_os_family in ['Gentoo', 'RedHat', 'Debian', 'Archlinux',
                          'Suse', 'FreeBSD', 'OpenBSD', 'Void', 'NixOS', 'Solus']

- name: Provision OpenBSD hosts
  hosts: provision_os_openbsd
  serial: "{{ provision_serial | default(1) }}"
  gather_facts: false
  ignore_unreachable: true
  any_errors_fatal: false
  tasks:
    - name: Provision benchmark dependencies
      ansible.builtin.include_role:
        name: provision_benchmarks
        tasks_from: os/openbsd.yml
```

- [ ] **Step 4: Extend defaults with OpenBSD package maps**

```yaml
# roles/provision_benchmarks/defaults/main.yml
  OpenBSD:
    - gcc%11
    - llvm
    - python
    - rust
    - go
    - git
    - zstd
    - lz4
    - gnupg
    - p7zip
    - ImageMagick
    - sqlite3
    - hyperfine
    - bash

provision_benchmarks_numpy_packages:
  OpenBSD:
    - py3-numpy

provision_benchmarks_opencv_packages:
  OpenBSD:
    - opencv

provision_benchmarks_botan_packages:
  OpenBSD: []

provision_benchmarks_mold_packages:
  OpenBSD: []

provision_benchmarks_octave_packages:
  OpenBSD:
    - octave
```

- [ ] **Step 5: Run the provisioning test to verify it passes**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_provisioning.py -v`

Expected: PASS for the new OpenBSD defaults, task file, dispatcher entry, and playbook wiring.

- [ ] **Step 6: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
git add tests/unit/test_openbsd_provisioning.py \
  roles/provision_benchmarks/defaults/main.yml \
  roles/provision_benchmarks/tasks/main.yml \
  roles/provision_benchmarks/tasks/os/openbsd.yml \
  playbooks/provision_benchmarks.yml
git commit -m "feat: add OpenBSD benchmark provisioning"
```

## Task 2: Resolve OpenBSD command names and verification behavior

**Files:**
- Modify: `roles/provision_benchmarks/tasks/verify.yml`
- Modify: `roles/run_benchmarks/tasks/setup.yml`
- Modify: `roles/run_benchmarks/tasks/sanity_check.yml`
- Test: `tests/unit/test_openbsd_benchmarking.py`

- [ ] **Step 1: Write the failing command-resolution tests**

```python
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
VERIFY = os.path.join(ROOT, "roles", "provision_benchmarks", "tasks", "verify.yml")
SETUP = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "setup.yml")
SANITY = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "sanity_check.yml")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_verify_supports_openbsd_command_aliases() -> None:
    content = _read(VERIFY)
    assert "python3" in content
    assert "python" in content
    assert "doas" in content or "become" in content


def test_setup_defines_openbsd_command_facts() -> None:
    content = _read(SETUP)
    assert "run_benchmarks_python_cmd" in content
    assert "run_benchmarks_gcc_cmd" in content
    assert "run_benchmarks_privilege_cmd" in content


def test_sanity_no_longer_hardcodes_sudo_only() -> None:
    content = _read(SANITY)
    assert "sudo -n true" not in content
    assert "run_benchmarks_privilege_cmd" in content
```

- [ ] **Step 2: Run the OpenBSD command-resolution test to verify it fails**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "command or sanity or verify" -v`

Expected: FAIL because verification and sanity-check logic still assume universal command names and `sudo`.

- [ ] **Step 3: Add setup facts for resolved tool commands**

```yaml
# roles/run_benchmarks/tasks/setup.yml
- name: Resolve benchmark command names
  ansible.builtin.set_fact:
    run_benchmarks_python_cmd: >-
      {{ 'python3' if ansible_system | default('') != 'OpenBSD' else 'python3' }}
    run_benchmarks_gcc_cmd: >-
      {{ 'gcc' if ansible_system | default('') != 'OpenBSD' else 'gcc' }}
    run_benchmarks_privilege_cmd: >-
      {{ 'doas -n' if ansible_system | default('') == 'OpenBSD' else 'sudo -n' }}
```

```yaml
# use resolved commands in setup.yml version gathering
      echo "::gcc::$({{ run_benchmarks_gcc_cmd }} --version 2>/dev/null | head -1 || echo 'not installed')"
      echo "::python::$({{ run_benchmarks_python_cmd }} --version 2>/dev/null || echo 'not installed')"
      echo "::numpy::$({{ run_benchmarks_python_cmd }} -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'not installed')"
```

- [ ] **Step 4: Replace hardcoded tool and privilege assumptions**

```yaml
# roles/provision_benchmarks/tasks/verify.yml
      if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
        printf "  %-15s OK\n" "python"
      else
        printf "  %-15s MISSING\n" "python"
      fi
```

```yaml
# roles/run_benchmarks/tasks/sanity_check.yml
- name: Probe passwordless privilege escalation access
  ansible.builtin.shell:
    cmd: "{{ run_benchmarks_privilege_cmd }} true"
    executable: /bin/sh
  register: run_benchmarks_sanity_privilege
  changed_when: false
  failed_when: false
```

```yaml
# roles/run_benchmarks/tasks/sanity_check.yml warning text
      ✗ Passwordless privilege escalation NOT available — CPU governor pinning and swap
          disable/restore steps will be skipped or may fail.
          Ensure the Ansible user can use sudo or doas without a password.
```

- [ ] **Step 5: Run the OpenBSD command-resolution test to verify it passes**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "command or sanity or verify" -v`

Expected: PASS with resolved command facts in setup, non-`sudo`-only privilege probing, and OpenBSD-friendly verification logic.

- [ ] **Step 6: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
git add tests/unit/test_openbsd_benchmarking.py \
  roles/provision_benchmarks/tasks/verify.yml \
  roles/run_benchmarks/tasks/setup.yml \
  roles/run_benchmarks/tasks/sanity_check.yml
git commit -m "fix: resolve OpenBSD benchmark commands"
```

## Task 3: Add OpenBSD setup metadata and safe-subset normalization

**Files:**
- Modify: `roles/run_benchmarks/tasks/setup.yml`
- Modify: `roles/run_benchmarks/tasks/normalize.yml`
- Modify: `roles/run_benchmarks/tasks/denormalize.yml`
- Modify: `roles/run_benchmarks/tasks/run_category.yml`
- Test: `tests/unit/test_openbsd_benchmarking.py`

- [ ] **Step 1: Write the failing runtime-branch tests**

```python
def test_setup_has_openbsd_metadata_branches() -> None:
    content = _read(SETUP)
    assert "ansible_system | default('') == 'OpenBSD'" in content


def test_normalize_has_openbsd_safe_subset_branch() -> None:
    path = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "normalize.yml")
    assert "OpenBSD" in _read(path)


def test_denormalize_has_openbsd_safe_subset_branch() -> None:
    path = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "denormalize.yml")
    assert "OpenBSD" in _read(path)


def test_run_category_avoids_linux_only_cache_drop_on_openbsd() -> None:
    path = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "run_category.yml")
    content = _read(path)
    assert "OpenBSD" in content
    assert "run_benchmarks_category_prepare_cmd" in content
```

- [ ] **Step 2: Run the runtime-branch test to verify it fails**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "metadata or normalize or denormalize or run_category" -v`

Expected: FAIL because the clean baseline does not contain OpenBSD runtime branches.

- [ ] **Step 3: Add OpenBSD capability and metadata facts**

```yaml
# roles/run_benchmarks/tasks/setup.yml
- name: Set OpenBSD capability defaults
  ansible.builtin.set_fact:
    run_benchmarks_openbsd_safe_normalization: "{{ ansible_system | default('') == 'OpenBSD' }}"
    run_benchmarks_category_prepare_cmd: >-
      {{ 'sync' if ansible_system | default('') == 'OpenBSD' else '' }}
```

```yaml
# roles/run_benchmarks/tasks/setup.yml
- name: Get CPU max clock speed (OpenBSD)
  ansible.builtin.command:
    cmd: sysctl -n hw.cpuspeed
  register: run_benchmarks_cpu_freq_openbsd
  changed_when: false
  failed_when: false
  when: ansible_system | default('') == 'OpenBSD'
```

```yaml
# roles/run_benchmarks/tasks/setup.yml metadata shaping
      cpu_frequency_max_khz: >-
        {{
          (run_benchmarks_cpu_freq_openbsd.stdout | int * 1000)
          if ansible_system | default('') == 'OpenBSD'
          else (run_benchmarks_cpu_freq_raw.stdout | default('0') | int)
        }}
```

- [ ] **Step 4: Implement safe-subset OpenBSD normalization**

```yaml
# roles/run_benchmarks/tasks/normalize.yml
- name: Sync filesystems (OpenBSD safe subset)
  ansible.builtin.command:
    cmd: sync
  changed_when: false
  when: ansible_system | default('') == 'OpenBSD'
```

```yaml
# roles/run_benchmarks/tasks/denormalize.yml
- name: Drop no-op OpenBSD normalization restore marker
  ansible.builtin.set_fact:
    run_benchmarks_openbsd_normalization_restored: true
  when: ansible_system | default('') == 'OpenBSD'
```

```yaml
# roles/run_benchmarks/tasks/run_category.yml
- name: Prepare benchmark category on OpenBSD
  ansible.builtin.command:
    cmd: "{{ run_benchmarks_category_prepare_cmd }}"
  become: false
  changed_when: false
  when:
    - ansible_system | default('') == 'OpenBSD'
    - run_benchmarks_category_prepare_cmd | length > 0
```

- [ ] **Step 5: Run the runtime-branch test to verify it passes**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "metadata or normalize or denormalize or run_category" -v`

Expected: PASS because OpenBSD runtime paths now exist and Linux-only pre-category behavior is guarded.

- [ ] **Step 6: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
git add tests/unit/test_openbsd_benchmarking.py \
  roles/run_benchmarks/tasks/setup.yml \
  roles/run_benchmarks/tasks/normalize.yml \
  roles/run_benchmarks/tasks/denormalize.yml \
  roles/run_benchmarks/tasks/run_category.yml
git commit -m "feat: add OpenBSD benchmark runtime support"
```

## Task 4: Gate unsupported categories and preserve skip reasons

**Files:**
- Modify: `roles/run_benchmarks/tasks/disk.yml`
- Modify: `roles/run_benchmarks/tasks/boot_time.yml`
- Modify: `roles/run_benchmarks/tasks/sanity_check.yml`
- Test: `tests/unit/test_openbsd_benchmarking.py`

- [ ] **Step 1: Write the failing category-gating tests**

```python
def test_disk_task_explicitly_gates_openbsd() -> None:
    path = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "disk.yml")
    content = _read(path)
    assert "OpenBSD" in content
    assert "run_benchmarks_disk_skip_reason" in content


def test_boot_time_task_has_openbsd_policy_branch() -> None:
    path = os.path.join(ROOT, "roles", "run_benchmarks", "tasks", "boot_time.yml")
    content = _read(path)
    assert "OpenBSD" in content
    assert "unsupported on OpenBSD" in content or "method" in content
```

- [ ] **Step 2: Run the category-gating test to verify it fails**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "disk or boot_time" -v`

Expected: FAIL because `disk.yml` and `boot_time.yml` still describe Linux/non-systemd behavior only.

- [ ] **Step 3: Add explicit OpenBSD skip semantics for unsupported categories**

```yaml
# roles/run_benchmarks/tasks/disk.yml
- name: Mark disk benchmark unsupported on OpenBSD
  ansible.builtin.set_fact:
    run_benchmarks_disk_skip: true
    run_benchmarks_disk_skip_reason: "disk benchmark currently depends on Linux-specific cache dropping and filesystem probing"
  when: ansible_system | default('') == 'OpenBSD'
```

```yaml
# roles/run_benchmarks/tasks/boot_time.yml
- name: Write unsupported boot-time result for OpenBSD
  ansible.builtin.copy:
    dest: "{{ run_benchmarks_work_dir }}/boot_times.json"
    mode: "0644"
    content: >-
      {{ {
        'available': false,
        'method': 'unsupported',
        'error': 'boot_time benchmark is not yet supported on OpenBSD'
      } | to_json }}\n
  when: ansible_system | default('') == 'OpenBSD'
```

- [ ] **Step 4: Preserve OpenBSD skip reasons in benchmark notes**

```yaml
# roles/run_benchmarks/tasks/sanity_check.yml
      distro_notes: >-
        {{
          (run_benchmarks_sanity_distro_notes | default([])) +
          (['disk: ' ~ run_benchmarks_disk_skip_reason]
           if run_benchmarks_disk_skip_reason is defined else [])
        }}
```

- [ ] **Step 5: Run the category-gating test to verify it passes**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "disk or boot_time" -v`

Expected: PASS because disk and boot-time behavior is now intentionally modeled for OpenBSD and the skip/unsupported policy is explicit.

- [ ] **Step 6: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
git add tests/unit/test_openbsd_benchmarking.py \
  roles/run_benchmarks/tasks/disk.yml \
  roles/run_benchmarks/tasks/boot_time.yml \
  roles/run_benchmarks/tasks/sanity_check.yml
git commit -m "fix: gate unsupported OpenBSD benchmark categories"
```

## Task 5: Document OpenBSD support and add release notes

**Files:**
- Modify: `roles/run_benchmarks/README.md`
- Modify: `docs/benchmarks.md`
- Modify: `playbooks/run_benchmarks.yml`
- Create: `changelogs/fragments/openbsd-benchmarking.yml`
- Test: `tests/unit/test_openbsd_benchmarking.py`

- [ ] **Step 1: Write the failing documentation test**

```python
def test_help_text_and_docs_mention_openbsd_support() -> None:
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "roles" / "run_benchmarks" / "README.md").read_text()
    guide = (repo / "docs" / "benchmarks.md").read_text()
    playbook = (repo / "playbooks" / "run_benchmarks.yml").read_text()
    assert "OpenBSD" in readme
    assert "OpenBSD" in guide
    assert "OpenBSD" in playbook
```

- [ ] **Step 2: Run the documentation test to verify it fails**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_benchmarking.py -k "OpenBSD" -v`

Expected: FAIL because the benchmark README, benchmark guide, and benchmark playbook comments still describe only Linux and FreeBSD runtime support.

- [ ] **Step 3: Update the support docs and changelog fragment**

```markdown
# roles/run_benchmarks/README.md
Supports Linux (all major distributions), FreeBSD, OpenBSD, and Windows.

OpenBSD support uses a safe-subset normalization policy. Categories that depend
on unsupported or non-recommended OpenBSD tooling are skipped with explicit
notes instead of being treated as hard failures.
```

```markdown
# docs/benchmarks.md
| OpenBSD | pkg_add (+ standard ports where appropriate) | — | Supported with category-level caveats and reduced normalization where required. |
```

```yaml
# changelogs/fragments/openbsd-benchmarking.yml
---
minor_changes:
  - "roles/provision_benchmarks: add OpenBSD provisioning support in the clean baseline."
  - "roles/run_benchmarks: add OpenBSD runtime handling, safe-subset normalization, and explicit skip semantics."
  - "docs/benchmarks: document OpenBSD benchmark support and caveats."
```

- [ ] **Step 4: Run the documentation and targeted test suite**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan && uv run pytest tests/unit/test_openbsd_provisioning.py tests/unit/test_openbsd_benchmarking.py -v && uv run pytest tests/unit/`

Expected: PASS with OpenBSD support reflected in docs and no regression in the unit suite.

- [ ] **Step 5: Run repository lint/test commands required by the repo**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
uv run ruff check scripts/ tests/
uv run ruff format --check scripts/ tests/
uv run ansible-lint
uv run python scripts/shellcheck_yaml_blocks.py
shellcheck scripts/*.sh
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager/.worktrees/openbsd-benchmarking-plan
git add roles/run_benchmarks/README.md \
  docs/benchmarks.md \
  playbooks/run_benchmarks.yml \
  changelogs/fragments/openbsd-benchmarking.yml \
  tests/unit/test_openbsd_benchmarking.py
git commit -m "docs: describe OpenBSD benchmark support"
```
