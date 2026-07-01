# Rust benchmark expansion design (compiler category)

## Summary

Expand Rust benchmarking inside the existing `compiler` category to cover both:
1. **compile throughput** (already present, retained), and
2. **runtime performance/efficiency** (new),

using a **hybrid model**:
- deterministic self-contained workload, and
- one curated external-crate workload with pinned versions and deterministic input.

The goal is to improve Rust representativeness without introducing a new top-level benchmark category.

## Context and constraints

- The repository currently has no committed Rust source files (`*.rs`).
- Existing Rust benchmarking is generated at runtime in `roles/run_benchmarks/tasks/compiler.yml` and emitted as `compiler_rust.json`.
- The user requested:
  - compile + runtime coverage,
  - industry-standard representation,
  - hybrid dependency model,
  - keeping Rust under existing `compiler` category.
- Existing role behavior favors non-fatal category-level execution:
  benchmark commands use warning-on-failure patterns rather than hard-failing the full benchmark run.

## Design goals

1. Keep `compiler` as the top-level category shape.
2. Add Rust runtime signals alongside existing Rust compile timing.
3. Improve representativeness using one curated external workload.
4. Preserve reproducibility with deterministic fixtures and pinned dependency versions.
5. Preserve current cross-host resilience and warning semantics.

## Non-goals

- Creating a new top-level `rust` benchmark category.
- Converting the benchmark suite into a full `rustc-perf` integration.
- Making Rust benchmark failures fatal for the entire benchmark run.

## Proposed architecture

Rust remains in `roles/run_benchmarks/tasks/compiler.yml`, but gains two new output files:

- `compiler_rust.json` (existing): Rust compile throughput (`cargo build`, `cargo build --release`).
- `compiler_rust_runtime.json` (new): deterministic self-contained runtime workload.
- `compiler_rust_external.json` (new): curated external-crate workload with pinned versions.

### Workload structure

Inside the generated Rust benchmark project on target hosts:

1. **Self-contained runtime target**
   - no external crates,
   - fixed seed and fixed dataset/problem size,
   - compiled binary executed under `hyperfine`.

2. **External workload target**
   - a small, representative crate-backed task (for example JSON parsing/serialization and/or regex-heavy text processing),
   - dependencies pinned via lockfile and explicit versions,
   - deterministic fixture input generated/copied by the role.

Both workloads should produce stable command names that include toolchain label + workload type for report consistency.

## Data flow

1. Detect/resolve Rust toolchains (existing logic: rustup/eselect/PATH discovery).
2. For each resolved Rust toolchain label:
   - run compile benchmark commands -> `compiler_rust.json`,
   - run runtime benchmark commands -> `compiler_rust_runtime.json`,
   - run external-workload benchmark commands -> `compiler_rust_external.json`.
3. Result JSON files are collected into each host result directory as with other compiler outputs.
4. Report/article aggregation reads and renders the new Rust result files as compiler sub-sections.

## Error handling strategy

Follow existing benchmark-suite resilience patterns:

- benchmark steps remain non-fatal (`failed_when: false` where currently used for compiler benchmarks),
- emit explicit `[WARN]` tasks with return code and truncated stderr on Rust sub-benchmark failure,
- continue remaining benchmarks even if one Rust sub-benchmark fails.

Rust absence is not treated as failure; Rust-specific tasks remain gated on detected toolchain availability.

## Reporting and metadata integration

Update reporting surfaces that currently enumerate compiler JSON artifacts so the two new Rust outputs are included where appropriate:

- `scripts/generate_benchmark_report.py`
  - include `compiler_rust_runtime` and `compiler_rust_external` display sections/labels,
  - preserve existing compiler label parsing behavior (`rustc-x.y.z` formatting).
- Any category metadata/catalog layer used by article/report generation should include titles/descriptions for the new compiler Rust sub-results when needed.

No top-level category additions are expected; this is a compiler-subcategory expansion.

## Test design

### Unit tests to update/add

1. `tests/unit/test_benchmark_report.py`
   - verify new Rust compiler sub-result files are loaded and represented in report output,
   - verify compiler label formatting still handles Rust toolchain labels with new benchmark command naming.

2. `tests/unit/test_benchmarks_article_catalog.py` (and related catalog tests if affected)
   - ensure metadata coverage for newly surfaced compiler Rust sub-results if catalog requires explicit entries.

3. `tests/unit/test_run_benchmarks_defaults.py`
   - only if introducing Rust-specific default knobs (runs/warmup or fixture settings).

### Behavior checks

- Rust unavailable on host: compiler role path remains successful (Rust tasks skipped).
- Rust available, external workload issue: warning emitted, suite continues.
- Existing non-Rust compiler benchmarks (`compiler_c_*`, `compiler_go`, `compiler_sqlite`, `compiler_multifile`) remain unchanged.

## Acceptance criteria

1. Running compiler benchmarks on a Rust-capable host produces:
   - `compiler_rust.json`,
   - `compiler_rust_runtime.json`,
   - `compiler_rust_external.json`.
2. Rust command labels remain toolchain-qualified and reportable.
3. Report generation includes the new Rust sub-results without regressions in existing compiler sections.
4. Relevant unit tests pass with updated expectations.
5. Hosts without Rust still complete benchmark runs without fatal errors.

## Rollout notes

- Keep initial external workload narrow (single curated workload) to control runtime and maintenance.
- If runtime overhead is high, add Rust-specific run-count knobs in defaults and tests in a follow-up change.
- Revisit broader benchmark corpus only after baseline stability and report usefulness are confirmed.
