# BSD Portable Makefile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `compiler_multifile` generate and use a single portable Makefile that builds correctly on BSD and Linux while preserving benchmark comparability.

**Architecture:** Replace GNU-specific Makefile expressions in the multifile generator with explicit source/object lists emitted by Python. Keep benchmark orchestration (`make clean && make ... -j1/-jN`) unchanged so measured work remains equivalent. Preserve current hard-fail behavior and failure artifact logging.

**Tech Stack:** Python 3, Ansible role tasks, pytest, ansible-lint

---

### Task 1: Add failing portability tests first

**Files:**
- Modify: `tests/unit/test_multifile_harness_integrity.py`
- Test: `tests/unit/test_multifile_harness_integrity.py`

- [ ] **Step 1: Write the failing test**

Add this test near existing multifile integrity tests:

```python
def test_multifile_makefile_template_is_portable() -> None:
    content = _read("roles/run_benchmarks/files/generate_multifile_bench.py")
    assert "SRCS    := $(wildcard mod_*.c) main.c" not in content
    assert "OBJS    := $(SRCS:.c=.o)" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_multifile_harness_integrity.py::test_multifile_makefile_template_is_portable -v`  
Expected: `FAILED` because generator still contains GNU-style wildcard/substitution syntax.

- [ ] **Step 3: Commit failing test**

```bash
git add tests/unit/test_multifile_harness_integrity.py
git commit -m "tests: add failing portability check for multifile makefile" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement portable Makefile generation

**Files:**
- Modify: `roles/run_benchmarks/files/generate_multifile_bench.py`
- Modify: `tests/unit/test_multifile_harness_integrity.py`
- Test: `tests/unit/test_multifile_harness_integrity.py`

- [ ] **Step 1: Replace GNU-specific Makefile template with explicit lists**

Refactor template assembly so SRCS/OBJS are emitted concretely, for example:

```python
def _render_makefile(module_count: int) -> str:
    srcs = ["main.c", *[f"mod_{idx:02d}.c" for idx in range(module_count)]]
    objs = ["main.o", *[f"mod_{idx:02d}.o" for idx in range(module_count)]]
    return f"""\
# Auto-generated Makefile for multi-file compilation benchmark.
CC      ?= gcc
CFLAGS  ?= -O2
SRCS    = {' '.join(srcs)}
OBJS    = {' '.join(objs)}
BIN     := multifile_bench

.PHONY: all clean

all: $(BIN)

$(BIN): $(OBJS)
\t$(CC) $(CFLAGS) -o $@ $^ -lm

%.o: %.c
\t$(CC) $(CFLAGS) -c -o $@ $<

clean:
\t@rm -f $(OBJS) $(BIN)
"""
```

Then use `_render_makefile(args.modules)` when writing `Makefile`.

- [ ] **Step 2: Strengthen test to assert expected portable structure**

Extend the new test:

```python
def test_multifile_makefile_template_is_portable() -> None:
    content = _read("roles/run_benchmarks/files/generate_multifile_bench.py")
    assert "SRCS    := $(wildcard mod_*.c) main.c" not in content
    assert "OBJS    := $(SRCS:.c=.o)" not in content
    assert "SRCS    = {' '.join(srcs)}" in content
    assert "OBJS    = {' '.join(objs)}" in content
```

- [ ] **Step 3: Run tests to verify green**

Run: `uv run pytest tests/unit/test_multifile_harness_integrity.py -v`  
Expected: all tests pass.

- [ ] **Step 4: Commit implementation**

```bash
git add roles/run_benchmarks/files/generate_multifile_bench.py tests/unit/test_multifile_harness_integrity.py
git commit -m "fix: generate portable multifile makefile for BSD and Linux" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Verify runtime behavior and diagnostics

**Files:**
- Modify: `changelogs/fragments/bsd-portable-multifile-makefile.yml`
- Test/Run: benchmark wrapper + focused unit/lint commands

- [ ] **Step 1: Add changelog fragment**

Create `changelogs/fragments/bsd-portable-multifile-makefile.yml`:

```yaml
bugfixes:
  - "roles/run_benchmarks: generate a portable compiler_multifile Makefile so BSD and Linux use the same build graph without GNU make-only syntax."
```

- [ ] **Step 2: Run focused regression checks**

Run:

```bash
uv run pytest tests/unit/test_multifile_harness_integrity.py tests/unit/test_benchmark_failure_logging.py
uv run ansible-lint roles/run_benchmarks/tasks/compiler.yml playbooks/run_benchmarks.yml
```

Expected: both commands succeed.

- [ ] **Step 3: Re-run BSD compiler benchmark category to validate fix**

Run:

```bash
HYPERVISOR_HOSTS=adele,elise ./scripts/run_benchmarks.sh --host freebsd-luba --category compiler --manage-power
HYPERVISOR_HOSTS=adele,elise ./scripts/run_benchmarks.sh --host openbsd-penelope --category compiler --manage-power
```

Expected:
- `compiler_multifile_failure.json` is not produced for these hosts.
- `compiler_multifile.json` exists with successful results.
- run exits cleanly for compiler category on both BSD hosts.

- [ ] **Step 4: Commit verification/changelog**

```bash
git add changelogs/fragments/bsd-portable-multifile-makefile.yml
git commit -m "chore: document portable multifile makefile fix" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
