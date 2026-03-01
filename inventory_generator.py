#!/usr/bin/env python3
"""Dynamic Ansible inventory generator.

Connects to one or more KVM/QEMU hypervisors via SSH, enumerates all libvirt
domains, detects their OS (via QEMU guest agent or XML metadata), and emits a
JSON inventory compatible with ``ansible-inventory --list``.

Usage::

    ansible-playbook site.yml -i inventory_generator.py
    ansible-inventory -i inventory_generator.py --list
    ansible-inventory -i inventory_generator.py --list --probe-cflags
"""
import argparse
import concurrent.futures
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Capability groups derived from Gentoo build-profile variables
# ---------------------------------------------------------------------------
# Mapping: group name → callable(cflags, features) → bool
_CAPABILITY_GROUPS = {
    "lto_enabled": lambda cf, ft: "-flto" in cf,
    "pgo_enabled": lambda cf, ft: "-fprofile" in cf or "pgo" in ft.lower(),
    "hardened": lambda cf, ft: any(
        kw in ft.lower() for kw in ("hardened", "pie", "ssp", "stack-clash-protection")
    ),
    "cflags_O3": lambda cf, ft: "-O3" in cf.split(),
    "cflags_O2": lambda cf, ft: "-O2" in cf.split() and "-O3" not in cf.split(),
    "cflags_native": lambda cf, ft: "-march=native" in cf,
}

# Ansible-style SSH connection multiplexing for performance improvement
SSH_OPTIONS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPath=/tmp/ansible-ssh-%u-%r@%h:%p",
    "-o",
    "ControlPersist=60",
]


def get_vms_from_host(host):
    """Connect via SSH and list libvirt VMs, reading their OS type if available."""
    try:
        # Get list of running + shutdown domains
        result = subprocess.run(
            ["ssh"]
            + SSH_OPTIONS
            + [host, "virsh", "--connect", "qemu:///system", "list", "--all", "--name"],
            capture_output=True,
            text=True,
            check=True,
        )
        vms = [v.strip() for v in result.stdout.strip().split("\n") if v.strip()]

        inventory_items = []
        for vm in vms:
            os_name = "unknown_os"

            # 1. Try QEMU guest agent for the most accurate OS detection
            agent_cmd = f'virsh --connect qemu:///system qemu-agent-command {shlex.quote(vm)} \'{{"execute": "guest-get-osinfo"}}\''
            agent_result = subprocess.run(
                ["ssh"] + SSH_OPTIONS + [host, agent_cmd],
                capture_output=True,
                text=True,
            )

            if agent_result.returncode == 0:
                try:
                    agent_info = json.loads(agent_result.stdout)
                    if "return" in agent_info and "id" in agent_info["return"]:
                        os_name = agent_info["return"]["id"]
                except json.JSONDecodeError:
                    pass

            # 2. Fallback to XML Metadata
            if os_name == "unknown_os":
                xml_cmd = f"virsh --connect qemu:///system dumpxml {shlex.quote(vm)}"
                xml_result = subprocess.run(
                    ["ssh"] + SSH_OPTIONS + [host, xml_cmd],
                    capture_output=True,
                    text=True,
                )
                if xml_result.returncode == 0:
                    try:
                        root = ET.fromstring(xml_result.stdout)

                        # Try to extract the OS from libosinfo metadata
                        ns = {
                            "libosinfo": "http://libosinfo.org/xmlns/libvirt/domain/1.0"
                        }
                        elem = root.find(".//libosinfo:short-id", ns)
                        if elem is not None and elem.text:
                            os_name = elem.text
                        else:
                            # Fallback metadata check or title
                            title = root.find("./title")
                            if title is not None and title.text and title.text.strip():
                                os_name = title.text.strip().replace(" ", "_").lower()
                    except ET.ParseError:
                        pass

            # 3. Fallback to VM name prefix parsing (e.g. gentoo-vm1 -> gentoo)
            if os_name == "unknown_os" and "-" in vm:
                # Many hosts are named os-hostname, we assume the first part might be the OS
                os_name = vm.split("-")[0].lower()

            # 4. Try to get the actual hostname from the QEMU guest agent
            actual_hostname = vm  # default: fall back to libvirt VM name
            hostname_cmd = f'virsh --connect qemu:///system qemu-agent-command {shlex.quote(vm)} \'{{"execute":"guest-get-host-name"}}\''
            hostname_result = subprocess.run(
                ["ssh"] + SSH_OPTIONS + [host, hostname_cmd],
                capture_output=True,
                text=True,
            )
            if hostname_result.returncode == 0:
                try:
                    hostname_info = json.loads(hostname_result.stdout)
                    if "return" in hostname_info and "host-name" in hostname_info["return"]:
                        actual_hostname = hostname_info["return"]["host-name"].strip().split(".")[0]
                except json.JSONDecodeError:
                    pass

            inventory_items.append({"name": vm, "os": os_name, "hostname": actual_hostname})
        return inventory_items
    except subprocess.CalledProcessError as e:
        print(f"Error querying host {host}: {e.stderr}", file=sys.stderr)
        return []


