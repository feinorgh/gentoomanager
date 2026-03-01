//! Core inventory generation logic.
//!
//! Pure functions are exposed for unit testing.  The SSH / subprocess layer is
//! kept separate so tests can exercise the inventory-building logic without
//! network access.

use quick_xml::events::Event;
use quick_xml::Reader;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::io::BufRead;
use std::process::Command;

// ── SSH helpers ─────────────────────────────────────────────────────────

pub const SSH_OPTIONS: &[&str] = &[
    "-o",
    "BatchMode=yes",
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPath=/tmp/ansible-ssh-%u-%r@%h:%p",
    "-o",
    "ControlPersist=60",
];

fn ssh_run(host: &str, remote_args: &[&str]) -> Option<String> {
    let mut cmd = Command::new("ssh");
    for opt in SSH_OPTIONS {
        cmd.arg(opt);
    }
    cmd.arg(host);
    for a in remote_args {
        cmd.arg(a);
    }
    let output = cmd.output().ok()?;
    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).into_owned())
    } else {
        None
    }
}

fn ssh_run_unchecked(host: &str, remote_cmd: &str) -> (bool, String) {
    let mut cmd = Command::new("ssh");
    for opt in SSH_OPTIONS {
        cmd.arg(opt);
    }
    cmd.arg(host).arg(remote_cmd);
    match cmd.output() {
        Ok(o) => (
            o.status.success(),
            String::from_utf8_lossy(&o.stdout).into_owned(),
        ),
        Err(_) => (false, String::new()),
    }
}

// ── Data types ──────────────────────────────────────────────────────────

/// A VM discovered on a hypervisor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VmInfo {
    pub name: String,
    pub os: String,
    pub hostname: String,
}

/// Build-profile data probed from a Gentoo VM.
#[derive(Debug, Clone, Default)]
pub struct BuildProfile {
    pub cflags: String,
    pub features: String,
}

// ── SSH interaction (side-effectful) ────────────────────────────────────

/// Shell-quote a string for use in a remote command.
fn shell_quote(s: &str) -> String {
    if s.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' || c == '/')
    {
        s.to_string()
    } else {
        format!("'{}'", s.replace('\'', "'\"'\"'"))
    }
}

/// Detect the OS from a libvirt XML dump by searching for the libosinfo
/// `short-id` element, then falling back to `<title>`.
pub fn detect_os_from_xml(xml: &str) -> Option<String> {
    // Look for <ns:short-id>...</ns:short-id> inside libosinfo metadata.
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut inside_short_id = false;
    let mut inside_title = false;
    let mut short_id: Option<String> = None;
    let mut title: Option<String> = None;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) => {
                let local = e.local_name();
                if local.as_ref() == b"short-id" {
                    inside_short_id = true;
                } else if local.as_ref() == b"title" {
                    inside_title = true;
                }
            }
            Ok(Event::Text(e)) => {
                if inside_short_id {
                    let t = e.unescape().unwrap_or_default().to_string();
                    if !t.is_empty() {
                        short_id = Some(t);
                    }
                    inside_short_id = false;
                }
                if inside_title {
                    let t = e.unescape().unwrap_or_default().trim().to_string();
                    if !t.is_empty() {
                        title = Some(t.replace(' ', "_").to_lowercase());
                    }
                    inside_title = false;
                }
            }
            Ok(Event::End(_)) => {
                inside_short_id = false;
                inside_title = false;
            }
            Ok(Event::Eof) => break,
            Err(_) => break,
            _ => {}
        }
        buf.clear();
    }

    short_id.or(title)
}

