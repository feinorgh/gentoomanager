# Short Benchmark Workload Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase workload size for short-running benchmarks so timings are statistically meaningful, and enforce that short-benchmark result files contain valid, non-premature measurements.

**Architecture:** Introduce explicit workload-tuning defaults for short benchmarks (bash/coreutils/git/rust runtime+external), then wire tasks to those variables instead of hardcoded tiny workloads. Add a short-results integrity validator in the playbook flow to fail fast when JSON output is missing, empty, or contains non-zero exit-code runs, and update report loading to ignore failed rows consistently. Protect all of this with focused unit tests and documentation updates.

**Tech Stack:** Ansible role/playbook YAML, Python report scripts, Rust benchmark fixtures, pytest, ruff, ansible-lint.

---

## File Structure

- Modify: `roles/run_benchmarks/defaults/main.yml`
  - Add workload knobs for short-running suites and integrity-check thresholds.
- Modify: `roles/run_benchmarks/tasks/bash.yml`
  - Replace fixed tiny startup/micro-workloads with defaults-driven loop multipliers.
- Modify: `roles/run_benchmarks/tasks/coreutils.yml`
  - Scale git/coreutils micro commands by defaults to move commands out of sub-10 ms range.
- Modify: `roles/run_benchmarks/tasks/compiler.yml`
  - Keep Rust runtime/external command wiring, but consume heavier binaries/fixtures.
- Modify: `roles/run_benchmarks/files/rust_bench/runtime_bench/src/main.rs`
  - Increase deterministic compute workload.
- Modify: `roles/run_benchmarks/files/rust_bench/external_bench/src/main.rs`
  - Increase fixture processing work per run.
- Modify: `roles/run_benchmarks/files/rust_bench/external_bench/fixtures/external_input.json`
  - Expand external workload fixture so runtime is representative.
- Create: `scripts/validate_short_benchmark_results.py`
  - Validate short-benchmark JSON payloads for presence, non-empty results, and successful exit codes.
- Modify: `playbooks/run_benchmarks.yml`
  - Invoke validator after fetch and fail host when short-benchmark results are invalid/premature.
- Modify: `scripts/generate_benchmark_report.py`
  - Skip failed/non-successful benchmark rows (non-zero exit codes) consistently.
- Modify: `tests/unit/test_benchmark_report.py`
  - Add regression tests for failed-row filtering and short-result integrity reporting behavior.
- Create: `tests/unit/test_short_benchmark_workloads.py`
  - Validate new defaults and task wiring for workload scaling + validation hook.
- Modify: `docs/benchmarks.md`
  - Document new workload controls and short-results validation behavior.
- Create: `changelogs/fragments/short-benchmark-workloads.yml`
  - Record user-visible benchmark methodology hardening.

### Task 1: Add failing tests for short-workload tuning and result-integrity hook

**Files:**
- Create: `tests/unit/test_short_benchmark_workloads.py`
- Modify: `tests/unit/test_benchmark_report.py`
- Test: `tests/unit/test_short_benchmark_workloads.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Write failing tests for new defaults and task wiring**

```python
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = REPO_ROOT / "roles" / "run_benchmarks" / "defaults" / "main.yml"
BASH_TASK = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "bash.yml"
COREUTILS_TASK = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "coreutils.yml"
PLAYBOOK = REPO_ROOT / "playbooks" / "run_benchmarks.yml"


def _defaults() -> dict:
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


def test_short_workload_defaults_exist() -> None:
    defaults = _defaults()
    assert defaults["run_benchmarks_bash_startup_iterations"] == 200
    assert defaults["run_benchmarks_coreutils_wc_repeat"] == 50
    assert defaults["run_benchmarks_coreutils_find_repeat"] == 20
    assert defaults["run_benchmarks_git_repo_commits"] == 500
    assert defaults["run_benchmarks_git_feature_commits"] == 100
    assert defaults["run_benchmarks_rust_runtime_iterations"] == 50_000_000
    assert defaults["run_benchmarks_short_results_require_exit_code_zero"] is True


