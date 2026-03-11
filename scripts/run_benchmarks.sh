#!/usr/bin/env bash
# run_benchmarks.sh — Wrapper for ansible-playbook playbooks/run_benchmarks.yml
#
# Usage:
#   ./scripts/run_benchmarks.sh [OPTIONS]
#
# Examples:
#   ./scripts/run_benchmarks.sh
#   ./scripts/run_benchmarks.sh --host gentoo-alice
#   ./scripts/run_benchmarks.sh --hypervisor hv1
#   ./scripts/run_benchmarks.sh --category compression,crypto
#   ./scripts/run_benchmarks.sh --runs 10 --warmup 5
#   ./scripts/run_benchmarks.sh --no-report --verbose --dry-run
#   ./scripts/run_benchmarks.sh --include-windows
#   ./scripts/run_benchmarks.sh --cpu-affinity 0-3
#   ./scripts/run_benchmarks.sh --no-ram-scale --compress-size 128
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLAYBOOK="${REPO_ROOT}/playbooks/run_benchmarks.yml"
INVENTORY="${REPO_ROOT}/inventory_generator.py"

# ── Defaults ─────────────────────────────────────────────────────────────────
DRY_RUN=0
LIMIT=""
CATEGORIES=""
RUNS=""
WARMUP=""
CPU_AFFINITY=""
INCLUDE_WINDOWS=0
NO_RAM_SCALE=0
NO_REPORT=0
COMPRESS_SIZE=""
FFMPEG_DURATION=""
EXTRA_ARGS=()

# ── Helpers ──────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_ANSIBLE_ARGS...]

Host selection (mutually exclusive):
  --host HOST[,HOST...]       Run on specific host(s) by name
  --hypervisor HV[,HV...]     Run only on VMs belonging to hypervisor(s)
                              (e.g. hv1, hv2 — matches hypervisor_<name>)
  --group GROUP[,GROUP...]    Run on an inventory group (e.g. gentoo, ubuntu, baremetal)
  --limit PATTERN             Raw ansible --limit expression

Benchmark control:
  --category CAT[,CAT...]     Run only these categories (comma-separated)
                              Available: compression, crypto, compiler, python,
                                ffmpeg, imagemagick, opencv, coreutils, startup,
                                gentoo_build_times, numeric, sqlite, memory,
                                process, disk, linker
  --runs N                    Benchmark repetitions per command (default: 5)
  --warmup N                  Warmup runs before measurement (default: 3)
  --cpu-affinity RANGE        Pin benchmarks to CPU range (e.g. 0-3)
  --compress-size MB          Compression test data size in MB (default: 64)
  --ffmpeg-duration SEC       FFmpeg test clip duration in seconds (default: 10)

Flags:
  --include-windows           Also run benchmarks on Windows VMs
  --no-ram-scale              Skip temporary RAM scaling on VMs
  --skip-complete             Skip hosts that already have a full set of results
  --no-report                 Skip report generation after benchmarks
  --verbose, -v               Pass -v to ansible-playbook (repeat for more: -vvv)
  --dry-run, -C               Pass --check to ansible-playbook (no changes)
  --ask-become-pass, -K       Prompt for sudo/become password
  --help, -h                  Show this help

Extra args after -- are passed directly to ansible-playbook.

Examples:
  # Run all benchmarks on all hosts
  $(basename "$0")

  # Single host, verbose
  $(basename "$0") --host gentoo-alice --verbose

  # All VMs on hypervisor hv1 only
  $(basename "$0") --hypervisor hv1

  # Only compression and crypto, more runs
  $(basename "$0") --category compression,crypto --runs 10 --warmup 5

  # Gentoo group, no RAM scaling, no report
  $(basename "$0") --group gentoo --no-ram-scale --no-report

  # Dry run to check what would happen
  $(basename "$0") --dry-run --verbose

  # Including Windows VMs
  $(basename "$0") --include-windows

  # Pass extra ansible flags
  $(basename "$0") -- --tags setup --skip-tags disk
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

