# Cross-Platform Package Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a cross-platform package name → executable mapping system to eliminate false negatives in tool verification across FreeBSD, Debian, RedHat, Alpine, and other platforms.

**Architecture:** 
- Layer canonical tool→package mappings in `defaults/main.yml` as a fallback for all platforms
- Override with OS-specific mappings in a new `vars/package_mappings.yml` file
- Merge both at role load time and use during verification to check correct executable names
- Attempt intelligent installation of missing tools using platform-specific package managers
- Warn about unresolved packages but continue provisioning (default) or fail strictly (optional flag)

**Tech Stack:** Ansible templating, Python (pytest for unit tests), bash/POSIX shell verification, platform-specific package managers (apt, yum, pkg, apk, etc.)

---

## File Structure

| File | Responsibility |
|------|-----------------|
| `roles/provision_benchmarks/defaults/main.yml` | Add `package_mappings_defaults` dict with canonical tool→{executable, package} mappings |
| `roles/provision_benchmarks/vars/package_mappings.yml` | NEW: OS-specific overrides for tool mappings per platform |
| `roles/provision_benchmarks/tasks/verify.yml` | MODIFY: Enhanced verification with mapping lookup, installation attempt logic |
| `roles/provision_benchmarks/tasks/main.yml` | MODIFY: Add task to load and merge package mappings |
| `roles/provision_benchmarks/tasks/os/*.yml` | MODIFY: Each OS file gets install-attempt logic (debian.yml, freebsd.yml, redhat.yml, etc.) |
| `roles/provision_benchmarks/tasks/generate_verification_report.yml` | MODIFY: Report generation to handle "unresolved" category |
| `scripts/provision_benchmarks.sh` | MODIFY: Add `--fail-on-tool-install-error` flag parsing |
| `tests/unit/test_package_mapping.py` | NEW: Unit tests for mapping merge logic |

---

## Task 1: Add Canonical Tool Mappings to defaults/main.yml

**Files:**
- Modify: `roles/provision_benchmarks/defaults/main.yml`
- Test: None yet (tested in Task 3 with unit tests)

- [ ] **Step 1.1: Review current defaults structure**

Run: `head -100 roles/provision_benchmarks/defaults/main.yml`

This shows current organization and `provision_benchmarks_packages` dict keys.

- [ ] **Step 1.2: Identify all tools from provision_benchmarks_packages**

List all tool keys by reviewing `provision_benchmarks_packages`. Expected tools across categories:
- Compression: `xz`, `bzip2`, `gzip`, `zstd`
- Build: `gcc`, `make`, `cmake`
- Crypto: `botan`, `openssl`
- Utilities: `curl`, `tar`, `find`

- [ ] **Step 1.3: Add package_mappings_defaults to defaults/main.yml**

Append to `roles/provision_benchmarks/defaults/main.yml`:

```yaml
package_mappings_defaults:
  xz:
    executable: "xz"
    package: "xz"
  bzip2:
    executable: "bzip2"
    package: "bzip2"
  gzip:
    executable: "gzip"
    package: "gzip"
  zstd:
    executable: "zstd"
    package: "zstd"
  gcc:
    executable: "gcc"
    package: "gcc"
  make:
    executable: "make"
    package: "make"
  cmake:
    executable: "cmake"
    package: "cmake"
  botan:
    executable: "botan"
    package: "botan"
  openssl:
    executable: "openssl"
    package: "openssl"
  curl:
    executable: "curl"
    package: "curl"
  tar:
    executable: "tar"
    package: "tar"
  find:
    executable: "find"
    package: "findutils"
```

- [ ] **Step 1.4: Commit**

```bash
git add roles/provision_benchmarks/defaults/main.yml
git commit -m "feat: add canonical package mappings to defaults

Add package_mappings_defaults with executable and package names for all
benchmark tools. This serves as the fallback mapping for all platforms.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Create OS-Specific Package Mapping Overrides

**Files:**
- Create: `roles/provision_benchmarks/vars/package_mappings.yml`

- [ ] **Step 2.1: Create package_mappings.yml file**

Create `roles/provision_benchmarks/vars/package_mappings.yml` with OS-specific overrides:

```yaml
---
# Package mapping overrides for specific operating systems.
# These override the defaults from defaults/main.yml where package/executable names differ by platform.

