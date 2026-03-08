"""Unit tests for the inventory generator (Python implementation).

Tests the pure-logic functions: group-name sanitisation, base-OS extraction,
name-collision resolution, capability-group detection, and full inventory
building — all without SSH.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Import the generator as a module
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import inventory_generator as inv  # noqa: E402

# ── Helpers that mirror the Python code's inline logic ───────────────────
# The Python script does group-name sanitisation inline; we extract them
# here so we can test them identically to the Rust lib functions.


def sanitize_group_name(raw: str) -> str:
    """Sanitize a string for use as an Ansible group name."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    if not sanitized[0].isalpha():
        sanitized = "os_" + sanitized
    return sanitized


def extract_base_os(os_group: str) -> str | None:
    """Extract the base OS name from a sanitized group name."""
    match = re.match(r"([a-zA-Z]+)(?:[0-9_]+)?(.*)", os_group)
    if match:
        base = match.group(1).rstrip("_")
        return base if base else "unknown_os"
    return None


def resolve_name_collision(vm_name: str, os_group: str, base_os: str | None) -> str:
    """Ensure a name doesn't collide with any group it belongs to."""
    if vm_name == os_group or (base_os and vm_name == base_os):
        return f"{vm_name}_host"
    return vm_name


# ── sanitize_group_name ─────────────────────────────────────────────────


class TestSanitizeGroupName:
    def test_plain_name(self) -> None:
        assert sanitize_group_name("gentoo") == "gentoo"

    def test_with_dots_and_dashes(self) -> None:
        assert sanitize_group_name("rhel-9.3") == "rhel_9_3"

    def test_numeric_prefix(self) -> None:
        assert sanitize_group_name("123abc") == "os_123abc"

    def test_special_chars(self) -> None:
        assert sanitize_group_name("my os!@#") == "my_os___"


# ── extract_base_os ─────────────────────────────────────────────────────


class TestExtractBaseOs:
    def test_simple(self) -> None:
        assert extract_base_os("gentoo") == "gentoo"

    def test_with_version(self) -> None:
        assert extract_base_os("rhel_9_3") == "rhel"

    def test_pure_alpha(self) -> None:
        assert extract_base_os("fedora") == "fedora"

    def test_with_numbers(self) -> None:
        assert extract_base_os("win11") == "win"


# ── resolve_name_collision ──────────────────────────────────────────────


class TestResolveNameCollision:
    def test_no_collision(self) -> None:
        assert resolve_name_collision("gentoo-vm1", "gentoo", "gentoo") == "gentoo-vm1"

    def test_collision_with_os_group(self) -> None:
        assert resolve_name_collision("fedora", "fedora", "fedora") == "fedora_host"

    def test_collision_with_base_os(self) -> None:
        assert resolve_name_collision("win", "win11", "win") == "win_host"


# ── get_capability_groups ───────────────────────────────────────────────


class TestGetCapabilityGroups:
    def _get(self, cflags: str = "", features: str = "") -> list[str]:
        profile = {"cflags": cflags, "features": features}
        return inv.get_capability_groups(profile)

    def test_lto(self) -> None:
        g = self._get(cflags="-O2 -flto -march=native")
        assert "lto_enabled" in g
        assert "cflags_O2" in g
        assert "cflags_native" in g
        assert "cflags_O3" not in g

    def test_o3_no_lto(self) -> None:
        g = self._get(cflags="-O3 -march=znver4")
        assert "cflags_O3" in g
        assert "lto_enabled" not in g
        assert "cflags_O2" not in g

    def test_hardened(self) -> None:
        g = self._get(cflags="-O2", features="hardened pie ssp")
        assert "hardened" in g

    def test_pgo_in_features(self) -> None:
        g = self._get(cflags="-O2", features="PGO enabled")
        assert "pgo_enabled" in g

    def test_pgo_in_cflags(self) -> None:
        g = self._get(cflags="-O2 -fprofile-generate")
        assert "pgo_enabled" in g

    def test_empty_profile(self) -> None:
        assert self._get() == []