def probe_build_profile(host: str, vm: str) -> dict:
    """SSH into a VM (via hypervisor proxy) and extract CFLAGS/FEATURES.

    Returns a dict with keys 'cflags' and 'features' (both strings).
    Returns empty strings on failure (probe is best-effort).
    """
    proxy_opts = ["-o", f"ProxyCommand=ssh -W %h:%p -q {host}"]
    cmd = "grep -E '^(CFLAGS|FEATURES)=' /etc/portage/make.conf 2>/dev/null || true"
    try:
        result = subprocess.run(
            ["ssh"] + SSH_OPTIONS + proxy_opts + [vm, cmd],
            capture_output=True,
            text=True,
            timeout=10,
        )
        cflags = ""
        features = ""
        for line in result.stdout.splitlines():
            m = re.match(r'^CFLAGS=["\']?([^"\'\n]+)["\']?', line)
            if m:
                cflags = m.group(1).strip()
            m = re.match(r'^FEATURES=["\']?([^"\'\n]+)["\']?', line)
            if m:
                features = m.group(1).strip()
        return {"cflags": cflags, "features": features}
    except Exception as exc:
        print(f"WARNING: probe_build_profile({host!r}, {vm!r}) failed: {exc}", file=sys.stderr)
        return {"cflags": "", "features": ""}


def get_capability_groups(build_profile: dict) -> list:
    """Return list of capability group names that match the build profile."""
    cflags = build_profile.get("cflags", "")
    features = build_profile.get("features", "")
    return [grp for grp, check in _CAPABILITY_GROUPS.items() if check(cflags, features)]


