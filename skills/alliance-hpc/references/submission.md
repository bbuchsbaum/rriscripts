# Submission recipes

These are **adaptable recipes**, not authorization to submit. Set account, run paths, resource sizes, and a tested environment first. Default to the site's normal selection mechanism; add a partition or QOS only when required and verified. Source keys: [sources.md](sources.md).

## 1. One-node R/Python analysis

`templates/cpu.sbatch` accepts a trusted environment script followed by an executable and its arguments. It preserves argument boundaries, defaults numerical-library threads to one, and launches one Slurm task. Set `THREADS_PER_WORKER` in the environment script only for intentional threading. Set the analysis's process-worker count separately; allocating CPUs does not configure it. [S11,S12]

Prepare an immutable run directory containing the template, environment, analysis, and manifest. Record code/dependency versions. On Trillium, **also `cd` to that scratch run directory**. `RUN` below is absolute; the example assumes 8 CPUs and 32G are justified.

```bash
set -euo pipefail
umask 077
: "${ACCOUNT:?Select a verified project account}"
: "${RUN:?Set an absolute, writable, frozen run directory}"
: "${RUN_ID:?Set a unique run label}"
: "${CLUSTER:?Set the verified scheduler cluster name}"
[[ "$RUN" == /* ]] || { printf 'RUN must be absolute.\n' >&2; exit 64; }
cd "$RUN"
mkdir -p "$RUN/logs"
common=(--account="$ACCOUNT" --nodes=1 --ntasks=1
        --time=01:00:00 --job-name="analysis-$RUN_ID"
        --chdir="$RUN" --output="$RUN/logs/%j.out" --error="$RUN/logs/%j.err")
resources=(--cpus-per-task=8 --mem=32G)  # Shared-node systems only.
payload=("$RUN/cpu.sbatch" "$RUN/environment.sh"
         Rscript --vanilla "$RUN/analysis.R" "$RUN/manifest.txt")
for script in "$RUN/cpu.sbatch" "$RUN/environment.sh"; do
  bash -n "$script" || exit 1
done
if ! sbatch --test-only "${common[@]}" "${resources[@]}" "${payload[@]}"; then
  printf 'Preflight failed; no job submitted.\n' >&2
  exit 1
fi
```

After preflight succeeds and submission is authorized, continue in the same Bash
session. Persist the intent before submitting, then record the receipt. If the
submit response is lost or invalid, reconcile this intent before trying again.

```bash
printf '%s\t%s\t%s\n' "$CLUSTER" "$RUN_ID" "$(date -u +%FT%TZ)" \
  >> "$RUN/submission-intents.tsv" || exit 1
if ! receipt=$(sbatch --parsable "${common[@]}" "${resources[@]}" "${payload[@]}"); then
  printf 'Submission unconfirmed; reconcile before retrying.\n' >&2
  exit 1
fi
job_id=${receipt%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || { printf 'Unrecognized receipt; reconcile before retrying.\n' >&2; exit 1; }
printf 'Accepted: cluster=%s job_id=%s\n' "$CLUSTER" "$job_id"
printf '%s\t%s\t%s\n' "$CLUSTER" "$job_id" "$receipt" >> "$RUN/jobs.tsv" || exit 1
```

Set `RUN_ID` and `CLUSTER` explicitly in your controller. Protect and durably mirror the ledger; a TSV append is for a **single writer**, not multiagent coordination. Do not repeat the submit line after a lost response until reconciled. If ledger writing fails after submission, the job may already exist. [S11; workflow design]

For a **verified standard Trillium CPU node**, substitute:

```bash
resources=(--cpus-per-task=192)  # No memory flag; whole-node CPU profile.
```

The payload must productively use that allocation, e.g. an appropriately sized process pool or packed tasks. A few highly threaded BLAS calls do not guarantee good 192-core utilization. Pilot scaling and memory bandwidth. [S1–S3; sizing design]

**Syntax traps:** native `sbatch -n` is task count, `-c` is CPUs/task; bare native time is minutes. Put submission options before the script. `#SBATCH` does not expand shell variables. Inspect conflicting inherited `SBATCH_*` settings; a CLI override does not erase an unrelated inherited option. Avoid inherited `--export=NONE` surprises; the template restores export for its `srun` step after loading the environment. [S11,S12]

