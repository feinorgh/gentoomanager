# Auto-Selecting Benchmark Work Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent benchmark fixture copy failures on low-RAM hosts by automatically choosing a non-tmpfs work directory with enough free space when `/tmp` is unsuitable.

**Architecture:** Add a dedicated Unix work-directory selection task file that evaluates candidate base directories using actual free space and filesystem type, then sets `run_benchmarks_work_dir` and `run_benchmarks_effective_work_dir` to the selected path. Wire this selector into both VM and hypervisor benchmark plays before sanity checks and role execution so all downstream tasks (including fixture copy, result discovery, and cleanup) use the same resolved directory.

**Tech Stack:** Ansible YAML tasks (`ansible.builtin.shell`, `set_fact`, `include_tasks`), role defaults, pytest unit tests, role/playbook docs, antsibull changelog fragment.

---

## File structure and responsibilities

- **Create:** `roles/run_benchmarks/tasks/select_work_dir.yml`
  - Single-purpose selector for Unix hosts: detect viable work dir from candidate list, ensure capacity, expose resolved facts.
- **Create:** `tests/unit/test_run_benchmarks_workdir_selection.py`
  - Unit coverage for selector task behavior, playbook wiring, and default variable presence.
- **Modify:** `roles/run_benchmarks/defaults/main.yml`
  - New defaults for auto-selection toggle, candidate directories, and required free space.
- **Modify:** `playbooks/run_benchmarks.yml`
  - Include selector in both benchmark plays before sanity checks; preserve Windows behavior.
- **Modify:** `roles/run_benchmarks/README.md`
  - Document new auto-selection variables and behavior.
- **Modify:** `docs/benchmarks.md`
  - Add configuration reference and troubleshooting note for tmpfs work-dir fallback.
- **Create:** `changelogs/fragments/benchmark-workdir-autoselect.yml`
  - User-visible changelog entry for tmpfs-safe directory selection.

### Task 1: Write failing tests for work-dir auto-selection behavior

**Files:**
- Create: `tests/unit/test_run_benchmarks_workdir_selection.py`
- Test: `tests/unit/test_run_benchmarks_workdir_selection.py`

- [ ] **Step 1: Add a test that defaults define selector variables**

```python
def test_defaults_define_workdir_autoselect_variables() -> None:
    defaults = _load_yaml("roles/run_benchmarks/defaults/main.yml")
    assert "run_benchmarks_auto_select_work_dir" in defaults
    assert "run_benchmarks_work_dir_candidates" in defaults
    assert "run_benchmarks_work_dir_required_mb" in defaults
```

- [ ] **Step 2: Add a test that selector task exists and sets resolved facts**

```python
def test_selector_task_sets_effective_workdir_facts() -> None:
    content = _read_text("roles/run_benchmarks/tasks/select_work_dir.yml")
    assert "Select benchmark work directory candidate (Unix)" in content
    assert "run_benchmarks_selected_work_dir" in content
    assert "run_benchmarks_effective_work_dir" in content
```

- [ ] **Step 3: Add a test that playbook includes selector before sanity check**

```python
def test_playbook_runs_selector_before_sanity_check() -> None:
    content = _read_text("playbooks/run_benchmarks.yml")
    selector_idx = content.index("roles/run_benchmarks/tasks/select_work_dir.yml")
    sanity_idx = content.index("roles/run_benchmarks/tasks/sanity_check.yml")
    assert selector_idx < sanity_idx
```

- [ ] **Step 4: Run tests and confirm failure before implementation**

Run: `uv run pytest tests/unit/test_run_benchmarks_workdir_selection.py -v`  
Expected: FAIL (new selector files/variables not present yet).

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/unit/test_run_benchmarks_workdir_selection.py
git commit -m "test: add coverage for benchmark workdir auto-selection"
```

### Task 2: Implement portable Unix work-dir selector and defaults

**Files:**
- Modify: `roles/run_benchmarks/defaults/main.yml`
- Create: `roles/run_benchmarks/tasks/select_work_dir.yml`
- Test: `tests/unit/test_run_benchmarks_workdir_selection.py`

- [ ] **Step 1: Add selector defaults in role defaults**

```yaml
run_benchmarks_auto_select_work_dir: true
run_benchmarks_work_dir_required_mb: 2048
run_benchmarks_work_dir_candidates:
  - /var/tmp
  - /var/cache
  - /opt
  - /usr/local/tmp
