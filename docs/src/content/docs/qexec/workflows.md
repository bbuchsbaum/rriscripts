---
title: Workflows
description: The common qexec submission patterns, from a single command to a generated parameter sweep.
---

## Run one batch command

```bash
qexec.sh --time 4 --ncpus 8 --mem 32G --account mylab -- Rscript run.R
```

Everything after `--` is the command to run. `qexec.sh` accepts both flag forms:

```bash
qexec.sh --time=4 --ncpus=8 --mem=32G --account=mylab -- Rscript run.R
```

Add `--dry-run` to print the computed `sbatch` call and job script without
submitting anything.

## Start an interactive session

```bash
qexec.sh --interactive --time 4 --ncpus 8 --mem 32G
```

This uses `salloc` rather than `sbatch`. Add `--nox11` if the cluster or session
should not request X11 forwarding.

## Run one command per array task

Create a command file with one command per nonblank line:

```text
sleep 60
sleep 30
sleep 25
```

Submit it as a SLURM array, one command per task:

```bash
qexec.sh --file commands.txt --time 1 --ncpus 1
```

This submits `--array=1-N`, where `N` is the number of nonblank command lines.
Each task gets its own allocation — the right shape when individual commands are
substantial. For many short commands, [pack them](../packing/) instead.

## Batch a command file across several array tasks

Use `bexec.sh` when you already have a command file and want it split across
several array tasks, each running many commands concurrently:

```bash
bexec.sh --file commands.txt --nodes 4 --jobs 10 --ncpus 40 --time 3
```

This creates a 4-task array. Each array task receives a slice of `commands.txt`
and runs up to 10 commands at a time.

`qexec.sh` expresses the same thing directly:

```bash
qexec.sh --file commands.txt --nodes 4 --pack 10 --ncpus 40 --time 3
```

`bexec.sh` exists mainly for its file-oriented defaults (40 CPUs, 40 parallel
jobs, 1 hour) so routine submissions stay short.

## Generate and submit a command grid

Use `batch_exec.sh` when the command lines can be generated from bracket
expressions instead of written out:

```bash
batch_exec.sh --time 2 --nodes 5 --ncpus 40 --mem 16G --jobs 40 -- \
    Rscript analyze.R --sub [1..100] --method [lasso,ridge]
```

This expands to 200 commands, submits a 5-task SLURM array, and runs each task's
slice with GNU Parallel. See [`cmd_expand` syntax](../cmd-expand/) for
everything that can go inside the brackets.

## Generate, review, then submit

Bracket expansion is easy to get subtly wrong, so it is often worth looking at
the commands before spending an allocation:

```bash
cmd_expand.sh Rscript run.R --sub [1..50] --roi [V1,MT,FFA] > commands.txt
cat commands.txt
bexec.sh --file commands.txt --nodes 4 --jobs 10 --ncpus 40 --time 3
```

For a single-node packed run from the same file:

```bash
qexec.sh --file commands.txt --pack 5 --ncpus 5 --time 1
```

## Pipe commands into SLURM

```bash
cmd_expand.sh prog [1..50] | send_slurm.sh --time 2 --ncpus 8
```

`send_slurm.sh` stores the generated commands and a runner script under
`.qexec-state` by default, so the submitted job can still read them after the
shell pipeline exits. Override the location with `--state-dir` or
`QEXEC_STATE_DIR`.

To split piped commands across 5 packed array tasks, with at most 3 commands
running at once in each task:

```bash
cmd_expand.sh command.sh [1..10] | send_slurm.sh --nodes 5 --pack 3 --time 1
```

## Chain jobs with dependencies

`--after JOBID` submits with `sbatch --dependency=afterok:JOBID`, so the second
job starts only if the first succeeds:

```bash
qexec.sh --time 1 -- Rscript step1.R
# Executing: sbatch --time=60 ...
# Submitted batch job 12345

qexec.sh --after 12345 --time 2 -- Rscript step2.R
```

`qexec.sh` prints its computed `sbatch` call before submitting, so its stdout is
more than just the job ID. To capture the ID in a script, pull the trailing
number off the last line:

```bash
first=$(qexec.sh --time 1 -- Rscript step1.R | grep -oE '[0-9]+$' | tail -1)
qexec.sh --after "$first" --time 2 -- Rscript step2.R
```

## Wait for a job and see how it went

```bash
qexec.sh --wait --time 1 --ncpus 4 -- Rscript run.R
```

`--wait` blocks until the batch job finishes and then reports efficiency stats.
For jobs you have already submitted, use
[`slurm_job_monitor.sh`](../monitoring/).

## Use a resource preset

```bash
qexec.sh --preset freesurfer -- recon-all -s sub-01 -all
```

Presets set time, CPUs, and memory in one flag. Explicit flags after the preset
override it. See [the preset table](../reference/#resource-presets).
