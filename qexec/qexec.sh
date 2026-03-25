#!/bin/bash
set -euo pipefail

# qexec.sh
# This script submits jobs to SLURM, either as interactive or batch jobs.
# It constructs and executes 'salloc' for interactive jobs or 'sbatch' for batch jobs.
#
# Usage:
#   qexec.sh [options] <command>
#
# Options:
#   -t, --time             Time in hours to allocate for the job (default: "1").
#   -i, --interactive      Submit an interactive job (default: false).
#   -m, --mem              Amount of memory per node (default: not set).
#   -n, --ncpus            Number of CPUs per task (default: "1").
#       --nodes            Number of nodes (default: "1").
#   -j, --name             Job name (default: "").
#   -a, --array            Array indices for array jobs (default: "").
#       --account          Account name (default: "rrg-brad").
#       --nox11            Disable X11 forwarding (default: false).
#   -o, --omp_num_threads  Number of OpenMP threads (default: 1).
#       --no-mem           Do not pass --mem to Slurm (overrides -m/--mem).
#
# Arguments:
#   <command>              Command to execute in the job (required unless interactive mode is used).

# Default values
TIME=1
INTERACTIVE=false
MEM="${QEXEC_DEFAULT_MEM:-}"
NCPUS=1
NODES=1
JOB_NAME=""
ARRAY=""
ACCOUNT="${QEXEC_DEFAULT_ACCOUNT:-rrg-brad}"
NOX11=false
OMP_NUM_THREADS=1
LOG_DIR="${QEXEC_LOG_DIR:-}"
DRY_RUN=false
NO_MEM=false
COMMAND=""

# If set (any value), skip adding --mem even if provided
if [ -n "${QEXEC_DISABLE_MEM:-}" ]; then
    NO_MEM=true
fi

# Help message
usage() {
    echo "Usage: $0 [options] <command>"
    echo ""
    echo "Options:"
    echo "  -t, --time             Time in hours to allocate for the job (default: 1)."
    echo "  -i, --interactive      Submit an interactive job (default: false)."
    echo "  -m, --mem              Amount of memory per node (default: not set)."
    echo "  -n, --ncpus            Number of CPUs per task (default: 1)."
    echo "      --nodes            Number of nodes (default: 1)."
    echo "  -j, --name             Job name (default: '')."
    echo "  -a, --array            Array indices for array jobs (default: '')."
    echo "      --account          Account name (default: rrg-brad)."
    echo "      --nox11            Disable X11 forwarding (default: false)."
    echo "  -o, --omp_num_threads  Number of OpenMP threads (default: 1)."
    echo "      --no-mem           Do not pass --mem to Slurm (overrides -m/--mem)."
    echo "  -l, --log-dir          Directory for log output (default: current dir or \$QEXEC_LOG_DIR)."
    echo "  -d, --dry-run          Show computed SLURM command and exit."
    echo ""
    echo "Arguments:"
    echo "  <command>              Command to execute in the job (required unless interactive mode is used)."
    echo ""
    echo "Environment:"
    echo "  QEXEC_DISABLE_MEM=1    Skip --mem even if provided (for whole-node clusters)."
    echo "  QEXEC_DEFAULT_MEM=VAL  Default memory request unless disabled or overridden."
    exit 1
}

