# qexec.sh: source-audited interface and traps

Applies to **the Bash implementation**, not `qexec.hs` or GUI variants. Audited 2026-09-21. `qexec.sh` blob: `85aaa67554a1941e06bfdd4b66716779a3c11e0c`; latest modifying commit retrieved: `25fcd3b05dbb1606039a26362ef0342031afbcc9` (2026-06-19). Also read `command_distributor.sh` and `slurm_job_monitor.sh`. Source links/hashes: [Q1–Q3](sources.md#qexec-source-audit).

Inspect the installed version before relying on this audit; `git hash-object /path/qexec.sh` yields its comparable blob hash. Do not silently upgrade or patch the user's checkout. The skill supplies no replacement qexec binary.

## Choose the right interface

Use qexec for simple **CPU** submissions and trusted packed command files. Use native `sbatch` for GPUs, explicit partitions/QOS, constraints, MPI task layouts, signals, more complex dependencies, or tightly controlled arrays. There is no generic Slurm-option passthrough in this version. An unsupported flag is not made valid by putting it after the payload.

| Feature | Actual behavior |
|---|---|
| `-n N` / `--ncpus N` | `--cpus-per-task=N`, **not** number of Slurm tasks. |
| `-t 1`, `-t .5`, `-t 30m` | 60, 30, 30 minutes respectively. Bare numbers mean hours. Fractional minutes round up. `HH:MM:SS` and day syntax are rejected. |
| `-m 12G` | Memory **per node**. No memory request by default. `--no-mem` or nonempty `QEXEC_DISABLE_MEM` suppresses even an explicit `-m`. |
| `-o N` | Sets `OMP_NUM_THREADS` and `MKL_NUM_THREADS`; does not configure every BLAS library or application pool. Defaults to one. |
| `--account A` | Explicit account. Otherwise the script defaults to `rrg-brad` unless overridden; this is not proof of membership or correct charging. |
| `--preset P` | Applied at its position in argument parsing; put it **before** explicit overrides. Presets are convenience guesses, not calibrated sizes. |
| `--after ID` | Numeric ID only, `afterok` only; not `afterany`/`aftercorr`. |
| `--array 1-100%8` | Supports a single index/range and optional throttle; no comma list or stride. |
| `--file F` / `--cmd-file F` | One job per nonblank line unless packed. Comments count as commands. Cannot combine with `--array` or a positional command. |
| `--file F --pack W --nodes B` | **B independent one-node array tasks**, each running up to W commands concurrently; not one B-node allocation. Without explicit `--nodes`, B=1. |
| `--dry-run` | Prints computed resources/script without submitting. Still sources trusted config/presets and checks required helpers. Does not validate site policy. |
| `-i --nox11` | Calls `salloc` without X11. Interactive mode does **not execute the positional command**; verify/enter a compute-node shell yourself. |
| `--wait` | Runs the adjacent monitoring helper when available. It is not an assertion that the job or every array element succeeded. |

## Trillium detection is unsafe

With no `CC_CLUSTER`, a matching Trillium hostname is mapped to **Niagara**, selecting 40 CPUs and suppressing memory. With `CC_CLUSTER=trillium`, that Niagara branch does not run: CPUs remain one by default and memory may be passed. Nibi, Fir, and Rorqual have no dedicated default branches. Always specify the resource profile; never fix this by lying about `CC_CLUSTER`, which other software also uses.

For a validated standard Trillium CPU node, explicitly use `--no-mem -n 192`. Submit from the scratch run directory. Native Slurm remains preferable when the installed wrapper's behavior is uncertain.

## Safe command patterns

All paths below are examples; use frozen, absolute paths. A **single quoted shell snippet** avoids accidental expansion of runtime variables on the login node. The wrapper reconstructs its payload using `$*`; it does not preserve an arbitrary original argv exactly. A strict entry script is safer than nested shell quoting.

```bash
# Shared-node pilot; inspect, then repeat without --dry-run to submit.
qexec.sh --account "$ACCOUNT" -t 30m -n 4 -m 12G -o 1 \
  --log-dir "$RUN/logs" --dry-run 'bash /absolute/run/entry.sh'

# Trillium example only: 4 one-node bundles, at most 48 commands/node.
# Each command must really use at most 4 threads, and RAM must fit.
qexec.sh --account "$ACCOUNT" --no-mem -n 192 -o 4 -t 1hr \
  --file "$RUN/commands.txt" --pack 48 --nodes 4 \
  --log-dir "$RUN/logs" --dry-run

# Allocation only; a positional command would not be executed.
qexec.sh --account "$ACCOUNT" -i --nox11 -t 30m -n 4 -m 12G
```

The last example is for shared-node clusters, not the Trillium CPU profile. Use a tested environment/entrypoint to set other library thread limits. qexec does not enforce `workers × threads ≤ CPUs`; in packed mode auto-sizing may set CPUs to W, **not W×T**. Specify CPUs explicitly.

## Packed execution and result integrity

The distributor takes consecutive slices of approximately equal **line count**, then feeds each slice to GNU Parallel `--jobs W`. It does not load-balance across nodes, add `--halt`, or create a per-command job log. It continues other commands after failures; GNU Parallel's exit status can still fail the batch. Compound commands can mask earlier errors unless each entrypoint propagates them. Use explicit per-item validation and an attempt ledger.

Freeze command files and all referenced entrypoints: Slurm copies the temporary submission script, **not those external files**. Empty batches can occur when B is too large. `--file` cannot be combined with `--array`, so this version exposes no `%K` throttle for generated file arrays. Use bounded manifests or native Slurm for that control. Prefer grouping similar runtimes over a naive split of highly skewed workloads.

`qexec --wait` depends on executable `slurm_job_monitor.sh` beside qexec. If missing, it warns after submitting. The monitor's final exit is zero even for failed jobs; its terminal-state check reads only the first accounting state and is not array-wide validation. Always independently inspect complete accounting and expected outputs. qexec stdout also contains status text: do not treat its complete output as a numeric job ID.

## Config hygiene

`~/.qexecrc` (or `QEXEC_CONFIG`) and custom presets are **sourced shell code**. Audit them before use. Order: built-in defaults → cluster detection → config → memory-disable environment override → CLI processing. An explicit CLI `--preset` can overwrite earlier CPU/time/memory flags. `--help` exits 1 in this implementation; that alone is not an installation failure.

Potential improvements outside this bundle: current cluster profiles; explicit task/GPU/partition support; generated-array throttling; argv-safe payloads; enforced packed thread budgets; machine-readable receipts; array-wide failure-aware waiting. Implement these only within the user's requested scope.
