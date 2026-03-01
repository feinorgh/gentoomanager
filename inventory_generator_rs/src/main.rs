use clap::Parser;
use rayon::prelude::*;
use std::path::PathBuf;

use inventory_generator::{
    build_inventory, get_vms_from_host, probe_build_profile, read_hypervisors_file, VmInfo,
};

#[derive(Parser)]
#[command(about = "Generate Ansible inventory from hypervisor VMs via SSH")]
struct Args {
    /// List of hypervisor hosts
    #[arg(long)]
    hosts: Vec<String>,

    /// Ansible dynamic inventory --list flag
    #[arg(long)]
    list: bool,

    /// Ansible dynamic inventory --host flag
    #[arg(long)]
    host: Option<String>,

    /// SSH into each Gentoo VM to read CFLAGS/FEATURES and assign capability
    /// groups (lto_enabled, hardened, cflags_O3, …).
    #[arg(long)]
    probe_cflags: bool,
}

fn main() {
    let args = Args::parse();

    if args.list {
        // Determine hypervisor list: CLI > env > file
        let hosts_list: Vec<String> = if !args.hosts.is_empty() {
            args.hosts.clone()
        } else if let Ok(env) = std::env::var("HYPERVISOR_HOSTS") {
            env.split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect()
        } else {
            let exe = std::env::current_exe().unwrap_or_default();
            let fallback = PathBuf::from(".");
            let dir = exe.parent().unwrap_or(&fallback);
            // Look next to the binary first, then the cwd
            let candidates = [
                dir.join("hypervisors.txt"),
                PathBuf::from("hypervisors.txt"),
            ];
            candidates
                .iter()
                .find(|p| p.exists())
                .map(|p| read_hypervisors_file(p))
                .unwrap_or_default()
        };

        // Query hypervisors in parallel
        let host_vms: Vec<(String, Vec<VmInfo>)> = hosts_list
            .par_iter()
            .map(|h| {
                let vms = get_vms_from_host(h);
                (h.clone(), vms)
            })
            .collect();

        let probe_fn = |host: &str, vm: &str| probe_build_profile(host, vm);

        let inventory = build_inventory(
            &host_vms,
            args.probe_cflags,
            if args.probe_cflags {
                Some(&probe_fn as &dyn Fn(&str, &str) -> _)
            } else {
                None
            },
        );

        println!(
            "{}",
            serde_json::to_string_pretty(&inventory).unwrap_or_else(|_| "{}".to_string())
        );
    } else if args.host.is_some() {
        println!("{{}}");
    } else {
        eprintln!("Usage: inventory_generator --list | --host <hostname>");
        eprintln!("       inventory_generator --list --probe-cflags");
        std::process::exit(1);
    }
}