require_value() {
    local flag="$1"
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: ${flag} requires a value." >&2
        usage
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--time)
            require_value "$1" "$2"
            TIME="$2"
            shift 2
            ;;
        --time=*)
            TIME="${1#--time=}"
            shift
            ;;
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -m|--mem)
            require_value "$1" "$2"
            MEM="$2"
            shift 2
            ;;
        --mem=*)
            MEM="${1#--mem=}"
            shift
            ;;
        -n|--ncpus)
            require_value "$1" "$2"
            NCPUS="$2"
            shift 2
            ;;
        --ncpus=*)
            NCPUS="${1#--ncpus=}"
            shift
            ;;
        --nodes)
            require_value "$1" "$2"
            NODES="$2"
            shift 2
            ;;
        --nodes=*)
            NODES="${1#--nodes=}"
            shift
            ;;
        -j|--name)
            require_value "$1" "$2"
            JOB_NAME="$2"
            shift 2
            ;;
        --name=*)
            JOB_NAME="${1#--name=}"
            shift
            ;;
        -a|--array)
            require_value "$1" "$2"
            ARRAY="$2"
            shift 2
            ;;
        --array=*)
            ARRAY="${1#--array=}"
            shift
            ;;
        --account)
            require_value "$1" "$2"
            ACCOUNT="$2"
            shift 2
            ;;
        --account=*)
            ACCOUNT="${1#--account=}"
            shift
            ;;
        --nox11)
            NOX11=true
            shift
            ;;
        -o|--omp_num_threads)
            require_value "$1" "$2"
            OMP_NUM_THREADS="$2"
            shift 2
            ;;
        --omp_num_threads=*)
            OMP_NUM_THREADS="${1#--omp_num_threads=}"
            shift
            ;;
        -l|--log-dir)
            require_value "$1" "$2"
            LOG_DIR="$2"
            shift 2
            ;;
        --log-dir=*)
            LOG_DIR="${1#--log-dir=}"
            shift
            ;;
        --no-mem)
            NO_MEM=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        --)
            shift
            COMMAND="$*"
            break
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            usage
            ;;
        *)
            COMMAND="$*"
            break
            ;;
    esac
done

