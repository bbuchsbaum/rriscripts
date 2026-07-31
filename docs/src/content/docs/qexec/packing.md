---
title: Packing and concurrency
description: How --pack and --jobs control how many commands run at once on each node.
---

Packing is the answer to one problem: you have far more commands than it makes
sense to have SLURM array tasks. Instead of `N` commands becoming `N` tasks,
packing makes them `K` tasks that each run `M` commands concurrently.

## The two numbers

Every packed submission is described by two numbers:

- **`K` — how many array tasks**, set by `--nodes`
- **`M` — how many commands run at once inside each task**, set by `--pack` (or
  equivalently `--jobs`)

Under the hood every packing tool calls `command_distributor.sh`, which slices
the command file and runs its slice through GNU Parallel with `--jobs M`:

```
command_distributor.sh <commands_file> <number_of_batches> [jobs_per_batch]
```

## Pack onto one node

To run commands from a file on a single node with no more than 5 active at once:

```bash
qexec.sh --file commands.txt --pack 5 --time 1 --ncpus 5
```

This submits one SLURM task and runs the command file through
`command_distributor.sh` with GNU Parallel capped at the requested pack size.

If `--ncpus` is not given and `qexec.sh` would otherwise request one CPU, it
sets `--ncpus` to the pack size — so you rarely need to state both. Ask for
enough CPUs to actually run `M` things at once.

## Pack across several nodes

To split the same file across 4 packed array tasks, with no more than 4 commands
active in each:

```bash
qexec.sh --file commands.txt --nodes 4 --pack 4 --time 1 --ncpus 4
```

With `--file --pack`, an explicit `--nodes K` means **K packed one-node array
tasks**. The example above submits `--array=1-4 --nodes=1`, and each array task
runs its slice through `command_distributor.sh` with GNU Parallel capped at 4
commands. Total concurrency is `K × M` — here, 16 commands in flight.

## `--pack` and `--jobs` are aliases

The per-task concurrency cap has two accepted long-option spellings, `--pack`
and `--jobs`, and **every tool accepts both**. These all express *K packed array
tasks with at most M commands running inside each*:

```bash
qexec.sh     --file commands.txt --nodes K --pack M
qexec.sh     --file commands.txt --nodes K --jobs M
bexec.sh     --file commands.txt --nodes K --jobs M
bexec.sh     --file commands.txt --nodes K --pack M
batch_exec.sh --nodes K --jobs M -- <command with [brackets]>
send_slurm.sh --nodes K --pack M
send_slurm.sh --nodes K --jobs M
```

:::note[Historical wrinkle]
These used to differ: `--pack` on `qexec.sh` was single-node only, while
multi-node packing lived under `--jobs` on `bexec.sh`. Both the aliasing and
multi-node `qexec.sh --pack` were added later, so older notes and scripts may
still describe the split behavior.
:::

## Packing piped commands

`send_slurm.sh` packs the same way, reading commands from stdin:

```bash
cmd_expand.sh command.sh [1..10] | send_slurm.sh --nodes 5 --pack 3 --time 1
```

In pack mode `--nodes` is the number of packed array tasks and `--pack`/`--jobs`
is the per-task concurrency cap. As with `qexec.sh`, if `--ncpus` is not
provided and it would otherwise request one CPU, it sets `--ncpus` to the pack
size.

`--array` cannot be combined with `--pack`; use `--nodes` to set the number of
packed batches.

## Choosing K and M

- `M` should not exceed the CPUs you request per task, unless the commands are
  I/O-bound rather than CPU-bound.
- `K × M` is your total concurrency. Keep it under whatever your allocation and
  the cluster's queue limits allow.
- Very small `M` wastes the node; very large `M` oversubscribes it and can push
  the task over its memory limit, since all `M` commands share one allocation.

## GNU Parallel

Packing requires GNU Parallel on the compute node. On many clusters:

```bash
module load parallel
```

Set `QEXEC_PARALLEL_BIN` if the executable is somewhere `command_distributor.sh`
would not find it.
