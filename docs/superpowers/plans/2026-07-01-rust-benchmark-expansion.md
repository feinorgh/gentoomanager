# Rust Compiler Benchmark Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Rust benchmarking within the existing `compiler` category to include compile, runtime, and curated external-workload measurements with stable reporting.

**Architecture:** Keep all Rust benchmark orchestration inside `roles/run_benchmarks/tasks/compiler.yml`, extending the existing generated Rust project and toolchain loop rather than adding a new top-level category. Emit two additional Rust compiler JSON outputs (`compiler_rust_runtime.json`, `compiler_rust_external.json`) and wire them into report titles and unit tests. Preserve the current non-fatal warning-on-failure benchmark behavior.

**Tech Stack:** Ansible YAML tasks, shell/hyperfine commands, generated Rust/Cargo project files, Python report generation, pytest.

---

## File structure and responsibilities

- `roles/run_benchmarks/tasks/compiler.yml`
  - Source of truth for compiler benchmarks.
  - Extend generated Rust project shape and add two Rust benchmark execution blocks.
- `scripts/generate_benchmark_report.py`
  - Report category title mapping and compiler section rendering labels.
  - Add labels for new Rust compiler outputs.
- `tests/unit/test_benchmark_report.py`
  - Regression tests for report category visibility and compiler label parsing.
  - Add expectations for new Rust output categories.
- `tests/unit/test_compiler_rust_benchmarks.py` (new)
  - Guardrails for compiler task content: required output filenames, runtime/external command names, and warning tasks.

### Task 1: Add failing tests for new Rust compiler outputs

**Files:**
- Create: `tests/unit/test_compiler_rust_benchmarks.py`
- Modify: `tests/unit/test_benchmark_report.py`
- Test: `tests/unit/test_compiler_rust_benchmarks.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Write failing task-content tests for Rust runtime/external outputs**

```python
from __future__ import annotations

from pathlib import Path

COMPILER_TASK = Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"


def _content() -> str:
    return COMPILER_TASK.read_text(encoding="utf-8")


def test_compiler_task_exports_rust_runtime_json() -> None:
    assert "compiler_rust_runtime.json" in _content()


def test_compiler_task_exports_rust_external_json() -> None:
    assert "compiler_rust_external.json" in _content()


def test_compiler_task_has_warn_blocks_for_new_rust_benchmarks() -> None:
    text = _content()
    assert "Warn on compiler_rust_runtime benchmark failure" in text
    assert "Warn on compiler_rust_external benchmark failure" in text
```

- [ ] **Step 2: Write failing report test for Rust category titles**

```python
from scripts.generate_benchmark_report import CATEGORY_TITLES


def test_category_titles_include_new_rust_compiler_outputs() -> None:
    assert CATEGORY_TITLES["compiler_rust_runtime"] == "Rust Runtime Performance"
    assert CATEGORY_TITLES["compiler_rust_external"] == "Rust External Workload Performance"
```

- [ ] **Step 3: Run the new tests and confirm they fail**

Run: `uv run pytest tests/unit/test_compiler_rust_benchmarks.py tests/unit/test_benchmark_report.py::test_category_titles_include_new_rust_compiler_outputs -v`  
Expected: FAIL with missing `compiler_rust_runtime.json` / `compiler_rust_external.json` and missing category-title keys.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/unit/test_compiler_rust_benchmarks.py tests/unit/test_benchmark_report.py
git commit -m "tests: add rust runtime/external compiler benchmark expectations"
```

### Task 2: Extend Rust benchmark generation in `compiler.yml`

**Files:**
- Modify: `roles/run_benchmarks/tasks/compiler.yml`
- Test: `tests/unit/test_compiler_rust_benchmarks.py`

- [ ] **Step 1: Extend generated `Cargo.toml` and sources for runtime + external workloads**

