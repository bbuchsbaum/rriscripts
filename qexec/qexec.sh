#!/bin/bash

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
#   -m, --mem              Amount of memory per node (default: "6G").
#   -n, --ncpus            Number of CPUs per task (default: "1").
#       --nodes            Number of nodes (default: "1").
#   -j, --name             Job name (default: "").
#   -a, --array            Array indices for array jobs (default: "").
#       --account          Account name (default: "rrg-brad").
#       --nox11            Disable X11 forwarding (default: false).
#   -o, --omp_num_threads  Number of OpenMP threads (default: 1).
#
# Arguments:
#   <command>              Command to execute in the job (required unless interactive mode is used).

# Default values
TIME=1
INTERACTIVE=false
MEM=""
NCPUS=1
NODES=1
JOB_NAME=""
ARRAY=""
ACCOUNT="rrg-brad"
NOX11=false
OMP_NUM_THREADS=1
LOG_DIR="${QEXEC_LOG_DIR:-}"  # Use environment variable if set, otherwise empty
DRY_RUN=false

# Help message
usage() {
    echo "Usage: $0 [options] <command>"
    echo ""
    echo "Options:"
    echo "  -t, --time             Time in hours to allocate for the job (default: 1)."
    echo "  -i, --interactive      Submit an interactive job (default: false)."
    echo "  -m, --mem              Amount of memory per node (default: 6G)."
    echo "  -n, --ncpus            Number of CPUs per task (default: 1)."
    echo "      --nodes            Number of nodes (default: 1)."
    echo "  -j, --name             Job name (default: '')."
    echo "  -a, --array            Array indices for array jobs (default: '')."
    echo "      --account          Account name (default: rrg-brad)."
    echo "      --nox11            Disable X11 forwarding (default: false)."
    echo "  -o, --omp_num_threads  Number of OpenMP threads (default: 1)."
    echo "  -l, --log-dir          Directory for log output (default: current dir or \$QEXEC_LOG_DIR)."
    echo "  -d, --dry-run          Show computed SLURM command and exit."
    echo ""
    echo "Arguments:"
    echo "  <command>              Command to execute in the job (required unless interactive mode is used)."
    exit 1
}

# Parse arguments
# Detect GNU enhanced getopt reliably: it returns status 4 for `-T`
getopt -T >/dev/null 2>&1
GETOPT_STATUS=$?
if [ $GETOPT_STATUS -eq 4 ]; then
    # Use enhanced getopt for robust parsing
    SHORT_OPTS="t:im:n:j:a:o:l:hd"
    LONG_OPTS="time:,interactive,mem:,ncpus:,nodes:,name:,array:,account:,nox11,omp_num_threads:,log-dir:,help,dry-run"
    PARSED_OPTIONS=$(getopt --options $SHORT_OPTS --longoptions $LONG_OPTS --name "$0" -- "$@")
    if [[ $? -ne 0 ]]; then
        usage
    fi
    eval set -- "$PARSED_OPTIONS"

    while true; do
        case "$1" in
            -t|--time)
                TIME="$2"; shift 2 ;;
            -i|--interactive)
                INTERACTIVE=true; shift ;;
            -m|--mem)
                MEM="$2"; shift 2 ;;
            -n|--ncpus)
                NCPUS="$2"; shift 2 ;;
            --nodes)
                NODES="$2"; shift 2 ;;
            -j|--name)
                JOB_NAME="$2"; shift 2 ;;
            -a|--array)
                 if [[ "$2" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then
                     ARRAY="$2"; shift 2
                 else
                     echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
                     usage
                 fi
                 ;;
            --account)
                ACCOUNT="$2"; shift 2 ;;
            --nox11)
                NOX11=true; shift ;;
            -o|--omp_num_threads)
                OMP_NUM_THREADS="$2"; shift 2 ;;
            -l|--log-dir)
                LOG_DIR="$2"; shift 2 ;;
            -d|--dry-run)
                DRY_RUN=true; shift ;;
            -h|--help)
                usage ;;
            --)
                shift; COMMAND="$@"; break ;;
            *)
                echo "Internal error! Unexpected option: $1" >&2; exit 1 ;;
        esac
    done
