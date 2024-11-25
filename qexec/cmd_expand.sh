#!/bin/bash

# cmd_expand.sh
# This script generates a list of commands by expanding combinations of provided options and their values.
# It supports reading option values from files, CSV data frames, and handles glob patterns.
# It also supports a link mode to combine options by matching their positions.
#
# Usage:
#   cmd_expand.sh [--link] <base_command> [options and values]
#
# Arguments:
#   --link             Optional flag to enable link mode (combines options by matching positions).
#   <base_command>     The base command to be executed.
#   [options and values] Options and their corresponding values in a specific format.
#
# Options can be specified as:
#   -option [value1,value2,...]        Option with multiple values.
#   [value1,value2,...]                Unnamed arguments (without option flags).
#
# Special prefixes for values:
#   file:<filename>    Reads values from the specified file, one per line.
#   df:<column>:<file> Reads values from the specified column in a CSV file.
#   glob:<pattern>     Expands to match files using the specified glob pattern.
#
# Examples:
#   1. **Basic Usage Without Link Mode**
#      ```
#      ./cmd_expand.sh "echo" -a "[1,2,3]" "file:values.txt"
#      ```
#      **Generated Commands:**
#      ```
#      echo -a 1 A
#      echo -a 1 B
#      echo -a 2 A
#      echo -a 2 B
#      echo -a 3 A
#      echo -a 3 B
#      ```
#
#   2. **Using the `--link` Flag**
#      ```
#      ./cmd_expand.sh --link "echo" -a "[1,2,3]" "file:values.txt"
#      ```
#      **Generated Commands:**
#      ```
#      echo -a 1 A
#      echo -a 2 B
#      echo -a 3 B
#      ```
#
#   3. **Using Data Frame Input**
#      ```
#      ./cmd_expand.sh "run_analysis" -p "df:param:data.csv" -d "10,20"
#      ```
#      **Generated Commands:**
#      ```
#      run_analysis -p X -d 10
#      run_analysis -p Y -d 20
#      run_analysis -p Z -d 20
#      ```
#
#   4. **Using Glob Patterns**
#      ```
#      ./cmd_expand.sh "process_files" "glob:*.txt" -v "fast,slow"
#      ```
#      **Generated Commands:**
#      ```
#      process_files file1.txt -v fast
#      process_files file1.txt -v slow
#      process_files file2.txt -v fast
#      process_files file2.txt -v slow
#      ```
#
#   5. **Combining Multiple Options with and without `--link`**
#      ```
#      ./cmd_expand.sh "deploy" -e "dev,prod" -t "us,eu" "file:services.txt"
#      ```
#      **Generated Commands:**
#      ```
#      deploy -e dev -t us serviceA
#      deploy -e dev -t us serviceB
#      deploy -e dev -t eu serviceA
#      deploy -e dev -t eu serviceB
#      deploy -e prod -t us serviceA
#      deploy -e prod -t us serviceB
#      deploy -e prod -t eu serviceA
#      deploy -e prod -t eu serviceB
#      ```
#
#   6. **Handling Unequal Lengths with `--link` Flag**
#      ```
#      ./cmd_expand.sh --link "backup" -s "daily,weekly,monthly" "file:directories.txt"
#      ```
#      **Generated Commands:**
#      ```
#      backup -s daily /var/log
#      backup -s weekly /home/user
#      backup -s monthly /home/user
#      ```

# Exit immediately if a command exits with a non-zero status
set -e

#########################
# Function Definitions  #
#########################

# Function to display usage information
usage() {
    echo "Usage: $0 [--link] <base_command> [options and values]"
    echo ""
    echo "Arguments:"
    echo "  --link             Optional flag to enable link mode (combines options by matching positions)."
    echo "  <base_command>     The base command to be executed."
    echo "  [options and values] Options and their corresponding values in a specific format."
    echo ""
    echo "Options can be specified as:"
    echo "  -option [value1,value2,...]        Option with multiple values."
    echo "  [value1,value2,...]                Unnamed arguments (without option flags)."
    echo ""
    echo "Special prefixes for values:"
    echo "  file:<filename>    Reads values from the specified file, one per line."
    echo "  df:<column>:<file> Reads values from the specified column in a CSV file."
    echo "  glob:<pattern>     Expands to match files using the specified glob pattern."
    echo ""
    echo "Use '$0 --help' to display detailed examples."
    exit 1
}

