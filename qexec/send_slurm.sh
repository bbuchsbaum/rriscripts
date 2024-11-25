#!/bin/bash

# send_slurm.sh
# This script reads a list of commands from stdin and submits them as an array job to SLURM.
# It leverages qexec.sh to handle the actual job submission.
#
# Usage:
#   cmd_expand.sh ... | send_slurm.sh [options]
#
# Options:
#   -t, --time             Time in hours to allocate for the job (default: 1).
#   -m, --mem              Amount of memory per node (default: 6G).
#   -n, --ncpus            Number of CPUs per task (default: 1).
#       --nodes            Number of nodes (default: 1).
#   -j, --name             Job name (default: 'array_job').
#   -a, --array            Array indices for array jobs (default: determined by number of commands).
#       --account          Account name (default: 'rrg-brad').
#       --nox11            Disable X11 forwarding (default: false).
#   -o, --omp_num_threads  Number of OpenMP threads (default: 1).
#   -h, --help             Display help information.

# Exit immediately if a command exits with a non-zero status
set -e

# Function to display usage information
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -t, --time             Time in hours to allocate for the job (default: 1)."
    echo "  -m, --mem              Amount of memory per node (default: 6G)."
    echo "  -n, --ncpus            Number of CPUs per task (default: 1)."
    echo "      --nodes            Number of nodes (default: 1)."
    echo "  -j, --name             Job name (default: 'array_job')."
    echo "  -a, --array            Array indices for array jobs (default: determined by number of commands)."
    echo "      --account          Account name (default: 'rrg-brad')."
    echo "      --nox11            Disable X11 forwarding (default: false)."
    echo "  -o, --omp_num_threads  Number of OpenMP threads (default: 1)."
    echo "  -h, --help             Display help information."
    echo ""
    echo "Use '$0 --help' to display detailed examples."
    exit 1
}

# Function to display detailed help
detailed_help() {
    usage
    echo ""
    echo "This script reads commands from stdin and submits them as an array job to SLURM."
    echo "Each command corresponds to a separate task within the array job."
    echo ""
    echo "Parameters are passed to SLURM's sbatch command to configure resources."
    echo ""
    echo "Example Usage:"
    echo "  cmd_expand.sh \"echo\" -a \"[1,2,3]\" | send_slurm.sh -j echo_array -t 1 -m 4G -n 2"
    echo ""
    exit 0
}

# Check if no arguments are provided
if [ $# -eq 0 ]; then
    usage
fi

# Check for help flag
for arg in "$@"; do
    if [ "$arg" == "--help" ] || [ "$arg" == "-h" ]; then
        detailed_help
    fi
done

# Initialize variables with default values
JOB_NAME="array_job"
TIME=1
MEM="6G"
NCPUS=1
NODES=1
ARRAY=""
ACCOUNT="rrg-brad"
NOX11=false
OMP_NUM_THREADS=1

# Parse send_slurm.sh arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--time)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                TIME="$2"
                shift 2
            else
                echo "Error: --time requires a value."
                usage
            fi
            ;;
        -m|--mem)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                MEM="$2"
                shift 2
            else
                echo "Error: --mem requires a value."
                usage
            fi
            ;;
        -n|--ncpus)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                NCPUS="$2"
                shift 2
            else
                echo "Error: --ncpus requires a value."
                usage
            fi
            ;;
        --nodes)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                NODES="$2"
                shift 2
            else
                echo "Error: --nodes requires a value."
                usage
            fi
            ;;
        -j|--name)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                JOB_NAME="$2"
                shift 2
            else
                echo "Error: --name requires a value."
                usage
            fi
            ;;
        -a|--array)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                ARRAY="$2"
                shift 2
            else
                echo "Error: --array requires a value."
                usage
            fi
            ;;
        --account)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                ACCOUNT="$2"
                shift 2
            else
                echo "Error: --account requires a value."
                usage
            fi
            ;;
        --nox11)
            NOX11=true
            shift
            ;;
        -o|--omp_num_threads)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                OMP_NUM_THREADS="$2"
                shift 2
            else
                echo "Error: --omp_num_threads requires a value."
                usage
            fi
            ;;
        *)
            echo "Error: Unknown option: $1"
            usage
            ;;
    esac
done

# Read commands from stdin and store in a temporary file
COMMANDS_FILE=$(mktemp)
trap 'rm -f "$COMMANDS_FILE"' EXIT

while IFS= read -r line; do
    # Ignore empty lines
    [[ -z "$line" ]] && continue
    echo "$line" >> "$COMMANDS_FILE"
done

# Check if commands file is not empty
if [[ ! -s "$COMMANDS_FILE" ]]; then
    echo "Error: No commands provided to submit."
    exit 1
fi

# Count the number of commands
NUM_COMMANDS=$(wc -l < "$COMMANDS_FILE" | xargs)

# Determine array indices
if [[ -n "$ARRAY" ]]; then
    ARRAY_PARAM="$ARRAY"
else
    # Set array indices from 1 to NUM_COMMANDS
    ARRAY_PARAM="1-$NUM_COMMANDS"
fi

# Create a temporary job script
JOB_SCRIPT=$(mktemp)
trap 'rm -f "$COMMANDS_FILE" "$JOB_SCRIPT"' EXIT

# Write the job script
{
    echo "#!/bin/bash"
    echo "#SBATCH --job-name=${JOB_NAME}"
    echo "#SBATCH --cpus-per-task=${NCPUS}"
    echo "#SBATCH --mem=${MEM}"
    echo "#SBATCH --nodes=${NODES}"
    echo "#SBATCH --account=${ACCOUNT}"
    echo "#SBATCH --time=${TIME}:00:00"  # Assuming TIME is in hours
    if [ "$NOX11" = true ]; then
        echo "#SBATCH --nox11"
    fi
    echo "#SBATCH --array=${ARRAY_PARAM}"
    echo "#SBATCH --output=${JOB_NAME}_%A_%a.out"
    echo "#SBATCH --error=${JOB_NAME}_%A_%a.err"
    echo ""
    echo "export OMP_NUM_THREADS=${OMP_NUM_THREADS}"
    echo "export MKL_NUM_THREADS=${OMP_NUM_THREADS}"
    echo ""
    echo "# Read the command corresponding to this array task"
    echo "COMMAND=\$(sed -n \"\${SLURM_ARRAY_TASK_ID}p\" \"$COMMANDS_FILE\")"
    echo "echo \"Executing: \$COMMAND\""
    echo "eval \"\$COMMAND\""
} > "$JOB_SCRIPT"

# Make the job script executable
chmod +x "$JOB_SCRIPT"

# Submit the job script with sbatch
sbatch \
    --job-name="${JOB_NAME}" \
    --cpus-per-task="${NCPUS}" \
    --mem="${MEM}" \
    --nodes="${NODES}" \
    --account="${ACCOUNT}" \
    --time="${TIME}:00:00" \
    $( [ "$NOX11" = true ] && echo "--nox11" ) \
    --array="${ARRAY_PARAM}" \
    --output="${JOB_NAME}_%A_%a.out" \
    --error="${JOB_NAME}_%A_%a.err" \
    "$JOB_SCRIPT"

# Clean up temporary files via trap
exit 0
