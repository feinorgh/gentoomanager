# General RAM Pre-Flight Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general memory-pressure pre-flight warning that detects low available RAM and risky swap usage for benchmark runs, even when the work directory is not tmpfs.

**Architecture:** Extend `roles/run_benchmarks/tasks/sanity_check.yml` with Linux-only probes for `MemAvailable` and swap usage, then evaluate a category-aware warning predicate. Keep behavior non-fatal and additive to the existing warning block, and persist concise RAM-pressure notes into `benchmark_notes.json` for report/debug context.

**Tech Stack:** Ansible task YAML (`ansible.builtin.shell`, `set_fact`, `debug`), role defaults, pytest unit tests (task-content assertions), docs, antsibull changelog fragments.

---

## File structure and responsibilities

- **Create:** `tests/unit/test_run_benchmarks_sanity_ram_warning.py`
  - Focused tests for new RAM-pressure probes, facts, warning text, and benchmark notes persistence.
- **Modify:** `roles/run_benchmarks/defaults/main.yml`
  - Add tunables for general RAM/swap warning thresholds and per-category multipliers.
- **Modify:** `roles/run_benchmarks/tasks/sanity_check.yml`
  - Add Linux MemAvailable/swap probes and category-aware warning logic; append RAM-pressure notes.
- **Modify:** `docs/benchmarks.md`
  - Document new RAM-pressure pre-flight variables and interpretation.
- **Create:** `changelogs/fragments/benchmark-ram-preflight-warning.yml`
  - User-visible changelog entry.

### Task 1: Add failing unit tests for RAM-pressure sanity checks

**Files:**
- Create: `tests/unit/test_run_benchmarks_sanity_ram_warning.py`
- Test: `tests/unit/test_run_benchmarks_sanity_ram_warning.py`

- [ ] **Step 1: Create test scaffold and helper readers**

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")
```

- [ ] **Step 2: Add failing test for MemAvailable and swap probes**

```python
def test_sanity_check_probes_memavailable_and_swap_usage() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "MemAvailable" in content
    assert "SwapTotal" in content
    assert "SwapFree" in content
    assert "run_benchmarks_sanity_memavail_raw" in content
    assert "run_benchmarks_sanity_swap_raw" in content
```

- [ ] **Step 3: Add failing test for category-aware RAM-pressure fact and warning text**

```python
def test_sanity_check_has_general_ram_pressure_warning_logic() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "run_benchmarks_sanity_ram_pressure_warn" in content
    assert "run_benchmarks_sanity_ram_pressure_required_mb" in content
    assert "Low available RAM for selected benchmark categories" in content
```

- [ ] **Step 4: Add failing test for persisted benchmark notes fields**

```python
def test_sanity_notes_include_ram_pressure_context() -> None:
    content = _read("roles/run_benchmarks/tasks/sanity_check.yml")
    assert "ram_pressure" in content
    assert "available_mb" in content
    assert "swap_used_pct" in content
```

- [ ] **Step 5: Run tests to confirm failure**

Run: `uv run pytest tests/unit/test_run_benchmarks_sanity_ram_warning.py -v`  
Expected: FAIL (new RAM-pressure logic not implemented yet).

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/unit/test_run_benchmarks_sanity_ram_warning.py
git commit -m "test: add coverage for general benchmark RAM pre-flight warning"
```

### Task 2: Add RAM-pressure tuning defaults

**Files:**
- Modify: `roles/run_benchmarks/defaults/main.yml`
- Test: `tests/unit/test_run_benchmarks_sanity_ram_warning.py`

- [ ] **Step 1: Add base RAM/swap warning thresholds**

```yaml
# General memory-pressure warning thresholds (Linux pre-flight)
run_benchmarks_min_available_ram_mb: 1024
run_benchmarks_warn_swap_used_pct: 25
```

- [ ] **Step 2: Add category-sensitive RAM multipliers**

```yaml
# Additional recommended free RAM (MB) for heavy categories. Values are added
# to run_benchmarks_min_available_ram_mb when category is selected.
run_benchmarks_ram_pressure_category_add_mb:
  ffmpeg: 1024
  compression: 512
  compiler: 512
  linker: 512
  memory: 1024
```

- [ ] **Step 3: Add test assertions for new default keys**

