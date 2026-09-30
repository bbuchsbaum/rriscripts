#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
# Supply account, CPUs, time, memory (except Trillium CPU), paths, and logs via CLI.
# Usage: sbatch [OPTIONS] cpu.sbatch /ABS/environment.sh EXECUTABLE [ARGUMENT ...]
set -euo pipefail
fail() { printf 'cpu.sbatch: %s\n' "$*" >&2; exit 64; }
(( $# >= 2 )) || fail 'need an absolute environment script and executable'
[[ -n ${SLURM_JOB_ID:-} ]] || fail 'run through a Slurm allocation, not on a login node'
[[ ${SLURM_NTASKS:-1} == 1 ]] || fail 'this template supports exactly one task'
[[ ${SLURM_JOB_NUM_NODES:-${SLURM_NNODES:-1}} == 1 ]] || fail 'this template supports exactly one node'
cpus=${SLURM_CPUS_PER_TASK:-}
[[ "$cpus" =~ ^[1-9][0-9]{0,5}$ ]] || fail 'request a positive --cpus-per-task explicitly'
environment=$1
shift
[[ "$environment" == /* && -f "$environment" && -r "$environment" ]] || fail 'environment script must be an absolute readable file'
umask 077
# This is trusted code: inspect/freeze it before submission.
# shellcheck source=/dev/null
source "$environment"
set -euo pipefail
threads=${THREADS_PER_WORKER:-1}
[[ "$threads" =~ ^[1-9][0-9]{0,5}$ ]] || fail 'THREADS_PER_WORKER must be a positive integer'
(( threads <= cpus )) || fail 'threads exceed the allocated CPU budget'
# These cap numerical-library threads, not application process-worker counts.
export OMP_NUM_THREADS="$threads" MKL_NUM_THREADS="$threads"
export OPENBLAS_NUM_THREADS="$threads" BLIS_NUM_THREADS="$threads"
export NUMEXPR_NUM_THREADS="$threads" NUMEXPR_MAX_THREADS="$threads"
export VECLIB_MAXIMUM_THREADS="$threads"
# Make the tested batch environment visible to the launched step.
export SLURM_EXPORT_ENV=ALL
printf 'job=%s host=%s cpus=%s library_threads=%s\n' \
    "$SLURM_JOB_ID" "$(hostname)" "$cpus" "$threads"
# No eval: preserve each supplied argument, including spaces and metacharacters.
srun --ntasks=1 --cpus-per-task="$cpus" "$@"
