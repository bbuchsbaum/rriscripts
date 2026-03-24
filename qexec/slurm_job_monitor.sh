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

is_completed() {
    local job_id="$1"
    case " ${completed_jobs:-} " in
        *" ${job_id} "*) return 0 ;;
        *) return 1 ;;
    esac
}

# Check whether a job has truly finished by querying sacct for a terminal state.
# Returns 0 (true) if the job is in a terminal state, 1 otherwise.
# Sets JOB_FINAL_STATE to the state string.
check_job_finished() {
    local job_id="$1"
    JOB_FINAL_STATE=""

    # sacct is authoritative — squeue can be transiently empty
    local state
    state="$(sacct -j "$job_id" --noheader --parsable2 \
        --format=State | head -n1 | cut -d'|' -f1 || true)"

    case "$state" in
        COMPLETED|FAILED|CANCELLED|CANCELLED+|TIMEOUT|PREEMPTED|NODE_FAIL|OUT_OF_MEMORY|DEADLINE)
            JOB_FINAL_STATE="$state"
            return 0 ;;
        *)
            return 1 ;;
    esac
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
            if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value." >&2; usage; fi
            interval="$2"; shift 2 ;;
        -e|--email)
            if [[ $# -lt 2 ]]; then echo "Error: $1 requires a value." >&2; usage; fi
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
    # Only pick up parent job IDs (pure digits), not array sub-tasks (digits_digits)
    while IFS= read -r job_id; do
        [[ -z "$job_id" ]] && continue
        job_ids+=("$job_id")
    done < <(sacct -u "$USER" --starttime "$start_time" \
        --format=JobID --noheader | awk '{print $1}' | grep -E '^[0-9]+$' | sort -u)
fi

if [[ ${#job_ids[@]} -eq 0 ]]; then
    echo "No jobs to monitor." >&2
    exit 1
fi

echo "Monitoring ${#job_ids[@]} job(s): ${job_ids[*]}"
echo "Poll interval: ${interval}s"
echo "---"

#########################
# Monitoring Loop       #
#########################

completed_jobs=""
completed_count=0
summaries=()

# Print partial results on Ctrl-C
trap 'echo ""; echo "Interrupted. Partial results:"; \
      if [[ ${#summaries[@]} -gt 0 ]]; then printf "%b\n" "${summaries[@]}"; \
      else echo "  (no jobs completed yet)"; fi; exit 130' INT TERM

while (( completed_count < ${#job_ids[@]} )); do
    for job in "${job_ids[@]}"; do
        if is_completed "$job"; then
            continue
        fi

        # First check squeue for running/pending status
        state="$(squeue -j "$job" -h -o '%T' 2>/dev/null || true)"

        if [[ -z "$state" ]]; then
            # squeue is empty — verify with sacct that the job truly finished
            # (avoids race condition during job startup or scheduler hiccups)
            if check_job_finished "$job"; then
                echo "Job $job finished ($JOB_FINAL_STATE)."
                if command -v seff >/dev/null 2>&1; then
                    seff_output="$(seff "$job" 2>&1 || true)"
                else
                    seff_output="seff not available; install or load the Slurm efficiency tools to get a completion summary."
                fi
                echo "$seff_output"
                summaries+=("$(printf 'Job %s (%s):\n%s\n' "$job" "$JOB_FINAL_STATE" "$seff_output")")
                completed_jobs="${completed_jobs} ${job}"
                completed_count=$((completed_count + 1))
            else
                # Not in squeue but sacct doesn't show terminal state — transient, retry next poll
                echo "Job $job: state unclear (not in squeue, sacct shows non-terminal) — will retry"
            fi
        else
            runtime="$(squeue -j "$job" -h -o '%M' 2>/dev/null || true)"
            cpu=""
            mem=""
            if [[ "$state" == "RUNNING" ]]; then
                # For array jobs, sstat needs the sub-task ID; for regular jobs, use .batch
                local_stats=""
                if [[ "$job" =~ _[0-9]+$ ]]; then
                    # Array sub-task: use as-is with .batch
                    local_stats="$(sstat -j "${job}.batch" -P -o AveCPU,AveRSS 2>/dev/null | tail -n1 || true)"
                else
                    # Try parent.batch first, then without suffix
                    local_stats="$(sstat -j "${job}.batch" -P -o AveCPU,AveRSS 2>/dev/null | tail -n1 || true)"
                fi
                if [[ -n "$local_stats" ]]; then
                    cpu=$(echo "$local_stats" | cut -d'|' -f1)
                    mem=$(echo "$local_stats" | cut -d'|' -f2)
                fi
            fi
            echo "Job $job: $state  TIME=$runtime  CPU=${cpu:--}  MEM=${mem:--}"
        fi
    done

    # Only sleep if there are still jobs to monitor
    if (( completed_count < ${#job_ids[@]} )); then
        sleep "$interval"
        echo "---"
    fi
done

#########################
# Final Notification    #
#########################

echo ""
echo "=== All ${#job_ids[@]} job(s) complete ==="

if [[ ${#summaries[@]} -gt 0 ]]; then
    summary=$(printf '%s\n' "${summaries[@]}")
else
    summary="All jobs completed (no summaries available)."
fi

if [[ -n "$email" ]]; then
    if command -v mail >/dev/null 2>&1; then
        echo "$summary" | mail -s "SLURM job summary" "$email"
        echo "Summary emailed to $email."
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
