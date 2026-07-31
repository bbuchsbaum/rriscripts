---
title: Choosing a tool
description: Which rriscripts tool to reach for, and how the overlapping qexec submitters relate to each other.
---

The three toolkits do not overlap: `qexec` submits SLURM jobs, `fmriprep`
builds fMRIPrep jobs, `xnat_cli` talks to XNAT. Within `qexec`, though, several
tools can submit a command file, and picking between them is the one genuinely
confusing choice in this repo. This page exists to make that choice fast.

## The qexec submitters

The question is always the same: **what shape is your work, and do you want it
on one node or several?**

| Your input | One node | Several nodes |
|---|---|---|
| A single command | `qexec.sh -- <cmd>` | — |
| An interactive shell | `qexec.sh --interactive` | — |
| A file of commands | `qexec.sh --file f.txt --pack M` | `qexec.sh --file f.txt --nodes K --pack M`<br />or `bexec.sh --file f.txt --nodes K --jobs M` |
| A parameter sweep | `batch_exec.sh --nodes 1 --jobs M -- <cmd> [1..N]` | `batch_exec.sh --nodes K --jobs M -- <cmd> [1..N]` |
| Commands on stdin | `… \| send_slurm.sh --pack M` | `… \| send_slurm.sh --nodes K --pack M` |

Read `K` as *how many nodes* and `M` as *how many commands at once on each
node*.

## One command per task, or many?

Without a concurrency flag, a command file becomes a **one-command-per-task**
array — `N` commands means `N` array tasks:

```bash
qexec.sh --file commands.txt --time 1 --ncpus 1   # --array=1-N
```

That is the right shape when each command is big enough to deserve its own
allocation. When you have hundreds of short commands, it wastes scheduler
overhead — pack them instead, so a smaller number of tasks each run several
commands concurrently. See [Packing and concurrency](../qexec/packing/).

## `--pack` and `--jobs` are the same knob

Every packing tool eventually calls `command_distributor.sh`, which runs the
slice through GNU Parallel with `--jobs M`. Historically that cap surfaced under
two different flag names; **both spellings are now accepted everywhere**, so
these are all the same request — *K packed array tasks, at most M commands
running inside each*:

```bash
qexec.sh --file commands.txt --nodes K --pack M
qexec.sh --file commands.txt --nodes K --jobs M
bexec.sh --file commands.txt --nodes K --jobs M
bexec.sh --file commands.txt --nodes K --pack M
batch_exec.sh --nodes K --jobs M -- <command>
send_slurm.sh --nodes K --pack M
send_slurm.sh --nodes K --jobs M
```

Pick the tool by input shape, not by flag name.

## So why are there several tools?

They differ only in where the command list comes from:

| Tool | Gets commands from | Use when |
|---|---|---|
| `qexec.sh` | a file (`--file`) | you already have the file and want one tool for everything |
| `bexec.sh` | a file (`--file`) | you want the file-oriented defaults (40 cpus, 40 jobs) without spelling them out |
| `batch_exec.sh` | bracket expansion of a template command | your commands follow a pattern like `--sub [1..100]` |
| `send_slurm.sh` | stdin | you are piping from `cmd_expand.sh` or generating commands on the fly |

`bexec.sh` and `batch_exec.sh` are thin wrappers over `qexec.sh` +
`command_distributor.sh`. Anything they do, `qexec.sh` can do with more typing.

## The other two toolkits

**Use `fmriprep`** when the job is fMRIPrep specifically. It knows about BIDS
layouts, container runtimes, FreeSurfer licenses, TemplateFlow, and per-subject
retry — none of which `qexec` models. Start at
[the fmriprep workflow](../fmriprep/workflow/).

**Use `xnat_cli`** to get data off an XNAT server before any of the above.
Start at [authentication](../xnat-cli/authentication/).