```

- [ ] **Step 2: Create selector task file with capacity-based candidate scan**

```yaml
- name: Select benchmark work directory candidate (Unix)
  ansible.builtin.shell:
    cmd: |
      set -eu
      required_kb=$(( {{ run_benchmarks_work_dir_required_mb | int }} * 1024 ))
      for base in {{ run_benchmarks_work_dir_candidates | map('quote') | join(' ') }}; do
        [ -d "$base" ] || continue
        fstype=$(df -PT "$base" 2>/dev/null | awk 'NR==2{print $2}')
        avail_kb=$(df -Pk "$base" 2>/dev/null | awk 'NR==2{print $4}')
        [ -n "$fstype" ] || continue
        [ -n "$avail_kb" ] || continue
        case "$fstype" in tmpfs|ramfs|devtmpfs) continue ;; esac
        if [ "$avail_kb" -ge "$required_kb" ]; then
          echo "selected=${base}/ansible-benchmarks"
          echo "base=$base"
          echo "fstype=$fstype"
          echo "avail_kb=$avail_kb"
          exit 0
        fi
      done
      exit 1
    executable: /bin/sh
  register: run_benchmarks_workdir_select_raw
  changed_when: false
  failed_when: false
  when:
    - ansible_os_family | default('') != 'Windows'
    - run_benchmarks_auto_select_work_dir | default(true) | bool
```

- [ ] **Step 3: Set selected and effective facts, with explicit fallback**

```yaml
- name: Set selected benchmark work directory facts
  ansible.builtin.set_fact:
    run_benchmarks_selected_work_dir: >-
      {{ (run_benchmarks_workdir_select_raw.stdout_lines
          | select('match', '^selected=')
          | first
          | default('selected=' + run_benchmarks_work_dir)
          | regex_replace('^selected=', '')) }}
    run_benchmarks_effective_work_dir: >-
      {{ (run_benchmarks_workdir_select_raw.stdout_lines
          | select('match', '^selected=')
          | first
          | default('selected=' + run_benchmarks_work_dir)
          | regex_replace('^selected=', '')) }}
```

- [ ] **Step 4: Rebind `run_benchmarks_work_dir` to the selected Unix directory**

```yaml
- name: Apply selected benchmark work directory for downstream tasks
  ansible.builtin.set_fact:
    run_benchmarks_work_dir: "{{ run_benchmarks_selected_work_dir }}"
  when:
    - ansible_os_family | default('') != 'Windows'
    - run_benchmarks_selected_work_dir is defined
    - run_benchmarks_selected_work_dir | length > 0
```

- [ ] **Step 5: Add fail-fast message when no candidate has sufficient capacity**

```yaml
- name: Fail when no suitable non-tmpfs work directory is available
  ansible.builtin.fail:
    msg: >-
      No suitable benchmark work directory found. Required free space:
      {{ run_benchmarks_work_dir_required_mb }} MB. Checked:
      {{ run_benchmarks_work_dir_candidates | join(', ') }}.
      Override run_benchmarks_work_dir or adjust candidate list/required size.
  when:
    - ansible_os_family | default('') != 'Windows'
    - run_benchmarks_auto_select_work_dir | default(true) | bool
    - run_benchmarks_workdir_select_raw.rc | default(1) != 0
```

- [ ] **Step 6: Run selector tests and confirm pass**

Run: `uv run pytest tests/unit/test_run_benchmarks_workdir_selection.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit selector implementation**

```bash
git add roles/run_benchmarks/defaults/main.yml roles/run_benchmarks/tasks/select_work_dir.yml tests/unit/test_run_benchmarks_workdir_selection.py
git commit -m "feat: auto-select non-tmpfs benchmark workdir with capacity check"
```

### Task 3: Wire selector into benchmark play flow