if [[ -n "$ARRAY" ]] && ! [[ "$ARRAY" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then
    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
    usage
fi

# Validate TIME is a positive integer
if ! [[ "$TIME" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --time must be a positive integer (hours)." >&2
    exit 1
fi

if ! [[ "$NCPUS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --ncpus must be a positive integer." >&2
    exit 1
fi

if ! [[ "$NODES" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --nodes must be a positive integer." >&2
    exit 1
fi

if ! [[ "$OMP_NUM_THREADS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --omp_num_threads must be a positive integer." >&2
    exit 1
fi

# Validate required arguments
if [ -z "$COMMAND" ] && [ "$INTERACTIVE" == "false" ]; then
    echo "Error: A command is required unless interactive mode is used." >&2
    usage
fi

# Set environment variables for OpenMP
export OMP_NUM_THREADS=$OMP_NUM_THREADS
export MKL_NUM_THREADS=$OMP_NUM_THREADS

# Determine whether to pass --mem
USE_MEM=true
if [ "$NO_MEM" = true ]; then
    USE_MEM=false
fi
MEM_FLAG=""
if [ "$USE_MEM" = true ] && [ -n "$MEM" ]; then
    MEM_FLAG="--mem=${MEM}"
elif [ "$USE_MEM" = false ] && [ -n "$MEM" ]; then
    echo "Note: skipping --mem because memory requests are disabled (QEXEC_DISABLE_MEM or --no-mem)." >&2
fi

if [ "$INTERACTIVE" == "true" ]; then
    # Interactive job: build salloc command as an array
    TIME_MINUTES=$((TIME * 60))
    SALLOC_CMD=(salloc --time="${TIME_MINUTES}" --account="${ACCOUNT}" --cpus-per-task="${NCPUS}" --nodes="${NODES}")
    [ -n "$MEM_FLAG" ] && SALLOC_CMD+=("${MEM_FLAG}")
    if [ "$NOX11" == "false" ]; then
        SALLOC_CMD+=(--x11)
    fi
    if [ "$DRY_RUN" = true ]; then
        echo "Dry-run: Parsed arguments:"
        echo "  TIME=$TIME (minutes=$TIME_MINUTES)"
        echo "  NCPUS=$NCPUS"
        echo "  NODES=$NODES"
        echo "  ARRAY=$ARRAY"
        echo "  MEM=${MEM:-}"
        echo "  MEM_FLAG=${MEM_FLAG:-<none>}"
        echo "  ACCOUNT=$ACCOUNT"
        echo "Dry-run: Would execute interactive command:"
        echo "  ${SALLOC_CMD[*]}"
        exit 0
    fi
    echo "Executing: ${SALLOC_CMD[*]}"
    "${SALLOC_CMD[@]}"
else
    # Batch job: build sbatch command as an array
    TIME_MINUTES=$((TIME * 60))

    # Expand a common ~/bin shorthand without mutating other command arguments.
    CLEAN_CMD=$(printf '%s' "$COMMAND" | sed "s|~/bin|$HOME/bin|g")

    if [ "$DRY_RUN" = true ]; then
        # Build the sbatch args for display
        SBATCH_CMD=(sbatch)
        [ -n "$ARRAY" ] && SBATCH_CMD+=(--array="${ARRAY}")
        SBATCH_CMD+=(--time="${TIME_MINUTES}" --account="${ACCOUNT}" --cpus-per-task="${NCPUS}" --nodes="${NODES}")
        [ -n "$MEM_FLAG" ] && SBATCH_CMD+=("${MEM_FLAG}")
        [ -n "$JOB_NAME" ] && SBATCH_CMD+=(--job-name="${JOB_NAME}")
        if [ -n "$LOG_DIR" ]; then
            SBATCH_CMD+=(--output="${LOG_DIR}/slurm-%j.out" --error="${LOG_DIR}/slurm-%j.err")
        fi
        SBATCH_CMD+=("<job_script>")

        echo "Dry-run: Parsed arguments:"
        echo "  TIME=$TIME (minutes=$TIME_MINUTES)"
        echo "  NCPUS=$NCPUS"
        echo "  NODES=$NODES"
        echo "  ARRAY=$ARRAY"
        echo "  MEM=${MEM:-}"
        echo "  MEM_FLAG=${MEM_FLAG:-<none>}"
        echo "  ACCOUNT=$ACCOUNT"
        echo "  COMMAND=$COMMAND"
        echo "Dry-run: Would submit batch command:"
        echo "  ${SBATCH_CMD[*]}"
        echo "Dry-run: Job script content would be:"
        echo "  #!/bin/bash"
        echo "  export OMP_NUM_THREADS=${OMP_NUM_THREADS}"
        echo "  export MKL_NUM_THREADS=${OMP_NUM_THREADS}"
        echo "  ${CLEAN_CMD}"
        exit 0
    fi

    # Create temp script and set up cleanup immediately
    JOB_SCRIPT=$(mktemp)
    trap 'rm -f "$JOB_SCRIPT"' EXIT

    cat > "$JOB_SCRIPT" <<JOBEOF
#!/bin/bash
set -euo pipefail
export OMP_NUM_THREADS=${OMP_NUM_THREADS}
export MKL_NUM_THREADS=${OMP_NUM_THREADS}
${CLEAN_CMD}
JOBEOF

    # Build sbatch command as an array for safe execution
    SBATCH_CMD=(sbatch)
    [ -n "$ARRAY" ] && SBATCH_CMD+=(--array="${ARRAY}")
    SBATCH_CMD+=(--time="${TIME_MINUTES}" --account="${ACCOUNT}" --cpus-per-task="${NCPUS}" --nodes="${NODES}")
    [ -n "$MEM_FLAG" ] && SBATCH_CMD+=("${MEM_FLAG}")
    [ -n "$JOB_NAME" ] && SBATCH_CMD+=(--job-name="${JOB_NAME}")

    # Set output and error file locations if LOG_DIR is specified
    if [ -n "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        SBATCH_CMD+=(--output="${LOG_DIR}/slurm-%j.out" --error="${LOG_DIR}/slurm-%j.err")
    fi

    SBATCH_CMD+=("$JOB_SCRIPT")

    echo "Executing: ${SBATCH_CMD[*]}"
    "${SBATCH_CMD[@]}"
fi
