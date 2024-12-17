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
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -t|--time) TIME="$2"; shift ;;
        -i|--interactive) INTERACTIVE=true ;;
        -m|--mem) MEM="$2"; shift ;;
        -n|--ncpus) NCPUS="$2"; shift ;;
        --nodes) NODES="$2"; shift ;;
        -j|--name) JOB_NAME="$2"; shift ;;
        -a|--array) ARRAY="$2"; shift ;;
        --account) ACCOUNT="$2"; shift ;;
        --nox11) NOX11=true ;;
        -o|--omp_num_threads) OMP_NUM_THREADS="$2"; shift ;;
        -h|--help) usage ;;
        *) COMMAND="$*"; break ;;
    esac
    shift
done

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
        # Remove array parameter from command if present
        EXEC_CMD=$(echo "$COMMAND" | sed 's/--array=[0-9-]*//')
        echo "$EXEC_CMD"
    } > "$JOB_SCRIPT"
    
    TIME_MINUTES=$((TIME * 60))
    SBATCH_ARGS="--time=${TIME_MINUTES} --account=${ACCOUNT} --cpus-per-task=${NCPUS} --nodes=${NODES}"
    [ -n "$MEM" ] && SBATCH_ARGS+=" --mem=${MEM}"
    [ -n "$JOB_NAME" ] && SBATCH_ARGS+=" --job-name=${JOB_NAME}"
    [ -n "$ARRAY" ] && SBATCH_ARGS+=" --array=${ARRAY}"

    SBATCH_CMD="sbatch $SBATCH_ARGS $JOB_SCRIPT"
    execute_command "$SBATCH_CMD"
    
    # Clean up temporary job script
    trap 'rm -f "$JOB_SCRIPT"' EXIT
fi
