# qexec — SLURM Job Submission Toolkit

`qexec` is a small set of shell tools for submitting and monitoring SLURM jobs.
It covers single commands, interactive sessions, generated command grids,
prewritten command files, packed command-file runs across one or more array
tasks, and lightweight job monitoring.

📖 **Full documentation: <https://bbuchsbaum.github.io/rriscripts/qexec/>**

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

Installs to `~/bin` by default; pass `-s -- --prefix /path/to/bin` to change it.
Needs Bash 3.2+, Python 3.7+, SLURM, and GNU Parallel for packed runs.

## The tools

| Script | Purpose |
|---|---|
| `qexec.sh` | Main launcher: batch, interactive, array, and packed submissions |
| `cmd_expand.sh` | Expands `[1..10]`-style bracket expressions into command lines |
| `batch_exec.sh` | Expands a parameterized command and submits it as an array job |
| `bexec.sh` | Submits an existing command file as a batched array job |
| `send_slurm.sh` | Reads commands from stdin and submits them |
| `command_distributor.sh` | Runs a task's slice of a command file under GNU Parallel |
| `rjobtop.py` | Live CPU and memory use for a running job |
| `slurm_job_monitor.sh` | Polls jobs to completion and reports efficiency |
| `qexec_gui.tcl`, `batch_exec_gui.tcl` | Optional Tcl/Tk frontends |

## Quick examples

```bash
# One batch command
qexec.sh --time 4 --ncpus 8 --mem 32G -- Rscript run.R

# Interactive session
qexec.sh --interactive --time 4 --ncpus 8 --mem 32G

# A command file, 4 array tasks, 10 commands at a time in each
qexec.sh --file commands.txt --nodes 4 --pack 10 --ncpus 40 --time 3

# A parameter sweep
batch_exec.sh --time 2 --nodes 5 --ncpus 40 --jobs 40 -- \
    Rscript analyze.R --sub [1..100] --method [lasso,ridge]
```

Add `--dry-run` to any of these to see the computed `sbatch` call without
submitting.

For flag tables, environment variables, presets, packing semantics, and the
`cmd_expand` value syntax, see the
[qexec guide](https://bbuchsbaum.github.io/rriscripts/qexec/).

## Tests

Tests use [bats-core](https://github.com/bats-core/bats-core) and need no SLURM:

```bash
bats qexec/tests/
```

## License

See the repository root for license information.
