# qexec - SLURM Job Submission Toolkit

`qexec` is a small set of shell tools for submitting and monitoring SLURM jobs. It covers single commands, interactive sessions, generated command grids, prewritten command files, packed command-file runs across one or more array tasks, and lightweight job monitoring.

## Tools

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

## Common Workflows

### Run One Batch Command

```bash
qexec.sh --time 4 --ncpus 8 --mem 32G --account mylab -- Rscript run.R
```

`qexec.sh` accepts both `--flag value` and `--flag=value` forms:

```bash
qexec.sh --time=4 --ncpus=8 --mem=32G --account=mylab -- Rscript run.R
```

### Start An Interactive Session

```bash
qexec.sh --interactive --time 4 --ncpus 8 --mem 32G
```

Add `--nox11` if the cluster or session should not request X11 forwarding.

### Run One Command Per Array Task

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

### Pack Commands Onto One Node

To run commands from a file on a single node with no more than 5 commands active at once:

```bash
qexec.sh --file commands.txt --pack 5 --time 1 --ncpus 5
```

Pack mode submits one SLURM task and runs the command file through `command_distributor.sh` with GNU Parallel capped at the requested pack size. If `--ncpus` is not provided and qexec would otherwise request one CPU, `qexec.sh` sets `--ncpus` to the pack size.

To split the same file across 4 packed array tasks, with no more than 4 commands active in each task:

```bash
qexec.sh --file commands.txt --nodes 4 --pack 4 --time 1 --ncpus 4
```

With `--file --pack`, an explicit `--nodes K` means K packed one-node array tasks. The example submits `--array=1-4 --nodes=1`, and each array task runs its slice through `command_distributor.sh` with GNU Parallel capped at 4 commands. `--jobs` is accepted as a long-option alias for `--pack`.

### Batch A Command File Across Several Array Tasks

Use `bexec.sh` when you already have a command file and want to split it across several SLURM array tasks:

```bash
bexec.sh --file commands.txt --nodes 4 --jobs 10 --ncpus 40 --time 3
```

This creates a 4-task array. Each array task receives a slice of `commands.txt` and runs up to 10 commands at a time.

The per-task concurrency cap has two accepted long-option spellings: `--jobs` and `--pack`. In other words, `qexec.sh --file commands.txt --nodes K --pack M`, `qexec.sh --file commands.txt --nodes K --jobs M`, `bexec.sh --nodes K --jobs M`, `batch_exec.sh --nodes K --jobs M`, and `send_slurm.sh --nodes K --pack M` all express K packed array tasks with at most M commands running inside each task. The wrapper scripts also accept the other long spelling for this cap.

### Generate And Submit A Command Grid

Use `batch_exec.sh` when command lines can be generated from bracket expressions:

```bash
batch_exec.sh --time 2 --nodes 5 --ncpus 40 --mem 16G --jobs 40 -- \
    Rscript analyze.R --sub [1..100] --method [lasso,ridge]
```

This expands to 200 commands, submits a 5-task SLURM array, and runs each task's slice with GNU Parallel.

### Generate, Review, Then Submit

```bash
cmd_expand.sh Rscript run.R --sub [1..50] --roi [V1,MT,FFA] > commands.txt
cat commands.txt
bexec.sh --file commands.txt --nodes 4 --jobs 10 --ncpus 40 --time 3
```

For a single-node packed run from the same file:

```bash
qexec.sh --file commands.txt --pack 5 --ncpus 5 --time 1
```

### Pipe Commands Into SLURM

```bash
cmd_expand.sh prog [1..50] | send_slurm.sh --time 2 --ncpus 8
```

`send_slurm.sh` stores the generated commands and a runner script under `.qexec-state` by default so the submitted job can read them after the shell pipeline exits.

To split piped commands across 5 packed array tasks, with at most 3 commands running at once in each task:

```bash
cmd_expand.sh command.sh [1..10] | send_slurm.sh --nodes 5 --pack 3 --time 1
```

In pack mode, `--nodes` is the number of packed array tasks and `--pack`/`--jobs` is the per-task command concurrency cap. If `--ncpus` is not provided and `send_slurm.sh` would otherwise request one CPU, it sets `--ncpus` to the pack size.

