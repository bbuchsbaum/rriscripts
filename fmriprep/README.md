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
2. Generate a project config with `fmriprep_launcher.py init`.
3. Edit the generated `fmriprep.ini` for your dataset.
4. Run `fmriprep_launcher.py wizard --quick`.
5. Use `print-cmd` or `slurm-array` directly once the config is stable.
6. If some subjects fail, use `rerun-failed` on the generated `job_manifest.json`.

### Canonical Entry Points

| File | Status | Purpose |
|---|---|---|
| **fmriprep_launcher.py** | Recommended | Main CLI with subcommands: `init`, `probe`, `print-cmd`, `slurm-array`, `rerun-failed`, and `wizard`. Owns runtime detection, config loading, subject discovery, command generation, SLURM script generation, and retry bundle generation for failed subjects. |
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

Generate a starter config in your BIDS directory:

```bash
python3 fmriprep_launcher.py init /path/to/my_study
```

This creates `fmriprep.ini` with sensible defaults. If you have a user-level
config (`~/.fmriprep.ini`), its values are pre-filled automatically — so
cluster paths, container locations, and account names carry over without
retyping. Edit the generated file to set dataset-specific values (subjects,
output spaces, etc.).

Options:
- `--force` — overwrite an existing `fmriprep.ini`
- Omit the directory argument to write into the current directory

You can also copy an example manually:

```bash
cp fmriprep_project_example.ini /path/to/my_study/fmriprep.ini
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

## Installation

Download all fmriprep launcher scripts to `~/bin` in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

To install to a different directory:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash -s -- --prefix /opt/bin
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
