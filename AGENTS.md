<!--# cspell: ignore SSOT CMDB antsibull -->
# AGENTS.md

Ensure that all practices and instructions described by
https://raw.githubusercontent.com/ansible/ansible-creator/refs/heads/main/docs/agents.md
are followed.

---

## Project Overview

`local.gentoomanager` is an Ansible collection for managing Gentoo Linux VMs
(and mixed fleets).  Key areas: USE flag / `make.conf` collection, a
cross-platform benchmark suite (`roles/run_benchmarks`), and a
`probe_command_output` custom module.

Important paths:

| Path | Purpose |
| ---- | ------- |
| `roles/` | Ansible roles (each has `tasks/`, `defaults/`, `meta/`) |
| `plugins/modules/` | Custom Ansible modules |
| `playbooks/` | Top-level playbooks |
| `scripts/` | Python/Bash helper scripts (report generator, dashboard, wrapper) |
| `tests/unit/` | pytest unit tests |
| `tests/integration/` | Molecule integration test targets |
| `extensions/molecule/` | Molecule scenarios |
| `changelogs/fragments/` | Antsibull changelog fragments |

---

## Build, Test, and Lint

Always run these before pushing.  All commands assume `uv` is available
(installed automatically if missing via `make setup`).

```bash
# Unit tests
uv run pytest tests/unit/

# Python linter + formatter check
uv run ruff check scripts/ tests/
uv run ruff format --check scripts/ tests/

# Ansible lint (roles, playbooks, tasks)
uv run ansible-lint

# ShellCheck — standalone .sh files AND inline YAML shell blocks
uv run python scripts/shellcheck_yaml_blocks.py
shellcheck scripts/*.sh

# Or run everything at once via make
make test lint shellcheck
```

Fix all reported issues before committing.  ShellCheck covers Jinja2-templated
`shell:` blocks (via `scripts/shellcheck_yaml_blocks.py`) — do not skip it.

---

## CI Verification

After every `git push`, **always** check that the GitHub Actions workflows pass
before considering a task complete.

```bash
# Watch the latest run
gh run list --branch main --limit 3
gh run watch <run-id>

# Retrieve logs for any failed jobs
gh run view <run-id> --log-failed
```

The gate job is named **all_green** — every other job must succeed before it
turns green.  Do not mark a task done until `all_green` passes.

---

## Commit Conventions

- Write clear, imperative-mood commit messages (`fix:`, `feat:`, `tests:`,
  `docs:`, `chore:` prefixes are encouraged but not enforced).
- Always append the Co-authored-by trailer:
  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  ```
- Keep commits focused — one logical change per commit.

---

## Changelog Fragments

For any user-visible change, add an
[antsibull-changelog](https://github.com/ansible-community/antsibull-changelog)
fragment under `changelogs/fragments/`.  File name: `<short-slug>.yml`.

```yaml
# changelogs/fragments/my-change.yml
minor_changes:
  - "roles/run_benchmarks: added bash performance benchmark category."
```

Valid section keys: `major_changes`, `minor_changes`, `bugfixes`,
`breaking_changes`, `deprecated_features`, `removed_features`,
`security_fixes`.  The CI changelog job (PR-only) validates fragments.

---

## Code Style

- Python: follow **ruff** defaults (line length 100, double quotes via the
  project's `pyproject.toml`).  No manual `# noqa` unless genuinely
  unavoidable — fix the root cause first.
- Do **not** use bare `_` as a throwaway variable name — `ansible-test
  sanity` runs pylint with `disallowed-name` enabled.  Use a descriptive
  name instead (e.g. `_ignored`, `_host_os`, `_unused`).
- Always pass `check=False` (or `check=True`) explicitly to
  `subprocess.run()` — pylint's `subprocess-run-check` rule requires it.
- Ansible tasks: use fully-qualified collection names (`ansible.builtin.*`).
  Add `# noqa: <rule>` with a comment explaining why only when ansible-lint
  cannot be satisfied correctly.
- Any `ansible.builtin.shell` task that uses bash features (`pipefail`,
  arrays `()`, `[[ ]]`, `(( ))`, `declare -A`, etc.) **must** include
  `executable: /bin/bash` — Ansible's default shell is `/bin/sh` (dash on
  Ubuntu/Debian) which does not support these constructs.  Silent failures
  (masked by `failed_when: false`) are a common symptom of this mistake.
- Shell scripts: POSIX-compatible where possible; bash-specific features only
  when needed.  All scripts must pass ShellCheck with no warnings.

---

## Off-limits / Safety

- Do **not** commit secrets, credentials, or real hostnames into any tracked
  file.
- Do **not** modify `inventory_generator.py` to hard-code hosts or credentials.
- `host_vars/` and `group_vars/` contain machine-specific data — treat changes
  there carefully and never commit real IP addresses or passwords.
- The benchmark shall be verified not to produce any permanent changes on the
  systems where they are run. Temporary files and fixtures shall be removed
  from the benchmarked hosts when the set of benchmarks is finished.
