#!/bin/bash
set -euo pipefail

# batch_exec.sh
# Expand a parameterized command (via cmd_expand.sh) and submit the resulting
# command list as a Slurm array job using qexec.sh + command_distributor.sh.
#
# Usage:
#   batch_exec.sh [options] -- <base_command> [args...]
#     Arguments may include cmd_expand-style bracketed values (e.g., [1,2], 1..4).
#
# Options:
#   -t, --time HOURS        Walltime in hours for each array task (default: 1)
#   -n, --nodes N           Number of array tasks / batches (default: 1)
#       --ncpus N           CPUs per array task (default: 40)
#   -m, --mem MEM           Memory per task (e.g., 6G). Omit to use qexec defaults.
#   -j, --jobs N            GNU parallel jobs per task (default: 40)
#   -N, --name NAME         Slurm job name (optional)
#       --account NAME      Slurm account (optional; defaults to qexec default)
#   -l, --log-dir DIR       Slurm log directory (passed to qexec)
#       --link              Link mode for cmd_expand (zip arguments by position)
#       --quote             Ask cmd_expand to shell-quote expanded tokens
#   -d, --dry-run           Show computed commands/qexec call and exit
#   -h, --help              Show this help

usage() {
    sed -n '1,32p' "$0"
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
        echo "Error: required script '$name' not found next to batch_exec.sh or in PATH." >&2
        exit 1
    fi
    printf '%s\n' "$candidate"
}

QEXEC_PATH="$(find_script qexec.sh)"
CMD_EXPAND_PATH="$(find_script cmd_expand.sh)"
CMD_DIST_PATH="$(find_script command_distributor.sh)"

# Defaults
time_hours=1
nodes=1
ncpus=40
mem=""
jobs=40
job_name=""
account=""
log_dir=""
link_mode=false
quote_mode=false
dry_run=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--time)     time_hours="$2"; shift 2 ;;
        -n|--nodes)    nodes="$2"; shift 2 ;;
        --ncpus)       ncpus="$2"; shift 2 ;;
        -m|--mem)      mem="$2"; shift 2 ;;
        -j|--jobs)     jobs="$2"; shift 2 ;;
        -N|--name)     job_name="$2"; shift 2 ;;
        --account)     account="$2"; shift 2 ;;
        -l|--log-dir)  log_dir="$2"; shift 2 ;;
        --link)        link_mode=true; shift ;;
        --quote)       quote_mode=true; shift ;;
        -d|--dry-run)  dry_run=true; shift ;;
        -h|--help)     usage ;;
        --)            shift; break ;;
        *)             echo "Unknown option: $1" >&2; usage ;;
    esac
done

if [[ $# -eq 0 ]]; then
    echo "Error: a base command and arguments are required after --." >&2
    usage
fi

# Basic validation
if ! [[ "$nodes" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --nodes must be a positive integer." >&2
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

# Build the command list using cmd_expand.sh
cmd_file=$(mktemp -p "$PWD" batch_exec_cmds.XXXXXX 2>/dev/null || mktemp)
cmd_expand_args=()
$link_mode && cmd_expand_args+=(--link)
$quote_mode && cmd_expand_args+=(--quote)

"$CMD_EXPAND_PATH" "${cmd_expand_args[@]}" "$@" >"$cmd_file"
num_cmds=$(wc -l <"$cmd_file" | xargs)

if [[ -z "$num_cmds" || "$num_cmds" -eq 0 ]]; then
    echo "Error: expansion produced zero commands." >&2
    exit 1
fi

# Construct qexec command
qexec_cmd=( "$QEXEC_PATH" "--time" "$time_hours" "--ncpus" "$ncpus" "--nodes" "1" "--array=1-${nodes}" )
[[ -n "$mem" ]]      && qexec_cmd+=( "--mem" "$mem" )
[[ -n "$job_name" ]] && qexec_cmd+=( "--name" "$job_name" )
[[ -n "$account" ]]  && qexec_cmd+=( "--account" "$account" )
[[ -n "$log_dir" ]]  && qexec_cmd+=( "--log-dir" "$log_dir" )
qexec_cmd+=( "--" "$CMD_DIST_PATH" "$cmd_file" "$nodes" "$jobs" )

echo "Expanded to $num_cmds commands in: $cmd_file"
echo "Submitting via qexec:"
echo "  ${qexec_cmd[*]}"

if [[ "$dry_run" == true ]]; then
    echo "Dry-run enabled; not submitting."
    exit 0
fi

# Note: we intentionally do not delete $cmd_file here; the array tasks need it.
"${qexec_cmd[@]}"