# Function to display detailed examples
detailed_help() {
    usage
    echo ""
    echo "Examples:"
    echo "  1. **Basic Usage Without Link Mode**"
    echo "     \$ $0 \"echo\" -a \"[1,2,3]\" \"file:values.txt\""
    echo ""
    echo "  2. **Using the '--link' Flag**"
    echo "     \$ $0 --link \"echo\" -a \"[1,2,3]\" \"file:values.txt\""
    echo ""
    echo "  3. **Using Data Frame Input**"
    echo "     \$ $0 \"run_analysis\" -p \"df:param:data.csv\" -d \"10,20\""
    echo ""
    echo "  4. **Using Glob Patterns**"
    echo "     \$ $0 \"process_files\" \"glob:*.txt\" -v \"fast,slow\""
    echo ""
    echo "  5. **Combining Multiple Options with and without '--link'**"
    echo "     \$ $0 \"deploy\" -e \"dev,prod\" -t \"us,eu\" \"file:services.txt\""
    echo ""
    echo "  6. **Handling Unequal Lengths with '--link' Flag**"
    echo "     \$ $0 --link \"backup\" -s \"daily,weekly,monthly\" \"file:directories.txt\""
    exit 0
}

# Function to parse option values
parse_option_values() {
    local value_str="$1"
    local values=()

    # Remove surrounding square brackets and normalize commas
    value_str="$(echo "$value_str" | sed -e 's/^[[:space:]]*\[[[:space:]]*//' -e 's/[[:space:]]*\][[:space:]]*$//' -e 's/[[:space:]]*,[[:space:]]*/,/g')"

    # Check for special prefixes
    if [[ "$value_str" == file:* ]]; then
        local filename="${value_str#file:}"
        if [[ ! -f "$filename" ]]; then
            echo "Error: Specified file does not exist: $filename"
            exit 1
        fi
        mapfile -t values < "$filename"
    elif [[ "$value_str" == df:* ]]; then
        IFS=':' read -r _ column_name filename <<< "$value_str"
        if [[ ! -f "$filename" ]]; then
            echo "Error: Specified CSV file does not exist: $filename"
            exit 1
        fi
        # Extract the specified column using awk
        # Assumes that the CSV is well-formed with a header row
        header=$(head -n 1 "$filename")
        # Convert header to array
        IFS=',' read -r -a columns <<< "$header"
        # Find the index of the desired column
        col_index=-1
        for i in "${!columns[@]}"; do
            # Remove possible carriage return and spaces
            col=$(echo "${columns[i]}" | tr -d '\r' | xargs)
            if [[ "$col" == "$column_name" ]]; then
                col_index=$((i + 1))
                break
            fi
        done
        if [[ $col_index -eq -1 ]]; then
            echo "Error: Specified column '$column_name' does not exist in the CSV file."
            exit 1
        fi
        # Use awk to extract the column, skipping the header
        while IFS= read -r line; do
            # Handle possible quoted fields
            value=$(echo "$line" | awk -v col="$col_index" -F',' '{print $col}' | sed 's/^"//;s/"$//')
            values+=("$value")
        done < <(tail -n +2 "$filename")
    elif [[ "$value_str" == glob:* ]]; then
        local pattern="${value_str#glob:}"
        # Use globbing to expand the pattern
        shopt -s nullglob
        files=( $pattern )
        shopt -u nullglob
        if [ ${#files[@]} -eq 0 ]; then
            echo "Error: No files match the glob pattern '$pattern'."
            exit 1
        fi
        values=("${files[@]}")
    else
        # Split by commas
        IFS=',' read -ra values <<< "$value_str"
    fi

    # Remove any empty values and trim whitespace
    filtered_values=()
    for val in "${values[@]}"; do
        trimmed=$(echo "$val" | xargs)
        if [[ -n "$trimmed" ]]; then
            filtered_values+=("$trimmed")
        fi
    done

    echo "${filtered_values[@]}"
}

# Function to generate all combinations (non-link mode)
generate_combinations() {
    local -a options_names=("${!1}")
    local -a options_values=("${!2}")
    local -a result=()

    # Initialize with an empty string
    result=("")

    for ((i=0; i<${#options_names[@]}; i++)); do
        local opt_name="${options_names[$i]}"
        local opt_values=(${options_values[$i]})

        local temp=()
        for cmd in "${result[@]}"; do
            for val in "${opt_values[@]}"; do
                if [[ -z "$cmd" ]]; then
                    temp+=("$opt_name $val")
                else
                    temp+=("$cmd $opt_name $val")
                fi
            done
        done
        result=("${temp[@]}")
    done

    # Now handle unnamed arguments by appending them to each command
    if [[ ${#unnamed_args[@]} -gt 0 ]]; then
        local temp=()
        for cmd in "${result[@]}"; do
            for arg in "${unnamed_args[@]}"; do
                temp+=("$cmd $arg")
            done
        done
        result=("${temp[@]}")
    fi

    # Output the combinations
    for cmd in "${result[@]}"; do
        echo "$base_command $cmd"
    done
}

# Function to generate linked combinations
generate_linked_combinations() {
    local -a options_names=("${!1}")
    local -a options_values=("${!2}")
    local -a result=()

    # Determine the maximum number of values among all options
    local max_length=0
    for ((i=0; i<${#options_values[@]}; i++)); do
        local len=$(echo "${options_values[$i]}" | wc -w)
        if (( len > max_length )); then
            max_length=$len
        fi
    done

    # Expand each option's values to match max_length by repeating the last value
    declare -a expanded_options_values=()
    for ((i=0; i<${#options_values[@]}; i++)); do
        local opt_values=(${options_values[$i]})
        local len=${#opt_values[@]}
        if (( len < max_length )); then
            local last="${opt_values[-1]}"
            for ((j=len; j<max_length; j++)); do
                opt_values+=("$last")
            done
        fi
        expanded_options_values+=("${opt_values[@]}")
    done

    # Generate combinations by matching positions
    for ((k=0; k<max_length; k++)); do
        local cmd="$base_command"
        for ((i=0; i<${#options_names[@]}; i++)); do
            local opt_name="${options_names[$i]}"
            local val="${expanded_options_values[$((i*max_length + k))]}"
            cmd+=" $opt_name $val"
        done
        # Append unnamed arguments if any
        for arg in "${unnamed_args[@]}"; do
            cmd+=" $arg"
        done
        result+=("$cmd")
    done

    # Output the combinations
    for cmd in "${result[@]}"; do
        echo "$cmd"
    done
}

#########################
# Main Script Execution #
#########################

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

# Initialize variables
LINK_MODE=false
option_names=()
option_values=()
unnamed_args=()
base_command=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --link)
            LINK_MODE=true
            shift
            ;;
        -*)
            # Option flag
            OPTION_NAME="$1"
            shift
            # Collect the value(s) for this option
            OPTION_VALUE=""
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                OPTION_VALUE+="$1 "
                shift
            done
            OPTION_VALUE="${OPTION_VALUE%% }"  # Remove trailing space
            if [[ -z "$OPTION_VALUE" ]]; then
                echo "Error: No value provided for option '$OPTION_NAME'."
                usage
            fi
            # Parse the option value
            parsed_values=$(parse_option_values "$OPTION_VALUE")
            option_names+=("$OPTION_NAME")
            option_values+=("$parsed_values")
            ;;
        *)
            if [[ -z "$base_command" ]]; then
                base_command="$1"
            else
                unnamed_args+=("$1")
            fi
            shift
            ;;
    esac
done

# Validate base command
if [[ -z "$base_command" ]]; then
    echo "Error: No base command provided."
    usage
fi

# Generate combinations based on link mode
if $LINK_MODE; then
    generate_linked_combinations option_names[@] option_values[@]
else
    generate_combinations option_names[@] option_values[@]
fi


