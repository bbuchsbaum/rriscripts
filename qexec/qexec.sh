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
#   -t, --time             Time to allocate; bare numbers are hours
#                          (examples: 1, .5, 30m, 1hr; default: "1").
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
#       --cmd-file FILE    Read commands from FILE and submit as an array job
#                          (one command per line; sets --array automatically).
#       --preset NAME      Load a named resource preset (e.g., fmriprep, freesurfer).
#       --after JOBID      Run after JOBID completes (adds --dependency=afterok:JOBID).
#   -w, --wait             Wait for the job to finish and show efficiency stats.
#
# Configuration:
#   ~/.qexecrc             Optional config file sourced before arg parsing.
#                          Set any default variable (TIME, MEM, NCPUS, ACCOUNT, etc.).
#                          Cluster is auto-detected via $CC_CLUSTER or hostname.
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
CMD_FILE=""
AFTER=""
PRESET=""
WAIT=false
COMMAND=""

# Cluster auto-detection: set sensible defaults per cluster.
# Runs before qexecrc so user config can override.
_qexec_detect_cluster() {
    local cluster="${CC_CLUSTER:-}"
    if [[ -z "$cluster" ]]; then
        local host
        host="$(hostname -f 2>/dev/null || hostname 2>/dev/null || true)"
        case "$host" in
            *niagara*|*nia*|*trillium*|*trl*) cluster="niagara" ;;
            *narval*|*nar*)                    cluster="narval" ;;
            *beluga*|*blg*)                    cluster="beluga" ;;
            *cedar*|*cdr*)                     cluster="cedar" ;;
            *graham*|*gra*)                    cluster="graham" ;;
        esac
    fi
    case "$cluster" in
        niagara)
            NO_MEM=true
            NCPUS=40
            ;;
    esac
}
_qexec_detect_cluster

# Optional config file (defaults that CLI flags override)
QEXEC_CONFIG="${QEXEC_CONFIG:-$HOME/.qexecrc}"
if [[ -f "$QEXEC_CONFIG" ]]; then
    # shellcheck source=/dev/null
    source "$QEXEC_CONFIG"
fi

# If set (any value), skip adding --mem even if provided
if [ -n "${QEXEC_DISABLE_MEM:-}" ]; then
    NO_MEM=true
fi

# Built-in presets and user preset loader
_qexec_apply_preset() {
    local name="$1"
    local user_preset="${HOME}/.qexec/presets/${name}"
    if [[ -f "$user_preset" ]]; then
        # shellcheck source=/dev/null
        source "$user_preset"
        return
    fi
    case "$name" in
        fmriprep)    TIME=12; NCPUS=8;  MEM=32G ;;
        freesurfer)  TIME=24; NCPUS=1;  MEM=8G  ;;
        mriqc)       TIME=4;  NCPUS=4;  MEM=16G ;;
        light)       TIME=1;  NCPUS=1;  MEM=4G  ;;
        heavy)       TIME=24; NCPUS=16; MEM=64G ;;
        *)
            echo "Error: Unknown preset '$name'." >&2
            echo "Built-in presets: fmriprep, freesurfer, mriqc, light, heavy" >&2
            echo "Or create a custom preset at ~/.qexec/presets/$name" >&2
            exit 1
            ;;
    esac
}

# Help message
usage() {
    echo "Usage: $0 [options] <command>"
    echo ""
    echo "Options:"
    echo "  -t, --time             Time to allocate; bare numbers are hours (e.g. 1, .5, 30m, 1hr)."
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
    echo "      --cmd-file FILE    Read commands from FILE and submit as an array job."
    echo "      --preset NAME      Load resource preset (fmriprep, freesurfer, mriqc, light, heavy)."
    echo "      --after JOBID      Run after JOBID completes (sbatch --dependency=afterok:JOBID)."
    echo "  -w, --wait             Wait for the job to finish and show efficiency stats."
    echo "  -l, --log-dir          Directory for log output (default: current dir or \$QEXEC_LOG_DIR)."
    echo "  -d, --dry-run          Show computed SLURM command and exit."
    echo ""
    echo "Arguments:"
    echo "  <command>              Command to execute in the job (required unless interactive mode is used)."
    echo ""
    echo "Environment:"
    echo "  QEXEC_CONFIG=FILE      Path to config file (default: ~/.qexecrc)."
    echo "  QEXEC_DISABLE_MEM=1    Skip --mem even if provided (for whole-node clusters)."
    echo "  QEXEC_DEFAULT_MEM=VAL  Default memory request unless disabled or overridden."
    echo "  CC_CLUSTER=NAME        Override cluster auto-detection (niagara, narval, etc.)."
    exit 1
}

require_value() {
    local flag="$1"
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: ${flag} requires a value." >&2
        usage
    fi
}

