---
title: fmriprep
description: A launcher toolkit that builds fMRIPrep commands and SLURM array bundles for BIDS datasets.
---

The `fmriprep` toolkit builds [fMRIPrep](https://fmriprep.org) commands and
SLURM array jobs for BIDS datasets. It supports Singularity/Apptainer, the
`fmriprep-docker` wrapper, and plain Docker. INI is the only supported config
format.

This directory contains several interfaces, but there is **one recommended
path**:

1. Use `fmriprep_launcher.py`.
2. Put stable settings in INI config files.
3. Generate a SLURM bundle with `fmriprep_launcher.py slurm-array`.
4. Submit the generated `fmriprep_array.sbatch` with `sbatch`.

That is the default, no-frills command-line workflow. It is non-interactive,
reproducible, and writes the `job_manifest.json` needed by `rerun-failed`.

The wizard, Textual TUI, Tk GUI, and `run_fmriprep_wizard.sh` are convenience
frontends around the same launcher and backend. They are optional — do not treat
them as separate primary workflows.

## Start here

- [Prerequisites](./prerequisites/) — the container image, FreeSurfer license,
  and TemplateFlow cache you need on the cluster first
- [Command-line workflow](./workflow/) — the recommended end-to-end path
- [Subcommands](./subcommands/) — `probe`, `init`, `slurm-array`, `print-cmd`,
  `rerun-failed`, and the interactive frontends
- [Configuration reference](./configuration/) — every INI key
- [Cluster notes](./cluster-notes/) — read-only filesystems, whole-node
  scheduling, subject batching

## Installation

See [Installation](../install/#install-fmriprep). In short:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

**Requirements:** Python 3.10+, SLURM, and Singularity/Apptainer or Docker.
`questionary` (`pip install --user questionary`) is optional but improves the
wizard UX.

## What's in this directory

| File | Purpose |
|---|---|
| `fmriprep_launcher.py` | Main CLI entrypoint. |
| `fmriprep_backend.py` | `BuildConfig`, command construction, SLURM template, manifest I/O. |
| `fmriprep_shared.py` | INI loading, runtime detection, subject discovery, memory parsing. |
| `fmriprep_tui_autocomplete.py` | Optional Textual TUI (`pip install textual`). |
| `fmriprep_gui_tk.py` | Optional Tk GUI (needs Tk and an X11 display). |
| `fmriprep.ini.example` | Annotated example covering user-level and project-level keys. |
| `run_fmriprep_wizard.sh` | Convenience wrapper that activates a likely venv before launching the wizard. |
| `install.sh` | One-shot installer. |
| `tests/` | Unit tests (`python3 -m unittest tests.test_backend`). |

## Deprecated

**ICA-AROMA** (`--use-aroma`) was removed from fMRIPrep ≥ 23.1.0. The launcher
raises an error if this option is set.
