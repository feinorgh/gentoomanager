# Missing hypervisors.txt provisioning warning design

**Date:** 2026-07-03  
**Scope:** Ensure provisioning clearly reports missing `hypervisors.txt`, with wrapper-level non-zero exit and inventory-level warning.

## Goal

When running benchmark provisioning, detect missing `hypervisors.txt` early and provide an actionable message, instead of silently producing an empty inventory and skipped plays.

## Architecture

Implement guardrails in both layers:

1. **Wrapper (`scripts/provision_benchmarks.sh`)** enforces the selected behavior (`warn_and_exit`) and stops before running Ansible.
2. **Inventory (`inventory_generator.py`)** emits a warning when its file-based hypervisor source is missing and no environment override is provided.

This gives direct users of the wrapper a hard failure, while still making direct inventory usage diagnosable.

## Behavior

### Wrapper behavior

- Preflight checks for `${REPO_ROOT}/hypervisors.txt` before `ansible-playbook`.
- If `HYPERVISOR_HOSTS` is unset and `hypervisors.txt` is missing:
  - print warning/error to stderr,
  - include remediation:
    - `cp hypervisors.txt.example hypervisors.txt`
    - edit `hypervisors.txt` with hypervisor hostnames,
  - exit with non-zero status.
- If `HYPERVISOR_HOSTS` is set, proceed without requiring `hypervisors.txt`.

### Inventory behavior

- In `--list` mode, when `HYPERVISOR_HOSTS` is unset and `hypervisors.txt` is missing:
  - emit a single warning to stderr explaining why inventory is empty,
  - still return valid JSON dynamic inventory with empty hostvars.

## Data flow

1. User runs wrapper script.
2. Wrapper validates inventory source prerequisites.
3. Missing file case triggers explicit failure (wrapper path).
4. For direct inventory calls, inventory script warns and returns empty but valid JSON.

## Error handling

- Wrapper: explicit non-zero exit (no silent fallback) for missing file in file-based mode.
- Inventory: warning-only, protocol-safe JSON output.
- Existing behavior remains unchanged when `hypervisors.txt` exists.

## Files to modify

- `scripts/provision_benchmarks.sh`
- `inventory_generator.py`
- `tests/unit/test_run_benchmarks_sh.py` (or nearest wrapper-script tests)
- `tests/unit/test_inventory_generator.py`

## Testing

- Add/adjust wrapper test:
  - missing `hypervisors.txt` + no env override -> warns and exits non-zero.
- Add/adjust inventory test:
  - missing `hypervisors.txt` + no env override -> emits warning and returns empty inventory JSON.
- Verify normal path:
  - file present or env override set -> no regression.

## Scope boundaries

Included:
- Missing-file diagnostics and behavior for provisioning/inventory entry points.

Excluded:
- Changing host discovery logic itself.
- Changing provisioning role logic.
- Any benchmark category behavior.