/// Connect to a hypervisor via SSH and enumerate its libvirt VMs.
pub fn get_vms_from_host(host: &str) -> Vec<VmInfo> {
    let stdout = match ssh_run(
        host,
        &[
            "virsh",
            "--connect",
            "qemu:///system",
            "list",
            "--all",
            "--name",
        ],
    ) {
        Some(s) => s,
        None => {
            eprintln!("Error querying host {host}");
            return Vec::new();
        }
    };

    let vms: Vec<&str> = stdout.lines().map(|l| l.trim()).filter(|l| !l.is_empty()).collect();
    let mut items = Vec::with_capacity(vms.len());

    for vm in vms {
        let quoted = shell_quote(vm);
        let mut os_name = String::from("unknown_os");

        // 1. QEMU guest agent – OS info
        let agent_cmd = format!(
            "virsh --connect qemu:///system qemu-agent-command {} '{{\"execute\": \"guest-get-osinfo\"}}'",
            quoted
        );
        let (ok, agent_out) = ssh_run_unchecked(host, &agent_cmd);
        if ok {
            if let Ok(v) = serde_json::from_str::<Value>(&agent_out) {
                if let Some(id) = v.get("return").and_then(|r| r.get("id")).and_then(|i| i.as_str())
                {
                    os_name = id.to_string();
                }
            }
        }

        // 2. Fallback: XML metadata
        if os_name == "unknown_os" {
            let xml_cmd = format!(
                "virsh --connect qemu:///system dumpxml {}",
                quoted
            );
            let (ok2, xml_out) = ssh_run_unchecked(host, &xml_cmd);
            if ok2 {
                if let Some(detected) = detect_os_from_xml(&xml_out) {
                    os_name = detected;
                }
            }
        }

        // 3. Fallback: VM name prefix
        if os_name == "unknown_os" {
            if let Some(prefix) = vm.split('-').next() {
                if vm.contains('-') {
                    os_name = prefix.to_lowercase();
                }
            }
        }

        // 4. Actual hostname from guest agent
        let mut actual_hostname = vm.to_string();
        let hn_cmd = format!(
            "virsh --connect qemu:///system qemu-agent-command {} '{{\"execute\":\"guest-get-host-name\"}}'",
            quoted
        );
        let (ok3, hn_out) = ssh_run_unchecked(host, &hn_cmd);
        if ok3 {
            if let Ok(v) = serde_json::from_str::<Value>(&hn_out) {
                if let Some(hn) = v
                    .get("return")
                    .and_then(|r| r.get("host-name"))
                    .and_then(|h| h.as_str())
                {
                    actual_hostname = hn.trim().split('.').next().unwrap_or(hn.trim()).to_string();
                }
            }
        }

        items.push(VmInfo {
            name: vm.to_string(),
            os: os_name,
            hostname: actual_hostname,
        });
    }

    items
}

