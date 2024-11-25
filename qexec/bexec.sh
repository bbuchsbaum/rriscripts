#!/bin/bash

# bexec.sh
# This script submits a batch job to SLURM using 'qexec.sh' to execute 'command_distributor.sh' as an array job.
# It reads a command file and submits an array job that distributes and executes the commands across nodes.
#
# Usage:
#   bexec.sh [options]
#
# Options:
#   -f, --file       Path to the file containing the list of commands (required).
#   -n, --nodes      Number of nodes/batches (default: 1).
#       --time       Time for each job in hours (default: 1).
#       --ncpus      Number of CPUs per job (default: 40).
#       --mem        Memory per job (default: "6G").
#   -j, --jobs       Maximum number of tasks executed concurrently on a node (default: 40).
#
# Arguments:
#   None
#
# Examples:
#
#   1. **Basic Submission with Default Parameters**
#      ```
#      ./bexec.sh -f commands.txt
#      ```
#
#   2. **Submitting to Multiple Nodes with Specific CPU Allocation**
#      ```
#      ./bexec.sh -f commands.txt -n 4 --ncpus 20
#      ```
#
#   3. **Limiting Concurrent Jobs on Each Node**
#      ```
#      ./bexec.sh -f commands.txt -n 2 --ncpus 10 -j 20
#      ```
#
#   ... (Other examples as per original bexec.R documentation)

# Exit immediately if a command exits with a non-zero status
set -e

#########################
# Function Definitions  #
#########################

# Function to display usage information
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -f, --file       Path to the file containing the list of commands (required)."
    echo "  -n, --nodes      Number of nodes/batches (default: 1)."
    echo "      --time       Time for each job in hours (default: 1)."
    echo "      --ncpus      Number of CPUs per job (default: 40)."
    echo "      --mem        Memory per job (default: \"6G\")."
    echo "  -j, --jobs       Maximum number of tasks executed concurrently on a node (default: 40)."
    echo "  -h, --help       Display help information."
    echo ""
    echo "Example:"
    echo "  $0 -f commands.txt -n 4 --ncpus 20 -j 20 --mem \"12G\" --time 2"
    exit 1
}

# Function to display detailed help
detailed_help() {
    usage
    echo ""
    echo "Examples:"
    echo "  1. **Basic Submission with Default Parameters**"
    echo "     \$ $0 -f commands.txt"
    echo ""
    echo "  2. **Submitting to Multiple Nodes with Specific CPU Allocation**"
    echo "     \$ $0 -f commands.txt -n 4 --ncpus 20"
    echo ""
    echo "  3. **Limiting Concurrent Jobs on Each Node**"
    echo "     \$ $0 -f commands.txt -n 2 --ncpus 10 -j 20"
    echo ""
    echo "  ... (Additional examples as per original bexec.R documentation)"
    exit 0
}

# Function to parse command-line arguments
parse_args() {
    # Initialize default values
    nodes=1
    time=1
    ncpus=40
    mem="6G"
    jobs=40
    commands_file=""
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--file)
                if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                    commands_file="$2"
                    shift 2
                else
                    echo "Error: --file requires a non-empty option argument."
                    usage
                fi
                ;;
            -n|--nodes)
                if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                    nodes="$2"
                    shift 2
                else
                    echo "Error: --nodes requires a positive integer."
                    usage
                fi
                ;;
            --time)
                if [[ -n "$2" && "$2" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
                    time="$2"
                    shift 2
                else
                    echo "Error: --time requires a positive number."
                    usage
                fi
                ;;
            --ncpus)
                if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                    ncpus="$2"
                    shift 2
                else
                    echo "Error: --ncpus requires a positive integer."
                    usage
                fi
                ;;
            --mem)
                if [[ -n "$2" && "$2" =~ ^[0-9]+[KMG]$ ]]; then
                    mem="$2"
                    shift 2
                else
                    echo "Error: --mem requires a value like '6G', '12G', etc."
                    usage
                fi
                ;;
            -j|--jobs)
                if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                    jobs="$2"
                    shift 2
                else
                    echo "Error: --jobs requires a positive integer."
                    usage
                fi
                ;;
            -h|--help)
                detailed_help
                ;;
            *)
                echo "Error: Unknown option: $1"
                usage
                ;;
        esac
    done
    
    # Check if commands_file is provided
    if [[ -z "$commands_file" ]]; then
        echo "Error: The --file option is required."
        usage
    fi
    
    # Validate commands_file existence
    if [[ ! -f "$commands_file" ]]; then
        echo "Error: Commands file '$commands_file' does not exist."
        exit 1
    fi
}

# Function to construct and execute the qexec.sh command
execute_qexec() {
    # Determine the number of commands
    total_commands=$(wc -l < "$commands_file" | xargs)
    
    if [[ $total_commands -eq 0 ]]; then
        echo "Error: Commands file '$commands_file' is empty."
        exit 1
    fi
    
    # Construct the qexec.sh command
    qexec_cmd="./qexec.sh --time ${time} --mem ${mem} --ncpus ${ncpus} --nodes ${nodes} --array=1-${nodes} ./command_distributor.sh ${commands_file} ${nodes} ${jobs}"
    
    echo "Submitting array job with the following command:"
    echo "$qexec_cmd"
    
    # Execute the qexec.sh command
    eval "$qexec_cmd"
}

#########################
# Main Script Execution #
#########################

# Parse the command-line arguments
parse_args "$@"

# Execute the qexec.sh command to submit the job
execute_qexec
