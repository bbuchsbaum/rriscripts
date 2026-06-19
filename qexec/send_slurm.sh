#!/bin/bash
set -euo pipefail

# send_slurm.sh
# Read commands from stdin and submit them as a Slurm array job via qexec.sh.
# The command list and runner script are written to a persistent directory so
# the submitted array job can still read them later.
#
# Usage:
#   cmd_expand.sh ... | send_slurm.sh [options]
#
# Options:
#   -t, --time HOURS        Hours per task (default: 1)
#   -m, --mem MEM           Memory per task
#   -n, --ncpus N           CPUs per task (default: 1)
#       --nodes N           Nodes per array task; with --pack, number of batches
#       --pack N, --jobs N  Split stdin across --nodes array tasks and run up to
#                           N commands concurrently per task
#   -j, --name NAME         Slurm job name (default: array_job)
#   -a, --array SPEC        Override array indices (default: 1-N for N input commands)
#       --account NAME      Slurm account (default: rrg-brad)
#       --nox11             Disable X11 forwarding (passed through to qexec)
#   -o, --omp_num_threads N OpenMP/MKL threads (default: 1)
#   -l, --log-dir DIR       Slurm log directory
#       --state-dir DIR     Directory for persisted command/runner files
#   -d, --dry-run           Show computed qexec call and exit
#   -h, --help              Show this help

usage() {
    sed -n '1,27p' "$0"
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
        echo "Error: required script '$name' not found next to send_slurm.sh or in PATH." >&2
        exit 1
    fi

    printf '%s\n' "$candidate"
}

QEXEC_PATH="$(find_script qexec.sh)"
CMD_DIST_PATH=""

TIME=1
MEM=""
NCPUS=1
NCPUS_WAS_SET=false
NODES=1
PACK=""
JOB_NAME="array_job"
ARRAY=""
ACCOUNT="rrg-brad"
NOX11=false
OMP_NUM_THREADS=1
LOG_DIR=""
STATE_DIR="${QEXEC_STATE_DIR:-$PWD/.qexec-state}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--time)            TIME="${2:-}"; shift 2 ;;
        -m|--mem)             MEM="${2:-}"; shift 2 ;;
        -n|--ncpus)           NCPUS="${2:-}"; NCPUS_WAS_SET=true; shift 2 ;;
        --nodes)              NODES="${2:-}"; shift 2 ;;
        --pack|--jobs)        PACK="${2:-}"; shift 2 ;;
        --pack=*|--jobs=*)    PACK="${1#*=}"; shift ;;
        -j|--name)            JOB_NAME="${2:-}"; shift 2 ;;
        -a|--array)           ARRAY="${2:-}"; shift 2 ;;
        --account)            ACCOUNT="${2:-}"; shift 2 ;;
        --nox11)              NOX11=true; shift ;;
        -o|--omp_num_threads) OMP_NUM_THREADS="${2:-}"; shift 2 ;;
        -l|--log-dir)         LOG_DIR="${2:-}"; shift 2 ;;
        --state-dir)          STATE_DIR="${2:-}"; shift 2 ;;
        -d|--dry-run)         DRY_RUN=true; shift ;;
        -h|--help)            usage ;;
        *)                    echo "Error: Unknown option: $1" >&2; usage ;;
    esac
done

for value_spec in \
    "time:$TIME" \
    "ncpus:$NCPUS" \
    "nodes:$NODES" \
    "omp_num_threads:$OMP_NUM_THREADS"
do
    label="${value_spec%%:*}"
    value="${value_spec#*:}"
    if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: --${label} must be a positive integer." >&2
        exit 1
    fi
done

