# Binary Resolution via Package Manager Design

**Date:** 2026-08-17  
**Status:** Approved  
**Context:** Cross-platform package mapping system (see `2026-08-16-cross-platform-package-mapping-design.md`)

---

## Problem

The existing package mapping system stores `{executable, package}` pairs per OS family, but those mappings are authored manually. This causes false negatives: a package may be installed yet the binary name differs from what the mapping specifies. For example, `diffutils` is installed on Gentoo but its binary is `diff`, not `diffutils`.

---

## Solution: Hybrid Package Binary Resolution

**Try static mapping first. If the executable is not found and a package mapping exists, query the OS package manager to discover the actual binary name. Write stable discoveries back so future runs skip the query.**

Three components:

1. **Ansible query tasks** — per-OS tasks that query the package manager for an installed package's file list, filter for executables, and write per-host discovery YAML to localhost.
2. **Python post-processor** (`scripts/resolve_package_binaries.py`) — reads discovery files, applies consensus/flap logic, updates the two mapping files.
3. **Wrapper integration** — `provision_benchmarks.sh` calls the script automatically after the playbook.

---

## Architecture

```
Ansible run
  └─ per-OS query task (runs on each host)
       └─ writes benchmarks/package_discoveries/<hostname>_<ts>.yml  (localhost)

provision_benchmarks.sh
  └─ calls scripts/resolve_package_binaries.py
       ├─ reads all discovery files
       ├─ consensus check
       ├─ updates roles/provision_benchmarks/vars/package_mappings.yml      (stable)
       └─ updates roles/provision_benchmarks/vars/package_mappings_variants.yml  (flapping)

verify.yml
  └─ merges: variants[family_version] > package_mappings[family] > defaults
```

---

## Data Structures

### Per-Host Discovery File

Written by Ansible to `benchmarks/package_discoveries/<hostname>_<timestamp>.yml`.  
**Not committed to git** (added to `.gitignore`).

```yaml
hostname: ubuntu-faith
os_family: debian
os_major_version: "12"
timestamp: "2026-08-17T13:42:30Z"
discoveries:
  diffutils:
    package: diffutils
    executable: diff          # first candidate found via command -v
    all_candidates: [diff, diff3, cmp, sdiff]
  botan:
    package: libbotan-3-dev
    executable: null          # package installed but no candidate found in PATH
    all_candidates: []
```

If the package is not installed (package manager returns an error), the tool is omitted entirely from the discovery file — no existing mapping is overwritten with nothing.

### Variants File

Written by the Python script. Committed to git.  
Path: `roles/provision_benchmarks/vars/package_mappings_variants.yml`

```yaml
package_mappings_variants:
  debian_12:
    diffutils:
      executable: diff
      package: diffutils
  gentoo_2:
    diffutils:
      executable: diff
      package: sys-apps/diffutils
  redhat_8:
    somepackage:
      executable: sometool-8
      package: somepackage
  redhat_9:
    somepackage:
      executable: sometool-9   # disagrees with redhat_8 → flap, stays here only
      package: somepackage
```

Key format: `{ansible_os_family | lower}_{ansible_distribution_major_version}`

---

## Package Manager Commands

| OS Family | Command | Notes |
|-----------|---------|-------|
| Gentoo | `qlist {package}` | Requires `app-portage/portage-utils` |
| Debian | `dpkg -L {package}` | Always available |
| RedHat | `rpm -ql {package}` | Always available; covers RHEL, Fedora, Oracle |
| Archlinux | `pacman -Ql {package}` | Always available; covers Manjaro, CachyOS |
| Suse | `rpm -ql {package}` | Same as RedHat |
| FreeBSD | `pkg info -l {package}` | Always available |
| OpenBSD | `pkg_info -L {package}` | Always available |
| Void | `xbps-query -f {package}` | Always available |
| Solus | `eopkg list-files {package}` | Always available |
| Alpine | `apk info -L {package}` | Always available |
| NixOS | Special — see below | No file listing by package name |

### Binary Resolution Steps (all platforms except NixOS)

1. Run the package manager command for the tool's package name
2. Filter output: keep only paths containing `/bin/`, `/sbin/`, or `/libexec/`
3. Extract basename of each matching path → candidates list
4. For each candidate: `command -v <candidate>` — first success is `executable`
5. Write `{executable, all_candidates, package}` to discovery file

### NixOS Special Case

NixOS packages are declared declaratively in `/etc/nixos/configuration.nix` under `environment.systemPackages`. There is no per-package file listing command.

