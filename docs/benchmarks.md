# Benchmark Suite User Guide

The benchmark suite measures and compares performance across VMs with
different Linux distributions, compiler flags, and system configurations.
It uses [hyperfine](https://github.com/sharkdp/hyperfine) for statistical
benchmarking and produces Markdown and interactive HTML reports with
charts.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Provisioning VMs](#provisioning-vms)
- [Running Benchmarks](#running-benchmarks)
  - [Full Suite](#full-suite)
  - [Selected Categories](#selected-categories)
  - [Limiting Hosts](#limiting-hosts)
  - [Tuning Parameters](#tuning-parameters)
- [Benchmark Categories](#benchmark-categories)
  - [Compression](#compression)
  - [Cryptography](#cryptography)
  - [Compiler](#compiler)
  - [Python](#python)
  - [FFmpeg](#ffmpeg)
  - [Coreutils](#coreutils)
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
# 1. Install benchmark dependencies on all VMs
ansible-playbook playbooks/provision_benchmarks.yml

# 2. Run the full benchmark suite
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py

# 3. View results
open benchmarks/report.html      # interactive HTML with charts
cat benchmarks/report.md          # Markdown tables
```

## Architecture Overview

```
Controller                          VMs (one at a time)
──────────                          ───────────────────
provision_benchmarks.yml ────────► Install tools (hyperfine, gcc, …)
                                         │
run_benchmarks.yml ──────────────► Scale RAM → run benchmarks → fetch JSON
         │                               │
         │  benchmarks/results/<host>/   ◄┘  *.json (hyperfine output)
         │
         ▼
generate_benchmark_report.py ───► benchmarks/report.md
                                  benchmarks/report.html
```

The suite processes VMs **one at a time** (`serial: 1`) to avoid resource
contention on shared hypervisors.  Each VM's RAM is temporarily scaled to
its maximum configured value during the benchmark run and restored
afterwards — even if the benchmarks fail.

## Prerequisites

- **Ansible** 2.14+ on the controller
- **Python 3** on each target VM
- **SSH access** to all VMs (key-based recommended)
- **libvirt/virsh** access on hypervisors (for RAM scaling; optional)
- **hyperfine** on each target VM (installed by the provisioning playbook)

## Provisioning VMs

Before running benchmarks for the first time, install all required
software on the target VMs:

```bash
ansible-playbook playbooks/provision_benchmarks.yml
```

This installs compilers (GCC, Clang), language runtimes (Rust, Go,
Python), compression tools, FFmpeg, OpenSSL, and hyperfine.  It handles
package manager differences across OS families:

| OS Family  | Package Manager | Notes                                    |
|------------|-----------------|------------------------------------------|
| Gentoo     | emerge          | Full package atoms                       |
| RedHat     | dnf/yum         | Enables EPEL for hyperfine               |
| Debian     | apt             | Includes build-essential                 |
| Archlinux  | pacman          | Includes Manjaro, CachyOS                |
| Suse       | zypper          | openSUSE, SLES                           |
| FreeBSD    | pkg             | Uses llvm for clang                      |

If a package fails to install, provisioning continues with the remaining
packages and reports a summary at the end.

### Provisioning options

```bash
# Only provision VMs on one hypervisor
ansible-playbook playbooks/provision_benchmarks.yml --limit hypervisor_hv1

# Also install FFmpeg from extra repos (default: true)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_ffmpeg=true

# Install OpenCV Python bindings (default: false)
ansible-playbook playbooks/provision_benchmarks.yml \
  -e provision_benchmarks_install_opencv=true

# Provide sudo password interactively
ansible-playbook playbooks/provision_benchmarks.yml --ask-become-pass
```

## Running Benchmarks

### Full Suite

Run all benchmark categories on all reachable VMs:

```bash
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py
```

### Selected Categories

Run only specific categories to save time:

```bash
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e '{"run_benchmarks_categories": ["compression", "ffmpeg"]}'
```

Valid category names: `compression`, `crypto`, `compiler`, `python`,
`ffmpeg`, `coreutils`, `opencv`, `startup`, `gentoo_build_times`.

### Limiting Hosts

```bash
# Only VMs on one hypervisor
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  --limit 'hypervisor_hv1,localhost'

# Single VM
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  --limit 'gentoo-alice,localhost'
```

> **Note:** Always include `localhost` in the limit so the report
> generation play can run.

### Tuning Parameters

```bash
# More iterations for higher statistical confidence
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_runs=10 -e run_benchmarks_warmup=3

# Skip automatic RAM scaling
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_scale_ram=false

# Larger test data for compression benchmarks (MB)
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_compress_size_mb=128

# Longer FFmpeg test video (seconds)
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_ffmpeg_duration_sec=30
```

## Benchmark Categories

### Compression

Tests compression and decompression speed with a random data file.

| Benchmark       | Tool  | Description                  |
|-----------------|-------|------------------------------|
| gzip-compress   | gzip  | Compress with default level  |
| gzip-decompress | gzip  | Decompress                   |
| bzip2-compress  | bzip2 | Compress with default level  |
| bzip2-decompress| bzip2 | Decompress                   |
| xz-compress     | xz    | Compress with default level  |
| xz-decompress   | xz    | Decompress                   |
| zstd-compress   | zstd  | Compress with default level  |
| zstd-decompress | zstd  | Decompress                   |
| lz4-compress    | lz4   | Compress with default level  |
| lz4-decompress  | lz4   | Decompress                   |

**Test data:** Random binary file (`run_benchmarks_compress_size_mb`, default 64 MB).

### Cryptography

Tests encryption, hashing, and GPG operations.

| Benchmark          | Tool     | Description                       |
|--------------------|----------|-----------------------------------|
| aes-256-cbc        | openssl  | AES-256-CBC encryption            |
| sha256sum          | sha256sum| SHA-256 hash                      |
| sha512sum          | sha512sum| SHA-512 hash                      |
| b2sum              | b2sum    | BLAKE2 hash                       |
| gpg-sign           | gpg      | Sign a file with GPG              |
| gpg-verify         | gpg      | Verify a GPG signature            |

### Compiler

Tests compilation speed and resulting binary performance.

| Benchmark            | Tool      | Description                        |
|----------------------|-----------|------------------------------------|
| gcc-O0-compile       | gcc       | Compile at -O0                     |
| gcc-O2-compile       | gcc       | Compile at -O2                     |
| gcc-O3-compile       | gcc       | Compile at -O3                     |
| gcc-O3-lto-compile   | gcc       | Compile at -O3 with LTO            |
| gcc-Os-compile       | gcc       | Compile at -Os                     |
| clang-O0-compile     | clang     | Compile at -O0                     |
| clang-O2-compile     | clang     | Compile at -O2                     |
| clang-O3-compile     | clang     | Compile at -O3                     |
| clang-O3-lto-compile | clang     | Compile at -O3 with LTO            |
| clang-Os-compile     | clang     | Compile at -Os                     |
| gcc-O2-runtime       | gcc       | Run -O2-compiled binary            |
| gcc-O3-runtime       | gcc       | Run -O3-compiled binary            |
| clang-O2-runtime     | clang     | Run -O2-compiled binary            |
| clang-O3-runtime     | clang     | Run -O3-compiled binary            |
| rust-debug           | rustc     | Compile in debug mode              |
| rust-release         | rustc     | Compile in release mode            |
| go-build             | go        | Compile a Go program               |

### Python

Tests Python interpreter performance.

| Benchmark   | Description                              |
|-------------|------------------------------------------|
| fibonacci   | Recursive Fibonacci(32)                  |
| json-serde  | JSON encode/decode round-trip            |
| regex       | Regex IP address matching                |
| hashlib     | MD5 hashing                              |
| numpy       | NumPy matrix operations (if installed)   |

### FFmpeg

Discovers all available encoders and decoders on each host and benchmarks
them automatically.  Codec availability varies across distributions
depending on installed libraries and USE flags.

**Video Encoders** (benchmarked if available):

| Benchmark         | Library     | Parameters                     |
|-------------------|-------------|--------------------------------|
| h264-encode       | libx264     | preset medium, CRF 23         |
| h265-encode       | libx265     | preset medium, CRF 28         |
| vp8-encode        | libvpx      | CRF 10, 1M bitrate            |
| vp9-encode        | libvpx-vp9  | CRF 30, variable bitrate      |
| av1-svt-encode    | libsvtav1   | CRF 35, preset 8              |
| av1-aom-encode    | libaom-av1  | CRF 35, cpu-used 8            |
| av1-rav1e-encode  | librav1e    | QP 100, speed 10              |
| theora-encode     | libtheora   | quality 7                      |
| xvid-encode       | libxvid     | quality 5                      |
| mpeg2-encode      | mpeg2video  | 5 Mbit/s                      |
| mjpeg-encode      | mjpeg       | quality 5                      |

**Video Decoders:** Each successfully encoded format is also decoded
using the corresponding decoder.

**Audio Encoders** (benchmarked if available):

| Benchmark       | Library     | Parameters          |
|-----------------|-------------|---------------------|
| aac-encode      | aac         | 192 kbit/s          |
| opus-encode     | libopus     | 128 kbit/s          |
| mp3-encode      | libmp3lame  | 192 kbit/s          |
| flac-encode     | flac        | Lossless            |
| vorbis-encode   | libvorbis   | quality 4           |
| ac3-encode      | ac3         | 384 kbit/s          |
| eac3-encode     | eac3        | 384 kbit/s          |
| wavpack-encode  | wavpack     | Lossless            |
| alac-encode     | alac        | Lossless            |

**Audio Decoders:** Each successfully encoded format is also decoded.

**Test media:** Synthetic 1920×1080 30fps video with 440 Hz sine tone
(`run_benchmarks_ffmpeg_duration_sec`, default 10 seconds); 60-second
audio for audio-only tests.

The report includes a **codec availability matrix** showing which codecs
are available on each host — useful for comparing Gentoo USE flag
configurations.

### Coreutils

Tests common command-line utilities on multi-megabyte datasets.

| Benchmark   | Tool  | Description                     |
|-------------|-------|---------------------------------|
| sort        | sort  | Sort a large text file          |
| find        | find  | Recursive file search           |
| sed         | sed   | Stream text transformation      |
| grep        | grep  | Pattern matching                |
| wc          | wc    | Line/word/byte counting         |
| diff        | diff  | File comparison                 |

### OpenCV

Tests image processing operations (requires OpenCV Python bindings).

| Benchmark       | Description                  |
|-----------------|------------------------------|
| load-save       | Image I/O round-trip         |
| blur            | Gaussian blur filter         |
| edge-detect     | Canny edge detection         |
| color-convert   | Color space conversion       |

### Application Startup

Measures cold-start time for GUI applications using a virtual
framebuffer (Xvfb).

| Benchmark       | Application | Description          |
|-----------------|-------------|----------------------|
| firefox-startup | Firefox     | Launch and exit      |
| gimp-startup    | GIMP        | Launch and exit      |
| inkscape-startup| Inkscape    | Launch and exit      |

### Gentoo Build Times

**Gentoo-only.** Analyzes emerge build history using `qlop` to identify
packages with long build times and correlate them with kernel and
compiler versions.

- Finds packages whose longest build exceeded 5 minutes (configurable
  via `run_benchmarks_gentoo_min_build_secs`)
- Reports the last 3 builds per package (configurable via
  `run_benchmarks_gentoo_max_builds`)
- For each build, shows: version, build date, duration, kernel version
  at build time, compiler, and CFLAGS

This is useful for tracking how compiler changes or kernel updates
affect build times for heavy packages like `webkit-gtk`, `firefox`,
`gcc`, or `llvm`.

## Reports

After all benchmarks complete, the suite automatically generates two
report files.

### Markdown Report

**`benchmarks/report.md`** — Plain-text tables suitable for Git
repositories, wikis, or terminal viewing.

Contents:
- Host configuration summary (OS, kernel, CPU, compiler versions, flags)
- Per-category comparison tables with mean ± stddev (fastest in bold)
- FFmpeg codec availability matrix
- Gentoo build time analysis (if applicable)

### HTML Report

**`benchmarks/report.html`** — Interactive single-file HTML page with a
dark theme and Chart.js bar charts.

Contents:
- Navigation bar linking to each category
- Host summary table with LTO badges, hardening flags, compiler versions
- Interactive bar charts for each benchmark category
- Sortable comparison tables with fastest results highlighted
- Codec availability matrix with checkmarks
- Gentoo build time tables with date, duration, kernel, compiler

Open it in any browser — no server required, all assets are loaded from
CDNs.

### Regenerating Reports

If you have existing results and want to regenerate reports without
re-running benchmarks:

```bash
python3 scripts/generate_benchmark_report.py benchmarks/
```

This reads all JSON files from `benchmarks/results/` and produces
updated `report.md` and `report.html`.

### Anonymized Reports

To share benchmark results publicly without revealing internal
hostnames, use the `--anonymize` flag:

```bash
python3 scripts/generate_benchmark_report.py benchmarks/ --anonymize
```

This replaces all hostnames with names from Greek mythology (Zeus, Hera,
Poseidon, …) throughout both the Markdown and HTML reports.  The mapping
is deterministic — sorted hostnames are assigned names in order, so
regenerating the report produces the same pseudonyms.

## RAM Management

By default, the playbook temporarily scales each VM's RAM to its maximum
configured value (from the libvirt XML) during the benchmark run.  This
ensures consistent results even when VMs normally run with minimal
memory.

The scaling flow:
1. Read max memory from `virsh dumpxml` (persistent configuration)
2. Scale up via `virsh setmem --live`
3. Run benchmarks
4. **Always** restore to the minimal value from `virsh dumpxml --inactive`
   (even on failure)

To disable RAM scaling (for VMs that already have enough memory):

```bash
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_scale_ram=false
```

The `hypervisor_host` inventory variable must be set for each VM so the
playbook knows which hypervisor to delegate `virsh` commands to.

## Windows Support

Windows benchmarks are **opt-in** and require WinRM connectivity.  A
subset of categories (compression, crypto, compiler, Python, coreutils)
have Windows task variants.

```bash
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e run_benchmarks_include_windows=true
```

## Configuration Reference

### run\_benchmarks Role

All variables are prefixed with `run_benchmarks_` and can be overridden
via `-e` on the command line or in inventory.

| Variable                            | Default                      | Description                                    |
|-------------------------------------|------------------------------|------------------------------------------------|
| `run_benchmarks_runs`               | `5`                          | Number of hyperfine iterations per benchmark   |
| `run_benchmarks_warmup`             | `1`                          | Warmup runs before measurement                 |
| `run_benchmarks_categories`         | `[]` (all)                   | List of categories to run                      |
| `run_benchmarks_results_dir`        | `{{ playbook_dir }}/../benchmarks` | Local directory for collected results    |
| `run_benchmarks_work_dir`           | `/tmp/ansible-benchmarks`    | Remote working directory (Unix)                |
| `run_benchmarks_work_dir_win`       | `C:\ansible-benchmarks`      | Remote working directory (Windows)             |
| `run_benchmarks_compress_size_mb`   | `64`                         | Size of random test data for compression       |
| `run_benchmarks_ffmpeg_duration_sec`| `10`                         | Duration of test video in seconds              |
| `run_benchmarks_hyperfine_bin`      | `hyperfine`                  | Path or name of the hyperfine binary           |
| `run_benchmarks_include_windows`    | `false`                      | Include Windows hosts in benchmark runs        |
| `run_benchmarks_gentoo_min_build_secs` | `300`                     | Minimum build time to include (seconds)        |
| `run_benchmarks_gentoo_max_builds`  | `3`                          | Number of recent builds to collect per package |
| `run_benchmarks_scale_ram`          | `true`                       | Scale VM RAM to max during benchmarks          |

### provision\_benchmarks Role

| Variable                                | Default     | Description                               |
|-----------------------------------------|-------------|-------------------------------------------|
| `provision_benchmarks_packages`         | (per OS)    | Package lists per OS family               |
| `provision_benchmarks_epel_packages`    | `[hyperfine]` | Extra EPEL packages for RHEL            |
| `provision_benchmarks_hyperfine_version`| `0.1.4`     | Hyperfine version for binary fallback     |
| `provision_benchmarks_install_ffmpeg`   | `true`      | Install FFmpeg from extra repos           |
| `provision_benchmarks_install_opencv`   | `false`     | Install OpenCV Python bindings            |

## Troubleshooting

### "hyperfine is not installed"

Run the provisioning playbook first:

```bash
ansible-playbook playbooks/provision_benchmarks.yml
```

### VM is unreachable

The playbook automatically skips unreachable VMs and continues with the
next one.  Check SSH connectivity:

```bash
ansible -m ping <hostname>
```

### RAM scaling fails

- Ensure `hypervisor_host` is set in the VM's inventory
- Ensure the Ansible controller can SSH to the hypervisor
- Ensure `virsh` is available and the user has permissions
- Disable scaling with `-e run_benchmarks_scale_ram=false`

### Benchmark fails for a specific category

Individual category failures do not stop the entire suite.  The
`always:` block ensures RAM is restored and any completed results are
still fetched.  Check the Ansible output for the specific error.

### "No results found" when generating report

Ensure `benchmarks/results/` contains host directories with JSON files.
The directory structure should be:

```
benchmarks/results/<hostname>/metadata.json
benchmarks/results/<hostname>/compression.json
benchmarks/results/<hostname>/...
```

### Slow AV1 encoding benchmarks

The `libaom-av1` encoder is significantly slower than other codecs, even
at its fastest preset (`cpu-used 8`).  If this is too slow, run
benchmarks without the FFmpeg category and add it separately for a subset
of hosts:

```bash
# Run everything except FFmpeg
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e '{"run_benchmarks_categories": ["compression", "crypto", "compiler", "python", "coreutils"]}'

# Run FFmpeg separately on one host
ansible-playbook playbooks/run_benchmarks.yml -i inventory_generator.py \
  -e '{"run_benchmarks_categories": ["ffmpeg"]}' \
  --limit 'gentoo-alice,localhost'
```

## Directory Layout

```
.
├── playbooks/
│   ├── run_benchmarks.yml          # Main benchmark playbook
│   └── provision_benchmarks.yml    # Dependency installer
├── roles/
│   ├── run_benchmarks/
│   │   ├── defaults/main.yml       # Configurable variables
│   │   └── tasks/
│   │       ├── main.yml            # Category dispatcher
│   │       ├── setup.yml           # Verify tools, create test data, metadata
│   │       ├── compression.yml     # gzip, bzip2, xz, zstd, lz4
│   │       ├── crypto.yml          # OpenSSL, GPG
│   │       ├── compiler.yml        # GCC, Clang, Rust, Go
│   │       ├── python.yml          # Python micro-benchmarks
│   │       ├── ffmpeg.yml          # Video/audio encode/decode (all codecs)
│   │       ├── coreutils.yml       # sort, grep, find, sed, wc, diff
│   │       ├── opencv.yml          # Image processing
│   │       ├── startup.yml         # GUI application startup times
│   │       ├── gentoo_build_times.yml  # Gentoo qlop analysis
│   │       ├── normalize.yml       # Pre-benchmark VM state prep
│   │       └── denormalize.yml     # Post-benchmark VM state restore
│   └── provision_benchmarks/
│       ├── defaults/main.yml       # Per-OS package lists
│       └── tasks/main.yml          # Package installation logic
├── scripts/
│   └── generate_benchmark_report.py  # Report generator (MD + HTML)
├── tests/unit/
│   └── test_benchmark_report.py    # Report generator tests
└── benchmarks/                     # Output (git-ignored)
    ├── report.md                   # Generated Markdown report
    ├── report.html                 # Generated HTML report
    └── results/
        └── <hostname>/
            ├── metadata.json       # Host configuration metadata
            ├── compression.json    # Hyperfine results
            ├── ffmpeg_video_encode.json
            ├── ffmpeg_video_decode.json
            ├── ffmpeg_audio_encode.json
            ├── ffmpeg_audio_decode.json
            ├── ffmpeg_codecs.json  # Available codec list
            └── ...
```