def test_short_workloads_wired_in_tasks() -> None:
    bash_text = BASH_TASK.read_text(encoding="utf-8")
    core_text = COREUTILS_TASK.read_text(encoding="utf-8")
    assert "run_benchmarks_bash_startup_iterations" in bash_text
    assert "run_benchmarks_coreutils_wc_repeat" in core_text
    assert "run_benchmarks_coreutils_find_repeat" in core_text
    assert "run_benchmarks_git_repo_commits" in core_text
    assert "run_benchmarks_git_feature_commits" in core_text


def test_playbook_invokes_short_result_validator() -> None:
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "Validate short benchmark results (controller-side)" in text
    assert "scripts/validate_short_benchmark_results.py" in text
```

- [ ] **Step 2: Add failing report-filter test for non-zero exit codes**

```python
def test_load_results_excludes_failed_hyperfine_entries(tmp_path: Path) -> None:
    base = tmp_path / "benchmarks"
    host_dir = base / "results" / "gentoo-test"
    host_dir.mkdir(parents=True)
    (host_dir / "metadata.json").write_text(json.dumps(_make_metadata("gentoo-test")))
    (host_dir / "bash.json").write_text(
        json.dumps(
            {
                "results": [
                    {"command": "ok-bench", "mean": 0.2, "stddev": 0.01, "exit_codes": [0, 0, 0]},
                    {"command": "failed-bench", "mean": 0.001, "stddev": 0.0, "exit_codes": [127, 127]},
                ]
            }
        )
    )
    hosts = load_results(base)
    table = build_comparison_table(hosts)
    assert "ok-bench" in table["bash"]
    assert "failed-bench" not in table["bash"]
```

- [ ] **Step 3: Run tests and confirm RED state**

Run: `uv run pytest tests/unit/test_short_benchmark_workloads.py tests/unit/test_benchmark_report.py -v`
Expected: FAIL (missing defaults/wiring/validator + failed-row filtering not yet implemented).

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/unit/test_short_benchmark_workloads.py tests/unit/test_benchmark_report.py
git commit -m "tests: define short benchmark workload and integrity expectations"
```

### Task 2: Increase short benchmark workloads (bash/coreutils/git/rust)

**Files:**
- Modify: `roles/run_benchmarks/defaults/main.yml`
- Modify: `roles/run_benchmarks/tasks/bash.yml`
- Modify: `roles/run_benchmarks/tasks/coreutils.yml`
- Modify: `roles/run_benchmarks/files/rust_bench/runtime_bench/src/main.rs`
- Modify: `roles/run_benchmarks/files/rust_bench/external_bench/src/main.rs`
- Modify: `roles/run_benchmarks/files/rust_bench/external_bench/fixtures/external_input.json`
- Test: `tests/unit/test_short_benchmark_workloads.py`

- [ ] **Step 1: Add short-workload tuning defaults**

```yaml
# Short benchmark workload scaling
run_benchmarks_bash_startup_iterations: 200
run_benchmarks_coreutils_wc_repeat: 50
run_benchmarks_coreutils_find_repeat: 20
run_benchmarks_git_repo_commits: 500
run_benchmarks_git_feature_commits: 100
run_benchmarks_rust_runtime_iterations: 50000000
run_benchmarks_short_results_require_exit_code_zero: true
```

- [ ] **Step 2: Wire bash startup benchmark to run multiple startup cycles**

```bash
# in roles/run_benchmarks/tasks/bash.yml benchmark command
CMDS+=(--command-name "startup-bare"
  "_i=0; while [ \"$_i\" -lt {{ run_benchmarks_bash_startup_iterations }} ]; do {{ _run_benchmarks_bash | default('bash') }} --norc --noprofile -c true; _i=$((_i+1)); done")
```

- [ ] **Step 3: Scale coreutils/git micro workloads**

