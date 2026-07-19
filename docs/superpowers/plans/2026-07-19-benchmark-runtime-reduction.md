# Benchmark Runtime Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce end-to-end benchmark runtime by ~25-35% while preserving statistically meaningful results and maintaining cross-host comparability.

**Architecture:** Introduce dedicated runtime-tuning defaults for the heaviest benchmark groups (crypto asymmetric, SSH signing, SQLite compile, compression, FFmpeg video). Wire these defaults into task files so tuning is explicit, documented, and overrideable via `-e`. Protect behavior with focused unit tests that assert both default values and task wiring.

**Tech Stack:** Ansible task YAML, Jinja templating, pytest, ruff, ansible-lint, shellcheck.

---

## File Structure

- Modify: `roles/run_benchmarks/defaults/main.yml`
  - Add dedicated runtime knobs for heavy benchmark sections.
- Modify: `roles/run_benchmarks/tasks/crypto.yml`
  - Use new per-section run/warmup vars and loop-iteration vars (replace hardcoded `N=1000` and global `runs/warmup` for heavy asymmetric blocks).
- Modify: `roles/run_benchmarks/tasks/compiler.yml`
  - Make SQLite optimization list configurable and drop `-O0` from default path.
- Modify: `docs/benchmarks.md`
  - Update defaults table and category text to reflect new runtime tuning.
- Create: `tests/unit/test_benchmark_runtime_tuning.py`
  - Assert new defaults exist and task files consume them.
- Create: `changelogs/fragments/benchmark-runtime-reduction.yml`
  - Document user-visible benchmark runtime change.

### Task 1: Add failing tests for runtime-tuning defaults and task wiring

**Files:**
- Create: `tests/unit/test_benchmark_runtime_tuning.py`
- Test: `tests/unit/test_benchmark_runtime_tuning.py`

- [ ] **Step 1: Write the failing test file**

```python
"""Tests for benchmark runtime tuning defaults and task wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = REPO_ROOT / "roles" / "run_benchmarks" / "defaults" / "main.yml"
CRYPTO_TASK = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "crypto.yml"
COMPILER_TASK = REPO_ROOT / "roles" / "run_benchmarks" / "tasks" / "compiler.yml"


def _defaults() -> dict:
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


def test_runtime_tuning_defaults_present() -> None:
    defaults = _defaults()
    assert defaults["run_benchmarks_crypto_asymmetric_runs"] == 3
    assert defaults["run_benchmarks_crypto_asymmetric_warmup"] == 1
    assert defaults["run_benchmarks_crypto_asymmetric_iterations"] == 500
    assert defaults["run_benchmarks_crypto_ssh_sign_runs"] == 3
    assert defaults["run_benchmarks_crypto_ssh_sign_warmup"] == 1
    assert defaults["run_benchmarks_crypto_ssh_sign_iterations"] == 500
    assert defaults["run_benchmarks_compression_runs"] == 2
    assert defaults["run_benchmarks_compression_warmup"] == 1
    assert defaults["run_benchmarks_ffmpeg_video_runs"] == 2
    assert defaults["run_benchmarks_ffmpeg_video_warmup"] == 1
    assert defaults["run_benchmarks_compiler_sqlite_opt_levels"] == ["-O2", "-O3"]


def test_crypto_task_uses_dedicated_runtime_tuning_vars() -> None:
    text = CRYPTO_TASK.read_text(encoding="utf-8")
    assert "N={{ run_benchmarks_crypto_asymmetric_iterations }}" in text
    assert "N={{ run_benchmarks_crypto_ssh_sign_iterations }}" in text
    assert "--runs {{ run_benchmarks_crypto_asymmetric_runs }}" in text
    assert "--warmup {{ run_benchmarks_crypto_asymmetric_warmup }}" in text
    assert "--runs {{ run_benchmarks_crypto_ssh_sign_runs }}" in text
    assert "--warmup {{ run_benchmarks_crypto_ssh_sign_warmup }}" in text


def test_compiler_task_uses_configurable_sqlite_opt_levels() -> None:
    text = COMPILER_TASK.read_text(encoding="utf-8")
    assert "run_benchmarks_compiler_sqlite_opt_levels" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_runtime_tuning.py -v`
Expected: FAIL with missing default keys / missing task wiring strings.

- [ ] **Step 3: Commit the failing-test checkpoint**

```bash
git add tests/unit/test_benchmark_runtime_tuning.py
git commit -m "tests: add runtime tuning expectations for benchmark tasks"
```

### Task 2: Implement heavy crypto runtime reductions (asymmetric + SSH signing)

**Files:**
- Modify: `roles/run_benchmarks/defaults/main.yml`
- Modify: `roles/run_benchmarks/tasks/crypto.yml`
- Test: `tests/unit/test_benchmark_runtime_tuning.py`

- [ ] **Step 1: Add dedicated crypto runtime tuning defaults**

```yaml
# Crypto asymmetric/signing tuning (heavy sections)
run_benchmarks_crypto_asymmetric_runs: 3
run_benchmarks_crypto_asymmetric_warmup: 1
run_benchmarks_crypto_asymmetric_iterations: 500

run_benchmarks_crypto_ssh_sign_runs: 3
run_benchmarks_crypto_ssh_sign_warmup: 1
run_benchmarks_crypto_ssh_sign_iterations: 500
```

- [ ] **Step 2: Replace hardcoded asymmetric loop count and run/warmup**