def main():
    parser = argparse.ArgumentParser(
        description="Generate Ansible inventory from hypervisor VMs via SSH"
    )
    parser.add_argument(
        "--hosts", nargs="+", help="List of hypervisor hosts", required=False
    )
    parser.add_argument(
        "--list", action="store_true", help="Ansible dynamic inventory --list flag"
    )
    parser.add_argument("--host", help="Ansible dynamic inventory --host flag")
    parser.add_argument(
        "--probe-cflags",
        action="store_true",
        default=False,
        help=(
            "SSH into each Gentoo VM to read CFLAGS/FEATURES and assign "
            "capability groups (lto_enabled, hardened, cflags_O3, …). "
            "Adds one extra SSH connection per Gentoo VM."
        ),
    )

    args = parser.parse_args()

    inventory = {"_meta": {"hostvars": {}}, "all": {"children": []}}

    hosts_list = []

    if args.list:
        # Default fallback hosts or read from an environment variable or file
        env_hosts = os.environ.get("HYPERVISOR_HOSTS")
        if env_hosts:
            hosts_list = [h.strip() for h in env_hosts.split(",") if h.strip()]
        elif args.hosts:
            hosts_list = args.hosts
        else:
            try:
                with open(Path(__file__).parent / "hypervisors.txt") as f:
                    hosts_list = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                hosts_list = []

        # Dictionary to hold the future to host mapping
        future_to_host = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(10, len(hosts_list) if hosts_list else 1)
        ) as executor:
            for host in hosts_list:
                future = executor.submit(get_vms_from_host, host)
                future_to_host[future] = host

            for future in concurrent.futures.as_completed(future_to_host):
                host = future_to_host[future]
                try:
                    vms = future.result()
                    for vm in vms:
                        vm_name = vm["name"]
                        os_group = vm["os"]

                        # Sanitize os_group for Ansible (must start with letter, only contain letters, numbers, and underscores)
                        os_group = re.sub(r"[^a-zA-Z0-9_]", "_", os_group)
                        if not os_group[0].isalpha():
                            os_group = "os_" + os_group

                        # Base OS logic
                        match = re.match(r"([a-zA-Z]+)(?:[0-9_]+)?(.*)", os_group)
                        base_os = None
                        if match:
                            base_os = match.group(1).rstrip("_")
                            if not base_os:
                                base_os = "unknown_os"

                        # Prevent group and host name collisions (e.g. host win11 and group win11)
                        inventory_vm_name = vm_name
                        if (
                            inventory_vm_name == os_group
                            or inventory_vm_name == base_os
                        ):
                            # To avoid naming collisions in the dynamic inventory
                            inventory_vm_name = f"{vm_name}_host"

                        # Add to primary OS group
                        if os_group not in inventory:
                            inventory[os_group] = {"hosts": []}
                            if os_group not in inventory["all"]["children"]:
                                inventory["all"]["children"].append(os_group)

                        if inventory_vm_name not in inventory[os_group]["hosts"]:
                            inventory[os_group]["hosts"].append(inventory_vm_name)

                        # Add to base OS group
                        if base_os and base_os != os_group:
                            if base_os not in inventory:
                                inventory[base_os] = {"hosts": []}
                                if base_os not in inventory["all"]["children"]:
                                    inventory["all"]["children"].append(base_os)

                            if inventory_vm_name not in inventory[base_os]["hosts"]:
                                inventory[base_os]["hosts"].append(inventory_vm_name)

                        # Use the actual hostname reported by the VM (via QEMU guest agent)
                        # for ansible_host and the ProxyCommand target, so Ansible connects
                        # by the machine's real hostname rather than the libvirt domain name.
                        # Falls back to the libvirt VM name if the guest agent was unavailable.
                        actual_hostname = vm.get("hostname", vm_name)
                        hostvars = {
                            "ansible_host": actual_hostname,
                            "hypervisor_host": host,
                            "ansible_ssh_common_args": f'-o ProxyCommand="ssh -W %h:%p -q {host}"',
                        }
                        inventory["_meta"]["hostvars"][inventory_vm_name] = hostvars

                        # Add to hypervisor group (e.g. hypervisor_hv1)
                        hv_group = "hypervisor_" + re.sub(r"[^a-zA-Z0-9_]", "_", host)
                        if hv_group not in inventory:
                            inventory[hv_group] = {"hosts": []}
                            if hv_group not in inventory["all"]["children"]:
                                inventory["all"]["children"].append(hv_group)
                        if inventory_vm_name not in inventory[hv_group]["hosts"]:
                            inventory[hv_group]["hosts"].append(inventory_vm_name)

                        # Optional capability group probe (Gentoo only)
                        is_gentoo = base_os and "gentoo" in base_os.lower()
                        if args.probe_cflags and is_gentoo:
                            build_profile = probe_build_profile(host, vm_name)
                            cap_groups = get_capability_groups(build_profile)
                            for cap_grp in cap_groups:
                                if cap_grp not in inventory:
                                    inventory[cap_grp] = {"hosts": []}
                                    if cap_grp not in inventory["all"]["children"]:
                                        inventory["all"]["children"].append(cap_grp)
                                if inventory_vm_name not in inventory[cap_grp]["hosts"]:
                                    inventory[cap_grp]["hosts"].append(
                                        inventory_vm_name
                                    )

                except Exception as exc:
                    print(f"Host {host} generated an exception: {exc}", file=sys.stderr)

        print(json.dumps(inventory, indent=2))
        sys.exit(0)

    elif args.host:
        # Required for dynamic inventory script --host <hostname> fallback
        print(json.dumps({}))
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
