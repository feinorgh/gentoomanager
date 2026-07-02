# Linux performance-context metadata + cross-host signal visualization design

**Date:** 2026-07-02  
**Scope:** Extend Linux benchmark metadata with curated performance-relevant system settings, then present host/OS defaults and salient differences with parity across Markdown and HTML reports.

## Goal

Capture a strict, high-signal set of Linux scheduler/virtual-memory/performance-affecting settings that are not already represented by benchmark timings, and surface them as:

1. per-host values,
2. per-OS default baselines, and
3. graphical difference views when there is meaningful cross-host signal.

## Design decisions (approved)

1. **Approach A:** extend existing `metadata.json` with `linux_perf_context`; derive comparisons at report time.
2. **Reporting parity:** Markdown and HTML are equally important and must render from one shared derived model.
3. **Strict relevance over breadth:** collect only curated, high-signal settings with stable cross-distro semantics.

## Architecture

Keep benchmark execution unchanged and add a Linux-only metadata extension:

- Collection: `roles/run_benchmarks/tasks/setup.yml` adds `linux_perf_context` fields.
- Transport: existing result fetch flow continues unchanged.
- Interpretation: report generation computes OS defaults, host deltas, and salience.
- Presentation: both Markdown and HTML consume the same derived structures.

No new benchmark category is introduced.

## Data model

Add nested object under host metadata:

```json
{
  "linux_perf_context": {
    "vm_swappiness": 60,
    "vm_overcommit_memory": 0,
    "vm_overcommit_ratio": 50,
    "vm_dirty_background_ratio": 10,
    "vm_dirty_ratio": 20,
    "vm_dirty_writeback_centisecs": 500,
    "vm_dirty_expire_centisecs": 3000,
    "vm_zone_reclaim_mode": 0,
    "vm_watermark_scale_factor": 10,
    "kernel_numa_balancing": 1,
    "kernel_sched_autogroup_enabled": 1,
    "thp_defrag": "madvise",
    "zswap_enabled": false,
    "zram_enabled": false,
    "cpu_idle_governor": "menu",
    "cpu_boost_enabled": true
  }
}
```

Field values should be emitted as stable scalar types (int/bool/string) or explicit `"unknown"` when unavailable.

## Curated Linux settings to collect

Primary additions (if not already captured elsewhere):

- VM overcommit and reclaim behavior:
  - `vm.swappiness`
  - `vm.overcommit_memory`
  - `vm.overcommit_ratio`
  - `vm.zone_reclaim_mode`
  - `vm.watermark_scale_factor`
  - `kernel.numa_balancing`
- Dirty page writeback behavior:
  - `vm.dirty_background_ratio` and/or bytes variant fallback
  - `vm.dirty_ratio` and/or bytes variant fallback
  - `vm.dirty_writeback_centisecs`
  - `vm.dirty_expire_centisecs`
- Scheduler-adjacent and memory subsystem toggles:
  - `kernel.sched_autogroup_enabled`
  - THP defrag mode (`/sys/kernel/mm/transparent_hugepage/defrag`)
  - zswap enabled state
  - zram active/present state
- CPU power behavior relevant to performance consistency:
  - idle governor (when exposed)
  - boost/turbo enabled state (intel_pstate/cpufreq source as available)

## Data flow

1. Setup phase probes Linux settings and writes `linux_perf_context` into `metadata.json`.
2. Existing playbook fetches JSON artifacts to controller.
3. Report builder loads all host metadata and selects Linux hosts with known values.
4. For each field:
   - normalize value type,
   - compute per-OS default baseline,
   - compute host delta vs baseline,
   - compute salience signal.
5. Render identical derived results into:
   - Markdown host/OS sections and compact difference tables,
   - HTML host/OS sections and charts for salient fields.

## Salience rules for graphical differences

Graph only when signal is meaningful across relevant hosts:

- **Categorical / boolean fields:** at least two distinct known values across hosts.
- **Numeric fields:** spread exceeds threshold (robust spread rule such as IQR/min-max threshold).
- **Coverage guard:** require minimum known-value coverage (for example, at least 3 hosts or a configurable ratio).

If no field meets salience criteria, render an explicit “no strong cross-host signal detected” message instead of empty charts.

## Presentation requirements (Markdown + HTML parity)

Both outputs should include:

1. **Per-host view:** value, OS default, and deviation marker for each curated field.
2. **Per-OS defaults view:** baseline value per field and host coverage counts.
3. **Differences view:** only salient fields shown graphically (or textual fallback if no signal).

Charts may differ by medium constraints, but field inclusion and underlying derived values must match.

## Error handling and compatibility

- Missing files/paths/sysctls are non-fatal; emit `"unknown"` for that field.
- Parse failures must not silently coerce to plausible but wrong numeric defaults.
- Non-Linux hosts keep current metadata behavior; no forced Linux fields.
- Older result sets without `linux_perf_context` must continue to render without failure.

## Files expected to change

- `roles/run_benchmarks/tasks/setup.yml`
  - add Linux probe tasks and metadata wiring for `linux_perf_context`
- `scripts/generate_benchmark_report.py`
  - add derivation logic (OS defaults, host deltas, salience, parity model)
- `docs/benchmarks.md`
  - document curated fields and interpretation as context metadata
- HTML report generation code/templates used by current report pipeline
  - add host/default/differences rendering based on shared derived model
- Unit tests under `tests/unit/`
  - metadata parsing/normalization
  - default/delta/salience derivation
  - Markdown/HTML parity and fallback behavior

## Testing strategy

1. Unit-test each new probe parsing path (present, absent, malformed).
2. Unit-test default derivation per field type (numeric/categorical/bool).
3. Unit-test salience gating rules and no-signal fallback.
4. Verify report parity: same salient-field set and same default/delta values in Markdown and HTML.
5. Backward-compatibility tests with legacy metadata lacking `linux_perf_context`.

## Scope boundaries

Included:

- Linux metadata collection for curated performance-context settings.
- Report-side default/difference derivation and parity presentation in Markdown/HTML.

Excluded:

- Changing benchmark command behavior/timing methodology.
- Enforcing normalization based on collected settings.
- New top-level benchmark categories.
