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
#   1. Basic Usage Without Link Mode
#      ./cmd_expand.sh "echo" -a "[1,2,3]" "file:values.txt"
#
#   2. Using the `--link` Flag
#      ./cmd_expand.sh --link "echo" -a "[1,2,3]" "file:values.txt"
#
#   3. Using Data Frame Input
#      ./cmd_expand.sh "run_analysis" -p "df:param:data.csv" -d "10,20"
#
#   4. Using Glob Patterns
#      ./cmd_expand.sh "process_files" "glob:*.txt" -v "fast,slow"
#
#   5. Combining Multiple Options
#      ./cmd_expand.sh "deploy" -e "dev,prod" -t "us,eu" "file:services.txt"
#
#   6. Handling Unequal Lengths with `--link`
#      ./cmd_expand.sh --link "backup" -s "daily,weekly,monthly" "file:directories.txt"

set -e

#########################
# Function Definitions  #
#########################

usage() {
    cat <<EOF
Usage: $0 [--link] <base_command> [arguments...]

Generates a list of commands by expanding combinations of provided arguments.
Arguments can be named options (e.g., -f file.txt) or unnamed values.

Modes:
  Default: Generates the Cartesian product (all possible combinations) of values.
  --link:  Links arguments by position. Combines the first value of each argument,
           then the second, and so on. If lists have different lengths, the last
           item of shorter lists is repeated.

Arguments:
  <base_command>     The command prefix for each generated line.
  [arguments...]     One or more arguments. These can be:

    Named Options:
      -opt [value_spec]  An option flag followed by its value specification.
                         Example: -input [file1.txt,file2.txt]

    Unnamed Arguments:
      value_spec         A value specification without an option flag.
                         Example: [1,2,3] or just literal_value

Value Specification ([value_spec]):
  - Must be enclosed in square brackets [] to enable expansion.
  - Literal values (not in []) are treated as a single item.
  - Inside brackets, values can be:
      val1,val2,...    Comma-separated values.
      N..M or N:M      An inclusive integer range (e.g., 1..5, -3..3).
      file:<filename>  Values read line-by-line from <filename>.
      df:<col>:<file>  Values read from CSV <file>'s column <col>.
      glob:<pattern>   Files matching the shell <pattern> (e.g., *.txt).

Shell Quoting:
  IMPORTANT: Arguments containing special characters ([, ], *, etc.)
  must be quoted or escaped in your shell (especially zsh) to prevent
  unintended expansion before they reach this script.
  Example: $0 cmd '[1,2]' 'glob:*.csv' or $0 cmd "[1,2]" "glob:*.csv"

Use '$0 --help' for detailed examples.
EOF
    exit 1
}

detailed_help() {
    # Display basic usage first
    usage

    # Add detailed examples
    cat <<EOF

Examples:

  1. Basic Cartesian Product:
     # Generates: command -a 1 x, command -a 1 y, command -a 2 x, command -a 2 y
     $0 command -a '[1,2]' '[x,y]'

  2. Unnamed Arguments & Range:
     # Generates: process 1 -5, process 1 -4, ..., process 1 0, ..., process 3 5
     $0 process '[1..3]' '[-5..5]'

  3. Using File Input:
     # Reads values for -s from servers.txt and combines with env values
     $0 deploy -s '[file:servers.txt]' -e '[dev,prod]'

  4. Using Glob Pattern (Remember to Quote!):
     # Processes each .log file found
     $0 analyze '[glob:*.log]'

  5. Using CSV Data Frame:
     # Reads 'subject_id' column from data.csv
     $0 run_trial -s '[df:subject_id:data.csv]' -t '[fast,slow]'

  6. Link Mode (--link):
     # Generates: task -f file1.txt -p A, task -f file2.txt -p B, task -f file3.txt -p C
     $0 --link task -f '[file1.txt,file2.txt,file3.txt]' -p '[A,B,C]'

  7. Link Mode with Uneven Lists:
     # Generates: backup src1 daily, backup src2 weekly, backup src3 monthly, backup src4 monthly
     # Note: 'monthly' is repeated for the last item.
     $0 --link backup '[src1,src2,src3,src4]' '[daily,weekly,monthly]'

  8. Literal Unnamed Argument:
     # Generates: setup main_db primary, setup main_db replica
     $0 setup main_db '[primary,replica]'

EOF
    exit 0
}

