# Linux Perf Context Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect curated Linux performance-affecting settings into benchmark metadata and present host values, OS defaults, and salient cross-host differences in both Markdown and HTML reports.

**Architecture:** Extend existing metadata collection with a Linux-only `linux_perf_context` object, then compute one shared derived signal model in `generate_benchmark_report.py`. Render that model into both Markdown and HTML so both surfaces have parity for host/default/difference views and no-signal fallback.

**Tech Stack:** Ansible role tasks (YAML), Python 3.10+ report generator, pytest, Chart.js HTML output.

---

## File structure and responsibilities

- **Modify:** `roles/run_benchmarks/tasks/setup.yml`
  - Collect curated Linux perf-context fields and store under `run_benchmarks_metadata.linux_perf_context`.
- **Modify:** `scripts/generate_benchmark_report.py`
  - Normalize perf-context values, derive OS defaults and host deltas, compute salience, and render Markdown/HTML sections from one shared structure.
- **Modify:** `tests/unit/test_benchmark_report.py`
  - Add focused tests for normalization, OS-default derivation, salience gating, Markdown/HTML parity, and no-signal fallback.
- **Modify:** `docs/benchmarks.md`
  - Document `linux_perf_context` fields and explain "context metadata" semantics.

### Task 1: Add failing report tests for perf-context derivation and parity

**Files:**
- Modify: `tests/unit/test_benchmark_report.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add a metadata helper variant that includes linux perf context**

```python
def _make_metadata_with_perf(hostname: str, perf: dict[str, object]) -> dict:
    md = _make_metadata(hostname)
    md["os"] = "Gentoo"
    md["os_family"] = "Gentoo"
    md["linux_perf_context"] = perf
    return md
```

- [ ] **Step 2: Add failing test for OS default + host delta in Markdown**

```python
def test_markdown_includes_linux_perf_context_defaults_and_deltas(tmp_path: Path) -> None:
    results = tmp_path / "results"
    a = results / "h1"
    b = results / "h2"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    (a / "metadata.json").write_text(
        json.dumps(
            _make_metadata_with_perf(
                "h1",
                {"vm_swappiness": 10, "kernel_sched_autogroup_enabled": 1, "thp_defrag": "madvise"},
            )
        )
    )
    (b / "metadata.json").write_text(
        json.dumps(
            _make_metadata_with_perf(
                "h2",
                {"vm_swappiness": 60, "kernel_sched_autogroup_enabled": 1, "thp_defrag": "always"},
            )
        )
    )
    (a / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 1.0, 0.01))))
    (b / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 0.9, 0.01))))

    hosts = load_results(tmp_path)
    table = build_comparison_table(hosts)
    md = generate_markdown(hosts, table)

    assert "Linux Performance Context — Host vs OS Defaults" in md
    assert "vm_swappiness" in md
    assert "thp_defrag" in md
```

- [ ] **Step 3: Add failing test for salient-differences section in HTML**

```python
def test_html_includes_linux_perf_context_salient_differences(tmp_path: Path) -> None:
    results = tmp_path / "results"
    a = results / "h1"
    b = results / "h2"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    (a / "metadata.json").write_text(
        json.dumps(_make_metadata_with_perf("h1", {"vm_swappiness": 10, "thp_defrag": "madvise"}))
    )
    (b / "metadata.json").write_text(
        json.dumps(_make_metadata_with_perf("h2", {"vm_swappiness": 80, "thp_defrag": "always"}))
    )
    (a / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 1.0, 0.01))))
    (b / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 0.9, 0.01))))

    hosts = load_results(tmp_path)
    table = build_comparison_table(hosts)
    html = generate_html(hosts, table)

    assert "Linux Performance Context — Salient Differences" in html
    assert "linux-perf-context-chart" in html
```

- [ ] **Step 4: Add failing test for no-signal fallback parity**

```python
def test_perf_context_no_signal_fallback_in_both_outputs(tmp_path: Path) -> None:
    results = tmp_path / "results"
    a = results / "h1"
    b = results / "h2"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    perf = {"vm_swappiness": 60, "thp_defrag": "madvise", "kernel_sched_autogroup_enabled": 1}
    (a / "metadata.json").write_text(json.dumps(_make_metadata_with_perf("h1", perf)))
    (b / "metadata.json").write_text(json.dumps(_make_metadata_with_perf("h2", perf)))
    (a / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 1.0, 0.01))))
    (b / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 0.9, 0.01))))

    hosts = load_results(tmp_path)
    table = build_comparison_table(hosts)
    md = generate_markdown(hosts, table)
    html = generate_html(hosts, table)

    assert "No strong cross-host signal detected" in md
    assert "No strong cross-host signal detected" in html
