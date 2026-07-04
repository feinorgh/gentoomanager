# SSH Connectivity Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add actionable SSH connectivity warnings on both inventory-query and provisioning failure surfaces so users are prompted to check SSH key distribution and `~/.ssh/config` host entries.

**Architecture:** Add lightweight pattern-based diagnostics without changing provisioning semantics. In `inventory_generator.py`, classify SSH stderr failures and append targeted warnings after the existing error line. In `scripts/provision_benchmarks.sh`, stream ansible output unchanged while appending the same warning block on matching `UNREACHABLE` SSH failure lines, preserving exit code behavior.

**Tech Stack:** Python 3, Bash, pytest, ruff.

---

## File structure and responsibilities

- **Modify:** `inventory_generator.py`
  - Add SSH failure pattern matcher and warning formatter used in host-query failure path.
- **Modify:** `scripts/provision_benchmarks.sh`
  - Add ansible output line filter that appends SSH guidance warnings for matching failures.
- **Modify:** `tests/unit/test_inventory_generator.py`
  - Add unit tests for matcher/formatter behavior and warning emission.
- **Modify:** `tests/unit/test_provision_benchmarks_sh.py`
  - Add wrapper tests for unreachable-output hinting and exit-code preservation.

### Task 1: Add failing inventory warning tests

**Files:**
- Modify: `tests/unit/test_inventory_generator.py`
- Test: `tests/unit/test_inventory_generator.py`

- [ ] **Step 1: Write failing tests for SSH hint classification**

```python
class TestBuildSshFailureHints:
    def test_publickey_failure_includes_key_and_ssh_config_hints(self) -> None:
        hints = inv.build_ssh_failure_hints(
            "openindiana-indiana",
            "Permission denied (publickey).",
        )
        joined = "\n".join(hints)
        assert "SSH public key" in joined
        assert "~/.ssh/config" in joined

    def test_host_key_failure_includes_known_hosts_hint_only(self) -> None:
        hints = inv.build_ssh_failure_hints(
            "openindiana-indiana",
            "Host key verification failed.",
        )
        joined = "\n".join(hints)
        assert "host key verification" in joined.lower()
        assert "~/.ssh/config" in joined

    def test_unrelated_stderr_produces_no_hints(self) -> None:
        assert inv.build_ssh_failure_hints("openindiana-indiana", "some other error") == []
```

- [ ] **Step 2: Run focused test selector to verify RED**

Run: `uv run pytest tests/unit/test_inventory_generator.py -k "BuildSshFailureHints" -v`  
Expected: FAIL (`AttributeError` because helper does not exist yet).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/unit/test_inventory_generator.py
git commit -m "test: add ssh failure hint coverage for inventory errors"
```

### Task 2: Implement inventory SSH warnings and make tests pass

**Files:**
- Modify: `inventory_generator.py`
- Modify: `tests/unit/test_inventory_generator.py`
- Test: `tests/unit/test_inventory_generator.py`

- [ ] **Step 1: Add helper for SSH failure hint formatting**

```python
def build_ssh_failure_hints(host: str, stderr: str) -> list[str]:
    text = (stderr or "").lower()
    hints: list[str] = []
    if (
        "permission denied (publickey)" in text
        or "connection closed" in text
        or "failed to connect to the host via ssh" in text
    ):
        hints.append(
            f"WARNING: SSH authentication/connectivity failed for {host}. "
            "Check that your SSH public key is installed on the target host."
        )
        hints.append(
            "WARNING: Also verify the host is defined in ~/.ssh/config (or equivalent SSH config)."
        )
    elif "host key verification failed" in text:
        hints.append(
            f"WARNING: Host key verification failed for {host}. "
            "Check known_hosts trust and ensure host mapping in ~/.ssh/config is correct."
        )
    return hints
```

- [ ] **Step 2: Call helper in host query exception path**

```python
except subprocess.CalledProcessError as exc:
    stderr = exc.stderr or ""
    print(f"Error querying host {host}: {stderr}", file=sys.stderr)
    for hint in build_ssh_failure_hints(host, stderr):
        print(hint, file=sys.stderr)
    return []
```

- [ ] **Step 3: Re-run targeted tests**

Run: `uv run pytest tests/unit/test_inventory_generator.py -k "BuildSshFailureHints" -v`  
Expected: PASS.

- [ ] **Step 4: Run full inventory unit suite**

Run: `uv run pytest tests/unit/test_inventory_generator.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit implementation**

```bash
git add inventory_generator.py tests/unit/test_inventory_generator.py
git commit -m "feat: add ssh troubleshooting hints for inventory connection failures"
```

### Task 3: Add failing wrapper warning-filter tests

**Files:**
- Modify: `tests/unit/test_provision_benchmarks_sh.py`
- Test: `tests/unit/test_provision_benchmarks_sh.py`

- [ ] **Step 1: Add failing wrapper test for UNREACHABLE SSH line hinting**

