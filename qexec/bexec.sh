#!/bin/bash
set -euo pipefail

# bexec.sh
# Submit a pre-written commands file as a Slurm array job via qexec.sh and
# command_distributor.sh. This is the file-oriented counterpart to batch_exec.sh.
#
# Usage:
#   bexec.sh -f commands.txt [options]
#
# Options:
#   -f, --file FILE         Commands file to submit (required)
#   -n, --nodes N           Number of array tasks / batches (default: 1)
#       --time HOURS        Hours per array task (default: 1)
#       --ncpus N           CPUs per array task (default: 40)
#       --mem MEM           Memory per task (e.g. 12G). Omit to use qexec defaults.
#       --no-mem            Pass through qexec's --no-mem switch
#   -j, --jobs N            GNU parallel jobs per batch (default: 40)
#   -N, --name NAME         Slurm job name
#       --account NAME      Slurm account
#   -l, --log-dir DIR       Slurm log directory
#   -d, --dry-run           Show computed qexec call and exit
#   -h, --help              Show this help

usage() {
    sed -n '1,22p' "$0"
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_script() {
    local name="$1"
    local candidate="$SCRIPT_DIR/$name"
    if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return
    fi

    candidate="$(command -v "$name" 2>/dev/null || true)"
    if [[ -z "$candidate" ]]; then
        echo "Error: required script '$name' not found next to bexec.sh or in PATH." >&2
        exit 1
    fi

    printf '%s\n' "$candidate"
}

QEXEC_PATH="$(find_script qexec.sh)"
CMD_DIST_PATH="$(find_script command_distributor.sh)"

commands_file=""
nodes=1
time_hours=1
ncpus=40
mem=""
no_mem=false
jobs=40
job_name=""
account=""
log_dir=""
dry_run=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)      commands_file="${2:-}"; shift 2 ;;
        -n|--nodes)     nodes="${2:-}"; shift 2 ;;
        --time)         time_hours="${2:-}"; shift 2 ;;
        --ncpus)        ncpus="${2:-}"; shift 2 ;;
        --mem)          mem="${2:-}"; shift 2 ;;
        --no-mem)       no_mem=true; shift ;;
        -j|--jobs)      jobs="${2:-}"; shift 2 ;;
        -N|--name)      job_name="${2:-}"; shift 2 ;;
        --account)      account="${2:-}"; shift 2 ;;
        -l|--log-dir)   log_dir="${2:-}"; shift 2 ;;
        -d|--dry-run)   dry_run=true; shift ;;
        -h|--help)      usage ;;
        *)              echo "Error: Unknown option: $1" >&2; usage ;;
    esac
done

if [[ -z "$commands_file" ]]; then
    echo "Error: --file is required." >&2
    usage
fi

if [[ ! -f "$commands_file" ]]; then
    echo "Error: Commands file '$commands_file' does not exist." >&2
    exit 1
fi

if ! [[ "$nodes" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --nodes must be a positive integer." >&2
    exit 1
fi

if ! [[ "$time_hours" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --time must be a positive integer number of hours." >&2
    exit 1
fi

if ! [[ "$ncpus" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --ncpus must be a positive integer." >&2
    exit 1
fi

if ! [[ "$jobs" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --jobs must be a positive integer." >&2
    exit 1
fi

if [[ -n "$mem" ]]; then
    upper_mem="$(printf '%s' "$mem" | tr '[:lower:]' '[:upper:]')"
    if ! [[ "$upper_mem" =~ ^[0-9]+[KMGTP]$ ]]; then
        echo "Error: --mem must look like 6G, 512M, 1T, etc." >&2
        exit 1
    fi
fi

total_commands="$(grep -cve '^[[:space:]]*$' "$commands_file" || true)"
if [[ -z "$total_commands" || "$total_commands" -eq 0 ]]; then
    echo "Error: Commands file '$commands_file' is empty after removing blank lines." >&2
    exit 1
fi

qexec_cmd=( "$QEXEC_PATH" "--time" "$time_hours" "--ncpus" "$ncpus" "--nodes" "1" "--array=1-${nodes}" )
[[ -n "$mem" ]] && qexec_cmd+=( "--mem" "$mem" )
[[ "$no_mem" == true ]] && qexec_cmd+=( "--no-mem" )
[[ -n "$job_name" ]] && qexec_cmd+=( "--name" "$job_name" )
[[ -n "$account" ]] && qexec_cmd+=( "--account" "$account" )
[[ -n "$log_dir" ]] && qexec_cmd+=( "--log-dir" "$log_dir" )
[[ "$dry_run" == true ]] && qexec_cmd+=( "--dry-run" )
qexec_cmd+=( "--" "$CMD_DIST_PATH" "$commands_file" "$nodes" "$jobs" )

echo "Submitting $total_commands commands across $nodes batch(es)."
echo "qexec command:"
printf '  %q' "${qexec_cmd[@]}"
printf '\n'

"${qexec_cmd[@]}"
