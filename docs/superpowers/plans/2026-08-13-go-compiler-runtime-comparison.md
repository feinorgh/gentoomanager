# Go compiler/runtime comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare standard Go and gccgo on both compile time and runtime, with each phase written to its own benchmark result file.

**Architecture:** Extend the existing compiler benchmark role so it discovers Go and gccgo toolchains, emits separate compile/runtime JSON artifacts for each, and keeps the runtime phase limited to executing already-built binaries. Update report generation, docs, and resume/skip logic so the new result files are visible everywhere the existing compiler categories already appear.

**Tech Stack:** Ansible YAML task files, hyperfine JSON output, Python report generation, pytest unit tests, ruff, ansible-lint, shellcheck, antsibull changelog fragments.

---

## File structure and responsibilities

- **Modify:** `roles/run_benchmarks/tasks/compiler.yml`
  - Add gccgo discovery, build/runtime split for Go, new result file names, and warning blocks.
- **Modify:** `roles/run_benchmarks/tasks/main.yml`
  - Update `skip-existing` handling so `compiler_go_runtime.json`, `compiler_gccgo.json`, and `compiler_gccgo_runtime.json` count toward completion when the relevant toolchains exist.
- **Modify:** `playbooks/run_benchmarks.yml`
  - Update `skip-complete` handling with the same result-file set used by `main.yml`.
- **Modify:** `scripts/generate_benchmark_report.py`
  - Add titles for the new result files and keep compiler-page rendering consistent.
- **Modify:** `docs/benchmarks.md`
  - Document the new Go/gccgo compile/runtime outputs and explain that runtime benchmarks measure the already-built binaries.
- **Create:** `tests/unit/test_go_compiler_runtime_benchmarks.py`
  - Assert compiler task wiring, skip logic, and gccgo/Go runtime result-file names.
- **Modify:** `tests/unit/test_benchmark_report.py`
  - Add coverage for the new category titles and gccgo label formatting.
- **Create:** `changelogs/fragments/go-compiler-runtime-comparison.yml`
  - Record the user-visible benchmark expansion.

## Task 1: Write failing tests for Go/gccgo split output and report labels

**Files:**
- Create: `tests/unit/test_go_compiler_runtime_benchmarks.py`
- Modify: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add a test file that locks down the task-file strings**

```python
"""Tests for Go and gccgo compiler/runtime benchmark wiring."""

from __future__ import annotations

from pathlib import Path

COMPILER_TASK = (
    Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"
)
MAIN_TASKS = Path(__file__).resolve().parents[2] / "roles" / "run_benchmarks" / "tasks" / "main.yml"
PLAYBOOK = Path(__file__).resolve().parents[2] / "playbooks" / "run_benchmarks.yml"


def test_compiler_task_exports_separate_go_and_gccgo_result_files() -> None:
    text = COMPILER_TASK.read_text(encoding="utf-8")
    assert "compiler_go.json" in text
    assert "compiler_go_runtime.json" in text
    assert "compiler_gccgo.json" in text
    assert "compiler_gccgo_runtime.json" in text
    assert "Run Go runtime benchmark" in text
    assert "Run gccgo compile benchmark" in text
    assert "Run gccgo runtime benchmark" in text


def test_skip_logic_accounts_for_new_go_result_files() -> None:
    for content in (
        MAIN_TASKS.read_text(encoding="utf-8"),
        PLAYBOOK.read_text(encoding="utf-8"),
    ):
        assert "compiler_go_runtime.json" in content
        assert "compiler_gccgo.json" in content
        assert "compiler_gccgo_runtime.json" in content
        assert "run_benchmarks_skip_existing_has_gccgo" in content


def test_compiler_task_labels_go_and_gccgo_runtime_commands() -> None:
    text = COMPILER_TASK.read_text(encoding="utf-8")
    assert '--command-name "{{ go_label }}-runtime"' in text
    assert '--command-name "{{ gccgo_label }}-compile"' in text
    assert '--command-name "{{ gccgo_label }}-runtime"' in text
```

- [ ] **Step 2: Add report assertions for new categories and gccgo labels**

```python
def test_category_titles_include_go_and_gccgo_runtime_outputs() -> None:
    assert CATEGORY_TITLES["compiler_go_runtime"] == "Go Runtime Performance"
    assert CATEGORY_TITLES["compiler_gccgo"] == "gccgo Compilation Speed"
    assert CATEGORY_TITLES["compiler_gccgo_runtime"] == "gccgo Runtime Performance"


def test_compiler_display_version_formats_gccgo_labels() -> None:
    assert _compiler_display_version("gccgo-14.3.0", "host-a", {}) == "gccgo 14.3.0"
    assert _sort_cc_label("gccgo-14.3.0") == ("gccgo", (14, 3, 0))
```

