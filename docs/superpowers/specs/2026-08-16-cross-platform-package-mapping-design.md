# Cross-Platform Package Name → Executable Mapping Design

**Date:** 2026-08-16  
**Status:** Approved  
**Related Issue:** Tool verification false negatives due to package name mismatches across platforms

## Problem Statement

The current provisioning and verification system reports tools as "missing" even when they are installed, due to platform-specific mismatches between package names and executable names. Examples:

- FreeBSD: package `security/botan3` provides executable `botan3`, but verification checks for `botan`
- Debian: package `libbotan-3-dev` provides executable `botan`, differs from FreeBSD
- Other platforms have similar discrepancies across compression, crypto, build, and utility tools

The verification script uses simplistic `command -v <tool>` checks with no awareness of platform-specific naming conventions. This causes:
- False negatives in tool detection (tool installed but marked missing)
- Loss of user confidence in verification reports
- Difficulty diagnosing actual missing tools vs. naming issues

## Solution Overview

Implement a **cross-platform package mapping system** that:

1. Maintains an authoritative mapping of package names → executable names per OS for all benchmark tools
2. Uses conservative, high-confidence mappings only (no guesses)
3. Attempts intelligent installation of missing tools using correct package names
4. Falls back gracefully to legacy behavior for unmapped tools
5. Warns about unresolved packages that couldn't be installed or weren't mapped
6. Provides optional strict mode for CI/CD enforcement

## Architecture

### Components

1. **Package Mapping Data** (`roles/provision_benchmarks/vars/package_mappings.yml`)
   - OS-specific overrides of canonical tool→package mappings
   - High-confidence mappings only; conservative approach
   
2. **Canonical Defaults** (in `roles/provision_benchmarks/defaults/main.yml`)
   - Baseline mapping for all tools (fallback for unmapped platforms)
   - Defines executable name and generic package name per tool
   
3. **Enhanced Verification** (`roles/provision_benchmarks/tasks/verify.yml`)
   - Lookup correct executable names via merged mappings
   - Attempt installation for missing tools with mapped packages
   - Categorize results (found, missing, unresolved)
   - Fall back to legacy `command -v <tool>` for unmapped tools
   
4. **Optional Install Trigger** (in `roles/provision_benchmarks/tasks/os/*.yml`)
   - Attempt package installation if tool verification fails and mapping exists
   - Log warnings for installation failures
   
5. **Strict Mode Flag** (addition to `scripts/provision_benchmarks.sh`)
   - `--fail-on-tool-install-error` — exit on any installation failure

### Data Structure

#### Canonical Defaults (in `defaults/main.yml`)

```yaml
package_mappings_defaults:
  botan:
    executable: "botan"
    package: "botan"
  xz:
    executable: "xz"
    package: "xz"
  zstd:
    executable: "zstd"
    package: "zstd"
  # ... all tools with canonical names
```

#### OS-Specific Overrides (in `vars/package_mappings.yml`)

```yaml
package_mappings_overrides:
  freebsd:
    botan:
      executable: "botan3"
      package: "security/botan3"
    xz:
      executable: "xz"
      package: "archivers/xz"
  debian:
    botan:
      executable: "botan"
      package: "libbotan-3-dev"
    # ... all tools for Debian
  redhat:
    botan:
      executable: "botan"
      package: "botan-devel"
    # ... all tools for RedHat
  # ... alpine, windows, etc.
```

### Verification Flow

1. **Load Mappings**
   - Load `package_mappings_defaults` from defaults
   - Load `package_mappings_overrides` from vars
   - Merge overrides into defaults for current OS

2. **For Each Tool**
   - Retrieve mapping entry: `{executable, package}`
   - Execute: `command -v <executable>`
   - **If found:** Mark as ✓ found
   - **If not found AND package mapping exists:**
     - Attempt: `pkg install <package>` (or equivalent for OS)
     - Re-check: `command -v <executable>`
     - **If found after install:** Mark as ✓ found (installed)
     - **If still not found:** Mark as ✗ missing, log warning with package name
   - **If not found AND no package mapping:**
     - Fall back: `command -v <tool_name>` using defaults
     - Mark as ✓ found or ✗ missing accordingly

