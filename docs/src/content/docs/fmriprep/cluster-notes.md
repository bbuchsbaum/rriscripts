---
title: Cluster notes
description: Read-only filesystems, whole-node scheduling on Trillium, and subject batching.
---

## Bundle directory and read-only filesystems

The bundle directory (`script_outdir`) holds runtime-mutated state — `status/`
markers are written from compute nodes during the job. If `script_outdir` sits
on a filesystem that is read-only from compute nodes (Trillium and some Alliance
clusters mount `/project` read-only there), the job dies before fMRIPrep starts
with `Permission denied` on `status/sub-XXX.running`.

The launcher handles this automatically: if `$SCRATCH` is set, the default
`script_outdir` is `$SCRATCH/<bids-basename>_fmriprep_job`. If you override it to
a path that is not under `$SCRATCH` (or `/scratch*`, `/tmp`, `$TMPDIR`), the
launcher prints a warning at generation time.

To set it explicitly:

```ini
[slurm]
script_outdir = /scratch/$USER/mystudy_fmriprep_job
```

Or pass `--script-outdir` to `slurm-array`.

:::caution
`out` and `work` should also be on scratch — both are written from compute nodes
at runtime.
:::

## Trillium (whole-node scheduling)

Trillium allocates entire nodes, so `--mem` in SLURM directives causes errors:

```ini
[slurm]
no_mem = true
```

The equivalent CLI flag is `--no-mem`. In the wizard, answer "n" to "Specify
memory limit?".

On Trillium also see the bundle-directory note above — `/project` is read-only
from compute nodes there.

## Subject batching

For large datasets, batch multiple subjects per array task to reduce SLURM
overhead:

```bash
fmriprep_launcher.py slurm-array ... --subjects-per-job 4
```

Each array task then runs 4 subjects in parallel via `xargs`. The launcher
requests 4× the per-subject CPU and memory for that array task and writes one
line per subject batch to `subjects.txt`.

The trade-off: a batched task is only as fast as its slowest subject, and if one
subject fails the others in that task still complete. Batch sizes of 2–4 are a
reasonable starting point for datasets of a few hundred subjects.

For worked examples mapping subject counts onto node counts, see
[Spreading subjects across nodes](../subcommands/#spreading-subjects-across-nodes).

## A note on scratch expiry

Most HPC sites purge scratch on a fixed schedule. Because the recommended layout
puts `work`, `script_outdir`, and often `out` on scratch, copy derivatives you
care about to project storage once a run completes — and keep
`job_manifest.json` if you may want `rerun-failed` later.