```python
def test_unreachable_ssh_output_includes_hint_messages(wrapper_repo_copy: Path) -> None:
    failing_ansible = (
        "#!/usr/bin/env bash\n"
        "echo 'fatal: [openindiana-indiana]: UNREACHABLE! => "
        "{\"msg\": \"Failed to connect to the host via ssh: Permission denied (publickey).\"}'\n"
        "exit 4\n"
    )
    result, _ = run_wrapper(wrapper_repo_copy, ansible_playbook_content=failing_ansible)
    stderr = result.stderr
    assert result.returncode != 0
    assert "SSH public key" in stderr
    assert "~/.ssh/config" in stderr
```

- [ ] **Step 2: Add failing wrapper test for non-SSH failure no extra hint**

```python
def test_non_ssh_failure_does_not_emit_ssh_hint(wrapper_repo_copy: Path) -> None:
    failing_ansible = (
        "#!/usr/bin/env bash\n"
        "echo 'fatal: [openindiana-indiana]: FAILED! => {\"msg\": \"package install failed\"}'\n"
        "exit 2\n"
    )
    result, _ = run_wrapper(wrapper_repo_copy, ansible_playbook_content=failing_ansible)
    stderr = result.stderr
    assert result.returncode != 0
    assert "SSH public key" not in stderr
```

- [ ] **Step 3: Run focused wrapper tests to verify RED**

Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py -k "ssh_output_includes_hint_messages or non_ssh_failure_does_not_emit_ssh_hint" -v`  
Expected: FAIL (filter not implemented yet).

- [ ] **Step 4: Commit failing wrapper tests**

```bash
git add tests/unit/test_provision_benchmarks_sh.py
git commit -m "test: cover provisioning ssh unreachable hint diagnostics"
```

### Task 4: Implement wrapper output filter for SSH hints

**Files:**
- Modify: `scripts/provision_benchmarks.sh`
- Modify: `tests/unit/test_provision_benchmarks_sh.py`
- Test: `tests/unit/test_provision_benchmarks_sh.py`

- [ ] **Step 1: Add SSH hint matcher helper in wrapper**

```bash
emit_ssh_failure_hints_if_needed() {
    local line="$1"
    local lower
    lower="$(printf '%s' "$line" | tr '[:upper:]' '[:lower:]')"

    if [[ "$lower" == *"unreachable"* ]] && [[ "$lower" == *"failed to connect to the host via ssh"* || "$lower" == *"permission denied (publickey)"* || "$lower" == *"connection closed"* ]]; then
        echo "WARNING: SSH authentication/connectivity failure detected. Check that your SSH public key is installed on the target host." >&2
        echo "WARNING: Also verify the host is defined in ~/.ssh/config (or equivalent SSH config)." >&2
    fi
}
```

- [ ] **Step 2: Execute ansible through a filter while preserving exit code**

```bash
run_with_output_hints() {
    set +e
    "${CMD[@]}" 2>&1 | while IFS= read -r line; do
        echo "$line" >&2
        emit_ssh_failure_hints_if_needed "$line"
    done
    local cmd_rc=${PIPESTATUS[0]}
    set -e
    return "$cmd_rc"
}
```

- [ ] **Step 3: Use filter in non-serial execution path**

```bash
echo "▶ Running: ${CMD[*]}" >&2
echo "" >&2
run_with_output_hints
```

- [ ] **Step 4: Re-run focused wrapper tests**

Run: `uv run pytest tests/unit/test_provision_benchmarks_sh.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit wrapper implementation**

```bash
git add scripts/provision_benchmarks.sh tests/unit/test_provision_benchmarks_sh.py
git commit -m "feat: add ssh troubleshooting hints to provisioning failures"
```

### Task 5: Validate integrated behavior and quality gates

**Files:**
- Modify: `inventory_generator.py`
- Modify: `scripts/provision_benchmarks.sh`
- Modify: `tests/unit/test_inventory_generator.py`
- Modify: `tests/unit/test_provision_benchmarks_sh.py`

- [ ] **Step 1: Run targeted regression suites**

Run: `uv run pytest tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py -v`  
Expected: PASS.

- [ ] **Step 2: Run linter on changed files**

Run: `uv run ruff check inventory_generator.py tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py`  
Expected: PASS.

- [ ] **Step 3: Manual smoke check for inventory warning**

Run:
```bash
uv run python inventory_generator.py --list >/tmp/inv.json 2>/tmp/inv.err || true
grep -E "SSH public key|~/.ssh/config|Host key verification" /tmp/inv.err
```

Expected: matching warning appears when SSH query failures are encountered.

- [ ] **Step 4: Commit final polish (if any)**

```bash
git add inventory_generator.py scripts/provision_benchmarks.sh tests/unit/test_inventory_generator.py tests/unit/test_provision_benchmarks_sh.py
git commit -m "test: finalize ssh connectivity diagnostic warning coverage"
```

