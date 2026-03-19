# Benchmark Suite User Guide

The benchmark suite measures and compares performance across VMs and physical
hosts with different Linux distributions, compiler flags, and system
configurations.  It uses [hyperfine](https://github.com/sharkdp/hyperfine)
for statistical benchmarking and produces Markdown and interactive HTML
reports with charts.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Provisioning Hosts](#provisioning-hosts)
  - [Provisioning Wrapper Script](#provisioning-wrapper-script)
  - [Provisioning Options](#provisioning-options)
- [Running Benchmarks](#running-benchmarks)
  - [Wrapper Script](#wrapper-script)
  - [Selected Categories](#selected-categories)
  - [Limiting Hosts](#limiting-hosts)
  - [Tuning Parameters](#tuning-parameters)
- [Benchmark Categories](#benchmark-categories)
  - [Compression](#compression)
  - [Cryptography](#cryptography)
  - [Compiler](#compiler)
  - [Python](#python)
  - [Octave](#octave)
  - [Numeric](#numeric)
  - [SQLite](#sqlite)
  - [FFmpeg](#ffmpeg)
  - [ImageMagick](#imagemagick)
  - [Coreutils](#coreutils)
  - [Memory](#memory)
  - [Process](#process)
  - [Disk I/O](#disk-io)
  - [Linker](#linker)
  - [OpenCV](#opencv)
  - [GIMP](#gimp)
  - [Inkscape](#inkscape)
  - [Application Startup](#application-startup)
  - [Bash](#bash)
  - [Boot Time](#boot-time)
  - [Gentoo Build Times](#gentoo-build-times)
- [Reports](#reports)
  - [Markdown Report](#markdown-report)
  - [HTML Report](#html-report)
  - [Regenerating Reports](#regenerating-reports)
  - [Dashboard](#dashboard)
- [Benchmark Fixture Files](#benchmark-fixture-files)
  - [Fixture Corpus Details](#fixture-corpus-details)
  - [Fallback Behaviour](#fallback-behaviour)
- [RAM Management](#ram-management)
- [Windows Support](#windows-support)
- [Configuration Reference](#configuration-reference)
  - [run\_benchmarks Role](#run_benchmarks-role)
  - [provision\_benchmarks Role](#provision_benchmarks-role)
- [Troubleshooting](#troubleshooting)
- [Directory Layout](#directory-layout)

## Quick Start

```bash
# 0. Install Ansible collection dependencies
ansible-galaxy collection install -r requirements.yml

# 1. Install benchmark dependencies on all hosts
./scripts/run_benchmarks.sh --dry-run   # Check what would change
ansible-playbook playbooks/provision_benchmarks.yml

# 2. Run the full benchmark suite
./scripts/run_benchmarks.sh

# 3. View results
open benchmarks/report.html      # interactive HTML with charts
cat benchmarks/report.md         # Markdown tables
```

## Architecture Overview

```
Controller                          Hosts (provisioning: serial=1 per OS family by default)
──────────                          ─────────────────────────────────────────────────────
provision_benchmarks.yml ────────► Play 1: gather facts → dynamic OS groups
                                   Play 2: Gentoo  (serial=1, scale RAM via virsh)
                                   Play 3: RedHat  (serial=1)
                                   Play 4: Debian  (serial=1)
                                   …
                                   Play 7: FreeBSD (serial=1, scale RAM via virsh)

Controller                          Hosts (benchmarks: one at a time)
──────────                          ──────────────────────────────────
run_benchmarks.yml ──────────────► Scale RAM → run benchmarks → fetch JSON
       │
       │  benchmarks/results/<host>/   ◄── *.json (hyperfine output)
       │
       ▼
generate_benchmark_report.py ───► benchmarks/report.md
                                  benchmarks/report.html
```

**Provisioning** runs one host at a time per OS family by default (`serial: 1`).
Gentoo and FreeBSD provisioning plays additionally scale VM RAM to the maximum
via `virsh setmem --live` before compiling packages, then restore it in an
`always:` block so it is reset even on failure.

When `--serial` is passed to the wrapper script, each host is processed
end-to-end (boot → provision → shutdown) before the next host begins,
regardless of OS family.

**Benchmarks** run one host at a time.  Each VM's RAM is temporarily scaled
to its maximum configured value during the run and restored afterwards —
even if benchmarks fail.

## Prerequisites

> **First time?** See **[docs/preparation.md](preparation.md)** for a complete
> step-by-step guide covering Ansible installation, inventory configuration,
> SSH key setup, passwordless privilege escalation, and special-case host
> bootstrapping.

### Linux / Unix / macOS Hosts

- **Ansible** 2.17+ on the controller
- **Python 3.10+** on the controller
- **Python 3.8+** on managed nodes (see [RHEL 7/8 note](preparation.md#61-rhel-7--rhel-8--python-bootstrap))
- **SSH key-based access** to all target hosts (see [docs/setup-access.md](setup-access.md))
- **libvirt/virsh** on hypervisors (for RAM scaling; optional)
- **Collections:** `ansible-galaxy collection install -r requirements.yml`

### Windows Hosts

Windows hosts need remote management enabled before Ansible can reach them.
See **[docs/preparation.md — Windows Hosts](preparation.md#62-windows-hosts)**
for full setup instructions (OpenSSH and WinRM options).

Verify connectivity after setup:

```bash
ansible mswindows -m ansible.windows.win_ping
```

**Benchmark software is installed automatically** during the first run of the
benchmark suite.  The setup step installs the following via
[Chocolatey](https://chocolatey.org/):

| Package | Purpose |
|---------|---------|
| `hyperfine` | Benchmark harness (required) |
| `mingw` | gcc / g++ / ld compiler toolchain |
| `python` | Python benchmarks + helper scripts |
| `openssl` | Crypto benchmarks |
| `7zip` | Compression benchmarks |
| `git` | Optional: git-based coreutils sub-cases |
| `nodejs` | Optional: Node.js startup benchmark |

NumPy is also installed via `pip` for the numeric benchmark category.
The `chocolatey.chocolatey` Ansible collection is required and is included in
`requirements.yml`.

## Provisioning Hosts

Before running benchmarks for the first time, install all required software:

```bash
ansible-playbook playbooks/provision_benchmarks.yml
```

This installs compilers (GCC, Clang), language runtimes (Rust, Go, Python),
compression tools, FFmpeg, OpenSSL, and hyperfine.  It handles package
manager differences across OS families:

| OS Family | Package manager | Extra repos | Notes |
|-----------|----------------|-------------|-------|
| Gentoo | emerge | — | |
| Red Hat (Fedora, RHEL, CentOS, OL) | dnf / yum | EPEL, RPM Fusion | |
| Debian (Ubuntu, Mint, elementary) | apt | — | |
| Arch Linux (Arch, Manjaro, CachyOS) | pacman | — | |
| SUSE (openSUSE, SLES) | zypper | — | |
| FreeBSD | ports (`make BATCH=yes`) | — | All packages (including optional ones: GIMP, Inkscape, OpenCV, Botan, mold, Octave) are built from the ports tree to avoid mixing pkg and ports. |
| Void Linux | xbps-install | — | |
| NixOS | nix-env | — | |
| Solus | eopkg | — | |

If `hyperfine` is not available in the package manager, a pre-built binary
is downloaded from the [GitHub release](https://github.com/sharkdp/hyperfine/releases).

> **Note:** `ffmpeg` on RHEL 9/10 currently fails to install from RPM Fusion
> due to a packaging issue in the RPM Fusion repo itself.  All other packages
> install successfully.  FFmpeg benchmarks will be skipped automatically on
> those hosts.

### Provisioning Wrapper Script

`scripts/provision_benchmarks.sh` is the recommended way to provision hosts.
It wraps `ansible-playbook playbooks/provision_benchmarks.yml` with
convenience options for host selection and power management.

```
Usage: provision_benchmarks.sh [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Provision specific host(s) by name
  --hypervisor HV[,HV...]     Provision VMs belonging to hypervisor(s)
                              (e.g. hv1, hv2 — matches hypervisor_<name>)
  --group GROUP[,GROUP...]    Provision an inventory group (e.g. gentoo, ubuntu)
  --limit PATTERN             Raw ansible --limit expression

Flags:
  --manage-power              Boot VMs that are off before provisioning and
                              shut them down again afterwards.  Only VMs
                              started by this run are shut down.
  --boot-timeout SEC          Seconds to wait for a VM to become reachable
                              after boot (default: 120)
  --serial [N]                Process one complete host lifecycle (boot →
                              provision → shutdown) at a time.  With N,
                              process N hosts in parallel.  Without this flag
                              all eligible hosts in each OS family are
                              provisioned in parallel.
  --include-windows           Also provision Windows hosts via Chocolatey
  --verbose, -v               Pass -v to ansible-playbook (repeat for -vvv)
  --dry-run, -C               Pass --check to ansible-playbook (no changes)
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

# Provision all hosts including Windows, one at a time
./scripts/provision_benchmarks.sh --include-windows --serial

# Dry run — show what would happen without making changes
./scripts/provision_benchmarks.sh --dry-run --verbose
```

### Provisioning Options

Fine-grained control via Ansible variables (pass with `-e`):

```bash
# Provision only one hypervisor's VMs
ansible-playbook playbooks/provision_benchmarks.yml --limit hypervisor_hv1

# Skip FFmpeg (saves time on hosts where it is slow to install)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_ffmpeg=false

# Install OpenCV Python bindings (default: false, heavy)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_opencv=true

# Install GIMP for batch-mode image-processing benchmarks
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_gimp=true

# Install Inkscape 1.x for SVG rendering benchmarks
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_inkscape=true

# Install mold linker (default: true)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_mold=true

# Install GNU Octave for numerical benchmarks (default: true)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_octave=true

# Prompt for sudo password
ansible-playbook playbooks/provision_benchmarks.yml --ask-become-pass
```

## Running Benchmarks

### Wrapper Script

`scripts/run_benchmarks.sh` is the recommended way to run benchmarks.
It wraps `ansible-playbook playbooks/run_benchmarks.yml` with convenience
options for host selection, category filtering, and tuning.

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
  --cpu-affinity RANGE        Pin benchmarks to CPU range (e.g. 0-3)
  --compress-size MB          Test data size for compression (default: 64)
  --ffmpeg-duration SEC       Test clip duration for FFmpeg (default: 10)
  --extended-codecs           Include non-standard FFmpeg codecs (slow,
                              experimental, and legacy; adds vp8, libaom-av1,
                              librav1e, theora, xvid, mpeg2, mjpeg, ac3, eac3,
                              wavpack, alac — see FFmpeg section)

Flags:
  --include-windows           Also run benchmarks on Windows VMs
  --no-ram-scale              Skip temporary RAM scaling
  --skip-complete             Skip hosts that already have a full set of results
  --skip-existing             Skip individual categories whose result file already exists
  --manage-power              Boot VMs that are off; shut them down after benchmarking
                              (only VMs started by this run are shut down afterwards)
  --no-report                 Skip report generation after benchmarks
  --verbose, -v               Enable verbose Ansible output (repeat for -vvv)
  --dry-run, -C               Check mode — no changes applied
  --ask-become-pass, -K       Prompt for sudo/become password
```

```bash
# Run all benchmarks on all hosts
./scripts/run_benchmarks.sh

# Single host, verbose
./scripts/run_benchmarks.sh --host gentoo-vm1 -v

# Only compression and crypto on hypervisor hv1's VMs
./scripts/run_benchmarks.sh --hypervisor hv1 --category compression,crypto

# All baremetal hosts, 10 runs, no report generation
./scripts/run_benchmarks.sh --group baremetal --runs 10 --no-report

# Pin to first 4 CPUs for consistency
./scripts/run_benchmarks.sh --cpu-affinity 0-3
```

### Selected Categories

To run specific categories without the wrapper script:

```bash
ansible-playbook playbooks/run_benchmarks.yml \
  -e '{"run_benchmarks_categories": ["compression", "ffmpeg"]}'
```

Valid category names: `compression`, `crypto`, `compiler`, `python`,
`octave`, `numeric`, `sqlite`, `ffmpeg`, `imagemagick`, `coreutils`, `memory`,
`process`, `disk`, `linker`, `opencv`, `startup`, `gentoo_build_times`.

Pass an empty list `[]` (the default) to run all categories.

### Limiting Hosts

```bash
# Only VMs on one hypervisor
./scripts/run_benchmarks.sh --hypervisor hv1

# Single VM
./scripts/run_benchmarks.sh --host gentoo-vm1

# Inventory group
./scripts/run_benchmarks.sh --group gentoo

# Baremetal machines (hostnames read from baremetal.txt)
./scripts/run_benchmarks.sh --group baremetal

# Raw Ansible limit expression
./scripts/run_benchmarks.sh --limit 'gentoo-vm1,gentoo-vm2'
```

> **Note:** The controller node (localhost) is automatically detected
> and run with a local (`local`) Ansible connection instead of SSH.

### Tuning Parameters

```bash
# More iterations for higher statistical confidence
./scripts/run_benchmarks.sh --runs 10 --warmup 5

# Skip automatic RAM scaling
./scripts/run_benchmarks.sh --no-ram-scale

# Larger test data for compression benchmarks
./scripts/run_benchmarks.sh --compress-size 128

# Longer FFmpeg test clip
./scripts/run_benchmarks.sh --ffmpeg-duration 30

# FFmpeg with extended (slow/legacy) codecs
./scripts/run_benchmarks.sh --category ffmpeg --extended-codecs
```

### Skipping Already-Benchmarked Hosts

When resuming an interrupted run, pass `--skip-complete` to skip hosts that
already have a full set of result files in `benchmarks/results/<hostname>/`.
A host is considered complete if every active category's primary result JSON
file is present and non-empty on the controller.

```bash
# Only run benchmarks on hosts that don't yet have results
./scripts/run_benchmarks.sh --skip-complete

# Combine with category filter to skip hosts that already have those results
./scripts/run_benchmarks.sh --skip-complete \
  -e '{"run_benchmarks_categories": ["compression", "ffmpeg"]}'
```

Alternatively, pass the variable directly to `ansible-playbook`:

```bash
ansible-playbook playbooks/run_benchmarks.yml \
  -e run_benchmarks_skip_complete=true
```

### Resuming a Partial Run (per-category)

`--skip-existing` is more granular than `--skip-complete`: it resumes at the
individual category level rather than the host level.  Before each category
runs, the playbook checks whether the primary JSON result file already exists
and is non-empty on the controller.  If it does, that category is skipped for
that host.  This makes it safe to interrupt and restart a benchmark run without
re-running completed categories.

```bash
# Resume an interrupted run — skip categories that already have results
./scripts/run_benchmarks.sh --skip-existing

# Combine with --skip-complete to skip fully-done hosts entirely
./scripts/run_benchmarks.sh --skip-complete --skip-existing
```

### VM Power Management

When `--manage-power` is passed, the playbook will boot VMs that are currently
shut off and shut them down again once benchmarking is complete.  This makes it
possible to run the full benchmark suite without first manually starting every
VM.

**How it works:**

1. Before attempting SSH, the playbook queries the VM's power state on its
   hypervisor via `virsh domstate`.
2. If the domain is not running, `virsh start` is issued and the playbook waits
   up to `run_benchmarks_boot_timeout_sec` seconds (default: 180) for SSH to
   become available.
3. After benchmarks finish, work-dir cleanup and RAM restoration complete, the
   VM is gracefully shut down with `virsh shutdown`.
4. **Only VMs that were started by this run are ever shut down.**  VMs that were
   already running when the play started are left running.

```bash
# Boot off VMs, benchmark them, then shut them down again
./scripts/run_benchmarks.sh --manage-power

# Combine with --skip-existing to resume partial runs on powered-off hosts
./scripts/run_benchmarks.sh --manage-power --skip-existing

# Use a longer boot timeout (seconds) for slow-booting VMs
ansible-playbook playbooks/run_benchmarks.yml \
  -e run_benchmarks_manage_power=true \
  -e run_benchmarks_boot_timeout_sec=300
```

> **Requirements:** `hypervisor_host` must be set in each VM's inventory
> (populated automatically by `inventory_generator.py`) and the controller
> must be able to SSH to the hypervisor and run `virsh`.

## Benchmark Categories

### Compression

Tests compression and decompression speed on a real-world mixed-content corpus.

| Benchmark        | Tool  | Description                 |
|------------------|-------|-----------------------------|
| gzip-compress    | gzip  | Compress (default level)    |
| gzip-decompress  | gzip  | Decompress                  |
| bzip2-compress   | bzip2 | Compress (default level)    |
| bzip2-decompress | bzip2 | Decompress                  |
| xz-compress      | xz    | Compress (default level)    |
| xz-decompress    | xz    | Decompress                  |
| zstd-compress    | zstd  | Compress (default level)    |
| zstd-decompress  | zstd  | Decompress                  |
| lz4-compress     | lz4   | Compress (default level)    |
| lz4-decompress   | lz4   | Decompress                  |

**Test data:** [Silesia corpus](http://sun.aei.polsl.pl/~sdeor/corpus/) — a
211 MiB concatenation of 12 diverse real-world files (English text, compiled
binary, medical image, XML, database, etc.).  This is the standard corpus
used to publish zstd, lz4, and brotli reference benchmarks.  Downloaded once
to the controller by `scripts/download_benchmark_fixtures.py` and copied to
each host; if unavailable, falls back to a random binary file of
**64 MiB** (the default `--compress-size` value) — which only tests the
incompressible-data fast-path, not actual compression performance.  Any
previously generated fallback file smaller than 64 MiB is automatically
deleted and regenerated at the start of the next benchmark run.

The `xz-compress` benchmark passes `-T0` to enable multi-threaded compression,
exercising multi-core performance in addition to per-core IPC.

The compression category uses its own run/warmup defaults
(`run_benchmarks_compression_runs=3`, `run_benchmarks_compression_warmup=1`)
rather than the global values, since bzip2 and xz are deterministic
single-threaded operations with negligible run-to-run variance — three
measured runs is statistically sufficient and keeps this category under
~5 minutes on typical hardware.

The [Canterbury corpus](https://corpus.canterbury.ac.nz/) is also downloaded
to `benchmarks/fixtures/cantrbry/` for ad-hoc comparison with published
results, but is not used in the automated benchmark runs.

### Cryptography

Tests symmetric ciphers, digests, asymmetric key operations, HMAC, key
derivation, and GPG.  Highly sensitive to `-march=native` (enables AES-NI
and SHA-NI hardware instructions), LTO, and optimization level.

**Symmetric ciphers** (file-level, `openssl enc`):

| Benchmark   | Tool    | Notes                              |
|-------------|---------|-------------------------------------|
| aes-256-cbc | openssl | Hardware-accelerated via AES-NI    |
| aes-128-cbc | openssl | Smaller key variant                |
| aes-256-ctr | openssl | Parallelizable counter mode        |
| chacha20    | openssl | Pure software — compiler-sensitive |

**OpenSSL `speed` throughput** (includes AEAD modes):

| Benchmark               | Notes                            |
|-------------------------|----------------------------------|
| speed-aes-256-gcm       | TLS 1.3 default                  |
| speed-aes-256-cbc       | AES-256-CBC throughput           |
| speed-chacha20-poly1305 | Compiler-optimized code path     |
| speed-sha256            | SHA-256 throughput               |
| speed-sha512            | SHA-512 throughput               |

**Digests** (OpenSSL vs coreutils):
`openssl-sha256`, `openssl-sha512`, `openssl-sha3-256`, `openssl-sha1`,
`openssl-md5`, `openssl-blake2b512`, `sha256sum`, `sha512sum`, `md5sum`, `b2sum`

**Asymmetric / public key:**

Individual asymmetric operations complete in well under 1 ms, making it
impossible for hyperfine to measure them accurately in a single invocation.
Each command therefore wraps the `openssl` call in a shell loop of **1000
iterations** so wall-clock totals are directly comparable across algorithms.
Command names carry the suffix `-1000x` (e.g. `rsa-2048-sign-1000x`).

| Benchmark (sign + verify pair) | Algorithm / security level |
|---|---|
| `rsa-2048-sign-1000x` / `rsa-2048-verify-1000x` | RSA-2048, SHA-256 (acceptable to 2030, NIST SP 800-57) |
| `rsa-3072-sign-1000x` / `rsa-3072-verify-1000x` | RSA-3072, SHA-256 (NIST minimum for post-2030) |
| `rsa-4096-sign-1000x` / `rsa-4096-verify-1000x` | RSA-4096, SHA-256 (long-lived CA keys) |
| `ecdsa-p256-sign-1000x` / `ecdsa-p256-verify-1000x` | ECDSA P-256, 128-bit security |
| `ecdsa-p384-sign-1000x` / `ecdsa-p384-verify-1000x` | ECDSA P-384, 192-bit security (CNSA Suite 2.0 minimum) |
| `ecdsa-p521-sign-1000x` / `ecdsa-p521-verify-1000x` | ECDSA P-521, 260-bit security |
| `ed25519-sign-1000x` / `ed25519-verify-1000x` | Ed25519, 128-bit security, FIPS 186-5 |
| `ed448-sign-1000x` / `ed448-verify-1000x` | Ed448, 224-bit security |
| `ml-dsa-44-sign-1000x` / `ml-dsa-44-verify-1000x` | ML-DSA-44 (FIPS 204, 128-bit PQ security) — skipped if OpenSSL < 3.5 |
| `ml-dsa-65-sign-1000x` / `ml-dsa-65-verify-1000x` | ML-DSA-65 (FIPS 204, 192-bit PQ security) — skipped if OpenSSL < 3.5 |
| `ml-dsa-87-sign-1000x` / `ml-dsa-87-verify-1000x` | ML-DSA-87 (FIPS 204, 256-bit PQ security) — skipped if OpenSSL < 3.5 |
| `slh-dsa-sha2-128f-sign-1000x` / `slh-dsa-sha2-128f-verify-1000x` | SLH-DSA-SHA2-128f (FIPS 205, 128-bit PQ security) — skipped if OpenSSL < 3.5 |

The input file `signdata.bin` is **1 KiB** of random data.
Post-quantum algorithms (ML-DSA, SLH-DSA) are silently skipped on hosts
whose OpenSSL version does not support them.

**SSH asymmetric signing** (output file: `crypto_ssh_sign.json`):

The same 1000-iteration loop methodology is applied to SSH key types using
`ssh-keygen -Y sign`.  Results are directly comparable to the OpenSSL
asymmetric benchmarks above.

| Benchmark (sign + verify pair) | Algorithm |
|---|---|
| `ssh-ed25519-sign-1000x` / `ssh-ed25519-verify-1000x` | Ed25519 |
| `ssh-rsa-2048-sign-1000x` / `ssh-rsa-2048-verify-1000x` | RSA-2048 |
| `ssh-rsa-3072-sign-1000x` / `ssh-rsa-3072-verify-1000x` | RSA-3072 |
| `ssh-rsa-4096-sign-1000x` / `ssh-rsa-4096-verify-1000x` | RSA-4096 |
| `ssh-ecdsa-p256-sign-1000x` / `ssh-ecdsa-p256-verify-1000x` | ECDSA P-256 |
| `ssh-ecdsa-p384-sign-1000x` / `ssh-ecdsa-p384-verify-1000x` | ECDSA P-384 |
| `ssh-ecdsa-p521-sign-1000x` / `ssh-ecdsa-p521-verify-1000x` | ECDSA P-521 |

**Botan** (output file: `crypto_botan.json`):

Benchmarks the [Botan](https://botan.randombit.net) C++ crypto library as an
independent cross-check against OpenSSL.  The `botan speed` command is used;
its ops/sec output is converted to hyperfine-compatible JSON so results are
directly comparable to `crypto_asymmetric.json`.  Skipped on hosts where
`botan`, `botan3`, or `botan2` is not installed.

| Benchmark (sign + verify pair) | Algorithm |
|---|---|
| `rsa-2048-sign-1000x` / `rsa-2048-verify-1000x` | RSA-2048 |
| `rsa-3072-sign-1000x` / `rsa-3072-verify-1000x` | RSA-3072 |
| `rsa-4096-sign-1000x` / `rsa-4096-verify-1000x` | RSA-4096 |
| `ecdsa-p256-sign-1000x` / `ecdsa-p256-verify-1000x` | ECDSA P-256 |
| `ecdsa-p384-sign-1000x` / `ecdsa-p384-verify-1000x` | ECDSA P-384 |
| `ecdsa-p521-sign-1000x` / `ecdsa-p521-verify-1000x` | ECDSA P-521 |
| `ed25519-sign-1000x` / `ed25519-verify-1000x` | Ed25519 |
| `ed448-sign-1000x` / `ed448-verify-1000x` | Ed448 |
| `ml-dsa-44-sign-1000x` / `ml-dsa-44-verify-1000x` | ML-DSA-44 — skipped if Botan < 3.4 |
| `ml-dsa-65-sign-1000x` / `ml-dsa-65-verify-1000x` | ML-DSA-65 — skipped if Botan < 3.4 |
| `ml-dsa-87-sign-1000x` / `ml-dsa-87-verify-1000x` | ML-DSA-87 — skipped if Botan < 3.4 |

**HMAC:** `hmac-sha256`, `hmac-sha512`, `hmac-sha3-256`

**Key derivation:** `pbkdf2-sha256-100k`, `pbkdf2-sha256-10k`

**GPG:** `gpg-sign`, `gpg-verify`

### Compiler

Tests compilation speed and the performance of the compiled output.

| Benchmark            | Tool  | Description                    |
|----------------------|-------|--------------------------------|
| gcc-O0-compile       | gcc   | Compile at -O0                 |
| gcc-O2-compile       | gcc   | Compile at -O2                 |
| gcc-O3-compile       | gcc   | Compile at -O3                 |
| gcc-O3-lto-compile   | gcc   | Compile at -O3 with LTO        |
| gcc-Os-compile       | gcc   | Compile at -Os                 |
| gcc-O3_graphite-compile | gcc | Compile at -O3 with Graphite polyhedral loop optimiser (`-floop-nest-optimize`); skipped if GCC was not built with ISL |
| clang-O0-compile     | clang | Compile at -O0                 |
| clang-O2-compile     | clang | Compile at -O2                 |
| clang-O3-compile     | clang | Compile at -O3                 |
| clang-O3-lto-compile | clang | Compile at -O3 with LTO        |
| clang-Os-compile     | clang | Compile at -Os                 |
| clang-O3_polly-compile | clang | Compile at -O3 with Polly polyhedral loop optimiser (`-mllvm -polly`); skipped if Clang was not built with Polly |
| gcc-O2-runtime       | gcc   | Run -O2-compiled binary        |
| gcc-O3-runtime       | gcc   | Run -O3-compiled binary        |
| gcc-O3_graphite-run  | gcc   | Run Graphite-optimised binary  |
| clang-O2-runtime     | clang | Run -O2-compiled binary        |
| clang-O3-runtime     | clang | Run -O3-compiled binary        |
| clang-O3_polly-run   | clang | Run Polly-optimised binary     |
| rust-debug           | rustc | Compile in debug mode          |
| rust-release         | rustc | Compile in release mode        |
| go-build             | go    | Compile a Go program           |

Results are written to `compiler_c_compile.json`, `compiler_c_runtime.json`,
`compiler_rust.json`, and `compiler_go.json`.

The `compiler_c_compile` and `compiler_c_runtime` report tables use a pivot
layout: compiler version strings (extracted from `--version` output) appear as
rows, and optimization levels (`-O0`, `-O2`, `-O3`, `-O3 -flto`, `-Os`, etc.)
appear as columns.

#### SQLite Amalgamation Compile (`compiler_sqlite.json`)

Compiles the SQLite 3.52 amalgamation (`sqlite3.c`, ≈8.5 MiB, ≈230 000 lines)
at `-O0`, `-O2`, and `-O3` with each available C compiler.  This gives
meaningful, multi-second timings that clearly separate fast and slow
configurations:

| Optimisation | Typical time (2-vCPU VM) |
|--------------|--------------------------|
| `-O0`        | 4–8 s                    |
| `-O2`        | 12–25 s                  |
| `-O3`        | 20–35 s                  |

SQLite and multi-file compile benchmarks use `run_benchmarks_large_compile_runs`
(default `2`) and `run_benchmarks_large_compile_warmup` (default `1`) rather
than the global run count, since compilation is highly deterministic and 2
measured runs + 1 warmup is sufficient for accurate timing.

The fixture file `benchmarks/fixtures/sqlite3.c` is downloaded by
`scripts/download_benchmark_fixtures.py`.

#### Multi-file Parallel Build (`compiler_multifile.json`)

Compiles a generated 30-module C project (~5 800 lines of non-trivial
arithmetic, sorting, and hashing code) sequentially (`-j1`) and in parallel
(`-j$(nproc)`) at `-O2` with each available C compiler.  This directly
measures parallelism benefit and is sensitive to CPU count and core speed.

Typical times on a 2-vCPU VM at -O2:

| Mode    | Typical time |
|---------|--------------|
| `-j1`   | 3–6 s        |
| `-j2`   | 1.5–3 s      |

The project is generated at benchmark time by
`scripts/generate_multifile_bench.py` and written to
`{{ run_benchmarks_work_dir }}/multifile_project/`.

### Python

Tests Python interpreter performance on micro-benchmarks using a single
`pybench.py` script.

| Benchmark           | Description                                     |
|---------------------|-------------------------------------------------|
| prime-sieve         | Sieve of Eratosthenes to 2 000 000              |
| json-serde          | JSON encode/decode round-trip (200× over 100-key dict) |
| regex               | Regex IP-address matching (500× over 1000-repeat string) |
| sha256-hash         | SHA-256 hash of 1 MiB buffer (200× iterations)  |
| list-comprehension  | `[x**2 for x in range(10000)]` — 500× iterations |
| dict-operations     | Dict build + `sum(values())` for 10 000 keys (500×) |
| python-all          | Composite: all six sub-benchmarks in sequence   |

The `python` report table uses a pivot layout: Python version label (e.g.
`py3.13`) appears as rows, and benchmark names appear as columns.  The
benchmark discovers all `python3.X` interpreters on the host, excluding
`python3.X-config` scripts.  NumPy benchmarks are in the separate `numeric`
category, not here.

### Octave

Tests GNU Octave numerical computing performance.

**File:** `octave.json`  
**Requires:** `octave` installed (via provisioning; default: `true`). Windows: installed via Chocolatey.

| Benchmark      | Description                                      |
|----------------|--------------------------------------------------|
| matrix-multiply| 500×500 matrix multiplication (BLAS-backed)      |
| fft            | 1 000 000-point FFT                               |
| sort           | Sort 1 000 000 values                             |
| prime-sieve    | Sieve of Eratosthenes to 1 000 000               |
| lu-decomp      | 500×500 LU decomposition                         |
| octave-all     | Composite: all five sub-benchmarks in sequence   |

The report table uses a pivot layout: Octave version label appears as rows,
benchmark names appear as columns, and results are aggregated per host.

### Numeric

Tests floating-point performance using compiled C programs and NumPy.
Results are written to **two separate JSON files**.

**`numeric_compiled.json`** — compiled C benchmarks (no external dependencies):

| Benchmark          | Description                                    |
|--------------------|------------------------------------------------|
| nbody-30m          | N-body simulation, 30 000 000 steps            |
| mandelbrot-6000    | Mandelbrot set, 6 000×6 000 grid               |
| spectral-norm-1000 | Spectral norm of a 1 000×1 000 matrix          |

**`numeric_numpy.json`** — NumPy benchmarks (skipped if NumPy not installed):

| Benchmark        | Description                                      |
|------------------|--------------------------------------------------|
| numpy-matmul-2000| 2 000×2 000 matrix multiplication                |
| numpy-fft2-2048  | 2D FFT on a 2 048×2 048 array                   |
| numpy-sort-10m   | Sort 10 000 000 random floats                    |

These benchmarks stress FP vectorisation, FMA, and SIMD instruction generation;
they are highly sensitive to `-march=native`, LTO, and compiler optimisation
level.

### SQLite

Tests SQLite I/O, transaction throughput, and query performance.

The template database contains **1 000 000 rows** and is created via Python's
`sqlite3` module at setup time.  If an existing database is smaller than
**10 MiB** it is considered stale (from an older run) and is automatically
deleted and regenerated before benchmarks run.

**Write benchmarks:**

| Benchmark    | Description                                      |
|--------------|--------------------------------------------------|
| insert-100k  | Bulk-insert 100 000 rows (Python inline script)  |
| update-500k  | Update 500 000 rows in place                     |

**Read benchmarks:**

| Benchmark        | Description                                    |
|------------------|------------------------------------------------|
| full-scan-agg    | Full table scan with aggregate (COUNT/SUM)     |
| indexed-range-sum| Range query on indexed column with SUM         |
| order-top-100k   | ORDER BY + LIMIT 100 000 on large table        |

### FFmpeg

Automatically discovers all available encoders and decoders and
benchmarks them.  Codec availability varies across distributions
depending on installed libraries and Gentoo USE flags.

**Video encoders — standard** (always benchmarked when available):

| Benchmark       | Library    | Parameters              |
|-----------------|------------|-------------------------|
| h264-encode     | libx264    | preset medium, CRF 23   |
| h265-encode     | libx265    | preset medium, CRF 28   |
| vp9-encode      | libvpx-vp9 | CRF 30, deadline=realtime, cpu-used 8 |
| av1-svt-encode  | libsvtav1  | CRF 35, preset 8        |

**Video encoders — extended** (only with `--extended-codecs` /
`run_benchmarks_ffmpeg_extended_codecs=true`):

| Benchmark       | Library    | Notes                   |
|-----------------|------------|-------------------------|
| vp8-encode      | libvpx     | Superseded by VP9/AV1; ~65 s/run on typical hardware |
| av1-aom-encode  | libaom-av1 | Reference AV1 encoder; very slow (research use) |
| av1-rav1e-encode| librav1e   | Experimental AV1 encoder |
| theora-encode   | libtheora  | Legacy Ogg/Theora       |
| xvid-encode     | libxvid    | Legacy MPEG-4 Part 2    |
| mpeg2-encode    | mpeg2video | Legacy MPEG-2           |
| mjpeg-encode    | mjpeg      | Motion JPEG             |

**Video decoders:** Each successfully encoded format is also decoded.

**Audio encoders — standard** (always benchmarked when available):

| Benchmark     | Library   | Parameters    |
|---------------|-----------|---------------|
| aac-encode    | aac       | 192 kbit/s    |
| opus-encode   | libopus   | 128 kbit/s    |
| mp3-encode    | libmp3lame| 192 kbit/s    |
| flac-encode   | flac      | Lossless      |
| vorbis-encode | libvorbis | quality 4     |

**Audio encoders — extended** (only with `--extended-codecs` /
`run_benchmarks_ffmpeg_extended_codecs=true`):

| Benchmark      | Library | Notes              |
|----------------|---------|--------------------|
| ac3-encode     | ac3     | Dolby Digital, 384 kbit/s |
| eac3-encode    | eac3    | Dolby Digital Plus, 384 kbit/s |
| wavpack-encode | wavpack | Lossless           |
| alac-encode    | alac    | Apple Lossless     |

**Audio decoders:** Each successfully encoded format is also decoded.

**Test media:** [Big Buck Bunny](https://peach.blender.org/) (CC BY 3.0, Blender
Foundation) — a 30-second FFV1 lossless 1080p 30fps clip extracted from the
9-minute film, plus a 60-second PCM audio track.  This real-world animated
source exercises colour prediction, motion estimation, and codec
entropy-coding in a way that a synthetic test card cannot.  The clip is
downloaded once to the controller by `scripts/download_benchmark_fixtures.py`
and copied to each host before the benchmarks run; if unavailable, a
deterministic synthetic source (1080p 30fps FFV1-encoded `testsrc2` pattern)
is generated as a fallback.

The audio source, extracted from the same BBB film, gives realistic codec
complexity; the fallback is a 440 Hz sine wave.

The report includes a **codec availability matrix** showing which codecs
are present on each host — useful for comparing Gentoo USE flag configurations.

### ImageMagick

Tests image manipulation operations on two sets of source images:

**4K noise image** — a deterministic 4096×4096 RGB PNG generated from a fixed
random seed (42) on the controller by `scripts/generate_benchmark_images.py`.
Identical on every host and every run.

| Benchmark   | Description                       |
|-------------|-----------------------------------|
| resize      | Resize to 50% with Lanczos filter |
| blur        | Gaussian blur                     |
| sharpen     | Unsharp mask sharpening           |
| convert-png | Convert JPEG → PNG                |
| convert-jpg | Convert PNG → JPEG (quality 85)   |
| rotate      | Rotate 90°                        |
| grayscale   | Convert to grayscale              |

**[Kodak Lossless True Color Image Suite](http://r0k.us/graphics/kodak/)** —
24 natural-scene photographs at 768×512 (free for research use), the standard
reference set used in published image-codec papers.  All 24 images are
processed in **2 batch commands** using shell loops rather than 24 individual
hyperfine commands; this avoids hyperfine startup overhead dominating the
measurement:

| Benchmark              | Description                                      |
|------------------------|--------------------------------------------------|
| encode-all-24-jpeg-q90 | JPEG Q90 encode of all 24 Kodak images (shell loop) |
| encode-all-24-png-z6   | PNG zlib-level-6 encode of all 24 images (shell loop) |

### Coreutils

Tests common command-line utilities on multi-megabyte datasets.  Results are
split across three JSON files.

**`coreutils.json`** — text-processing and file-system utilities:

| Benchmark   | Tool | Description                                      |
|-------------|------|--------------------------------------------------|
| sort        | sort | Sort a large text file                           |
| sort-unique | sort | Sort with deduplication (`-u`)                   |
| wc-lines    | wc   | Line count of the sort dataset                   |
| grep-pattern| grep | Count lines matching `^[A-Z].*[0-9]$`            |
| find-files  | find | Recursive `.txt` search across 10 000-file tree  |
| find-exec   | find | Recursive find with `wc -c` per file             |
| tar-create  | tar  | Create archive from 10 000-file tree             |
| du-summary  | du   | `du -sh` on the 10 000-file tree                 |

**`git.json`** — Git porcelain commands on a synthetic 300-commit repo:

| Benchmark    | Description                                          |
|--------------|------------------------------------------------------|
| git-log      | `git log --oneline` (full history)                   |
| git-log-stat | `git log --stat --quiet`                             |
| git-diff     | `git diff feature..<main>` across branches           |
| git-blame    | `git blame file_1.txt`                               |
| git-status   | `git status`                                         |

Git benchmarks are skipped if `git` is not installed.

**`diff.json`** — text-comparison utilities:

| Benchmark | Tool | Description                           |
|-----------|------|---------------------------------------|
| diff      | diff | Compare two 400 000-line half-files   |
| comm      | comm | Sorted-set operations on same files   |

Diff/comm benchmarks are skipped if `diff` is not installed.

The `findtree` fixture consists of **10 000 files** arranged as
100 directories × 2 subdirectories × 50 files each.  If an existing tree
contains fewer than 9 000 files (generated by an older run), it is
automatically removed and rebuilt at the start of the next run.

### Memory

Tests memory bandwidth and random-access latency.

| Benchmark        | Description                                                          |
|------------------|----------------------------------------------------------------------|
| shm-write-512m   | Sequential write: 512 MiB to `/dev/shm` tmpfs via `dd` (64 MiB × 8) |
| shm-read-512m    | Sequential read: 512 MiB from `/dev/shm` tmpfs via `dd` (64 MiB × 8) |
| pointer-chase-64m | Random pointer-chasing in a 64 MiB heap — measures cache/memory latency |

`shm-write-512m` and `shm-read-512m` are skipped on hosts without `/dev/shm`.
`pointer-chase-64m` uses a compiled C binary built on first run.

### Process

Tests process creation and IPC overhead.

| Benchmark        | Description                                                       |
|------------------|-------------------------------------------------------------------|
| fork-exec        | Fork + exec latency                                               |
| pipe-throughput  | Data throughput over a pipe                                       |
| shell-startup    | `/bin/sh -c true` startup latency                                 |
| python-startup   | `python3 -c pass` startup latency                                 |
| shell-spawn-500  | 500 `/bin/true` invocations per hyperfine run (process spawn cost)|
| python3-import   | Import latency: `os, sys, json, re, hashlib, pathlib, ast, socket, threading, subprocess, collections, itertools` |

### Disk I/O

Tests filesystem read and write performance.

| Benchmark     | Description                              |
|---------------|------------------------------------------|
| seq-write     | Sequential write via `dd`                |
| seq-read      | Sequential read via `dd`                 |
| sync-write    | Synchronous write (fsync per block)      |
| tar-create    | Create a tar archive                     |
| tar-extract   | Extract a tar archive                    |

> **Note:** Disk benchmarks are most meaningful on physical machines or
> VMs with dedicated storage.  VMs sharing a single HDD/SSD image will
> see high variance.

### Linker

Tests link time for both static and dynamic linking.

| Benchmark        | Description                            |
|------------------|----------------------------------------|
| ld-dynamic       | Link a medium C project dynamically    |
| ld-static        | Link a medium C project statically     |
| lld-dynamic      | Link with LLVM's lld (if available)    |
| gold-dynamic     | Link with GNU gold (if available)      |
| mold-dynamic     | Link with mold (if available)          |

The linker project consists of **400 source files** (`unit_000.c` …
`unit_399.c`), each containing 10 distinct functions, giving a realistic
many-object link workload.  Typical link times on a 2-vCPU VM:

| Linker | Typical time |
|--------|--------------|
| ld (BFD)  | 0.8–2.0 s |
| gold      | 0.4–1.0 s |
| lld       | 0.2–0.6 s |
| mold      | 0.1–0.3 s |

If the project directory contains fewer than **350** `unit_*.c` files (from
an older run), it is automatically deleted and regenerated before benchmarks
run.

### OpenCV

Tests image processing operations (requires OpenCV Python bindings).

| Benchmark     | Description                    |
|---------------|--------------------------------|
| load-save     | Image I/O round-trip           |
| blur          | Gaussian blur filter           |
| edge-detect   | Canny edge detection           |
| color-convert | Color space conversion         |

#### Kodak Corpus Benchmarks (`opencv_kodak.json`)

When Kodak images are available, a second set of benchmarks operates on all
24 natural-scene photographs to measure OpenCV throughput on realistic
photographic content.  The images are copied to the work directory
independently of the ImageMagick category, so these benchmarks function even
when ImageMagick is not installed.  If the Kodak images are absent the entire
`opencv_kodak.json` run is skipped gracefully.

| Command            | Operation                                               |
|--------------------|---------------------------------------------------------|
| `kodak-load`       | Decode all 24 PNGs — PNG decode throughput baseline     |
| `kodak-blur`       | GaussianBlur + bilateralFilter on all 24 images         |
| `kodak-edges`      | Canny + Sobel edge detection on all 24 images           |
| `kodak-color`      | BGR→HSV and BGR→Lab colour space conversion on all 24   |
| `kodak-orb`        | ORB keypoint detection and description on all 24 images |
| `kodak-clahe`      | CLAHE histogram equalisation on all 24 images           |
| `kodak-encode-jpeg`| In-memory JPEG Q90 re-encode on all 24 images           |

Results are written to `opencv_kodak.json`.

### GIMP

**File:** `gimp.json`  
**Requires:** GIMP installed (`media-gfx/gimp` on Gentoo). Enable with `provision_benchmarks_install_gimp: true`.  
**Corpus:** All 24 Kodak natural-scene photographs (768×512 PNG)

Benchmarks GIMP's batch-mode image processing using Script-Fu (`-i -n --no-data --no-fonts`).
`--no-data` and `--no-fonts` suppress loading of brushes, patterns, and fonts to keep startup
overhead consistent. Each benchmark processes all 24 Kodak images in a single GIMP invocation,
so startup time (typically 2–4 s in batch mode) is included in each measurement — this reflects
real-world GIMP invocation cost.

A Script-Fu library (`gimp_bench.scm`) and a shell wrapper (`gimp_bench_run.sh`) are written to
the work directory during setup.

| Command | Operation |
|---|---|
| `gimp-load-24` | Load + release all 24 PNGs — PNG decode throughput baseline |
| `gimp-blur-24` | Gaussian blur 21×21 kernel on all 24 images |
| `gimp-unsharp-24` | Unsharp mask (radius 3, strength 0.5) on all 24 images |
| `gimp-pipeline-24` | brightness-contrast + Gaussian blur + 2× cubic scale on all 24 |

Kodak images are copied to the work directory independently of the ImageMagick category,
so these benchmarks function even when ImageMagick is not installed.

### Inkscape

**File:** `inkscape.json`  
**Requires:** Inkscape **1.x** (`media-gfx/inkscape` on Gentoo). Enable with `provision_benchmarks_install_inkscape: true`.  
**Fixture:** `inkscape_bench.svg` — generated on the host during setup

A complex 440-element SVG fixture is generated via an inline Python script on first run:
- **300 star/polygon paths** with bezier curves, linear gradient fills, and occasional
  Gaussian-blur or drop-shadow filter effects
- **80 transformed groups** of 4 gradient-filled rectangles (rotate + scale transforms)
- **60 text labels** with gradient fills and mixed font families

The fixture is deterministic (`random.seed(42)`) for reproducible timings. At 96 DPI the
output is ~1200×900 px; at 300 DPI it is ~3750×2813 px, exercising the full rasterisation
pipeline at a meaningful resolution.

| Command | Operation |
|---|---|
| `render-96dpi` | SVG → PNG at 96 DPI (screen resolution) |
| `render-300dpi` | SVG → PNG at 300 DPI (print resolution, ~10 MP output) |
| `export-pdf` | SVG → PDF via Cairo |

> **Note:** Uses Inkscape 1.x CLI syntax (`--export-type`, `--export-dpi`, `--export-filename`).
> Inkscape 0.9x is not supported.

### Bash

Benchmarks bash shell interpreter performance on common build-system workload
patterns.  All execution benchmarks run with `bash --norc --noprofile` so
results reflect the interpreter, not rc-file loading overhead.

**File:** `bash.json`  
**Platform:** Linux/Unix only (not available on Windows).

| Benchmark    | Description                                                   |
|--------------|---------------------------------------------------------------|
| startup-bare | Binary load + exit (`bash --norc --noprofile -c true`)        |
| arith-loop   | Integer arithmetic via `(( ))` — 100 000-iteration loop       |
| str-concat   | String concatenation via `+=` — 30 000 appends                |
| str-subst    | Global pattern substitution `${s//x/y}` on 5 000-char string |
| array-build  | Indexed array: build 3 000 elements + full iteration          |
| assoc-array  | Associative array (`declare -A`): fill 2 000 keys + key scan  |
| func-calls   | Function-call overhead — 5 000 calls (no subshells)           |
| cmd-subst    | `$( )` command substitution — 200 iterations (always forks)   |
| while-read   | `while IFS= read -r` loop over 3 000 lines                    |
| regex-match  | `[[ "$s" =~ ERE ]]` in a 5 000-iteration loop                 |
| glob-match   | `[[ "$s" == *pattern* ]]` in a 10 000-iteration loop          |

### Boot Time

Collects system boot timing metrics.  Prefers `systemd-analyze` for accurate
phase breakdowns; falls back to `dmesg` timestamp parsing on non-systemd hosts
(OpenRC, SysVinit, etc.).

**File:** `boot_times.json`  
**Platform:** Linux/Unix only (not available on Windows).

| Metric        | Source                    | Description                                                    |
|---------------|---------------------------|----------------------------------------------------------------|
| firmware_sec  | systemd-analyze only      | UEFI/BIOS firmware initialisation time                         |
| loader_sec    | systemd-analyze only      | Boot loader (GRUB/systemd-boot) time                           |
| kernel_sec    | systemd-analyze / dmesg   | Kernel initialisation up to userspace handoff                  |
| userspace_sec | systemd-analyze / dmesg   | Time from kernel handoff to `graphical.target` (or last entry) |
| graphical_sec | systemd-analyze only      | Time to reach `graphical.target`                               |
| total_sec     | systemd-analyze / dmesg   | Total measured boot duration                                   |
| top_services  | systemd-analyze only      | Top 15 slowest systemd units by activation time                |

On non-systemd hosts only `kernel_sec`, `userspace_sec`, and `total_sec` are
populated; `firmware_sec`, `loader_sec`, `graphical_sec`, and `top_services`
are `null`.

### Application Startup

Measures cold-start time for GUI applications using a virtual framebuffer.

| Benchmark        | Application | Description     |
|------------------|-------------|-----------------|
| firefox-startup  | Firefox     | Launch and exit |
| gimp-startup     | GIMP        | Launch and exit |
| inkscape-startup | Inkscape    | Launch and exit |

### Gentoo Build Times

**Gentoo-only.** Analyzes emerge build history via `qlop` to correlate
package build times with kernel version and compiler configuration.

- Finds packages whose longest build exceeded 5 minutes (configurable via
  `run_benchmarks_gentoo_min_build_secs`)
- Reports the last 3 builds per package (configurable via
  `run_benchmarks_gentoo_max_builds`)
- For each build: version, date, duration, kernel version, compiler, CFLAGS

Only installation records (`>>>` in the emerge log) are included;
uninstallation records (`<<<`) are ignored.

## Reports

After benchmarks complete, two reports are generated automatically.

### Markdown Report

**`benchmarks/report.md`** — Plain-text tables for Git repos, wikis, or
terminal viewing.

Contents:
- Host configuration summary (OS, kernel, CPU, compiler versions, flags)
- Per-category comparison tables with mean ± stddev (fastest in bold)
- FFmpeg codec availability matrix
- Gentoo build time analysis (if applicable)

### HTML Report

**`benchmarks/report.html`** — Interactive single-file HTML page with dark
theme and Chart.js bar charts.

Contents:
- Navigation bar linking to each category
- Host summary table with LTO badges, hardening flags, compiler versions
- Interactive bar charts for each category
- Sortable comparison tables with fastest results highlighted
- Codec availability matrix with checkmarks
- Gentoo build time tables

No server required — all assets load from CDN.

### Regenerating Reports

If you have existing results and want to regenerate without re-running:

```bash
python3 scripts/generate_benchmark_report.py benchmarks/
```

This reads all JSON files in `benchmarks/results/` and produces updated
`report.md` and `report.html`.

### Anonymized Reports

To share results publicly without revealing internal hostnames:

```bash
python3 scripts/generate_benchmark_report.py benchmarks/ --anonymize
```

Hostnames are replaced with names from Greek mythology.  The mapping is
deterministic — sorted hostnames are assigned names in order.

### Performance Scores

Both reports include a **weighted performance score** (0–100) for each host
in the Host Configuration Summary.

**Formula:**

1. For every benchmark a host participated in:
   ```
   bench_score = min_time_across_all_hosts / host_time × 100
   ```
   The fastest host for that benchmark scores 100; a host twice as slow scores 50.

2. Scores are averaged per category → `category_score`.

3. A weighted average is taken across all categories:
   ```
   final_score = Σ(category_score × weight) / Σ(weights_used)
   ```

Hosts that did not run a benchmark are simply excluded from that benchmark's
scoring — they are not penalised for missing data (e.g. an incomplete run).

**Customising weights:**

Edit `scripts/scoring_weights.yml` to change how much each category
contributes to the final score.  The defaults reflect a Gentoo system
manager perspective where compilation speed is most important:

```yaml
weights:
  compiler:    3.0   # most relevant for emerge
  linker:      2.0
  compression: 2.0
  crypto:      2.0
  memory:      2.0
  disk:        2.0
  ffmpeg:      1.0
  # ... other categories at 1.0
  gentoo_build_times: 0.0  # excluded — not comparable hyperfine data
```

You can also pass a custom weights file at report-generation time:

```bash
python3 scripts/generate_benchmark_report.py benchmarks/ --weights my_weights.yml
```

Scores are printed to stdout when the report is generated:

```
Scores (weighted, 0–100):
   1. gentoo-beatrice: 94.3
   2. gentoo-clio: 87.6
   ...
```

The summary table is sorted by score (highest first) with 🥇🥈🥉 medals for
the top three hosts.  In the HTML report, scores are colour-coded green (high)
through amber to red (low).

> **Note:** Scores are only meaningful when hosts have run the same set of
> benchmarks.  A host that completed all categories will always score lower
> than one that only ran fast categories from a full run, so compare scores
> across full runs for fair results.

### Dashboard

`scripts/benchmark_dashboard.py` serves an interactive Plotly Dash web
dashboard for exploring and comparing results across hosts and categories.
It requires `pip install dash pandas`.

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
pip install dash pandas
python3 scripts/benchmark_dashboard.py benchmarks/

# Serve on all interfaces (e.g. inside a VM)
python3 scripts/benchmark_dashboard.py benchmarks/ --host 0.0.0.0 --port 9090
```

Then open `http://localhost:8050` in a browser.  Press **Ctrl+C** to stop.

Dashboard features:
- Filter by OS family or individual host
- Switch between benchmark categories
- Normalize times relative to the fastest host per benchmark
- Compare against a fixed baseline host
- Sort by name, fastest mean, or largest spread
- Toggle error bars (stddev) and horizontal bar orientation
- Export data as CSV

## Benchmark Fixture Files

The benchmark suite uses real-world standardised fixture files as inputs
instead of synthetic or randomly-generated data.  This ensures results are
meaningful, reproducible, and comparable against published benchmarks for the
same tools.

All fixtures are downloaded once to the controller by
`scripts/download_benchmark_fixtures.py` and then copied to each host before
the benchmarks run.  They are stored in `benchmarks/fixtures/` (git-ignored).

```bash
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/
# Skip the ~330 MiB BBB download (FFmpeg will use a synthetic fallback):
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --skip-video
# Force re-download of everything:
python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --force
```

This step is also run automatically (with `creates:` guard) at the start of
each benchmark play via `delegate_to: localhost, run_once: true`.

### Fixture Corpus Details

| Corpus | Category | Size | Licence |
|--------|----------|------|---------|
| [Silesia](http://sun.aei.polsl.pl/~sdeor/corpus/) | Compression | 211 MiB (12 files) | Free for benchmarking |
| [Canterbury](https://corpus.canterbury.ac.nz/) | Compression (reference) | 2.8 MiB (18 files) | Public domain |
| [Big Buck Bunny](https://peach.blender.org/) 1080p | FFmpeg video | ≈30 s FFV1 + 60 s WAV | CC BY 3.0, Blender Foundation |
| [Kodak LTCI](http://r0k.us/graphics/kodak/) | ImageMagick / OpenCV / GIMP | 24 PNG, ≈18 MiB | Free for research |
| Seed-42 4K PNG | ImageMagick | 48 MiB (generated) | Generated locally |
| [SQLite amalgamation](https://www.sqlite.org/amalgamation.html) 3.52 | Compiler | ≈8.5 MiB (`sqlite3.c`) | Public domain |
| SQLite benchmark DB | SQLite | ≥10 MiB (1 000 000 rows, Python-generated) | Generated locally |

### Fallback Behaviour

If a fixture file is unavailable (download failed or `--skip-video` was
passed), the corresponding benchmark task falls back to a synthetic source:

| Fixture | Fallback |
|---------|----------|
| `silesia_combined.bin` | **64 MiB** random binary (`/dev/urandom`); any existing file < 64 MiB is rebuilt |
| `bbb_1080p_30s.mkv` | `testsrc2` 1080p FFV1 synthetic video |
| `bbb_audio_60s.wav` | 440 Hz sine PCM audio |
| `kodak/` | Kodak benchmark is skipped |

## RAM Management

By default, each VM's RAM is scaled to its maximum configured value before
benchmarks run.  This ensures consistent results even when VMs normally
operate with reduced memory.

The provisioning plays for both Gentoo and FreeBSD also scale VM RAM to the
maximum via `virsh setmem --live` before compiling or installing ports, then
restore it to the configured minimum in an `always:` block — even if
provisioning fails.

Scaling flow (benchmarks):
1. Read max memory from `virsh dumpxml` (persistent configuration)
2. Scale up with `virsh setmem --live`
3. Run benchmarks
4. **Always** restore to the inactive config value (even on failure)

To disable RAM scaling:

```bash
./scripts/run_benchmarks.sh --no-ram-scale
```

`hypervisor_host` must be set in each VM's inventory variables so the
playbook knows which hypervisor to delegate `virsh` commands to.

## Windows Support

Windows benchmarks are opt-in.  Before running them, complete the
**[Windows connectivity setup](#windows-hosts)** in the Prerequisites section
above, then verify with:

```bash
ansible mswindows -m ansible.windows.win_ping
```

The following categories have Windows-specific task variants (`*_win.yml`):

| Category | What it measures |
|----------|-----------------|
| `compression` | Archive compress/decompress (7-Zip, tar) |
| `crypto` | Hash and cipher throughput (certutil, OpenSSL) |
| `compiler` | C/Rust/Go compile time (MSVC, gcc/MinGW, rustc, go) |
| `python` | Python stdlib workloads (prime-sieve, JSON, regex, SHA-256 hash, list comprehension, dict operations) |
| `octave` | GNU Octave numerical benchmarks (matrix-multiply, fft, sort, prime-sieve, lu-decomp) |
| `coreutils` | Sort, grep, find, archive, git operations (PowerShell) |
| `sqlite` | Bulk INSERT, indexed SELECT, ORDER BY (Python sqlite3) |
| `numeric` | Compiled FP workloads: n-body, Mandelbrot, spectral norm; numpy matmul/FFT/sort |
| `process` | Process creation overhead (cmd.exe, PowerShell, trivial exe) |
| `linker` | Link time for 400-file synthetic project (gcc/ld or MSVC link.exe) |
| `startup` | Interpreter and shell startup latency (Python, Node, PowerShell, cmd.exe) |
| `ffmpeg` | Video/audio encode+decode across available codecs (installed via Chocolatey) |
| `imagemagick` | Resize, effects, format encode/decode (Kodak suite + 4K fixture) |

```bash
./scripts/run_benchmarks.sh --include-windows
./scripts/run_benchmarks.sh --include-windows --manage-power --skip-existing
```

Normalization on Windows:
- Switches the power plan to **High Performance**
- Disables Windows Defender real-time protection temporarily
- Stops background services (SysMain, WSearch, wuauserv, DiagTrack, etc.)
- Disables automatic page-file management during the run

Categories not available on Windows: `memory`, `disk`, `bash`, `boot_time`,
`gentoo_build_times`, `opencv`, `gimp`, `inkscape`.

## Configuration Reference

### run\_benchmarks Role

All variables are prefixed `run_benchmarks_` and can be overridden via `-e`
or in inventory.

| Variable | Default | Description |
|----------|---------|-------------|
| `run_benchmarks_runs` | `5` | Hyperfine iterations per benchmark |
| `run_benchmarks_warmup` | `3` | Warmup runs before measurement |
| `run_benchmarks_large_compile_runs` | `2` | Hyperfine iterations for large-compile benchmarks (SQLite amalgamation, multi-file) |
| `run_benchmarks_large_compile_warmup` | `1` | Warmup runs for large-compile benchmarks |
| `run_benchmarks_compression_runs` | `3` | Hyperfine iterations for compression benchmarks (bzip2/xz are deterministic; 3 runs is sufficient) |
| `run_benchmarks_compression_warmup` | `1` | Warmup runs for compression benchmarks |
| `run_benchmarks_categories` | `[]` (all) | Categories to run |
| `run_benchmarks_results_dir` | `{{ playbook_dir }}/../benchmarks` | Local results directory |
| `run_benchmarks_work_dir` | `/tmp/ansible-benchmarks` | Remote working directory (Unix) |
| `run_benchmarks_work_dir_win` | `C:\ansible-benchmarks` | Remote working directory (Windows) |
| `run_benchmarks_compress_size_mb` | `64` | Test data size for compression fallback (MB) |
| `run_benchmarks_ffmpeg_video_runs` | `3` | Hyperfine iterations for FFmpeg video encode/decode |
| `run_benchmarks_ffmpeg_video_warmup` | `1` | Warmup runs for FFmpeg video benchmarks |
| `run_benchmarks_ffmpeg_audio_runs` | `3` | Hyperfine iterations for FFmpeg audio encode/decode |
| `run_benchmarks_ffmpeg_audio_warmup` | `1` | Warmup runs for FFmpeg audio benchmarks |
| `run_benchmarks_ffmpeg_task_timeout_sec` | `5400` | Per-task timeout for FFmpeg benchmarks (s) |
| `run_benchmarks_ffmpeg_extended_codecs` | `false` | Include extended codecs (slow/experimental/legacy; see [FFmpeg](#ffmpeg)) |
| `run_benchmarks_startup_runs` | `10` | Hyperfine iterations for application startup benchmarks |
| `run_benchmarks_startup_warmup` | `3` | Warmup runs for application startup benchmarks |
| `run_benchmarks_ffmpeg_duration_sec` | `10` | Test clip duration for FFmpeg synthetic fallback (s) |
| `run_benchmarks_min_disk_mb` | `2048` | Minimum free disk space on work_dir partition (MB) |
| `run_benchmarks_min_ram_mb` | `4096` | Minimum total RAM when work_dir is on tmpfs (MB) |
| `run_benchmarks_cpu_affinity` | `""` | CPU affinity range (e.g. `0-3`); empty = no pinning |
| `run_benchmarks_hyperfine_bin` | `hyperfine` | Path or name of the hyperfine binary |
| `run_benchmarks_include_windows` | `false` | Include Windows hosts |
| `run_benchmarks_skip_complete` | `false` | Skip hosts that already have a full result set |
| `run_benchmarks_skip_existing` | `false` | Skip individual categories whose result file already exists (non-empty) on the controller |
| `run_benchmarks_manage_power` | `false` | Boot shut-off VMs before benchmarking; shut them down afterwards |
| `run_benchmarks_boot_timeout_sec` | `180` | Seconds to wait for a VM to become reachable after `virsh start` |
| `run_benchmarks_is_hypervisor` | `false` | Set to `true` for hypervisor hosts |
| `run_benchmarks_gentoo_min_build_secs` | `300` | Minimum build time to include (s) |
| `run_benchmarks_gentoo_max_builds` | `3` | Recent builds to collect per package |

### provision\_benchmarks Role

| Variable | Default | Description |
|----------|---------|-------------|
| `provision_benchmarks_packages` | (per OS) | Package lists per OS family |
| `provision_benchmarks_epel_packages` | `[hyperfine]` | Extra EPEL packages for RHEL |
| `provision_benchmarks_hyperfine_version` | `1.20.0` | Hyperfine version for binary fallback |
| `provision_benchmarks_hyperfine_url` | (GitHub release URL) | URL for binary fallback download |
| `provision_benchmarks_hyperfine_sha256` | `63ad5393…` | SHA256 of the fallback binary tarball |
| `provision_benchmarks_install_ffmpeg` | `true` | Install FFmpeg from extra repos |
| `provision_benchmarks_install_numpy` | `true` | Install NumPy Python bindings |
| `provision_benchmarks_install_opencv` | `false` | Install OpenCV Python bindings |
| `provision_benchmarks_install_gimp` | `false` | Install GIMP for batch-mode image-processing benchmarks |
| `provision_benchmarks_install_inkscape` | `false` | Install Inkscape 1.x for SVG rendering benchmarks |
| `provision_benchmarks_install_mold` | `true` | Install mold linker for linker benchmarks |
| `provision_benchmarks_install_octave` | `true` | Install GNU Octave for numerical benchmarks |

## Troubleshooting

### "hyperfine is not installed"

Run the provisioning playbook first:

```bash
ansible-playbook playbooks/provision_benchmarks.yml
```

### VM is unreachable

The playbook skips unreachable hosts automatically and continues.  Check
connectivity:

```bash
ansible -m ping <hostname>
```

### RAM scaling fails

- Verify `hypervisor_host` is set in the VM's inventory
- Verify the controller can SSH to the hypervisor and `virsh` is available
- Disable scaling: `./scripts/run_benchmarks.sh --no-ram-scale`

### VM does not boot with `--manage-power`

- Verify `hypervisor_host` is set in the VM's inventory (populated by
  `inventory_generator.py`)
- Verify the controller can SSH to the hypervisor and that `virsh` is in PATH
- Check the VM name matches the `inventory_hostname` exactly:
  `virsh --connect qemu:///system domstate <hostname>`
- If the VM takes longer than 180 s to boot, increase the timeout:
  `-e run_benchmarks_boot_timeout_sec=300`

### Benchmark fails for a specific category

Individual failures do not stop the suite.  The `always:` block ensures
RAM is restored and completed results are still fetched.  Check Ansible
output for the specific error.

### "No results found" when generating report

Verify `benchmarks/results/` contains host directories with JSON files:

```
benchmarks/results/<hostname>/metadata.json
benchmarks/results/<hostname>/compression.json
…
```

### Slow AV1 encoding benchmarks

`libaom-av1` and `librav1e` are significantly slower than other codecs and are
excluded from the standard run.  They are available as **extended codecs** — opt
in only when needed:

```bash
# FFmpeg with all extended (slow/legacy) codecs
./scripts/run_benchmarks.sh --category ffmpeg --extended-codecs

# Or via Ansible variable
ansible-playbook playbooks/run_benchmarks.yml \
  -e run_benchmarks_ffmpeg_extended_codecs=true
```

If you only need the standard fast codecs, the default run takes approximately
20 minutes for FFmpeg across a typical Gentoo VM fleet.

### RHEL / OL hosts fail with "SyntaxError: future feature annotations"

Python 3.6 on RHEL 7/8 is too old for Ansible 2.17+.  See the
[prerequisites](#prerequisites) section for how to bootstrap Python 3.8
and set `ansible_python_interpreter`.

## Directory Layout

```
.
├── playbooks/
│   ├── run_benchmarks.yml           # Main benchmark playbook
│   └── provision_benchmarks.yml     # Benchmark tool installer
├── roles/
│   ├── run_benchmarks/
│   │   ├── defaults/main.yml        # Configurable variables
│   │   └── tasks/
│   │       ├── main.yml             # Category dispatcher
│   │       ├── setup.yml            # Verify tools, create test data, collect metadata
│   │       ├── calibrate.yml        # Calibrate hyperfine min-runs
│   │       ├── run_category.yml     # Generic per-category runner
│   │       ├── compression.yml
│   │       ├── crypto.yml
│   │       ├── compiler.yml
│   │       ├── python.yml
│   │       ├── octave.yml
│   │       ├── numeric.yml
│   │       ├── sqlite.yml
│   │       ├── ffmpeg.yml
│   │       ├── imagemagick.yml
│   │       ├── coreutils.yml
│   │       ├── memory.yml
│   │       ├── process.yml
│   │       ├── disk.yml
│   │       ├── linker.yml
│   │       ├── opencv.yml
│   │       ├── startup.yml
│   │       ├── gentoo_build_times.yml
│   │       ├── normalize.yml        # Pre-benchmark VM state (RAM scale-up)
│   │       └── denormalize.yml      # Post-benchmark VM state (RAM restore)
│   └── provision_benchmarks/
│       ├── defaults/main.yml        # Per-OS package lists and hyperfine version
│       └── tasks/
│           ├── main.yml             # OS-family dispatcher
│           ├── hyperfine_fallback.yml  # Binary download from GitHub
│           ├── verify.yml           # Tool availability check
│           └── os/
│               ├── gentoo.yml
│               ├── redhat.yml
│               ├── debian.yml
│               ├── archlinux.yml
│               ├── suse.yml
│               ├── freebsd.yml
│               ├── void.yml
│               ├── nixos.yml
│               └── solus.yml
├── scripts/
│   ├── run_benchmarks.sh                    # Benchmark wrapper script
│   ├── generate_benchmark_report.py         # Report generator (MD + HTML)
│   ├── generate_benchmark_images.py         # Deterministic 4K fixture image generator
│   ├── download_benchmark_fixtures.py       # Standard corpus downloader
│   └── benchmark_dashboard.py              # Interactive Plotly Dash dashboard
├── tests/unit/
│   └── test_benchmark_report.py            # Report generator tests
├── requirements.yml                        # Ansible collection dependencies
├── baremetal.txt                           # Hostnames of physical (non-VM) machines
└── benchmarks/                            # Output — git-ignored
    ├── report.md
    ├── report.html
    ├── fixtures/                           # Standardised benchmark inputs (git-ignored)
    │   ├── silesia/                        # Silesia corpus (12 files)
    │   ├── silesia_combined.bin            # All 12 files concatenated (~211 MiB)
    │   ├── cantrbry/                       # Canterbury corpus (18 files)
    │   ├── bbb_sunflower_1080p.mp4.zip     # BBB source zip download
    │   ├── bbb_sunflower_1080p_30fps_normal.mp4  # Extracted MP4
    │   ├── bbb_1080p_30s.mkv               # 30-second FFV1 lossless clip
    │   ├── bbb_audio_60s.wav               # 60-second PCM audio
    │   ├── kodak/                          # Kodak True Color Image Suite (24 PNG)
    │   ├── sqlite3.c                       # SQLite 3.52 amalgamation (~8.5 MiB)
    │   ├── im_4k.png                       # Deterministic seed-42 4K noise image
    │   ├── im_4k_q90.jpg                   # JPEG Q90 derivative
    │   └── im_4k.webp                      # WebP Q90 derivative
    └── results/
        └── <hostname>/
            ├── metadata.json
            ├── compression.json
            ├── crypto.json
            ├── compiler.json
            ├── ffmpeg_video_encode.json
            ├── ffmpeg_video_decode.json
            ├── ffmpeg_audio_encode.json
            ├── ffmpeg_audio_decode.json
            ├── ffmpeg_codecs.json
            ├── imagemagick_kodak_encode.json
            └── …
```