else
    # Fallback to basic manual parsing if enhanced getopt is not available
    echo "Warning: Enhanced getopt not found. Using basic argument parsing." >&2
    echo "Hint: Place qexec options before the command, or use -- to separate." >&2

    # Parse options but preserve the original command tokens as-is
    CMD_PARTS=()
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            -t|--time)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                TIME="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -i|--interactive)
                INTERACTIVE=true; CMD_PARTS+=("$1"); shift; continue ;;
            -m|--mem)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                MEM="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -n|--ncpus)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                NCPUS="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            --nodes)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                NODES="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -j|--name)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                JOB_NAME="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -a|--array)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                if [[ "$2" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then
                    ARRAY="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue
                else
                    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
                    usage
                fi
                ;;
            --array=*)
                ARRAY_VAL="${1#--array=}"
                if [[ "$ARRAY_VAL" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then
                    ARRAY="$ARRAY_VAL"; CMD_PARTS+=("$1"); shift; continue
                else
                    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
                    usage
                fi
                ;;
            --account)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                ACCOUNT="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            --nox11)
                NOX11=true; CMD_PARTS+=("$1"); shift; continue ;;
            -o|--omp_num_threads)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                OMP_NUM_THREADS="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -l|--log-dir)
                if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value" >&2; usage; fi
                LOG_DIR="$2"; CMD_PARTS+=("$1" "$2"); shift 2; continue ;;
            -d|--dry-run)
                DRY_RUN=true; shift; continue ;;
            -h|--help)
                usage ;;
            --)
                CMD_PARTS+=("$1"); shift
                # Remainder is part of the command unchanged
                while [[ "$#" -gt 0 ]]; do CMD_PARTS+=("$1"); shift; done
                break ;;
            *)
                # Unrecognized or positional token; keep it as part of the command
                CMD_PARTS+=("$1"); shift; continue ;;
        esac
    done
    # Reconstruct the command string preserving spacing
    COMMAND="${CMD_PARTS[*]}"
fi

# Validate required arguments
if [ -z "$COMMAND" ] && [ "$INTERACTIVE" == "false" ]; then
    echo "Error: A command is required unless interactive mode is used."
    usage
fi

# Set environment variables for OpenMP
export OMP_NUM_THREADS=$OMP_NUM_THREADS
export MKL_NUM_THREADS=$OMP_NUM_THREADS

# Helper function to run commands with logging
execute_command() {
    echo "Executing: $1"
    eval "$1"
}

if [ "$INTERACTIVE" == "true" ]; then
    # Interactive job: use salloc
    TIME_MINUTES=$((TIME * 60))
    SALLOC_CMD="salloc --time=${TIME_MINUTES} --account=${ACCOUNT} --cpus-per-task=${NCPUS} --nodes=${NODES}"
    [ -n "$MEM" ] && SALLOC_CMD+=" --mem=${MEM}"
    if [ "$NOX11" == "false" ]; then
        SALLOC_CMD+=" --x11"
    fi
    if [ "$DRY_RUN" = true ]; then
        echo "Dry-run: Parsed arguments:"
        echo "  TIME=$TIME (minutes=$TIME_MINUTES)"
        echo "  NCPUS=$NCPUS"
        echo "  NODES=$NODES"
        echo "  ARRAY=$ARRAY"
        echo "  MEM=${MEM:-}"
        echo "  ACCOUNT=$ACCOUNT"
        echo "Dry-run: Would execute interactive command:"
        echo "$SALLOC_CMD"
        exit 0
    fi
    execute_command "$SALLOC_CMD"
