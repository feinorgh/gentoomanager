---
title: OpenBSD Benchmarking Integration Design
date: 2026-05-21
status: approved-in-conversation
---

# OpenBSD Benchmarking Integration Design

## Summary

Add OpenBSD as a first-class benchmark target in the `run_benchmarks` suite.
The suite should run as many benchmark categories as are practical on OpenBSD
while excluding tools and behaviors that are not supported or not recommended
on OpenBSD. Safe OpenBSD-specific normalization should be used where available;
Linux- or FreeBSD-specific tuning steps must not be forced onto OpenBSD.

## Problem Statement

The repository already contains partial OpenBSD support in
`provision_benchmarks`, but the benchmark execution role still assumes Linux and
FreeBSD runtime behavior in several places. As a result, OpenBSD can be
provisioned to some extent, yet it is not fully supported as a benchmark target.

Current gaps include:

- package and tool-name mismatches between OpenBSD and the benchmark role;
- Linux- and FreeBSD-specific normalization and metadata probes;
- category tasks that rely on unsupported kernel interfaces or command options;
- documentation that does not list OpenBSD as a supported runtime target;
- lack of OpenBSD-specific validation for benchmark behavior and skip semantics.

## Goals

- Treat OpenBSD as a supported Unix target in `roles/run_benchmarks`.
- Run all benchmark categories that work with standard OpenBSD packages or
  standard ports that are still considered normal and recommended.
- Use only safe, supported OpenBSD normalization behavior.
- Skip unsupported categories and sub-benchmarks explicitly, with clear reasons.
- Make OpenBSD support visible in documentation, metadata, and tests.

## Non-Goals

- Force full feature parity with Linux or FreeBSD where OpenBSD does not expose
  equivalent interfaces.
- Rely on non-recommended tools or unsupported kernel tuning features just to
  increase category count.
- Hide real implementation bugs behind broad skip behavior.

## Design Principles

1. **Portable first:** prefer portable command paths and behavior over OS
   special cases where that keeps the benchmark honest.
2. **OpenBSD-aware, not Linux-compatible-by-accident:** support should come
   from explicit OpenBSD logic, not from whatever happens to work today.
3. **Safe subset normalization:** if OpenBSD lacks a safe equivalent for a
   Linux or FreeBSD tuning step, omit that step and record the limitation.
4. **Explicit capability reporting:** distinguish supported, unsupported, and
   unknown features in metadata and reporting.
5. **Category-level clarity:** support decisions should be made per category or
   sub-benchmark, not as a blanket all-or-nothing decision.

## Target State

OpenBSD is considered fully integrated when:

- `run_benchmarks` treats OpenBSD as a supported target platform;
- supported categories run without relying on non-recommended tools;
- unsupported categories are skipped intentionally with explicit reasons;
- normalization is limited to the safe OpenBSD subset;
- generated metadata and documentation explain what is supported on OpenBSD;
- tests validate OpenBSD-specific branching and reporting behavior.

## Architecture

### 1. Platform handling in `run_benchmarks`

`roles/run_benchmarks` should add explicit OpenBSD handling in all runtime
paths that currently branch only on Linux, FreeBSD, or Windows.

Affected areas:

- `tasks/setup.yml`
- `tasks/normalize.yml`
- `tasks/denormalize.yml`
- `tasks/run_category.yml`
- `tasks/sanity_check.yml`

OpenBSD should not be modeled as a variant of FreeBSD. The role should instead
branch on `ansible_facts["system"] == "OpenBSD"` where runtime behavior differs.

### 2. Capability-driven runtime behavior

Setup should compute an OpenBSD capability picture once and make later tasks use
that information instead of re-probing arbitrary interfaces.

The metadata model should distinguish:

- **supported**: feature exists and can be used safely on OpenBSD;
- **unsupported**: feature is not available or is not recommended on OpenBSD;
- **unknown**: the suite does not have a safe/public interface to determine it.

This avoids pretending that missing Linux sysfs data means failure when the real
answer is that the concept is not observable on OpenBSD in the same way.

## Provisioning Design

### 1. OpenBSD as a capability builder

`roles/provision_benchmarks/tasks/os/openbsd.yml` should evolve from a minimal
package installation task into the OpenBSD provisioning entrypoint for benchmark
capabilities.

It should ensure that the installed tools match what `run_benchmarks` actually
invokes, including:

- shell interpreter support for Bash benchmarks when Bash is intended to run;
- compiler and linker entrypoints expected by the suite;
- Python command resolution expected by metadata and benchmark tasks;
- crypto, media, image, and database command-line tools used by categories;
- optional scientific and graphics dependencies for conditional categories.

### 2. Package source policy

The design assumes:

- use packages first;
- use standard ports when that is still considered a normal and recommended
  OpenBSD path for the tool;
- do not depend on tools that are unsupported or not recommended on OpenBSD.

This means a category may be considered supported through ports if that is still
an acceptable standard OpenBSD workflow, but not through ad hoc or dubious
installation methods.

### 3. Command resolution

The suite currently assumes universal command names such as `gcc`, `python3`,
and `sudo`. OpenBSD support should replace those assumptions with explicit
resolution rules.

Resolution should follow this order:

1. preferred command name for the current OS;
2. acceptable alternate command names;
3. provisioning-created stable aliases, if the repository already uses that
   pattern safely for the platform;
