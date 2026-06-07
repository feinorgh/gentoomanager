# Quarto Benchmark Article

This directory contains a Quarto project for long-form benchmark analysis.

## Local preview

```bash
pip install jupyter pandas numpy plotly
quarto preview docs/benchmarks-article
```

## Data source

The article reads benchmark JSON from:

`benchmarks/results/<host>/*.json`

through:

`scripts/benchmarks_article_data.py`

## GitHub Pages

The workflow `.github/workflows/quarto-pages.yml` renders this project and deploys it through
GitHub Pages (GitHub Actions source).