```

- [ ] **Step 5: Run test subset to confirm failures**

Run:  
`uv run pytest tests/unit/test_benchmark_report.py -k "perf_context or linux_perf_context" -v`

Expected: FAIL (new sections/helpers not implemented yet).

- [ ] **Step 6: Commit test additions**

```bash
git add tests/unit/test_benchmark_report.py
git commit -m "test: add failing linux perf-context report coverage"
```

### Task 2: Implement shared perf-context normalization and signal derivation

**Files:**
- Modify: `scripts/generate_benchmark_report.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add field catalog and normalization helpers**

```python
_LINUX_PERF_FIELDS: dict[str, dict[str, str]] = {
    "vm_swappiness": {"type": "int"},
    "vm_overcommit_memory": {"type": "int"},
    "vm_overcommit_ratio": {"type": "int"},
    "vm_dirty_background_ratio": {"type": "int"},
    "vm_dirty_ratio": {"type": "int"},
    "vm_dirty_writeback_centisecs": {"type": "int"},
    "vm_dirty_expire_centisecs": {"type": "int"},
    "vm_zone_reclaim_mode": {"type": "int"},
    "vm_watermark_scale_factor": {"type": "int"},
    "kernel_numa_balancing": {"type": "boolish"},
    "kernel_sched_autogroup_enabled": {"type": "boolish"},
    "thp_defrag": {"type": "str"},
    "zswap_enabled": {"type": "boolish"},
    "zram_enabled": {"type": "boolish"},
    "cpu_idle_governor": {"type": "str"},
    "cpu_boost_enabled": {"type": "boolish"},
}
```

- [ ] **Step 2: Add a shared derivation function consumed by both outputs**

```python
def _derive_linux_perf_context(hosts: dict[str, dict[str, Any]], hostnames: list[str]) -> dict[str, Any]:
    host_features = {h: extract_features(hosts[h].get("metadata", {})) for h in hostnames}
    os_defaults: dict[str, dict[str, str]] = {}
    host_rows: list[dict[str, str]] = []
    coverage: dict[str, dict[str, int]] = {}

    for field in _LINUX_PERF_FIELDS:
        by_os: dict[str, list[str]] = defaultdict(list)
        all_values: list[str] = []
        known_count = 0
        for host in hostnames:
            os_family = host_features[host].get("os_family", "unknown")
            value = host_features[host].get(field, "unknown")
            all_values.append(value)
            if value != "unknown":
                known_count += 1
                by_os[os_family].append(value)
        coverage[field] = {"known": known_count, "total": len(hostnames)}

        for os_family, values in by_os.items():
            if os_family not in os_defaults:
                os_defaults[os_family] = {}
            os_defaults[os_family][field] = sorted(values)[0]

        for host in hostnames:
            os_family = host_features[host].get("os_family", "unknown")
            value = host_features[host].get(field, "unknown")
            default = os_defaults.get(os_family, {}).get(field, "unknown")
            delta = "same" if value == default else "different"
            host_rows.append(
                {"host": host, "os_family": os_family, "field": field, "value": value, "os_default": default, "delta": delta}
            )

    salient_fields = [
        field
        for field, cfg in _LINUX_PERF_FIELDS.items()
        if _is_field_salient([r["value"] for r in host_rows if r["field"] == field], cfg["type"])
    ]
    return {"host_rows": host_rows, "os_defaults": os_defaults, "salient_fields": salient_fields, "coverage": coverage}
```

- [ ] **Step 3: Implement salience rules (categorical split + numeric spread)**

```python
def _is_field_salient(values: list[Any], field_type: str) -> bool:
    known = [v for v in values if v not in ("unknown", "", None)]
    if len(known) < 3:
        return False
    if field_type in {"str", "boolish"}:
        return len(set(known)) >= 2
    nums = [float(v) for v in known]
    return (max(nums) - min(nums)) >= 5.0
```

- [ ] **Step 4: Add small pure helper tests for derivation internals**

```python
def test_perf_context_salience_numeric_threshold() -> None:
    assert _is_field_salient(["10", "20", "30"], "int") is True
    assert _is_field_salient(["10", "11", "12"], "int") is False
    assert _is_field_salient(["madvise", "always", "always"], "str") is True
    assert _is_field_salient(["madvise", "madvise", "madvise"], "str") is False
```

- [ ] **Step 5: Run targeted tests to verify pass**

Run:  
`uv run pytest tests/unit/test_benchmark_report.py -k "perf_context or linux_perf_context" -v`

Expected: PASS.

- [ ] **Step 6: Commit derivation logic**

```bash
git add scripts/generate_benchmark_report.py tests/unit/test_benchmark_report.py
git commit -m "feat: derive linux perf-context defaults and salience model"
```

