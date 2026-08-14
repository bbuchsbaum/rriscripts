---
title: Subcommands
description: probe, init, wizard, slurm-array, print-cmd, rerun-failed, tui, and gui.
---

All subcommands accept `--help` for full options. Examples assume the launcher
is on `PATH`; otherwise prefix with `python3`.

## `probe` — show what's detected

```bash
fmriprep_launcher.py probe
```

Lists the loaded config files and effective config values, detects the available
runtime (Singularity/Apptainer/Docker), and reports configured SIF images or
local Docker fMRIPrep images.

Run this first to confirm the launcher sees the same prerequisites you expect.
Most "why did my job die immediately" questions are answered here.

## `init` — generate a starter config

```bash
fmriprep_launcher.py init --user           # ~/.config/fmriprep/config.ini
fmriprep_launcher.py init                  # ./fmriprep.ini in current dir
fmriprep_launcher.py init /path/to/dataset # ./fmriprep.ini in a specific dir
fmriprep_launcher.py init --force          # overwrite existing
```

Project configs are pre-filled from the user config, so you only need to set
dataset-specific values.

## `slurm-array` — write the sbatch directly

This is the default path once your config is stable. If `fmriprep.ini` contains
the required values, `fmriprep_launcher.py slurm-array` alone is enough. You can
also pass values explicitly:

```bash
# rrg-mypi is a placeholder — use your own allocation account.
fmriprep_launcher.py slurm-array \
    --bids /path/to/BIDS \
    --out /path/to/BIDS/derivatives/fmriprep \
    --work /scratch/$USER/fmriprep_work \
    --subjects all \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --partition compute --time 24:00:00 \
    --cpus-per-task 8 --mem 32G \
    --account rrg-mypi
```

Writes a complete bundle to `$SCRATCH/<bids-basename>_fmriprep_job/` when
`$SCRATCH` is set, otherwise `./fmriprep_job/`:

| File | What it is |
|---|---|
| `fmriprep_array.sbatch` | The SLURM script you submit |
| `subjects.txt` | The work list — see below |
| `job_manifest.json` | Config snapshot used by `rerun-failed` |
| `status/` | Per-subject `.running`, `.ok`, `.failed` markers, written at runtime |

Then submit it yourself:

```bash
sbatch /path/to/bundle/fmriprep_array.sbatch
```

### What `subjects.txt` is

`subjects.txt` is how the array job knows what to work on. Each **line** is one
array task, and `$SLURM_ARRAY_TASK_ID` indexes into it — task 0 processes line
1, task 1 line 2, and so on. The `#SBATCH --array` range is set to match the
number of lines.

By default that is one subject per line:

```text
sub-01
sub-02
sub-03
sub-04
sub-05
```

giving `#SBATCH --array=0-4` — five tasks, one subject each.

With `--subjects-per-job 2`, subjects are grouped and each line holds a
space-separated batch:

```text
sub-01 sub-02
sub-03 sub-04
sub-05
```

giving `#SBATCH --array=0-2` — three tasks. The last line holds the remainder
when the count does not divide evenly.

Assignment and execution are separate controls. `--subjects-per-job` sets how
many subjects go on each line; `--parallel-subjects` sets how many independent
fMRIPrep processes may be active at once inside the task. When the second value
is smaller, GNU `xargs` runs the assigned subjects in waves. If
`--parallel-subjects` is omitted, it defaults to `--subjects-per-job`, preserving
the all-at-once behavior.

Because it is a plain text file, you can edit it before submitting: delete lines
to skip subjects, or reorder them. Just keep the `--array` range in the sbatch
consistent with the number of lines.

### Subject placement and concurrency

There are three independent scheduling counts:

