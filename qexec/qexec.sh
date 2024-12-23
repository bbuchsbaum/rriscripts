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
        -a|--array)
            if [[ "$2" =~ ^[0-9-]+$ ]]; then
                ARRAY="$2"
                shift
            else
                echo "Error: --array requires a valid range (e.g., 1-5)"
                usage
            fi
            ;;
        --array=*)
            ARRAY="${1#--array=}"
            if ! [[ "$ARRAY" =~ ^[0-9-]+$ ]]; then
                echo "Error: --array requires a valid range (e.g., 1-5)"
                usage
            fi
            ;;
        --account) ACCOUNT="$2"; shift ;;
        --nox11) NOX11=true ;;
        -o|--omp_num_threads) OMP_NUM_THREADS="$2"; shift ;;
        -h|--help) usage ;;
        --) shift; COMMAND="$*"; break ;;
        -*) echo "Error: Unknown option: $1"; usage ;;
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
        # Expand home directory and clean up command
        CLEAN_CMD=$(echo "$COMMAND" | sed "s|~/bin|$HOME/bin|g" | sed 's/--array=[0-9-]*//')
        echo "$CLEAN_CMD"
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
