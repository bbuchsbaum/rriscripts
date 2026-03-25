# rriscripts

Scripts and tools for neuroimaging research on SLURM-based HPC clusters. Built for day-to-day use at [RRI](https://research.baycrest.org/rotman) but designed to be portable to any SLURM environment.

## Contents

### [`qexec/`](qexec/) — SLURM Job Submission Toolkit

A complete pipeline for parameterized batch job submission on SLURM clusters:

- **cmd_expand.sh** — expand parameterized commands via Cartesian product or positional zip (ranges, file lists, CSV columns, globs)
- **qexec.sh** — submit single interactive (`salloc`) or batch (`sbatch`) jobs with a clean option interface
- **batch_exec.sh** — orchestrator that expands commands and distributes them across a SLURM array job via GNU Parallel
- **command_distributor.sh** — splits a command file by array task ID and runs each batch in parallel
- **rjobtop.py** — live CPU/memory monitoring for running SLURM jobs (great for R/future/callr workloads)
- **Tcl/Tk GUIs** for both `qexec.sh` and `batch_exec.sh` with tooltips, output preview, and input validation
- **Haskell implementations** of the core scripts for compiled-binary deployments

See the full **[qexec README](qexec/README.md)** for usage examples, the expansion syntax reference, installation instructions, and how the scripts compose together.

### [`fmriprep/`](fmriprep/) — fMRIPrep Launcher

Tools for building and submitting [fMRIPrep](https://fmriprep.org) preprocessing jobs:

- **fmriprep_launcher.py** — one-stop CLI with `init`, `probe`, `print-cmd`, `slurm-array`, `rerun-failed`, and `wizard` subcommands. Auto-detects runtimes and containers. Supports Singularity/Apptainer, fmriprep-docker, and Docker.
- **Express wizard** (`wizard --quick`) — only asks 3-5 questions when a project config file is present; derives everything else from config/env
- **fmriprep_gui_tk.py** / **fmriprep_tui_autocomplete.py** — graphical (Tk) and terminal (Textual) UI front-ends
- **TemplateFlow support** — automatically binds and validates TemplateFlow caches for air-gapped compute nodes
- **Retry support** — generated job bundles include `job_manifest.json` plus per-subject `status/` markers so failed subjects can be resubmitted with `rerun-failed`
- **Config system** — cascading INI configs (system → user → project → CLI) so you set paths once and reuse

See the full **[fMRIPrep README](fmriprep/README.md)** for usage examples, configuration guide, TemplateFlow setup, and cluster-specific notes.

### [`xnat_cli/`](xnat_cli/) — XNAT Command-Line Client

- **xnat_cli.R** — an R CLI for [XNAT](https://www.xnat.org/) repositories. List projects, subjects, experiments, and scans; download files for individual subjects or entire projects. Built on the `xnatR` package.

## Quick Install

Each sub-project can be installed independently to `~/bin`:

```bash
# SLURM job submission toolkit
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash

# fMRIPrep launcher (installs to ~/.local/share/fmriprep, symlinks to ~/bin)
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

Use `-- --prefix /dir` (qexec) or `-- --lib-dir /dir --bin-dir /dir` (fmriprep)
to customize install paths. Or clone the whole repo:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
```

## Requirements

- **bash** 4.0+, **Python 3.7+**
- **SLURM** (for job submission scripts)
- **GNU Parallel** (for `command_distributor.sh`)
- **R** (for `xnat_cli.R`)
- **Tcl/Tk** (`wish`) — only for the GUI tools

Most of these are already available on typical HPC clusters.

## License

[Mozilla Public License 2.0](LICENSE)
