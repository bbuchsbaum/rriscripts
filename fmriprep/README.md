# fmriprep/ — fMRIPrep Launcher Toolkit

This directory contains one backend with several frontends for building correct
[fMRIPrep](https://fmriprep.org) commands and generating SLURM array jobs for
BIDS datasets.

The important distinction is:

- `fmriprep_launcher.py` is the canonical entrypoint.
- The Textual UI, Tk UI, and shell wrapper are optional frontends.
- `fmriprep_command_builder.py` is a legacy interactive frontend kept for compatibility.
- INI is the canonical config format.
- The `config_*.json` files are legacy examples and are not read by the current launcher.

## Start Here

For most users, the recommended path is:

1. Probe your environment.
2. Create a project `fmriprep.ini`.
3. Run `fmriprep_launcher.py wizard --quick`.
4. Use `print-cmd` or `slurm-array` directly once the config is stable.
5. If some subjects fail, use `rerun-failed` on the generated `job_manifest.json`.

### Canonical Entry Points

| File | Status | Purpose |
|---|---|---|
| **fmriprep_launcher.py** | Recommended | Main CLI with subcommands: `probe`, `print-cmd`, `slurm-array`, `rerun-failed`, and `wizard`. Owns runtime detection, config loading, subject discovery, command generation, SLURM script generation, and retry bundle generation for failed subjects. |
| **run_fmriprep_wizard.sh** | Convenience | Wrapper that activates a likely virtualenv and launches `fmriprep_launcher.py wizard`. |
| **fmriprep_project_example.ini** | Recommended | Project-level config example (`./fmriprep.ini`). This is the most useful config file for repeatable runs. |
| **fmriprep_config_example.ini** | Optional | User-level config example (`~/.config/fmriprep/config.ini`). Useful for personal defaults shared across projects. |

### Optional Frontends

| File | Purpose |
|---|---|
| **fmriprep_tui_autocomplete.py** | Terminal UI built with [Textual](https://textual.textualize.io/). Best terminal frontend when `textual` is available. |
| **fmriprep_gui_tk.py** | Tk GUI for clusters or desktops where Textual is unavailable but Tk/X11 works. |

### Compatibility / Internal Files

| File | Status | Notes |
|---|---|---|
| **fmriprep_command_builder.py** | Legacy frontend | Older interactive questionary-based builder. Prefer `fmriprep_launcher.py wizard`. |
| **slurm_batched_template.sh** | Internal template | Used by the launcher when generating batched SLURM jobs. Not intended as a primary user entrypoint. |
| **config_simple.json** / **config_fixed.json** / **config_v3.json** | Legacy examples | Not read by the current launcher. Keep only as historical examples unless you have an external workflow that still uses them. |

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

### 2. Create a project config

The launcher reads INI-format config files in priority order:

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` or `~/.fmriprep.ini` (user)
3. `./fmriprep.ini` (project-specific — recommended)
4. `--config path/to/file.ini` (explicit override)

Later files override earlier ones.

```bash
cp fmriprep_project_example.ini /path/to/my_study/fmriprep.ini
```

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

Every `slurm-array` bundle now writes:

- `fmriprep_array.sbatch`
- `subjects.txt`
- `job_manifest.json`
- `status/` containing per-subject `.running`, `.ok`, and `.failed` markers

To generate a new bundle containing only failed subjects:

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

This writes a fresh rerun bundle without mutating the original one.

## Configuration Files

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

Use INI for all current workflows. The JSON example files in this directory are
legacy artifacts and are not loaded by `fmriprep_launcher.py`.

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

## Requirements

- **Python 3.7+**
- **SLURM** (for job submission)
- **Singularity/Apptainer or Docker** (for container execution)
- **questionary** (optional, for improved wizard experience): `pip install --user questionary`
- **textual** (optional, for the TUI): `pip install --user textual`
- **Tk** (optional, for the GUI): usually available via `python3-tk` system package

## Deprecated Features

- **ICA-AROMA** (`--use-aroma`): Removed from fMRIPrep >= 23.1.0. The launcher will warn if this option is selected.