3. **Report Results**
   - Categorize: found, missing (unmapped), unresolved (mapped but install failed)
   - Warnings to stdout immediately
   - Detailed logs to verification report file

### Installation Attempt Behavior

**Default Mode (safe, permissive)**
- Attempt installation for missing tools with mappings
- Log warnings for installation failures
- Continue provisioning (do not exit)
- Use case: Normal provisioning runs

**Strict Mode** (with `--fail-on-tool-install-error` flag)
- Same installation attempts
- Exit with error if any installation fails
- Use case: CI/CD pipelines, automated testing

### Warnings & Logging

**Displayed to stdout (immediately)**
```
Warning: Tool 'botan' mapped to package 'security/botan3' on FreeBSD, but installation failed
Warning: Package name for tool 'some_tool' could not be resolved on this platform
```

**Logged to verification report file** (detailed)
```
[UNRESOLVED] botan: Mapped package security/botan3 failed to install
  Error: pkg: No packages available: security/botan3
  Attempted command: pkg install -y security/botan3
  Suggestion: Check if package name is correct or if tool is available in this platform's repository
```

## Scope & Constraints

- **In Scope:**
  - All tools used by the benchmark suite (compression, crypto, build, utilities)
  - All supported platforms (FreeBSD, Debian, RedHat, Alpine, Windows if applicable)
  - Conservative, high-confidence mappings only
  
- **Out of Scope:**
  - Guessing at package names; unmapped tools fall back to legacy behavior
  - Installing dependencies of tools (only the tool itself)
  - Platform-specific build flags or options (mapping is package name only)

## Success Criteria

1. Tool verification accurately reports tools installed on all supported platforms
2. False negatives for tools like `botan3` are eliminated via correct mappings
3. Warnings about unresolved packages guide users toward missing dependencies
4. Provisioning script runs successfully with no hard failures on missing packages (default mode)
5. Strict mode allows CI/CD to enforce zero missing tools when desired
6. All existing tests pass; verification reports are categorized correctly
7. Implementation is backward compatible: unmapped tools behave as before

## Testing Strategy

1. **Unit tests** — Verify mapping merge logic (defaults + overrides)
2. **Integration tests via Molecule** — Test on each OS with known problematic packages
   - FreeBSD: verify `botan3` is correctly mapped and found
   - Debian: verify same tool is found as `botan`
   - Each OS: verify at least one tool that requires installation
3. **Functional tests** — Run provision_benchmarks.sh with and without strict mode
4. **Report validation** — Verify categorization (found, missing, unresolved) is correct

## Implementation Phases

1. **Phase 1: Data & Defaults**
   - Add `package_mappings_defaults` to defaults/main.yml with all tools
   - Create `vars/package_mappings.yml` with OS-specific overrides
   - Add merge logic to load and combine mappings

2. **Phase 2: Verification Enhancement**
   - Modify verify.yml to use mappings for executable lookup
   - Add fallback to legacy behavior for unmapped tools
   - Update report generation to categorize results

3. **Phase 3: Installation Attempt**
   - Add install logic to OS-specific tasks (os/*.yml)
   - Implement warning logging to stdout and report file
   - Add strict mode flag to provision_benchmarks.sh

4. **Phase 4: Testing & Validation**
   - Write and run unit tests for mapping logic
   - Run Molecule integration tests on FreeBSD and Debian
   - Functional test with real provisioning runs
   - Validate backward compatibility

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Incorrect package mappings | Conservative approach: only map high-confidence names; test on each platform before committing |
| Installation failures break provisioning | Default permissive mode; warnings logged but script continues |
| Complex merge logic has bugs | Write unit tests for mapping merge; test with multiple OS combinations |
| Verification report structure breaks existing parsers | Add new "unresolved" category but keep existing "found"/"missing" logic intact |

## Future Enhancements (Not in Scope)

- Package metadata caching to avoid repeated install attempts
- Multi-version executable support (e.g., python2 vs python3)
- Automatic mapping discovery via package manager queries
- Web UI for visualizing which tools are available per platform