```yaml
# Before:
# N=1000
# --runs {{ run_benchmarks_runs }}
# --warmup {{ run_benchmarks_warmup }}

# After:
N={{ run_benchmarks_crypto_asymmetric_iterations }}
...
--runs {{ run_benchmarks_crypto_asymmetric_runs }} \
--warmup {{ run_benchmarks_crypto_asymmetric_warmup }} \
```

- [ ] **Step 3: Replace hardcoded SSH loop count and run/warmup**

```yaml
# Before:
# N=1000
# --runs {{ run_benchmarks_runs }}
# --warmup {{ run_benchmarks_warmup }}

# After:
N={{ run_benchmarks_crypto_ssh_sign_iterations }}
...
--runs {{ run_benchmarks_crypto_ssh_sign_runs }} \
--warmup {{ run_benchmarks_crypto_ssh_sign_warmup }} \
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_benchmark_runtime_tuning.py tests/unit/test_benchmark_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add roles/run_benchmarks/defaults/main.yml roles/run_benchmarks/tasks/crypto.yml tests/unit/test_benchmark_runtime_tuning.py
git commit -m "perf: shorten heavy crypto benchmark sections"
```

### Task 3: Reduce long compiler/compression/FFmpeg sections

**Files:**
- Modify: `roles/run_benchmarks/defaults/main.yml`
- Modify: `roles/run_benchmarks/tasks/compiler.yml`
- Test: `tests/unit/test_benchmark_runtime_tuning.py`

- [ ] **Step 1: Add/update defaults for long-running non-crypto sections**

```yaml
# Compression: deterministic codecs, fewer samples still stable
run_benchmarks_compression_runs: 2
run_benchmarks_compression_warmup: 1

# FFmpeg video encode/decode remains comparable with fewer rounds
run_benchmarks_ffmpeg_video_runs: 2
run_benchmarks_ffmpeg_video_warmup: 1

# SQLite compile: drop -O0 from default runtime path
run_benchmarks_compiler_sqlite_opt_levels:
  - "-O2"
  - "-O3"
```

- [ ] **Step 2: Wire compiler SQLite optimization list into task**

```yaml
# Before:
# for opt in "-O0" "-O2" "-O3"; do

# After:
for opt in {% for opt in run_benchmarks_compiler_sqlite_opt_levels %}"{{ opt }}" {% endfor %}; do
```

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest tests/unit/test_benchmark_runtime_tuning.py tests/unit/test_compiler_rust_benchmarks.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add roles/run_benchmarks/defaults/main.yml roles/run_benchmarks/tasks/compiler.yml tests/unit/test_benchmark_runtime_tuning.py
git commit -m "perf: reduce benchmark rounds for long-running categories"
```

### Task 4: Update docs and changelog for the new tuning model

**Files:**
- Modify: `docs/benchmarks.md`
- Create: `changelogs/fragments/benchmark-runtime-reduction.yml`

- [ ] **Step 1: Update benchmark docs (defaults and rationale)**

```markdown
- Document new defaults:
  - run_benchmarks_crypto_asymmetric_runs=3
  - run_benchmarks_crypto_asymmetric_warmup=1
  - run_benchmarks_crypto_asymmetric_iterations=500
  - run_benchmarks_crypto_ssh_sign_runs=3
  - run_benchmarks_crypto_ssh_sign_warmup=1
  - run_benchmarks_crypto_ssh_sign_iterations=500
  - run_benchmarks_compression_runs=2
  - run_benchmarks_ffmpeg_video_runs=2
  - run_benchmarks_compiler_sqlite_opt_levels=["-O2","-O3"]

- Update crypto section text to describe configurable iteration count
  (not hardcoded 1000) and explain default 500 tradeoff.
```

- [ ] **Step 2: Add changelog fragment**

```yaml
minor_changes:
  - "roles/run_benchmarks: reduced default runtime for long-running benchmark sections (crypto asymmetric/SSH signing, compression, ffmpeg video, sqlite compile) while preserving statistically stable sampling."
```

- [ ] **Step 3: Commit**

```bash
git add docs/benchmarks.md changelogs/fragments/benchmark-runtime-reduction.yml
git commit -m "docs: describe benchmark runtime tuning defaults"
```

### Task 5: Validation run and final integration commit

**Files:**
- Modify: none (verification only unless fixes are required)
- Test: `tests/unit/test_benchmark_runtime_tuning.py`

- [ ] **Step 1: Run targeted unit tests**

Run:
`uv run pytest tests/unit/test_benchmark_runtime_tuning.py tests/unit/test_compiler_rust_benchmarks.py tests/unit/test_run_benchmarks_defaults.py tests/unit/test_benchmark_report.py -v`

Expected: PASS

- [ ] **Step 2: Run benchmark-related lint checks**

Run:
`uv run ruff check tests/unit/`

Expected: PASS

- [ ] **Step 3: Run ansible-lint for changed role files**

Run:
`uv run ansible-lint roles/run_benchmarks/tasks/crypto.yml roles/run_benchmarks/tasks/compiler.yml roles/run_benchmarks/defaults/main.yml`

Expected: PASS

- [ ] **Step 4: Final commit if any validation-driven edits were needed**

```bash
git add -A
git commit -m "chore: finalize benchmark runtime reduction changes"
```

## Self-Review Checklist (completed by implementer)

- Spec coverage: all runtime-heavy categories identified in analysis are addressed by defaults + task wiring.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: variable names are consistent between defaults, tasks, tests, and docs.

