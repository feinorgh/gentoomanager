# Host detail pages and dataset hyperlinks design

## Goal

Add shareable host detail pages and hyperlink each host in the article's Dataset Summary table so readers can inspect full host context when comparing benchmark results.

## Scope

In scope:

- Generate one host detail page per `benchmarks/results/<host>/metadata.json`.
- Include full metadata (structured sections plus complete key/value table), including parsed `versions`.
- Link Dataset Summary `host` cells to `hosts/<host>.html`.
- Keep current benchmark anonymization behavior unchanged.

Out of scope:

- Changing benchmark collection logic.
- Altering benchmark result aggregation semantics.
- Replacing existing per-section benchmark analysis charts.

## Architecture

### 1. Host page generation

Add `scripts/benchmarks_article_hosts.py` with functions to:

- discover host metadata files under `benchmarks/results/*/metadata.json`,
- load and normalize metadata values,
- parse `versions` entries from `key=value` format,
- render deterministic `.qmd` content per host into `docs/benchmarks-article/hosts/`.

Generated pages use a consistent layout:

1. Identity and platform
2. Hardware and runtime
3. Build and tuning
4. Tool versions
5. Full metadata dump table

### 2. Article integration

In `docs/benchmarks-article/index.qmd`:

- keep the existing Dataset Summary aggregation,
- convert the `host` column to markdown links using each host ID,
- render the table with escaped markdown disabled so links are clickable.

### 3. Quarto integration

Update `docs/benchmarks-article/_quarto.yml` to include a hosts section in the website sidebar/navigation without crowding the top navbar.

## Data flow

`metadata.json` -> host generator script -> `docs/benchmarks-article/hosts/*.qmd` -> Quarto render -> linked host detail HTML pages.

Dataset summary DataFrame -> host link formatting -> markdown table render -> clickable links in article.

## Error handling

- Skip unreadable/invalid metadata files with explicit exceptions in script CLI output.
- Ensure missing optional metadata fields render as `"n/a"` (not empty cells) in host pages.
- Preserve stable output ordering to avoid noisy diffs.

## Testing strategy

Add unit tests covering:

- host path/link generation,
- version parsing and normalization,
- deterministic host page rendering from fixture metadata.

Retain existing article data loader tests; add only host-link-specific assertions.

## Risks and mitigations

- **Risk:** Missing metadata keys across distros produce broken tables.  
  **Mitigation:** normalization helper with defaults and robust rendering for absent fields.
- **Risk:** Generated pages drift from metadata schema changes.  
  **Mitigation:** centralize field mapping in one helper and test with representative fixtures.

## Success criteria

- Dataset Summary host names are clickable links.
- Each link resolves to a host-specific detail page in the rendered site.
- Host pages include full metadata and tool versions for evaluative context.
- Unit tests for new helpers pass.