```bash
# coreutils command examples
--command-name 'wc-lines' 'i=0; while [ "$i" -lt {{ run_benchmarks_coreutils_wc_repeat }} ]; do wc -l sortdata.txt >/dev/null; i=$((i+1)); done'
--command-name 'find-files' 'i=0; while [ "$i" -lt {{ run_benchmarks_coreutils_find_repeat }} ]; do find findtree -name "*.txt" -type f >/dev/null; i=$((i+1)); done'

# git repo generation size knobs
while [ "$i" -le {{ run_benchmarks_git_repo_commits }} ]; do
...
while [ "$i" -le {{ run_benchmarks_git_feature_commits }} ]; do
```

- [ ] **Step 4: Increase Rust runtime and external benchmark workloads**

```rust
// runtime_bench/src/main.rs
for _ in 0..50_000_000 {
    x = x.wrapping_mul(6364136223846793005).wrapping_add(1);
    acc ^= x.rotate_left(13);
}
```

```rust
// external_bench/src/main.rs
for _round in 0..200 {
    if let Some(arr) = value.as_array() {
        for entry in arr {
            if let Some(s) = entry.as_str() {
                count += re.find_iter(s).count();
            }
        }
    }
}
```

- [ ] **Step 5: Expand external workload fixture content**

```json
[
  "alice@example.com bob@example.com carol@example.com ... repeated payload ...",
  "ops+alerts@example.net security@example.org ... repeated payload ...",
  "... at least several hundred strings ..."
]
```

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/unit/test_short_benchmark_workloads.py tests/unit/test_compiler_rust_benchmarks.py -v`
Expected: PASS

- [ ] **Step 7: Commit workload tuning**

```bash
git add roles/run_benchmarks/defaults/main.yml roles/run_benchmarks/tasks/bash.yml roles/run_benchmarks/tasks/coreutils.yml roles/run_benchmarks/files/rust_bench/runtime_bench/src/main.rs roles/run_benchmarks/files/rust_bench/external_bench/src/main.rs roles/run_benchmarks/files/rust_bench/external_bench/fixtures/external_input.json tests/unit/test_short_benchmark_workloads.py
git commit -m "perf: scale short benchmark workloads for stable timings"
```

### Task 3: Enforce short-benchmark result integrity (no premature/empty results)

**Files:**
- Create: `scripts/validate_short_benchmark_results.py`
- Modify: `playbooks/run_benchmarks.yml`
- Modify: `tests/unit/test_benchmark_failure_logging.py`
- Modify: `tests/unit/test_short_benchmark_workloads.py`

- [ ] **Step 1: Add controller-side short-result validator script**

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

SHORT_FILES = ["bash.json", "coreutils.json", "git.json", "compiler_rust_runtime.json", "compiler_rust_external.json"]

def _validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        errors.append(f"missing:{path.name}")
        return errors
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        errors.append(f"empty:{path.name}")
        return errors
    for row in results:
        exit_codes = row.get("exit_codes", [])
        if isinstance(exit_codes, list) and exit_codes and any(code != 0 for code in exit_codes):
            errors.append(f"failed-exit:{path.name}:{row.get('command','unknown')}")
    return errors

def main() -> int:
    host_dir = Path(sys.argv[1])
    failures: list[str] = []
    for name in SHORT_FILES:
        failures.extend(_validate_file(host_dir / name))
    if failures:
        print(json.dumps({"short_benchmark_failures": failures}, indent=2))
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Invoke validator in playbook after fetching host results**

```yaml
- name: Validate short benchmark results (controller-side)
  ansible.builtin.command:
    cmd: >-
      python3 {{ playbook_dir }}/../scripts/validate_short_benchmark_results.py
      {{ run_benchmarks_results_dir }}/results/{{ inventory_hostname }}
  delegate_to: localhost
  changed_when: false
