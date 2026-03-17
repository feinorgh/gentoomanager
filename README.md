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
- [Preparation guide](#preparation-guide)
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
- `chocolatey.chocolatey` — Windows benchmark provisioning via Chocolatey
- `ansible.windows` — Windows connectivity and management modules

> **Full preparation guide:** [docs/preparation.md](docs/preparation.md) covers every
> one-time setup step in detail — SSH key setup, passwordless privilege escalation,
> RHEL Python bootstrap, Windows connectivity, and inventory configuration.

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

**Playbook variables** (pass with `-e`):

| Variable | Default | Description |
|----------|---------|-------------|
| `target_hosts` | `all` | Inventory pattern to provision |
| `provision_include_windows` | `false` | Also provision Windows hosts |
| `provision_manage_power` | `false` | Boot shut-off VMs; shut them down after |
| `provision_boot_timeout_sec` | `120` | Seconds to wait for a VM to boot |
| `provision_serial` | unset | Provision N hosts at a time (default: parallel per OS family) |

See [docs/benchmarks.md](docs/benchmarks.md#provisioning-hosts) for the full
`provision_benchmarks` role variable reference.

### `playbooks/run_benchmarks.yml`

```bash
# Run all benchmarks
ansible-playbook playbooks/run_benchmarks.yml

# Run only compression and crypto categories
ansible-playbook playbooks/run_benchmarks.yml \
  -e '{"run_benchmarks_categories": ["compression", "crypto"]}'

# Limit to a specific host
ansible-playbook playbooks/run_benchmarks.yml --limit gentoo-vm1
```

See [docs/benchmarks.md](docs/benchmarks.md#running-benchmarks) for the complete
options and [docs/benchmarks.md](docs/benchmarks.md#configuration-reference) for
the full variable reference.

### `playbooks/collect_use_flags.yml`

Collects Gentoo `package.use` and `make.conf` settings from Gentoo hosts and
writes them into `host_vars/<host>/use_flags.yml` (host-specific flags) and
`group_vars/all/use_flags.yml` (settings common to all machines).

```bash
# Collect from all Gentoo hosts
ansible-playbook playbooks/collect_use_flags.yml -i inventory_generator.py

# Collect from a subset
ansible-playbook playbooks/collect_use_flags.yml --limit gentoo-vm1

# Dry-run — show what would be written without touching the filesystem
ansible-playbook playbooks/collect_use_flags.yml --check
```

**Playbook variables** (pass with `-e`):

| Variable | Default | Description |
|----------|---------|-------------|
| `target_hosts` | `gentoo` | Inventory pattern to collect from |

**Role variables** (set in inventory or with `-e`):

| Variable | Default | Description |
|----------|---------|-------------|
| `collect_use_flags_make_conf` | `/etc/portage/make.conf` | Path to make.conf on the remote host |
| `collect_use_flags_package_use_dir` | `/etc/portage/package.use` | Directory with per-package USE flag files |
| `collect_use_flags_portage_repo_dir` | `/var/db/repos/gentoo` | Gentoo repository root (for USE flag descriptions) |
| `collect_use_flags_facts_dir` | `~/.ansible/use_flags_facts` | Controller-local staging directory |
| `collect_use_flags_output_dir` | (collection root) | Project root where `group_vars/` and `host_vars/` will be written |

### `playbooks/apply_portage_config.yml`

Applies previously-collected Portage configuration to Gentoo hosts, writing
`/etc/portage/make.conf` and `/etc/portage/package.use/` files.

```bash
# Preview changes before applying
ansible-playbook playbooks/apply_portage_config.yml --check --diff

# Apply to all Gentoo hosts
ansible-playbook playbooks/apply_portage_config.yml

# Apply to a single host
ansible-playbook playbooks/apply_portage_config.yml --limit gentoo-vm1
```

**Playbook variables** (pass with `-e`):

| Variable | Default | Description |
|----------|---------|-------------|
| `target_hosts` | `gentoo` | Inventory pattern to apply configuration to |

**Role variables** (set in inventory or with `-e`):

| Variable | Default | Description |
|----------|---------|-------------|
| `apply_portage_config_make_conf` | `/etc/portage/make.conf` | Path to make.conf on the remote host |
| `apply_portage_config_package_use_dir` | `/etc/portage/package.use` | Directory for per-package USE flag files |
| `apply_portage_config_group_vars_file` | `group_vars/all/use_flags.yml` | Controller file with shared USE flags |
| `apply_portage_config_host_vars_file` | `host_vars/<host>/use_flags.yml` | Controller file with host-specific USE flags |

## Scripts

### `scripts/provision_benchmarks.sh`

A convenience wrapper around `ansible-playbook playbooks/provision_benchmarks.yml`
with options for host selection and provisioning control.

```
Usage: provision_benchmarks.sh [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Provision specific host(s) by name
  --hypervisor HV[,HV...]     Provision VMs belonging to hypervisor(s)
  --group GROUP[,GROUP...]    Provision an inventory group (e.g. gentoo, ubuntu)
  --limit PATTERN             Raw ansible --limit expression

Flags:
  --manage-power              Boot VMs that are off; shut them down afterwards
  --boot-timeout SEC          Seconds to wait for a VM to boot (default: 120)
  --serial [N]                Provision N hosts at a time (default: 1 when given)
  --include-windows           Also provision Windows hosts via Chocolatey
  --verbose, -v               Verbose Ansible output (repeat for -vvv)
  --dry-run, -C               Check mode (no changes applied)
  --ask-become-pass, -K       Prompt for sudo/become password
```

```bash
# Provision all hosts
./scripts/provision_benchmarks.sh

# Provision a single host
./scripts/provision_benchmarks.sh --host gentoo-vm1

# Provision all VMs on one hypervisor, boot/shutdown as needed
./scripts/provision_benchmarks.sh --hypervisor hv1 --manage-power

# Provision only Gentoo hosts with sudo prompt
./scripts/provision_benchmarks.sh --group gentoo --ask-become-pass

# Provision all hosts including Windows
./scripts/provision_benchmarks.sh --include-windows

# Dry run — show what would happen
./scripts/provision_benchmarks.sh --dry-run --verbose
```

### `scripts/run_benchmarks.sh`

A convenience wrapper around `ansible-playbook playbooks/run_benchmarks.yml`
with options for host selection, category filtering, and tuning.

```
Usage: run_benchmarks.sh [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Run on specific host(s) by name
  --hypervisor HV[,HV...]     Run on all VMs belonging to hypervisor(s)
  --group GROUP[,GROUP...]    Run on an inventory group (e.g. gentoo, baremetal)
  --limit PATTERN             Raw ansible --limit expression

Benchmark control:
  --category CAT[,CAT...]     Run only these categories (comma-separated)
  --runs N                    Repetitions per benchmark (default: 5)
  --warmup N                  Warmup runs (default: 3)
  --cpu-affinity RANGE        Pin to CPU range (e.g. 0-3)
  --compress-size MB          Compression test data size in MB (default: 64)
  --ffmpeg-duration SEC       FFmpeg test clip duration (default: 10)
  --extended-codecs           Include extended FFmpeg codecs (slow/legacy)

Flags:
  --include-windows           Also run benchmarks on Windows VMs
  --no-ram-scale              Skip temporary RAM scaling
  --skip-complete             Skip hosts that already have a full result set
  --skip-existing             Skip individual categories whose result file exists
  --manage-power              Boot VMs that are off; shut them down afterwards
  --no-report                 Skip report generation after benchmarks
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

```
Usage: generate_benchmark_report.py [OPTIONS] benchmarks_dir

Arguments:
  benchmarks_dir        Directory containing results/<host>/*.json

Options:
  --anonymize           Replace hostnames with Greek mythology names
  --weights FILE        YAML file with category scoring weights
                        (default: scripts/scoring_weights.yml if present)
```

```bash
# Regenerate reports from existing results
python3 scripts/generate_benchmark_report.py benchmarks/

# Anonymize hostnames for public sharing
python3 scripts/generate_benchmark_report.py benchmarks/ --anonymize

# Use custom scoring weights
python3 scripts/generate_benchmark_report.py benchmarks/ --weights my_weights.yml
```

### `scripts/benchmark_dashboard.py`

Serves an interactive Plotly Dash web dashboard for exploring and comparing
benchmark results.  Requires `pip install dash pandas`.

```
Usage: benchmark_dashboard.py [OPTIONS] benchmarks_dir

Arguments:
  benchmarks_dir        Directory containing results/<host>/*.json

Options:
  --port PORT           Port to listen on (default: 8050)
  --host ADDR           Interface address to bind (default: 127.0.0.1)
                        Use 0.0.0.0 to listen on all interfaces
  --anonymize           Replace hostnames with Greek mythology names
```

```bash
# Start the dashboard locally
pip install dash pandas
python3 scripts/benchmark_dashboard.py benchmarks/

# Listen on all interfaces for remote access
python3 scripts/benchmark_dashboard.py benchmarks/ --host 0.0.0.0 --port 9090

# Open http://localhost:8050 in a browser; Ctrl+C to stop
```

### `scripts/collapse_use_flags.py`

Post-processes collected USE flags and splits them into per-host and
common (all-hosts) entries.  Called automatically by
`playbooks/collect_use_flags.yml`; can also be run standalone.

```
Usage: collapse_use_flags.py --facts-dir DIR --output-dir DIR [OPTIONS]

Required:
  --facts-dir DIR       Directory containing per-host JSON fact files
  --output-dir DIR      Project root where group_vars/ and host_vars/ are written

Options:
  --dry-run             Print what would be written; do not touch the filesystem
  --update              Merge with existing YAML files instead of overwriting
```

```bash
python3 scripts/collapse_use_flags.py \
  --facts-dir ~/.ansible/use_flags_facts \
  --output-dir .
```

### `scripts/download_benchmark_fixtures.py`

Downloads standard benchmark corpora (Silesia, Canterbury, Big Buck Bunny,
Kodak, SQLite amalgamation) to the controller.  Called automatically at the
start of each benchmark run; can also be run standalone.

```
Usage: download_benchmark_fixtures.py [OPTIONS] fixtures_dir

Arguments:
  fixtures_dir          Output directory (e.g. benchmarks/fixtures/)

Options:
  --skip-video          Skip the ~330 MiB Big Buck Bunny download
                        (FFmpeg will use a synthetic fallback)
  --force               Re-download all files even if they already exist
```

```bash
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --skip-video
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --force
```

### `scripts/generate_benchmark_images.py`

Generates deterministic test images for ImageMagick benchmarks.  Creates
a 4096×4096 PNG, a JPEG Q90 derivative, and a WebP derivative from a fixed
random seed (42) so every host and run gets identical input.  Called
automatically at benchmark time; can also be run standalone.  Requires
`pip install numpy Pillow`.

```
Usage: generate_benchmark_images.py [OPTIONS] fixtures_dir

Arguments:
  fixtures_dir          Output directory (e.g. benchmarks/fixtures/)

Options:
  --force               Regenerate images even if they already exist
```

```bash
python3 scripts/generate_benchmark_images.py benchmarks/fixtures/
python3 scripts/generate_benchmark_images.py benchmarks/fixtures/ --force
```

### `scripts/generate_multifile_bench.py`

Generates a multi-file C project used for compiler speed tests.  Creates a
directory with a Makefile and N independent C source modules (default 30).
Called automatically at benchmark time; can also be run standalone.

```
Usage: generate_multifile_bench.py [OPTIONS] output_dir

Arguments:
  output_dir            Directory to write the project into

Options:
  --modules N           Number of C modules to generate (default: 30)
```

```bash
python3 scripts/generate_multifile_bench.py /tmp/multifile_project
python3 scripts/generate_multifile_bench.py /tmp/multifile_project --modules 50
```

### `scripts/shellcheck_yaml_blocks.py`

Extracts and shellcheck-lints every `shell:` / `ansible.builtin.shell:` block
from Ansible YAML task files.  Used by CI; can also be run locally via
`make shellcheck`.

```
Usage: shellcheck_yaml_blocks.py [OPTIONS] [paths ...]

Arguments:
  paths                 YAML files or directories to scan
                        (default: roles/ and playbooks/)

Options:
  --shell SHELL         Shell dialect passed to shellcheck (default: bash)
  --no-color            Disable colour in shellcheck output
```

```bash
# Check all roles and playbooks (default)
python3 scripts/shellcheck_yaml_blocks.py

# Check a specific role
python3 scripts/shellcheck_yaml_blocks.py roles/run_benchmarks/
```

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

## Preparation guide

See **[docs/preparation.md](docs/preparation.md)** for a consolidated,
step-by-step guide covering every one-time setup task:
- Requirements and installation
- Inventory configuration (hypervisors, bare-metal, group/host vars)
- SSH key generation and distribution
- Configuring passwordless `sudo` (all Linux distros)
- Configuring passwordless `doas` (Gentoo, FreeBSD, OpenBSD)
- RHEL 7 / RHEL 8 Python bootstrap
- Windows host connectivity setup (OpenSSH and WinRM)
- Verification commands

For SSH-specific details see also **[docs/setup-access.md](docs/setup-access.md)**.

## License

GNU General Public License v3.0 or later.
See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) for the full text.