parse_option_values() {
    local value_str="$1"
    local values=()

    # Remove leading/trailing spaces
    value_str="$(echo "$value_str" | xargs)"
    # Remove surrounding square brackets if present
    value_str="$(echo "$value_str" | sed -e 's/^\[//; s/\]$//')"

    # Handle special prefixes
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
        # Extract the specified column
        header=$(head -n 1 "$filename")
        IFS=',' read -r -a columns <<< "$header"
        col_index=-1
        for i in "${!columns[@]}"; do
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
        while IFS= read -r line; do
            value=$(echo "$line" | awk -v col="$col_index" -F',' '{print $col}' | sed 's/^"//;s/"$//')
            values+=("$value")
        done < <(tail -n +2 "$filename")
    elif [[ "$value_str" == glob:* ]]; then
        local pattern="${value_str#glob:}"
        shopt -s nullglob
        files=( $pattern )
        shopt -u nullglob
        if [ ${#files[@]} -eq 0 ]; then
            echo "Error: No files match the glob pattern '$pattern'."
            exit 1
        fi
        values=("${files[@]}")
    else
        # Check for range expansion (e.g. 1..100 or 1:100 or -5..5)
        if [[ "$value_str" =~ ^(-?[0-9]+)(\.\.|:)(-?[0-9]+)$ ]]; then
            start=${BASH_REMATCH[1]}
            end=${BASH_REMATCH[3]}
            if (( start <= end )); then
                for ((num=start; num<=end; num++)); do
                    values+=("$num")
                done
            else
                for ((num=start; num>=end; num--)); do
                    values+=("$num")
                done
            fi
        else
            # Split by commas
            IFS=',' read -ra values <<< "$value_str"
        fi
    fi

    # Trim whitespace and remove empty entries
    filtered_values=()
    for val in "${values[@]}"; do
        trimmed=$(echo "$val" | xargs)
        if [[ -n "$trimmed" ]]; then
            filtered_values+=("$trimmed")
        fi
    done

    echo "${filtered_values[@]}"
}

generate_combinations() {
    local -a all_option_names=("${!1}")
    local -a all_option_values=("${!2}")
    local result=("")

    # Cartesian product of all options
    for ((i=0; i<${#all_option_names[@]}; i++)); do
        local opt_name="${all_option_names[$i]}"
        local opt_values=(${all_option_values[$i]})
        local temp=()
        for cmd in "${result[@]}"; do
            for val in "${opt_values[@]}"; do
                if [[ -n "$opt_name" ]]; then
                    temp+=("$cmd $opt_name $val")
                else
                    # Unnamed argument
                    temp+=("$cmd $val")
                fi
            done
        done
        result=("${temp[@]}")
    done

    # Output the combinations
    for cmd in "${result[@]}"; do
        echo "$base_command $cmd" | xargs
    done
}

generate_linked_combinations() {
    local -a all_option_names=("${!1}")
    local -a all_option_values=("${!2}")
    local max_length=0

    # Find max length
    for vals in "${all_option_values[@]}"; do
        local count=$(echo "$vals" | wc -w)
        (( count > max_length )) && max_length=$count
    done

    # Expand all arrays to max_length by repeating last value
    local expanded_values=()
    for vals in "${all_option_values[@]}"; do
        local arr=($vals)
        local len=${#arr[@]}
        if (( len < max_length )); then
            local last="${arr[-1]}"
            for (( j=len; j<max_length; j++ )); do
                arr+=("$last")
            done
        fi
        expanded_values+=("$(echo "${arr[@]}")")
    done

    # Build commands line by line
    for (( idx=0; idx<max_length; idx++ )); do
        cmd="$base_command"
        for (( i=0; i<${#all_option_names[@]}; i++ )); do
            local opt_name="${all_option_names[$i]}"
            local arr=(${expanded_values[$i]})
            local val="${arr[$idx]}"
            if [[ -n "$opt_name" ]]; then
                cmd+=" $opt_name $val"
            else
                cmd+=" $val"
            fi
        done
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

LINK_MODE=false
base_command=""
raw_options=()
unnamed_raw_values=()

# First pass: extract --link and base_command
while [[ $# -gt 0 ]]; do
    case "$1" in
        --link)
            LINK_MODE=true
            shift
            ;;
        -*)
            # This is an option, let's push it to raw_options to handle after
            raw_options+=("$1")
            shift
            if [[ $# -gt 0 && ! "$1" =~ ^- ]]; then
                raw_options+=("$1")
                shift
            else
                echo "Error: No value provided for option '$1'."
                usage
            fi
            ;;
        *)
            if [[ -z "$base_command" ]]; then
                base_command="$1"
                shift
            else
                unnamed_raw_values+=("$1")
                shift
            fi
            ;;
    esac
done

if [[ -z "$base_command" ]]; then
    echo "Error: No base command provided."
    usage
fi

option_names=()
option_values=()

# Parse option arguments
i=0
while (( i < ${#raw_options[@]} )); do
    opt="${raw_options[$i]}"
    ((i++))
    val="${raw_options[$i]}"
    ((i++))

    parsed_values=$(parse_option_values "$val")
    option_names+=("$opt")
    option_values+=("$parsed_values")
done

# Parse unnamed arguments
# Each unnamed argument source is treated as a separate option without a name
if (( ${#unnamed_raw_values[@]} > 0 )); then
    for uval in "${unnamed_raw_values[@]}"; do
        # Check if the argument is wrapped in [] for expansion
        if [[ "$uval" == \[* && "$uval" == *\] ]]; then
            parsed_values=$(parse_option_values "$uval")
        else
            # Treat as a literal value
            parsed_values="$uval"
        fi

        if [[ -n "$parsed_values" ]]; then # Ensure we don't add empty sets
            option_names+=("")
            option_values+=("$parsed_values")
        fi
    done
fi

if $LINK_MODE; then
    generate_linked_combinations option_names[@] option_values[@]
else
    generate_combinations option_names[@] option_values[@]
fi
