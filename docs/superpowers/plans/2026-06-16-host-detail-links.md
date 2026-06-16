# Host Detail Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-host detail pages and wire Dataset Summary host names to clickable links in the Quarto benchmark article.

**Architecture:** Add a focused host-page generator in `scripts/` that reads `benchmarks/results/*/metadata.json` and writes deterministic `.qmd` pages under `docs/benchmarks-article/hosts/`. Update the article notebook code to render markdown links in the summary table. Keep existing benchmark row loading and anonymization behavior unchanged.

**Tech Stack:** Python 3, pandas in Quarto python cells, pytest, Quarto website config.

---

### Task 1: Add failing tests for host-link rendering helpers

**Files:**
- Create: `tests/unit/test_benchmarks_article_hosts.py`
- Modify: `tests/unit/test_benchmarks_article_data.py`
- Test: `tests/unit/test_benchmarks_article_hosts.py`

- [ ] **Step 1: Write failing tests for host link formatting and metadata normalization**

```python
from scripts import benchmarks_article_hosts as hosts


def test_host_link_markdown_uses_hosts_html_path() -> None:
    assert hosts.host_link_markdown("gentoo-alma") == "[gentoo-alma](hosts/gentoo-alma.html)"


def test_parse_versions_list_handles_key_value_lines() -> None:
    parsed = hosts.parse_versions_list(["gcc=gcc (Gentoo) 15.2.1", "ffmpeg=ffmpeg version 8.1"])
    assert parsed["gcc"].startswith("gcc (Gentoo)")
    assert parsed["ffmpeg"].startswith("ffmpeg version")


def test_normalize_metadata_populates_na_for_missing_optional_fields() -> None:
    normalized = hosts.normalize_metadata({"hostname": "debian-debbie"})
    assert normalized["cpu_model"] == "n/a"
    assert normalized["os"] == "n/a"
```

- [ ] **Step 2: Run tests to verify they fail first**

Run: `uv run pytest tests/unit/test_benchmarks_article_hosts.py -q`  
Expected: FAIL with import or missing symbol errors until implementation exists.

- [ ] **Step 3: Add article-level regression test for host link expression in dataset summary block**

```python
def test_article_dataset_summary_builds_host_links() -> None:
    qmd = Path(REPO_ROOT / "docs/benchmarks-article/index.qmd").read_text(encoding="utf-8")
    assert "summary[\"host_link\"]" in qmd
    assert "to_markdown(index=False)" in qmd
```

- [ ] **Step 4: Run targeted existing tests**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py -q`  
Expected: PASS except the newly added host-link assertion until article update is done.

- [ ] **Step 5: Commit tests**

```bash
git add tests/unit/test_benchmarks_article_hosts.py tests/unit/test_benchmarks_article_data.py
git commit -m "tests: add host detail link coverage"
```

### Task 2: Implement host detail page generator and link helpers

**Files:**
- Create: `scripts/benchmarks_article_hosts.py`
- Modify: `scripts/benchmarks_article_data.py`
- Test: `tests/unit/test_benchmarks_article_hosts.py`

- [ ] **Step 1: Implement minimal helper API used by tests**

```python
def host_link_markdown(hostname: str) -> str:
    safe = str(hostname).strip()
    return f"[{safe}](hosts/{safe}.html)"


def parse_versions_list(values: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        key, parsed = value.split("=", 1)
        versions[key.strip()] = parsed.strip() or "n/a"
    return versions
```

- [ ] **Step 2: Implement metadata normalization and host-page rendering**

```python
def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    for key in ["hostname", "os", "os_family", "os_version", "cpu_model", "cflags", "common_flags", "ldflags"]:
        normalized[key] = str(normalized.get(key, "")).strip() or "n/a"
    normalized["versions_parsed"] = parse_versions_list(list(metadata.get("versions", [])))
    return normalized
```

- [ ] **Step 3: Implement filesystem generation entrypoint**

```python
def generate_host_pages(results_dir: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for metadata_file in sorted(results_dir.glob("*/metadata.json")):
        metadata = json.loads(metadata_file.read_text())
        host = str(metadata.get("hostname", metadata_file.parent.name))
        page_path = output_dir / f"{host}.qmd"
        page_path.write_text(render_host_qmd(normalize_metadata(metadata)), encoding="utf-8")
        written.append(page_path)
    return written
```

- [ ] **Step 4: Re-export or mirror host-link helper in article data module if needed**

```python
from benchmarks_article_hosts import host_link_markdown
```

- [ ] **Step 5: Run tests and commit implementation**

Run: `uv run pytest tests/unit/test_benchmarks_article_hosts.py tests/unit/test_benchmarks_article_data.py -q`  
Expected: PASS.

```bash
git add scripts/benchmarks_article_hosts.py scripts/benchmarks_article_data.py
git commit -m "feat: generate host detail pages and link helpers"
```

### Task 3: Wire links into article and include host pages in Quarto site

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`
- Modify: `docs/benchmarks-article/_quarto.yml`
- Create: `docs/benchmarks-article/hosts/.gitkeep` (if directory absent)
- Test: `tests/unit/test_benchmarks_article_data.py`

- [ ] **Step 1: Update Dataset Summary cell rendering to markdown links**

```python
summary["host_link"] = summary["host"].map(lambda value: f"[{value}](hosts/{value}.html)")
summary = summary.drop(columns=["host"]).rename(columns={"host_link": "host"})
from IPython.display import Markdown, display
display(Markdown(summary.to_markdown(index=False)))
```

- [ ] **Step 2: Add host pages content listing to Quarto config**

```yaml
website:
  sidebar:
    - title: "Host Details"
      style: "docked"
      contents: "hosts/*.qmd"
```

- [ ] **Step 3: Generate initial host pages from current benchmark metadata**

Run: `uv run python scripts/benchmarks_article_hosts.py --results benchmarks/results --output docs/benchmarks-article/hosts`  
Expected: one `.qmd` per host appears in `docs/benchmarks-article/hosts/`.

- [ ] **Step 4: Run targeted tests and render**

Run: `uv run pytest tests/unit/test_benchmarks_article_hosts.py tests/unit/test_benchmarks_article_data.py -q`  
Expected: PASS.

Run: `quarto render docs/benchmarks-article`  
Expected: render succeeds and Dataset Summary host links open host pages.

- [ ] **Step 5: Commit article integration**

```bash
git add docs/benchmarks-article/index.qmd docs/benchmarks-article/_quarto.yml docs/benchmarks-article/hosts
git commit -m "feat: add host detail pages to benchmark article"
```