```python
import yaml


def test_defaults_define_general_ram_warning_variables() -> None:
    defaults_path = REPO_ROOT / "roles/run_benchmarks/defaults/main.yml"
    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    assert "run_benchmarks_min_available_ram_mb" in defaults
    assert "run_benchmarks_warn_swap_used_pct" in defaults
    assert "run_benchmarks_ram_pressure_category_add_mb" in defaults
```

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/test_run_benchmarks_sanity_ram_warning.py -v`  
Expected: still FAIL (sanity_check implementation missing).

- [ ] **Step 5: Commit defaults + tests**

```bash
git add roles/run_benchmarks/defaults/main.yml tests/unit/test_run_benchmarks_sanity_ram_warning.py
git commit -m "feat: add tunables for benchmark RAM pressure warnings"
```

### Task 3: Implement general RAM-pressure pre-flight warning in sanity_check.yml

**Files:**
- Modify: `roles/run_benchmarks/tasks/sanity_check.yml`
- Test: `tests/unit/test_run_benchmarks_sanity_ram_warning.py`

- [ ] **Step 1: Add Linux probes for MemAvailable and swap state**

```yaml
- name: Probe available RAM (MemAvailable from /proc/meminfo)
  ansible.builtin.shell:
    cmd: awk '/^MemAvailable:/{print $2}' /proc/meminfo
    executable: /bin/sh
  register: run_benchmarks_sanity_memavail_raw
  changed_when: false
  failed_when: false
  when: ansible_system | default('Linux') not in ['OpenBSD', 'SunOS']

- name: Probe swap usage (SwapTotal/SwapFree from /proc/meminfo)
  ansible.builtin.shell:
    cmd: awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print t " " f}' /proc/meminfo
    executable: /bin/sh
  register: run_benchmarks_sanity_swap_raw
  changed_when: false
  failed_when: false
  when: ansible_system | default('Linux') not in ['OpenBSD', 'SunOS']
```

- [ ] **Step 2: Evaluate category-aware RAM-pressure facts**

```yaml
- name: Evaluate general RAM-pressure warning thresholds
  ansible.builtin.set_fact:
    run_benchmarks_sanity_ram_available_mb: >-
      {{ ((run_benchmarks_sanity_memavail_raw.stdout | default('0') | int) / 1024) | round(0) | int }}
    run_benchmarks_sanity_swap_total_kb: >-
      {{ (run_benchmarks_sanity_swap_raw.stdout.split() | first | default('0')) | int }}
    run_benchmarks_sanity_swap_free_kb: >-
      {{ (run_benchmarks_sanity_swap_raw.stdout.split() | last | default('0')) | int }}
    run_benchmarks_sanity_swap_used_pct: >-
      {{
        (100 - ((run_benchmarks_sanity_swap_free_kb | int * 100) / (run_benchmarks_sanity_swap_total_kb | int)))
        | round(1)
        if (run_benchmarks_sanity_swap_total_kb | int) > 0
        else 0
      }}
    run_benchmarks_sanity_ram_pressure_add_mb: >-
      {{
        (
          run_benchmarks_active_categories | default([])
          | map('extract', run_benchmarks_ram_pressure_category_add_mb | default({}), default=0)
          | list | max
        ) if (run_benchmarks_active_categories | default([]) | length > 0) else 0
      }}
    run_benchmarks_sanity_ram_pressure_required_mb: >-
      {{ (run_benchmarks_min_available_ram_mb | int) + (run_benchmarks_sanity_ram_pressure_add_mb | int) }}
    run_benchmarks_sanity_ram_pressure_warn: >-
      {{
        (run_benchmarks_sanity_ram_available_mb | int) < (run_benchmarks_sanity_ram_pressure_required_mb | int)
        or (run_benchmarks_sanity_swap_used_pct | float) > (run_benchmarks_warn_swap_used_pct | float)
      }}
  when: ansible_system | default('Linux') not in ['OpenBSD', 'SunOS']
```

- [ ] **Step 3: Add portable defaults for OpenBSD/OpenIndiana branch**

```yaml
- name: Default general RAM-pressure facts on OpenBSD/OpenIndiana
  ansible.builtin.set_fact:
    run_benchmarks_sanity_ram_available_mb: 0
    run_benchmarks_sanity_swap_used_pct: 0
    run_benchmarks_sanity_ram_pressure_required_mb: 0
    run_benchmarks_sanity_ram_pressure_warn: false
  when: ansible_system | default('Linux') in ['OpenBSD', 'SunOS']
