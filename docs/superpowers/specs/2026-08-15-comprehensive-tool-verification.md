# Comprehensive Tool Verification for Benchmark Provisioning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the provisioning verification system to check all 16+ installed benchmark tools (currently only 13 verified) and generate detailed timestamped reports of missing tools.

**Architecture:** Expand `roles/provision_benchmarks/tasks/verify.yml` to verify all installed tools across compression, build, crypto, utilities, and optional categories. Missing tools trigger both immediate stdout warnings and are logged to timestamped report files in `benchmarks/verification_reports/` for later review. Missing tools are treated as optional—they don't block provisioning.

**Tech Stack:** Ansible (verify.yml), Jinja2 templating, bash/PowerShell for tool detection

---

## Current State Analysis

### Tools Currently Verified (13 tools)
- hyperfine, bash, openssl, git, compiler (gcc/cc), python, clang, rustc, go, ffmpeg, octave, imagemagick

### Tools Installed But Not Verified (16+ tools)

**Compression tools (6):** gzip, bzip2, xz, zstd, lz4, 7zip
**Build tools (2):** make, cargo
**Crypto (1):** gpg/gpg2
**Utilities (2):** diffutils, sqlite3
**Optional (6):** botan, mold, numpy, opencv, gimp, inkscape

### Verification Gaps
- No checks for any compression tools despite being universally installed
- No checks for build tools (make, cargo) despite being essential
- No checks for security/utility tools
- Optional tools have no conditional verification

---

## Requirements

### Functional Requirements

1. **Verify all installed tools** — check existence of 16+ additional tools across all categories
2. **Categorized output** — organize missing tools by category (compression, build, crypto, utilities, optional)
3. **Dual reporting** — output warnings to stdout AND create timestamped report files
4. **Report persistence** — store reports in `benchmarks/verification_reports/verification_YYYY-MM-DD_HHMMSS.txt`
5. **OS compatibility** — handle both Linux (bash `command -v`) and Windows (PowerShell `Get-Command`)
6. **Optional tool handling** — don't warn about missing optional tools unless explicitly enabled
7. **Non-blocking** — missing tools produce warnings only, don't fail provisioning

### Non-Functional Requirements

1. **Performance** — verification should complete in <5 seconds per host
2. **Maintainability** — tool list centralized in defaults, reused by verify.yml
3. **Backward compatibility** — existing verify.yml behavior unchanged for currently-checked tools
4. **Report format** — human-readable, sortable by category and hostname

---

## Design Details

### Verification Task Flow

1. **Check tool availability** — per-host verification runs for all tools in provision_benchmarks_packages
2. **Collect results** — build list of missing tools organized by category
3. **Generate warnings** — output to stdout showing what's missing
4. **Create report** — write timestamped file with full details
5. **Report directory** — auto-create `benchmarks/verification_reports/` if missing

### Report File Format

```
Benchmark Provisioning Verification Report
Generated: 2026-08-15 23:46:09 UTC
Hostname: gentoo-caramel
Provisioning Date: 2026-08-15 23:40:00 UTC

=== MISSING TOOLS SUMMARY ===
Total Missing: 3 tools

=== BY CATEGORY ===

COMPRESSION TOOLS (0/6 missing):
  ✓ gzip, bzip2, xz, zstd, lz4, 7zip

BUILD TOOLS (1/2 missing):
  ✓ make
  ✗ cargo

CRYPTO TOOLS (0/1 missing):
  ✓ gpg

UTILITIES (0/2 missing):
  ✓ diffutils, sqlite3

OPTIONAL TOOLS (2/6 missing):
  ? botan (not installed - optional)
  ? numpy (not installed - optional)
  ✓ mold, opencv, gimp, inkscape

=== NOTES ===
Optional tools only warn if explicitly provisioned via flags.
All compression tools verified successfully.
```

### Verification Implementation

**Linux verification** (in `verify.yml`):
```bash
for tool in gzip bzip2 xz zstd lz4 7zip make cargo gpg diffutils sqlite3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing_tools+=("$tool")
  fi
done
```

**Windows verification** (PowerShell):
```powershell
foreach ($tool in @('gzip', 'bzip2', 'xz', 'zstd', 'lz4', '7z', 'make', 'cargo', 'gpg')) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    $missingTools += $tool
  }
}
```

### Data Structures

**Ansible variables (in defaults/main.yml):**
```yaml
provision_benchmarks_verification_categories:
  compression:
    name: "Compression Tools"
    tools: [gzip, bzip2, xz, zstd, lz4, 7zip]
  build:
    name: "Build Tools"
    tools: [make, cargo]
  crypto:
    name: "Crypto Tools"
    tools: [gpg]
  utilities:
    name: "Utilities"
    tools: [diffutils, sqlite3]
  optional:
    name: "Optional Tools"
    tools: [botan, mold, numpy, opencv, gimp, inkscape]
    conditional: true
```

**Per-host missing tools list:**
```yaml
run_benchmarks_missing_tools:
  compression: []
  build: [cargo]
  crypto: []
  utilities: []
  optional: [botan, numpy]
```

---

## Implementation Strategy

### Phase 1: Update Defaults & Verification
1. Add `provision_benchmarks_verification_categories` to `defaults/main.yml`
2. Refactor `verify.yml` to check all tool categories
3. Collect missing tools into structured dictionary

### Phase 2: Report Generation
1. Create report generation task in `verify.yml`
2. Implement report file writing with timestamp
3. Add stdout warning output

### Phase 3: Testing & Validation
1. Run provisioning on test host with some tools missing
2. Verify stdout warnings appear
3. Verify report file is created correctly
4. Verify report format and categorization

---

## Files Modified

| File | Purpose | Changes |
|------|---------|---------|
| `roles/provision_benchmarks/defaults/main.yml` | Central tool definitions | Add `provision_benchmarks_verification_categories` dict with all tool groups |
| `roles/provision_benchmarks/tasks/verify.yml` | Tool verification | Refactor to check all categories; add report generation; add stdout warnings |
| `benchmarks/verification_reports/` | NEW | Directory for timestamped report files |

---

## Success Criteria

- ✅ All 13 originally-verified tools still verified
- ✅ All 16+ new tools checked on each provisioning run
- ✅ Missing tools show warnings on stdout
- ✅ Timestamped report files created in `benchmarks/verification_reports/`
- ✅ Reports contain categorized missing tool listings
- ✅ Optional tools don't warn if not explicitly provisioned
- ✅ No impact on provisioning success/failure
- ✅ Works on both Linux and Windows hosts

---

## Edge Cases & Mitigations

| Edge Case | Mitigation |
|-----------|-----------|
| Report directory doesn't exist | Task creates `benchmarks/verification_reports/` if needed |
| Concurrent provisioning runs | Each gets unique timestamped filename |
| Optional tools not installed | Check `provision_benchmarks_install_*` flags before reporting |
| Windows vs. Linux tool names differ | Use OS-specific check logic (PowerShell vs. bash) |
| Tool name varies by distro (e.g., sqlite vs. sqlite3) | Define aliases in defaults for platform-specific names |
| Missing tools on minimal systems | Warnings only, no failure; user can manually install |

---

## Testing Plan

1. **Unit test scenario:** Run provisioning on a test Gentoo VM, verify report file structure
2. **Integration test scenario:** Provision all 27 adele VMs, collect reports, verify categorization accuracy
3. **Edge case test:** Deliberately remove a tool, re-provision, verify warning appears
4. **Windows test:** Verify Windows verification task works correctly with PowerShell detection

