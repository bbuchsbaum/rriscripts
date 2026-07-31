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

There is one command you run — `fmriprep_launcher.py`. Everything else in the
directory is either an optional frontend it can launch for you or an internal
module it imports; see [Repository layout](../repository-layout/) if you need
the map.