- [ ] **Step 3: Run the tests and verify they fail for the missing wiring**

Run: `uv run pytest tests/unit/test_go_compiler_runtime_benchmarks.py tests/unit/test_benchmark_report.py -v`

Expected: FAIL, because the new result files, task labels, and category titles do not exist yet.

- [ ] **Step 4: Commit the failing-test checkpoint**

```bash
git add tests/unit/test_go_compiler_runtime_benchmarks.py tests/unit/test_benchmark_report.py
git commit -m "tests: add Go and gccgo runtime comparison expectations"
```

## Task 2: Implement compiler task changes for Go and gccgo compile/runtime measurement

**Files:**
- Modify: `roles/run_benchmarks/tasks/compiler.yml`
- Modify: `roles/run_benchmarks/tasks/main.yml`
- Modify: `playbooks/run_benchmarks.yml`
- Test: `tests/unit/test_go_compiler_runtime_benchmarks.py`

- [ ] **Step 1: Add gccgo discovery alongside the existing Go toolchain discovery**

Use the same pattern the role already uses for `go`:

```yaml
- name: Discover gccgo toolchains
  ansible.builtin.shell:
    cmd: |
      set +e
      set -o pipefail
      {
        IFS=:
        for d in $PATH; do
          [ -d "$d" ] || continue
          for f in "$d"/gccgo-[0-9]* "$d"/gccgo[0-9]*; do
            [ -x "$f" ] || continue
            printf '%s %s\n' "$(basename "$f")" "$f"
          done
        done
        unset IFS
        full=$(command -v gccgo 2>/dev/null) || true
        [ -n "$full" ] && printf 'gccgo %s\n' "$full"
      } | while IFS=' ' read -r label path; do
          real=$({{ run_benchmarks_python_cmd }} -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$path" 2>/dev/null || echo "$path")
          printf '%s\t%s\t%s\n' "$real" "$label" "$path"
        done | sort -t$'\t' -k1,1 -u | awk -F'\t' '{print $2" "$3}'
```

Also update the existing availability probe near the top of `compiler.yml` from `for cmd in gcc clang rustc go; do` to include `gccgo`, and resolve the version with `gccgo --version` so the report labels normalize to `gccgo-X.Y.Z`. Keep the existing Go resolver unchanged except for any shared refactoring needed to reuse the same version-map output.

- [ ] **Step 2: Split the Go benchmark into compile-only and runtime-only result files**

Keep `compiler_go.json` for `go build`, then add a runtime task that builds each `go_label` binary once and benchmarks the binary itself:

```yaml
- name: Run Go compile benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/go_bench
      CMDS=()
      {% for go in run_benchmarks_go_resolved.stdout_lines | default([]) %}
      {% set go_parts = go.split() %}
      {% if go_parts | length >= 2 %}
      {% set go_label = go_parts[0] %}
      {% set go_exe = go_parts[1] %}
      if [ -x "{{ go_exe }}" ]; then
        CMDS+=(--command-name "{{ go_label }}-compile"
          "{{ go_exe }} build -o bench_{{ go_label }} .")
      fi
      {% endif %}
      {% endfor %}
      if [ -z "${CMDS[*]}" ]; then
        exit 0
      fi
      {{ run_benchmarks_hyperfine_bin }} \
        --runs {{ run_benchmarks_runs }} \
        --warmup {{ run_benchmarks_warmup }} \
        --ignore-failure \
        --prepare 'rm -f bench_*' \
        --export-json {{ run_benchmarks_work_dir }}/compiler_go.json \
        "${CMDS[@]}"
```

```yaml
- name: Run Go runtime benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/go_bench
      CMDS=()
      {% for go in run_benchmarks_go_resolved.stdout_lines | default([]) %}
      {% set go_parts = go.split() %}
      {% if go_parts | length >= 2 %}
      {% set go_label = go_parts[0] %}
      {% set go_exe = go_parts[1] %}
      if [ -x "{{ go_exe }}" ]; then
        "{{ go_exe }}" build -o bench_{{ go_label }} .
        CMDS+=(--command-name "{{ go_label }}-runtime" "./bench_{{ go_label }}")
      fi
      {% endif %}
      {% endfor %}
      if [ -z "${CMDS[*]}" ]; then
        exit 0
      fi
      {{ run_benchmarks_hyperfine_bin }} \
        --runs {{ run_benchmarks_runs }} \
        --warmup {{ run_benchmarks_warmup }} \
        --ignore-failure \
        --export-json {{ run_benchmarks_work_dir }}/compiler_go_runtime.json \
        "${CMDS[@]}"
```