### Monitor Jobs

```bash
rjobtop.py --job 123456
slurm_job_monitor.sh 123456 123457
```

## `cmd_expand.sh` Value Syntax

Values inside `[]` are expanded:

| Syntax | Example | Expands to |
|---|---|---|
| Comma list | `[a,b,c]` | `a`, `b`, `c` |
| Integer range | `[1..5]` or `[1:5]` | `1`, `2`, `3`, `4`, `5` |
| File lines | `[file:subjects.txt]` | One value per nonblank line |
| CSV column | `[df:subject:data.csv]` | Values from column `subject` |
| Glob | `[glob:data/*.nii]` | Matching file paths |

Modes:

- Default mode computes the Cartesian product of all expanded values.
- `--link` zips expanded values by position. Shorter lists repeat their last value.

Output options:

- `--json` emits commands as a JSON array.
- `--quote` shell-quotes expanded tokens.

## Main `qexec.sh` Options

| Option | Effect |
|---|---|
| `--time`, `-t` | Wall time. Bare numbers are hours; suffixes such as `30m` and `1hr` are accepted. |
| `--ncpus`, `-n` | CPUs per task. |
| `--nodes` | Nodes per task. With `--file --pack`, explicit `--nodes K` means K packed one-node array tasks. |
| `--mem`, `-m` | Memory request. |
| `--no-mem` | Do not pass `--mem` to SLURM. |
| `--name`, `-j` | SLURM job name. |
| `--array`, `-a` | SLURM array range, including throttles such as `1-100%10`. |
| `--file` | Command file, one nonblank command per line. |
| `--pack`, `--jobs` | With `--file`, run commands through GNU Parallel with this many concurrent commands per packed array task. |
| `--account` | SLURM account. |
| `--omp_num_threads`, `-o` | Sets `OMP_NUM_THREADS` and `MKL_NUM_THREADS`. |
| `--log-dir`, `-l` | Directory for SLURM stdout and stderr files. |
| `--after` | Submit with `sbatch --dependency=afterok:JOBID`. |
| `--wait`, `-w` | Wait for a submitted batch job and show efficiency stats. |
| `--dry-run`, `-d` | Print the computed submission command and job script without submitting. |

## Installation

### Prerequisites

- Bash 3.2+
- Python 3.7+
- SLURM commands such as `sbatch`, `salloc`, and `squeue`
- GNU Parallel for packed and batched command-file execution
- Tcl/Tk `wish` for the GUI tools

On many clusters, GNU Parallel is provided through the module system:

```bash
module load parallel
```

### Quick Install

Install the command-line tools to `~/bin`:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

Install to a different directory:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash -s -- --prefix /opt/bin
```

### Manual Setup

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
export PATH="$HOME/code/rriscripts/qexec:$PATH"
qexec.sh --help
cmd_expand.sh --help
batch_exec.sh --help
```

## Environment Variables

| Variable | Effect |
|---|---|
| `QEXEC_DEFAULT_ACCOUNT` | Default SLURM account for `qexec.sh`. |
| `QEXEC_DEFAULT_MEM` | Default memory request for `qexec.sh`, such as `4G`. |
| `QEXEC_DISABLE_MEM` | Suppress `--mem` entirely, useful for whole-node scheduling. |
| `QEXEC_LOG_DIR` | Default directory for SLURM stdout and stderr files. |
| `QEXEC_STATE_DIR` | Default state directory for `send_slurm.sh`. |
| `QEXEC_PARALLEL_BIN` | GNU Parallel executable used by `command_distributor.sh`. |
| `QEXEC_CONFIG` | Path to qexec config file. Defaults to `~/.qexecrc`. |
| `CC_CLUSTER` | Override cluster auto-detection for cluster-specific defaults. |

## Tests

Tests use [bats-core](https://github.com/bats-core/bats-core). They do not require SLURM because they use dry-runs and mocks.

```bash
git clone https://github.com/bats-core/bats-core.git /tmp/bats-core
PATH="/tmp/bats-core/bin:$PATH" bats qexec/tests/
```

## License

See the repository root for license information.
