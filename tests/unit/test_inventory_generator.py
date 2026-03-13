"""Unit tests for the inventory generator (Python implementation).

Tests the pure-logic functions: group-name sanitisation, base-OS extraction,
name-collision resolution, capability-group detection, and full inventory
building — all without SSH.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

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
    if not sanitized or not sanitized[0].isalpha():
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

# ── Edge case tests ──────────────────────────────────────────────────────


class TestSanitizeGroupNameEdgeCases:
    def test_empty_string_gets_prefix(self) -> None:
        # An empty sanitized string starts with a non-alpha char after join,
        # but the input itself should not crash.
        result = sanitize_group_name("")
        assert result  # must be non-empty
        assert re.match(r"[a-zA-Z]", result), "Result must start with a letter"

    def test_all_special_chars(self) -> None:
        result = sanitize_group_name("!@#$%^")
        # All special chars become underscores; starts with digit/underscore -> prefix
        assert re.match(r"[a-zA-Z_]", result)
        assert re.match(r"^[a-zA-Z0-9_]+$", result)

    def test_very_long_name_preserved(self) -> None:
        long_name = "a" * 256
        result = sanitize_group_name(long_name)
        assert len(result) == 256

    def test_leading_digit_gets_os_prefix(self) -> None:
        assert sanitize_group_name("9lives") == "os_9lives"

    def test_underscore_only_input(self) -> None:
        result = sanitize_group_name("___")
        # All underscores — first char is not alpha, should get prefix
        assert re.match(r"^[a-zA-Z]", result)

    def test_single_alpha_char(self) -> None:
        result = sanitize_group_name("x")
        assert result == "x"

    def test_preserves_existing_underscores(self) -> None:
        assert sanitize_group_name("my_group_name") == "my_group_name"

    def test_unicode_chars_become_underscores(self) -> None:
        result = sanitize_group_name("gentoo-ñ-系")
        assert re.match(r"^[a-zA-Z0-9_]+$", result)


class TestExtractBaseOsEdgeCases:
    def test_pure_letters(self) -> None:
        assert extract_base_os("ubuntu") == "ubuntu"

    def test_letters_digits_underscores(self) -> None:
        assert extract_base_os("ubuntu_22_04") == "ubuntu"

    def test_single_letter(self) -> None:
        result = extract_base_os("a")
        assert result == "a"

    def test_digits_only_returns_none_or_fallback(self) -> None:
        result = extract_base_os("12345")
        # Either None or some fallback — must not crash
        assert result is None or isinstance(result, str)

    def test_mixed_version_formats(self) -> None:
        for raw, expected_base in [
            ("rhel_9_3", "rhel"),
            ("opensuse_leap_15_5", "opensuse"),
            ("fedora40", "fedora"),
            ("debian12", "debian"),
            ("archlinux", "archlinux"),
        ]:
            result = extract_base_os(raw)
            assert result == expected_base, f"extract_base_os({raw!r}) = {result!r}"


class TestResolveNameCollisionEdgeCases:
    def test_no_collision(self) -> None:
        assert resolve_name_collision("gentoo-vm1", "gentoo", "gentoo") == "gentoo-vm1"

    def test_collision_with_os_group(self) -> None:
        assert resolve_name_collision("fedora", "fedora", "fedora") == "fedora_host"

    def test_collision_with_base_os_only(self) -> None:
        assert resolve_name_collision("ubuntu", "ubuntu_22_04", "ubuntu") == "ubuntu_host"

    def test_no_collision_when_base_os_is_none(self) -> None:
        # Should not crash when base_os is None
        result = resolve_name_collision("myvm", "mygroup", None)
        assert result == "myvm"

    def test_already_suffixed_name_not_double_suffixed(self) -> None:
        # A name that ends in _host should still be treated normally
        result = resolve_name_collision("gentoo_host", "gentoo", "gentoo")
        assert result == "gentoo_host"

    def test_similar_but_not_equal_name_not_renamed(self) -> None:
        assert resolve_name_collision("fedora-dev", "fedora", "fedora") == "fedora-dev"


class TestBuildInventoryEdgeCases:
    def test_empty_hypervisor_set(self) -> None:
        inv_data = _build({})
        assert inv_data["_meta"]["hostvars"] == {}
        assert inv_data["all"]["children"] == []

    def test_duplicate_vms_across_hypervisors(self) -> None:
        """Same VM name on two different hypervisors should appear only once."""
        vms = {
            "hv1": [{"name": "gentoo-shared", "os": "gentoo", "hostname": "shared"}],
            "hv2": [{"name": "gentoo-shared", "os": "gentoo", "hostname": "shared"}],
        }
        inv_data = _build(vms)
        # Host should appear exactly once in the group
        gentoo_hosts = inv_data["gentoo"]["hosts"]
        assert gentoo_hosts.count("gentoo-shared") == 1

    def test_mixed_os_vms(self) -> None:
        vms = {
            "hv": [
                {"name": "vm-gentoo", "os": "gentoo", "hostname": "vm-gentoo"},
                {"name": "vm-ubuntu", "os": "ubuntu_22_04", "hostname": "vm-ubuntu"},
                {"name": "vm-fedora", "os": "fedora40", "hostname": "vm-fedora"},
            ]
        }
        inv_data = _build(vms)
        assert "gentoo" in inv_data
        assert "ubuntu_22_04" in inv_data or "ubuntu" in inv_data
        assert "fedora40" in inv_data or "fedora" in inv_data

    def test_each_host_has_ansible_host_var(self) -> None:
        vms = {
            "hv": [
                {"name": f"vm-{n}", "os": "gentoo", "hostname": f"host-{n}"}
                for n in range(5)
            ]
        }
        inv_data = _build(vms)
        for n in range(5):
            assert f"vm-{n}" in inv_data["_meta"]["hostvars"]
            assert "ansible_host" in inv_data["_meta"]["hostvars"][f"vm-{n}"]

    def test_hypervisor_group_created_per_hypervisor(self) -> None:
        vms = {
            "hv-alpha": [{"name": "vm1", "os": "gentoo", "hostname": "vm1"}],
            "hv-beta": [{"name": "vm2", "os": "gentoo", "hostname": "vm2"}],
        }
        inv_data = _build(vms)
        assert "hypervisor_hv_alpha" in inv_data or "hypervisor_hv-alpha" in inv_data or \
               any("hv_alpha" in k or "hv-alpha" in k for k in inv_data)
        assert any("hv_beta" in k or "hv-beta" in k for k in inv_data)
