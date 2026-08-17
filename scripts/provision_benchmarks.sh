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
FAIL_ON_TOOL_INSTALL_ERROR=0
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
  --serial [N]                Provision one host at a time (or N hosts per
                              batch), completing the full boot → provision →
                              shutdown lifecycle before moving to the next.
                              Default batch size is 1 when flag is given.
  --include-windows           Also provision Windows hosts (installs benchmark
                              dependencies via Chocolatey)
  --fail-on-tool-install-error
                              Exit with error if any tool installation fails
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

_is_unreachable_ssh_failure_line() {
    local line="$1"
    local lowered_line="${line,,}"

    [[ "${lowered_line}" == *"unreachable!"* ]] || return 1
    [[ "${lowered_line}" == *"via ssh"* \
        || "${lowered_line}" == *"permission denied (publickey)"* \
        || "${lowered_line}" == *"connection closed"* \
        || "${lowered_line}" == *"connection refused"* \
        || "${lowered_line}" == *"connection timed out"* \
        || "${lowered_line}" == *"no route to host"* \
        || "${lowered_line}" == *"could not resolve hostname"* ]]
}

_emit_ssh_troubleshooting_warning() {
    echo "WARNING: SSH connectivity issue detected while contacting target host(s)." >&2
    echo "WARNING: Check that your SSH public key is installed on the target host." >&2
    echo "WARNING: Check that the host is defined in ~/.ssh/config (or equivalent)." >&2
}

_filter_output_stream_and_warn() {
    local stream="$1"
    local warned=0

    while IFS= read -r line || [[ -n "${line}" ]]; do
        if [[ "${stream}" == "stderr" ]]; then
            printf "%s\n" "${line}" >&2
        else
            printf "%s\n" "${line}"
        fi

        if [[ "${warned}" -eq 0 ]] && _is_unreachable_ssh_failure_line "${line}"; then
            _emit_ssh_troubleshooting_warning
            warned=1
        fi
    done
}

run_ansible_with_output_filter() {
    set +e
    "$@" \
        > >(_filter_output_stream_and_warn stdout) \
        2> >(_filter_output_stream_and_warn stderr)
    local cmd_status=$?
    set -e
    return "${cmd_status}"
}

preflight_check_hypervisors_file() {
    local hypervisors_file="${REPO_ROOT}/hypervisors.txt"

    if [[ -n "${HYPERVISOR_HOSTS:-}" ]]; then
        return 0
    fi

    if [[ ! -f "${hypervisors_file}" ]]; then
        echo "WARNING: Missing ${hypervisors_file}" >&2
        echo "ERROR: Copy ${REPO_ROOT}/hypervisors.txt.example to ${hypervisors_file} and set hostnames, or set HYPERVISOR_HOSTS." >&2
        exit 1
    fi
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
        --fail-on-tool-install-error)
            FAIL_ON_TOOL_INSTALL_ERROR=1; shift ;;
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
preflight_check_hypervisors_file

cd "${REPO_ROOT}"

# ── Build ansible-playbook command (no --limit yet) ──────────────────────────
CMD=(env ANSIBLE_FORCE_COLOR=1 ansible-playbook "${PLAYBOOK}" -i "${INVENTORY}")

[[ -n "${VERBOSITY}" ]] && CMD+=("-${VERBOSITY}")
[[ "${DRY_RUN}"     -eq 1 ]] && CMD+=(--check)
[[ "${BECOME_PASS}" -eq 1 ]] && CMD+=(-K)

# ── Build extra-vars ─────────────────────────────────────────────────────────
declare -A EVARS=()

[[ "${MANAGE_POWER}"    -eq 1 ]] && EVARS[provision_manage_power]="true"
[[ -n "${BOOT_TIMEOUT}" ]]       && EVARS[provision_boot_timeout_sec]="${BOOT_TIMEOUT}"
[[ "${INCLUDE_WINDOWS}" -eq 1 ]] && EVARS[provision_include_windows]="true"
[[ "${FAIL_ON_TOOL_INSTALL_ERROR}" -eq 1 ]] && EVARS[provision_benchmarks_fail_on_install_error]="true"

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

# ── Serial mode: one host (or batch of N) at a time ──────────────────────────
# When --serial is given, enumerate all matching hosts and run the full
# playbook once per host (or per batch of N).  This guarantees the complete
# boot → provision → shutdown lifecycle completes for each host before the
# next one is started — something that cannot be achieved with Ansible's
# serial: keyword alone, because the boot play would still run across the
# entire fleet before any provisioning play begins.
if [[ -n "${SERIAL}" ]]; then
    SERIAL_N="${SERIAL}"

    # Query inventory for all hosts matching the user's selection
    HOST_QUERY=(ansible-inventory -i "${INVENTORY}" --list)
    [[ -n "${LIMIT}" ]] && HOST_QUERY+=(--limit "${LIMIT}")

    mapfile -t ALL_HOSTS < <(
        "${HOST_QUERY[@]}" 2>/dev/null | \
        python3 -c "
import json, sys
d = json.load(sys.stdin)
for h in sorted(d.get('_meta', {}).get('hostvars', {}).keys()):
    print(h)
"
    )

    [[ "${#ALL_HOSTS[@]}" -eq 0 ]] && die "No hosts matched the given selection"

    echo "▶ Serial mode: ${#ALL_HOSTS[@]} host(s), batch size ${SERIAL_N}" >&2
    echo "" >&2

    batch_start=0
    while [[ "${batch_start}" -lt "${#ALL_HOSTS[@]}" ]]; do
        batch=("${ALL_HOSTS[@]:${batch_start}:${SERIAL_N}}")
        batch_limit="$(IFS=','; echo "${batch[*]}")"

        echo "▶ Running: ${CMD[*]} --limit ${batch_limit}" >&2
        echo "" >&2

        run_ansible_with_output_filter "${CMD[@]}" --limit "${batch_limit}"
        batch_start=$(( batch_start + SERIAL_N ))
    done
    exit 0
fi

# ── Non-serial: add limit (if any) and exec ──────────────────────────────────
[[ -n "${LIMIT}" ]] && CMD+=(--limit "${LIMIT}")

echo "▶ Running: ${CMD[*]}" >&2
echo "" >&2

run_ansible_with_output_filter "${CMD[@]}"