4. explicit unsupported state if no supported command exists.

This keeps runtime tasks simple without depending on accidental PATH behavior.

## Runtime Design

### 1. Setup and metadata collection

`setup.yml` should:

- gather OpenBSD metadata where there is a stable interface;
- record `unknown` for Linux-only concepts that have no OpenBSD equivalent;
- avoid Linux-only command options such as GNU-specific `grep -P`, `df --output`,
  or `/proc` and `/sys` paths unless guarded out;
- expose the resolved command paths and category capabilities for downstream
  tasks.

OpenBSD metadata fields do not need to match Linux field-for-field in
implementation, but the output shape should remain consistent enough for reports
and downstream consumers.

### 2. Safe-subset normalization

`normalize.yml` and `denormalize.yml` should implement only safe OpenBSD tuning.

If an existing Linux or FreeBSD normalization feature has no clear OpenBSD
equivalent, the design is to:

- omit that step on OpenBSD;
- record that reduced normalization applied;
- keep the benchmark runnable unless the category explicitly requires the
  missing behavior.

Unsupported normalization must not be treated as benchmark failure by itself.

### 3. Category dispatch

`run_category.yml` should become OpenBSD-aware. It must not run Linux-specific
cache-dropping or other preparation commands unconditionally.

The dispatch layer should support:

- pre-category preparation valid on OpenBSD;
- per-category skip decisions with reasons;
- partial category execution where only some sub-benchmarks are unsuitable.

## Category Support Policy

### Tier 1: expected to run on OpenBSD

These categories are the default target set once provisioning and runtime
handling are corrected:

- compression
- crypto
- python
- numeric
- sqlite
- memory
- process
- linker
- coreutils, when required tool behavior is supported
- bash, when Bash is installed through an accepted OpenBSD path

### Tier 2: conditional support

These categories depend on package availability, command behavior, or acceptable
ports support:

- ffmpeg
- imagemagick
- octave
- opencv
- gimp
- inkscape

They should be supported on OpenBSD only if the toolchain is available through
the approved package-source policy.

### Tier 3: platform review required

These categories need dedicated OpenBSD review because the current
implementation is tied to Linux or FreeBSD assumptions:

- disk
- boot_time

For these categories, the design goal is:

- implement an OpenBSD-native path if a safe and meaningful one exists;
- otherwise mark the category unsupported on OpenBSD with a clear reason.

## Error Handling and Skip Semantics

OpenBSD support must preserve the difference between an unsupported benchmark
and a broken supported benchmark.

### Unsupported cases

Use explicit skip behavior when:

- the required tool is unavailable through approved OpenBSD sources;
- the benchmark depends on an interface not supported on OpenBSD;
- the task relies on behavior that is not recommended on OpenBSD.

Skip metadata should state whether the cause is:

- missing tool,
- unsupported platform feature,
- excluded by OpenBSD policy,
- disabled due to unsupported normalization dependency.

### Broken supported cases

If a category is declared supported on OpenBSD and then fails because of bad
task logic, bad command construction, or invalid assumptions, it should remain a
real failure. The design must not paper over such failures by silently treating
them as skips.

## Reporting and Documentation

### 1. User-facing docs

Update the benchmark documentation and role README to list OpenBSD as a
supported target with category-level caveats.

Documentation should describe three states:

- supported;
- supported with reduced normalization;
- unsupported on OpenBSD.

### 2. Metadata and notes

Benchmark metadata and notes should capture:

- missing tools;
- distro-specific or platform-specific limitations;
- reduced normalization on OpenBSD;
- explicit reasons for skipped categories or sub-benchmarks.

This makes report output reproducible and avoids ambiguous omissions.

## Testing Strategy

Testing should focus on OpenBSD-specific decision logic even if CI cannot run a
full native OpenBSD benchmark host for every category.

### Required test coverage

- OpenBSD provisioning package and capability decisions.
- Verification behavior for OpenBSD command naming differences.
- Sanity checks without Linux-only `sudo` assumptions.
- OpenBSD setup metadata behavior for supported, unsupported, and unknown
  fields.
- Category gating and skip reasons for unsupported OpenBSD categories.
- Reduced-normalization behavior on OpenBSD.

### Test philosophy

Tests do not need to prove every OpenBSD package exists in CI. They do need to
prove that:

- OpenBSD-specific branches are exercised;
- supported-versus-unsupported decisions are stable;
- skip reasons are explicit and preserved;
- the role does not accidentally regress back to Linux-only assumptions.

## Implementation Boundaries

This design intentionally stays within the benchmark suite and directly related
documentation/tests. It does not propose unrelated refactors outside:

- `roles/provision_benchmarks`
- `roles/run_benchmarks`
- benchmark docs and playbook comments
- directly relevant tests

## Acceptance Criteria

The implementation should be considered complete when all of the following are
true:

1. OpenBSD is documented as a supported runtime target.
2. The benchmark runner has explicit OpenBSD runtime branches where needed.
3. Supported OpenBSD categories run without depending on non-recommended tools.
4. Unsafe or unsupported normalization is replaced by a safe subset.
5. Unsupported categories are skipped with durable, user-visible reasons.
6. Tests validate OpenBSD-specific provisioning, setup, normalization, and skip
   semantics.

