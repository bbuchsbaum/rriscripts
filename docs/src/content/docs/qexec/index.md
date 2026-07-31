---
title: qexec
description: A small set of shell tools for submitting and monitoring SLURM jobs.
---

`qexec` is a small set of shell tools for submitting and monitoring SLURM jobs.
It covers single commands, interactive sessions, generated command grids,
prewritten command files, packed command-file runs across one or more array
tasks, and lightweight job monitoring.

Nothing here replaces SLURM — `qexec.sh` computes an `sbatch`/`salloc`
invocation and runs it. `--dry-run` prints exactly what it would submit, which
makes it easy to check your reasoning before spending an allocation.

## The tools

| Script | Purpose |
|---|---|
| `qexec.sh` | Main SLURM launcher. Submits batch jobs with `sbatch`, interactive jobs with `salloc`, command files as arrays, and packed command files with a per-task concurrency cap. |
| `cmd_expand.sh` | Expands bracket expressions into concrete command lines. Use it to generate command files or pipe commands into `send_slurm.sh`. |
| `batch_exec.sh` | Expands a parameterized command with `cmd_expand.sh`, then submits the generated commands as a SLURM array job using `command_distributor.sh`. |
| `bexec.sh` | Submits an existing command file as a batched SLURM array job using `command_distributor.sh`. |
| `command_distributor.sh` | Runs inside a SLURM array task, selects that task's slice of a command file, and executes the slice with GNU Parallel. |
| `send_slurm.sh` | Reads commands from stdin, persists them under `.qexec-state` or `--state-dir`, and submits them as one command per SLURM array task or as packed batches with `--pack`. |
| `rjobtop.py` | Shows live CPU and memory use for a running SLURM job. |
| `slurm_job_monitor.sh` | Polls SLURM jobs until completion and reports efficiency with `seff` when available. |
| `qexec_gui.tcl` | Tcl/Tk GUI for `qexec.sh`. |
| `batch_exec_gui.tcl` | Tcl/Tk GUI for `batch_exec.sh`. |
| `batch_exec_gui` | Convenience launcher for `batch_exec_gui.tcl`. |

Haskell implementations of several core tools (`qexec.hs`, `cmd_expand.hs`,
`bexec.hs`, `command_distributor.hs`) also live in the directory.

## Start here

```bash
qexec.sh --time 4 --ncpus 8 --mem 32G --account mylab -- Rscript run.R
```

Both `--flag value` and `--flag=value` forms work throughout:

```bash
qexec.sh --time=4 --ncpus=8 --mem=32G --account=mylab -- Rscript run.R
```

Then read:

- [Workflows](./workflows/) — the common submission patterns
- [Packing and concurrency](./packing/) — running many commands per node
- [`cmd_expand` syntax](./cmd-expand/) — turning `[1..100]` into commands
- [Reference](./reference/) — every flag, environment variable, and preset

## Installation

See [Installation](../install/#install-qexec). In short:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

## Tests

Tests use [bats-core](https://github.com/bats-core/bats-core). They do not
require SLURM — they use dry runs and mocks.

```bash
git clone https://github.com/bats-core/bats-core.git /tmp/bats-core
PATH="/tmp/bats-core/bin:$PATH" bats qexec/tests/
```