| Control | Meaning |
|---|---|
| `--subjects-per-job B` | Subjects assigned to each array task |
| `--parallel-subjects M` | Maximum fMRIPrep processes active inside each task; `1 <= M <= B` |
| `--array-concurrency C` | Maximum array tasks Slurm may run at once; rendered using [Slurm's `%C` array limit](https://slurm.schedmd.com/job_array.html) |

For `S` subjects, the launcher creates:

```text
T = ceil(S / B) array tasks
maximum active fMRIPrep processes <= min(T, C) x M   (when C is set)
maximum active fMRIPrep processes <= T x M           (when C is omitted)
```

These are upper bounds. Slurm may run fewer tasks because of queue state,
fair-share, or available resources, and the last batch may contain fewer than
`M` subjects.

Each array task requests `--nodes=1`, so all processes inside one task run in
one Slurm allocation on one physical node. Different array tasks are separate
allocations, but Slurm may place them on the same physical node. Add
`--exclusive` to request an unshared node for each active task. Site policy may
override exclusivity, and neither arrays nor `%C` guarantee that tasks start at
the same time.

The examples below assume a per-subject cost of `nprocs = 4` and
`mem_mb = 8000`, either from your config or auto-detected. These values are
passed unchanged to every independent fMRIPrep process. By default, the launcher
requests `M x 4` CPUs and `M x 8000 MB` for the array task. Explicit
`--cpus-per-task` or `--mem` values are total task allocations and are not
scaled again.

#### Ten subjects as ten independent tasks

```bash
fmriprep_launcher.py slurm-array \
    --subjects all \
    --subjects-per-job 1 \
    --parallel-subjects 1 \
    --array-concurrency 10 \
    --exclusive
```

```text
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --array=0-9%10
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
```

There is one subject and one fMRIPrep process per task. Up to ten tasks may be
active, each requesting an unshared node. This is the closest array-job form of
"one subject per node," but it is not gang scheduling: Slurm may start the ten
tasks at different times.

If you need only independent tasks, not exclusive physical nodes, omit
`--exclusive`. If you do not need to cap active tasks, omit
`--array-concurrency` as well.

#### Ten subjects in one task, all at once

```bash
fmriprep_launcher.py slurm-array \
    --subjects all \
    --subjects-per-job 10 \
    --parallel-subjects 10
```

```text
#SBATCH --array=0-0
#SBATCH --nodes=1
#SBATCH --cpus-per-task=40      # 4 x 10 active subjects
#SBATCH --mem=80G               # 8000 MB x 10 active subjects
```

All ten independent fMRIPrep processes run inside one task allocation on one
node. Check that a real node in the partition has 40 CPUs and 80 GB available;
this shape may wait longer or be rejected if it cannot fit.

#### Ten subjects in one task, two at a time

```bash
fmriprep_launcher.py slurm-array \
    --subjects all \
    --subjects-per-job 10 \
    --parallel-subjects 2
```

```text
#SBATCH --array=0-0
#SBATCH --cpus-per-task=8       # 4 x 2 active subjects
#SBATCH --mem=16G               # 8000 MB x 2 active subjects
```

The one task keeps all ten subjects assigned to it, but `xargs -P 2` runs at
most two at a time: five waves when runtimes are similar. This is the useful
distinction between batch size (`B=10`) and in-task concurrency (`M=2`).

#### Twenty subjects in four task allocations

```bash
fmriprep_launcher.py slurm-array \
    --subjects all \
    --subjects-per-job 5 \
    --parallel-subjects 2 \
    --array-concurrency 4
```

```text
#SBATCH --array=0-3%4
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
```

`subjects.txt` has four five-subject batches:

```text
sub-01 sub-02 sub-03 sub-04 sub-05
sub-06 sub-07 sub-08 sub-09 sub-10
sub-11 sub-12 sub-13 sub-14 sub-15
sub-16 sub-17 sub-18 sub-19 sub-20
```

Up to four array tasks and eight subjects may be active. Each task runs its five
assigned subjects two at a time. Without `--exclusive`, the four task
allocations are not guaranteed to occupy four distinct physical nodes.

#### Choosing the three counts

| Goal or constraint | Adjustment |
|---|---|
| Isolate failures and balance uneven subject runtimes | Smaller `B` |
| Reduce array size and scheduler overhead | Larger `B` |
| Fit CPU and memory available in one task | Smaller `M` |
| Finish each batch in fewer waves | Larger `M`, if the node can hold it |
| Respect a site or allocation limit on active jobs | Smaller `C` |
| Request distinct, unshared physical nodes | `B=1`, `M=1`, plus `--exclusive` |

A batched task is only as fast as its slowest subject, and it holds the whole
allocation until all assigned subjects finish. A large `B` does not require a
large allocation when `M` is small; it instead creates more waves inside the
same allocation.

#### Native multi-subject fMRIPrep versus launcher packing

fMRIPrep itself accepts a
[space-delimited list of participant labels](https://fmriprep.org/en/stable/usage.html)
in one invocation. That is a different execution model. The launcher currently
starts one fMRIPrep invocation and one container per subject, gives each subject
its own work directory and status marker, and uses GNU `xargs -P M` only to
bound how many are active. It does not expose a single native multi-participant
invocation as a Slurm mode.

An array also cannot guarantee that several nodes begin together. A workflow
that requires simultaneous multi-node startup needs a gang-scheduled multi-node
job (typically coordinated with `srun`), which this launcher does not generate.

See also [Subject batching](../cluster-notes/#subject-batching).

## `print-cmd` — print commands without submitting

```bash
fmriprep_launcher.py print-cmd \
    --bids /path/to/BIDS \
    --subjects sub-01 sub-02 \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --output-spaces "MNI152NLin2009cAsym:res-2 T1w"
```

Useful for inspecting exactly what will be invoked — including how your config
keys became fMRIPrep flags and how the container bind mounts were computed.

## `rerun-failed` — retry only the failed subjects

```bash
fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json
```

Reads the manifest and `status/` markers from a previous run and writes a new
bundle — in `rerun_failed_job/` next to the manifest by default — containing
only subjects with `.failed` markers. The original bundle is not mutated.

Optional overrides:

```bash
fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json \
    --status-dir /path/to/fmriprep_job/status \
    --script-outdir /path/to/fmriprep_rerun \
    --subjects-per-job 4 \
    --parallel-subjects 2 \
    --array-concurrency 3 \
    --exclusive \
    --job-name fmriprep_retry
```

Without overrides, the rerun inherits all four scheduling settings from the
manifest. If only `--subjects-per-job` is reduced, stored in-task parallelism is
clamped to the new batch size.

## `wizard` — interactive setup

```bash
fmriprep_launcher.py wizard --quick    # express: only ask what's missing
fmriprep_launcher.py wizard            # review-and-edit table of all values
```

Both modes auto-discover defaults from your config and environment.

`--quick` asks only for items the launcher can't infer and writes an sbatch plus
`subjects.txt`. The default mode shows a numbered table of every value, lets you
edit by field number, and writes the sbatch, `subjects.txt`, **and**
`job_manifest.json`.

:::caution
`wizard --quick` does not write `job_manifest.json`, so `rerun-failed` cannot
work from it. For a repeatable non-interactive run, prefer `slurm-array`.
:::

## `tui` / `gui` — alternative frontends

```bash
fmriprep_launcher.py tui   # requires: pip install textual
fmriprep_launcher.py gui   # requires Tk and an X11 display
```

Both wrap the same backend as the CLI. They are optional frontends; the default
path remains `fmriprep_launcher.py slurm-array`.
