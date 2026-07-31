# fmriprep/ — fMRIPrep Launcher Toolkit

This directory contains several interfaces, but there is one recommended
path:

1. Use `fmriprep_launcher.py`.
2. Put stable settings in INI config files.
3. Generate a SLURM bundle with `fmriprep_launcher.py slurm-array`.
4. Submit the generated `fmriprep_array.sbatch` with `sbatch`.

That is the default, no-frills command-line workflow. It is non-interactive,
reproducible, and writes the `job_manifest.json` needed by `rerun-failed`.

The wizard, Textual TUI, Tk GUI, and `run_fmriprep_wizard.sh` are convenience
frontends around the same launcher/backend. They are optional; do not treat
them as separate primary workflows.

The launcher builds [fMRIPrep](https://fmriprep.org) commands and SLURM array
jobs for BIDS datasets. It supports Singularity/Apptainer, the
`fmriprep-docker` wrapper, and plain Docker. INI is the only supported config
format.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

This installs the launcher to `~/.local/share/fmriprep` and symlinks
`fmriprep_launcher.py` and `run_fmriprep_wizard.sh` into `~/bin`. The rest of
this README uses `fmriprep_launcher.py`; the wrapper is only for users who
want the interactive wizard.

To customize directories:

```bash
curl -fsSL ... | bash -s -- --lib-dir ~/.fmriprep --bin-dir /opt/bin
```

Or clone and add to `PATH`:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
export PATH="$HOME/code/rriscripts/fmriprep:$PATH"
```

If `~/bin` is not on your `PATH`, add it to `~/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

**Requirements:** Python 3.10+, SLURM, and Singularity/Apptainer or Docker.
`questionary` (`pip install --user questionary`) is optional but improves the
wizard UX.

## Before You Run Anything

You need three things on the cluster before the launcher can do useful work.
These are one-time setup steps and are usually shared across a lab.

### 1. An fMRIPrep container image

Run this on a **login node** — compute nodes typically have no internet:

```bash
# Pick and pin a version from https://hub.docker.com/r/nipreps/fmriprep/tags
# or https://fmriprep.org/en/latest/changes.html
VERSION=25.2.5

# Singularity (15-30 min):
singularity build fmriprep_${VERSION}.sif docker://nipreps/fmriprep:${VERSION}
# or with Apptainer:
apptainer pull docker://nipreps/fmriprep:${VERSION}

# Docker (local workstation):
docker pull nipreps/fmriprep:${VERSION}
```

Put the `.sif` somewhere lab members can share:

```bash
mv fmriprep_${VERSION}.sif /project/def-piname/shared/bin/
```

You will set `container = /project/def-piname/shared/bin/fmriprep_25.2.5.sif`
in your config below. Replace `25.2.5` with the version your project has
validated. Docker users can skip the path if the image is already local — the
launcher auto-discovers local Docker images.

### 2. A FreeSurfer license

Get a free license at <https://surfer.nmr.mgh.harvard.edu/registration.html>
and save the returned file as `license.txt`. fMRIPrep needs that file inside
the container, so put it on a filesystem visible to the compute nodes running
your SLURM jobs.

For a lab-shared setup, use a shared project path:

```bash
mkdir -p /project/def-piname/shared/freesurfer
cp license.txt /project/def-piname/shared/freesurfer/license.txt
chmod a+r /project/def-piname/shared/freesurfer/license.txt
```

Then set this once in your user-level config:

```ini
[defaults]
fs_license = /project/def-piname/shared/freesurfer/license.txt
```

For a private per-user setup, use a path that compute jobs can read, such as
`$HOME/.licenses/freesurfer/license.txt` if home directories are mounted on
compute nodes, or `$SCRATCH/.licenses/freesurfer/license.txt` if they are not.
You can also set `FS_LICENSE=/path/to/license.txt`, but the config key is more
explicit and easier to share in project run notes.

### 3. A populated TemplateFlow cache

fMRIPrep downloads brain templates via [TemplateFlow](https://www.templateflow.org/),
which fails on air-gapped compute nodes. Pre-populate the cache **on a login
node**:

```bash
# Option A — use the templateflow Python API:
python -c "
import templateflow.api as tfa
tfa.get('MNI152NLin2009cAsym')
tfa.get('MNI152NLin6Asym')
tfa.get('fsaverage')
tfa.get('fsLR')
"

# Option B — copy from someone who already has it:
cp -r /project/shared/templateflow ~/.cache/templateflow
```

The launcher auto-binds your local cache into the container and sets
`TEMPLATEFLOW_HOME` inside it. The interactive wizards warn when the cache is
missing or empty; `slurm-array` assumes the path you pass is ready to use.

## Default Command-Line Workflow

Once the prerequisites above are in place, use the CLI/config path below. This
is the recommended workflow for routine cluster runs and lab documentation.

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

If you do not set `--script-outdir`, the launcher writes the bundle to
`$SCRATCH/<bids-basename>_fmriprep_job/` when `$SCRATCH` is set, otherwise to
`./fmriprep_job/`. The bundle directory must be writable from compute nodes
because `status/` markers are updated while the array job runs.

Use the interactive paths only when they help:

- `fmriprep_launcher.py wizard` reviews every value, writes an sbatch,
  `subjects.txt`, and `job_manifest.json`.
- `fmriprep_launcher.py wizard --quick` asks only for missing essentials, but
  currently writes only the sbatch and `subjects.txt`; use `slurm-array` or the
  full `wizard` if you need manifest-backed reruns.
- `run_fmriprep_wizard.sh` just activates a likely virtualenv and runs
  `fmriprep_launcher.py wizard`.
- `fmriprep_launcher.py tui` and `fmriprep_launcher.py gui` are optional UI
  frontends.

A complete annotated config is in `fmriprep.ini.example`. The launcher reads
config files in priority order (later overrides earlier):

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` (user — infrastructure)
3. `~/.fmriprep.ini` (legacy user override, if present)
4. `./fmriprep.ini` (project — dataset-specific)
5. `--config path/to/file.ini` (explicit override)

The recommended split is:

- **User config** — stable infrastructure: `runtime`, `container`,
  `fs_license`, `templateflow_home`, `account`, `partition`.
- **Project config** — dataset-specific: `bids`, `out`, `work`, `subjects`,
  `output_spaces`, `job_name`, `script_outdir`, `log_dir`.

## Subcommand Reference

All subcommands accept `--help` for full options. Examples below assume the
launcher is on `PATH`; otherwise prefix with `python3`.

### `probe` — show what's detected

```bash
fmriprep_launcher.py probe
```

Lists the loaded config files and effective config values, detects the
available runtime (Singularity/Apptainer/Docker), and reports configured SIF
images or local Docker fMRIPrep images. Run this first to confirm the launcher
sees the same prerequisites you expect.

### `init` — generate a starter config

```bash
fmriprep_launcher.py init --user           # ~/.config/fmriprep/config.ini
fmriprep_launcher.py init                  # ./fmriprep.ini in current dir
fmriprep_launcher.py init /path/to/dataset # ./fmriprep.ini in a specific dir
fmriprep_launcher.py init --force          # overwrite existing
```

Project configs are pre-filled from the user config so you only need to set
dataset-specific values.

### `wizard` — interactive setup

```bash
fmriprep_launcher.py wizard --quick    # express: only ask what's missing
fmriprep_launcher.py wizard            # review-and-edit table of all values
```

Both modes auto-discover defaults from your config and environment. `--quick`
asks only for items the launcher can't infer and writes an sbatch plus
`subjects.txt`. The default mode shows a numbered table of every value, lets
you edit by field number, and writes the sbatch, `subjects.txt`, and
`job_manifest.json`. For a repeatable non-interactive run, prefer
`slurm-array`.

### `slurm-array` — write the sbatch directly

This is the default path once your config is stable. If `fmriprep.ini` contains
the required values, `fmriprep_launcher.py slurm-array` is enough. You can also
pass values explicitly:

```bash
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

### `print-cmd` — print commands without submitting

```bash
fmriprep_launcher.py print-cmd \
    --bids /path/to/BIDS \
    --subjects sub-01 sub-02 \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --output-spaces "MNI152NLin2009cAsym:res-2 T1w"
```

Useful for inspecting exactly what will be invoked.

### `rerun-failed` — retry only the failed subjects

```bash
fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json
```

Reads the manifest and `status/` markers from a previous run and writes a new
bundle (in `rerun_failed_job/` next to the manifest by default) containing only
subjects with `.failed` markers. The original bundle is not mutated.

Optional overrides:

```bash
fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json \
    --status-dir /path/to/fmriprep_job/status \
    --script-outdir /path/to/fmriprep_rerun \
    --subjects-per-job 2 \
    --job-name fmriprep_retry
```

### `tui` / `gui` — alternative frontends

```bash
fmriprep_launcher.py tui   # requires: pip install textual
fmriprep_launcher.py gui   # requires Tk and an X11 display
```

Both wrap the same backend as the CLI. They are optional frontends; the default
path remains `fmriprep_launcher.py slurm-array`.

## Configuration File Reference

A well-populated project config lets `slurm-array` run without long flag lists:

```ini
[defaults]
bids = /project/rrg-mypi/shared/my_study
out = /project/rrg-mypi/shared/my_study/derivatives/fmriprep
work = /scratch/myuser/fmriprep_work
runtime = singularity
container = /project/rrg-mypi/shared/bin/fmriprep_latest.sif
fs_license = /project/rrg-mypi/shared/bin/license.txt
templateflow_home = /project/rrg-mypi/shared/opt/templateflow

nprocs = 8
omp_threads = 4
mem_mb = 32000
skip_bids_validation = true
output_spaces = MNI152NLin2009cAsym:res-2 T1w
fs_reconall = true
use_syn_sdc = true

[slurm]
partition = compute
time = 24:00:00
account = rrg-mypi
job_name = fmriprep_mystudy
script_outdir = /scratch/myuser/my_study_fmriprep_job
log_dir = /scratch/myuser/my_study_fmriprep_job/logs
```

### `[defaults]` keys

The table reports behavior when a key is omitted. The generated starter
configs intentionally set some lab-friendly defaults, including
`skip_bids_validation = true` and `fs_reconall = true`; edit those values for
your study.

| Key | Type | Default if omitted | Description |
|---|---|---|---|
| `bids` | path | *(required)* | BIDS dataset root directory |
| `out` | path | *(required)* | Output directory (usually `<bids>/derivatives/fmriprep`) |
| `work` | path | *(required)* | Working directory (use fast scratch storage) |
| `runtime` | string | `auto` | Container runtime: `singularity`, `docker`, `fmriprep-docker`, or `auto` |
| `container` | path/string | `auto` | Path to `.sif` file, Docker `image:tag`, or `auto` to search `$FMRIPREP_SIF_DIR` |
| `fs_license` | path | `$FS_LICENSE` | Path to FreeSurfer `license.txt` |
| `templateflow_home` | path | `$TEMPLATEFLOW_HOME` | Path to pre-populated TemplateFlow cache |
| `nprocs` | int | auto-detect | `--nprocs` passed to fMRIPrep |
| `omp_threads` | int | `min(8, nprocs)` | `--omp-nthreads` passed to fMRIPrep |
| `mem_mb` | int/string | ~90% of available | Memory limit in MB (also accepts `32G`, `2T`) |
| `output_spaces` | string | — | Space-separated list, e.g. `MNI152NLin2009cAsym:res-2 T1w fsnative` |
| `skip_bids_validation` | bool | `false` | Pass `--skip-bids-validation` |
| `fs_reconall` | bool | `false` | Run FreeSurfer `recon-all`; generated project configs set this to `true` |
| `use_syn_sdc` | bool | `false` | Enable SyN-based fieldmap-less distortion correction |
| `cifti_output` | bool | `false` | Generate CIFTI outputs |
| `use_aroma` | bool | `false` | **Deprecated** — removed in fMRIPrep >= 23.1.0 |
| `extra` | string | — | Extra flags appended verbatim to the fMRIPrep command |
| `subjects` | string | — | `all` or space-separated list (e.g. `sub-01 sub-02`) |

### `[slurm]` keys

| Key | Type | Default if omitted | Description |
|---|---|---|---|
| `partition` | string | `compute` | SLURM partition name |
| `time` | string | `24:00:00` | Walltime limit (`HH:MM:SS`) |
| `account` | string | — | SLURM account/allocation (e.g. `def-piname`) |
| `job_name` | string | `fmriprep` | SLURM job name |
| `log_dir` | path | `<script_outdir>/logs` | Directory for SLURM stdout/stderr logs |
| `script_outdir` | path | `$SCRATCH/<bids-basename>_fmriprep_job` if `$SCRATCH` set, else `./fmriprep_job` | Where to write the generated sbatch + bundle. Must be writable from compute nodes (`status/` is mutated at runtime). |
| `cpus_per_task` | int | from `nprocs` | Override `--cpus-per-task` in the SLURM header |
| `mem` | string | from `mem_mb` | SLURM `--mem` value (e.g. `32G`). Use `none` to omit |
| `no_mem` | bool | `false` | Omit `--mem` entirely (for whole-node clusters like Trillium) |
| `email` | string | — | Email address for SLURM notifications |
| `mail_type` | string | — | SLURM mail events (e.g. `END,FAIL`) |
| `module_singularity` | bool | `false` | Insert `module load singularity` in the generated script |

Boolean values are case-insensitive (`true`/`True`/`TRUE`). Use `#` for inline
comments.

### Environment variables

| Variable | Effect |
|---|---|
| `FMRIPREP_SIF_DIR` | Directory to search for `.sif/.simg` images (used when `container = auto`). |
| `FS_LICENSE` | Path to FreeSurfer license file (fallback if not in config). |
| `TEMPLATEFLOW_HOME` | Path to TemplateFlow cache directory (fallback if not in config). |

## Cluster Notes

### Bundle directory and read-only filesystems

The bundle dir (`script_outdir`) holds runtime-mutated state — `status/`
markers are written from compute nodes during the job. If `script_outdir`
sits on a filesystem that's read-only from compute nodes (Trillium and some
Alliance clusters mount `/project` read-only there), the job dies before
fMRIPrep starts with `Permission denied` on `status/sub-XXX.running`.

The launcher handles this automatically: if `$SCRATCH` is set, the default
`script_outdir` is `$SCRATCH/<bids-basename>_fmriprep_job`. If you override
it to a path that isn't under `$SCRATCH` (or `/scratch*`, `/tmp`, `$TMPDIR`)
the launcher prints a warning at generation time.

To set explicitly:

```ini
[slurm]
script_outdir = /scratch/$USER/mystudy_fmriprep_job
```

Or pass `--script-outdir` to `slurm-array`. `out` and `work` should also be
on scratch — both are written from compute nodes at runtime.

### Trillium (whole-node scheduling)

Trillium allocates entire nodes, so `--mem` in SLURM directives causes errors:

```ini
[slurm]
no_mem = true
```

Equivalent CLI flag: `--no-mem`. In the wizard, answer "n" to "Specify memory
limit?". On Trillium also see the bundle-dir note above — `/project` is
read-only from compute nodes.

### Subject batching

For large datasets, batch multiple subjects per array task to reduce SLURM
overhead:

```bash
fmriprep_launcher.py slurm-array ... --subjects-per-job 4
```

Each array task then runs 4 subjects in parallel via `xargs`. The launcher
requests 4× the per-subject CPU and memory for that array task and writes one
line per subject batch to `subjects.txt`.

## What's in This Directory

| File | Purpose |
|---|---|
| `fmriprep_launcher.py` | Main CLI entrypoint (subcommands listed above). |
| `fmriprep_backend.py` | `BuildConfig`, command construction, SLURM template, manifest I/O. |
| `fmriprep_shared.py` | INI loading, runtime detection, subject discovery, memory parsing. |
| `fmriprep_tui_autocomplete.py` | Optional Textual TUI (`pip install textual`). |
| `fmriprep_gui_tk.py` | Optional Tk GUI (needs Tk and X11). |
| `fmriprep.ini.example` | Annotated example covering both user-level and project-level keys. |
| `run_fmriprep_wizard.sh` | Convenience wrapper that activates a likely venv before launching the wizard. |
| `install.sh` | One-shot installer. |
| `tests/` | Unit tests (`python3 -m unittest tests.test_backend`). |

## Deprecated

- **ICA-AROMA** (`--use-aroma`): Removed from fMRIPrep ≥ 23.1.0. The launcher
  raises an error if this option is set.
