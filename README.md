# local.gentoomanager

An Ansible collection for **managing Gentoo Linux systems** and running a
**cross-platform performance benchmark suite** across VMs and physical hosts.

## Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Inventory](#inventory)
- [Roles](#roles)
- [Playbooks](#playbooks)
- [Scripts](#scripts)
- [Development and testing](#development-and-testing)
- [Benchmark documentation](#benchmark-documentation)
- [Passwordless access setup](#passwordless-access-setup)
- [License](#license)

## Requirements

| Component | Minimum version |
|-----------|----------------|
| Ansible (controller) | 2.17 |
| Python (controller) | 3.10 |
| Python (managed nodes) | 3.8 |
| SSH (managed nodes) | key-based recommended |

> **RHEL 7 / RHEL 8 note:** These ship Python 3.6, which is below the minimum.
> Bootstrap a compatible interpreter before provisioning:
> - RHEL 7: `rh-python38` from Software Collections (`rhel-server-rhscl-7-rpms`)
> - RHEL 8: `python38` from AppStream (`dnf install python38`)
>
> Configure the correct path in `host_vars/<host>/main.yml`:
> ```yaml
> ansible_python_interpreter: /opt/rh/rh-python38/root/usr/bin/python3.8  # RHEL 7
> ansible_python_interpreter: /usr/bin/python3.8                           # RHEL 8
> ```

## Setup

```bash
# 1. Clone the repository
git clone <repo-url> && cd local.gentoomanager

# 2. Install collection dependencies
ansible-galaxy collection install -r requirements.yml

# 3. Configure your hypervisors and bare-metal hosts
cp hypervisors.txt.example hypervisors.txt   # then add your hypervisor hostnames
cp baremetal.txt.example baremetal.txt       # then add bare-metal hostnames (optional)

# 4. Verify connectivity
ansible all -m ping
```

Dependencies (`requirements.yml`):
- `community.general` — Portage module, make module for FreeBSD ports

## Inventory

The inventory is generated dynamically by `inventory_generator.py`.
It reads host configuration files and produces groups including:

| Group | Members |
|-------|---------|
| `gentoo` | All Gentoo Linux VMs |
| `fedora`, `rhel`, `ubuntu`, `debian`, … | Per-distro groups |
| `hypervisor_hv1`, `hypervisor_hv2` | VMs on each KVM hypervisor |
| `baremetal` | Physical machines (hostnames in `baremetal.txt`) |
| `win`, `win10`, `win11` | Windows VMs |

```bash
# List all hosts
ansible-inventory --list --yaml

# Show a host's variables
ansible-inventory --host <hostname>
```

## Roles

### `provision_benchmarks`

Installs all software required for the benchmark suite on target VMs.

Supported OS families:

| OS Family | Package manager | Extra repos |
|-----------|----------------|-------------|
| Gentoo | emerge | — |
| Red Hat (Fedora, RHEL, CentOS, OL) | dnf / yum | EPEL, RPM Fusion |
| Debian (Ubuntu, Mint, elementary) | apt | — |
| Arch Linux (Arch, Manjaro, CachyOS) | pacman | — |
| SUSE (openSUSE) | zypper | — |
| FreeBSD | ports (`make BATCH=yes`) | — |
| Void Linux | xbps-install | — |
| NixOS | nix-env | — |
| Solus | eopkg | — |

If a package manager is unavailable for the configured Python interpreter
(e.g. RHEL 7/8 with SCL Python), the role falls back to invoking `dnf`/`yum`
as shell commands so no Python bindings are needed.

Hyperfine is installed via the native package manager where possible; if
unavailable, a pre-built binary is downloaded from the GitHub release.

### `run_benchmarks`

Runs the benchmark suite on each target host using hyperfine.
See [docs/benchmarks.md](docs/benchmarks.md) for full documentation.

### `collect_use_flags`

Collects Gentoo `package.use` and `make.conf` settings from each host and
writes them into `host_vars/<host>/use_flags.yml` and
`group_vars/all/make_conf.yml` (settings common to all machines).

### `apply_portage_config`

Applies collected USE flags and make.conf settings back to target hosts.

## Playbooks

| Playbook | Description |
|----------|-------------|
| `playbooks/provision_benchmarks.yml` | Install benchmark tools on all VMs |
| `playbooks/run_benchmarks.yml` | Run the full benchmark suite |
| `playbooks/collect_use_flags.yml` | Collect Gentoo USE flags / make.conf |
| `playbooks/apply_portage_config.yml` | Apply portage configuration |

### Provisioning strategy

Play 1 gathers facts from all hosts **in parallel** and creates per-OS-family
dynamic groups (`provision_os_gentoo`, `provision_os_redhat`, …).  Subsequent
plays provision each OS family in its own parallel play.

**Gentoo is the exception**: because packages are compiled from source and share
hypervisor CPU, Gentoo hosts are provisioned `serial: 1` to avoid build-time
noise bleeding into benchmark results.

```bash
# Provision all hosts
ansible-playbook playbooks/provision_benchmarks.yml

# Provision only one hypervisor's VMs
ansible-playbook playbooks/provision_benchmarks.yml --limit hypervisor_hv1

# Provision with sudo password prompt
ansible-playbook playbooks/provision_benchmarks.yml --ask-become-pass
```

## Scripts

### `scripts/run_benchmarks.sh`

A convenience wrapper around `ansible-playbook playbooks/run_benchmarks.yml`
with options for host selection, category filtering, and tuning.

```
Usage: run_benchmarks.sh [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Run on specific host(s) by name
  --hypervisor HV[,HV...]     Run on VMs belonging to hypervisor(s)
  --group GROUP[,GROUP...]    Run on an inventory group (e.g. gentoo, baremetal)
  --limit PATTERN             Raw ansible --limit expression

Benchmark control:
  --category CAT[,CAT...]     Run only these categories (comma-separated)
  --runs N                    Repetitions per benchmark (default: 5)
  --warmup N                  Warmup runs (default: 3)
  --cpu-affinity RANGE        Pin to CPU range (e.g. 0-3)
  --compress-size MB          Compression test data size in MB (default: 64)
  --ffmpeg-duration SEC       FFmpeg test clip duration (default: 10)

Flags:
  --include-windows           Also run benchmarks on Windows VMs
  --no-ram-scale              Skip temporary RAM scaling
  --no-report                 Skip report generation
  --verbose, -v               Verbose Ansible output (repeat for -vvv)
  --dry-run, -C               Check mode (no changes)
  --ask-become-pass, -K       Prompt for sudo password
```

```bash
# Run all benchmarks on all hosts
./scripts/run_benchmarks.sh

# Single host, verbose
./scripts/run_benchmarks.sh --host gentoo-vm1 --verbose

# Only compression and crypto on hypervisor hv1
./scripts/run_benchmarks.sh --hypervisor hv1 --category compression,crypto

# All hosts, 10 runs, no report
./scripts/run_benchmarks.sh --runs 10 --no-report
```

### `scripts/generate_benchmark_report.py`

Generates Markdown and HTML benchmark reports from collected JSON results.

```bash
# Regenerate reports from existing results
python3 scripts/generate_benchmark_report.py benchmarks/

# Anonymize hostnames for public sharing
python3 scripts/generate_benchmark_report.py benchmarks/ --anonymize
```

### `scripts/collapse_use_flags.py`

Post-processes collected USE flags and splits them into per-host and
common (all-hosts) entries.

## Development and testing

### Quick start

```bash
# With uv (recommended — fast, reproducible)
uv sync --all-extras   # create .venv and install all dev deps from uv.lock
make test              # run the unit test suite

# Without uv (standard pip fallback)
python3 -m venv .venv
source .venv/bin/activate
pip install -r test-requirements.txt
pytest tests/unit/
```

### Makefile targets

| Target | Description |
|--------|-------------|
| `make setup` | Create `.venv` and install all dev dependencies |
| `make test` | Run the unit test suite |
| `make lint` | Run `ruff` linter and `ansible-lint` |
| `make fmt` | Auto-format Python sources with `ruff format` |
| `make shellcheck` | Lint `.sh` files and YAML `shell:` blocks with shellcheck |
| `make clean` | Remove the `.venv` directory |

`uv` is used automatically when it is on `PATH`; otherwise the targets
fall back to `python3 -m venv` + `pip`.  Install `uv` from
<https://docs.astral.sh/uv/getting-started/installation/>.

See **[docs/development.md](docs/development.md)** for the full
development guide, including dependency management, integration tests,
CI details, and project layout.

## Benchmark documentation

See **[docs/benchmarks.md](docs/benchmarks.md)** for the full benchmark
suite user guide including:
- Architecture overview
- All benchmark categories and what they measure
- Configuration reference
- Troubleshooting guide

## Passwordless access setup

See **[docs/setup-access.md](docs/setup-access.md)** for step-by-step
instructions on:
- Generating and distributing SSH key pairs
- Configuring passwordless `sudo` (all Linux distros)
- Configuring passwordless `doas` (Gentoo, FreeBSD, OpenBSD)
- Setting the relevant Ansible connection and become variables
- Security notes and verification commands

## License

GNU General Public License v3.0 or later.
See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) for the full text.
