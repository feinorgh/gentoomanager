#!/usr/bin/env bash
# provision_benchmarks.sh — Wrapper for ansible-playbook playbooks/provision_benchmarks.yml
#
# Installs all benchmark software dependencies on managed hosts.  Optionally
# boots powered-off VMs before provisioning and shuts them down again afterwards
# (--manage-power).
#
# Usage:
#   ./scripts/provision_benchmarks.sh [OPTIONS]
#
# Examples:
#   ./scripts/provision_benchmarks.sh
#   ./scripts/provision_benchmarks.sh --host gentoo-alma
#   ./scripts/provision_benchmarks.sh --hypervisor adele
#   ./scripts/provision_benchmarks.sh --group gentoo
#   ./scripts/provision_benchmarks.sh --manage-power
#   ./scripts/provision_benchmarks.sh --manage-power --limit hypervisor_adele
#   ./scripts/provision_benchmarks.sh --include-windows
#   ./scripts/provision_benchmarks.sh --ask-become-pass --verbose
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLAYBOOK="${REPO_ROOT}/playbooks/provision_benchmarks.yml"
INVENTORY="${REPO_ROOT}/inventory_generator.py"

# ── Defaults ─────────────────────────────────────────────────────────────────
LIMIT=""
INCLUDE_WINDOWS=0
MANAGE_POWER=0
BOOT_TIMEOUT=""
SERIAL=""
DRY_RUN=0
VERBOSITY=""
BECOME_PASS=0
EXTRA_ARGS=()

# ── Helpers ──────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Provision specific host(s) by name
  --hypervisor HV[,HV...]     Provision only VMs belonging to hypervisor(s)
                              (e.g. adele, elise — matches hypervisor_<name>)
  --group GROUP[,GROUP...]    Provision an inventory group (e.g. gentoo, ubuntu)
  --limit PATTERN             Raw ansible --limit expression

Flags:
  --manage-power              Boot VMs that are off before provisioning and
                              shut them down again afterwards.  Only VMs
                              started by this run are shut down.
  --boot-timeout SEC          Seconds to wait for a VM to become reachable
                              after boot (default: 120)
  --serial [N]                Provision N hosts at a time (default: 1 when
                              flag is given).  Without this flag all eligible
                              hosts in each OS family are provisioned in
                              parallel.
  --include-windows           Also provision Windows hosts (installs benchmark
                              dependencies via Chocolatey)
  --verbose, -v               Pass -v to ansible-playbook (repeat for -vvv)
  --dry-run, -C               Pass --check to ansible-playbook (no changes)
  --ask-become-pass, -K       Prompt for sudo/become password
  --help, -h                  Show this help

Extra args after -- are passed directly to ansible-playbook.

Examples:
  # Provision all hosts
  $(basename "$0")

  # Provision a single host
  $(basename "$0") --host gentoo-alma

  # Provision all VMs on one hypervisor, boot/shutdown as needed
  $(basename "$0") --hypervisor adele --manage-power

  # Provision only Gentoo hosts, prompt for sudo
  $(basename "$0") --group gentoo --ask-become-pass

  # Provision all hosts including Windows
  $(basename "$0") --include-windows

  # Provision all hosts including Windows, one at a time
  $(basename "$0") --include-windows --serial

  # Dry run — show what would happen without making changes
  $(basename "$0") --dry-run --verbose

  # Pass extra ansible flags (e.g. tags)
  $(basename "$0") -- --tags packages
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2"; shift 2 ;;
        --hypervisor)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            IFS=',' read -ra _HVS <<< "$2"
            _HV_PARTS=()
            for _hv in "${_HVS[@]}"; do
                _hv="${_hv#hypervisor_}"
                _HV_PARTS+=("hypervisor_${_hv}")
            done
            LIMIT="$(IFS=','; echo "${_HV_PARTS[*]}")"
            shift 2 ;;
        --group)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2"; shift 2 ;;
        --limit)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2"; shift 2 ;;
        --manage-power)
            MANAGE_POWER=1; shift ;;
        --boot-timeout)
            [[ "$2" =~ ^[0-9]+$ ]] || die "--boot-timeout requires a positive integer"
            BOOT_TIMEOUT="$2"; shift 2 ;;
        --serial)
            # Optional numeric argument; default to 1 if omitted
            if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
                SERIAL="$2"; shift 2
            else
                SERIAL="1"; shift
            fi ;;
        --include-windows)
            INCLUDE_WINDOWS=1; shift ;;
        --verbose|-v)
            VERBOSITY="${VERBOSITY}v"; shift ;;
        --dry-run|-C)
            DRY_RUN=1; shift ;;
        --ask-become-pass|-K)
            BECOME_PASS=1; shift ;;
        --help|-h)
            usage; exit 0 ;;
        --)
            shift
            EXTRA_ARGS+=("$@")
            break ;;
        *)
            die "Unknown option: $1 (use -- to pass extra ansible args)" ;;
    esac
done

# ── Preflight checks ─────────────────────────────────────────────────────────
require_cmd ansible-playbook
require_cmd python3

[[ -f "${PLAYBOOK}" ]]   || die "Playbook not found: ${PLAYBOOK}"
[[ -f "${INVENTORY}" ]]  || die "Inventory not found: ${INVENTORY}"
[[ -x "${INVENTORY}" ]]  || die "Inventory script not executable: ${INVENTORY}"

cd "${REPO_ROOT}"

# ── Build ansible-playbook command ───────────────────────────────────────────
CMD=(ansible-playbook "${PLAYBOOK}" -i "${INVENTORY}")

[[ -n "${VERBOSITY}" ]] && CMD+=("-${VERBOSITY}")

[[ -n "${LIMIT}" ]] && CMD+=(--limit "${LIMIT}")

[[ "${DRY_RUN}"     -eq 1 ]] && CMD+=(--check)
[[ "${BECOME_PASS}" -eq 1 ]] && CMD+=(-K)

# ── Build extra-vars ─────────────────────────────────────────────────────────
declare -A EVARS=()

[[ "${MANAGE_POWER}"    -eq 1 ]] && EVARS[provision_manage_power]="true"
[[ -n "${BOOT_TIMEOUT}" ]]       && EVARS[provision_boot_timeout_sec]="${BOOT_TIMEOUT}"
[[ -n "${SERIAL}" ]]             && EVARS[provision_serial]="${SERIAL}"
[[ "${INCLUDE_WINDOWS}" -eq 1 ]] && EVARS[provision_include_windows]="true"

if [[ "${#EVARS[@]}" -gt 0 ]]; then
    _EVAR_JSON="{"
    for _key in "${!EVARS[@]}"; do
        _val="${EVARS[${_key}]}"
        if [[ "${_val}" =~ ^(true|false)$|^[0-9]+$ ]]; then
            _EVAR_JSON+="\"${_key}\":${_val},"
        else
            _EVAR_JSON+="\"${_key}\":\"${_val}\","
        fi
    done
    _EVAR_JSON="${_EVAR_JSON%,}}"
    CMD+=(-e "${_EVAR_JSON}")
fi

CMD+=("${EXTRA_ARGS[@]}")

# ── Print and run ─────────────────────────────────────────────────────────────
echo "▶ Running: ${CMD[*]}" >&2
echo "" >&2

exec "${CMD[@]}"