**Files:**
- Modify: `playbooks/run_benchmarks.yml`
- Test: `tests/unit/test_run_benchmarks_workdir_selection.py`
- Test: `tests/unit/test_benchmark_failure_logging.py`

- [ ] **Step 1: Include selector in VM benchmark play before sanity check**

```yaml
- name: Resolve benchmark work directory
  ansible.builtin.include_tasks:
    file: "{{ playbook_dir }}/../roles/run_benchmarks/tasks/select_work_dir.yml"
  when: ansible_os_family | default('') != 'Windows'
```

- [ ] **Step 2: Include selector in hypervisor benchmark play before sanity check**

```yaml
- name: Resolve benchmark work directory
  ansible.builtin.include_tasks:
    file: "{{ playbook_dir }}/../roles/run_benchmarks/tasks/select_work_dir.yml"
```

- [ ] **Step 3: Ensure Windows path logic remains unchanged**

```yaml
- name: Set effective work directory
  ansible.builtin.set_fact:
    run_benchmarks_effective_work_dir: >-
      {{ run_benchmarks_work_dir_win
         if (ansible_os_family | default('') == 'Windows')
         else run_benchmarks_work_dir }}
```

- [ ] **Step 4: Run focused regression tests**

Run: `uv run pytest tests/unit/test_run_benchmarks_workdir_selection.py tests/unit/test_benchmark_failure_logging.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit playbook wiring**

```bash
git add playbooks/run_benchmarks.yml tests/unit/test_run_benchmarks_workdir_selection.py
git commit -m "feat: wire benchmark workdir selector into playbook flow"
```

### Task 4: Document behavior and add changelog fragment

**Files:**
- Modify: `roles/run_benchmarks/README.md`
- Modify: `docs/benchmarks.md`
- Create: `changelogs/fragments/benchmark-workdir-autoselect.yml`

- [ ] **Step 1: Document new selector variables in role README**

```markdown
| `run_benchmarks_auto_select_work_dir` | `true` | Auto-select a non-tmpfs work directory with enough space on Unix hosts |
| `run_benchmarks_work_dir_candidates` | `[/var/tmp,/var/cache,/opt,/usr/local/tmp]` | Candidate base directories scanned for available capacity |
| `run_benchmarks_work_dir_required_mb` | `2048` | Minimum free space required for selected benchmark work directory |
```

- [ ] **Step 2: Document tmpfs fallback behavior in benchmark docs**

```markdown
When `run_benchmarks_auto_select_work_dir=true`, Unix hosts automatically choose
a non-tmpfs work directory from `run_benchmarks_work_dir_candidates` with at least
`run_benchmarks_work_dir_required_mb` free space. This prevents large fixture copy
failures on RAM-backed `/tmp` mounts.
```

- [ ] **Step 3: Add antsibull changelog fragment**

```yaml
minor_changes:
  - "roles/run_benchmarks: automatically select a non-tmpfs Unix work directory with sufficient free space to avoid large fixture copy failures on RAM-backed /tmp."
```

- [ ] **Step 4: Commit docs and changelog**

```bash
git add roles/run_benchmarks/README.md docs/benchmarks.md changelogs/fragments/benchmark-workdir-autoselect.yml
git commit -m "docs: document benchmark workdir auto-selection"
```

### Task 5: Final targeted verification and integration commit

**Files:**
- Modify: (none required; verification-only task)

- [ ] **Step 1: Run targeted unit tests for touched benchmark surfaces**

Run: `uv run pytest tests/unit/test_run_benchmarks_workdir_selection.py tests/unit/test_run_benchmarks_defaults.py tests/unit/test_openbsd_benchmarking.py tests/unit/test_openindiana_benchmarking.py tests/unit/test_benchmark_failure_logging.py -v`  
Expected: PASS.

- [ ] **Step 2: Run lint/tests command set required by repository guidance**

Run: `make test lint shellcheck`  
Expected: PASS.

- [ ] **Step 3: Create final integration commit**

```bash
git add -A
git commit -m "feat: auto-select benchmark workdir on low-memory tmpfs hosts"
```

