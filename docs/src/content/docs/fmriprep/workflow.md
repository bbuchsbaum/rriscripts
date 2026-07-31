---
title: Command-line workflow
description: The recommended non-interactive path from config files to a submitted SLURM array.
---

Once the [prerequisites](../prerequisites/) are in place, this is the recommended
path for routine cluster runs and lab documentation.

## The shape of it

The launcher never runs fMRIPrep itself. It **writes a SLURM script**, and you
submit that script. That separation is the thing to hold on to: everything below
is either telling the launcher what you want, or dealing with the bundle of
files it produces.

The work splits into three phases:

1. **Describe your setup, once.** Two config files — one for the cluster, one
   for the dataset. This is where nearly all the detail lives.
2. **Check, then generate.** Confirm the launcher sees what you expect, then
   have it write the job bundle.
3. **Submit, and retry what failed.** Hand the generated script to `sbatch`;
   afterwards, re-generate a bundle containing only the subjects that failed.

Steps 1 and 2 cost you a few minutes the first time and almost nothing
afterwards. A second dataset on the same cluster starts at step 2.

## Step 1 — configure the cluster, once per account

```bash
fmriprep_launcher.py init --user
$EDITOR ~/.config/fmriprep/config.ini
```

:::note[`$EDITOR`]
`$EDITOR` is the shell's convention for "whichever text editor you prefer" — it
is not part of this tool. If it is set in your environment, that line opens the
file in your editor. If it is not, substitute the editor directly:

```bash
nano ~/.config/fmriprep/config.ini    # or vim, emacs, micro, ...
```

To set it for future sessions, add `export EDITOR=nano` to your `~/.bashrc`.
:::

`init --user` writes a starter `~/.config/fmriprep/config.ini`. Fill in the
things that are true of *this cluster and your account*, and will stay true
across every dataset you ever process here:

```ini
[defaults]
runtime = singularity
container = /project/def-piname/shared/bin/fmriprep_25.2.5.sif
fs_license = /project/def-piname/shared/freesurfer/license.txt
templateflow_home = /project/def-piname/shared/opt/templateflow

[slurm]
account = def-piname
partition = compute
```

If you worked through [Prerequisites](../prerequisites/), this file already
exists and most of it is filled in — the container, license, and TemplateFlow
paths came from there.

You do this once. Every later dataset inherits it.

## Step 2 — configure the dataset

```bash
cd /path/to/my_bids_dataset
fmriprep_launcher.py init
$EDITOR fmriprep.ini
```

`init` (without `--user`) writes an `fmriprep.ini` in the current directory,
**pre-filled from your user config**, so you only supply what is specific to
this dataset:

```ini
[defaults]
bids = /project/def-piname/shared/my_study
out = /project/def-piname/shared/my_study/derivatives/fmriprep
work = /scratch/myuser/fmriprep_work
subjects = all
output_spaces = MNI152NLin2009cAsym:res-2 T1w

[slurm]
job_name = fmriprep_mystudy
time = 24:00:00
```

`subjects = all` means "every subject in the BIDS directory"; a space-separated
list like `sub-01 sub-02` restricts it. See
[the configuration reference](../configuration/) for every key.

## Step 3 — check before you spend anything

```bash
fmriprep_launcher.py probe
```

`probe` prints which config files it loaded, the effective value of every
setting after merging them, and which container runtime it detected. Read it as
a rehearsal of the run.

This step is worth its ten seconds. Almost every "the array job died a minute
after starting" report is a missing license path, an unset container, or a
config file that isn't being loaded from where you thought — all of which are
visible here.

## Step 4 — generate the bundle, then submit it

```bash
JOB_DIR="${SCRATCH:-$PWD}/$(basename "$PWD")_fmriprep_job"
fmriprep_launcher.py slurm-array --script-outdir "$JOB_DIR"
```

