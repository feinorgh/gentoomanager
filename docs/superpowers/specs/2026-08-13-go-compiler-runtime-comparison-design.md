# Go compiler/runtime comparison design

## Summary

Expand the benchmark suite so Go can be compared in two dimensions:

1. **compile performance** for the standard Go toolchain and gccgo, and
2. **runtime performance** of the binaries those toolchains produce.

The change keeps the current synthetic Go workload, but splits the measurements
into separate result files so the standard compiler and gccgo stay easy to
compare.

## Context and constraints

- The current Go benchmark only measures `go build`.
- The benchmark source is a deterministic synthetic program in
  `roles/run_benchmarks/files/go_bench/main.go`.
- gccgo may or may not be installed on a host, so its benchmarks must be
  optional and non-fatal when unavailable.
- The benchmark suite already follows a warning-on-failure pattern for other
  compiler sub-benchmarks.
- Report generation already understands category-per-JSON result files, so the
  new work should fit that shape.

## Goals

1. Measure Go compiler build time separately from binary runtime.
2. Add gccgo as a peer to the standard Go toolchain when present.
3. Keep the standard Go compiler and gccgo in separate result files.
4. Preserve graceful skipping when gccgo is not available.
5. Keep report output readable without adding a new top-level benchmark area.

## Non-goals

- Replacing the Go workload with a real application or multi-package corpus.
- Adding Go module/download benchmarking.
- Making gccgo required for the benchmark suite.
- Folding Go into the C/Rust compiler pivot tables.

## Proposed architecture

### Benchmark outputs

Use four result files:

- `compiler_go.json` for standard Go compile timing.
- `compiler_go_runtime.json` for standard Go binary runtime.
- `compiler_gccgo.json` for gccgo compile timing.
- `compiler_gccgo_runtime.json` for gccgo binary runtime.

This keeps compile and runtime measurements separate and makes gccgo optional
without changing the existing standard-Go result file name.

### Benchmark flow

1. Discover available Go toolchains.
2. Discover available gccgo toolchains, including versioned binaries.
3. Resolve each toolchain to a stable label for reporting.
4. Run compile benchmarks:
   - standard Go: `go build`
   - gccgo: `gccgo -O2`
5. Prebuild runtime binaries for each discovered toolchain.
6. Run runtime benchmarks against the resulting binaries only.
7. Export each phase to its own JSON file.

### Workload

Reuse the existing Go source unchanged unless implementation work shows a
runtime-specific adjustment is needed. The current program is deterministic,
single-binary, and already large enough to produce stable timings.

### Reporting

Update report metadata so the new result files render with clear titles, such
as:

- Go Compilation Speed
- Go Runtime Performance
- Go Compilation Speed (gccgo)
- Go Runtime Performance (gccgo)

The compiler page grouping should continue to collect these categories under the
compiler section.

## Data flow

1. `roles/run_benchmarks/tasks/compiler.yml` detects `go` and `gccgo`.
2. Build benchmarks export `compiler_go.json` and `compiler_gccgo.json`.
3. Runtime binaries are built once per available toolchain.
4. Runtime benchmarks export `compiler_go_runtime.json` and
   `compiler_gccgo_runtime.json`.
5. `scripts/generate_benchmark_report.py` reads and labels the four files.
6. Docs describe how to interpret the two toolchains and the two phases.

## Error handling

- If gccgo is absent, only the standard Go benchmarks run.
- If a specific gccgo toolchain cannot be resolved, it is skipped without
  failing the whole category.
- If a runtime binary cannot be produced, that runtime result file is skipped
  while the other toolchain/phase combinations continue.
- Benchmark failures remain warning-level so the suite stays resilient.

## Testing

Add or update unit tests to cover:

1. gccgo toolchain discovery and label normalization.
2. new Go and gccgo result-file titles in report generation.
3. runtime and compile phase naming in benchmark output.
4. graceful handling when gccgo is not present.

## Acceptance criteria

1. Hosts with the standard Go toolchain produce compile and runtime result
   files for Go.
2. Hosts with gccgo also produce compile and runtime result files for gccgo.
3. Hosts without gccgo still complete successfully.
4. Report generation renders the new files with clear titles and no regressions
   in existing compiler reports.
5. Existing Go benchmark behavior remains deterministic and repeatable.

## Rollout notes

- Prefer the smallest change that keeps the two toolchains comparable.
- Document the fact that the runtime phase measures the compiled binary only,
  not compilation plus execution.
- If the gccgo optimization choice proves contentious, keep it explicit in the
  implementation and docs rather than implicit in the task logic.
