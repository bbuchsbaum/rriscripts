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

- **fmriprep_launcher.py** — one-stop CLI to probe your environment, build per-subject fMRIPrep commands, and generate SLURM array scripts for a BIDS dataset. Supports Singularity/Apptainer, fmriprep-docker, and Docker.
- **fmriprep_gui_tk.py** / **fmriprep_tui.py** — graphical and terminal UI front-ends for the launcher
- **run_fmriprep_wizard.sh** — interactive wizard for guided setup
- **Config templates** — example `.ini` and `.json` files for common fMRIPrep configurations

See the **[fMRIPrep launcher README](fmriprep/README_fmriprep_launcher.md)** for quick-start examples.

### [`xnat_cli/`](xnat_cli/) — XNAT Command-Line Client

- **xnat_cli.R** — an R CLI for [XNAT](https://www.xnat.org/) repositories. List projects, subjects, experiments, and scans; download files for individual subjects or entire projects. Built on the `xnatR` package.

## Requirements

- **bash** 4.0+, **Python 3.7+**
- **SLURM** (for job submission scripts)
- **GNU Parallel** (for `command_distributor.sh`)
- **R** (for `xnat_cli.R`)
- **Tcl/Tk** (`wish`) — only for the GUI tools

Most of these are already available on typical HPC clusters. See the [qexec README](qexec/README.md#installation) for detailed installation steps.

## License

[Mozilla Public License 2.0](LICENSE)
