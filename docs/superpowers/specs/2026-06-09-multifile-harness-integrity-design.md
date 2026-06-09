# Multifile Harness Integrity Design

## Goal

Ensure `compiler_multifile` runs correctly across supported OSes and never records invalid near-zero timings caused by failed commands (for example, missing `make`).

## Scope

- In scope:
  - Multifile benchmark execution path in `roles/run_benchmarks/tasks/compiler.yml`
  - Provisioning coverage for multifile-required tooling on NixOS and SUSE/openSUSE
  - Post-run validation of `compiler_multifile.json` exit codes
- Out of scope:
  - Reworking unrelated benchmark categories
  - Changing article rendering logic

## Root Cause Summary

`compiler_multifile` currently runs with tolerant failure behavior. If a command fails quickly (e.g., `make` missing, exit code 127), the run can still produce JSON and be fetched as if valid. This allows invalid timings to enter results.

## Design

### 1. Execution Integrity (Hard-Fail Policy)

For `compiler_multifile`, enforce hard-fail behavior:

1. Preflight checks before running hyperfine:
   - `make` must be available on PATH
   - At least one resolved C compiler command is executable
2. If preflight fails:
   - fail multifile benchmark task explicitly
   - do not treat category as successful
3. Run benchmark as usual only when preflight passes.

### 2. Post-Run JSON Validation

After `compiler_multifile.json` is generated:

1. Parse `results[*].exit_codes`
2. If any exit code is non-zero:
   - fail multifile benchmark task with explicit message containing host and failing command labels
3. Only accept multifile result as valid when all exit codes are zero.

This creates defense-in-depth:
- preflight catches known missing prerequisites
- post-validation catches runtime failures that still produce JSON

### 3. Provisioning Consistency

Provisioning should guarantee multifile prerequisites:

- NixOS (`roles/provision_benchmarks/tasks/os/nixos.yml`):
  - include `gnumake` package explicitly
- SUSE/openSUSE (`roles/provision_benchmarks/defaults/main.yml` package map):
  - include `make` package explicitly in `Suse` list

Optional follow-up: include multifile-specific verification messaging in existing tool verification output.

## Error Handling

- No silent fallback to valid-looking multifile output when commands fail.
- Error messages must state:
  - host
  - failing phase (`preflight` or `post-validation`)
  - failing requirement or command exit code details

## Testing Strategy

### Unit/Static Validation

- Add/adjust tests to assert article/data loader rejects or flags multifile data with non-zero exit codes if applicable.
- Validate existing tests still pass for benchmark data loading paths.

### Runtime Verification

For each affected OS (at minimum NixOS and openSUSE):

1. Provision host
2. Run benchmarks with multifile enabled
3. Confirm:
   - `compiler_multifile.json` exists
   - all multifile `exit_codes` are zero
   - multifile means are plausible (non-trivial compile durations)

## Success Criteria

1. Multifile benchmark cannot silently pass with non-zero exit codes.
2. Missing `make` fails multifile clearly instead of writing deceptive timings.
3. NixOS/openSUSE provisioning includes required make implementation.
4. Re-run results for affected hosts show valid multifile execution (exit code 0 only).