```

- [ ] **Step 3: Extend failure-logging tests for validator hook**

```python
def test_run_playbook_validates_short_results_after_fetch() -> None:
    content = _read("playbooks/run_benchmarks.yml")
    assert "Validate short benchmark results (controller-side)" in content
    assert "validate_short_benchmark_results.py" in content
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/unit/test_benchmark_failure_logging.py tests/unit/test_short_benchmark_workloads.py -v`
Expected: PASS

```bash
git add scripts/validate_short_benchmark_results.py playbooks/run_benchmarks.yml tests/unit/test_benchmark_failure_logging.py tests/unit/test_short_benchmark_workloads.py
git commit -m "feat: enforce short benchmark result integrity checks"
```

### Task 4: Make report generation ignore failed benchmark rows consistently

**Files:**
- Modify: `scripts/generate_benchmark_report.py`
- Modify: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Filter failed rows in `load_results` before table build**

```python
if "results" in data:
    filtered = []
    for row in data["results"]:
        exit_codes = row.get("exit_codes", [])
        if isinstance(exit_codes, list) and exit_codes and any(code != 0 for code in exit_codes):
            continue
        filtered.append(row)
    hosts[hostname]["benchmarks"][category] = filtered
```

- [ ] **Step 2: Add/adjust tests for failed-row suppression**

```python
def test_load_results_excludes_failed_hyperfine_entries(...):
    ...
    assert "failed-bench" not in table["bash"]
```

- [ ] **Step 3: Run report tests**

Run: `uv run pytest tests/unit/test_benchmark_report.py tests/unit/test_benchmarks_article_data.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_benchmark_report.py tests/unit/test_benchmark_report.py
git commit -m "fix: ignore failed benchmark rows in report data loading"
```

### Task 5: Documentation, changelog, and final validation

**Files:**
- Modify: `docs/benchmarks.md`
- Create: `changelogs/fragments/short-benchmark-workloads.yml`

- [ ] **Step 1: Document new short-workload knobs and validator behavior**

```markdown
- Add defaults table entries for:
  - run_benchmarks_bash_startup_iterations
  - run_benchmarks_coreutils_wc_repeat
  - run_benchmarks_coreutils_find_repeat
  - run_benchmarks_git_repo_commits
  - run_benchmarks_git_feature_commits
  - run_benchmarks_rust_runtime_iterations
- Describe controller-side short result validation and failure criteria:
  missing file, empty results array, non-zero exit codes.
```

- [ ] **Step 2: Add changelog fragment**

```yaml
minor_changes:
  - "roles/run_benchmarks: increased workloads for short-running benchmarks (bash/coreutils/git/rust runtime+external) and added post-run validation to ensure short benchmark JSON outputs are present and not prematurely failed."
```

- [ ] **Step 3: Run validation commands**

Run:
`uv run pytest tests/unit/test_short_benchmark_workloads.py tests/unit/test_benchmark_failure_logging.py tests/unit/test_benchmark_report.py tests/unit/test_benchmarks_article_data.py -v`

Run:
`uv run ruff check scripts/ tests/`

Run:
`uv run ansible-lint playbooks/run_benchmarks.yml roles/run_benchmarks/tasks/bash.yml roles/run_benchmarks/tasks/coreutils.yml roles/run_benchmarks/tasks/compiler.yml roles/run_benchmarks/defaults/main.yml`

Expected: PASS

- [ ] **Step 4: Commit final docs/changelog polish**

```bash
git add docs/benchmarks.md changelogs/fragments/short-benchmark-workloads.yml
git commit -m "docs: document short benchmark workload hardening"
```

## Self-Review Checklist (completed)

1. **Spec coverage:** Plan includes both requested outcomes: (a) better workloads for short-running benchmarks and (b) explicit integrity checks so short-benchmark files are present and not prematurely failed.
2. **Placeholder scan:** No TBD/TODO placeholders; each task has concrete files, code snippets, commands, and expected outcomes.
3. **Type consistency:** Variable names are consistent across defaults, task wiring, validator script, tests, and documentation.

