# local.gentoomanager apply_portage_config Role

Applies Portage configuration to Gentoo hosts by writing
`/etc/portage/make.conf` and `/etc/portage/package.use/*` from variables
previously collected by the `collect_use_flags` role.

## Requirements

- Gentoo Linux target hosts
- Variables populated by the `collect_use_flags` role (or equivalent)
- Privilege escalation (`become: true`) for writing to `/etc/portage/`

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `apply_portage_config_make_conf_vars` | `{}` | Dict of make.conf key/value pairs to write |
| `apply_portage_config_package_use` | `{}` | Dict of package atoms → USE flag lists |
| `apply_portage_config_backup` | `true` | Whether to back up existing files before overwriting |

## Dependencies

Typically run after `collect_use_flags`.

## Example Playbook

```yaml
- name: Apply collected Portage configuration
  hosts: gentoo_hosts
  roles:
    - role: local.gentoomanager.collect_use_flags
    - role: local.gentoomanager.apply_portage_config
```

## License

GPL-3.0-or-later

## Author Information

https://github.com/feinorgh/gentoomanager