```yaml
- name: Create Rust benchmark project
  ansible.builtin.shell:
    cmd: |
      set -e
      if command -v rustc >/dev/null 2>&1 && [ ! -d {{ run_benchmarks_work_dir }}/rust_bench ]; then
        mkdir -p {{ run_benchmarks_work_dir }}/rust_bench/src {{ run_benchmarks_work_dir }}/rust_bench/fixtures
        cat > {{ run_benchmarks_work_dir }}/rust_bench/Cargo.toml << 'TOML'
      [package]
      name = "bench"
      version = "0.1.0"
      edition = "2021"

      [dependencies]
      regex = "1.11.1"
      serde_json = "1.0.140"

      [[bin]]
      name = "rust_runtime"
      path = "src/runtime.rs"

      [[bin]]
      name = "rust_external"
      path = "src/external.rs"
      TOML
```

- [ ] **Step 2: Add deterministic runtime and external source files**

```yaml
        cat > {{ run_benchmarks_work_dir }}/rust_bench/src/runtime.rs << 'RUST'
      fn main() {
          let mut x: u64 = 42;
          let mut acc: u64 = 0;
          for _ in 0..5_000_000 {
              x = x.wrapping_mul(6364136223846793005).wrapping_add(1);
              acc ^= x.rotate_left(13);
          }
          println!("{}", acc);
      }
      RUST

        cat > {{ run_benchmarks_work_dir }}/rust_bench/src/external.rs << 'RUST'
      use regex::Regex;
      use serde_json::Value;
      use std::fs;

      fn main() {
          let data = fs::read_to_string("fixtures/external_input.json").expect("fixture");
          let value: Value = serde_json::from_str(&data).expect("json");
          let re = Regex::new(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}").expect("regex");
          let mut count = 0usize;
          if let Some(arr) = value.as_array() {
              for entry in arr {
                  if let Some(s) = entry.as_str() {
                      count += re.find_iter(s).count();
                  }
              }
          }
          println!("{}", count);
      }
      RUST
```

- [ ] **Step 3: Add deterministic fixture and lockfile bootstrap**

```yaml
        cat > {{ run_benchmarks_work_dir }}/rust_bench/fixtures/external_input.json << 'JSON'
      ["alice@example.com","invalid","bob.smith@example.org","carol+ops@example.net"]
      JSON
        (cd {{ run_benchmarks_work_dir }}/rust_bench && cargo generate-lockfile >/dev/null 2>&1 || true)
      fi
```

- [ ] **Step 4: Add runtime benchmark block**

```yaml
- name: Run Rust runtime benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/rust_bench
      CMDS=()
      {% for tc in run_benchmarks_rust_resolved.stdout_lines | default([]) %}
      {% set tc_parts = tc.split() %}
      {% if tc_parts | length >= 2 %}
      {% set tc_label = tc_parts[0] %}
      {% set tc_cargo = tc_parts[1] %}
      if [ -x "{{ tc_cargo }}" ]; then
        {{ tc_cargo }} build --release --bin rust_runtime >/dev/null 2>&1 || true
        CMDS+=(--command-name "{{ tc_label }}-runtime" "./target/release/rust_runtime")
      fi
      {% endif %}
      {% endfor %}
      [ -z "${CMDS[*]}" ] && exit 0
      {{ run_benchmarks_hyperfine_bin }} --runs {{ run_benchmarks_runs }} --warmup {{ run_benchmarks_warmup }} --ignore-failure --export-json {{ run_benchmarks_work_dir }}/compiler_rust_runtime.json "${CMDS[@]}"
```

- [ ] **Step 5: Add external-workload benchmark block + warning blocks**

```yaml
- name: Run Rust external workload benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/rust_bench
      CMDS=()
      {% for tc in run_benchmarks_rust_resolved.stdout_lines | default([]) %}
      {% set tc_parts = tc.split() %}
      {% if tc_parts | length >= 2 %}
      {% set tc_label = tc_parts[0] %}
      {% set tc_cargo = tc_parts[1] %}
      if [ -x "{{ tc_cargo }}" ]; then
        {{ tc_cargo }} build --release --bin rust_external >/dev/null 2>&1 || true
        CMDS+=(--command-name "{{ tc_label }}-external" "./target/release/rust_external")
      fi
      {% endif %}
      {% endfor %}
      [ -z "${CMDS[*]}" ] && exit 0
      {{ run_benchmarks_hyperfine_bin }} --runs {{ run_benchmarks_runs }} --warmup {{ run_benchmarks_warmup }} --ignore-failure --export-json {{ run_benchmarks_work_dir }}/compiler_rust_external.json "${CMDS[@]}"

- name: Warn on compiler_rust_runtime benchmark failure
  ansible.builtin.debug:
    msg: >-
      [WARN] {{ inventory_hostname }}: compiler_rust_runtime benchmark exited
      rc={{ run_benchmarks_compiler_rust_runtime_result.rc }}.

- name: Warn on compiler_rust_external benchmark failure
  ansible.builtin.debug:
    msg: >-
      [WARN] {{ inventory_hostname }}: compiler_rust_external benchmark exited
      rc={{ run_benchmarks_compiler_rust_external_result.rc }}.
```

