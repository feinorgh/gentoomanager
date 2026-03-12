# Development Guide

This guide covers how to set up a local development environment,
run the test suite, and use the project tooling.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setting Up the Environment](#setting-up-the-environment)
  - [With uv (recommended)](#with-uv-recommended)
  - [With pip (fallback)](#with-pip-fallback)
- [Makefile Reference](#makefile-reference)
- [Running Tests](#running-tests)
  - [Unit Tests](#unit-tests)
  - [Integration Tests](#integration-tests)
  - [Sanity Tests](#sanity-tests)
- [Linting and Formatting](#linting-and-formatting)
- [Dependency Management](#dependency-management)
  - [Adding a New Dependency](#adding-a-new-dependency)
  - [Updating the Lock File](#updating-the-lock-file)
- [CI / GitHub Actions](#ci--github-actions)
- [Project Layout](#project-layout)

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.11 | Matches `requires-python` in `pyproject.toml` |
| [uv](https://docs.astral.sh/uv/) | any recent | Optional but strongly recommended |
| Ansible Core | 2.15 | Installed as a dev dependency |
| Git | any | For cloning and committing |

Install `uv` using whichever method suits your environment:

```bash
# One-line installer (installs to ~/.local/bin, no root required)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Distribution packages (no pip or venv needed)
emerge dev-python/uv            # Gentoo
pacman -S uv                    # Arch Linux
apt install uv                  # Debian 13+ / Ubuntu 25.04+
dnf install uv                  # Fedora 40+
pkg install uv                  # FreeBSD ports
brew install uv                 # macOS (Homebrew)

# PyPI — install into an existing virtual environment
pip install uv

# pipx — install as an isolated tool (no active venv needed)
pipx install uv
```

Official installation docs: <https://docs.astral.sh/uv/getting-started/installation/>

---

## Setting Up the Environment

### With uv (recommended)

`uv` creates an isolated `.venv` directory, resolves all dependencies
against the committed `uv.lock`, and activates the environment
automatically when you run `uv run <command>`.

```bash
# Clone the repository
git clone <repo-url>
cd local.gentoomanager

# Create .venv and install all dev/test dependencies from uv.lock
uv sync --all-extras

# Verify
uv run pytest --version
uv run ansible --version
```

The `.venv` directory is created in the project root. Re-running
`uv sync` is a no-op when the lock file hasn't changed, so it's
safe to run before any `make` target.

### With pip (fallback)

If `uv` is not available, use the standard `venv` + `pip` workflow:

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -r test-requirements.txt
```

All `make` targets detect whether `uv` is on `PATH` and switch
automatically — no manual configuration is required.

---

## Makefile Reference

Run `make help` to list all targets:

```
  setup   — create virtual environment and install all dev dependencies
  test    — run the unit test suite
  lint    — run ruff linter and ansible-lint
  fmt     — auto-format Python sources with ruff format
  clean   — remove the virtual environment
  help    — list available targets
```

| Target | uv command | pip fallback |
|--------|-----------|--------------|
| `make setup` | `uv sync --all-extras` | `python3 -m venv .venv && pip install -r test-requirements.txt` |
| `make test` | `uv run pytest tests/unit/` | `.venv/bin/pytest tests/unit/` |
| `make lint` | `uv run ruff check …` + `uv run ansible-lint` | `.venv/bin/ruff check …` + `.venv/bin/ansible-lint` |
| `make fmt` | `uv run ruff format …` | `.venv/bin/ruff format …` |
| `make clean` | `rm -rf .venv` | same |

---

## Running Tests

### Unit Tests

Unit tests live in `tests/unit/` and cover the Python scripts in
`scripts/`.  They run entirely offline with no Ansible inventory or
remote hosts required.

```bash
# Via make (auto-selects uv or pip)
make test

# Direct uv invocation
uv run pytest tests/unit/

# Direct invocation inside an activated venv
pytest tests/unit/

# Verbose with coverage of a single file
uv run pytest tests/unit/test_benchmark_report.py -v
```

The `pyproject.toml` `[tool.pytest.ini_options]` section sets default
flags (`-vvv -n 2 --log-level WARNING`).  The `-n 2` flag enables
parallel execution via `pytest-xdist`.

### Integration Tests

Integration tests use [Molecule](https://ansible.readthedocs.io/projects/molecule/)
with the **delegated** driver (no Docker or VMs required) and target
the Ansible modules in `plugins/modules/`.

```bash
# List available scenarios
ls extensions/molecule/

# Run a specific scenario
uv run molecule test -s integration_probe_command_output
```

Each scenario in `extensions/molecule/` maps to a target in
`tests/integration/targets/`.

### Sanity Tests

Ansible sanity tests check documentation, argument specs, and Python
compatibility across the collection:

```bash
# Run via ansible-test (inside a collection-installed path)
ansible-test sanity --python 3.11
```

Sanity tests are also run automatically in CI
(see [CI / GitHub Actions](#ci--github-actions)).

---

## Linting and Formatting

```bash
# Check for linting errors
make lint

# Auto-fix formatting
make fmt

# Run ruff manually (check only)
uv run ruff check scripts/ tests/

# Run ansible-lint
uv run ansible-lint
```

Ruff configuration is in `pyproject.toml` under `[tool.ruff]`.
Notable settings:

- Line length: 100
- Target version: Python 3.11
- Enabled rule sets: `E` (pycodestyle), `W`, `F` (pyflakes), `I` (isort),
  `B` (bugbear), `UP` (pyupgrade)
- `plugins/**/*.py` and `tests/**/*.py` are exempt from `E402`
  (module-level import position) because Ansible plugins and test helpers
  require `sys.path` manipulation before imports.

---

## Dependency Management

Dependencies are declared in two places:

| File | Purpose |
|------|---------|
| `pyproject.toml` — `[tool.uv].dev-dependencies` | Authoritative list for `uv sync` |
| `test-requirements.txt` | Fallback for users without `uv` |
| `uv.lock` | Pinned transitive dependency tree (committed) |

Both lists must be kept in sync when adding or removing packages.

### Adding a New Dependency

```bash
# Add to uv dev-dependencies and regenerate the lock file
uv add --dev <package>

# Then manually add the same package to test-requirements.txt
# (no version pin needed there — just the package name)
echo "<package>" >> test-requirements.txt
git add pyproject.toml uv.lock test-requirements.txt
```

### Updating the Lock File

```bash
# Update all packages to latest compatible versions
uv lock --upgrade

# Update a single package
uv lock --upgrade-package <package>

# Re-sync the environment after updating
uv sync --all-extras
```

Commit the updated `uv.lock` so that all contributors get the same
resolved versions.

---

## CI / GitHub Actions

### Tests (`tests.yml`)

Runs on every pull request and on `workflow_dispatch`:

| Job | Reusable workflow | What it does |
|-----|------------------|-------------|
| `changelog` | `ansible-content-actions/changelog.yaml` | Verifies a changelog fragment exists (PR only) |
| `build-import` | `ansible-content-actions/build_import.yaml` | Builds the collection tarball and validates it with the Galaxy importer |
| `ansible-lint` | `ansible-content-actions/ansible_lint.yaml` | Runs `ansible-lint` on all playbooks and roles |
| `sanity` | `ansible-content-actions/sanity.yaml` | Runs `ansible-test sanity` across a Python/Ansible version matrix |
| `unit-galaxy` | `ansible-content-actions/unit.yaml` | Installs collection from Galaxy and runs pytest unit tests |
| `unit-source` | `ansible-network/github_actions/unit_source.yml` | Runs pytest unit tests directly from source |
| `integration` | `ansible-content-actions/integration.yaml` | Runs Molecule integration tests across a Python/Ansible version matrix |
| `shellcheck` | *(inline)* | Lints standalone `.sh` files and inline YAML `shell:` blocks (see below) |
| `all_green` | *(inline)* | Aggregates all job results; branch protection can require this single job |

All reusable workflows are sourced from
`ansible/ansible-content-actions@main` and
`ansible-network/github_actions@main`.

#### shellcheck job

The `shellcheck` job has two steps:

1. **`ludeeus/action-shellcheck`** — scans all `*.sh` files under `scripts/`
   using shellcheck at `warning` severity or above.

2. **`scripts/shellcheck_yaml_blocks.py`** — a custom Python script that
   extracts every `shell:` and `ansible.builtin.shell:` block from all YAML
   task files under `roles/` and `playbooks/`, strips Jinja2 expressions,
   and runs shellcheck on each block as a temporary `#!/bin/bash` script.
   SC2154 is suppressed globally (variables assigned by Ansible are
   unknown to shellcheck).

   The script also handles block scalars that start `{` (Bash group commands),
   inline Jinja2 variable placeholders (`{{ var }}`), and `{% if %}` /
   `{% for %}` control blocks.  Exit code 1 if any block produces findings.

Run locally:

```bash
make shellcheck
```

### Release (`release.yml`)

Triggered when a GitHub Release is published.  The workflow builds the
collection tarball with `ansible-galaxy collection build` and uploads it
as an asset on the same release using the built-in `GITHUB_TOKEN` — no
external secrets or accounts required.

| Job | What it does |
|-----|-------------|
| `build-and-attach` | Builds `local-gentoomanager-<version>.tar.gz` and attaches it to the GitHub Release |

**How to make a release:**

1. Update `version` in `galaxy.yml`.
2. Add a changelog fragment under `changelogs/fragments/`.
3. Commit and push to `master`.
4. Go to *GitHub → Releases → Draft a new release*, set a tag (e.g. `v1.1.0`),
   fill in the title/notes, and click **Publish release**.
5. The workflow attaches the tarball automatically within ~1 minute.

Users can then install directly from the GitHub Release asset:

```bash
ansible-galaxy collection install \
  https://github.com/feinorgh/gentoomanager/releases/download/v1.1.0/local-gentoomanager-1.1.0.tar.gz
```

No `ANSIBLE_GALAXY_API_KEY` or `AH_TOKEN` secrets are needed.

### Reproducing CI failures locally

```bash
# Unit tests (same as unit-source job)
make test

# Lint (same as ansible-lint job)
make lint

# shellcheck (same as shellcheck job)
make shellcheck

# Integration tests (same as integration job — requires Molecule)
uv run molecule test -s integration_probe_command_output
```

---

## Project Layout

```
local.gentoomanager/
├── Makefile                    ← dev task runner (uv-first, pip fallback)
├── pyproject.toml              ← project metadata, ruff/pytest config, uv deps
├── test-requirements.txt       ← pip fallback dependency list
├── uv.lock                     ← pinned transitive dependency tree
├── requirements.yml            ← Ansible collection runtime dependencies
├── plugins/
│   └── modules/                ← Ansible modules (probe_command_output, …)
├── roles/
│   ├── provision_benchmarks/   ← install benchmark tools on remote hosts
│   └── run_benchmarks/         ← execute benchmarks, collect results
├── playbooks/                  ← top-level playbooks (site.yml, run_benchmarks.yml, …)
├── scripts/                    ← Python helper scripts (report, fixtures, …)
├── tests/
│   ├── unit/                   ← pytest unit tests (run offline, no inventory)
│   └── integration/targets/    ← Molecule integration test targets
├── extensions/molecule/        ← Molecule scenario definitions
└── docs/                       ← documentation
```