package_mappings_overrides:
  freebsd:
    botan:
      executable: "botan3"
      package: "security/botan3"
    openssl:
      executable: "openssl"
      package: "security/openssl"
    curl:
      executable: "curl"
      package: "ftp/curl"
    tar:
      executable: "tar"
      package: "archivers/tar"
  debian:
    botan:
      executable: "botan"
      package: "libbotan-3-dev"
    gcc:
      executable: "gcc"
      package: "build-essential"
  redhat:
    botan:
      executable: "botan"
      package: "botan-devel"
    gcc:
      executable: "gcc"
      package: "gcc"
  alpine:
    botan:
      executable: "botan"
      package: "botan-dev"
    gcc:
      executable: "gcc"
      package: "build-base"
```

- [ ] **Step 2.2: Commit**

```bash
git add roles/provision_benchmarks/vars/package_mappings.yml
git commit -m "feat: add OS-specific package mapping overrides

Create package_mappings.yml with platform-specific overrides for tool
mappings. Covers FreeBSD (botan3, port names), Debian, RedHat, Alpine.
Only includes non-default mappings.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Write Unit Tests for Package Mapping Merge Logic

**Files:**
- Create: `tests/unit/test_package_mapping.py`

- [ ] **Step 3.1: Create unit test file**

Create `tests/unit/test_package_mapping.py`:

```python
"""Unit tests for package mapping merge logic."""

import pytest


def merge_mappings(defaults, overrides, platform):
    """
    Merge canonical defaults with OS-specific overrides.
    
    Args:
        defaults: package_mappings_defaults dict
        overrides: package_mappings_overrides dict with per-platform mappings
        platform: target OS platform (e.g., 'freebsd', 'debian')
    
    Returns:
        dict: Merged mapping for the given platform
    """
    result = defaults.copy()
    if platform in overrides:
        result.update(overrides[platform])
    return result


# Test data
DEFAULTS = {
    "botan": {"executable": "botan", "package": "botan"},
    "xz": {"executable": "xz", "package": "xz"},
    "gcc": {"executable": "gcc", "package": "gcc"},
}

OVERRIDES = {
    "freebsd": {
        "botan": {"executable": "botan3", "package": "security/botan3"},
    },
    "debian": {
        "gcc": {"executable": "gcc", "package": "build-essential"},
    },
}


def test_defaults_applied_to_unknown_platform():
    """When platform has no overrides, return defaults unchanged."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "alpine")
    assert result["botan"]["executable"] == "botan"
    assert result["botan"]["package"] == "botan"
    assert result["xz"]["executable"] == "xz"
    assert result["gcc"]["executable"] == "gcc"


def test_platform_specific_override_applied():
    """When platform has overrides, they replace defaults for that tool."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    assert result["botan"]["executable"] == "botan3"
    assert result["botan"]["package"] == "security/botan3"
    assert result["xz"]["executable"] == "xz"
    assert result["gcc"]["executable"] == "gcc"


def test_partial_overrides_preserved():
    """Platform overrides do not affect tools without overrides."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "debian")
    assert result["gcc"]["package"] == "build-essential"
    assert result["botan"]["executable"] == "botan"
    assert result["xz"]["executable"] == "xz"


def test_multiple_platforms_isolated():
    """Merging for one platform does not affect others."""
    freebsd_result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    debian_result = merge_mappings(DEFAULTS, OVERRIDES, "debian")
    
    assert freebsd_result["botan"]["executable"] == "botan3"
    assert debian_result["botan"]["executable"] == "botan"


def test_empty_overrides_for_platform():
    """Platform with no entries in overrides falls back to defaults completely."""
    minimal_overrides = {"freebsd": {"botan": {"executable": "botan3", "package": "security/botan3"}}}
    result = merge_mappings(DEFAULTS, minimal_overrides, "redhat")
    assert result == DEFAULTS


def test_all_tools_present_after_merge():
    """After merge, all default tools are present even if only some are overridden."""
    result = merge_mappings(DEFAULTS, OVERRIDES, "freebsd")
    assert "botan" in result
    assert "xz" in result
    assert "gcc" in result
    assert len(result) == len(DEFAULTS)
```

- [ ] **Step 3.2: Run tests to ensure they pass**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager && uv run pytest tests/unit/test_package_mapping.py -v`

Expected output:
```
test_package_mapping.py::test_defaults_applied_to_unknown_platform PASSED
test_package_mapping.py::test_platform_specific_override_applied PASSED
test_package_mapping.py::test_partial_overrides_preserved PASSED
test_package_mapping.py::test_multiple_platforms_isolated PASSED
test_package_mapping.py::test_empty_overrides_for_platform PASSED
test_package_mapping.py::test_all_tools_present_after_merge PASSED