Resolution:
1. Read `/etc/nixos/configuration.nix`, extract packages listed in `environment.systemPackages`
2. Run `command -v <executable>` for each tool — if installed (nix symlinks into PATH), works normally
3. If tool not found **and** package absent from config → warn: *"NixOS: `{package}` not in environment.systemPackages — add it and run `nixos-rebuild switch`"*
4. If tool not found **and** package IS in config → warn: *"NixOS: `{package}` is configured but binary not found — try running `nixos-rebuild switch`"*
5. If `command -v` succeeds: binary resolution proceeds as normal (no package manager file listing needed)

NixOS participates in binary discovery and variant tracking like all other platforms.

---

## Consensus Logic (Python Post-Processor)

`scripts/resolve_package_binaries.py` runs after the playbook:

1. Read all `benchmarks/package_discoveries/*.yml` files
2. Group entries by `(os_family, tool)`
3. For each `(os_family, tool)`:
   - Collect all `executable` values from all hosts across all major versions of that family
   - **Consensus:** all agree on the same executable → write/update entry in `package_mappings.yml` under `os_family` key
   - **Flapping:** any host disagrees → do NOT update `package_mappings.yml`; write per-`{family}_{major_version}` entries to `package_mappings_variants.yml`
4. Print summary:
   - N mappings promoted to `package_mappings.yml`
   - N flapping mappings written to `package_mappings_variants.yml` (list them with conflicting values)
   - N tools where package was not installed (skipped)

**Promotion is additive:** the script only updates entries where new data exists. It never removes existing manually-authored entries from `package_mappings.yml`.

---

## Merge Priority in verify.yml

```
package_mappings_variants[{os_family}_{major_version}]   ← highest priority
  ↓ overrides
provision_benchmarks_mappings_overrides[{os_family}]
  ↓ overrides
package_mappings_defaults                                  ← lowest priority
```

`verify.yml` loads `package_mappings_variants.yml` (if it exists) and merges the current host's `{os_family}_{major_version}` key on top of the family-level overrides.

---

## Wrapper Integration

`provision_benchmarks.sh` calls the post-processor after a successful playbook run:

```bash
if command -v uv >/dev/null 2>&1; then
    uv run python scripts/resolve_package_binaries.py \
        benchmarks/package_discoveries/ \
        roles/provision_benchmarks/vars/package_mappings.yml \
        roles/provision_benchmarks/vars/package_mappings_variants.yml
fi
```

The script is skipped (with a warning) if `uv` is not available.

---

## File Changes

| File | Action |
|------|--------|
| `roles/provision_benchmarks/tasks/os/debian.yml` (and all OS files) | Add binary resolution query task |
| `roles/provision_benchmarks/tasks/os/nixos.yml` | Add NixOS special-case resolution task |
| `roles/provision_benchmarks/tasks/verify.yml` | Load and merge `package_mappings_variants.yml` |
| `roles/provision_benchmarks/vars/package_mappings_variants.yml` | NEW — auto-generated, committed to git |
| `scripts/resolve_package_binaries.py` | NEW — Python post-processor |
| `scripts/provision_benchmarks.sh` | Add post-processor invocation |
| `benchmarks/package_discoveries/` | NEW directory, added to `.gitignore` |
| `tests/unit/test_resolve_package_binaries.py` | NEW — unit tests for consensus logic |

---

## Testing Strategy

**Unit tests** (`tests/unit/test_resolve_package_binaries.py`):
- Consensus detection: same executable across all hosts → promoted
- Flap detection: differing executables within same family → variants only
- Missing package (not installed): entry omitted, no existing mapping changed
- NixOS config parsing: packages present/absent detected correctly
- Merge priority: variants override family-level overrides override defaults

**Integration validation:**
- Run provisioning on Gentoo host; verify `diff` reported as found for `diffutils`
- Verify `package_mappings.yml` updated with `diffutils → diff` for gentoo family
- Introduce a synthetic flap (two hosts with different values); verify variants file receives both and `package_mappings.yml` is unchanged

---

## Success Criteria

- Gentoo `diffutils` resolves to `diff` executable after one provisioning run
- No manually maintained entry required for tools where package manager query succeeds
- Flapping is detected and surfaced clearly in post-processor output
- NixOS receives actionable warnings for missing/unconfigured packages
- `package_mappings.yml` is only updated with stable, agreed-upon mappings
- All existing tests continue to pass