if [[ -n "$PACK" ]] && ! [[ "$PACK" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --pack/--jobs must be a positive integer." >&2
    exit 1
fi

if [[ -n "$PACK" && -n "$ARRAY" ]]; then
    echo "Error: --array cannot be used with --pack/--jobs; use --nodes to set the number of packed batches." >&2
    exit 1
fi

if [[ -n "$MEM" ]]; then
    upper_mem="$(printf '%s' "$MEM" | tr '[:lower:]' '[:upper:]')"
    if ! [[ "$upper_mem" =~ ^[0-9]+[KMGTP]$ ]]; then
        echo "Error: --mem must look like 6G, 512M, 1T, etc." >&2
        exit 1
    fi
fi

mkdir -p "$STATE_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
COMMANDS_FILE="$(mktemp "$STATE_DIR/${JOB_NAME}.commands.${timestamp}.XXXXXX")"
RUNNER_SCRIPT=""
if [[ -z "$PACK" ]]; then
    RUNNER_SCRIPT="$(mktemp "$STATE_DIR/${JOB_NAME}.runner.${timestamp}.XXXXXX")"
fi

while IFS= read -r line; do
    [[ -z "${line//[[:space:]]/}" ]] && continue
    printf '%s\n' "$line" >> "$COMMANDS_FILE"
done

NUM_COMMANDS="$(wc -l < "$COMMANDS_FILE" | xargs)"
if [[ -z "$NUM_COMMANDS" || "$NUM_COMMANDS" -eq 0 ]]; then
    rm -f "$COMMANDS_FILE"
    [[ -n "$RUNNER_SCRIPT" ]] && rm -f "$RUNNER_SCRIPT"
    echo "Error: No commands provided on stdin." >&2
    exit 1
fi

if [[ -n "$PACK" ]]; then
    CMD_DIST_PATH="$(find_script command_distributor.sh)"
    ARRAY="1-${NODES}"
    if [[ "$NCPUS_WAS_SET" == false && "$NCPUS" -eq 1 ]]; then
        NCPUS="$PACK"
    fi
elif [[ -z "$ARRAY" ]]; then
    ARRAY="1-${NUM_COMMANDS}"
fi

if [[ -z "$PACK" ]]; then
    commands_file_quoted="$(printf '%q' "$COMMANDS_FILE")"
    cat > "$RUNNER_SCRIPT" <<EOF
#!/bin/bash
set -euo pipefail
COMMANDS_FILE=${commands_file_quoted}
TASK_ID=\${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}
COMMAND=\$(sed -n "\${TASK_ID}p" "\$COMMANDS_FILE")
if [[ -z "\$COMMAND" ]]; then
    echo "Error: no command found for array task \${TASK_ID} in \$COMMANDS_FILE" >&2
    exit 1
fi
echo "Executing[\${TASK_ID}]: \$COMMAND"
exec bash -lc "\$COMMAND"
EOF
    chmod +x "$RUNNER_SCRIPT"
fi

qexec_nodes="$NODES"
if [[ -n "$PACK" ]]; then
    qexec_nodes=1
fi

qexec_cmd=( "$QEXEC_PATH" "--time" "$TIME" "--ncpus" "$NCPUS" "--nodes" "$qexec_nodes" "--name" "$JOB_NAME" "--array=$ARRAY" "--account" "$ACCOUNT" "--omp_num_threads" "$OMP_NUM_THREADS" )
[[ -n "$MEM" ]] && qexec_cmd+=( "--mem" "$MEM" )
[[ "$NOX11" == true ]] && qexec_cmd+=( "--nox11" )
[[ -n "$LOG_DIR" ]] && qexec_cmd+=( "--log-dir" "$LOG_DIR" )
[[ "$DRY_RUN" == true ]] && qexec_cmd+=( "--dry-run" )
if [[ -n "$PACK" ]]; then
    qexec_cmd+=( "--" "$CMD_DIST_PATH" "$COMMANDS_FILE" "$NODES" "$PACK" )
else
    qexec_cmd+=( "--" "$RUNNER_SCRIPT" )
fi

echo "Persisted commands file: $COMMANDS_FILE"
if [[ -n "$RUNNER_SCRIPT" ]]; then
    echo "Persisted runner script: $RUNNER_SCRIPT"
fi
if [[ -n "$PACK" ]]; then
    echo "Submitting $NUM_COMMANDS command(s) across $NODES packed batch(es), up to $PACK concurrent command(s) per batch with:"
else
    echo "Submitting $NUM_COMMANDS command(s) with:"
fi
printf '  %q' "${qexec_cmd[@]}"
printf '\n'

"${qexec_cmd[@]}"
