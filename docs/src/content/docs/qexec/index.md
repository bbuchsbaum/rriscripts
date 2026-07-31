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

## The commands

Most work uses one or two of these. Start with `qexec.sh`; reach for the others
when your commands come from somewhere other than a file you wrote by hand.

**Submitting**

| Command | Use it when |
|---|---|
| `qexec.sh` | You have a command, an interactive session, or a command file. Does all of it. |
| `bexec.sh` | You have a command file and want the batched-array defaults without spelling them out. |
| `batch_exec.sh` | Your commands follow a pattern like `--sub [1..100]`. |
| `send_slurm.sh` | Your commands arrive on stdin, from `cmd_expand.sh` or something else. |

**Generating**

| Command | Use it when |
|---|---|
| `cmd_expand.sh` | You want to turn `[1..100]` into concrete command lines, and look at them before submitting. |

**Watching**

| Command | Use it when |
|---|---|
| `rjobtop.py` | A job is running and you want live CPU and memory use. |
| `slurm_job_monitor.sh` | You want to be told when jobs finish, with efficiency stats. |

Optional Tcl/Tk frontends (`qexec_gui.tcl`, `batch_exec_gui.tcl`) and Haskell
reimplementations of several tools also ship in the directory; see
[Repository layout](../repository-layout/).

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
