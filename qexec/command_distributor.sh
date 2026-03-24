#!/bin/bash
set -euo pipefail

# command_distributor.sh
# Run the slice of a commands file assigned to the current SLURM array task.
# Blank lines are ignored. The selected commands are streamed to GNU parallel.
#
# Usage:
#   command_distributor.sh <commands_file_path> <number_of_batches> [jobs_per_batch]

usage() {
    echo "Usage: $0 <commands_file_path> <number_of_batches> [jobs_per_batch]"
    echo "Example: $0 commands.txt 4 20"
    exit 1
}

require_positive_int() {
    local label="$1"
    local value="$2"
    if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: ${label} must be a positive integer." >&2
        exit 1
    fi
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
fi

commands_file="$1"
number_of_batches="$2"
jobs_per_batch="${3:-40}"
parallel_bin="${QEXEC_PARALLEL_BIN:-parallel}"

if [[ ! -f "$commands_file" ]]; then
    echo "Error: Commands file '$commands_file' does not exist." >&2
    exit 1
fi

require_positive_int "number_of_batches" "$number_of_batches"
require_positive_int "jobs_per_batch" "$jobs_per_batch"

if [[ -z "${SLURM_ARRAY_TASK_ID:-}" ]]; then
    echo "Error: SLURM_ARRAY_TASK_ID environment variable is not set." >&2
    exit 1
fi

batch_index="$SLURM_ARRAY_TASK_ID"
require_positive_int "SLURM_ARRAY_TASK_ID" "$batch_index"

if (( batch_index > number_of_batches )); then
    echo "Error: SLURM_ARRAY_TASK_ID ($batch_index) is out of range (1-$number_of_batches)." >&2
    exit 1
fi

if ! command -v "$parallel_bin" >/dev/null 2>&1; then
    echo "Error: GNU parallel is required but '$parallel_bin' was not found in PATH." >&2
    exit 1
fi

commands=()
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line//[[:space:]]/}" ]] && continue
    commands+=("$line")
done < "$commands_file"

total_commands="${#commands[@]}"

if (( total_commands == 0 )); then
    echo "Error: Commands file '$commands_file' is empty after removing blank lines." >&2
    exit 1
fi

lines_per_batch=$(( (total_commands + number_of_batches - 1) / number_of_batches ))
start_line=$(( (batch_index - 1) * lines_per_batch ))
end_line=$(( batch_index * lines_per_batch ))
if (( end_line > total_commands )); then
    end_line=$total_commands
fi

commands_subset=("${commands[@]:start_line:end_line - start_line}")

if (( ${#commands_subset[@]} == 0 )); then
    echo "No commands to execute for batch $batch_index."
    exit 0
fi

echo "Executing batch $batch_index: ${#commands_subset[@]} commands with $jobs_per_batch concurrent jobs."

printf '%s\n' "${commands_subset[@]}" | "$parallel_bin" --jobs "$jobs_per_batch"
