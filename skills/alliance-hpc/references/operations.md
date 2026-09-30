# Operations: storage, environments, monitoring, recovery

Read the relevant section only. Source keys: [sources.md](sources.md). Operational recommendations below are workflow design, not invented site policy.

## Storage and staging

Use an explicit three-tier design: authoritative inputs/results on authorized durable storage; reusable per-cluster cache; disposable per-run work. Never assume files exist on all five clusters because account names match. Resolve `$SCRATCH` and project symlinks rather than constructing paths from a username. [S2; workflow design]

Before a campaign, inspect byte and inode quotas, free capacity, output permissions, and scratch cleanup policy. `df` reports filesystem space, not your remaining quota. Use `diskusage_report` if available and the site's documented quota tools. Check both capacity and file count. Do not periodically touch files to defeat purge. Scratch and job-local temp are not backup. Exact purge ages and quota sizes are deliberately not frozen in this skill; confirm current policy. [Policy verification requirement]

Where node-local `$SLURM_TMPDIR` exists, stage the needed working subset, point application temp files there, and copy/check outputs before allocation teardown. It is not a cross-session cache or a filesystem shared between MPI nodes. Inspect its capacity and mount **inside** the allocation. Trillium is diskless: use job-specific shared scratch instead unless an explicitly verified alternative is appropriate. RAM-backed temp counts against the memory budget. [S1,S2]

For S3-backed work, keep bucket/key/version or checksums in the manifest. Transfer once through an approved network-capable host/service; verify a `.partial` staging area before promoting it to a ready cache. Compute reads only ready data and writes unique outputs. Publish through an approved transfer path; verify remote results before cleanup. Do not assume a Slurm transfer job has internet just because a login node does. [Workflow design]

Use Globus/approved data-transfer services for large transfers; verify collection UUID, ownership, paths, permissions, and completion. Internal portal node names are not permission to SSH to them. Use bounded rsync where permitted; avoid default `--delete`. Group many small files when useful, but unpack on appropriate resources, not through an uncontrolled login-node operation. Avoid every worker walking or hashing the full dataset. [S6,S7; workflow design]

Coordinate cache staging with a single controller or a locking scheme tested on that filesystem. Write completion markers only after validating files. Use same-filesystem rename for atomic local publication; a cross-filesystem move or an object-store “rename” is not the same guarantee. A failed transfer is not a ready cache. [Workflow design]

## Reproducible R/Python/container environments

Pin modules, runtime versions, package lockfiles, container digests, and analysis configuration. Inspect `module spider`/`module avail` on the target and write a small, tested `environment.sh`. Use an available `StdEnv` stack where appropriate; do not blindly impose another cluster's module recipe. Load the environment in the batch job, not only in an interactive shell. [S2; environment design]

Build/restore the environment once on compatible scheduled resources, using staged packages or an authorized network path. Record R `sessionInfo()` / Python package versions. Do not run `renv::restore()`, `install.packages()`, unrestricted `pip install`, or image pulls in every array element. Alliance wheels can be discovered with `avail_wheels`; use pinned offline installation where supported. [S2; environment design]

Treat compiled R libraries, Python virtual environments, MPI binaries, and architecture-specific builds as cluster/stack-specific until tested. Filesystem continuity from Graham/Cedar is not ABI validation. Do not copy a macOS environment to Linux or rely on `-march=native` binaries everywhere. Containers still need compatible CPU instructions, mounts, host GPU drivers and, for MPI, the site's supported integration. Pre-pull the image and verify the offline job. [Environment design]

For R/Python pools, bound workers from the allocation, not the login node's CPU count or `nproc --all`. Control OpenMP, MKL, OpenBLAS, BLIS, and NumExpr threading; inspect application-specific pools separately. Fork copy-on-write is not a promise of zero per-worker memory: modified pages and private heaps multiply. Profile the actual pipeline, especially image loading, large matrices, compression, and temporary arrays. [Sizing design]

