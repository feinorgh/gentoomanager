# Virtualization Host Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the physical virtualization host CPU and host OS directly in the benchmark article tables.

**Architecture:** Keep the data source simple and local to the article: use a small hardcoded mapping for the two physical hosts already described in the intro, then render a CPU badge column and a host OS column in the existing tables. Leave benchmark statistics, host grouping, and winner calculations unchanged; this is presentation-only metadata.

**Tech Stack:** Quarto, Python (inside `index.qmd`), pandas, Plotly, CSS.

---

## File Structure

- Modify: `docs/benchmarks-article/index.qmd`
  - Add a small virtualization-host mapping helper.
  - Add a CPU badge column and a host OS column to the intro host summary table.
  - Add the same columns to the per-category Gentoo tuning tables.

- Modify: `docs/benchmarks-article/styles.css`
  - Keep the new columns narrow and readable.

---

### Task 1: Add virtualization-host columns to the article tables

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`

- [ ] **Step 1: Write the failing render check**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && \
uv run quarto render docs/benchmarks-article/index.qmd && \
rg -n "Virtualization Host|Host OS|☕|🧊|Gentoo \\(Alder Lake\\)|Gentoo \\(Coffee Lake\\)" docs/benchmarks-article/_site/index.html
```

Expected: no matches yet for the new table columns or host labels.

- [ ] **Step 2: Write the minimal implementation**

Add a small helper in the article Python cell and update both table builders:

```python
def virtualization_host_fields(march_native: str) -> tuple[str, str]:
    if march_native == "alderlake":
        return "🧊 Alder Lake", "Gentoo (Alder Lake)"
    if march_native == "skylake":
        return "☕ Coffee Lake", "Gentoo (Coffee Lake)"
    return "?", "unknown"
```

Then add the new columns to the generated HTML tables:

```python
md_table = "| Host | Virtualization Host | Host OS | Profile | LTO | PGO | Graphite | CFLAGS |\n"
md_table += "|------|---------------------|---------|---------|-----|-----|----------|--------|\n"
```

and for each row:

```python
virt_host, host_os = virtualization_host_fields(row["march_native"])
md_table += f"| {host} | {virt_host} | {host_os} | {profile} | {lto} | {pgo} | {graphite} | {cflags_expanded} |\n"
```

- [ ] **Step 3: Run the render check again**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && \
uv run quarto render docs/benchmarks-article/index.qmd && \
rg -n "Virtualization Host|Host OS|☕|🧊|Gentoo \\(Alder Lake\\)|Gentoo \\(Coffee Lake\\)" docs/benchmarks-article/_site/index.html
```

Expected: the new headers and host labels are present in the rendered HTML.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/index.qmd
git commit -m "docs: add virtualization host columns"
```

---

### Task 2: Narrow the new columns with CSS

**Files:**
- Modify: `docs/benchmarks-article/styles.css`

- [ ] **Step 1: Write the failing visual check**

Render the article after Task 1 and observe that the new columns are too wide without explicit sizing.

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: render succeeds, but the new host columns need compact styling.

- [ ] **Step 2: Write the minimal implementation**

Add column-specific CSS:

```css
.virtualization-host-col {
  width: 10rem;
  white-space: nowrap;
}

.host-os-col {
  width: 11rem;
  white-space: nowrap;
}
```

and apply those classes to the new table cells and headers in `index.qmd`.

- [ ] **Step 3: Re-render and verify**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: the article still renders successfully and the new columns remain compact and readable.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/styles.css docs/benchmarks-article/index.qmd
git commit -m "docs: style virtualization host columns"
```

---

## Self-Review

- Spec coverage: the plan adds the requested CPU icon column and host OS column, keeps the existing benchmark math untouched, and updates the article tables where the user asked.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: the helper returns the exact tuple shape used by the table builders, and the CSS class names match the article markup.
