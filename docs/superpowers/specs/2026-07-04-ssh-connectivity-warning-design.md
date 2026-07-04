# SSH Connectivity Warning Design

## Goal

When SSH connectivity fails during inventory query or provisioning, emit actionable warnings that explicitly tell users to check:
1. SSH public key distribution to the target host.
2. Host entry/alias in `~/.ssh/config` (or equivalent SSH config).

## Scope

- In scope:
  - `inventory_generator.py` host query failures.
  - `scripts/provision_benchmarks.sh` output path for provisioning `UNREACHABLE` SSH failures.
  - Unit tests for both surfaces.
- Out of scope:
  - New preflight host linting.
  - Changing playbook logic, host matching rules, or provisioning semantics.
  - Auto-fixing SSH config or key distribution.

## Architecture

Use additive diagnostics only:
- Preserve original failure output exactly.
- Add warning lines only when known SSH failure signatures are detected.
- Keep command exit codes and task failure behavior unchanged.

## Components

### 1) inventory_generator.py

Add a helper that maps stderr text to diagnostics:
- Input: failing host name and stderr text from SSH subprocess failure.
- Output: list of warning lines (possibly empty).

Trigger patterns:
- `Host key verification failed`
- `Permission denied (publickey)`
- `Connection closed`

Behavior:
- Existing `Error querying host <host>: ...` line stays.
- If pattern matches, print additional warning block:
  - check key distribution to target host
  - check `~/.ssh/config` entry/alias

### 2) scripts/provision_benchmarks.sh

Add a line-filter function around `ansible-playbook` output:
- Echo all original output lines unchanged.
- Detect `UNREACHABLE` lines containing SSH failure signatures.
- Print matching warning block with the same two checks.

The wrapper must preserve original ansible exit status.

## Data Flow

1. SSH failure occurs.
2. Existing failure line is printed by current logic.
3. New matcher evaluates failure text.
4. If matched, warning block is appended to output.
5. Execution/failure semantics continue unchanged.

## Error Handling

- No broad try/except or silent fallbacks.
- No mutation of existing error text.
- If matcher cannot classify a line, no extra warning is emitted.

## Testing Strategy

### inventory_generator tests

Extend unit tests to verify:
- Matching stderr adds warning lines mentioning:
  - SSH key distribution check
  - SSH config host-entry check
- Non-matching stderr does not add warnings.

### wrapper script tests

Extend unit tests to verify:
- Simulated ansible `UNREACHABLE` + SSH failure line triggers warning block.
- Non-SSH failure lines do not trigger SSH guidance.
- Non-zero exit remains non-zero when ansible fails.

## Acceptance Criteria

1. SSH auth/connectivity failures in inventory output include both requested checks.
2. SSH `UNREACHABLE` failures in provisioning output include both requested checks.
3. Original error output and exit status behavior remain intact.
4. Unit tests cover positive and negative matching cases on both surfaces.
