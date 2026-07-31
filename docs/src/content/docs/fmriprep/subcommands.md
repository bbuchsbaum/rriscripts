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

- `fmriprep_array.sbatch` — the SLURM script
- `subjects.txt` — one line per array task
- `job_manifest.json` — config snapshot used by `rerun-failed`
- `status/` — per-subject `.running`, `.ok`, `.failed` markers populated at runtime

Then submit it yourself:

```bash
sbatch /path/to/bundle/fmriprep_array.sbatch
```

### Batching subjects per task

```bash
fmriprep_launcher.py slurm-array ... --subjects-per-job 4
```

Each array task then runs 4 subjects in parallel via `xargs`. The launcher
requests 4× the per-subject CPU and memory for that array task and writes one
line per subject batch to `subjects.txt`. See
[Subject batching](../cluster-notes/#subject-batching).

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
