---
title: Installation
description: Install qexec, fmriprep, or the whole rriscripts repository.
---

Most users only need one of the two installable toolkits. `xnat_cli` is a single
R script used from a clone.

## Install qexec

Use this if you want the general-purpose SLURM helpers — `qexec.sh`,
`batch_exec.sh`, `bexec.sh`, `cmd_expand.sh`, `send_slurm.sh`, `rjobtop.py`.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

This installs the `qexec` scripts to `~/bin` by default. To install elsewhere:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash -s -- --prefix /opt/bin
```

### Prerequisites

- Bash 3.2+
- Python 3.7+
- SLURM commands such as `sbatch`, `salloc`, and `squeue`
- GNU Parallel for packed and batched command-file execution
- Tcl/Tk `wish` for the GUI tools

On many clusters GNU Parallel comes from the module system:

```bash
module load parallel
```

## Install fmriprep

Use this if you want the fMRIPrep launcher and its frontends.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

By default this installs the launcher bundle under `~/.local/share/fmriprep` and
symlinks `fmriprep_launcher.py` and `run_fmriprep_wizard.sh` into `~/bin`.

To customize locations:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash -s -- --lib-dir ~/.fmriprep --bin-dir /opt/bin
```

### Prerequisites

Python 3.10+, SLURM, and Singularity/Apptainer or Docker. `questionary`
(`pip install --user questionary`) is optional but improves the wizard UX.

The launcher also needs three things that live on the cluster rather than in
this repo — a container image, a FreeSurfer license, and a TemplateFlow cache.
See [fmriprep prerequisites](../fmriprep/prerequisites/).

## Clone the full repository

Use this if you want everything, including `xnat_cli` and the full source tree:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
cd rriscripts
```

Then put the tools on your `PATH` directly:

```bash
export PATH="$HOME/code/rriscripts/qexec:$PATH"
export PATH="$HOME/code/rriscripts/fmriprep:$PATH"
```

## Put `~/bin` on your PATH

If `~/bin` is not already on your `PATH`, add it:

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
```

## Verify

```bash
qexec.sh --help
cmd_expand.sh --help
fmriprep_launcher.py probe
Rscript xnat_cli/xnat_cli.R help
```
