#!/usr/bin/env bash
# Read-only evidence collection. No submissions, filesystem mutation, or network tests.
# Usage: bash probe.sh [EXISTING_WORKDIR]
set -euo pipefail
if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [existing-workdir]\n' "$0" >&2; exit 64
fi
workdir=${1:-$PWD}
if [[ ! -d "$workdir" ]]; then
    printf 'Work directory does not exist: %s\n' "$workdir" >&2; exit 64
fi
seconds=${ALLIANCE_PROBE_TIMEOUT:-15}
if ! [[ "$seconds" =~ ^[1-9][0-9]?$ ]]; then
    printf 'ALLIANCE_PROBE_TIMEOUT must be an integer from 1 to 99.\n' >&2; exit 64
fi
if [[ -n ${ALLIANCE_PROBE_QOS:-} ]] && ! [[ "$ALLIANCE_PROBE_QOS" =~ ^[A-Za-z0-9_.+-]+$ ]]; then
    printf 'Invalid ALLIANCE_PROBE_QOS name.\n' >&2; exit 64
fi
if ! command -v timeout >/dev/null 2>&1; then
    printf 'GNU timeout is required for bounded probing; no queries run.\n' >&2; exit 2
fi
warnings=0
run() {
    local label=$1 output rc=0
    shift
    printf '\n## %s\n' "$label"
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'UNAVAILABLE: %s\n' "$1"
        warnings=$((warnings + 1)); return 0
    fi
    output=$(timeout --signal=TERM --kill-after=2s "${seconds}s" "$@" 2>&1) || rc=$?
    # Consume all captured output, but avoid flooding an agent's context.
    if ! printf '%s\n' "$output" | awk '
        NR<=120 {print}
        END {if(NR>120) {print "INCOMPLETE: output truncated; inspect selected records separately"; exit 1}}
    '; then
        warnings=$((warnings + 1))
    fi
    if (( rc != 0 )); then
        printf 'INCOMPLETE: exit=%s\n' "$rc"
        warnings=$((warnings + 1))
    fi
}
user=$(id -un)
printf '# Alliance cluster evidence — not submission approval\n'
printf 'UTC=%s\nUser=%s\nCC_CLUSTER=%s\n' "$(date -u +%FT%TZ)" "$user" "${CC_CLUSTER:-UNSET}"
printf 'Workdir=%s\nHOME=%s\nSCRATCH=%s\n' "$workdir" "$HOME" "${SCRATCH:-UNSET}"
printf 'Inherited SBATCH variable NAMES only: '
# Deliberately do not print values or the full environment.
printf '%s\n' "${!SBATCH_@}"
run 'Host' hostname -f
run 'Slurm client version' sbatch --version
run 'Own account associations and inherited association fields' \
    sacctmgr -nP show assoc where "user=$user" \
    format=Cluster,Account,User,Partition,QOS,DefaultQOS,MaxJobs,MaxSubmitJobs,MaxWall,GrpTRES
run 'Own fairshare context (not a queue-time prediction)' sshare -U
run 'Exact grouped profiles: partition|up|time|nodes|CPUs|RAM_MiB|S:C:T|GRES|features' \
    sinfo -h -e -o '%P|%a|%l|%D|%c|%m|%z|%G|%f'
run 'Partition definitions (visibility does not establish access)' scontrol -o show partition
run 'Selected scheduler constants (global limits are not user limits)' bash -c \
    'set -o pipefail; scontrol show config | awk "/^[[:space:]]*(ClusterName|SlurmctldVersion|MaxArraySize|MaxJobCount|SelectType|SelectTypeParameters|SchedulerType|SchedulerParameters)[[:space:]]*=/"'
if [[ -n ${ALLIANCE_PROBE_QOS:-} ]]; then
    run 'Selected QOS; also inspect relevant parent/group policy' \
        sacctmgr -nP show qos where "name=$ALLIANCE_PROBE_QOS" \
        format=Name,Flags,MaxWall,MaxJobsPU,MaxSubmitJobsPU,MaxTRESPU,GrpTRES
else
    printf '\nQOS details not queried: select an authorized QOS first.\n'
fi
run 'Own queued jobs (bounded display)' squeue -u "$user" -h \
    -o '%i|%j|%a|%P|%T|%M|%l|%C|%R'
paths=("$HOME" "$workdir")
if [[ -n ${SCRATCH:-} && -d "$SCRATCH" && "$SCRATCH" != "$workdir" && "$SCRATCH" != "$HOME" ]]; then
    paths+=("$SCRATCH")
fi
run 'Filesystem capacity — NOT your quota' df -hP "${paths[@]}"
run 'Filesystem inodes — NOT your quota' df -iP "${paths[@]}"
run 'Workdir mount on THIS host; does not describe compute-node temp' \
    findmnt -T "$workdir" -n -o TARGET,FSTYPE,SOURCE
run 'Site disk usage/quota report (if installed)' diskusage_report
printf '\nUNVERIFIED: effective parent/QOS policy, current notices, purge/backup rules,\n'
printf 'automation authorization, compute-node temp mounts/egress, application validity.\n'
printf 'Incomplete diagnostics=%s. Keep a selected summary; do not treat blanks as unlimited.\n' "$warnings"
if (( warnings > 0 )); then exit 2; fi
