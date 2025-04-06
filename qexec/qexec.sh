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
    echo ""
    echo "Arguments:"
    echo "  <command>              Command to execute in the job (required unless interactive mode is used)."
    exit 1
}

# Parse arguments
# Check if enhanced getopt is available
if getopt --test > /dev/null; then
    # Use enhanced getopt for robust parsing
    SHORT_OPTS="t:im:n:j:a:o:h"
    LONG_OPTS="time:,interactive,mem:,ncpus:,nodes:,name:,array:,account:,nox11,omp_num_threads:,help"
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
    while [[ "$#" -gt 0 ]]; do
        case $1 in
            -t|--time) TIME="$2"; shift ;;       # Note: Original shift logic retained for fallback
            -i|--interactive) INTERACTIVE=true ;; # Note: Original shift logic retained for fallback
            -m|--mem) MEM="$2"; shift ;;          # Note: Original shift logic retained for fallback
            -n|--ncpus) NCPUS="$2"; shift ;;       # Note: Original shift logic retained for fallback
            --nodes) NODES="$2"; shift ;;       # Note: Original shift logic retained for fallback
            -j|--name) JOB_NAME="$2"; shift ;;    # Note: Original shift logic retained for fallback
            -a|--array)
                if [[ "$2" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then # Use updated regex for consistency
                    ARRAY="$2"
                    shift
                else
                    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
                    usage
                fi
                ;;
            --array=*)
                ARRAY_VAL="${1#--array=}"
                if [[ "$ARRAY_VAL" =~ ^[0-9]+(-[0-9]+)?(%[0-9]+)?$ ]]; then # Use updated regex for consistency
                    ARRAY="$ARRAY_VAL"
                else
                    echo "Error: --array requires a valid range (e.g., 1-5 or 1-10%2)" >&2
                    usage
                fi
                ;;
            --account) ACCOUNT="$2"; shift ;;   # Note: Original shift logic retained for fallback
            --nox11) NOX11=true ;;             # Note: Original shift logic retained for fallback
            -o|--omp_num_threads) OMP_NUM_THREADS="$2"; shift ;; # Note: Original shift logic retained for fallback
            -h|--help) usage ;;
            --) shift; COMMAND="$*"; break ;;
            -*) echo "Error: Unknown option: $1"; usage ;;
            *) COMMAND="$*"; break ;;
        esac
        shift # Note: Original shift logic retained for fallback
    done
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
    execute_command "$SALLOC_CMD"
else
    # Batch job: use sbatch
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
    
    TIME_MINUTES=$((TIME * 60))
    SBATCH_ARGS=""
    [ -n "$ARRAY" ] && SBATCH_ARGS+=" --array=${ARRAY}"
    SBATCH_ARGS+=" --time=${TIME_MINUTES} --account=${ACCOUNT} --cpus-per-task=${NCPUS} --nodes=${NODES}"
    [ -n "$MEM" ] && SBATCH_ARGS+=" --mem=${MEM}"
    [ -n "$JOB_NAME" ] && SBATCH_ARGS+=" --job-name=${JOB_NAME}"

    SBATCH_CMD="sbatch $SBATCH_ARGS $JOB_SCRIPT"
    echo "Debug: ARRAY=$ARRAY"
    echo "Debug: SBATCH_ARGS=$SBATCH_ARGS"
    echo "Debug: Full command being executed:"
    echo "$COMMAND"
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
