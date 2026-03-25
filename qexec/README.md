# qexec — SLURM Job Submission Toolkit

A suite of shell scripts for submitting and managing jobs on SLURM clusters. Designed for researchers who need to run many parameterized commands (e.g., neuroimaging pipelines, simulations, R batch jobs) across cluster nodes with minimal boilerplate.

## Scripts at a Glance

### Core Pipeline

| Script | What it does |
|---|---|
| **cmd_expand.sh** | Expands a parameterized command into a list of concrete commands via Cartesian product or positional zip. Pure text transformation — no SLURM dependency. |
| **qexec.sh** | Submits a single job to SLURM: `salloc` for interactive sessions, `sbatch` for batch jobs. Handles time, memory, CPUs, array indices, logging, and OpenMP threading. The parser is portable across BSD/macOS/Linux shells and supports both `--flag value` and `--flag=value` forms. |
| **command_distributor.sh** | Runs inside a SLURM array task. Splits a command file into batches by `SLURM_ARRAY_TASK_ID` and executes its share via GNU Parallel. |
| **batch_exec.sh** | Orchestrator that ties the above together: expands commands with `cmd_expand.sh`, then submits them as a SLURM array job that uses `command_distributor.sh` to distribute work across nodes. |

### Additional Tools

| Script | What it does |
|---|---|
| **bexec.sh** | Older batch executor. Takes a pre-written command file (`-f commands.txt`) and submits it as an array job via `qexec.sh` + `command_distributor.sh`. |
| **send_slurm.sh** | Pipe-friendly interface: reads commands from stdin, persists the generated command list/runner under `.qexec-state` (or `--state-dir`), and submits them as a SLURM array job. Useful with `cmd_expand.sh \| send_slurm.sh`. |
| **rjobtop.py** | Live monitoring of a running SLURM job's CPU and memory utilization. Shows per-process breakdown, fork rate, and ASCII sparklines. Useful for R/future/callr workloads. |
| **slurm_job_monitor.sh** | Polls SLURM jobs until completion, then reports efficiency via `seff`. Optional email or desktop notifications. |

### GUIs

Both GUIs include input validation, tooltips on every field, a scrollable output pane for viewing results, and confirmation dialogs before real submissions. They require Tcl/Tk (`wish`).

| Script | What it does |
|---|---|
| **qexec_gui.tcl** | GUI for `qexec.sh` — fill in fields, submit batch or interactive jobs, and see dry-run output in the built-in output pane. |
| **batch_exec_gui.tcl** | GUI for `batch_exec.sh` — configure expansions, use the "Preview Expansion" button to see expanded commands before submitting, and build bracket expressions with the argument helper. |
| **batch_exec_gui** | Convenience launcher for `batch_exec_gui.tcl`. |

### Haskell Implementations

`qexec.hs`, `cmd_expand.hs`, `bexec.hs`, and `command_distributor.hs` are Haskell implementations of the corresponding shell scripts. They are functionally equivalent and can be compiled as standalone binaries if preferred.

## How the Scripts Work Together

The typical workflow for running many parameterized jobs:

```
cmd_expand.sh                    batch_exec.sh (orchestrator)
  Expands parameters      --->     Calls cmd_expand.sh
  into N commands                  Writes commands to a file
                                   Submits via qexec.sh
                                        |
                                        v
                                   qexec.sh
                                     Submits sbatch --array=1-K
                                        |
                                        v
                              command_distributor.sh
                                (runs on each node)
                                Reads its share of commands
                                Executes via GNU Parallel
```

### Example: Run an R script over 100 subjects on 5 nodes

```bash
# batch_exec.sh does the expansion + submission in one step:
batch_exec.sh -t 2 -n 5 --ncpus 40 -m 16G -- \
    Rscript analyze.R --sub [1..100] --method [lasso,ridge]

# This expands to 200 commands (100 subjects x 2 methods),
# submits a 5-element array job, each node runs ~40 commands
# in parallel via GNU Parallel.
```

### Example: Expand commands, review, then submit separately

```bash
# Step 1: Generate the command list
cmd_expand.sh Rscript run.R --sub [1..50] --roi [V1,MT,FFA] > commands.txt

# Step 2: Review
cat commands.txt   # 150 commands (50 x 3)

# Step 3: Submit with the older bexec interface
bexec.sh -f commands.txt -n 4 --ncpus 40 --time 3

# Or pipe directly:
cmd_expand.sh prog [1..50] | send_slurm.sh -t 2 -n 4 --ncpus 8
```