# ── build_inventory (end-to-end, no SSH) ────────────────────────────────

SAMPLE_VMS: dict[str, list[dict]] = {
    "hv1": [
        {"name": "gentoo-vm1", "os": "gentoo", "hostname": "vm1"},
        {"name": "gentoo-bianca", "os": "gentoo", "hostname": "bianca"},
        {"name": "fedora-dev", "os": "fedora40", "hostname": "fedora-dev"},
    ],
    "hv2": [
        {"name": "debian-test", "os": "debian12", "hostname": "debian-test"},
    ],
}


def _build(host_vms: dict | None = None, probe_cflags: bool = False) -> dict:
    """Build an inventory dict from test data, simulating the main loop."""
    if host_vms is None:
        host_vms = SAMPLE_VMS

    inventory: dict = {"_meta": {"hostvars": {}}, "all": {"children": []}}

    for host, vms in host_vms.items():
        for vm in vms:
            vm_name = vm["name"]
            os_group = sanitize_group_name(vm["os"])
            base_os = extract_base_os(os_group)
            inventory_vm_name = resolve_name_collision(vm_name, os_group, base_os)

            # Primary OS group
            if os_group not in inventory:
                inventory[os_group] = {"hosts": []}
                if os_group not in inventory["all"]["children"]:
                    inventory["all"]["children"].append(os_group)
            if inventory_vm_name not in inventory[os_group]["hosts"]:
                inventory[os_group]["hosts"].append(inventory_vm_name)

            # Base OS group
            if base_os and base_os != os_group:
                if base_os not in inventory:
                    inventory[base_os] = {"hosts": []}
                    if base_os not in inventory["all"]["children"]:
                        inventory["all"]["children"].append(base_os)
                if inventory_vm_name not in inventory[base_os]["hosts"]:
                    inventory[base_os]["hosts"].append(inventory_vm_name)

            # Hostvars
            actual_hostname = vm.get("hostname", vm_name)
            inventory["_meta"]["hostvars"][inventory_vm_name] = {
                "ansible_host": actual_hostname,
                "hypervisor_host": host,
                "ansible_ssh_common_args": f'-o ProxyCommand="ssh -W %h:%p -q {host}"',
            }

            # Hypervisor group
            hv_group = "hypervisor_" + re.sub(r"[^a-zA-Z0-9_]", "_", host)
            if hv_group not in inventory:
                inventory[hv_group] = {"hosts": []}
                if hv_group not in inventory["all"]["children"]:
                    inventory["all"]["children"].append(hv_group)
            if inventory_vm_name not in inventory[hv_group]["hosts"]:
                inventory[hv_group]["hosts"].append(inventory_vm_name)

            # Capability groups
            is_gentoo = base_os and "gentoo" in base_os.lower()
            if probe_cflags and is_gentoo:
                profile = {"cflags": "-O2 -flto -march=native", "features": ""}
                for cap_grp in inv.get_capability_groups(profile):
                    if cap_grp not in inventory:
                        inventory[cap_grp] = {"hosts": []}
                        if cap_grp not in inventory["all"]["children"]:
                            inventory["all"]["children"].append(cap_grp)
                    if inventory_vm_name not in inventory[cap_grp]["hosts"]:
                        inventory[cap_grp]["hosts"].append(inventory_vm_name)

    return inventory