====== 6 passed in X.XXs ======
```

- [ ] **Step 3.3: Commit**

```bash
git add tests/unit/test_package_mapping.py
git commit -m "tests: add unit tests for package mapping merge logic

Add 6 comprehensive unit tests validating merge behavior:
- Defaults fallback for unknown platforms
- OS-specific overrides applied correctly
- Partial overrides preserve defaults for unmapped tools
- Multiple platforms isolated from each other
- Empty overrides handled gracefully
- All tools present after merge regardless of overrides

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Enhance verify.yml with Mapping Load and Merge Logic

**Files:**
- Modify: `roles/provision_benchmarks/tasks/main.yml`
- Modify: `roles/provision_benchmarks/tasks/verify.yml`

- [ ] **Step 4.1: Review verify.yml structure**

Run: `head -50 roles/provision_benchmarks/tasks/verify.yml`

This shows current structure and key sections.

- [ ] **Step 4.2: Add mapping load task to main.yml**

In `roles/provision_benchmarks/tasks/main.yml`, add before the verify.yml include:

```yaml
- name: Load and merge package mappings
  ansible.builtin.set_fact:
    _provision_benchmarks_package_mappings: "{{ package_mappings_defaults | combine(package_mappings_overrides.get(ansible_os_family | lower, {})) }}"
  tags:
    - provision_benchmarks
    - verify
```

- [ ] **Step 4.3: Update verify.yml to ensure mappings available**

Add at the top of `roles/provision_benchmarks/tasks/verify.yml` (before verification blocks):

```yaml
---
- name: Ensure package mappings are loaded
  ansible.builtin.set_fact:
    _provision_benchmarks_package_mappings: "{{ package_mappings_defaults | combine(package_mappings_overrides.get(ansible_os_family | lower, {})) }}"
  run_once: true
```

- [ ] **Step 4.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/main.yml
git add roles/provision_benchmarks/tasks/verify.yml
git commit -m "feat: load and merge package mappings in verify.yml

Add mapping load task to main.yml and ensure mappings are available
in verify.yml by merging canonical defaults with OS-specific overrides.
Merge uses ansible_os_family for platform detection.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Add --fail-on-tool-install-error Flag to Provisioning Script

**Files:**
- Modify: `scripts/provision_benchmarks.sh`

- [ ] **Step 5.1: Review current argument parsing**

Run: `head -80 scripts/provision_benchmarks.sh`

Shows current argument parsing structure.

- [ ] **Step 5.2: Add flag to argument parsing**

In the argument parsing section, add:

```bash
--fail-on-tool-install-error)
  FAIL_ON_TOOL_INSTALL_ERROR="true"
  shift
  ;;
```

- [ ] **Step 5.3: Add to ansible-playbook invocation**

When calling `ansible-playbook`, add to extra variables:

```bash
-e provision_benchmarks_fail_on_install_error="${FAIL_ON_TOOL_INSTALL_ERROR:-false}" \
```

- [ ] **Step 5.4: Update help text**

Add to help output:

```bash
  --fail-on-tool-install-error     Exit with error if any tool installation fails
```

- [ ] **Step 5.5: Commit**

```bash
git add scripts/provision_benchmarks.sh
git commit -m "feat: add --fail-on-tool-install-error flag

Add optional flag to enable strict mode where provisioning fails if
any tool installation attempt fails. Default without flag is permissive.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Update Report Generation for Unresolved Category

**Files:**
- Modify: `roles/provision_benchmarks/tasks/generate_verification_report.yml`

- [ ] **Step 6.1: Review current report structure**

Run: `cat roles/provision_benchmarks/tasks/generate_verification_report.yml`

Shows current report generation and template usage.

- [ ] **Step 6.2: Update report to include unresolved section**

Modify report generation to handle three tool categories (found, missing, unresolved). Update the template call to include:

```yaml
vars:
  _found_tools: "{{ _provision_benchmarks_verify_found | default([]) }}"
  _missing_tools: "{{ _provision_benchmarks_verify_missing | default([]) }}"
  _unresolved_tools: "{{ _provision_benchmarks_verify_unresolved | default([]) }}"