- [ ] **Step 6: Run task-content tests and commit**

Run: `uv run pytest tests/unit/test_compiler_rust_benchmarks.py -v`  
Expected: PASS.

```bash
git add roles/run_benchmarks/tasks/compiler.yml tests/unit/test_compiler_rust_benchmarks.py
git commit -m "feat: add rust runtime and external workload compiler benchmarks"
```

### Task 3: Wire new Rust outputs into report titles and expectations

**Files:**
- Modify: `scripts/generate_benchmark_report.py`
- Modify: `tests/unit/test_benchmark_report.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add new category titles**

```python
CATEGORY_TITLES = {
    # ...
    "compiler_rust": "Rust Compilation Speed",
    "compiler_rust_runtime": "Rust Runtime Performance",
    "compiler_rust_external": "Rust External Workload Performance",
    "compiler_go": "Go Compilation Speed",
    # ...
}
```

- [ ] **Step 2: Add report fixture coverage for new Rust output files**

```python
(host_dir / "compiler_rust_runtime.json").write_text(
    json.dumps(_make_hyperfine_json(("rustc-1.86.0-runtime", 0.35, 0.01)))
)
(host_dir / "compiler_rust_external.json").write_text(
    json.dumps(_make_hyperfine_json(("rustc-1.86.0-external", 0.48, 0.02)))
)
```

- [ ] **Step 3: Add assertions that markdown/html include new Rust sections**

```python
md = generate_markdown(hosts, table)
assert "Rust Runtime Performance" in md
assert "Rust External Workload Performance" in md

html = generate_html(hosts, table)
assert "Rust Runtime Performance" in html
assert "Rust External Workload Performance" in html
```

- [ ] **Step 4: Run targeted tests**

Run: `uv run pytest tests/unit/test_benchmark_report.py -k "rust or compiler" -v`  
Expected: PASS with new Rust runtime/external expectations.

- [ ] **Step 5: Commit report integration**

```bash
git add scripts/generate_benchmark_report.py tests/unit/test_benchmark_report.py
git commit -m "feat: report rust runtime and external compiler workloads"
```

### Task 4: Final verification and integration commit

**Files:**
- Modify: `changelogs/fragments/rust-compiler-benchmarks.yml`
- Test: `tests/unit/test_compiler_rust_benchmarks.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add changelog fragment for user-visible benchmark expansion**

```yaml
minor_changes:
  - "roles/run_benchmarks: expand Rust compiler benchmarking with runtime and external workload outputs (compiler_rust_runtime.json, compiler_rust_external.json)."
```

- [ ] **Step 2: Run focused unit tests**

Run: `uv run pytest tests/unit/test_compiler_rust_benchmarks.py tests/unit/test_benchmark_report.py -k "rust or compiler" -v`  
Expected: PASS.

- [ ] **Step 3: Run benchmark-role lint checks**

Run: `uv run ansible-lint roles/run_benchmarks/tasks/compiler.yml`  
Expected: PASS with no new lint violations.

- [ ] **Step 4: Commit final polish**

```bash
git add changelogs/fragments/rust-compiler-benchmarks.yml
git commit -m "docs: add changelog for rust compiler benchmark expansion"
```

- [ ] **Step 5: Push and monitor CI**

Run: `git push`  
Expected: push succeeds.

Run: `gh run list --limit 5`  
Expected: new CI run appears for branch.