### Task 3: Render Markdown and HTML sections from the shared model

**Files:**
- Modify: `scripts/generate_benchmark_report.py`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add Markdown sections after runtime environment table**

```python
lines.append("## Linux Performance Context — Host vs OS Defaults")
lines.append("")
lines.append(_md_table(
    ["Host", "OS", "Field", "Value", "OS Default", "Delta"],
    perf_rows_md,
))
lines.append("")
lines.append("## Linux Performance Context — OS Defaults")
lines.append("")
lines.append(_md_table(["OS", "Field", "Default", "Coverage"], os_default_rows_md))
```

- [ ] **Step 2: Add Markdown salient-differences section with fallback**

```python
lines.append("## Linux Performance Context — Salient Differences")
lines.append("")
if perf_model["salient_fields"]:
    lines.append(_md_table(["Field", "Distinct values", "Coverage"], salient_rows_md))
else:
    lines.append("No strong cross-host signal detected.")
lines.append("")
```

- [ ] **Step 3: Add HTML host/default/salient sections with chart container**

```python
perf_context_html = f"""
<section id="cat-linux-perf-context">
  <h2>Linux Performance Context — Host vs OS Defaults</h2>
  {host_vs_default_table_html}
  <h3>OS Defaults</h3>
  {os_defaults_table_html}
  <h3>Salient Differences</h3>
  <div class="chart-container"><canvas id="linux-perf-context-chart"></canvas></div>
  {salience_fallback_html}
</section>"""
```

- [ ] **Step 4: Add Chart.js dataset generation gated by salient fields**

```python
if perf_model["salient_fields"]:
    chart_blocks.append(
        f"""
CHARTS['linux-perf-context-chart'] = new Chart(
  document.getElementById('linux-perf-context-chart'),
  {{
    type: 'bar',
    data: {salient_chart_data_json},
    options: {{responsive: true}}
  }}
);"""
    )
```

- [ ] **Step 5: Add/adjust assertions for section parity**

```python
def test_perf_context_section_parity_between_markdown_and_html(tmp_path: Path) -> None:
    results = tmp_path / "results"
    a = results / "h1"
    b = results / "h2"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "metadata.json").write_text(json.dumps(_make_metadata_with_perf("h1", {"vm_swappiness": 10})))
    (b / "metadata.json").write_text(json.dumps(_make_metadata_with_perf("h2", {"vm_swappiness": 70})))
    (a / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 1.0, 0.01))))
    (b / "compression.json").write_text(json.dumps(_make_hyperfine_json(("gzip", 0.9, 0.01))))
    hosts = load_results(tmp_path)
    table = build_comparison_table(hosts)
    md = generate_markdown(hosts, table)
    html = generate_html(hosts, table)
    assert "Linux Performance Context — Host vs OS Defaults" in md
    assert "Linux Performance Context — Host vs OS Defaults" in html
    assert "Linux Performance Context — Salient Differences" in md
    assert "Linux Performance Context — Salient Differences" in html
```

- [ ] **Step 6: Run focused report tests**

Run:  
`uv run pytest tests/unit/test_benchmark_report.py -k "perf_context or runtime environment" -v`

Expected: PASS.

- [ ] **Step 7: Commit rendering changes**

```bash
git add scripts/generate_benchmark_report.py tests/unit/test_benchmark_report.py
git commit -m "feat: render linux perf-context defaults and differences in md/html"
```

### Task 4: Collect missing Linux settings in role metadata and document behavior

**Files:**
- Modify: `roles/run_benchmarks/tasks/setup.yml`
- Modify: `docs/benchmarks.md`
- Test: `tests/unit/test_benchmark_report.py`

- [ ] **Step 1: Add Linux probe tasks for curated perf-context keys**

```yaml
- name: Collect Linux perf-context sysctl snapshot
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      for key in \
        vm.swappiness vm.overcommit_memory vm.overcommit_ratio \
        vm.dirty_background_ratio vm.dirty_ratio \
        vm.dirty_writeback_centisecs vm.dirty_expire_centisecs \
        vm.zone_reclaim_mode vm.watermark_scale_factor \
        kernel.numa_balancing kernel.sched_autogroup_enabled; do
        val=$(sysctl -n "$key" 2>/dev/null || echo unknown)
        echo "${key}=${val}"
      done
  register: run_benchmarks_linux_perf_sysctl_raw
  changed_when: false
  failed_when: false
  when: ansible_system | default('') == 'Linux'
```

- [ ] **Step 2: Add sysfs probes for THP defrag, zswap/zram, idle governor, boost**

