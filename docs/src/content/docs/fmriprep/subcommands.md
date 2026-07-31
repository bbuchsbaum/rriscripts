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

giving `#SBATCH --array=0-2` — three tasks, and the task that gets a
multi-subject line runs them in parallel via `xargs`. The last line holds the
remainder when the count does not divide evenly.

Because it is a plain text file, you can edit it before submitting: delete lines
to skip subjects, or reorder them. Just keep the `--array` range in the sbatch
consistent with the number of lines.

### Spreading subjects across nodes

You do not choose the number of nodes directly. You choose **how many subjects
share a task** with `--subjects-per-job`, and the number of array tasks follows:

```text
number of array tasks = ceil(subjects / subjects-per-job)
```

Each array task is one node's allocation, so "how many nodes" is really "how
many array tasks". To spread `S` subjects across `N` nodes, set
`--subjects-per-job` to `S / N`.

The examples below assume a per-subject cost of `nprocs = 4` and
`mem_mb = 8000`, either from your config or auto-detected. The launcher
multiplies both by the batch size, since the subjects in a task run
concurrently.

#### 20 subjects across 4 nodes

```bash
fmriprep_launcher.py slurm-array --subjects all --subjects-per-job 5
```

```text
#SBATCH --array=0-3
#SBATCH --cpus-per-task=20      # 4 x 5
#SBATCH --mem=40G               # 8000 MB x 5
```

`subjects.txt`:

```text
sub-01 sub-02 sub-03 sub-04 sub-05
sub-06 sub-07 sub-08 sub-09 sub-10
sub-11 sub-12 sub-13 sub-14 sub-15
sub-16 sub-17 sub-18 sub-19 sub-20
```

#### 10 subjects on 1 node

```bash
fmriprep_launcher.py slurm-array --subjects all --subjects-per-job 10
```

```text
#SBATCH --array=0-0
#SBATCH --cpus-per-task=40      # 4 x 10
#SBATCH --mem=80G               # 8000 MB x 10
```

A single task, all ten subjects running in parallel inside it. Note what that
asks for: 40 cores and 80 GB on one node. Check it against your partition's
node size before submitting — this is the shape most likely to sit in the queue
or be rejected outright.

#### 100 subjects across 10 nodes

```bash
fmriprep_launcher.py slurm-array --subjects all --subjects-per-job 10
```

```text
#SBATCH --array=0-9
#SBATCH --cpus-per-task=40
#SBATCH --mem=80G
```

Ten tasks of ten subjects each. Per-task resources are identical to the previous
example — only the array range grows, because `--subjects-per-job` sets the task
size and the subject count sets the task count.

To use smaller nodes instead, shrink the batch: `--subjects-per-job 5` gives 20
tasks at 20 cores and 40 GB each. Same total work, spread thinner.

#### Choosing a batch size

| Consideration | Pushes toward |
|---|---|
| Node core/memory limits | Smaller batches |
| Per-job scheduler overhead, queue limits on array size | Larger batches |
| Wanting failures isolated to few subjects | Smaller batches |
| Short per-subject runtimes | Larger batches |

A batched task is only as fast as its slowest subject, and it holds the whole
allocation until the last one finishes. Batches of 2–4 are a reasonable starting
point; go higher only when you have checked the resulting request fits a real
node.

:::caution
Throttle concurrent tasks with the SLURM array syntax if your site limits how
many you may run at once — edit `#SBATCH --array=0-9` to `0-9%3` in the
generated script to cap it at three at a time.
:::

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
    --subjects-per-job 2 \
    --job-name fmriprep_retry
```

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
