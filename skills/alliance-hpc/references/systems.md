# System selection and live policy

Read the selected system's section. Source keys resolve in [sources.md](sources.md). Values below are starting points, not guarantees about every partition or node.

## Compact map

| System / login | CPU starting profile | Accelerator starting point | Operational distinction |
|---|---|---|---|
| Trillium — `trillium.alliancecan.ca` | Whole node; 192 CPU cores; 768 GB installed RAM [S1] | Separate GPU subcluster | Diskless; scratch submission; pack CPU work [S1,S2] |
| Trillium GPU — `trillium-gpu.alliancecan.ca` | 96 CPU cores and 768 GB installed RAM per full node [S1] | 4 × H100 80 GB/full node [S1] | Whole-node or one-GPU quarter-node allocation [S2] |
| Nibi — `nibi.alliancecan.ca` | nf-core baseline: 192 CPUs, `750.GB` [S3] | H100 80 GB; MI300A resources also advertised [S2,S4] | Graham filesystem continuity; Open OnDemand; do not assume CUDA for every accelerator [S2,S4] |
| Fir — `fir.alliancecan.ca` | nf-core baseline: 192 CPUs, `750.GB` [S3] | H100 80 GB [S2] | Cedar replacement/filesystem continuity; rebuild or validate inherited environments [S2,S5] |
| Rorqual — `rorqual.alliancecan.ca` | nf-core baseline: 192 CPUs, `750.GB` [S3] | H100 80 GB [S2] | Offline compute; portal exposes scheduler/filesystem/transfer diagnostics [S2,S6] |
| Narval — `narval.alliancecan.ca` | nf-core baseline: 64 CPUs, `249.GB` [S3] | A100 40 GB [S2] | Offline compute; do not transplant a 192-CPU/750-GB request [S2,S3] |

**Interpretation:** nf-core values are the maintainer's baseline CPU workflow caps, not proof of physical capacity, maximum site resources, or allowed walltime. Its `168.h` cap is **not** a verified universal Alliance limit. High-memory, GPU, and restricted nodes can differ. Query `sinfo -e` and the chosen node/partition; `%m` is MiB, not nameplate GB. Inspect CPU topology rather than equating Slurm CPUs with physical cores. [S3,S9]

## Trillium

Use the CPU and GPU login endpoints as distinct scheduling targets; record both hostname and Slurm `ClusterName`. They share storage, not a single interchangeable submission profile. CPU jobs consume whole nodes. The starter CPU recipe requests one task with 192 CPUs and no `--mem`/`--mem-per-cpu`; verify against the current quickstart and scheduler before a campaign. A single-core job here still needs a whole-node justification or should go elsewhere. [S1–S3]

Submit with the current directory, logs, and working outputs under a verified `$SCRATCH` path. Use job-specific scratch directories on its shared VAST filesystem. There are no local disks: inspect `findmnt`/`df` inside an allocation before using `$TMPDIR` or `$SLURM_TMPDIR`; a RAM-backed temporary directory consumes memory. Do not copy data into `/tmp` on the assumption it is an NVMe drive. [S1,S2]

For GPU work, confirm the current GPU partition, GRES, CPU/RAM coupling, and quarter-node versus full-node requirements. Do not apply CPU 192-core flags to its 96-core GPU nodes. Restricted Neptune nodes are not generally available; their 40-core examples are not Trillium CPU defaults. [S1,S2,S1b]

## Nibi

Use shared-node sizing, with live inspection for larger/specialized node types. SHARCNET provides Open OnDemand for allocated interactive work. A 2026 SHARCNET seminar advertises MI300A APUs: establish actual access, ROCm compatibility, and GRES before targeting them. H100 is not an exhaustive Nibi accelerator inventory. [S3,S4]

Mila's 2026 operational table reports unrestricted internet on Nibi (and Fir). Treat this as a useful lead, not a promise for every node or destination: confirm any required endpoint with an approved minimal test. Prefer staged, reproducible dependencies even where egress works. [S2]

## Fir

Cedar data continuity does not make old Cedar CPU/GPU resources, binaries, partitions, or automation settings valid. Resolve the actual storage paths and validate the environment on Fir. Use its current hostname, not a historical Cedar SSH alias whose destination was never checked. [S2,S5]

Verify Globus collection identity from current site documentation or the authenticated service, including UUID and owner. Do not bake an old Cedar collection display name into unattended transfers: indexed old/new labels disagree. [S7]

## Rorqual

Make jobs self-contained: stage packages, datasets, model weights, licenses where applicable, and container images before compute starts. Do not have every array element attempt downloads. Consult the operator's portal when queue utilization or filesystem contention might explain slow throughput. Its portal lists transfer nodes, but internal node labels are not automatically approved public SSH transfer endpoints. [S2,S6]

Discover full-GPU versus any MIG/sliced resources from the current configuration. Do not invent a slice name or copy an internet example's GRES as a site guarantee. A successfully loaded NVIDIA module does not allocate a GPU. [S9,S12]

## Narval

The published CPU baseline is 64 rather than 192 CPUs; resize pools and packed batches accordingly. A100 40-GB VRAM may be sufficient and avoids requiring an H100 unnecessarily, but an older GPU does not imply a shorter queue. Compute jobs should have no internet dependency. [S2,S3]

Consult the operator's portal for scheduler and filesystem diagnostics. For high-memory work, discover eligible high-memory nodes instead of treating the standard baseline as the site's maximum. [S6,S9]

## What must be learned live

Use `scripts/probe.sh` for initial evidence. Then inspect **only the selected** partition, account, and QOS, including parent/group limits when relevant. A visible partition is not necessarily authorized. Blank or unavailable accounting fields do not prove unlimited access. [S8,S10]

```bash
scontrol show partition "$PARTITION"
sacctmgr -nP show assoc where user="$USER" account="$ACCOUNT" \
  format=Cluster,Account,User,Partition,QOS,DefaultQOS,MaxJobs,MaxSubmitJobs,MaxWall,GrpTRES
sacctmgr -nP show qos where name="$QOS" \
  format=Name,Flags,MaxWall,MaxJobsPU,MaxSubmitJobsPU,MaxTRESPU,GrpTRES
```

Check walltime and minimum/maximum job size; per-job/user/group resource limits; running/submitted/array limits; eligible GRES/features; maintenance; and actual storage quotas/retention. Partition, job-QOS, association, and parent limits interact; do not reduce the whole hierarchy to a minimum of whatever numbers happen to be printed. If a relevant rule cannot be verified, say so and resolve it before the action it governs. [S8,S10]
