# local.gentoomanager provision_benchmarks Role

Installs benchmark dependencies on target hosts across multiple operating
systems (Gentoo, Debian/Ubuntu, Fedora/RHEL, Arch Linux, FreeBSD, OpenBSD,
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
| `provision_benchmarks_freebsd_backend` | `ports` | FreeBSD build/install backend: `ports`, `poudriere`, or `auto` |
| `provision_benchmarks_freebsd_poudriere_jail` | `benchmark` | Poudriere jail name used when backend is `poudriere` or `auto` |
| `provision_benchmarks_freebsd_poudriere_ports_tree` | `default` | Poudriere ports tree name |
| `provision_benchmarks_freebsd_poudriere_set` | `benchmark` | Poudriere package set (`-z`) name |

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

Gentoo VMs are provisioned serially (one host at a time) to avoid saturating
shared hypervisor CPUs during source compilation. Before provisioning begins,
the VM's RAM is scaled to its libvirt maximum (`virsh setmem --live`), delegated
to the `hypervisor_host`. RAM is always restored to the inactive configuration
value when provisioning finishes — even if it fails. Bare-metal Gentoo hosts
(no `hypervisor_host`) skip the RAM scaling steps.

### FreeBSD

The role now supports two FreeBSD backends:

1. `ports` (default): installs directly from `/usr/ports` via
   `make install BATCH=yes`.
2. `poudriere`: validates poudriere jail/tree/pkg-repo wiring, runs
   `poudriere bulk -n` preflight for the full benchmark dependency set,
   then builds and installs from the poudriere pkg repository.

Set `provision_benchmarks_freebsd_backend: auto` to prefer poudriere only
when a complete poudriere setup is detected; otherwise the role falls back
to `ports`.

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
