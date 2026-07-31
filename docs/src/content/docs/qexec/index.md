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

## The two that matter

Almost everything is one of these:

| Command | What it does |
|---|---|
| `qexec.sh` | Submits work to SLURM — a single command, an interactive session, or a command file as an array. |
| `cmd_expand.sh` | Turns `[1..100]`-style patterns into concrete command lines, so you can read them before submitting. |

Learning those two covers the whole toolkit. Everything below is a convenience
on top of them.

## Convenience wrappers

Three scripts wrap `qexec.sh` with defaults tuned for a particular input shape.
Each one shells out to `qexec.sh` and `command_distributor.sh`, so anything they
do, `qexec.sh` can do with more typing:

| Command | Saves you from |
|---|---|
| `bexec.sh` | Spelling out the batched-array defaults for a command file you already have. |
| `batch_exec.sh` | Running `cmd_expand.sh` yourself before submitting a generated grid. |
| `send_slurm.sh` | Writing a command file at all, when commands arrive on stdin. |

Reach for them when they fit; ignore them otherwise.

## Also in the directory

These ship with the toolkit but sit outside the main path:

| Command | Notes |
|---|---|
| `rjobtop.py` | Live CPU and memory for a running job. Linux-only — it reads `/proc`, so it does not run on macOS. |
| `slurm_job_monitor.sh` | Polls jobs to completion and reports `seff` efficiency stats. Also what `qexec.sh --wait` calls. |
| `qexec_gui.tcl`, `batch_exec_gui.tcl` | Tcl/Tk frontends. Not installed by `install.sh`; run them from a clone. |
| `qexec.hs`, `cmd_expand.hs`, `bexec.hs`, `command_distributor.hs` | Haskell reimplementations. Not built or installed by `install.sh`. |

:::note[Coverage is uneven]
The submission path is well covered by the [bats suite](https://github.com/bats-core/bats-core) —
`qexec.sh` has 57 tests, `cmd_expand.sh` 23, `command_distributor.sh` 13,
`batch_exec.sh` 13, `send_slurm.sh` 7, `bexec.sh` 4.

The tools in this last section have **no automated tests**: the monitors need a
live SLURM job and a Linux `/proc`, and the GUIs need a display. The Haskell
ports are not built by CI either, so treat them as unmaintained relative to the
shell versions. Nothing here is broken as far as anyone knows — it is just less
exercised, so check its output rather than assuming.
:::

`command_distributor.sh` also ships in the directory but runs *inside* an array
task rather than being called directly; see
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
