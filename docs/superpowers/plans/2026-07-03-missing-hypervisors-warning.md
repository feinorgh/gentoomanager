# Missing Hypervisors Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provisioning fail fast with a clear warning when `hypervisors.txt` is missing, while also surfacing a warning from `inventory_generator.py` for direct inventory calls.

**Architecture:** Add a preflight guard to `scripts/provision_benchmarks.sh` that enforces warn-and-exit behavior when file-based hypervisor inventory is unavailable and no `HYPERVISOR_HOSTS` override is set. Add a non-fatal warning in `inventory_generator.py` for the same missing-file condition so direct inventory users get diagnostics. Cover both entry points with focused unit tests.

**Tech Stack:** Bash wrapper script, Python inventory generator, pytest unit tests.

---

## File structure and responsibilities

- **Create:** `tests/unit/test_provision_benchmarks_sh.py`
  - Wrapper-level behavior tests for missing `hypervisors.txt` (warn + non-zero exit) and env override behavior.
- **Modify:** `scripts/provision_benchmarks.sh`
  - Add preflight check and explicit warning/error message for missing `hypervisors.txt`.
- **Modify:** `tests/unit/test_inventory_generator.py`
  - Add test coverage for missing `hypervisors.txt` warning behavior in `--list` mode.
- **Modify:** `inventory_generator.py`
  - Emit stderr warning when `hypervisors.txt` is missing and no `HYPERVISOR_HOSTS` is set.

### Task 1: Add failing wrapper-script tests for missing hypervisors file

**Files:**
- Create: `tests/unit/test_provision_benchmarks_sh.py`
- Test: `tests/unit/test_provision_benchmarks_sh.py`

- [ ] **Step 1: Create a wrapper test fixture with a temporary repo copy**

```python
from pathlib import Path
import os
import shutil
import stat
import subprocess

import pytest

SCRIPT_REL = Path("scripts/provision_benchmarks.sh")


@pytest.fixture()
def temp_repo(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    work = tmp_path / "repo"
    shutil.copytree(repo_root, work)
    return work
```

- [ ] **Step 2: Add failing test for missing hypervisors.txt (warn + non-zero exit)**

```python
def test_missing_hypervisors_file_exits_nonzero(temp_repo: Path) -> None:
    hv_file = temp_repo / "hypervisors.txt"
    if hv_file.exists():
        hv_file.unlink()

    result = subprocess.run(
        ["bash", str(temp_repo / SCRIPT_REL), "--manage-power"],
        cwd=temp_repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "hypervisors.txt" in result.stderr
    assert "hypervisors.txt.example" in result.stderr
```

- [ ] **Step 3: Add failing test for env override bypass**

```python
def test_env_override_allows_run_without_hypervisors_file(temp_repo: Path) -> None:
    hv_file = temp_repo / "hypervisors.txt"
    if hv_file.exists():
        hv_file.unlink()

    mock_ap = temp_repo / "ansible-playbook"
    mock_ap.write_text("#!/usr/bin/env bash\nexit 0\n")
    mock_ap.chmod(mock_ap.stat().st_mode | stat.S_IEXEC)

    env = {**os.environ, "PATH": f"{temp_repo}:{os.environ['PATH']}", "HYPERVISOR_HOSTS": "hv1"}
    result = subprocess.run(
        ["bash", str(temp_repo / SCRIPT_REL)],
        cwd=temp_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
```

- [ ] **Step 4: Run tests and confirm at least one fails before implementation**

Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py -v`
Expected: FAIL (missing-file check not implemented yet).

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/unit/test_provision_benchmarks_sh.py
git commit -m "test: cover missing hypervisors file in provisioning wrapper"
```

### Task 2: Implement wrapper preflight warn-and-exit behavior

**Files:**
- Modify: `scripts/provision_benchmarks.sh`
- Test: `tests/unit/test_provision_benchmarks_sh.py`

- [ ] **Step 1: Add a small preflight helper**

```bash
warn_missing_hypervisors_file() {
    local hv_file="${REPO_ROOT}/hypervisors.txt"
    if [[ -n "${HYPERVISOR_HOSTS:-}" ]]; then
        return 0
    fi
    if [[ ! -f "${hv_file}" ]]; then
        echo "WARNING: Missing required inventory source: ${hv_file}" >&2
        echo "Create it from the template and add hypervisor hostnames:" >&2
        echo "  cp ${REPO_ROOT}/hypervisors.txt.example ${hv_file}" >&2
        exit 2
    fi
}
```

- [ ] **Step 2: Invoke preflight before assembling/running ansible command**

```bash
cd "${REPO_ROOT}"
warn_missing_hypervisors_file
```

- [ ] **Step 3: Re-run wrapper tests and verify pass**

Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py -v`
Expected: PASS.

- [ ] **Step 4: Commit wrapper implementation**

```bash
git add scripts/provision_benchmarks.sh tests/unit/test_provision_benchmarks_sh.py
git commit -m "feat: warn and fail when hypervisors file is missing"
```

### Task 3: Add failing inventory warning test

**Files:**
- Modify: `tests/unit/test_inventory_generator.py`
- Test: `tests/unit/test_inventory_generator.py`

- [ ] **Step 1: Add subprocess-based test for missing hypervisors.txt warning**

```python
def test_inventory_warns_when_hypervisors_file_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    inv_script = repo_root / "inventory_generator.py"
    hv_file = repo_root / "hypervisors.txt"
    backup = None
    if hv_file.exists():
        backup = hv_file.read_text()
        hv_file.unlink()

    try:
        result = subprocess.run(
            [sys.executable, str(inv_script), "--list"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "hypervisors.txt" in result.stderr
    finally:
        if backup is not None:
            hv_file.write_text(backup)
```

- [ ] **Step 2: Run this test and confirm it fails before inventory change**

Run: `uv run pytest tests/unit/test_inventory_generator.py -k "warns_when_hypervisors_file_missing" -v`
Expected: FAIL.

- [ ] **Step 3: Commit failing inventory test**

```bash
git add tests/unit/test_inventory_generator.py
git commit -m "test: assert inventory warns when hypervisors file is missing"
```

### Task 4: Implement inventory warning and verify targeted suite

**Files:**
- Modify: `inventory_generator.py`
- Modify: `tests/unit/test_inventory_generator.py`

- [ ] **Step 1: Add explicit warning in missing-file fallback path**

```python
        else:
            hv_file = Path(__file__).parent / "hypervisors.txt"
            try:
                with open(hv_file) as f:
                    hosts_list = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                print(
                    f"WARNING: {hv_file} not found; dynamic inventory is empty. "
                    f"Set HYPERVISOR_HOSTS or create {hv_file} from hypervisors.txt.example.",
                    file=sys.stderr,
                )
                hosts_list = []
```

- [ ] **Step 2: Run focused tests**

Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py tests/unit/test_inventory_generator.py -v`
Expected: PASS.

- [ ] **Step 3: Run lint checks for changed Python test/code files**

Run: `uv run ruff check inventory_generator.py tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py`
Expected: PASS.

- [ ] **Step 4: Commit inventory warning implementation**

```bash
git add inventory_generator.py tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py
git commit -m "feat: warn on missing hypervisors inventory source"
```

## Final verification

- [ ] Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py tests/unit/test_inventory_generator.py`
- [ ] Run: `uv run ruff check inventory_generator.py tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py`
- [ ] Run representative manual check:
  - `./scripts/provision_benchmarks.sh --manage-power` with missing `hypervisors.txt` should print warning and exit non-zero.

