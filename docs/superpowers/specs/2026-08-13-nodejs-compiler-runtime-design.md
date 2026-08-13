# Node.js compiler-category runtime benchmark design

## Goal

Add a representative Node.js benchmark program to the existing `compiler`
benchmark category so Node runtime performance is measured in the same flow as
Go and Rust runtime workloads.

## Scope

In scope:
- `roles/run_benchmarks/tasks/compiler.yml` Node runtime benchmark wiring
- Node benchmark fixture under `roles/run_benchmarks/files/node_bench/`
- Skip-existing and skip-complete completeness maps for Node runtime result
- Unit tests for compiler task wiring and completeness-map coverage

Out of scope:
- New top-level `nodejs` benchmark category
- Windows-specific Node benchmark task additions
- Report schema redesign

## Architecture and components

1. Keep Node benchmark orchestration in `compiler.yml` (same category as other
   language runtime benchmarks).
2. Add a small, deterministic Node benchmark program in
   `roles/run_benchmarks/files/node_bench/main.mjs`.
3. Reuse existing hyperfine orchestration style:
   - detect toolchain availability first,
   - generate labeled command list,
   - run hyperfine with `--ignore-failure`,
   - export JSON to work dir,
   - warn (non-fatal) on benchmark failures.

## Data flow

1. Detect Node availability (`node`) during compiler toolchain probing.
2. Create and populate `{{ run_benchmarks_work_dir }}/node_bench/` with the
   benchmark script when Node exists.
3. Discover Node binaries (generic `node` plus versioned names where present),
   deduplicate by resolved path, then resolve full version labels (for example
   `node22.16.0`) for stable command names.
4. Build hyperfine commands as:
   - command name: `<node-label>-runtime`
   - command: `<node-executable> main.mjs`
5. Export runtime results to:
   - `{{ run_benchmarks_work_dir }}/compiler_node_runtime.json`
6. Merge resolved Node version labels into `compiler_versions.json` so reports
   can display stable, human-readable toolchain labels.
7. Update completeness logic in:
   - `roles/run_benchmarks/tasks/main.yml` (skip-existing)
   - `playbooks/run_benchmarks.yml` (skip-complete preflight)
   so `compiler_node_runtime.json` is required only when Node is present.

## Error handling

- Preserve existing behavior: benchmark task failures are non-fatal and logged
  through dedicated warning tasks.
- If no runnable Node binaries are found after discovery/resolution, exit the
  Node runtime task without producing a failure.
- Keep result-file requirements conditional on detected Node availability to
  avoid false "incomplete result set" states on hosts without Node.

## Testing strategy

Add/update unit tests to assert:
1. `compiler.yml` contains `compiler_node_runtime.json` export wiring.
2. Node runtime command naming follows `<node-label>-runtime`.
3. `roles/run_benchmarks/tasks/main.yml` includes Node availability probe and
   conditional completeness requirement for `compiler_node_runtime.json`.
4. `playbooks/run_benchmarks.yml` mirrors the same preflight probe and
   conditional completeness requirement for `compiler_node_runtime.json`.

## Acceptance criteria

1. Running compiler benchmarks on a host with Node creates
   `compiler_node_runtime.json`.
2. Node runtime benchmark commands are labeled by resolved version.
3. Hosts without Node do not require `compiler_node_runtime.json` for
   skip-existing/skip-complete logic.
4. Existing compiler benchmark outputs and behaviors remain intact.