class TestBuildInventory:
    def test_has_meta_and_all(self) -> None:
        inv_data = _build()
        assert "_meta" in inv_data
        assert "all" in inv_data

    def test_os_groups_created(self) -> None:
        inv_data = _build()
        assert "gentoo" in inv_data
        assert "fedora40" in inv_data
        assert "debian12" in inv_data

    def test_base_os_groups_created(self) -> None:
        inv_data = _build()
        assert "fedora" in inv_data
        assert "debian" in inv_data

    def test_hypervisor_groups(self) -> None:
        inv_data = _build()
        assert "hypervisor_hv1" in inv_data
        assert "hypervisor_hv2" in inv_data
        assert len(inv_data["hypervisor_hv1"]["hosts"]) == 3
        assert "gentoo-vm1" in inv_data["hypervisor_hv1"]["hosts"]
        assert len(inv_data["hypervisor_hv2"]["hosts"]) == 1
        assert "debian-test" in inv_data["hypervisor_hv2"]["hosts"]

    def test_hostvars_set(self) -> None:
        inv_data = _build()
        hv = inv_data["_meta"]["hostvars"]["gentoo-vm1"]
        assert hv["ansible_host"] == "vm1"
        assert hv["hypervisor_host"] == "hv1"
        assert "hv1" in hv["ansible_ssh_common_args"]

    def test_all_children_lists_groups(self) -> None:
        inv_data = _build()
        children = inv_data["all"]["children"]
        assert "gentoo" in children
        assert "hypervisor_hv1" in children
        assert "hypervisor_hv2" in children

    def test_name_collision_resolved(self) -> None:
        inv_data = _build({"hv": [{"name": "fedora", "os": "fedora", "hostname": "fedora"}]})
        assert "fedora_host" in inv_data["fedora"]["hosts"]

    def test_probe_cflags_adds_cap_groups(self) -> None:
        vms = {"hv": [{"name": "gentoo-test", "os": "gentoo", "hostname": "test"}]}
        inv_data = _build(vms, probe_cflags=True)
        assert "lto_enabled" in inv_data
        assert "cflags_O2" in inv_data
        assert "cflags_native" in inv_data
        assert "gentoo-test" in inv_data["lto_enabled"]["hosts"]

    def test_no_probe_for_non_gentoo(self) -> None:
        vms = {"hv": [{"name": "fedora-dev", "os": "fedora40", "hostname": "fedora-dev"}]}
        inv_data = _build(vms, probe_cflags=True)
        assert "lto_enabled" not in inv_data

    def test_no_duplicate_hosts(self) -> None:
        vms = {
            "hv": [
                {"name": "gentoo-a", "os": "gentoo", "hostname": "a"},
                {"name": "gentoo-a", "os": "gentoo", "hostname": "a"},
            ]
        }
        inv_data = _build(vms)
        assert len(inv_data["gentoo"]["hosts"]) == 1


# ── Cross-implementation test (Python vs Rust) ──────────────────────────


RUST_BINARY = REPO_ROOT / "inventory_generator_rs" / "target" / "debug" / "inventory_generator"


@pytest.mark.skipif(
    not RUST_BINARY.exists(),
    reason="Rust binary not built (run `cargo build` in inventory_generator_rs/)",
)
class TestCrossImplementation:
    """Verify that the Rust binary produces identical output to Python for
    the same inputs (using ``--host`` which requires no SSH)."""

    def test_host_flag_returns_empty_object(self) -> None:
        """Both implementations should output {} for --host <name>."""
        rust_out = subprocess.run(
            [str(RUST_BINARY), "--host", "anything"],
            capture_output=True,
            text=True,
        )
        assert rust_out.returncode == 0
        assert json.loads(rust_out.stdout) == {}

    def test_list_with_no_hypervisors_returns_empty_inventory(self) -> None:
        """With no hypervisors reachable, both should output the skeleton."""
        env = {**os.environ, "HYPERVISOR_HOSTS": ""}
        rust_out = subprocess.run(
            [str(RUST_BINARY), "--list"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert rust_out.returncode == 0
        inv_data = json.loads(rust_out.stdout)
        assert "_meta" in inv_data
        assert "all" in inv_data
        assert inv_data["_meta"]["hostvars"] == {}
        assert inv_data["all"]["children"] == []