_qexec_parse_time_to_minutes() {
    local input="$1"
    local normalized=""
    local quantity=""
    local unit=""

    # Keep bare numbers as hours for backward compatibility while allowing unit suffixes.
    normalized="$(printf '%s' "$input" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"

    if [[ "$normalized" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]]; then
        quantity="${BASH_REMATCH[1]}"
        unit="hours"
    elif [[ "$normalized" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)(h|hr|hrs|hour|hours)$ ]]; then
        quantity="${BASH_REMATCH[1]}"
        unit="hours"
    elif [[ "$normalized" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)(m|min|mins|minute|minutes)$ ]]; then
        quantity="${BASH_REMATCH[1]}"
        unit="minutes"
    else
        return 1
    fi

    awk -v quantity="$quantity" -v unit="$unit" '
        BEGIN {
            minutes = (unit == "minutes") ? quantity : quantity * 60
            if (minutes <= 0) {
                exit 1
            }
            rounded = int(minutes)
            if (minutes > rounded) {
                rounded++
            }
            print rounded
        }
    '
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
        --cmd-file)
            require_value "$1" "$2"
            CMD_FILE="$2"
            shift 2
            ;;
        --cmd-file=*)
            CMD_FILE="${1#--cmd-file=}"
            shift
            ;;
        --preset)
            require_value "$1" "$2"
            PRESET="$2"
            _qexec_apply_preset "$PRESET"
            shift 2
            ;;
        --preset=*)
            PRESET="${1#--preset=}"
            _qexec_apply_preset "$PRESET"
            shift
            ;;
        --after)
            require_value "$1" "$2"
            AFTER="$2"
            shift 2
            ;;
        --after=*)
            AFTER="${1#--after=}"
            shift
            ;;
        -w|--wait)
            WAIT=true
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

# --cmd-file: validate file, set ARRAY and COMMAND automatically
if [[ -n "$CMD_FILE" ]]; then
    if [[ ! -f "$CMD_FILE" ]]; then
        echo "Error: --cmd-file '$CMD_FILE' does not exist." >&2
        exit 1
    fi
    NUM_LINES=$(grep -c . "$CMD_FILE" || true)
    if [[ "$NUM_LINES" -eq 0 ]]; then
        echo "Error: --cmd-file '$CMD_FILE' is empty." >&2
        exit 1
    fi
    if [[ -n "$ARRAY" ]]; then
        echo "Error: --cmd-file and --array are mutually exclusive." >&2
        exit 1
    fi
    if [[ -n "$COMMAND" ]]; then
        echo "Error: --cmd-file and a positional command are mutually exclusive." >&2
        exit 1
    fi
    CMD_FILE="$(cd "$(dirname "$CMD_FILE")" && pwd)/$(basename "$CMD_FILE")"
    ARRAY="1-${NUM_LINES}"
    COMMAND="sed -n \"\${SLURM_ARRAY_TASK_ID}p\" \"${CMD_FILE}\" | bash"
fi

if [[ -n "$ARRAY" ]] && ! [[ "$ARRAY" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then
    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
    usage
fi

# Validate --after is a numeric job ID
if [[ -n "$AFTER" ]] && ! [[ "$AFTER" =~ ^[0-9]+$ ]]; then
    echo "Error: --after requires a numeric Slurm job ID." >&2
    exit 1
fi

# --wait and --after are batch-only
if [[ "$INTERACTIVE" == "true" ]]; then
    if [[ "$WAIT" == true ]]; then
        echo "Error: --wait is not supported with interactive jobs." >&2
        exit 1
    fi
    if [[ -n "$AFTER" ]]; then
        echo "Error: --after is not supported with interactive jobs." >&2
        exit 1
    fi
fi

# Validate TIME and convert to Slurm minutes.
if ! TIME_MINUTES="$(_qexec_parse_time_to_minutes "$TIME")"; then
    echo "Error: --time must be a positive duration in hours by default (e.g. 1, .5, 30m, 1hr)." >&2
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
    # Expand a common ~/bin shorthand without mutating other command arguments.
    CLEAN_CMD=$(printf '%s' "$COMMAND" | sed "s|~/bin|$HOME/bin|g")

    if [ "$DRY_RUN" = true ]; then
        # Build the sbatch args for display
        SBATCH_CMD=(sbatch)
        [ -n "$ARRAY" ] && SBATCH_CMD+=(--array="${ARRAY}")
        [ -n "$AFTER" ] && SBATCH_CMD+=(--dependency="afterok:${AFTER}")
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
    [ -n "$AFTER" ] && SBATCH_CMD+=(--dependency="afterok:${AFTER}")
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
    if [[ "$WAIT" == true ]]; then
        SBATCH_OUTPUT=$("${SBATCH_CMD[@]}")
        echo "$SBATCH_OUTPUT"
        SUBMITTED_JOB_ID=$(echo "$SBATCH_OUTPUT" | grep -oE '[0-9]+$' | head -1)
        if [[ -n "$SUBMITTED_JOB_ID" ]]; then
            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            MONITOR_PATH="${SCRIPT_DIR}/slurm_job_monitor.sh"
            if [[ -x "$MONITOR_PATH" ]]; then
                echo "Waiting for job $SUBMITTED_JOB_ID to finish..."
                "$MONITOR_PATH" "$SUBMITTED_JOB_ID"
            else
                echo "Warning: slurm_job_monitor.sh not found at $MONITOR_PATH; cannot wait." >&2
                echo "Job $SUBMITTED_JOB_ID submitted but not monitored." >&2
            fi
        else
            echo "Warning: could not parse job ID from sbatch output; cannot wait." >&2
        fi
    else
        "${SBATCH_CMD[@]}"
    fi
fi
