# local.gentoomanager provision_benchmarks Role

Installs benchmark dependencies on target hosts across multiple operating
systems (Gentoo, Debian/Ubuntu, Fedora/RHEL, Arch Linux, FreeBSD, macOS,
Windows).  Handles package installation, Python/NumPy setup, and optional
FFmpeg installation.

## Requirements

- Privilege escalation (`become: true`) for package installation
- OS-specific package managers available on the target host

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `provision_benchmarks_packages` | *(per-OS dict)* | Packages to install per OS family |
| `provision_benchmarks_install_ffmpeg` | `false` | Whether to install FFmpeg |
| `provision_benchmarks_install_numpy` | `true` | Whether to install NumPy/Python |
| `provision_benchmarks_freebsd_hyperfine_port` | `benchmarks/hyperfine` | FreeBSD port for hyperfine |
| `provision_benchmarks_freebsd_ffmpeg_port` | `multimedia/ffmpeg` | FreeBSD port for FFmpeg |

## OS-Specific Notes

### Gentoo

Rust is installed separately from the main package list using a preferred/fallback
strategy:

1. **`dev-lang/rust`** (source build) is attempted first — preferred because it
   is compiled with the system's `CFLAGS`, `CHOST`, and other Portage settings.
2. **`dev-lang/rust-bin`** (pre-built binary) is installed as a fallback if the
   source build is unavailable (e.g. not keyworded or masked on that host).
3. **`eselect rust update`** is run after either install to activate the latest
   available Rust toolchain.

## Dependencies

None.

## Example Playbook

```yaml
- name: Provision benchmark dependencies
  hosts: all
  roles:
    - role: local.gentoomanager.provision_benchmarks
      vars:
        provision_benchmarks_install_ffmpeg: true
```

## License

GPL-3.0-or-later

## Author Information

https://github.com/feinorgh/gentoomanager
