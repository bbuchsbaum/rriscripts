---
name: alliance-hpc
description: Run and troubleshoot data-analysis jobs on Alliance/DRAC Trillium, Nibi, Fir, Rorqual, and Narval. Use for Slurm, qexec.sh, queues, arrays, resource sizing, storage, transfers, and resumable campaigns on these systems; not unrelated HPC providers.
---

# Alliance HPC

Optimize **time to validated results**, including staging, queueing, execution, and publication. Use the smallest sufficient allocation; exploit parallelism, not policy loopholes. Never invent an account, partition, QOS, resource limit, or successful execution.

## Load only what the task needs

Resolve paths relative to this skill directory. Do not read every reference.

| Need | Read |
|---|---|
| First use of a cluster; hardware or policy question | Relevant section of [systems.md](references/systems.md) |
| Compose a submission; arrays, packing, GPU or MPI | Relevant recipe in [submission.md](references/submission.md) |
| Storage, environments, queue diagnosis, recovery | Relevant section of [operations.md](references/operations.md) |
| Any use of `qexec.sh` | [qexec.md](references/qexec.md) |
| Verify a claim or refresh this skill | [sources.md](references/sources.md) |

Baseline audited **2026-09-21**, not a live service guarantee. Current site policy and authorized scheduler configuration govern; documentation conflicts are reasons to verify, not guess. Cached profiles save tokens, not permission checks.

## Before submission

Use an existing campaign profile if still current. Otherwise run `bash scripts/probe.sh /absolute/workdir` **on the target login host**, through an already authorized connection. Save output privately; condense it into the campaign profile. The probe is read-only, not a permission certificate. Refresh on cluster changes, stale profiles, maintenance, or scheduler rejection; do not repeat discovery for every task.

Establish: cluster/subcluster; permitted project account; suitable partition/QOS; allocation unit and CPU/RAM/GPU envelope; walltime/array/job limits; readable inputs and writable output/log paths; pinned working environment; concurrency and retry budget. Verify restrictions the probe cannot establish, including scratch retention and automation access. Check service notices before large campaigns. Do not block a simple job on unrelated GPU or transfer details.

**Cluster branches:** Trillium CPU is whole-node: baseline 192 cores/node; omit memory flags in its starter recipe, pack useful work, submit from scratch. It is diskless: never presume local SSD scratch. Trillium GPU has a separate login/scheduler and allocation rules. Nibi, Fir, Rorqual, and Narval support the shared-node CPU workflow; request CPUs and memory explicitly. Narval's published baseline is smaller. GPU types and network access differ; read the selected profile, not a generic “Alliance cluster” assumption. [Sources: S1–S5]

## Execute

1. **Measure one representative unit.** Use a scheduled pilot, not a heavy login-node test. Measure runtime, peak memory, output validity, and useful CPU scaling. Reuse trustworthy prior measurements. Add justified headroom; do not request a day for an hour of work merely for convenience.
2. **Choose the parallel shape.** For an R/Python process pool: one node, one task, `--cpus-per-task=C`; explicitly set worker count and keep inner BLAS/OpenMP threads at one. For a threaded program, allocate its thread budget. Require `workers × threads ≤ allocated CPUs` and a memory budget including the parent, private worker heaps, buffers, and headroom. Two nodes do not combine RAM or automatically distribute a process. MPI requires an MPI-aware launcher/application.
3. **Choose a legal queue fit.** Prefer existing data/environment locality. Compare eligible alternatives by staging + likely wait + measured runtime, not idle-node counts alone. Use default versus awarded accounts only when permitted for this project's work. Do not race duplicate jobs across clusters. Shard distinct units instead. Short truthful walltimes can help backfill; restartable chunks beat repeated timeout failures.
4. **Freeze and submit.** Use immutable run scripts, manifests, configuration, and input versions. Create log directories before submission. Inspect inherited `SBATCH_*` settings. Use native `sbatch` for control; use qexec only within its audited interface. Check `bash -n`; use `sbatch --test-only` once when supported. Neither validates the science. Record the exact command and returned `(cluster, job_id)` immediately. After an ambiguous SSH/submit failure, reconcile queue and accounting before retrying.
5. **Scale within bounds.** Prefer capped arrays for substantial independent units; pack short work into useful allocations. Array throttling does not bypass submission limits. Group similar resource needs, avoid filesystem stampedes, and collect results through dependencies. Retry only failed or absent units, within the agreed budget.
6. **Verify and preserve.** Poll only tracked jobs, normally at 60-second intervals with backoff; this is a conservative default, not a site rule. Require terminal accounting, successful exit status, expected outputs, and application checks. Inspect every array element. Preserve diagnostics and validated results before cleanup. Publish only within the user's authorized destination and scope.

## Non-negotiable operational rules

Analysis, substantial builds, and unpacking belong in suitable scheduled resources. Login nodes are for light control. Use approved transfer/automation services; never bypass MFA or host-key checks. An SSH session, `tmux`, or a waiting agent is not a durable workflow: batch jobs plus persisted run state are.

Keep reusable inputs in an authorized, checksummed cluster cache; work in approved scratch; keep authoritative results in backed-up/archival storage appropriate to the project. Job-local temporary storage is disposable and node-specific. Do not assume internet access, common filesystems across clusters, or portable compiled environments. Stage dependencies before offline jobs. Never evade purge with `touch`, put secrets in logs, broadly cancel a user's jobs, or delete shared data without authorization.

**qexec hazards:** `-n` means CPUs/task, not Slurm task count; bare `-t` means hours; old cluster detection mishandles Trillium; `--pack` controls inner concurrency; packed `--nodes` counts one-node array tasks. `--wait` is not a success assertion. Read the audit before composing a command.

## Handoff

Persist a compact run ledger: cluster/account, job and array IDs, frozen inputs/code/environment, resources, output/log paths, validated units, failed units, and next action. Keep state on durable authorized storage; do not use scratch as the sole controller database. Report **planned / submitted / running / validated / failed** accurately, with job IDs and paths. Never call “submitted” “done.”
