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
  - [Application Startup](#application-startup)
  - [Gentoo Build Times](#gentoo-build-times)
- [Reports](#reports)
  - [Markdown Report](#markdown-report)
  - [HTML Report](#html-report)
  - [Regenerating Reports](#regenerating-reports)
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
Controller                          Hosts (provisioning: parallel per OS family)
──────────                          ──────────────────────────────────────────
provision_benchmarks.yml ────────► Play 1: gather facts → dynamic OS groups
                                   Play 2: Gentoo  (serial=1, compile noise)
                                   Play 3: RedHat  (parallel)
                                   Play 4: Debian  (parallel)
                                   …

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

**Provisioning** is parallelized per OS family — all Debian hosts, all
RedHat hosts, etc. run simultaneously — except Gentoo, which is serialized
(`serial: 1`) because each `emerge` compilation saturates the hypervisor's
CPU cores and would add noise to build-time measurements.

**Benchmarks** run one host at a time.  Each VM's RAM is temporarily scaled
to its maximum configured value during the run and restored afterwards —
even if benchmarks fail.

## Prerequisites

- **Ansible** 2.17+ on the controller
- **Python 3.10+** on the controller
- **Python 3.8+** on managed nodes
- **SSH access** to all target hosts (key-based recommended)
- **libvirt/virsh** on hypervisors (for RAM scaling; optional)
- **Collections:** `ansible-galaxy collection install -r requirements.yml`

> **RHEL 7 / RHEL 8:** These ship Python 3.6, which is too old for
> Ansible 2.17+.  Bootstrap Python 3.8 before provisioning:
>
> ```bash
> # RHEL 7 — install via Software Collections
> subscription-manager repos --enable rhel-server-rhscl-7-rpms
> yum install rh-python38
>
> # RHEL 8 — install via AppStream
> dnf install python38
> ```
>
> Then set `ansible_python_interpreter` in `host_vars/<host>/main.yml`:
> ```yaml
> # RHEL 7
> ansible_python_interpreter: /opt/rh/rh-python38/root/usr/bin/python3.8
>
> # RHEL 8
> ansible_python_interpreter: /usr/bin/python3.8
> ```

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
| FreeBSD | ports (`make BATCH=yes`) | — | |
| Void Linux | xbps-install | — | |
| NixOS | nix-env | — | |
| Solus | eopkg | — | |

If `hyperfine` is not available in the package manager, a pre-built binary
is downloaded from the [GitHub release](https://github.com/sharkdp/hyperfine/releases).

> **Note:** `ffmpeg` on RHEL 9/10 currently fails to install from RPM Fusion
> due to a packaging issue in the RPM Fusion repo itself.  All other packages
> install successfully.  FFmpeg benchmarks will be skipped automatically on
> those hosts.

### Provisioning options

```bash
# Provision only one hypervisor's VMs
ansible-playbook playbooks/provision_benchmarks.yml --limit hypervisor_adele

# Skip FFmpeg (saves time on hosts where it is slow to install)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_ffmpeg=false

# Install OpenCV Python bindings (default: false, heavy)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_opencv=true

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

Flags:
  --include-windows           Also run benchmarks on Windows VMs
  --no-ram-scale              Skip temporary RAM scaling
  --no-report                 Skip report generation after benchmarks
  --verbose, -v               Enable verbose Ansible output (repeat for -vvv)
  --dry-run, -C               Check mode — no changes applied
  --ask-become-pass, -K       Prompt for sudo/become password
```

```bash
# Run all benchmarks on all hosts
./scripts/run_benchmarks.sh

# Single host, verbose
./scripts/run_benchmarks.sh --host gentoo-alma -v

# Only compression and crypto on hypervisor adele's VMs
./scripts/run_benchmarks.sh --hypervisor adele --category compression,crypto

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
`numeric`, `sqlite`, `ffmpeg`, `imagemagick`, `coreutils`, `memory`,
`process`, `disk`, `linker`, `opencv`, `startup`, `gentoo_build_times`.

Pass an empty list `[]` (the default) to run all categories.

### Limiting Hosts

```bash
# Only VMs on one hypervisor
./scripts/run_benchmarks.sh --hypervisor adele

# Single VM
./scripts/run_benchmarks.sh --host gentoo-alma

# Inventory group
./scripts/run_benchmarks.sh --group gentoo

# Baremetal machines (hostnames read from baremetal.txt)
./scripts/run_benchmarks.sh --group baremetal

# Raw Ansible limit expression
./scripts/run_benchmarks.sh --limit 'gentoo-alma,gentoo-diana'
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
```

## Benchmark Categories

### Compression

Tests compression and decompression speed on a random binary file.

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

**Test data:** Random binary file, size `run_benchmarks_compress_size_mb` (default 64 MB).

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
`rsa-2048-sign`, `rsa-2048-verify`, `rsa-4096-sign`,
`ecdsa-p256-sign`, `ecdsa-p256-verify`,
`ed25519-sign`, `ed25519-verify`

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
| clang-O0-compile     | clang | Compile at -O0                 |
| clang-O2-compile     | clang | Compile at -O2                 |
| clang-O3-compile     | clang | Compile at -O3                 |
| clang-O3-lto-compile | clang | Compile at -O3 with LTO        |
| clang-Os-compile     | clang | Compile at -Os                 |
| gcc-O2-runtime       | gcc   | Run -O2-compiled binary        |
| gcc-O3-runtime       | gcc   | Run -O3-compiled binary        |
| clang-O2-runtime     | clang | Run -O2-compiled binary        |
| clang-O3-runtime     | clang | Run -O3-compiled binary        |
| rust-debug           | rustc | Compile in debug mode          |
| rust-release         | rustc | Compile in release mode        |
| go-build             | go    | Compile a Go program           |

### Python

Tests Python interpreter performance on micro-benchmarks.

| Benchmark  | Description                            |
|------------|----------------------------------------|
| fibonacci  | Recursive Fibonacci(32)                |
| json-serde | JSON encode/decode round-trip          |
| regex      | Regex IP address matching              |
| hashlib    | MD5 hashing                            |
| numpy      | NumPy matrix operations (if installed) |

### Numeric

Tests floating-point performance using NumPy (requires numpy installed).

| Benchmark   | Description                             |
|-------------|-----------------------------------------|
| matmul      | Matrix multiplication                   |
| fft         | Fast Fourier Transform                  |
| svd         | Singular Value Decomposition            |
| linalg-norm | Linear algebra norm computation         |
| random-gen  | Random number generation (PCG-64)       |

### SQLite

Tests SQLite I/O, transaction throughput, and query performance.

| Benchmark      | Description                                |
|----------------|--------------------------------------------|
| insert-batch   | Bulk insert with transaction batching      |
| insert-single  | Single-row inserts (sync writes)           |
| select-scan    | Full table scan with filter                |
| select-index   | Indexed point lookup                       |
| update         | In-place row updates                       |
| pragma-wal     | Write-Ahead Logging mode performance       |

### FFmpeg

Automatically discovers all available encoders and decoders and
benchmarks them.  Codec availability varies across distributions
depending on installed libraries and Gentoo USE flags.

**Video encoders** (benchmarked when available):

| Benchmark       | Library    | Parameters              |
|-----------------|------------|-------------------------|
| h264-encode     | libx264    | preset medium, CRF 23   |
| h265-encode     | libx265    | preset medium, CRF 28   |
| vp8-encode      | libvpx     | CRF 10, 1M bitrate      |
| vp9-encode      | libvpx-vp9 | CRF 30, variable        |
| av1-svt-encode  | libsvtav1  | CRF 35, preset 8        |
| av1-aom-encode  | libaom-av1 | CRF 35, cpu-used 8      |
| av1-rav1e-encode| librav1e   | QP 100, speed 10        |
| theora-encode   | libtheora  | quality 7               |
| xvid-encode     | libxvid    | quality 5               |
| mpeg2-encode    | mpeg2video | 5 Mbit/s                |
| mjpeg-encode    | mjpeg      | quality 5               |

**Video decoders:** Each successfully encoded format is also decoded.

**Audio encoders** (benchmarked when available):

| Benchmark     | Library   | Parameters    |
|---------------|-----------|---------------|
| aac-encode    | aac       | 192 kbit/s    |
| opus-encode   | libopus   | 128 kbit/s    |
| mp3-encode    | libmp3lame| 192 kbit/s    |
| flac-encode   | flac      | Lossless      |
| vorbis-encode | libvorbis | quality 4     |
| ac3-encode    | ac3       | 384 kbit/s    |
| eac3-encode   | eac3      | 384 kbit/s    |
| wavpack-encode| wavpack   | Lossless      |
| alac-encode   | alac      | Lossless      |

**Audio decoders:** Each successfully encoded format is also decoded.

**Test media:** Synthetic 1920×1080 30fps video with 440 Hz sine tone,
duration `run_benchmarks_ffmpeg_duration_sec` (default 10 s); 60 s for
audio-only tests.

The report includes a **codec availability matrix** showing which codecs
are present on each host — useful for comparing Gentoo USE flag configurations.

### ImageMagick

Tests image manipulation operations on a generated test image.

| Benchmark   | Description                       |
|-------------|-----------------------------------|
| resize      | Resize to 50% with Lanczos filter |
| blur        | Gaussian blur                     |
| sharpen     | Unsharp mask sharpening           |
| convert-png | Convert JPEG → PNG                |
| convert-jpg | Convert PNG → JPEG (quality 85)   |
| rotate      | Rotate 90°                        |
| grayscale   | Convert to grayscale              |

### Coreutils

Tests common command-line utilities on multi-megabyte datasets.

| Benchmark | Tool  | Description                  |
|-----------|-------|------------------------------|
| sort      | sort  | Sort a large text file       |
| find      | find  | Recursive file search        |
| sed       | sed   | Stream text transformation   |
| grep      | grep  | Pattern matching             |
| wc        | wc    | Line/word/byte counting      |
| diff      | diff  | File comparison              |

### Memory

Tests memory allocation, copy, and access patterns.

| Benchmark     | Description                              |
|---------------|------------------------------------------|
| malloc-free   | Repeated allocation and deallocation     |
| memcpy        | Large block memory copy via `dd`         |
| sequential    | Sequential memory access pattern         |
| random-access | Random memory access (cache pressure)    |

### Process

Tests process creation and IPC overhead.

| Benchmark      | Description                            |
|----------------|----------------------------------------|
| fork-exec      | Fork + exec latency                    |
| pipe-throughput| Data throughput over a pipe            |
| shell-startup  | `/bin/sh -c true` startup latency      |
| python-startup | `python3 -c pass` startup latency      |

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

### OpenCV

Tests image processing operations (requires OpenCV Python bindings).

| Benchmark     | Description                    |
|---------------|--------------------------------|
| load-save     | Image I/O round-trip           |
| blur          | Gaussian blur filter           |
| edge-detect   | Canny edge detection           |
| color-convert | Color space conversion         |

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

## RAM Management

By default, each VM's RAM is scaled to its maximum configured value before
benchmarks run.  This ensures consistent results even when VMs normally
operate with reduced memory.

Scaling flow:
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

Windows benchmarks are opt-in and require WinRM connectivity.  A subset of
categories has Windows task variants: `compression`, `crypto`, `compiler`,
`python`, `coreutils`.

```bash
./scripts/run_benchmarks.sh --include-windows
```

## Configuration Reference

### run\_benchmarks Role

All variables are prefixed `run_benchmarks_` and can be overridden via `-e`
or in inventory.

| Variable | Default | Description |
|----------|---------|-------------|
| `run_benchmarks_runs` | `5` | Hyperfine iterations per benchmark |
| `run_benchmarks_warmup` | `3` | Warmup runs before measurement |
| `run_benchmarks_categories` | `[]` (all) | Categories to run |
| `run_benchmarks_results_dir` | `{{ playbook_dir }}/../benchmarks` | Local results directory |
| `run_benchmarks_work_dir` | `/tmp/ansible-benchmarks` | Remote working directory (Unix) |
| `run_benchmarks_work_dir_win` | `C:\ansible-benchmarks` | Remote working directory (Windows) |
| `run_benchmarks_compress_size_mb` | `64` | Test data size for compression (MB) |
| `run_benchmarks_ffmpeg_duration_sec` | `10` | Test clip duration for FFmpeg (s) |
| `run_benchmarks_cpu_affinity` | `""` | CPU affinity range (e.g. `0-3`); empty = no pinning |
| `run_benchmarks_hyperfine_bin` | `hyperfine` | Path or name of the hyperfine binary |
| `run_benchmarks_include_windows` | `false` | Include Windows hosts |
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

`libaom-av1` is significantly slower than other codecs even at the fastest
preset.  Run FFmpeg separately on a subset of hosts if needed:

```bash
# Everything except FFmpeg
./scripts/run_benchmarks.sh --category compression,crypto,compiler,python,coreutils

# FFmpeg only on one host
./scripts/run_benchmarks.sh --host gentoo-alma --category ffmpeg
```

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
│   ├── run_benchmarks.sh                # Benchmark wrapper script
│   └── generate_benchmark_report.py     # Report generator (MD + HTML)
├── tests/unit/
│   └── test_benchmark_report.py         # Report generator tests
├── requirements.yml                     # Ansible collection dependencies
├── baremetal.txt                        # Hostnames of physical (non-VM) machines
└── benchmarks/                          # Output — git-ignored
    ├── report.md
    ├── report.html
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
            └── …
```
