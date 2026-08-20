# Quarto Benchmark Article

This directory contains a Quarto project for long-form benchmark analysis.

## Local preview

```bash
uv sync --group docs
source .venv/bin/activate
quarto preview docs/benchmarks-article
```

## Data source

The article reads benchmark JSON from:

`benchmarks/results/<host>/*.json`

through:

`scripts/benchmarks_article_data.py`

Hostnames are anonymized by default using deterministic Greek mythology aliases.
To disable anonymization for local drafting:

```bash
QUARTO_BENCHMARKS_ANONYMIZE=0 quarto preview docs/benchmarks-article
```

## GitHub Pages

The workflow `.github/workflows/quarto-pages.yml` renders this project and deploys it through
GitHub Pages from the `gh-pages-build` branch.