# ── Argument parsing ─────────────────────────────────────────────────────────
VERBOSITY=""
BECOME_PASS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2"; shift 2 ;;
        --hypervisor)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            # Build a limit that includes each hypervisor group plus localhost
            # (localhost runs the report play)
            IFS=',' read -ra _HVS <<< "$2"
            _HV_PARTS=()
            for _hv in "${_HVS[@]}"; do
                # Strip leading "hypervisor_" if the user accidentally included it
                _hv="${_hv#hypervisor_}"
                _HV_PARTS+=("hypervisor_${_hv}")
            done
            LIMIT="$(IFS=','; echo "${_HV_PARTS[*]}"),localhost"
            shift 2 ;;
        --group)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2,localhost"; shift 2 ;;
        --limit)
            [[ -n "${LIMIT}" ]] && die "--host, --hypervisor, --group, --limit are mutually exclusive"
            LIMIT="$2"; shift 2 ;;
        --category)
            CATEGORIES="$2"; shift 2 ;;
        --runs)
            [[ "$2" =~ ^[0-9]+$ ]] || die "--runs requires a positive integer"
            RUNS="$2"; shift 2 ;;
        --warmup)
            [[ "$2" =~ ^[0-9]+$ ]] || die "--warmup requires a positive integer"
            WARMUP="$2"; shift 2 ;;
        --cpu-affinity)
            CPU_AFFINITY="$2"; shift 2 ;;
        --compress-size)
            [[ "$2" =~ ^[0-9]+$ ]] || die "--compress-size requires a positive integer"
            COMPRESS_SIZE="$2"; shift 2 ;;
        --ffmpeg-duration)
            [[ "$2" =~ ^[0-9]+$ ]] || die "--ffmpeg-duration requires a positive integer"
            FFMPEG_DURATION="$2"; shift 2 ;;
        --include-windows)
            INCLUDE_WINDOWS=1; shift ;;
        --no-ram-scale)
            NO_RAM_SCALE=1; shift ;;
        --skip-complete)
            SKIP_COMPLETE=1; shift ;;
        --no-report)
            NO_REPORT=1; shift ;;
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

# Verbosity
[[ -n "${VERBOSITY}" ]] && CMD+=("-${VERBOSITY}")

# Limit
if [[ -n "${LIMIT}" ]]; then
    # Always ensure localhost is reachable for the report play unless user
    # passed a raw --limit (they may know what they're doing)
    CMD+=(--limit "${LIMIT}")
fi

# Dry-run
[[ "${DRY_RUN}" -eq 1 ]] && CMD+=(--check)

# Become password
[[ "${BECOME_PASS}" -eq 1 ]] && CMD+=(-K)

# ── Build extra-vars dict ────────────────────────────────────────────────────
declare -A EVARS=()

if [[ -n "${CATEGORIES}" ]]; then
    # Convert comma-separated list to JSON array: "compression,crypto" → ["compression","crypto"]
    _CAT_JSON="["
    IFS=',' read -ra _CATS <<< "${CATEGORIES}"
    for _cat in "${_CATS[@]}"; do
        _CAT_JSON+="\"${_cat}\","
    done
    _CAT_JSON="${_CAT_JSON%,}]"
    EVARS[run_benchmarks_categories]="${_CAT_JSON}"
fi

[[ -n "${RUNS}" ]]           && EVARS[run_benchmarks_runs]="${RUNS}"
[[ -n "${WARMUP}" ]]         && EVARS[run_benchmarks_warmup]="${WARMUP}"
[[ -n "${CPU_AFFINITY}" ]]   && EVARS[run_benchmarks_cpu_affinity]="${CPU_AFFINITY}"
[[ -n "${COMPRESS_SIZE}" ]]  && EVARS[run_benchmarks_compress_size_mb]="${COMPRESS_SIZE}"
[[ -n "${FFMPEG_DURATION}" ]] && EVARS[run_benchmarks_ffmpeg_duration_sec]="${FFMPEG_DURATION}"
[[ "${INCLUDE_WINDOWS}" -eq 1 ]] && EVARS[run_benchmarks_include_windows]="true"
[[ "${NO_RAM_SCALE}" -eq 1 ]]    && EVARS[run_benchmarks_scale_ram]="false"
[[ "${SKIP_COMPLETE}" -eq 1 ]]   && EVARS[run_benchmarks_skip_complete]="true"

# Build -e JSON string from EVARS
if [[ "${#EVARS[@]}" -gt 0 ]]; then
    _EVAR_JSON="{"
    for _key in "${!EVARS[@]}"; do
        _val="${EVARS[${_key}]}"
        # Bare JSON values (arrays, true/false, numbers) pass through;
        # plain strings get quoted
        if [[ "${_val}" =~ ^[\[\{]|^(true|false)$|^[0-9]+$ ]]; then
            _EVAR_JSON+="\"${_key}\":${_val},"
        else
            _EVAR_JSON+="\"${_key}\":\"${_val}\","
        fi
    done
    _EVAR_JSON="${_EVAR_JSON%,}}"
    CMD+=(-e "${_EVAR_JSON}")
fi

# Skip report: replace Play 2 with a no-op via tags — since there are no tags
# we use --skip-tags and a synthetic tag. Simplest approach: run with
# --limit that excludes localhost for the report play, but that breaks the
# report play entirely.  Instead we just warn and let the user decide.
if [[ "${NO_REPORT}" -eq 1 ]]; then
    CMD+=(--skip-tags generate_report)
fi

# Append any extra passthrough args
CMD+=("${EXTRA_ARGS[@]}")

# ── Print and run ─────────────────────────────────────────────────────────────
echo "▶ Running: ${CMD[*]}" >&2
echo "" >&2

exec "${CMD[@]}"
