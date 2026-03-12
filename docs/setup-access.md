# Setting Up Passwordless Ansible Access

This guide explains how to configure remote systems so that Ansible can connect
and run privileged tasks without interactive password prompts.

Two independent pieces are needed:

1. **SSH key authentication** — so Ansible can open an SSH session without a
   password.
2. **Passwordless privilege escalation** — so Ansible can run `become: true`
   tasks (package installation, service management, etc.) without a `sudo`
   password prompt.

---

## Table of Contents

- [1. SSH Key Authentication](#1-ssh-key-authentication)
  - [1.1 Generate a Key Pair](#11-generate-a-key-pair)
  - [1.2 Copy the Public Key to the Managed Node](#12-copy-the-public-key-to-the-managed-node)
  - [1.3 Manual Setup (when ssh-copy-id is unavailable)](#13-manual-setup-when-ssh-copy-id-is-unavailable)
  - [1.4 Test the Connection](#14-test-the-connection)
  - [1.5 Ansible Connection Variables](#15-ansible-connection-variables)
- [2. Passwordless Privilege Escalation](#2-passwordless-privilege-escalation)
  - [2.1 sudo — Linux (all distros)](#21-sudo--linux-all-distros)
  - [2.2 doas — Gentoo, FreeBSD, OpenBSD](#22-doas--gentoo-freebsd-openbsd)
  - [2.3 Ansible Become Variables](#23-ansible-become-variables)
- [3. Verifying Everything Works](#3-verifying-everything-works)
- [4. Security Notes](#4-security-notes)
- [References](#references)

---

## 1. SSH Key Authentication

Ansible uses SSH to communicate with managed nodes. The simplest and most
reliable approach is to authenticate with an SSH key pair rather than a
password.

### 1.1 Generate a Key Pair

Run this **on the Ansible controller** (your workstation or CI host):

```bash
# Ed25519 is the recommended algorithm (small, fast, secure)
ssh-keygen -t ed25519 -C "ansible@controller" -f ~/.ssh/ansible_ed25519
```

- `-t ed25519` — key type. Use `rsa -b 4096` if the managed node's OpenSSH is
  older than 6.5 (unlikely on any modern system).
- `-C` — a comment to identify the key in `authorized_keys` files.
- `-f` — output file. Omit to use the default `~/.ssh/id_ed25519`.
- You will be asked for a **passphrase**. For automated Ansible runs, leave it
  empty (just press Enter) or use `ssh-agent` to unlock it once per session.

> **Using ssh-agent with a passphrase-protected key:**
> ```bash
> eval "$(ssh-agent -s)"
> ssh-add ~/.ssh/ansible_ed25519
> # The agent holds the decrypted key for the rest of the shell session.
> ```

**References:**
- `man ssh-keygen` — <https://man.openbsd.org/ssh-keygen>
- Ansible docs on SSH connection: <https://docs.ansible.com/ansible/latest/inventory_guide/connection_details.html>

---

### 1.2 Copy the Public Key to the Managed Node

Use `ssh-copy-id` to append the public key to the remote user's
`~/.ssh/authorized_keys`:

```bash
ssh-copy-id -i ~/.ssh/ansible_ed25519.pub user@managed-host
```

Replace `user` with the account Ansible will connect as (often `root` for
Gentoo VMs, or a dedicated `ansible` service account).

`ssh-copy-id` will ask for the remote user's password **once** — after this,
the key will be accepted instead.

**References:**
- `man ssh-copy-id` — <https://man.openbsd.org/ssh-copy-id>

---

### 1.3 Manual Setup (when ssh-copy-id is unavailable)

If `ssh-copy-id` is not available (e.g. the node is only accessible via a
jump host, or you are bootstrapping from a provisioning script):

```bash
# On the controller: print the public key
cat ~/.ssh/ansible_ed25519.pub

# On the managed node (as the target user):
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

The permissions are strict requirements of OpenSSH — incorrect permissions
cause silent authentication failures.

---

### 1.4 Test the Connection

```bash
ssh -i ~/.ssh/ansible_ed25519 user@managed-host
```

You should get a shell prompt without a password prompt. Exit, then confirm
Ansible can reach the host:

```bash
ansible -i 'managed-host,' all -m ping \
  -u user --private-key ~/.ssh/ansible_ed25519
```

Expected output:

```
managed-host | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

---

### 1.5 Ansible Connection Variables

Set the connection details in `host_vars/<hostname>/vars.yml` or in
`group_vars/all/vars.yml` (for all hosts):

```yaml
# group_vars/all/vars.yml
ansible_user: ansible           # remote user to log in as
ansible_ssh_private_key_file: ~/.ssh/ansible_ed25519
```

Or for hosts that use a different user:

```yaml
# host_vars/gentoo-web01/vars.yml
ansible_user: root
ansible_ssh_private_key_file: ~/.ssh/ansible_ed25519
```

These can also be set in `ansible.cfg` under `[defaults]`:

```ini
[defaults]
remote_user          = ansible
private_key_file     = ~/.ssh/ansible_ed25519
```

**References:**
- Ansible inventory connection variables:
  <https://docs.ansible.com/ansible/latest/reference_appendices/special_variables.html>
- `ansible.cfg` reference:
  <https://docs.ansible.com/ansible/latest/reference_appendices/config.html>

---

## 2. Passwordless Privilege Escalation

Many tasks in this collection require `become: true` (running as `root`).
To avoid interactive password prompts during automated runs, configure the
privilege escalation tool on each managed node to allow passwordless escalation
for the Ansible user.

### 2.1 sudo — Linux (all distros)

`sudo` is the standard privilege escalation tool on Linux. The configuration
file is `/etc/sudoers` (and drop-in files under `/etc/sudoers.d/`). Always
edit it with `visudo`, which validates syntax before saving.

**Option A — NOPASSWD for a dedicated Ansible user (recommended):**

```bash
# On the managed node, as root:
visudo -f /etc/sudoers.d/ansible
```

Add:

```sudoers
# Allow the 'ansible' user to run any command as root without a password
ansible ALL=(ALL) NOPASSWD: ALL
```

**Option B — NOPASSWD for a specific group:**

Many distros add admin users to the `wheel` group (RedHat/Arch) or `sudo`
group (Debian). To make the entire group passwordless:

```sudoers
# RedHat / Arch Linux
%wheel ALL=(ALL) NOPASSWD: ALL

# Debian / Ubuntu
%sudo  ALL=(ALL) NOPASSWD: ALL
```

> **Warning:** `NOPASSWD: ALL` grants unlimited root access without
> confirmation. Restrict to specific commands if the Ansible user also has
> interactive access. See [Security Notes](#4-security-notes).

**Verify:**

```bash
sudo -l -U ansible   # lists what 'ansible' may run — should show NOPASSWD
```

**Packages:**

| OS | Package |
|---|---|
| Gentoo | `app-admin/sudo` |
| Debian / Ubuntu | `sudo` (usually pre-installed) |
| RedHat / CentOS / Alma | `sudo` (usually pre-installed) |
| Arch Linux | `sudo` |
| SUSE | `sudo` |
| FreeBSD | `security/sudo` |

**References:**
- `man sudoers` — <https://www.sudo.ws/docs/man/sudoers.man/>
- `man sudo` — <https://www.sudo.ws/docs/man/sudo.man/>
- sudo project documentation — <https://www.sudo.ws/docs/>

---

### 2.2 doas — Gentoo, FreeBSD, OpenBSD

`doas` is a lighter alternative to `sudo`, originating in OpenBSD. It is
available on Gentoo (`app-admin/doas`) and FreeBSD (`security/doas`), and is
the only privilege escalation tool on OpenBSD.

Configuration is in `/etc/doas.conf`:

```bash
# On the managed node, as root:
$EDITOR /etc/doas.conf
chmod 0400 /etc/doas.conf    # doas requires strict permissions
```

Add:

```
# Allow 'ansible' to run any command as root without a password
permit nopass ansible as root
```

For a group (e.g. `wheel`):

```
permit nopass :wheel as root
```

**Verify:**

```bash
doas -u root id   # should print uid=0(root) without a password prompt
```

**Tell Ansible to use doas:**

```yaml
# host_vars/<hostname>/vars.yml
ansible_become_method: doas
```

Or globally in `ansible.cfg`:

```ini
[privilege_escalation]
become_method = doas
```

> **Gentoo note:** Gentoo ships `doas` but not `sudo` by default on minimal
> profiles. Check which is installed with `which sudo doas`.

**References:**
- `man doas` — <https://man.openbsd.org/doas>
- `man doas.conf` — <https://man.openbsd.org/doas.conf>
- Gentoo Wiki — doas: <https://wiki.gentoo.org/wiki/Doas>

---

### 2.3 Ansible Become Variables

These variables control how Ansible escalates privileges. Set them in
`group_vars`, `host_vars`, or `ansible.cfg`.

| Variable | Default | Description |
|---|---|---|
| `ansible_become` | `false` | Enable privilege escalation for this host |
| `ansible_become_method` | `sudo` | Escalation tool: `sudo`, `doas`, `su`, `pbrun`, … |
| `ansible_become_user` | `root` | Target user to become |
| `ansible_become_password` | _(none)_ | Password to supply — leave unset when using `NOPASSWD` |

**Example — `group_vars/all/vars.yml` (sudo, passwordless):**

```yaml
ansible_become: true
ansible_become_method: sudo
ansible_become_user: root
```

**Example — a host running doas instead of sudo:**

```yaml
# host_vars/gentoo-alma/vars.yml
ansible_become: true
ansible_become_method: doas
ansible_become_user: root
```

Playbooks in this collection already include `become: true` on tasks that
require root. You do **not** need to add `-b` or `--become` on the command
line once the variables are set.

**References:**
- Ansible privilege escalation guide:
  <https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_privilege_escalation.html>
- List of become plugins:
  <https://docs.ansible.com/ansible/latest/collections/ansible/builtin/#become-plugins>

---

## 3. Verifying Everything Works

After completing the above, run this end-to-end check for each host:

```bash
# 1. Passwordless SSH connection
ansible -i 'managed-host,' all -m ping -u ansible \
  --private-key ~/.ssh/ansible_ed25519

# 2. Passwordless privilege escalation
ansible -i 'managed-host,' all -m command -a 'id' \
  -u ansible --private-key ~/.ssh/ansible_ed25519 \
  --become --become-method sudo

# 3. Against all hosts in the collection inventory
ansible all -m ping
ansible all -m command -a 'id' --become
```

With this collection's inventory (`inventory_generator.py`):

```bash
python3 inventory_generator.py --list   # confirm hosts are discovered
ansible all -m ping                      # confirm SSH works for all
ansible all -m command -a 'whoami' --become  # confirm become works for all
```

---

## 4. Security Notes

- **Dedicated service account:** create a non-root `ansible` user on managed
  nodes rather than connecting directly as `root`. This limits the blast radius
  if the controller is compromised.

- **Restrict NOPASSWD scope:** if the `ansible` user also has interactive
  logins, use `NOPASSWD: /path/to/specific/commands` instead of `NOPASSWD: ALL`.

- **Key passphrase + ssh-agent:** a passphrase-protected key stored in
  `ssh-agent` gives the benefits of keyless automation without leaving an
  unprotected private key on disk.

- **Known hosts:** keep `~/.ssh/known_hosts` up to date (or set
  `host_key_checking = False` in `ansible.cfg` only on trusted isolated
  networks — never in production).

- **Audit logging:** `sudo` logs all commands to syslog by default.
  `doas` can be configured with `log` in `doas.conf`. Review these logs
  periodically.

---

## References

| Resource | URL |
|---|---|
| `ssh-keygen(1)` | <https://man.openbsd.org/ssh-keygen> |
| `ssh-copy-id(1)` | <https://man.openbsd.org/ssh-copy-id> |
| `sshd_config(5)` | <https://man.openbsd.org/sshd_config> |
| `sudoers(5)` | <https://www.sudo.ws/docs/man/sudoers.man/> |
| `doas(1)` | <https://man.openbsd.org/doas> |
| `doas.conf(5)` | <https://man.openbsd.org/doas.conf> |
| Gentoo Wiki — SSH | <https://wiki.gentoo.org/wiki/SSH> |
| Gentoo Wiki — Sudo | <https://wiki.gentoo.org/wiki/Sudo> |
| Gentoo Wiki — Doas | <https://wiki.gentoo.org/wiki/Doas> |
| Ansible — Connection details | <https://docs.ansible.com/ansible/latest/inventory_guide/connection_details.html> |
| Ansible — Privilege escalation | <https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_privilege_escalation.html> |
| Ansible — `ansible.cfg` reference | <https://docs.ansible.com/ansible/latest/reference_appendices/config.html> |
