# Preparation Guide

This guide covers every one-time setup step required before running any
playbook or script in this collection.  Complete these steps once per
controller host; re-running them is always safe.

## Table of Contents

- [1. Requirements](#1-requirements)
- [2. Installation](#2-installation)
  - [2.1 Clone the Repository](#21-clone-the-repository)
  - [2.2 Install Ansible Collection Dependencies](#22-install-ansible-collection-dependencies)
- [3. Configure the Inventory](#3-configure-the-inventory)
  - [3.1 Hypervisors](#31-hypervisors)
  - [3.2 Bare-metal Hosts](#32-bare-metal-hosts)
  - [3.3 Group and Host Variables](#33-group-and-host-variables)
- [4. SSH Access](#4-ssh-access)
  - [4.1 Generate an SSH Key Pair](#41-generate-an-ssh-key-pair)
  - [4.2 Copy the Public Key to Each Managed Node](#42-copy-the-public-key-to-each-managed-node)
  - [4.3 Configure Ansible Connection Variables](#43-configure-ansible-connection-variables)
- [5. Privilege Escalation](#5-privilege-escalation)
  - [5.1 sudo (Linux)](#51-sudo-linux)
  - [5.2 doas (Gentoo, FreeBSD, OpenBSD)](#52-doas-gentoo-freebsd-openbsd)
  - [5.3 Configure Ansible Become Variables](#53-configure-ansible-become-variables)
- [6. Special Cases](#6-special-cases)
  - [6.1 RHEL 7 / RHEL 8 — Python Bootstrap](#61-rhel-7--rhel-8--python-bootstrap)
  - [6.2 Windows Hosts](#62-windows-hosts)
- [7. Verify Everything Works](#7-verify-everything-works)

---

## 1. Requirements

| Component | Minimum version | Notes |
|-----------|----------------|-------|
| Ansible Core (controller) | 2.17 | |
| Python (controller) | 3.10 | |
| Python (managed nodes — Linux/Unix) | 3.8 | See [RHEL note](#61-rhel-7--rhel-8--python-bootstrap) |
| SSH (managed nodes) | key-based | See section 4 |
| libvirt / virsh (hypervisors) | any | Required only for RAM scaling and VM power management |

The collection has no runtime Python library requirements beyond Ansible
itself.  Development/test tooling requirements are listed in
[docs/development.md](development.md).

---

## 2. Installation

### 2.1 Clone the Repository

```bash
git clone <repo-url>
cd local.gentoomanager
```

### 2.2 Install Ansible Collection Dependencies

```bash
ansible-galaxy collection install -r requirements.yml
```

Runtime dependencies (`requirements.yml`):

| Collection | Purpose |
|-----------|---------|
| `community.general` | Portage module, make module for FreeBSD ports |
| `chocolatey.chocolatey` | Windows benchmark provisioning via Chocolatey |
| `ansible.windows` | Windows connectivity (`win_ping`, `win_command`, …) |

---

## 3. Configure the Inventory

The inventory is generated dynamically by `inventory_generator.py`.  It reads
two plain-text host lists and produces Ansible groups automatically.

### 3.1 Hypervisors

Copy the example file and add your KVM hypervisor hostnames (one per line):

```bash
cp hypervisors.txt.example hypervisors.txt
```

```
# hypervisors.txt — one hostname or IP per line; lines starting with # are ignored
hv1.example.com
hv2.example.com
```

Hosts defined in `hypervisors.txt` are reachable from the controller by their
hostname.  All VMs that belong to a given hypervisor are discovered automatically
from `virsh list --all` and placed in `hypervisor_<name>` groups.

### 3.2 Bare-metal Hosts

```bash
cp baremetal.txt.example baremetal.txt
```

Add bare-metal hostnames (one per line).  Bare-metal hosts are placed in the
`baremetal` group and are never subjected to VM power management or RAM scaling.

### 3.3 Group and Host Variables

Variable files live under `group_vars/` and `host_vars/`.  Example templates
are provided under `group_vars.example/` and `host_vars.example/`.

```bash
# Copy the example structure as a starting point
cp -r group_vars.example/* group_vars/
cp -r host_vars.example/* host_vars/
```

Each VM's `host_vars/<hostname>/main.yml` should at minimum define:

```yaml
# host_vars/gentoo-vm1/main.yml
hypervisor_host: hv1          # the hypervisor this VM lives on
ansible_host: 192.168.10.5   # IP (if DNS is not available)
```

List the currently known inventory:

```bash
# List all hosts and their groups
ansible-inventory --list --yaml

# Show a single host's variables
ansible-inventory --host <hostname>
```

---

## 4. SSH Access

Ansible connects to managed nodes over SSH.  Key-based authentication is
required for non-interactive operation.

> **Full guide:** [docs/setup-access.md](setup-access.md) contains detailed
> instructions for all scenarios including ssh-agent setup, vault-encrypted
> passphrases, and Windows SSH configuration.

### 4.1 Generate an SSH Key Pair

Run this **on the Ansible controller**:

```bash
# Ed25519 is recommended (fast, small, widely supported)
ssh-keygen -t ed25519 -C "ansible@controller" -f ~/.ssh/ansible_ed25519
```

Leave the passphrase empty for fully automated runs, or use `ssh-agent`
to unlock a passphrase-protected key once per session.

### 4.2 Copy the Public Key to Each Managed Node

**Linux / Unix:**

```bash
ssh-copy-id -i ~/.ssh/ansible_ed25519.pub <user>@<managed-host>
```

If `ssh-copy-id` is not available, append the key manually:

```bash
cat ~/.ssh/ansible_ed25519.pub | ssh <user>@<managed-host> \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
   cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

**Windows:** See [section 6.2](#62-windows-hosts) below.

### 4.3 Configure Ansible Connection Variables

Add to `group_vars/all/vars.yml` (applies to all hosts):

```yaml
ansible_user: ansible                           # remote user to log in as
ansible_ssh_private_key_file: ~/.ssh/ansible_ed25519
```

Or to a specific host's `host_vars/<host>/main.yml` for per-host overrides.

---

## 5. Privilege Escalation

Package installation and file writes to system directories require root
privileges.  Configure `become` so that Ansible can escalate without an
interactive password prompt.

### 5.1 sudo (Linux)

Add a passwordless sudo rule for the Ansible user.  Run this on each
**managed node** as root:

```bash
# /etc/sudoers.d/ansible  — created on the managed node
echo 'ansible ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/ansible
chmod 440 /etc/sudoers.d/ansible
```

Replace `ansible` with whatever username Ansible logs in as.

> **Minimal privilege option:** Replace `ALL` with specific command paths
> if you prefer to limit what the account can do.

### 5.2 doas (Gentoo, FreeBSD, OpenBSD)

Add a `permit nopass` rule to `/etc/doas.conf` on the managed node:

```
# /etc/doas.conf
permit nopass ansible as root
```

Set the Ansible become method in `group_vars/<group>/vars.yml`:

```yaml
ansible_become_method: doas
```

### 5.3 Configure Ansible Become Variables

In `group_vars/all/vars.yml`:

```yaml
ansible_become: true
ansible_become_method: sudo    # or: doas, su, pbrun, pfexec, …
```

If passwordless escalation is not configured, pass `-K` / `--ask-become-pass`
when running playbooks:

```bash
ansible-playbook playbooks/provision_benchmarks.yml --ask-become-pass
```

---

## 6. Special Cases

### 6.1 RHEL 7 / RHEL 8 — Python Bootstrap

RHEL 7 and RHEL 8 ship Python 3.6 as the system Python, which is too old
for Ansible 2.17+.  Bootstrap a compatible interpreter **on the managed
node** before provisioning:

**RHEL 7 — Software Collections:**

```bash
subscription-manager repos --enable rhel-server-rhscl-7-rpms
yum install rh-python38
```

**RHEL 8 — AppStream:**

```bash
dnf install python38
```

Then configure the interpreter path in `host_vars/<host>/main.yml`:

```yaml
# RHEL 7
ansible_python_interpreter: /opt/rh/rh-python38/root/usr/bin/python3.8

# RHEL 8
ansible_python_interpreter: /usr/bin/python3.8
```

### 6.2 Windows Hosts

Windows hosts need remote-management enabled before Ansible can connect.
Two options are supported; **OpenSSH is recommended** for Windows 10 1809+
because it integrates with the same SSH proxy infrastructure as all other hosts.

#### Option A — OpenSSH (Recommended, Windows 10 1809+ / Server 2019+)

Run the following in an **elevated PowerShell** on each Windows host:

```powershell
# 1. Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# 2. Start and auto-start the service
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# 3. Open the firewall (usually done automatically)
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' `
    -Enabled True -Direction Inbound -Protocol TCP `
    -Action Allow -LocalPort 22

# 4. Set PowerShell as the default SSH shell for Ansible
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' `
    -Name DefaultShell `
    -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -PropertyType String -Force

# 5. Authorize the controller's public key
$authorizedKeysFile = "$env:ProgramData\ssh\administrators_authorized_keys"
Add-Content -Path $authorizedKeysFile -Value '<paste controller public key here>'
# Fix permissions (required by OpenSSH):
icacls $authorizedKeysFile /inheritance:r /grant 'SYSTEM:(F)' /grant 'ADMINISTRATORS:(F)'
```

Create a **dedicated `ansible` Windows user** with Administrator privileges
(usernames with non-ASCII characters cause SSH path problems):

```powershell
$pass = ConvertTo-SecureString "ChangeMe123!" -AsPlainText -Force
New-LocalUser "ansible" -Password $pass -FullName "Ansible" `
    -Description "Ansible automation account" -PasswordNeverExpires
Add-LocalGroupMember -Group "Administrators" -Member "ansible"
```

Configure `group_vars/mswindows/connection.yml` on the controller
(copy from `group_vars.example/mswindows/connection.yml`):

```yaml
ansible_connection: ssh
ansible_shell_type: powershell
ansible_shell_executable: powershell.exe
ansible_user: ansible
ansible_ssh_private_key_file: ~/.ssh/ansible_ed25519
```

#### Option B — WinRM (Fallback, all Windows versions)

Install the Python WinRM client on the **controller**:

```bash
pip install pywinrm
```

Run the following in an **elevated PowerShell** on each Windows host:

```powershell
# 1. Enable WinRM
winrm quickconfig -q

# 2. Allow unencrypted auth (lab environments only)
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'

# 3. Auto-start WinRM
Set-Service -Name WinRM -StartupType Automatic

# 4. Open the firewall
New-NetFirewallRule -Name 'WinRM-HTTP' -DisplayName 'WinRM HTTP' `
    -Enabled True -Direction Inbound -Protocol TCP `
    -Action Allow -LocalPort 5985
```

Configure `group_vars/mswindows/connection.yml`:

```yaml
ansible_connection: winrm
ansible_winrm_transport: ntlm
ansible_winrm_port: 5985
ansible_winrm_scheme: http
ansible_winrm_server_cert_validation: ignore
ansible_user: ansible
```

---

## 7. Verify Everything Works

### Linux / Unix hosts

```bash
# Ping all hosts
ansible all -m ping

# Show gathered facts for one host
ansible <hostname> -m ansible.builtin.gather_facts

# Check privilege escalation
ansible all -m ansible.builtin.command -a "id" --become
```

### Windows hosts

```bash
ansible mswindows -m ansible.windows.win_ping
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Permission denied (publickey)` | Key not in `authorized_keys` | Re-run `ssh-copy-id` |
| `sudo: a password is required` | Passwordless sudo not configured | Add `NOPASSWD` rule or pass `-K` |
| `Python interpreter not found` | Wrong `ansible_python_interpreter` | Set correct path in host_vars |
| `UNREACHABLE — timed out` | Firewall / wrong hostname | Check `ansible_host` and SSH port |
| `WinRM connection refused` | WinRM not enabled | Run `winrm quickconfig` on the host |

---

## Next Steps

Once all hosts are reachable and privilege escalation is working, you are
ready to use the collection:

- **Benchmark suite** → [docs/benchmarks.md](benchmarks.md)
- **Portage USE flag management** → `playbooks/collect_use_flags.yml`,
  `playbooks/apply_portage_config.yml`
- **Full playbook reference** → [README.md](../README.md#playbooks)
- **Full script reference** → [README.md](../README.md#scripts)
