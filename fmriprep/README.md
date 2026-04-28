# fmriprep/ — fMRIPrep Launcher Toolkit

This directory contains one backend (`fmriprep_launcher.py`) with optional
frontends for building correct [fMRIPrep](https://fmriprep.org) commands and
generating SLURM array jobs for BIDS datasets.

- `fmriprep_launcher.py` is the canonical entrypoint.
- The Textual TUI and Tk GUI are optional alternative frontends.
- INI is the only supported config format.

## Start Here

The recommended path:

1. Probe your environment.
2. Generate a user config (once) with `fmriprep_launcher.py init --user`.
3. Generate a project config with `fmriprep_launcher.py init` from your BIDS root.
4. Edit `fmriprep.ini` for your dataset.
5. Run `fmriprep_launcher.py wizard --quick` to verify and generate the sbatch.
6. Use `print-cmd` or `slurm-array` directly once the config is stable.
7. If subjects fail, use `rerun-failed` on the generated `job_manifest.json`.

### Files

| File | Purpose |
|---|---|
| **fmriprep_launcher.py** | Main CLI: `init`, `probe`, `print-cmd`, `slurm-array`, `rerun-failed`, `wizard`, `tui`, `gui`. |
| **fmriprep_backend.py** | `BuildConfig`, command construction, SLURM script template, manifest I/O. |
| **fmriprep_shared.py** | INI loading, runtime detection, subject discovery, memory parsing. |
| **fmriprep_tui_autocomplete.py** | Optional Textual TUI (`pip install textual`). |
| **fmriprep_gui_tk.py** | Optional Tk GUI (needs Tk + X11). |
| **fmriprep.ini.example** | Annotated example config covering both user-level and project-level keys. |
| **run_fmriprep_wizard.sh** | Convenience wrapper that activates a likely venv before launching the wizard. |
| **install.sh** | One-shot installer to `~/.local/share/fmriprep` with symlinks in `~/bin`. |

## Quick Start

All examples below use `python3 fmriprep_launcher.py ...` for explicitness. If the script is executable and on your `PATH`, direct invocation also works:

```bash
./fmriprep_launcher.py probe
./fmriprep_launcher.py slurm-array --help
```

### 1. Probe your environment

```bash
python3 fmriprep_launcher.py probe
```

Shows detected runtimes (Singularity/Docker), available container images, FreeSurfer license location, and TemplateFlow status.

### 2. Create config files

First, create a **user-level config** with your cluster infrastructure (once):

```bash
python3 fmriprep_launcher.py init --user
# Writes ~/.config/fmriprep/config.ini
```

Edit it to fill in your container path, FreeSurfer license, account name, etc.
These values are shared across all projects.

Then, for each dataset, create a **project config**:

```bash
cd /path/to/my_study
python3 fmriprep_launcher.py init
# Writes ./fmriprep.ini, pre-filled from your user config
```

The project config automatically picks up values from your user config, so you
only need to set dataset-specific things (`bids`, `out`, `subjects`, etc.).

Options:
- `--user` — generate user-level config at `~/.config/fmriprep/config.ini`
- `--force` — overwrite an existing config file
- `init /path/to/dir` — write project config to a specific directory

You can also copy the annotated example manually:

```bash
cp fmriprep.ini.example /path/to/my_study/fmriprep.ini
```

The launcher reads INI-format config files in priority order (later files
override earlier ones):

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` or `~/.fmriprep.ini` (user)
3. `./fmriprep.ini` (project-specific — recommended)
4. `--config path/to/file.ini` (explicit override)

The recommended split is:

- **User config** (`~/.fmriprep.ini`): stable infrastructure — `runtime`,
  `container`, `fs_license`, `templateflow_home`, `account`, `partition`.
- **Project config** (`./fmriprep.ini`): dataset-specific — `bids`, `out`,
  `work`, `subjects`, `output_spaces`, `job_name`, `log_dir`.

### 3. Express wizard for normal use

```bash
cd /path/to/my_study
python3 fmriprep_launcher.py wizard --quick
```

The quick wizard is the best default UX. It asks only for items that are still
missing after config/environment discovery.

### 4. Full interactive wizard

```bash
python3 fmriprep_launcher.py wizard
```

Walks through every option with defaults from config. Install `questionary` for a better experience:

```bash
pip install --user questionary
```

### 5. Direct CLI for scripted or repeat usage

```bash
# Generate SLURM array script:
python3 fmriprep_launcher.py slurm-array \
    --bids /path/to/BIDS \
    --out /path/to/BIDS/derivatives/fmriprep \
    --work /scratch/fmriprep_work \
    --subjects all \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --partition compute --time 24:00:00 \
    --cpus-per-task 8 --mem 32G \
    --account rrg-mypi

# Print commands without submitting:
python3 fmriprep_launcher.py print-cmd \
    --bids /path/to/BIDS \
    --subjects sub-01 sub-02 \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --output-spaces "MNI152NLin2009cAsym:res-2 T1w"
```

### 6. Rerun failed subjects from a previous job bundle

Every `slurm-array` bundle writes:

- `fmriprep_array.sbatch`
- `subjects.txt`
- `job_manifest.json`
- `status/` containing per-subject `.running`, `.ok`, and `.failed` markers

To generate a bundle containing only failed subjects:

```bash
python3 fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json
```

Optional overrides:

```bash
python3 fmriprep_launcher.py rerun-failed \
    --manifest /path/to/fmriprep_job/job_manifest.json \
    --status-dir /path/to/fmriprep_job/status \
    --script-outdir /path/to/fmriprep_rerun \
    --subjects-per-job 2 \
    --job-name fmriprep_retry
```

This writes a rerun bundle without mutating the original one.

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

Boolean values are case-insensitive (`true`/`True`/`TRUE` all work). Inline
comments use `#` (preferred) or `;`.

## TemplateFlow on Air-Gapped Compute Nodes

Most HPC compute nodes have no internet access. fMRIPrep uses [TemplateFlow](https://www.templateflow.org/) to download brain templates, which will fail on air-gapped nodes.

The launcher handles this automatically:

1. **Binds your local TemplateFlow cache** into the container at `/opt/templateflow`
2. **Sets `TEMPLATEFLOW_HOME`** inside the container (with correct Apptainer/Singularity prefix detection)
3. **Validates** that your TemplateFlow directory actually contains templates before generating scripts

**You must pre-populate the cache on a login node** (which has internet):

```bash
# Option A: Use the templateflow Python API
python -c "
import templateflow.api as tfa
tfa.get('MNI152NLin2009cAsym')
tfa.get('MNI152NLin6Asym')
tfa.get('fsaverage')
tfa.get('fsLR')
"

# Option B: Copy from someone who already has it
cp -r /project/shared/templateflow ~/.cache/templateflow

# Option C: Set a shared path in your config
# templateflow_home = /project/rrg-mypi/shared/opt/templateflow
```

Configure the path via:
- Config file: `templateflow_home = /path/to/templateflow`
- Environment: `export TEMPLATEFLOW_HOME=/path/to/templateflow`
- CLI flag: `--templateflow-home /path/to/templateflow`

## Getting the Container Image

fMRIPrep runs inside a container. You need to download or build the image once,
then point your config at it.

### Singularity / Apptainer (HPC clusters)

Run this on a **login node** (compute nodes typically have no internet):

```bash
# Pick a version from https://hub.docker.com/r/nipreps/fmriprep/tags
VERSION=24.1.0

# Build the .sif file (may take 15-30 minutes)
singularity build fmriprep_${VERSION}.sif docker://nipreps/fmriprep:${VERSION}
# or with Apptainer:
apptainer pull docker://nipreps/fmriprep:${VERSION}
```

Put the `.sif` file in a shared project directory so lab members can reuse it:

```bash
mv fmriprep_${VERSION}.sif /project/def-piname/shared/bin/
```

Then set it in your config:

```ini
container = /project/def-piname/shared/bin/fmriprep_24.1.0.sif
```

Or point `FMRIPREP_SIF_DIR` at the directory and use `container = auto`:

```bash
export FMRIPREP_SIF_DIR=/project/def-piname/shared/bin
```

### Docker (local workstation)

```bash
docker pull nipreps/fmriprep:24.1.0
```

The launcher auto-discovers local Docker images — no config path needed.

### Checking the latest version

The latest version is listed at
[hub.docker.com/r/nipreps/fmriprep/tags](https://hub.docker.com/r/nipreps/fmriprep/tags)
and [fmriprep.org/en/latest/changes.html](https://fmriprep.org/en/latest/changes.html).

## Supported Runtimes

| Runtime | Container type | Auto-detected via |
|---|---|---|
| **singularity** | `.sif` or `.simg` file | `command -v singularity \|\| command -v apptainer` |
| **docker** | Docker image:tag | `command -v docker` |
| **fmriprep-docker** | Docker image:tag | `command -v fmriprep-docker` |

The launcher auto-detects the runtime and searches for containers in `$FMRIPREP_SIF_DIR` (Singularity) or local Docker images.

## Cluster-Specific Notes

### Trillium (whole-node scheduling)

Trillium allocates entire nodes, so `--mem` in SLURM directives causes errors. Use:

```bash
# CLI:
python3 fmriprep_launcher.py slurm-array ... --no-mem

# Config:
[slurm]
no_mem = true

# Wizard: select "n" when asked "Specify memory limit?"
# GUI: leave the Memory field blank or type "none"
```

### Subject Batching

For large datasets, batch multiple subjects per job to reduce SLURM overhead:

```bash
python3 fmriprep_launcher.py slurm-array ... --subjects-per-job 4
```

This creates array tasks where each runs 4 subjects in parallel via `xargs`. Resources are automatically scaled (4x nprocs, 4x memory).

## Environment Variables

| Variable | Effect |
|---|---|
| `FMRIPREP_SIF_DIR` | Directory to search for `.sif/.simg` container images. |
| `FS_LICENSE` | Path to FreeSurfer license file (fallback if not in config). |
| `TEMPLATEFLOW_HOME` | Path to TemplateFlow cache directory. |

## Installation

Install all fmriprep launcher files to `~/.local/share/fmriprep` with entry
point symlinks in `~/bin`:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

This keeps `~/bin` clean — only `fmriprep_launcher.py` and
`run_fmriprep_wizard.sh` are symlinked there; the Python modules they import
live together in `~/.local/share/fmriprep/`.

To customize the directories:

```bash
curl -fsSL ... | bash -s -- --lib-dir ~/.fmriprep --bin-dir /opt/bin
```

Or clone the repo and add to your PATH:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
export PATH="$HOME/code/rriscripts/fmriprep:$PATH"
```

## Requirements

- **Python 3.7+**
- **SLURM** (for job submission)
- **Singularity/Apptainer or Docker** (for container execution)
- **questionary** (optional, for improved wizard experience): `pip install --user questionary`
- **textual** (optional, for the TUI): `pip install --user textual`
- **Tk** (optional, for the GUI): usually available via `python3-tk` system package

## Deprecated Features

- **ICA-AROMA** (`--use-aroma`): Removed from fMRIPrep >= 23.1.0. The launcher will warn if this option is selected.