`slurm-array` reads the merged config and writes a **bundle** — a directory of
generated files, listed in [Where the bundle goes](#where-the-bundle-goes)
below. Nothing has been submitted yet, so this is a good moment to open
`fmriprep_array.sbatch` and read it.

The `JOB_DIR` line is just shell bookkeeping — it picks where the bundle goes so
that steps 4 and 5 can refer to the same place. Reading it piece by piece:

| Piece | Means |
|---|---|
| `${SCRATCH:-$PWD}` | use `$SCRATCH` if it is set, otherwise the current directory |
| `$(basename "$PWD")` | the name of the current directory, e.g. `my_bids_dataset` |
| `_fmriprep_job` | a suffix, so the directory is recognizable |

`$SCRATCH` is set by most HPC sites to your fast, large, periodically-purged
storage. The bundle belongs there because compute nodes must be able to **write**
to it while the job runs — see [Cluster notes](../cluster-notes/).

For `/data/my_study` with `$SCRATCH=/scratch/myuser`, that expands to
`/scratch/myuser/my_study_fmriprep_job`. You can equally well write the path out
by hand, or omit `--script-outdir` entirely and take
[the default](#where-the-bundle-goes) — which follows the same rule.

Then submit it yourself:

```bash
sbatch "$JOB_DIR/fmriprep_array.sbatch"
```

One array task per subject (or per batch of subjects, with
`--subjects-per-job`).

## Step 5 — retry only what failed

On a dataset of any size, some subjects will fail — a bad scan, a timeout, an
out-of-memory kill. Rather than resubmitting everything:

```bash
fmriprep_launcher.py rerun-failed --manifest "$JOB_DIR/job_manifest.json"
sbatch "$JOB_DIR/rerun_failed_job/fmriprep_array.sbatch"
```

This is why step 4 produced two files you have not used yet. `rerun-failed`
reads both:

- **`job_manifest.json`** — the snapshot of every config value the original run
  used, so the retry is built the same way rather than from whatever your config
  says today.
- **`status/`** — one marker file per subject (`.running`, `.ok`, `.failed`),
  written by the array tasks as they go, so the launcher can tell which subjects
  still need work.

From those it writes a **new** bundle, in `rerun_failed_job/` next to the
manifest, containing only the subjects with `.failed` markers. The original
bundle is not modified, so you can repeat this as many times as you need —
each round narrowing to whatever is still failing.

:::note
This only works if the run wrote a `job_manifest.json`. `slurm-array` always
does. Of the [interactive paths](#the-interactive-paths) below, the full
`wizard` does too, but `wizard --quick` does not — which is the main reason to
prefer `slurm-array` for anything larger than a handful of subjects.
:::

## The whole thing, condensed

Once the shape is familiar, the five steps are short enough to keep in one
place:

```bash
# 1. One-time user-level config for cluster infrastructure:
fmriprep_launcher.py init --user
$EDITOR ~/.config/fmriprep/config.ini   # set runtime, container, fs_license, account, ...

# 2. Per-dataset project config:
cd /path/to/my_bids_dataset
fmriprep_launcher.py init
$EDITOR fmriprep.ini                    # set bids, out, work, subjects, ...

# 3. Check what the launcher will use:
fmriprep_launcher.py probe

# 4. Generate the SLURM bundle and submit it:
JOB_DIR="${SCRATCH:-$PWD}/$(basename "$PWD")_fmriprep_job"
fmriprep_launcher.py slurm-array --script-outdir "$JOB_DIR"
sbatch "$JOB_DIR/fmriprep_array.sbatch"

# 5. If subjects fail, generate and submit a retry bundle:
fmriprep_launcher.py rerun-failed --manifest "$JOB_DIR/job_manifest.json"
sbatch "$JOB_DIR/rerun_failed_job/fmriprep_array.sbatch"
```

## Why two config files

Steps 1 and 2 wrote two files because the settings have two different
lifetimes. One set describes the cluster and changes almost never; the other
describes a dataset and changes with every study. Keeping them apart is what
makes a new dataset cost one short file instead of a full setup.

Which key goes where:

| | User config | Project config |
|---|---|---|
| **Path** | `~/.config/fmriprep/config.ini` | `./fmriprep.ini` |
| **Scope** | The cluster and your account | One dataset |
| **Keys** | `runtime`, `container`, `fs_license`, `templateflow_home`, `account`, `partition` | `bids`, `out`, `work`, `subjects`, `output_spaces`, `job_name`, `script_outdir`, `log_dir` |
| **How often you touch it** | Once per cluster account | Once per study |

The launcher merges every file it finds, in this order, with later entries
overriding earlier ones:

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` (user — infrastructure)
3. `~/.fmriprep.ini` (legacy user override, if present)
4. `./fmriprep.ini` (project — dataset-specific)
5. `--config path/to/file.ini` (explicit override)

Command-line flags override all of them. `probe` prints the result of the merge,
which is the quickest way to answer "where is that value actually coming from?"

A complete annotated config is in
[`fmriprep.ini.example`](https://github.com/bbuchsbaum/rriscripts/blob/main/fmriprep/fmriprep.ini.example).

## Where the bundle goes

If you do not set `--script-outdir`, the launcher writes the bundle to
`$SCRATCH/<bids-basename>_fmriprep_job/` when `$SCRATCH` is set, otherwise to
`./fmriprep_job/`.

The bundle contains:

| Path | Purpose |
|---|---|
| `fmriprep_array.sbatch` | The SLURM script you submit |
| `subjects.txt` | The work list — one line per array task, indexed by `$SLURM_ARRAY_TASK_ID`. See [What `subjects.txt` is](../subcommands/#what-subjectstxt-is). |
| `job_manifest.json` | Config snapshot used by `rerun-failed` |
| `status/` | Per-subject `.running`, `.ok`, `.failed` markers, written at runtime |

:::caution
The bundle directory must be writable **from compute nodes**, because `status/`
markers are updated while the array job runs. On clusters that mount `/project`
read-only from compute nodes, a bundle there dies before fMRIPrep starts. See
[Cluster notes](../cluster-notes/).
:::

## How paths on the command line are resolved

Every path flag — `--work`, `--bids`, `--out`, `--script-outdir` — is resolved
against your **current working directory**, and **replaces** the config value
rather than extending it.

This matters most for `--work`, because a bare name looks like it might mean
"a subdirectory of my configured work directory". It does not:

```ini
# fmriprep.ini
[defaults]
work = /scratch/myuser/fmriprep-work
```

```bash
cd /home/myuser/my_study
fmriprep_launcher.py slurm-array --work work1
# work dir becomes /home/myuser/my_study/work1
# NOT /scratch/myuser/fmriprep-work/work1
```

The configured `/scratch/myuser/fmriprep-work` is discarded entirely, and you
get a work directory on your home filesystem — usually the worst place for one,
since it is small, slow, and often not writable from compute nodes.

To get a subdirectory of the configured location, write it out:

```bash
fmriprep_launcher.py slurm-array --work /scratch/myuser/fmriprep-work/work1
```

Or, since per-dataset values belong in the project config anyway, set it there
and pass no flag at all:

```ini
[defaults]
work = /scratch/myuser/fmriprep-work/work1
```

:::caution
Nothing warns you about this. The work directory is not created at generation
time — the path is baked into the sbatch and created on the compute node at
runtime — so a misplaced `--work` surfaces as a slow run or an out-of-space
error partway in, not as an error when you generate the bundle.

`probe` and the generated `fmriprep_array.sbatch` both show the resolved
absolute path. Check `WORK_DIR=` near the top of the script before submitting.
:::

## The interactive paths

Everything above is non-interactive: you edit config files, and the launcher
reads them. There are also frontends that ask you questions instead, wrapping
the same backend. They replace steps 2–4, not the whole workflow — you still
submit the generated sbatch yourself.

Use them only when they help:

| Command | What it is |
|---|---|
| `fmriprep_launcher.py wizard` | Prompts through every value as a numbered table you can edit by field number. Writes the sbatch, `subjects.txt`, and `job_manifest.json`. |
| `fmriprep_launcher.py wizard --quick` | Asks only for values it cannot infer. Writes the sbatch and `subjects.txt` — **but not `job_manifest.json`**. |
| `run_fmriprep_wizard.sh` | Activates a likely virtualenv, then runs `wizard`. |
| `fmriprep_launcher.py tui` | Textual terminal UI (`pip install textual`). |
| `fmriprep_launcher.py gui` | Tk GUI (needs Tk and an X11 display). |

:::caution
Because `wizard --quick` writes no `job_manifest.json`, a run started that way
cannot use [`rerun-failed`](#step-5--retry-only-what-failed) afterwards. It is
fine for a quick test on a few subjects; for a real dataset use `slurm-array` or
the full `wizard`.
:::
