---
title: Reference
description: Every qexec flag, environment variable, config file, and resource preset.
---

## `qexec.sh`

```text
qexec.sh [options] -- <command>
```

| Option | Effect |
|---|---|
| `-t`, `--time` | Wall time. Bare numbers are hours; `.5`, `30m`, and `1hr` are accepted. |
| `-i`, `--interactive` | Submit an interactive job with `salloc` (default: false). |
| `-m`, `--mem` | Memory per node (default: not set). |
| `-n`, `--ncpus` | CPUs per task (default: 1). |
| `--nodes` | Nodes per task (default: 1). With `--file --pack`, an explicit `--nodes K` means K packed array tasks. |
| `-j`, `--name` | SLURM job name. |
| `-a`, `--array` | Array indices, including throttles such as `1-100%10`. |
| `--account` | SLURM account. |
| `--nox11` | Disable X11 forwarding. |
| `-o`, `--omp_num_threads` | Sets `OMP_NUM_THREADS` and `MKL_NUM_THREADS` (default: 1). |
| `--no-mem` | Do not pass `--mem` to SLURM; overrides `-m`/`--mem`. |
| `--cmd-file FILE` | Read commands from FILE and submit as an array job. |
| `--file FILE` | Alias for `--cmd-file`. |
| `--pack N` | With `--file`, run commands through GNU Parallel, N at a time per task. |
| `--jobs N` | Alias for `--pack`. |
| `--preset NAME` | Load a resource preset. See [below](#resource-presets). |
| `--after JOBID` | Submit with `sbatch --dependency=afterok:JOBID`. |
| `-w`, `--wait` | Submit, then block until *that* job finishes and show its efficiency stats. Not allowed with `--interactive`. |
| `-l`, `--log-dir` | Directory for SLURM stdout/stderr (default: current dir or `$QEXEC_LOG_DIR`). |
| `-d`, `--dry-run` | Print the computed SLURM command and job script, then exit. |

Both `--flag value` and `--flag=value` forms are accepted.

### Resource presets

`--preset NAME` sets time, CPUs, and memory together. Flags given after the
preset override it.

| Preset | Time (h) | CPUs | Memory |
|---|---|---|---|
| `fmriprep` | 12 | 8 | 32G |
| `freesurfer` | 24 | 1 | 8G |
| `mriqc` | 4 | 4 | 16G |
| `light` | 1 | 1 | 4G |
| `heavy` | 24 | 16 | 64G |

Define your own by creating a file at `~/.qexec/presets/<name>` that sets
`TIME`, `NCPUS`, and `MEM`. A user preset with the same name takes precedence
over a built-in one:

```bash
# ~/.qexec/presets/mystudy
TIME=6
NCPUS=12
MEM=48G
```

## `cmd_expand.sh`

```text
cmd_expand.sh [--link] [--quote] [--json] <base_command> [arguments...]
```

| Option | Effect |
|---|---|
| `--link` | Link arguments by position, repeating the last value of shorter lists. |
| `--quote` | Shell-quote tokens before joining. |
| `--json` | Emit commands as a JSON array of strings. |

Full value syntax is on the [cmd_expand page](../cmd-expand/).

## `bexec.sh`

```text
bexec.sh -f commands.txt [options]
```

| Option | Effect | Default |
|---|---|---|
| `-f`, `--file FILE` | Commands file to submit | *(required)* |
| `-n`, `--nodes N` | Number of array tasks / batches | 1 |
| `--time HOURS` | Hours per array task | 1 |
| `--ncpus N` | CPUs per array task | 40 |
| `--mem MEM` | Memory per task (e.g. `12G`) | qexec defaults |
| `--no-mem` | Pass through qexec's `--no-mem` switch | |
| `-j`, `--jobs`, `--pack N` | GNU Parallel jobs per batch | 40 |
| `-N`, `--name NAME` | SLURM job name | |
| `--account NAME` | SLURM account | |
| `-l`, `--log-dir DIR` | SLURM log directory | |
| `-d`, `--dry-run` | Show the computed qexec call and exit | |

## `batch_exec.sh`

```text
batch_exec.sh [options] -- <base_command> [args...]
```

Arguments may include `cmd_expand`-style bracketed values.

| Option | Effect | Default |
|---|---|---|
| `-t`, `--time HOURS` | Walltime per array task | 1 |
| `-n`, `--nodes N` | Number of array tasks / batches | 1 |
| `--ncpus N` | CPUs per array task | 40 |
| `-m`, `--mem MEM` | Memory per task (e.g. `6G`) | qexec defaults |
| `-j`, `--jobs`, `--pack N` | GNU Parallel jobs per task | 40 |
| `-N`, `--name NAME` | SLURM job name | |
| `--account NAME` | SLURM account | qexec default |
| `-l`, `--log-dir DIR` | SLURM log directory | |
| `--link` | Link mode for `cmd_expand` (zip by position) | |
| `--quote` | Ask `cmd_expand` to shell-quote expanded tokens | |
| `-d`, `--dry-run` | Show computed commands / qexec call and exit | |
| `-h`, `--help` | Show help | |

## `send_slurm.sh`

```text
cmd_expand.sh ... | send_slurm.sh [options]
```

| Option | Effect | Default |
|---|---|---|
| `-t`, `--time HOURS` | Hours per task | 1 |
| `-m`, `--mem MEM` | Memory per task | |
| `-n`, `--ncpus N` | CPUs per task | 1 |
| `--nodes N` | Nodes per array task; with `--pack`, the number of batches | |
| `--pack N`, `--jobs N` | Split stdin across `--nodes` tasks, N commands concurrently per task | |
| `-j`, `--name NAME` | SLURM job name | `array_job` |
| `-a`, `--array SPEC` | Override array indices | `1-N` for N input commands |
| `--account NAME` | SLURM account | |
| `--nox11` | Disable X11 forwarding | |
| `-o`, `--omp_num_threads N` | OpenMP/MKL threads | 1 |
| `-l`, `--log-dir DIR` | SLURM log directory | |
| `--state-dir DIR` | Directory for persisted command/runner files | `.qexec-state` |
| `-d`, `--dry-run` | Show the computed qexec call and exit | |
| `-h`, `--help` | Show help | |

`--array` cannot be combined with `--pack`/`--jobs`; use `--nodes` to set the
number of packed batches.

## `command_distributor.sh`

```text
command_distributor.sh <commands_file_path> <number_of_batches> [jobs_per_batch]
```

Runs inside a SLURM array task. It selects the slice of the command file
belonging to `$SLURM_ARRAY_TASK_ID` and runs it with `parallel --jobs
<jobs_per_batch>`. You normally do not call this directly — the submitters build
the call for you.

## `slurm_job_monitor.sh`

```text
slurm_job_monitor.sh [options] [jobid ...]
```

| Option | Effect | Default |
|---|---|---|
| `-i`, `--interval SECONDS` | Polling interval | 60 |
| `-e`, `--email ADDRESS` | Email address for the completion summary | |
| `-n`, `--notify` | Desktop notification via `notify-send` | |
| `-h`, `--help` | Show help | |

With no job IDs, monitors the current user's jobs from the last 30 minutes.

## `rjobtop.py`

See [Monitoring jobs](../monitoring/#options) for the full option table.

## Environment variables

| Variable | Effect |
|---|---|
| `QEXEC_DEFAULT_ACCOUNT` | Default SLURM account for `qexec.sh`. |
| `QEXEC_DEFAULT_MEM` | Default memory request, such as `4G`. |
| `QEXEC_DISABLE_MEM` | Set to any non-empty value to suppress `--mem` entirely — useful for whole-node scheduling. |
| `QEXEC_LOG_DIR` | Default directory for SLURM stdout and stderr files. |
| `QEXEC_STATE_DIR` | Default state directory for `send_slurm.sh`. |
| `QEXEC_PARALLEL_BIN` | GNU Parallel executable used by `command_distributor.sh`. |
| `QEXEC_CONFIG` | Path to the qexec config file (default: `~/.qexecrc`). |
| `CC_CLUSTER` | Override cluster auto-detection (`niagara`, `narval`, …). |

## Config file

`qexec.sh` sources `~/.qexecrc` (or `$QEXEC_CONFIG`) before parsing flags, so it
sets defaults that command-line flags then override. A missing file is silently
ignored. Set any of the script's default variables:

```bash
# ~/.qexecrc
# rrg-mypi is a placeholder — Alliance allocations are named after the PI's
# username, e.g. rrg-jsmith or def-jsmith.
ACCOUNT=rrg-mypi
NCPUS=4
MEM=16G
LOG_DIR=$HOME/slurm-logs
```

:::note
The built-in default account is `rrg-brad`. Unless that happens to be your
allocation, set `ACCOUNT` in `~/.qexecrc` or `QEXEC_DEFAULT_ACCOUNT` in your
environment, or pass `--account` every time.
:::

## Cluster detection and precedence

`qexec.sh` detects the cluster from `$CC_CLUSTER`, falling back to a hostname
match:

| Hostname contains | Detected as |
|---|---|
| `niagara`, `nia`, `trillium`, `trl` | `niagara` |
| `narval`, `nar` | `narval` |
| `beluga`, `blg` | `beluga` |
| `cedar`, `cdr` | `cedar` |
| `graham`, `gra` | `graham` |

Only `niagara` currently changes defaults: it sets whole-node scheduling by
suppressing `--mem` and defaulting `ncpus` to 40. Trillium hostnames map to the
same profile.

Settings are applied in this order, each layer overriding the one before:

1. Built-in defaults
2. Cluster detection
3. `~/.qexecrc` (or `$QEXEC_CONFIG`)
4. `--preset NAME`
5. Command-line flags

So a `~/.qexecrc` can override a cluster default, and an explicit flag always
wins.
