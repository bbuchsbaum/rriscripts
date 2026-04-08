# rriscripts

Tools for neuroimaging and SLURM-based HPC workflows. The repository currently
has three main parts:

- [`qexec/`](qexec/) for general SLURM job submission, command expansion, and job monitoring
- [`fmriprep/`](fmriprep/) for building and submitting fMRIPrep jobs
- [`xnat_cli/`](xnat_cli/) for working with XNAT from R

## Install

Most users only need one of the two installable toolkits below.

### Install `qexec`

Use this if you want general-purpose SLURM helpers such as `qexec.sh`,
`batch_exec.sh`, `cmd_expand.sh`, or `rjobtop.py`.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

This installs the `qexec` scripts to `~/bin` by default.

To install somewhere else:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash -s -- --prefix /path/to/bin
```

### Install `fmriprep`

Use this if you want the fMRIPrep launcher and its frontends.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

By default this installs the full launcher bundle under
`~/.local/share/fmriprep` and symlinks entry points into `~/bin`.

To customize locations:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash -s -- --lib-dir /path/to/lib --bin-dir /path/to/bin
```

### Clone The Full Repository

Use this if you want everything, including the XNAT CLI and the full source
tree:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
cd rriscripts
```

If `~/bin` is not already on your `PATH`, add it:

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
```

## Choose A Tool

### [`qexec/`](qexec/)

`qexec` is the general SLURM toolkit in this repo.

Main entry points:

- `qexec.sh` submits single interactive or batch jobs
- `batch_exec.sh` expands parameterized commands and submits them as a SLURM array workflow
- `bexec.sh` submits a prewritten command file as a batched job
- `cmd_expand.sh` turns bracket syntax such as `[1..10]` or `[a,b,c]` into concrete commands
- `send_slurm.sh` accepts commands on stdin and submits them as an array job
- `rjobtop.py` monitors CPU and memory usage for running SLURM jobs
- `slurm_job_monitor.sh` waits for jobs to finish and reports efficiency

Also included:

- `command_distributor.sh` for distributing command batches inside array tasks
- Tcl/Tk frontends for `qexec.sh` and `batch_exec.sh`
- Haskell implementations of several core `qexec` tools

See the full [`qexec` README](qexec/README.md) for command syntax, examples,
and cluster-oriented setup details.

### [`fmriprep/`](fmriprep/)

`fmriprep` is a launcher toolkit for generating correct fMRIPrep commands and
SLURM job bundles for BIDS datasets.

Main entry points:

- `fmriprep_launcher.py` is the canonical CLI
- `run_fmriprep_wizard.sh` is a convenience wrapper for the wizard flow
- `fmriprep_tui_autocomplete.py` provides a Textual terminal UI
- `fmriprep_gui_tk.py` provides a Tk GUI

The launcher currently supports:

- environment probing
- project and user config initialization
- command preview via `print-cmd`
- SLURM array bundle generation via `slurm-array`
- reruns for failed subjects via `rerun-failed`

See the full [`fmriprep` README](fmriprep/README.md) for configuration,
runtime detection, TemplateFlow handling, and launcher examples.

### [`xnat_cli/`](xnat_cli/)

`xnat_cli/xnat_cli.R` is an R-based CLI for XNAT repositories built on
`xnatR`.

It supports:

- authentication and token management
- listing projects, subjects, experiments, and scans
- scan search
- downloading files, experiments, subjects, or full project data

This tool is used directly from the repo unless you choose to symlink or copy
it into your own `PATH`.

## Requirements

Requirements depend on which part of the repo you use.

- `qexec` needs Bash, Python 3, SLURM, and GNU Parallel for the batched-array workflow
- `fmriprep` needs Python 3 plus whichever runtime you use to run fMRIPrep, such as Apptainer/Singularity or Docker
- `xnat_cli` needs R with `optparse` and `xnatR`
- Tcl/Tk is only needed for the GUI frontends

## More Documentation

- [`qexec/README.md`](qexec/README.md)
- [`fmriprep/README.md`](fmriprep/README.md)

## License

[Mozilla Public License 2.0](LICENSE)