## Diagnose without hammering Slurm

Use one bounded query for tracked IDs where possible. The skill's usual 60-second polling interval is a conservative default; back off during long pending periods and outages. A portal's free/idle resources or estimated start time is not a reservation. Scheduling depends on eligible shape, priority, limits, reservations, and backfill. [S9,S14–S16]

```bash
squeue -j "$JOB_IDS" -o '%.22i %.12T %.12M %.12l %.8C %.35R'
squeue --start -j "$JOB_IDS"       # Estimate only; may be unavailable.
scontrol show job "$JOB_ID"       # One problematic job, not the entire cluster.
sacct -j "$JOB_IDS" -P \
  -o JobID,JobName,State%32,ExitCode,Elapsed,AllocCPUS,ReqMem,MaxRSS,TotalCPU
# Optional installed tools: seff JOBID; sstat -j JOBID.STEP ...; sprio -j JOBID.
```

Inspect application steps as well as `.batch`; memory fields may be blank at the allocation row. `MaxRSS` is a maximum over measured tasks/steps, not automatically aggregate node memory. Missing measurements are not zero usage. CPU efficiency estimates must use the correct allocation and complete accounting. Validate actual outputs, not just an efficiency percentage. [S17]

| Observed state/reason | Response |
|---|---|
| `Priority`, `Resources` | Normal queueing possibilities. Check legal fit, walltime, and eligible alternatives; do not churn identical submissions. |
| `Assoc*`, `QOS*` limits | Inspect relevant account/QOS/group limits and running jobs. Throttle or reshape within policy; do not switch to an unrelated project. |
| `ReqNodeNotAvail` | Inspect maintenance, reservations, constraints, or drained hardware. |
| Dependency pending / impossible | Examine upstream states; fix/retry upstream or replace the dependency intentionally. |
| OOM | Reduce concurrent workers or increase justified memory; inspect hidden copies and temp usage. |
| Timeout | Measure, checkpoint/chunk, or request a legal longer time. Merely repeating the same job is not a repair. |
| Empty `squeue` response | Query accounting; allow reporting lag. Do not infer success or resubmit immediately. |
| Failed executable / missing package / missing input | Repair the environment or staging; do not label it a scheduler failure. |

State/reason definitions: [S18]. Actions are diagnostic recommendations.

## Durable campaigns and recovery

Keep orchestration on an authorized persistent control host or supported workflow service. `tmux` only preserves a shell where it is allowed; it neither grants resources nor guarantees host survival. Slurm batch jobs should survive a disconnected client. Use approved MFA-aware automation, not bypasses or unconstrained long-lived credentials. Indexed Alliance documentation lists robot hosts for Fir/Nibi/Rorqual/Narval; verify registration, restrictions, and permitted commands before use. No Trillium automation endpoint is assumed here. [S7a,S11; workflow design]

Persist submission **intent before submit**, then a receipt after acknowledgement. Reconcile ambiguous attempts by cluster, user, distinctive run/job name, submission time window, and accounting. A timeout after `sbatch` may still mean the job was accepted. Cross-cluster job IDs can collide. Keep `(cluster, job_id, array_index)` together. [Workflow design]

Checkpoint per logical analysis unit, with immutable input/config/code identifiers. Distinguish `computed`, `validated`, and `published`. A retry skips only matching validated outputs, never files merely present. Give each attempt unique temporary outputs; avoid concurrent writers to the same result. Rerun failed indices after root-cause correction, preserving original ID mapping. [Workflow design]

Use one writer or transactional coordination on suitable durable storage; do not put a multiwriter SQLite controller in arbitrary shared scratch. Mirror run manifests, job receipts, validation summaries, and checkpoints outside purgeable scratch. Cancel only exact authorized jobs. Cleanup requires published, verified results and a narrowly scoped list of owned temporary paths. [Workflow design]
