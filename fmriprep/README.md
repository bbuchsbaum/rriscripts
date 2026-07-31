# fmriprep — fMRIPrep Launcher Toolkit

Builds [fMRIPrep](https://fmriprep.org) commands and SLURM array jobs for BIDS
datasets. Supports Singularity/Apptainer, the `fmriprep-docker` wrapper, and
plain Docker. INI is the only supported config format.

📖 **Full documentation: <https://bbuchsbaum.github.io/rriscripts/fmriprep/>**

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

Installs the launcher to `~/.local/share/fmriprep` and symlinks
`fmriprep_launcher.py` and `run_fmriprep_wizard.sh` into `~/bin`.

**Requirements:** Python 3.10+, SLURM, and Singularity/Apptainer or Docker.

## The recommended workflow

There are several frontends, but one recommended path:

1. Use `fmriprep_launcher.py`.
2. Put stable settings in INI config files.
3. Generate a SLURM bundle with `fmriprep_launcher.py slurm-array`.
4. Submit the generated `fmriprep_array.sbatch` with `sbatch`.

```bash
fmriprep_launcher.py init --user   # cluster infrastructure config
fmriprep_launcher.py init          # per-dataset config
fmriprep_launcher.py probe         # check what's detected
fmriprep_launcher.py slurm-array --script-outdir "$JOB_DIR"
sbatch "$JOB_DIR/fmriprep_array.sbatch"

# Retry only the subjects that failed:
fmriprep_launcher.py rerun-failed --manifest "$JOB_DIR/job_manifest.json"
```

The wizard, Textual TUI, and Tk GUI are convenience frontends around the same
backend — not separate primary workflows.

## Before your first run

You need three things on the cluster: an fMRIPrep container image, a FreeSurfer
license, and a populated TemplateFlow cache. All three must be set up from a
login node, since compute nodes typically have no internet access. See
[Prerequisites](https://bbuchsbaum.github.io/rriscripts/fmriprep/prerequisites/).

## What's in this directory

| File | Purpose |
|---|---|
| `fmriprep_launcher.py` | Main CLI entrypoint |
| `fmriprep_backend.py` | Command construction, SLURM template, manifest I/O |
| `fmriprep_shared.py` | INI loading, runtime detection, subject discovery |
| `fmriprep_tui_autocomplete.py` | Optional Textual TUI |
| `fmriprep_gui_tk.py` | Optional Tk GUI |
| `fmriprep.ini.example` | Annotated example config |
| `run_fmriprep_wizard.sh` | Wrapper that activates a venv before the wizard |
| `install.sh` | One-shot installer |
| `tests/` | Unit tests (`python3 -m unittest discover -s tests`) |

For the full INI key reference, subcommand documentation, and cluster notes
(read-only filesystems, whole-node scheduling, subject batching), see the
[fmriprep guide](https://bbuchsbaum.github.io/rriscripts/fmriprep/).

## Deprecated

**ICA-AROMA** (`--use-aroma`) was removed from fMRIPrep ≥ 23.1.0. The launcher
raises an error if this option is set.
