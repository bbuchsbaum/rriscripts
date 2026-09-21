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
launcher prints a warning at generation time. It applies the same heuristic to
`out` and `work`, which fMRIPrep also writes from the compute node. This is a
warning rather than a mount test: the submit host cannot reliably determine
what a compute node can write.

To set it explicitly:

```ini
[slurm]
script_outdir = /scratch/$USER/mystudy_fmriprep_job
```

Or pass `--script-outdir` to `slurm-array`.

:::caution
`out` and `work` should also be on scratch — both are written from compute nodes
at runtime. Stage completed derivatives back to project storage from a login
node. If you reuse FreeSurfer results, also stage
`<out>/sourcedata/freesurfer`; otherwise moving `out` to scratch makes
fMRIPrep run `recon-all` again.
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
fmriprep_launcher.py slurm-array ... \
    --subjects-per-job 4 \
    --parallel-subjects 2
```

Each array task is assigned four subjects but runs no more than two concurrently
via GNU `xargs`. The launcher therefore requests 2x the per-subject CPU and
memory for the task. It writes one four-subject line per batch to
`subjects.txt`; after the first pair finishes, the remaining pair starts.

`--subjects-per-job` controls assignment. `--parallel-subjects` controls
within-task execution and defaults to the assignment count when omitted.
`--array-concurrency` independently caps the number of active array tasks. See
[Subject placement and concurrency](../subcommands/#subject-placement-and-concurrency)
for formulas and worked one-node/many-node examples.

The trade-off: a batched task is only as fast as its slowest subject, and if one
subject fails the others in that task still complete. Batch sizes of 2–4 are a
reasonable starting point for datasets of a few hundred subjects.

## A note on scratch expiry

Most HPC sites purge scratch on a fixed schedule. Because the recommended layout
puts `work`, `script_outdir`, and often `out` on scratch, copy derivatives you
care about to project storage once a run completes — and keep
`job_manifest.json` if you may want `rerun-failed` later.