```

- [ ] **Step 4: Extend warning message and when-condition**

```yaml
{% if run_benchmarks_sanity_ram_pressure_warn %}
⚠ Low available RAM for selected benchmark categories:
    available={{ run_benchmarks_sanity_ram_available_mb }} MB,
    recommended>= {{ run_benchmarks_sanity_ram_pressure_required_mb }} MB,
    swap used={{ run_benchmarks_sanity_swap_used_pct }}%
    (warn threshold={{ run_benchmarks_warn_swap_used_pct }}%).
    Results may be skewed by memory reclaim/swap pressure.
{% endif %}
```

And extend `when:` with:

```yaml
or run_benchmarks_sanity_ram_pressure_warn
```

- [ ] **Step 5: Persist RAM-pressure context in benchmark notes**

```yaml
      ram_pressure:
        available_mb: "{{ run_benchmarks_sanity_ram_available_mb | default(0) }}"
        required_mb: "{{ run_benchmarks_sanity_ram_pressure_required_mb | default(0) }}"
        swap_used_pct: "{{ run_benchmarks_sanity_swap_used_pct | default(0) }}"
        warning: "{{ run_benchmarks_sanity_ram_pressure_warn | default(false) }}"
```

- [ ] **Step 6: Run focused unit tests**

Run: `uv run pytest tests/unit/test_run_benchmarks_sanity_ram_warning.py tests/unit/test_openbsd_benchmarking.py tests/unit/test_openindiana_benchmarking.py tests/unit/test_benchmark_failure_logging.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit sanity-check implementation**

```bash
git add roles/run_benchmarks/tasks/sanity_check.yml tests/unit/test_run_benchmarks_sanity_ram_warning.py
git commit -m "feat: add general RAM pressure pre-flight warning for benchmarks"
```

### Task 4: Update docs and add changelog fragment

**Files:**
- Modify: `docs/benchmarks.md`
- Create: `changelogs/fragments/benchmark-ram-preflight-warning.yml`

- [ ] **Step 1: Add new configuration rows in benchmark docs**

```markdown
| `run_benchmarks_min_available_ram_mb` | `1024` | Base minimum recommended MemAvailable before warning (Linux pre-flight) |
| `run_benchmarks_warn_swap_used_pct` | `25` | Swap usage percentage above which pre-flight warns (Linux) |
| `run_benchmarks_ram_pressure_category_add_mb` | `{ffmpeg:1024,compression:512,compiler:512,linker:512,memory:1024}` | Extra recommended available RAM by selected heavy category |
```

- [ ] **Step 2: Add troubleshooting note for RAM-pressure warnings**

```markdown
When pre-flight reports low available RAM/high swap usage, benchmark timings
may include reclaim and swap I/O overhead. For cross-host comparisons, rerun
after reducing background load, increasing VM memory, or benchmarking fewer
heavy categories per pass.
```

- [ ] **Step 3: Add antsibull changelog fragment**

```yaml
minor_changes:
  - "roles/run_benchmarks: add general Linux pre-flight RAM pressure warning based on MemAvailable, swap usage, and selected heavy benchmark categories."
```

- [ ] **Step 4: Commit docs/changelog**

```bash
git add docs/benchmarks.md changelogs/fragments/benchmark-ram-preflight-warning.yml
git commit -m "docs: document general benchmark RAM pressure pre-flight warning"
```

### Task 5: Final validation pass for touched surfaces

**Files:**
- Modify: (none required; validation only)

- [ ] **Step 1: Run targeted benchmark-related test set**

Run: `uv run pytest tests/unit/test_run_benchmarks_sanity_ram_warning.py tests/unit/test_run_benchmarks_defaults.py tests/unit/test_openbsd_benchmarking.py tests/unit/test_openindiana_benchmarking.py tests/unit/test_benchmark_failure_logging.py -v`  
Expected: PASS.

- [ ] **Step 2: Run repo-required quality checks**

Run: `make test lint shellcheck`  
Expected: PASS.

- [ ] **Step 3: Final integration commit**

```bash
git add -A
git commit -m "feat: warn on general benchmark RAM pressure in pre-flight"
```