else
    # Batch job: use sbatch
    JOB_SCRIPT=""
    if [ "$DRY_RUN" != true ]; then
        JOB_SCRIPT=$(mktemp)
        {
            echo "#!/bin/bash"
            echo "export OMP_NUM_THREADS=${OMP_NUM_THREADS}"
            echo "export MKL_NUM_THREADS=${OMP_NUM_THREADS}"
            # Expand home directory and clean up command
            CLEAN_CMD=$(echo "$COMMAND" | sed "s|~/bin|$HOME/bin|g" | sed 's/--array=[0-9-]*//')
            # Use eval to execute the command string, preserving special characters
            # Single quotes prevent premature expansion in the here-doc/echo context
            # Double quotes around $CLEAN_CMD inside eval allow variable expansion *within* the command on the node
            echo 'eval "'$CLEAN_CMD'"'
        } > "$JOB_SCRIPT"
        echo "Debug: Contents of $JOB_SCRIPT:"
        cat "$JOB_SCRIPT"
    fi

    TIME_MINUTES=$((TIME * 60))
    SBATCH_ARGS=""
    [ -n "$ARRAY" ] && SBATCH_ARGS+=" --array=${ARRAY}"
    SBATCH_ARGS+=" --time=${TIME_MINUTES} --account=${ACCOUNT} --cpus-per-task=${NCPUS} --nodes=${NODES}"
    [ -n "$MEM" ] && SBATCH_ARGS+=" --mem=${MEM}"
    [ -n "$JOB_NAME" ] && SBATCH_ARGS+=" --job-name=${JOB_NAME}"
    
    # Set output and error file locations if LOG_DIR is specified
    if [ -n "$LOG_DIR" ]; then
        # Create the log directory if it doesn't exist
        mkdir -p "$LOG_DIR" 2>/dev/null || true
        SBATCH_ARGS+=" --output=${LOG_DIR}/slurm-%j.out"
        SBATCH_ARGS+=" --error=${LOG_DIR}/slurm-%j.err"
    fi

    SBATCH_CMD="sbatch $SBATCH_ARGS ${JOB_SCRIPT}"
    echo "Debug: ARRAY=$ARRAY"
    echo "Debug: SBATCH_ARGS=$SBATCH_ARGS"
    echo "Debug: Full command being executed:"
    echo "$COMMAND"
    if [ "$DRY_RUN" = true ]; then
        echo "Dry-run: Parsed arguments:"
        echo "  TIME=$TIME (minutes=$TIME_MINUTES)"
        echo "  NCPUS=$NCPUS"
        echo "  NODES=$NODES"
        echo "  ARRAY=$ARRAY"
        echo "  MEM=${MEM:-}"
        echo "  ACCOUNT=$ACCOUNT"
        echo "Dry-run: Would submit batch command:"
        echo "$SBATCH_CMD"
        echo "Dry-run: Job script content would be:"
        echo "#!/bin/bash"
        echo "export OMP_NUM_THREADS=${OMP_NUM_THREADS}"
        echo "export MKL_NUM_THREADS=${OMP_NUM_THREADS}"
        CLEAN_CMD=$(echo "$COMMAND" | sed "s|~/bin|$HOME/bin|g" | sed 's/--array=[0-9-]*//')
        echo "eval \"$CLEAN_CMD\""
        exit 0
    fi

    execute_command "$SBATCH_CMD"
    # Clean up temporary job script
    trap 'rm -f "$JOB_SCRIPT"' EXIT
fi

# Add near the start of the script, after argument parsing
echo "Debug: Command line arguments received: $@"
echo "Debug: After parsing: ARRAY='$ARRAY' COMMAND='$COMMAND'"

# Add after argument parsing
echo "Debug: Parsed arguments:"
echo "  TIME=$TIME"
echo "  NCPUS=$NCPUS"
echo "  NODES=$NODES"
echo "  ARRAY=$ARRAY"
echo "  COMMAND=$COMMAND"