### Example: Interactive session

```bash
qexec.sh -i -t 4 -n 8 -m 32G
# Allocates an interactive session with 8 CPUs, 32G RAM, 4 hours
```

### Example: Equals-style long options

```bash
qexec.sh --dry-run --time=4 --ncpus=8 --account=mylab --array=1-10 -- myscript.sh
```

This is equivalent to:

```bash
qexec.sh --dry-run --time 4 --ncpus 8 --account mylab --array 1-10 -- myscript.sh
```

### Example: Monitor a running job

```bash
# On the compute node:
rjobtop.py --job 123456

# From the login node, poll until done:
slurm_job_monitor.sh 123456 123457
```

## cmd_expand.sh — Value Syntax

Values inside `[]` are expanded:

| Syntax | Example | Expands to |
|---|---|---|
| Comma list | `[a,b,c]` | `a`, `b`, `c` |
| Integer range | `[1..5]` or `[1:5]` | `1`, `2`, `3`, `4`, `5` |
| File lines | `[file:subjects.txt]` | One value per non-blank line |
| CSV column | `[df:subject:data.csv]` | Values from column `subject` |
| Glob | `[glob:data/*.nii]` | Matching file paths |

**Modes:**
- Default: Cartesian product of all expanded values.
- `--link`: Zip arguments by position (shorter lists repeat their last value).

**Output:**
- `--json`: Emit commands as a JSON array.
- `--quote`: Shell-quote all tokens.

## Installation

### Prerequisites

- **bash** 4.0+ (for arrays and `mapfile`)
- **Python 3.7+** (used by `cmd_expand.sh` internally, and by `rjobtop.py`)
- **GNU Parallel** (used by `command_distributor.sh` to run commands concurrently)
- **SLURM** (the cluster must run SLURM for job submission)
- **Tcl/Tk** (`wish`) — only needed for the GUI tools

On most HPC clusters, Python 3, bash, and SLURM are already available. GNU Parallel may need to be loaded:

```bash
module load parallel    # cluster-specific; check 'module avail'
```

### Setup

1. **Clone or copy the scripts:**

   ```bash
   git clone https://github.com/bbuchsbaum/rriscripts.git
   ```

2. **Add to your PATH** (in `~/.bashrc` or `~/.bash_profile`):

   ```bash
   export PATH="$HOME/code/rriscripts/qexec:$PATH"
   ```

   Or symlink into a directory already on your PATH:

   ```bash
   mkdir -p ~/bin
   for f in qexec.sh cmd_expand.sh batch_exec.sh command_distributor.sh \
            bexec.sh send_slurm.sh rjobtop.py slurm_job_monitor.sh; do
       ln -sf "$HOME/code/rriscripts/qexec/$f" ~/bin/
   done
   ```

3. **Make scripts executable** (if not already):

   ```bash
   chmod +x ~/code/rriscripts/qexec/*.sh ~/code/rriscripts/qexec/*.py
   ```

4. **Verify:**

   ```bash
   qexec.sh --help
   cmd_expand.sh --help
   batch_exec.sh --help
   ```

### Optional: Compile Haskell Versions

If you prefer compiled binaries (no Python/bash dependency for the core tools):

```bash
# Requires GHC
ghc -O2 -o cmd_expand qexec/cmd_expand.hs
ghc -O2 -o qexec qexec/qexec.hs
```

### Environment Variables

| Variable | Effect |
|---|---|
| `QEXEC_DEFAULT_MEM` | Default memory request for `qexec.sh` (e.g., `4G`). |
| `QEXEC_DISABLE_MEM` | Set to any value to suppress `--mem` entirely (useful for whole-node scheduling). |
| `QEXEC_LOG_DIR` | Default directory for SLURM log files. |

## Running Tests

Tests use [bats-core](https://github.com/bats-core/bats-core):

```bash
# Install bats (one-time)
git clone https://github.com/bats-core/bats-core.git /tmp/bats-core

# Run all tests (no SLURM required — uses --dry-run and mocks)
PATH="/tmp/bats-core/bin:$PATH" bats qexec/tests/
```

## License

See the repository root for license information.