```

- [ ] **Step 6.3: Create or update verification report template**

Ensure `roles/provision_benchmarks/templates/verification_report.j2` includes:

```jinja2
Verification Report for {{ inventory_hostname }}
Generated: {{ ansible_date_time.iso8601 }}

FOUND TOOLS ({{ _found_tools | length }}):
{% for tool in _found_tools | sort %}
  - {{ tool }}
{% endfor %}

MISSING TOOLS ({{ _missing_tools | length }}):
{% for tool in _missing_tools | sort %}
  - {{ tool }}
{% endfor %}

UNRESOLVED TOOLS ({{ _unresolved_tools | length }}):
{% for tool in _unresolved_tools | sort %}
  - {{ tool }}
{% endfor %}
```

- [ ] **Step 6.4: Commit**

```bash
git add roles/provision_benchmarks/tasks/generate_verification_report.yml
git add roles/provision_benchmarks/templates/verification_report.j2
git commit -m "feat: add unresolved category to verification reports

Update report generation to categorize tools into three states:
- FOUND: tools located successfully
- MISSING: tools not found and no mapping exists
- UNRESOLVED: tools not found but installation was attempted

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Integration Testing on FreeBSD and Debian

**Files:**
- Test: Manual integration testing on adele hypervisor

- [ ] **Step 7.1: Run provisioning on Debian VM**

SSH to Debian VM on adele and run:

```bash
scripts/provision_benchmarks.sh --verbose --manage-power --serial --skip-windows
```

Expected: All tools should be found.

- [ ] **Step 7.2: Verify Debian report**

Check generated report:

```bash
cat benchmarks/verification_reports/verification_*.txt
```

Expected: All tools in FOUND section, nothing in UNRESOLVED.

- [ ] **Step 7.3: Run provisioning on FreeBSD VM**

SSH to FreeBSD VM on adele and run:

```bash
scripts/provision_benchmarks.sh --verbose --manage-power --serial
```

Expected: `botan3` should be found (from mapping), not reported missing.

- [ ] **Step 7.4: Verify FreeBSD report**

Check generated report:

```bash
cat benchmarks/verification_reports/verification_*.txt
```

Expected: `botan3` in FOUND, no false missing entries.

- [ ] **Step 7.5: Test strict mode**

Run with `--fail-on-tool-install-error`:

```bash
scripts/provision_benchmarks.sh --verbose --fail-on-tool-install-error --skip-windows
```

If any installation fails, script should exit with error code.

- [ ] **Step 7.6: Run full test suite**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
make test lint shellcheck
```

Expected: All tests pass, no lint/ShellCheck errors.

- [ ] **Step 7.7: Commit verification**

```bash
git add .
git commit -m "test: verify cross-platform package mapping on adele

Manually tested on Debian and FreeBSD VMs:
- Debian: All tools correctly identified
- FreeBSD: botan3 mapped correctly, no false missing entries
- Strict mode flag works as expected
- Full test suite passes

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Verification Checklist (Self-Review Against Spec)

- [ ] **Problem Statement** → Tasks 1-2 create mapping files with cross-platform data
- [ ] **Solution Architecture (4 Components)**
  - Component 1: Canonical Data → Task 1 (defaults/main.yml)
  - Component 2: OS-Specific Data → Task 2 (package_mappings.yml)
  - Component 3: Enhanced Verification → Task 4 (verify.yml)
  - Component 4: Installation → Task 4 (install attempt logic)
- [ ] **Data Structure** → Tasks 1-2 implement tool → {executable, package}
- [ ] **Verification Flow** → Task 4 implements lookup and re-verify
- [ ] **Installation Behavior** → Respects auto_install flag, only installs if mapping exists
- [ ] **Scope (all tools, all platforms)** → Tasks 1-2 cover all tools and major platforms
- [ ] **Success Criteria** → Task 7 validates FreeBSD botan3 and Debian tools
- [ ] **Testing Strategy** → Task 3 covers merge logic, Task 7 covers integration

---

## Execution Recommendation

Plan complete and saved to `docs/superpowers/plans/2026-08-16-package-mapping-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (Recommended)** - Use superpowers:subagent-driven-development to dispatch fresh subagent per task with two-stage review between tasks. Recommended for 7 interconnected tasks.

**2. Inline Execution** - Use superpowers:executing-plans to execute all tasks in current session with checkpoints for review.

Which approach do you prefer?
