# Virtualization Host Columns Design

**Date:** 2026-06-08  
**Scope:** Add virtualization-host context to the benchmark article tables so readers can see the host CPU and host OS alongside each benchmark row.

## Goal

Make the article tables explicitly show which physical virtualization host produced each benchmark result, with a CPU icon for Coffee Lake vs Alder Lake and a dedicated host OS column.

## Architecture

Use a small, hardcoded mapping in the Quarto article for the two known physical hosts. Each table row will gain two presentation-only columns:
- a virtualization-host column with a CPU symbol and short host label
- a host OS column showing the physical host operating system

This is a display-layer change only. Benchmark math, OS grouping, and tuning interpretation remain unchanged.

## Data Model

The article already knows the two physical hosts from the introduction:
- Coffee Lake host (Compulab Airtop3)
- Alder Lake host (Intel NUC12WSHi7)

The new table columns should reflect:
- host CPU family (Coffee Lake / Alder Lake)
- host operating system (short custom label, not necessarily the full distro string)

## Files

- Modify: `docs/benchmarks-article/index.qmd`
  - Add host CPU icons and a virtualization-host OS column to the existing tables.
  - Update the top host summary table and the per-category Gentoo tuning tables.

- Modify: `docs/benchmarks-article/styles.css`
  - Keep the new columns compact and readable.

## Behavior

1. Tables must show the virtualization host for each row with a CPU icon.
2. Tables must also show a host OS column using the approved short label format.
3. The existing sorting and benchmark interpretation logic must not change.
4. If a row cannot be mapped, the article should show a safe placeholder rather than fail.

## Error Handling

- Unknown virtualization-host mappings should render as `unknown`.
- Missing OS labels should fall back to the raw host OS string.
- The article should still render if a row lacks a virtualization-host mapping.

## Testing

- Add a targeted unit check or article-side sanity assertion for the hardcoded host mapping.
- Render the Quarto article and confirm the new columns appear in the host summary and category tables.
- Verify the existing winner interpretation still renders and still refers to the same metrics.

## Scope Boundaries

Included:
- Visualization of the physical virtualization host in tables.
- Host CPU icon and host OS column.

Excluded:
- Changing benchmark result selection or statistics.
- Moving host metadata into the benchmark JSON pipeline.
- Reworking the per-category deep-dive content.