/// Probe CFLAGS and FEATURES from a Gentoo VM via SSH proxy.
pub fn probe_build_profile(host: &str, vm: &str) -> BuildProfile {
    let proxy = format!("ProxyCommand=ssh -W %h:%p -q {host}");
    let cmd_str = "grep -E '^(CFLAGS|FEATURES)=' /etc/portage/make.conf 2>/dev/null || true";
    let mut cmd = Command::new("ssh");
    for opt in SSH_OPTIONS {
        cmd.arg(opt);
    }
    cmd.arg("-o").arg(&proxy).arg(vm).arg(cmd_str);

    let output = match cmd.output() {
        Ok(o) => String::from_utf8_lossy(&o.stdout).into_owned(),
        Err(e) => {
            eprintln!("WARNING: probe_build_profile({host:?}, {vm:?}) failed: {e}");
            return BuildProfile::default();
        }
    };

    let cflags_re = Regex::new(r#"^CFLAGS=["']?([^"'\n]+)["']?"#).unwrap();
    let features_re = Regex::new(r#"^FEATURES=["']?([^"'\n]+)["']?"#).unwrap();
    let mut profile = BuildProfile::default();

    for line in output.lines() {
        if let Some(m) = cflags_re.captures(line) {
            profile.cflags = m[1].trim().to_string();
        }
        if let Some(m) = features_re.captures(line) {
            profile.features = m[1].trim().to_string();
        }
    }
    profile
}

// ── Pure logic (unit-testable) ──────────────────────────────────────────

/// Sanitize a string for use as an Ansible group name.
pub fn sanitize_group_name(raw: &str) -> String {
    let re = Regex::new(r"[^a-zA-Z0-9_]").unwrap();
    let sanitized = re.replace_all(raw, "_").to_string();
    if sanitized.chars().next().map_or(true, |c| !c.is_ascii_alphabetic()) {
        format!("os_{sanitized}")
    } else {
        sanitized
    }
}

/// Extract the base OS name from a sanitized group name.
///
/// Matches the leading alphabetic run, strips trailing underscores.
/// Returns `None` only when the result would be empty.
pub fn extract_base_os(os_group: &str) -> Option<String> {
    let re = Regex::new(r"^([a-zA-Z]+)(?:[0-9_]+)?(.*)").unwrap();
    re.captures(os_group).and_then(|caps| {
        let base = caps[1].trim_end_matches('_').to_string();
        if base.is_empty() {
            Some("unknown_os".to_string())
        } else {
            Some(base)
        }
    })
}

/// Return capability group names that match the build profile.
pub fn get_capability_groups(profile: &BuildProfile) -> Vec<String> {
    let cflags = &profile.cflags;
    let features = &profile.features;
    let features_lower = features.to_lowercase();

    let cflags_words: Vec<&str> = cflags.split_whitespace().collect();

    let mut groups = Vec::new();

    if cflags.contains("-flto") {
        groups.push("lto_enabled".to_string());
    }
    if cflags.contains("-fprofile") || features_lower.contains("pgo") {
        groups.push("pgo_enabled".to_string());
    }
    if ["hardened", "pie", "ssp", "stack-clash-protection"]
        .iter()
        .any(|kw| features_lower.contains(kw))
    {
        groups.push("hardened".to_string());
    }
    if cflags_words.contains(&"-O3") {
        groups.push("cflags_O3".to_string());
    }
    if cflags_words.contains(&"-O2") && !cflags_words.contains(&"-O3") {
        groups.push("cflags_O2".to_string());
    }
    if cflags.contains("-march=native") {
        groups.push("cflags_native".to_string());
    }

    groups
}

/// Ensure a name doesn't collide with any group it belongs to.
pub fn resolve_name_collision(vm_name: &str, os_group: &str, base_os: Option<&str>) -> String {
    if vm_name == os_group || base_os.map_or(false, |b| vm_name == b) {
        format!("{vm_name}_host")
    } else {
        vm_name.to_string()
    }
}

// ── Inventory builder ───────────────────────────────────────────────────

/// Helper: ensure a group exists in the inventory and is listed as a child
/// of `all`.
fn ensure_group(inventory: &mut Map<String, Value>, group: &str) {
    if !inventory.contains_key(group) {
        inventory.insert(group.to_string(), json!({"hosts": []}));
        if let Some(Value::Object(all)) = inventory.get_mut("all") {
            if let Some(Value::Array(children)) = all.get_mut("children") {
                let gv = Value::String(group.to_string());
                if !children.contains(&gv) {
                    children.push(gv);
                }
            }
        }
    }
}

/// Helper: add a host to a group's host list (deduplicating).
fn add_host_to_group(inventory: &mut Map<String, Value>, group: &str, host: &str) {
    if let Some(Value::Object(g)) = inventory.get_mut(group) {
        if let Some(Value::Array(hosts)) = g.get_mut("hosts") {
            let hv = Value::String(host.to_string());
            if !hosts.contains(&hv) {
                hosts.push(hv);
            }
        }
    }
}

/// Build an Ansible inventory JSON from a list of (hypervisor, vms) pairs.
///
/// `probe_fn` is called for Gentoo VMs when `probe_cflags` is true; pass
/// `None` to skip probing (or in tests).
pub fn build_inventory(
    host_vms: &[(String, Vec<VmInfo>)],
    probe_cflags: bool,
    probe_fn: Option<&dyn Fn(&str, &str) -> BuildProfile>,
) -> Value {
    let mut inventory: Map<String, Value> = Map::new();
    inventory.insert("_meta".to_string(), json!({"hostvars": {}}));
    inventory.insert("all".to_string(), json!({"children": []}));

    for (host, vms) in host_vms {
        for vm in vms {
            let os_group = sanitize_group_name(&vm.os);
            let base_os = extract_base_os(&os_group);
            let inventory_vm_name =
                resolve_name_collision(&vm.name, &os_group, base_os.as_deref());

            // Primary OS group
            ensure_group(&mut inventory, &os_group);
            add_host_to_group(&mut inventory, &os_group, &inventory_vm_name);

            // Base OS group
            if let Some(ref bos) = base_os {
                if bos != &os_group {
                    ensure_group(&mut inventory, bos);
                    add_host_to_group(&mut inventory, bos, &inventory_vm_name);
                }
            }

            // Hostvars
            let hostvars_entry = json!({
                "ansible_host": vm.hostname,
                "hypervisor_host": host,
                "ansible_ssh_common_args": format!("-o ProxyCommand=\"ssh -W %h:%p -q {host}\""),
            });
            if let Some(Value::Object(meta)) = inventory.get_mut("_meta") {
                if let Some(Value::Object(hv)) = meta.get_mut("hostvars") {
                    hv.insert(inventory_vm_name.clone(), hostvars_entry);
                }
            }

            // Hypervisor group
            let hv_group = format!(
                "hypervisor_{}",
                sanitize_group_name(host)
            );
            ensure_group(&mut inventory, &hv_group);
            add_host_to_group(&mut inventory, &hv_group, &inventory_vm_name);

            // Capability groups (Gentoo only)
            let is_gentoo = base_os.as_deref().map_or(false, |b| b.to_lowercase().contains("gentoo"));
            if probe_cflags && is_gentoo {
                if let Some(pfn) = probe_fn {
                    let profile = pfn(host, &vm.name);
                    for cap_grp in get_capability_groups(&profile) {
                        ensure_group(&mut inventory, &cap_grp);
                        add_host_to_group(&mut inventory, &cap_grp, &inventory_vm_name);
                    }
                }
            }
        }
    }

    Value::Object(inventory)
}

// ── Read hypervisors.txt ────────────────────────────────────────────────

pub fn read_hypervisors_file(path: &std::path::Path) -> Vec<String> {
    match std::fs::File::open(path) {
        Ok(f) => std::io::BufReader::new(f)
            .lines()
            .map_while(Result::ok)
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect(),
        Err(_) => Vec::new(),
    }
}

// ── Tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // -- sanitize_group_name --

    #[test]
    fn sanitize_plain_name() {
        assert_eq!(sanitize_group_name("gentoo"), "gentoo");
    }

    #[test]
    fn sanitize_with_dots_and_dashes() {
        assert_eq!(sanitize_group_name("rhel-9.3"), "rhel_9_3");
    }

    #[test]
    fn sanitize_numeric_prefix() {
        assert_eq!(sanitize_group_name("123abc"), "os_123abc");
    }

    #[test]
    fn sanitize_special_chars() {
        assert_eq!(sanitize_group_name("my os!@#"), "my_os___");
    }

    // -- extract_base_os --

    #[test]
    fn base_os_simple() {
        assert_eq!(extract_base_os("gentoo"), Some("gentoo".to_string()));
    }

    #[test]
    fn base_os_with_version() {
        assert_eq!(extract_base_os("rhel_9_3"), Some("rhel".to_string()));
    }

    #[test]
    fn base_os_pure_alpha() {
        assert_eq!(extract_base_os("fedora"), Some("fedora".to_string()));
    }

    #[test]
    fn base_os_with_numbers() {
        assert_eq!(extract_base_os("win11"), Some("win".to_string()));
    }

    // -- resolve_name_collision --

    #[test]
    fn no_collision() {
        assert_eq!(
            resolve_name_collision("gentoo-vm1", "gentoo", Some("gentoo")),
            "gentoo-vm1"
        );
    }

    #[test]
    fn collision_with_os_group() {
        assert_eq!(
            resolve_name_collision("fedora", "fedora", Some("fedora")),
            "fedora_host"
        );
    }

    #[test]
    fn collision_with_base_os() {
        assert_eq!(
            resolve_name_collision("win", "win11", Some("win")),
            "win_host"
        );
    }

    // -- get_capability_groups --

    #[test]
    fn caps_lto() {
        let p = BuildProfile {
            cflags: "-O2 -flto -march=native".into(),
            features: String::new(),
        };
        let g = get_capability_groups(&p);
        assert!(g.contains(&"lto_enabled".to_string()));
        assert!(g.contains(&"cflags_O2".to_string()));
        assert!(g.contains(&"cflags_native".to_string()));
        assert!(!g.contains(&"cflags_O3".to_string()));
    }

    #[test]
    fn caps_o3_no_lto() {
        let p = BuildProfile {
            cflags: "-O3 -march=znver4".into(),
            features: String::new(),
        };
        let g = get_capability_groups(&p);
        assert!(g.contains(&"cflags_O3".to_string()));
        assert!(!g.contains(&"lto_enabled".to_string()));
        assert!(!g.contains(&"cflags_O2".to_string()));
    }

    #[test]
    fn caps_hardened() {
        let p = BuildProfile {
            cflags: "-O2".into(),
            features: "hardened pie ssp".into(),
        };
        let g = get_capability_groups(&p);
        assert!(g.contains(&"hardened".to_string()));
    }

    #[test]
    fn caps_pgo_in_features() {
        let p = BuildProfile {
            cflags: "-O2".into(),
            features: "PGO enabled".into(),
        };
        let g = get_capability_groups(&p);
        assert!(g.contains(&"pgo_enabled".to_string()));
    }

    #[test]
    fn caps_pgo_in_cflags() {
        let p = BuildProfile {
            cflags: "-O2 -fprofile-generate".into(),
            features: String::new(),
        };
        let g = get_capability_groups(&p);
        assert!(g.contains(&"pgo_enabled".to_string()));
    }

    #[test]
    fn caps_empty_profile() {
        let p = BuildProfile::default();
        assert!(get_capability_groups(&p).is_empty());
    }

    // -- detect_os_from_xml --

    #[test]
    fn xml_with_short_id() {
        let xml = r#"<domain type='kvm'>
          <metadata>
            <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
              <libosinfo:os id="http://gentoo.org/gentoo/rolling"/>
              <libosinfo:short-id>gentoo</libosinfo:short-id>
            </libosinfo:libosinfo>
          </metadata>
        </domain>"#;
        assert_eq!(detect_os_from_xml(xml), Some("gentoo".to_string()));
    }

    #[test]
    fn xml_with_title_fallback() {
        let xml = r#"<domain type='kvm'>
          <title>My Custom OS</title>
        </domain>"#;
        assert_eq!(
            detect_os_from_xml(xml),
            Some("my_custom_os".to_string())
        );
    }

    #[test]
    fn xml_no_os_info() {
        let xml = r#"<domain type='kvm'><name>test</name></domain>"#;
        assert_eq!(detect_os_from_xml(xml), None);
    }

    #[test]
    fn xml_short_id_takes_priority_over_title() {
        let xml = r#"<domain type='kvm'>
          <title>Wrong Name</title>
          <metadata>
            <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
              <libosinfo:short-id>fedora40</libosinfo:short-id>
            </libosinfo:libosinfo>
          </metadata>
        </domain>"#;
        assert_eq!(detect_os_from_xml(xml), Some("fedora40".to_string()));
    }

    // -- build_inventory --

    fn sample_vms() -> Vec<(String, Vec<VmInfo>)> {
        vec![
            (
                "hv1".to_string(),
                vec![
                    VmInfo {
                        name: "gentoo-vm1".into(),
                        os: "gentoo".into(),
                        hostname: "vm1".into(),
                    },
                    VmInfo {
                        name: "gentoo-bianca".into(),
                        os: "gentoo".into(),
                        hostname: "bianca".into(),
                    },
                    VmInfo {
                        name: "fedora-dev".into(),
                        os: "fedora40".into(),
                        hostname: "fedora-dev".into(),
                    },
                ],
            ),
            (
                "hv2".to_string(),
                vec![VmInfo {
                    name: "debian-test".into(),
                    os: "debian12".into(),
                    hostname: "debian-test".into(),
                }],
            ),
        ]
    }

    #[test]
    fn inventory_has_meta_and_all() {
        let inv = build_inventory(&sample_vms(), false, None);
        assert!(inv.get("_meta").is_some());
        assert!(inv.get("all").is_some());
    }

    #[test]
    fn inventory_os_groups_created() {
        let inv = build_inventory(&sample_vms(), false, None);
        assert!(inv.get("gentoo").is_some());
        assert!(inv.get("fedora40").is_some());
        assert!(inv.get("debian12").is_some());
    }

    #[test]
    fn inventory_base_os_groups_created() {
        let inv = build_inventory(&sample_vms(), false, None);
        // fedora40 → base "fedora", debian12 → base "debian"
        assert!(inv.get("fedora").is_some());
        assert!(inv.get("debian").is_some());
    }

    #[test]
    fn inventory_hypervisor_groups() {
        let inv = build_inventory(&sample_vms(), false, None);
        assert!(inv.get("hypervisor_hv1").is_some());
        assert!(inv.get("hypervisor_hv2").is_some());

        let hv1_hosts = inv["hypervisor_hv1"]["hosts"]
            .as_array()
            .unwrap();
        assert_eq!(hv1_hosts.len(), 3);
        assert!(hv1_hosts.contains(&json!("gentoo-vm1")));

        let hv2_hosts = inv["hypervisor_hv2"]["hosts"]
            .as_array()
            .unwrap();
        assert_eq!(hv2_hosts.len(), 1);
        assert!(hv2_hosts.contains(&json!("debian-test")));
    }

    #[test]
    fn inventory_hostvars_set() {
        let inv = build_inventory(&sample_vms(), false, None);
        let hv = &inv["_meta"]["hostvars"]["gentoo-vm1"];
        assert_eq!(hv["ansible_host"], "vm1");
        assert_eq!(hv["hypervisor_host"], "hv1");
        assert!(hv["ansible_ssh_common_args"]
            .as_str()
            .unwrap()
            .contains("hv1"));
    }

    #[test]
    fn inventory_all_children_lists_groups() {
        let inv = build_inventory(&sample_vms(), false, None);
        let children = inv["all"]["children"].as_array().unwrap();
        assert!(children.contains(&json!("gentoo")));
        assert!(children.contains(&json!("hypervisor_hv1")));
        assert!(children.contains(&json!("hypervisor_hv2")));
    }

    #[test]
    fn inventory_name_collision_resolved() {
        let vms = vec![(
            "hv".to_string(),
            vec![VmInfo {
                name: "fedora".into(),
                os: "fedora".into(),
                hostname: "fedora".into(),
            }],
        )];
        let inv = build_inventory(&vms, false, None);
        // The host should be renamed to avoid collision with the group
        let hosts = inv["fedora"]["hosts"].as_array().unwrap();
        assert!(hosts.contains(&json!("fedora_host")));
    }

    #[test]
    fn inventory_probe_cflags_adds_cap_groups() {
        let vms = vec![(
            "hv".to_string(),
            vec![VmInfo {
                name: "gentoo-test".into(),
                os: "gentoo".into(),
                hostname: "test".into(),
            }],
        )];
        let probe = |_host: &str, _vm: &str| -> BuildProfile {
            BuildProfile {
                cflags: "-O2 -flto -march=native".into(),
                features: String::new(),
            }
        };
        let inv = build_inventory(&vms, true, Some(&probe));
        assert!(inv.get("lto_enabled").is_some());
        assert!(inv.get("cflags_O2").is_some());
        assert!(inv.get("cflags_native").is_some());
        let lto_hosts = inv["lto_enabled"]["hosts"].as_array().unwrap();
        assert!(lto_hosts.contains(&json!("gentoo-test")));
    }

    #[test]
    fn inventory_no_probe_for_non_gentoo() {
        let vms = vec![(
            "hv".to_string(),
            vec![VmInfo {
                name: "fedora-dev".into(),
                os: "fedora40".into(),
                hostname: "fedora-dev".into(),
            }],
        )];
        let probe = |_: &str, _: &str| -> BuildProfile {
            panic!("should not be called for non-Gentoo");
        };
        let inv = build_inventory(&vms, true, Some(&probe));
        // No capability groups should exist
        assert!(inv.get("lto_enabled").is_none());
    }

    #[test]
    fn inventory_no_duplicate_hosts() {
        let vms = vec![(
            "hv".to_string(),
            vec![
                VmInfo {
                    name: "gentoo-a".into(),
                    os: "gentoo".into(),
                    hostname: "a".into(),
                },
                VmInfo {
                    name: "gentoo-a".into(),
                    os: "gentoo".into(),
                    hostname: "a".into(),
                },
            ],
        )];
        let inv = build_inventory(&vms, false, None);
        let hosts = inv["gentoo"]["hosts"].as_array().unwrap();
        assert_eq!(hosts.len(), 1);
    }

    // -- read_hypervisors_file --

    #[test]
    fn read_hypervisors_missing_file() {
        let result = read_hypervisors_file(std::path::Path::new("/nonexistent/file.txt"));
        assert!(result.is_empty());
    }

    #[test]
    fn read_hypervisors_from_tempfile() {
        let dir = std::env::temp_dir().join("inv_test_hv");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hypervisors.txt");
        std::fs::write(&path, "host1\n\nhost2\n  host3  \n").unwrap();
        let result = read_hypervisors_file(&path);
        assert_eq!(result, vec!["host1", "host2", "host3"]);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