The runtime task must execute already-built binaries only; it must not compile inside `hyperfine`.

- [ ] **Step 3: Add gccgo compile and runtime benchmark tasks with separate result files**

Use the same shape as the Go tasks, but compile with `gccgo -O2` and run the resulting binary:

```yaml
- name: Run gccgo compile benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/go_bench
      CMDS=()
      {% for gccgo in run_benchmarks_gccgo_resolved.stdout_lines | default([]) %}
      {% set gccgo_parts = gccgo.split() %}
      {% if gccgo_parts | length >= 2 %}
      {% set gccgo_label = gccgo_parts[0] %}
      {% set gccgo_exe = gccgo_parts[1] %}
      if [ -x "{{ gccgo_exe }}" ]; then
        CMDS+=(--command-name "{{ gccgo_label }}-compile"
          "{{ gccgo_exe }} -O2 -o bench_{{ gccgo_label }} main.go")
      fi
      {% endif %}
      {% endfor %}
      if [ -z "${CMDS[*]}" ]; then
        exit 0
      fi
      {{ run_benchmarks_hyperfine_bin }} \
        --runs {{ run_benchmarks_runs }} \
        --warmup {{ run_benchmarks_warmup }} \
        --ignore-failure \
        --prepare 'rm -f bench_*' \
        --export-json {{ run_benchmarks_work_dir }}/compiler_gccgo.json \
        "${CMDS[@]}"
```

```yaml
- name: Run gccgo runtime benchmark
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      cd {{ run_benchmarks_work_dir }}/go_bench
      CMDS=()
      {% for gccgo in run_benchmarks_gccgo_resolved.stdout_lines | default([]) %}
      {% set gccgo_parts = gccgo.split() %}
      {% if gccgo_parts | length >= 2 %}
      {% set gccgo_label = gccgo_parts[0] %}
      {% set gccgo_exe = gccgo_parts[1] %}
      if [ -x "{{ gccgo_exe }}" ]; then
        "{{ gccgo_exe }}" -O2 -o bench_{{ gccgo_label }} main.go
        CMDS+=(--command-name "{{ gccgo_label }}-runtime" "./bench_{{ gccgo_label }}")
      fi
      {% endif %}
      {% endfor %}
      if [ -z "${CMDS[*]}" ]; then
        exit 0
      fi
      {{ run_benchmarks_hyperfine_bin }} \
        --runs {{ run_benchmarks_runs }} \
        --warmup {{ run_benchmarks_warmup }} \
        --ignore-failure \
        --export-json {{ run_benchmarks_work_dir }}/compiler_gccgo_runtime.json \
        "${CMDS[@]}"
```

Keep the existing non-fatal warning pattern:

```yaml
- name: Warn on compiler_gccgo benchmark failure
- name: Warn on compiler_gccgo_runtime benchmark failure
```

- [ ] **Step 4: Extend skip-existing and skip-complete logic to include the new result files**

Update the compiler optional list in both `roles/run_benchmarks/tasks/main.yml` and `playbooks/run_benchmarks.yml` so `compiler` only counts as complete when the relevant files exist for the toolchains actually present:

```yaml
{%- set compiler_optional = (
     (['compiler_rust.json', 'compiler_rust_runtime.json', 'compiler_rust_external.json']
      if run_benchmarks_skip_existing_has_rustc | default(false) else [])
     +
     (['compiler_go.json', 'compiler_go_runtime.json']
      if run_benchmarks_skip_existing_has_go | default(false) else [])
     +
     (['compiler_gccgo.json', 'compiler_gccgo_runtime.json']
      if run_benchmarks_skip_existing_has_gccgo | default(false) else [])
   ) -%}
```

Add the corresponding `command -v gccgo` probe and `run_benchmarks_skip_existing_has_gccgo` fact alongside the existing Go/Rust availability checks.

In `playbooks/run_benchmarks.yml`, mirror the same availability probe with `run_benchmarks_preflight_has_gccgo` so the controller-side skip-complete filter can count `compiler_gccgo.json` and `compiler_gccgo_runtime.json` only when gccgo is actually present.

- [ ] **Step 5: Run the targeted tests and verify they still fail before the next step**

Run: `uv run pytest tests/unit/test_go_compiler_runtime_benchmarks.py tests/unit/test_benchmark_report.py -v`

Expected: FAIL until the compiler task and skip logic are updated.

- [ ] **Step 6: Commit the compiler-task implementation checkpoint**

