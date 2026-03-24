# fmriprep/ — fMRIPrep Launcher Toolkit

A one-stop toolkit for building correct [fMRIPrep](https://fmriprep.org) commands and generating SLURM array jobs for BIDS datasets. Supports Singularity/Apptainer, fmriprep-docker, and Docker runtimes.

## Scripts at a Glance

| Script | What it does |
|---|---|
| **fmriprep_launcher.py** | Main CLI with subcommands: `probe`, `print-cmd`, `slurm-array`, and `wizard`. Handles container discovery, subject resolution, resource detection, and SLURM script generation. |
| **fmriprep_command_builder.py** | Library/wizard for building fMRIPrep commands interactively (requires `questionary`). |
| **fmriprep_tui_autocomplete.py** | Terminal UI built with [Textual](https://textual.textualize.io/) — full-featured form interface with path tab-completion. |
| **fmriprep_gui_tk.py** | Tcl/Tk GUI — works over X11 forwarding on clusters without Textual/curses. |
| **run_fmriprep_wizard.sh** | Convenience launcher for the wizard with automatic virtualenv activation. |
| **slurm_batched_template.sh** | SLURM template for batched multi-subject jobs (used internally by the launcher). |

### Config Files

| File | Purpose |
|---|---|
| **fmriprep_config_example.ini** | Example user-level config (`~/.config/fmriprep/config.ini`). |
| **fmriprep_project_example.ini** | Example project-level config (`fmriprep.ini` in your project directory). |
| **config_*.json** | JSON config examples for specific fMRIPrep versions and setups. |

## Quick Start

### 1. Probe your environment

```bash
python fmriprep_launcher.py probe
```

Shows detected runtimes (Singularity/Docker), available container images, FreeSurfer license location, and TemplateFlow status.

### 2. Express wizard (recommended for repeat use)

```bash
# Create a project config first (copy and edit the example):
cp fmriprep_project_example.ini /path/to/my_study/fmriprep.ini

# Then run with --quick (only 3-5 questions):
cd /path/to/my_study
python fmriprep_launcher.py wizard --quick
```

The express wizard asks only for:
1. BIDS path (if not in config)
2. Subject selection (all / pick specific ones)
3. Container path (if not auto-detected or in config)
4. FreeSurfer license (if not in `$FS_LICENSE` or config)
5. Whether to generate SLURM script

Everything else (resources, output spaces, SLURM partition, account, etc.) comes from your config file.

### 3. Full interactive wizard

```bash
python fmriprep_launcher.py wizard
```

Walks through every option with defaults from config. Install `questionary` for a better experience:

```bash
pip install --user questionary
```

### 4. Direct CLI (no interactivity)

```bash
# Generate SLURM array script:
python fmriprep_launcher.py slurm-array \
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
python fmriprep_launcher.py print-cmd \
    --bids /path/to/BIDS \
    --subjects sub-01 sub-02 \
    --container /path/to/fmriprep.sif \
    --fs-license /path/to/license.txt \
    --output-spaces "MNI152NLin2009cAsym:res-2 T1w"
```

## Configuration Files

The launcher reads INI-format config files in priority order:

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` or `~/.fmriprep.ini` (user)
3. `./fmriprep.ini` (project-specific — **recommended**)
4. `--config path/to/file.ini` (explicit override)

Later files override earlier ones. A well-populated project config eliminates most wizard questions:

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
python fmriprep_launcher.py slurm-array ... --no-mem

# Config:
[slurm]
no_mem = true

# Wizard: select "n" when asked "Specify memory limit?"
# GUI: leave the Memory field blank or type "none"
```

### Subject Batching

For large datasets, batch multiple subjects per job to reduce SLURM overhead:

```bash
python fmriprep_launcher.py slurm-array ... --subjects-per-job 4
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
