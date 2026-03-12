# Makefile for local.gentoomanager
#
# Uses 'uv' for fast venv/dependency management when available,
# falls back to standard 'python -m venv' + 'pip' otherwise.
#
# Common targets:
#   make setup      — create venv and install all dev dependencies
#   make test       — run unit tests
#   make lint       — run ruff + ansible-lint
#   make clean      — remove the virtual environment
#   make help       — show this message

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PYTEST      := $(VENV)/bin/pytest
RUFF        := $(VENV)/bin/ruff
ANSIBLELINT := $(VENV)/bin/ansible-lint

# Detect uv; if absent fall back to pip
UV          := $(shell command -v uv 2>/dev/null)

.PHONY: setup test lint clean help

## setup: create virtual environment and install all dev dependencies
setup: $(PYTHON)

$(PYTHON):
ifdef UV
	uv sync --all-extras
else
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r test-requirements.txt
endif

## test: run the unit test suite
test: $(PYTHON)
ifdef UV
	uv run pytest tests/unit/
else
	$(PYTEST) tests/unit/
endif

## lint: run ruff linter and ansible-lint
lint: $(PYTHON)
ifdef UV
	uv run ruff check scripts/ tests/
	uv run ansible-lint
else
	$(RUFF) check scripts/ tests/
	$(ANSIBLELINT)
endif

## fmt: auto-format Python sources with ruff
fmt: $(PYTHON)
ifdef UV
	uv run ruff format scripts/ tests/
else
	$(RUFF) format scripts/ tests/
endif

## clean: remove the virtual environment
clean:
	rm -rf $(VENV)

## help: list available targets
help:
	@grep -E '^## ' Makefile | sed 's/^## /  /'
