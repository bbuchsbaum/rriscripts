---
title: Monitoring jobs
description: Watch live CPU and memory use with rjobtop.py, and poll jobs to completion with slurm_job_monitor.sh.
---

Two tools, two questions. `rjobtop.py` answers *what is this running job doing
right now?* `slurm_job_monitor.sh` answers *tell me when these jobs are done and
whether they used their allocation well.*

## `rjobtop.py` — live CPU and memory

```bash
rjobtop.py --job 123456
```

A curses UI showing live per-process CPU and memory for the job's processes.

:::note
`rjobtop.py` reads `/proc`, so it only runs on Linux compute nodes. On macOS it
exits with `rjobtop requires Linux with /proc filesystem`.
:::

### Common invocations

```bash
rjobtop.py --job 123456 --once            # one snapshot, no curses UI
rjobtop.py --job 123456 --json            # machine-readable snapshot (implies --once)
rjobtop.py --job 123456 --step batch      # restrict to one job step
rjobtop.py --pid 4242                     # monitor a PID subtree instead
rjobtop.py --job 123456 --multi           # one snapshot per allocated node, via srun
rjobtop.py --job 123456 --interval 2      # refresh every 2 seconds
```

### Options

| Option | Effect |
|---|---|
| `--job` | SLURM JobID to monitor |
| `--step` | Optional StepID (e.g. `0` or `batch`); otherwise all steps |
| `--pid` | Monitor a PID subtree instead of a SLURM job |
| `--pattern` | Process-name pattern to highlight (defaults to an R-oriented pattern) |
| `--interval` | Refresh interval in seconds |
| `--once` | Print a single snapshot and exit, no curses UI |
| `--json` | Emit the snapshot as JSON (implies `--once`) |
| `--multi` | Collect a snapshot from each allocated node via `srun` (requires `--job`, implies `--once`) |
| `--nodes` | Comma- or space-separated node list to sample (implies `--multi`) |
| `--no-alerts` | Disable alert threshold warnings |
| `--cpu-underutil-threshold` | CPU underutilization alert threshold |
| `--mem-high-threshold` | High-memory alert threshold |
| `--fork-rate-threshold` | Fork-rate alert threshold |

The alert thresholds are the useful part for HPC work: a job sitting at 12% CPU
across 40 requested cores is the single most common way to waste an allocation,
and `rjobtop.py` flags it while there is still time to cancel.

## `slurm_job_monitor.sh` — poll to completion

```bash
slurm_job_monitor.sh 123456 123457
```

Polls the given jobs, periodically printing runtime, CPU, and memory use. When
they finish it summarizes efficiency with `seff` if that command is available.

With no job IDs, it monitors jobs submitted by the current user in the last 30
minutes:

```bash
slurm_job_monitor.sh
```

### Options

| Option | Effect |
|---|---|
| `-i`, `--interval SECONDS` | Polling interval (default: 60) |
| `-e`, `--email ADDRESS` | Email the completion summary |
| `-n`, `--notify` | Send a desktop notification with `notify-send` |
| `-h`, `--help` | Show help |

### Waiting inline instead

`qexec.sh --wait` submits and then hands off to `slurm_job_monitor.sh` for you:

```bash
qexec.sh --wait --time 1 --ncpus 4 -- Rscript run.R
```

This is convenient for a single job you intend to sit and watch. For anything
longer, submit without `--wait` and monitor separately — otherwise the wait dies
with your login session.
