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

### `qexec.sh` — run something on the cluster

Give it a command and the resources it needs, and it submits that command as a
SLURM job:

```bash
qexec.sh --time 4 --ncpus 8 --mem 32G -- Rscript run.R
```

It also handles interactive sessions (`--interactive`) and whole files of
commands (`--file`). Under the hood it builds an `sbatch` or `salloc` call and
runs it — `--dry-run` shows you that call without submitting.

### `cmd_expand.sh` — write out one command per subject

The common HPC chore is running the same script over 100 subjects, or every
combination of 50 subjects × 3 ROIs. Writing those command lines by hand is
tedious and easy to get wrong. `cmd_expand.sh` writes them for you: you give it
one command with the varying parts in brackets, and it prints the full list.

```bash
cmd_expand.sh Rscript run.R --sub [1..3] --roi [V1,MT]
```

```text
Rscript run.R --sub 1 --roi V1
Rscript run.R --sub 1 --roi MT
Rscript run.R --sub 2 --roi V1
Rscript run.R --sub 2 --roi MT
Rscript run.R --sub 3 --roi V1
Rscript run.R --sub 3 --roi MT
```

It submits nothing — it just prints. That is the point: you can read the list,
count it, and fix a mistake before it becomes 600 queued jobs. Save it to a file
and hand it to `qexec.sh --file`, or pipe it straight into `send_slurm.sh`.

The brackets also read from files (`[file:subjects.txt]`), CSV columns
(`[df:subject:data.csv]`), and globs (`[glob:data/*.nii]`) — see
[`cmd_expand` syntax](./cmd-expand/).

---

Those two cover the whole toolkit. Everything below is a convenience on top of
them.

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
| `qexec.hs`, `cmd_expand.hs`, `bexec.hs`, `command_distributor.hs` | **Deprecated.** Haskell ports, kept for reference and scheduled for removal — see below. |

:::note[Coverage is uneven]
The submission path is well covered by the [bats suite](https://github.com/bats-core/bats-core) —
`qexec.sh` has 57 tests, `cmd_expand.sh` 23, `command_distributor.sh` 13,
`batch_exec.sh` 13, `send_slurm.sh` 7, `bexec.sh` 4.

The tools in this last section have **no automated tests**: the monitors need a
live SLURM job and a Linux `/proc`, and the GUIs need a display. Nothing there is
broken as far as anyone knows — it is just less exercised, so check its output
rather than assuming.
:::

:::caution[The Haskell ports are deprecated]
`qexec.hs`, `cmd_expand.hs`, `bexec.hs`, and `command_distributor.hs` were an
exercise. They landed in one commit in December 2025 and were never revised,
while the shell tools kept moving — `qexec.hs` alone is missing multi-node
packing (`--pack`/`--jobs`), `--preset`, `--after`, `--wait`, `~/.qexecrc`, and
`CC_CLUSTER` detection.

Nothing builds, installs, or tests them: `install.sh` ships only the shell
scripts and CI does not compile Haskell. They are kept for reference and are
expected to be removed. **Use the shell versions.**
:::

`command_distributor.sh` also ships in the directory but runs *inside* an array
task rather than being called directly; see
[Repository layout](../repository-layout/).

## Where to next

Both `--flag value` and `--flag=value` forms work throughout, so
`--time 4` and `--time=4` are interchangeable.

- [Workflows](./workflows/) — the common submission patterns, start to finish
- [Packing and concurrency](./packing/) — running many commands per node
- [`cmd_expand` syntax](./cmd-expand/) — every bracket form and both expansion modes
- [Monitoring jobs](./monitoring/) — watching a run and catching a wasted allocation
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
