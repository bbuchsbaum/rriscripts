#!/bin/bash

# command_distributor.sh
# This script distributes and executes a subset of commands from a command file based on the SLURM_ARRAY_TASK_ID.
# It reads the specified portion of the commands and executes them using GNU Parallel.
#
# Usage:
#   command_distributor.sh <commands_file_path> <number_of_batches> [jobs_per_batch]
#
# Arguments:
#   <commands_file_path>  Path to the file containing the list of commands.
#   <number_of_batches>   Total number of batches (should match the SLURM array job size).
#   [jobs_per_batch]      Optional. Number of concurrent jobs to run in GNU Parallel (default: 40).

# Exit immediately if a command exits with a non-zero status
set -e

# Function to display usage information
usage() {
    echo "Usage: $0 <commands_file_path> <number_of_batches> [jobs_per_batch]"
    echo ""
    echo "Arguments:"
    echo "  <commands_file_path>  Path to the file containing the list of commands."
    echo "  <number_of_batches>   Total number of batches (should match the SLURM array job size)."
    echo "  [jobs_per_batch]      Optional. Number of concurrent jobs to run in GNU Parallel (default: 40)."
    echo ""
    echo "Example:"
    echo "  $0 commands.txt 4 20"
    exit 1
}

# Check if the correct number of arguments is provided
if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
fi

# Assign arguments to variables
commands_file="$1"
number_of_batches="$2"
jobs_per_batch="${3:-40}"  # Default to 40 if not provided

# Validate commands_file existence
if [[ ! -f "$commands_file" ]]; then
    echo "Error: Commands file '$commands_file' does not exist."
    exit 1
fi

# Get the SLURM_ARRAY_TASK_ID from the environment
if [[ -z "$SLURM_ARRAY_TASK_ID" ]]; then
    echo "Error: SLURM_ARRAY_TASK_ID environment variable is not set."
    exit 1
fi

batch_index="$SLURM_ARRAY_TASK_ID"

# Validate batch_index
if (( batch_index < 1 || batch_index > number_of_batches )); then
    echo "Error: SLURM_ARRAY_TASK_ID ($batch_index) is out of range (1-$number_of_batches)."
    exit 1
fi

# Read all commands into an array
mapfile -t commands < "$commands_file"
total_commands="${#commands[@]}"

# Calculate lines per batch (ceil division)
lines_per_batch=$(( (total_commands + number_of_batches - 1) / number_of_batches ))

# Determine start and end lines for this batch
start_line=$(( (batch_index - 1) * lines_per_batch ))
end_line=$(( batch_index * lines_per_batch ))
if (( end_line > total_commands )); then
    end_line=$total_commands
fi

# Extract the subset of commands for this batch
commands_subset=("${commands[@]:start_line:end_line - start_line}")

# Check if there are commands to execute
if (( ${#commands_subset[@]} == 0 )); then
    echo "No commands to execute for batch $batch_index."
    exit 0
fi

# Create a temporary file to store the subset of commands
temp_file=$(mktemp)
trap 'rm -f "$temp_file"' EXIT

# Write commands to the temporary file
for cmd in "${commands_subset[@]}"; do
    echo "$cmd" >> "$temp_file"
done

# Execute the subset of commands using GNU Parallel
echo "Executing batch $batch_index: ${#commands_subset[@]} commands with $jobs_per_batch concurrent jobs."
parallel --jobs "$jobs_per_batch" < "$temp_file"