## 2. Capped, data-only arrays

Use a **frozen LF-delimited text file with one nonempty item ID per line, no header or NUL bytes**. IDs are data, never shell programs. `scripts/array-task.sh` appends the selected ID to the executable's argument vector; it does not use `eval`. Copy it into the run snapshot. The receiving program must treat that final argument as an ID; if it parses options, use its supported end-of-options marker or reject option-like IDs before submission.

```bash
# Example shape only; N and K must fit actual submission/concurrency limits.
N=120; K=8
sbatch --parsable --account="$ACCOUNT" --nodes=1 --ntasks=1 \
  --cpus-per-task=4 --mem=12G --time=00:45:00 \
  --array="1-${N}%${K}" --chdir="$RUN" \
  --output="$RUN/logs/%A_%a.out" --error="$RUN/logs/%A_%a.err" \
  "$RUN/cpu.sbatch" "$RUN/environment.sh" \
  bash "$RUN/array-task.sh" "$RUN/ids.txt" \
  Rscript --vanilla "$RUN/one_item.R"
```

`N` must equal the number of validated rows. A throttle limits simultaneously running elements, not how many count toward submitted-job limits. Do not expect array order. Store item IDs, not completion order, in results. Use the whole-node resource shape for arrays on Trillium; each element must justify one node. Native Slurm supports sparse retry lists; retain the **original** manifest when resubmitting original indices. [S13]

## 3. Pack short work

Use qexec's audited packing for trusted command files, or GNU Parallel inside one allocation. Start with enough work to amortize scheduling and staging; measure rather than adopting a universal minimum duration.

For `W` simultaneous commands and `T` threads each, reserve at least `W*T` CPUs and enough RAM for simultaneous peaks. Avoid either 192 single-threaded R workers that exhaust RAM or 48 workers each silently using 192 BLAS threads. Set process and library thread counts explicitly. Dispatch skewed-duration work carefully: equal line counts do not imply equal runtimes. [Sizing design]

When using GNU Parallel directly, use a job log and failure handling, with strict per-item entrypoints:

```bash
# Each trusted line invokes a checked entry script that propagates failures.
parallel --jobs "$W" --halt soon,fail=1 \
  --joblog "$RUN/parallel-${SLURM_JOB_ID}.tsv" < "$RUN/commands.txt"
```

Confirm these options against the installed `parallel --help`/manual. Never run a command file obtained from untrusted data. For multi-node packing, explicitly launch per-node workers with distinct work ownership; plain `--nodes=4` does not distribute a shell command. Prefer independent one-node array bundles when cross-node communication is unnecessary. [S12; execution design]

## 4. Dependencies, GPUs, interactive work, MPI

Use `--dependency=afterok:JOBID` for a collector that requires all upstream success; `afterany` for failure-aware diagnostics; `aftercorr` for corresponding array elements when supported. An afterok collector that remains pending after a failure is expected. Cross-cluster dependencies belong in the external controller, not assumed federated Slurm. [S11,S13]

For GPUs, use native Slurm and a **live-confirmed** request such as `--gres=gpu:TYPE:COUNT` or the site's documented `--gpus` form. Verify partition/account, host RAM, VRAM, CPU-to-GPU coupling, and full-versus-sliced device. Honor scheduler device visibility. Containers need the appropriate GPU pass-through and compatible host drivers; requesting a GPU alone does not accelerate ordinary R/Python code. Do not put `--gres` into qexec's unsupported CLI. [S11,S12]

For interactive diagnostics, request a bounded allocation using the selected cluster's resource shape. Verify the shell's hostname and allocation; where `salloc` leaves you on the login node, enter the allocation with `srun --ntasks=1 --pty bash -l` before analysis. Release resources when finished. Prefer Open OnDemand where suitable; do not treat debug/interactive queues as production shortcuts. [S12,S4; conservative usage rule]

For MPI, use a separate script with verified ranks/node, threads/rank, MPI module/ABI, and the site's recommended launcher. The supplied `cpu.sbatch` deliberately supports **one task on one node**, not MPI. Requesting multiple nodes never creates a shared-memory R session. [S12]