```bash
git add roles/run_benchmarks/tasks/compiler.yml roles/run_benchmarks/tasks/main.yml playbooks/run_benchmarks.yml
git commit -m "feat: add Go and gccgo runtime benchmark splits"
```

## Task 3: Update report generation, documentation, and changelog

**Files:**
- Modify: `scripts/generate_benchmark_report.py`
- Modify: `docs/benchmarks.md`
- Create: `changelogs/fragments/go-compiler-runtime-comparison.yml`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add the new category titles to the report generator**

Extend `CATEGORY_TITLES` so the report can render the new result files with explicit labels:

```python
CATEGORY_TITLES = {
    "compiler_go": "Go Compilation Speed",
    "compiler_go_runtime": "Go Runtime Performance",
    "compiler_gccgo": "gccgo Compilation Speed",
    "compiler_gccgo_runtime": "gccgo Runtime Performance",
}
```

Keep the compiler page grouping unchanged; the new categories should still fall under the existing compiler page because they share the `compiler` prefix.

- [ ] **Step 2: Keep the label-formatting helpers aligned with the new gccgo labels**

The plan is to normalize gccgo toolchains to `gccgo-X.Y.Z`, which means the existing generic compiler version formatter can stay simple. If the implementation discovers a non-versioned gccgo label, update `_compiler_display_version()` and `_sort_cc_label()` to treat it like the existing `go1.X.Y` path rather than adding a new reporting branch.

- [ ] **Step 3: Document the new output files and the runtime-vs-compile split**

Update the compiler section in `docs/benchmarks.md` so it explains:

```markdown
- `compiler_go.json` measures `go build` compile time.
- `compiler_go_runtime.json` measures the runtime of the Go-built binary.
- `compiler_gccgo.json` measures gccgo compile time when gccgo is installed.
- `compiler_gccgo_runtime.json` measures the runtime of the gccgo-built binary.
- gccgo is optional and is skipped cleanly when not present on the host.
```

Also update the results summary so the new files are listed alongside the existing compiler outputs.

- [ ] **Step 4: Add a changelog fragment for the user-visible benchmark expansion**

```yaml
minor_changes:
  - "roles/run_benchmarks: split Go benchmarking into compile/runtime result files and add optional gccgo compile/runtime coverage when gccgo is available."
```

- [ ] **Step 5: Run the focused report tests and verify they pass after implementation**

Run: `uv run pytest tests/unit/test_benchmark_report.py tests/unit/test_go_compiler_runtime_benchmarks.py -v`

Expected: PASS once the report titles, labels, and task wiring are in place.

- [ ] **Step 6: Commit the reporting/docs checkpoint**

```bash
git add scripts/generate_benchmark_report.py docs/benchmarks.md changelogs/fragments/go-compiler-runtime-comparison.yml tests/unit/test_benchmark_report.py
git commit -m "docs: describe Go and gccgo runtime comparison outputs"
```

## Task 4: Final validation and cleanup

**Files:**
- Test only, unless a final adjustment is needed

- [ ] **Step 1: Run the targeted benchmark-report and compiler wiring tests**

Run:

```bash
uv run pytest tests/unit/test_go_compiler_runtime_benchmarks.py tests/unit/test_benchmark_report.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the existing Python and Ansible checks that cover the touched files**

Run:

```bash
uv run ruff check scripts/ tests/unit/
uv run ruff format --check scripts/ tests/unit/
uv run ansible-lint roles/run_benchmarks/tasks/compiler.yml roles/run_benchmarks/tasks/main.yml playbooks/run_benchmarks.yml
uv run python scripts/shellcheck_yaml_blocks.py
```

Expected: PASS with no new warnings in the touched files.

- [ ] **Step 3: Fix any failures inline and rerun only the failing command**

If a check fails, adjust the touched file directly and rerun just that command until it passes. Do not broaden the validation set unless the failure shows a shared regression.

- [ ] **Step 4: Commit the final implementation**

```bash
git add roles/run_benchmarks/tasks/compiler.yml roles/run_benchmarks/tasks/main.yml playbooks/run_benchmarks.yml scripts/generate_benchmark_report.py docs/benchmarks.md tests/unit/test_go_compiler_runtime_benchmarks.py tests/unit/test_benchmark_report.py changelogs/fragments/go-compiler-runtime-comparison.yml
git commit -m "feat: compare Go and gccgo compile and runtime performance"
```

## Coverage check

- Compile/runtime split for standard Go: **Task 2**
- Optional gccgo support: **Task 2**
- Skip-complete and skip-existing updates: **Task 2**
- Report titles and label formatting: **Task 3**
- Docs and changelog: **Task 3**
- Validation commands: **Task 4**
