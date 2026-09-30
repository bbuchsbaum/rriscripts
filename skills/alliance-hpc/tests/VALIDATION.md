# Validation report

Date: 2026-09-21. **45 tests passed** in one complete local run on macOS with
Python 3.14.7, Bash 3.2.57, and GNU `timeout`. The imported bundle's original
35 tests also passed before changes. No live Alliance connection or Slurm job
was used.

## Verified locally

- Bash syntax for both helpers and the CPU template, plus every embedded Bash recipe.
- Minimal common skill frontmatter, all five cluster names, core under 1,000 words, and existing relative Markdown links.
- Array dispatch: 1-based IDs, exact argument boundaries, shell metacharacters treated as data, no trailing-newline requirement, rejection of invalid indices/blank rows/CRLF/missing inputs, and payload failure propagation.
- CPU launcher: one node/one task, allocation and CPU-request guards, trusted environment loading, numerical-library thread caps, rejection of excess threads, exact argv preservation, and environment/application failure propagation.
- Probe under mock commands: read-only Slurm call shapes, selected-QOS querying, bounded display, filtered configuration, secret values excluded from environment reporting, invalid-input rejection, and explicit incomplete-evidence status.
- Probe regressions: truncated evidence returns status 2; a timed-out query returns incomplete status while subsequent diagnostics still run; invalid QOS is rejected before querying.
- Documented installation commands: personal links share one canonical directory; repository links resolve relatively; existing files, directories, and dangling symlinks prevent installation without overwriting anything.
- Documented submission sequence under mocks: failed preflight or intent recording cannot submit; successful submission records a receipt once; failed or malformed responses require reconciliation without automatic retry.
- ShellCheck 0.11.0 for helpers and template; the explicitly trusted runtime environment file is outside static analysis and has its own `bash -n` preflight.
- Separate local qexec dry-runs confirmed the two Trillium autodetection paths and explicit packed-array resources against the recorded source hashes. These were not live submissions or part of the 45 bundle tests.

## Not established by these tests

Real scheduler acceptance, actual account/partition/QOS entitlements, current queue times or limits, compute-node mounts or egress, module compatibility, GPU/MIG/APU availability, application correctness/scaling, quotas, purge rules, or approved automation access. qexec was source-audited, not submitted to a cluster or replaced by this package. The GNU Parallel recipe must be checked against the installed version.

The original authoring report noted harness timeouts and split-suite execution.
The repository review ran the complete suite successfully without increasing
the existing 25-second subprocess timeout. The probe's per-query time bound is
unchanged.

## Reproduce

```bash
python3 tests/test_skill.py
```

For a targeted rerun, select the relevant test classes:

```bash
python3 tests/test_skill.py ProbeTests SubmissionTests InstallationTests
```

Tests use temporary local files and mocked Slurm tools; no network access or
external Python packages are required. The test harness requires Python 3.9+.
GNU `timeout` is required on `PATH` for probe tests, as it is for the Linux-targeted
probe itself. Tests for array/launcher logic and static content can also be run
separately. From this skill directory, run shell lint with:

```bash
shellcheck scripts/*.sh templates/*.sbatch
```
