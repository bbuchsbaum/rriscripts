# fmriprep/ — fMRIPrep Launcher Toolkit

A single CLI (`fmriprep_launcher.py`) that builds correct
[fMRIPrep](https://fmriprep.org) commands and generates SLURM array jobs for
BIDS datasets. Supports Singularity/Apptainer, the `fmriprep-docker` wrapper,
and plain Docker. INI is the only supported config format.

Optional Textual TUI and Tk GUI frontends are available; everything below uses
the CLI.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

This installs the launcher to `~/.local/share/fmriprep` and symlinks
`fmriprep_launcher.py` and `run_fmriprep_wizard.sh` into `~/bin`.

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

**Requirements:** Python 3.7+, SLURM, and Singularity/Apptainer or Docker.
`questionary` (`pip install --user questionary`) is optional but improves the
wizard UX.

## Before You Run Anything

You need three things on the cluster before the launcher can do useful work.
These are one-time setup steps and are usually shared across a lab.

### 1. An fMRIPrep container image

Run this on a **login node** — compute nodes typically have no internet:

```bash
# Pick a version from https://hub.docker.com/r/nipreps/fmriprep/tags
VERSION=24.1.0

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

You will set `container = /project/def-piname/shared/bin/fmriprep_24.1.0.sif`
in your config below. (Docker users can skip the path — the launcher
auto-discovers local Docker images.)

### 2. A FreeSurfer license

Get a free license at <https://surfer.nmr.mgh.harvard.edu/registration.html>
and save it somewhere readable by your jobs, e.g.
`/project/def-piname/shared/bin/license.txt`.

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

The launcher auto-binds your local cache into the container, sets
`TEMPLATEFLOW_HOME` inside it, and validates that templates exist before
generating the sbatch.

## Quick Start

Once the prerequisites above are in place:

```bash
# 1. Confirm everything is detected:
fmriprep_launcher.py probe

# 2. Write a user-level config (once per cluster):
fmriprep_launcher.py init --user
$EDITOR ~/.config/fmriprep/config.ini   # set runtime, container, fs_license, account, ...

# 3. Write a project config in your BIDS root:
cd /path/to/my_bids_dataset
fmriprep_launcher.py init
$EDITOR fmriprep.ini                    # set bids, out, work, subjects, ...

# 4. Verify and generate the sbatch:
fmriprep_launcher.py wizard --quick

# 5. Submit:
sbatch fmriprep_job/fmriprep_array.sbatch

# 6. If any subjects fail, rerun just those:
fmriprep_launcher.py rerun-failed --manifest fmriprep_job/job_manifest.json
```

What each step does is covered in [Subcommand Reference](#subcommand-reference)
below.

A complete annotated config is in `fmriprep.ini.example`. The launcher reads
config files in priority order (later overrides earlier):

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` or `~/.fmriprep.ini` (user — infrastructure)
3. `./fmriprep.ini` (project — dataset-specific)
4. `--config path/to/file.ini` (explicit override)

The recommended split is:

- **User config** — stable infrastructure: `runtime`, `container`,
  `fs_license`, `templateflow_home`, `account`, `partition`.
- **Project config** — dataset-specific: `bids`, `out`, `work`, `subjects`,
  `output_spaces`, `job_name`, `log_dir`.

## Subcommand Reference

All subcommands accept `--help` for full options. Examples below assume the
launcher is on `PATH`; otherwise prefix with `python3`.

### `probe` — show what's detected

```bash
fmriprep_launcher.py probe
```

Lists the runtime (Singularity/Apptainer/Docker), available container images,
your FreeSurfer license, TemplateFlow cache status, and the effective merged
config. Run this first to confirm prerequisites are in place.

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
asks only for items the launcher can't infer; the default mode shows a numbered
table of every value and lets you edit by field number.

### `slurm-array` — write the sbatch directly

For scripted or repeat runs, skip the wizard once your config is stable:

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

Writes a complete bundle to `./fmriprep_job/`:

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

Both wrap the same backend as the CLI; use whichever you prefer.

## Configuration File Reference

A well-populated project config eliminates most wizard questions:

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
log_dir = /scratch/myuser/fmriprep_logs
```

### `[defaults]` keys

| Key | Type | Default | Description |
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
| `fs_reconall` | bool | `false` | Run FreeSurfer `recon-all` |
| `use_syn_sdc` | bool | `false` | Enable SyN-based fieldmap-less distortion correction |
| `cifti_output` | bool | `false` | Generate CIFTI outputs |
| `use_aroma` | bool | `false` | **Deprecated** — removed in fMRIPrep >= 23.1.0 |
| `extra` | string | — | Extra flags appended verbatim to the fMRIPrep command |
| `subjects` | string | — | `all` or space-separated list (e.g. `sub-01 sub-02`) |

### `[slurm]` keys

| Key | Type | Default | Description |
|---|---|---|---|
| `partition` | string | `compute` | SLURM partition name |
| `time` | string | `24:00:00` | Walltime limit (`HH:MM:SS`) |
| `account` | string | — | SLURM account/allocation (e.g. `def-piname`) |
| `job_name` | string | `fmriprep` | SLURM job name |
| `log_dir` | path | `<script_outdir>/logs` | Directory for SLURM stdout/stderr logs |
| `script_outdir` | path | `./fmriprep_job` | Where to write the generated sbatch script and subject list |
| `cpus_per_task` | int | from `nprocs` | Override `--cpus-per-task` in the SLURM header |
| `mem` | string | from `mem_mb` | SLURM `--mem` value (e.g. `32G`). Use `none` to omit |
| `no_mem` | bool | `false` | Omit `--mem` entirely (for whole-node clusters like Trillium) |
| `email` | string | — | Email address for SLURM notifications |
| `mail_type` | string | — | SLURM mail events (e.g. `END,FAIL`) |
| `module_singularity` | bool | `false` | Insert `module load singularity` in the generated script |

Boolean values are case-insensitive (`true`/`True`/`TRUE`). Inline comments
use `#` (preferred) or `;`.

### Environment variables

| Variable | Effect |
|---|---|
| `FMRIPREP_SIF_DIR` | Directory to search for `.sif/.simg` images (used when `container = auto`). |
| `FS_LICENSE` | Path to FreeSurfer license file (fallback if not in config). |
| `TEMPLATEFLOW_HOME` | Path to TemplateFlow cache directory (fallback if not in config). |

## Cluster Notes

### Trillium (whole-node scheduling)

Trillium allocates entire nodes, so `--mem` in SLURM directives causes errors:

```ini
[slurm]
no_mem = true
```

Equivalent CLI flag: `--no-mem`. In the wizard, answer "n" to "Specify memory
limit?".

### Subject batching

For large datasets, batch multiple subjects per array task to reduce SLURM
overhead:

```bash
fmriprep_launcher.py slurm-array ... --subjects-per-job 4
```

Each array task then runs 4 subjects in parallel via `xargs`, and the
launcher scales `--nprocs` and `--mem` accordingly (4× per task).

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
