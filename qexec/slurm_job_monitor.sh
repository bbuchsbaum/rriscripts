#!/bin/bash
set -euo pipefail

# slurm_job_monitor.sh
# This script monitors SLURM jobs, periodically displaying runtime,
# CPU and memory usage. When jobs finish, it summarizes efficiency
# using 'seff'. Optionally an email or desktop notification can be
# sent with the final results.
#
# Usage:
#   slurm_job_monitor.sh [options] [jobid ...]
#
# Options:
#   -i, --interval SECONDS   Polling interval in seconds (default: 60).
#   -e, --email ADDRESS      Email address for completion summary.
#   -n, --notify             Send desktop notification with notify-send.
#   -h, --help               Display help information.
#
# If no job IDs are provided, the script monitors jobs submitted by the
# current user within the last 30 minutes.

usage() {
    echo "Usage: $0 [options] [jobid ...]"
    echo ""
    echo "Options:"
    echo "  -i, --interval SECONDS   Polling interval in seconds (default: 60)."
    echo "  -e, --email ADDRESS      Email address for completion summary."
    echo "  -n, --notify             Send desktop notification with notify-send."
    echo "  -h, --help               Display help information."
    echo ""
    echo "If no job IDs are provided, recent jobs from the last 30 minutes are monitored."
    exit 1
}

require_command() {
    local name="$1"
    if ! command -v "$name" >/dev/null 2>&1; then
        echo "Error: required command '$name' was not found in PATH." >&2
        exit 1
    fi
}

thirty_minutes_ago() {
    if date -d '-30 minutes' +%Y-%m-%dT%H:%M:%S >/dev/null 2>&1; then
        date -d '-30 minutes' +%Y-%m-%dT%H:%M:%S
        return
    fi

    python3 - <<'PY'
from datetime import datetime, timedelta
print((datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"))
PY
}

#########################
# Argument Parsing      #
#########################

interval=60
email=""
notify=false
job_ids=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interval)
            interval="$2"; shift 2 ;;
        -e|--email)
            email="$2"; shift 2 ;;
        -n|--notify)
            notify=true; shift ;;
        -h|--help)
            usage ;;
        *)
            job_ids+=("$1"); shift ;;
    esac
done

if ! [[ "$interval" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --interval must be a positive integer." >&2
    exit 1
fi

require_command sacct
require_command squeue

#########################
# Determine Job IDs     #
#########################

if [[ ${#job_ids[@]} -eq 0 ]]; then
    start_time="$(thirty_minutes_ago)"
    while IFS= read -r job_id; do
        [[ -z "$job_id" ]] && continue
        job_ids+=("$job_id")
    done < <(sacct -u "$USER" --starttime "$start_time" \
        --format=JobID --noheader | awk '{print $1}' | grep -E '^[0-9]+' | sort -u)
fi

if [[ ${#job_ids[@]} -eq 0 ]]; then
    echo "No jobs to monitor." >&2
    exit 1
fi

#########################
# Monitoring Loop       #
#########################

declare -A completed
summaries=()

while (( ${#completed[@]} < ${#job_ids[@]} )); do
    for job in "${job_ids[@]}"; do
        if [[ -n ${completed[$job]:-} ]]; then
            continue
        fi
        state="$(squeue -j "$job" -h -o '%T' 2>/dev/null || true)"
        if [[ -z "$state" ]]; then
            echo "Job $job finished."
            if command -v seff >/dev/null 2>&1; then
                seff_output="$(seff "$job" 2>&1 || true)"
            else
                seff_output="seff not available; install or load the Slurm efficiency tools to get a completion summary."
            fi
            echo "$seff_output"
            summaries+=("Job $job summary:\n$seff_output\n")
            completed[$job]=1
        else
            runtime="$(squeue -j "$job" -h -o '%M' 2>/dev/null || true)"
            cpu=""
            mem=""
            if [[ "$state" == "RUNNING" ]]; then
                stats="$(sstat -j "${job}.batch" -P -o AveCPU,AveRSS 2>/dev/null | tail -n1 || true)"
                cpu=$(echo "$stats" | cut -d'|' -f1)
                mem=$(echo "$stats" | cut -d'|' -f2)
            fi
            echo "Job $job: $state TIME=$runtime CPU=$cpu MEM=$mem"
        fi
    done
    sleep "$interval"
    echo "---"
done

#########################
# Final Notification    #
#########################

summary=$(printf '%b\n' "${summaries[@]}")

if [[ -n "$email" ]]; then
    if command -v mail >/dev/null 2>&1; then
        echo -e "$summary" | mail -s "SLURM job summary" "$email"
    else
        echo "mail command not found; unable to send email." >&2
    fi
fi

if [[ "$notify" == true ]]; then
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "SLURM job summary" "$summary"
    else
        echo "notify-send not found; unable to send desktop notification." >&2
    fi
fi

exit 0
