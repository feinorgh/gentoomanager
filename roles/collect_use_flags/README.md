# local.gentoomanager collect_use_flags Role

Collects Portage configuration from Gentoo hosts — USE flags from
`/etc/portage/package.use/*` and build settings from `/etc/portage/make.conf`
— and writes them into `host_vars/` and `group_vars/all/` for use by the
`apply_portage_config` role.

## Requirements

- Gentoo Linux target hosts
- Read access to `/etc/portage/` on the remote host (no `become` required for reading)

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `collect_use_flags_host_vars_dir` | `host_vars/` | Path to write per-host variable files |
| `collect_use_flags_group_vars_dir` | `group_vars/all/` | Path to write shared variable files |

## Dependencies

None.

## Example Playbook

```yaml
- name: Collect Portage configuration from all Gentoo hosts
  hosts: gentoo_hosts
  roles:
    - role: local.gentoomanager.collect_use_flags
```

## License

GPL-3.0-or-later

## Author Information

https://github.com/feinorgh/gentoomanager