```yaml
- name: Collect Linux perf-context sysfs snapshot
  ansible.builtin.shell:
    cmd: |
      set -eo pipefail
      thp_defrag=$(grep -oP '\[\K[^\]]+' /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null || echo unknown)
      zswap_enabled=$(cat /sys/module/zswap/parameters/enabled 2>/dev/null || echo unknown)
      zram_enabled=$(ls /sys/block | grep -q '^zram' && echo 1 || echo 0)
      idle_governor=$(cat /sys/devices/system/cpu/cpuidle/current_governor_ro 2>/dev/null || echo unknown)
      boost_enabled=$(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo unknown)
      printf 'thp_defrag=%s\nzswap_enabled=%s\nzram_enabled=%s\ncpu_idle_governor=%s\ncpu_boost_enabled=%s\n' \
        "$thp_defrag" "$zswap_enabled" "$zram_enabled" "$idle_governor" "$boost_enabled"
  register: run_benchmarks_linux_perf_sysfs_raw
  changed_when: false
  failed_when: false
  when: ansible_system | default('') == 'Linux'
```

- [ ] **Step 3: Wire parsed values into `run_benchmarks_metadata.linux_perf_context`**

```yaml
      linux_perf_context: >-
        {{
          {
            'vm_swappiness': _linux_perf_ctx.get('vm.swappiness', 'unknown'),
            'vm_overcommit_memory': _linux_perf_ctx.get('vm.overcommit_memory', 'unknown'),
            'vm_overcommit_ratio': _linux_perf_ctx.get('vm.overcommit_ratio', 'unknown'),
            'vm_dirty_background_ratio': _linux_perf_ctx.get('vm.dirty_background_ratio', 'unknown'),
            'vm_dirty_ratio': _linux_perf_ctx.get('vm.dirty_ratio', 'unknown'),
            'vm_dirty_writeback_centisecs': _linux_perf_ctx.get('vm.dirty_writeback_centisecs', 'unknown'),
            'vm_dirty_expire_centisecs': _linux_perf_ctx.get('vm.dirty_expire_centisecs', 'unknown'),
            'vm_zone_reclaim_mode': _linux_perf_ctx.get('vm.zone_reclaim_mode', 'unknown'),
            'vm_watermark_scale_factor': _linux_perf_ctx.get('vm.watermark_scale_factor', 'unknown'),
            'kernel_numa_balancing': _linux_perf_ctx.get('kernel.numa_balancing', 'unknown'),
            'kernel_sched_autogroup_enabled': _linux_perf_ctx.get('kernel.sched_autogroup_enabled', 'unknown'),
            'thp_defrag': _linux_perf_ctx.get('thp_defrag', 'unknown'),
            'zswap_enabled': _linux_perf_ctx.get('zswap_enabled', 'unknown'),
            'zram_enabled': _linux_perf_ctx.get('zram_enabled', 'unknown'),
            'cpu_idle_governor': _linux_perf_ctx.get('cpu_idle_governor', 'unknown'),
            'cpu_boost_enabled': _linux_perf_ctx.get('cpu_boost_enabled', 'unknown')
          }
        }}
```

- [ ] **Step 4: Document new metadata fields and salience behavior**

```markdown
### Linux performance-context metadata

`metadata.json` now includes `linux_perf_context` for Linux hosts. These fields are
context signals (not benchmark timing results) and are used to compute:
1. host-vs-OS-default comparisons,
2. per-OS defaults, and
3. salient-difference charts when cross-host variation is meaningful.
```

- [ ] **Step 5: Run focused validation commands**

Run:
`uv run pytest tests/unit/test_benchmark_report.py -k "perf_context or linux_perf_context" -v`  
`uv run ansible-lint`  
`uv run ruff check scripts/ tests/`

Expected: PASS with no new lint violations.

- [ ] **Step 6: Commit role + docs updates**

```bash
git add roles/run_benchmarks/tasks/setup.yml scripts/generate_benchmark_report.py tests/unit/test_benchmark_report.py docs/benchmarks.md
git commit -m "feat: collect and visualize linux perf-context defaults and differences"
```

## Final verification

- [ ] Run: `uv run pytest tests/unit/test_benchmark_report.py tests/unit/test_benchmark_dashboard.py`
- [ ] Run: `uv run ruff check scripts/ tests/ && uv run ruff format --check scripts/ tests/`
- [ ] Run: `uv run ansible-lint`
- [ ] Run: `uv run python scripts/shellcheck_yaml_blocks.py`
- [ ] Confirm reports generate with: `uv run python scripts/generate_benchmark_report.py benchmarks/`

## Notes

- Keep non-Linux hosts unaffected (`linux_perf_context` absent or empty).
- Keep benchmark execution behavior unchanged; this is metadata + presentation only.
- If salience thresholds need tuning, adjust in one place (`_is_field_salient`) and keep Markdown/HTML parity intact.
