# local.gentoomanager run_benchmarks Role

Runs a comprehensive cross-platform benchmark suite using
[hyperfine](https://github.com/sharkdp/hyperfine).  Covers compression,
cryptography, compiler (C/C++ compile and runtime), linker, disk I/O,
memory bandwidth, Python interpreter, and coreutils categories.

Supports Linux (all major distributions), macOS, FreeBSD, and Windows.

## Requirements

- `hyperfine` installed on the target (handled by `provision_benchmarks`)
- A writable work directory on the target host
- Standard build tools (`gcc`, `openssl`, etc.) for relevant categories

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `run_benchmarks_work_dir` | `/tmp/ansible-benchmarks` | Remote working directory |
| `run_benchmarks_fixture_dir` | *(controller path)* | Local directory for corpora fixtures |
| `run_benchmarks_runs` | `5` | Number of hyperfine timed runs |
| `run_benchmarks_warmup` | `3` | Number of hyperfine warm-up runs |
| `run_benchmarks_ffmpeg_video_runs` | `3` | Timed runs for FFmpeg video benchmarks |
| `run_benchmarks_ffmpeg_video_warmup` | `2` | Warmup runs for FFmpeg video benchmarks |
| `run_benchmarks_startup_runs` | `3` | Timed runs for application startup benchmarks |
| `run_benchmarks_startup_warmup` | `2` | Warmup runs for application startup benchmarks |
| `run_benchmarks_compress_size_mb` | `64` | Test data size for compression fallback (MB) |
| `run_benchmarks_categories` | *(all)* | List of benchmark categories to run |
| `run_benchmarks_report_dir` | `benchmarks/` | Output directory for JSON results |

See `defaults/main.yml` for the full variable reference.

## Dependencies

- `local.gentoomanager.provision_benchmarks` (recommended, run first)

## Example Playbook

```yaml
- name: Run benchmarks on all hosts
  hosts: all
  roles:
    - role: local.gentoomanager.provision_benchmarks
    - role: local.gentoomanager.run_benchmarks
      vars:
        run_benchmarks_runs: 5
        run_benchmarks_categories:
          - compression
          - crypto
          - compiler
```

## License

GPL-3.0-or-later

## Author Information

https://github.com/feinorgh/gentoomanager
