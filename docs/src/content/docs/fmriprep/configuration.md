---
title: Configuration reference
description: Every [defaults] and [slurm] INI key, plus the environment variables the launcher reads.
---

INI is the only supported config format. A well-populated project config lets
`slurm-array` run without long flag lists.

:::note[Paths below are examples]
`rrg-mypi` and `myuser` are placeholders. Allocation accounts on Digital
Research Alliance of Canada clusters are named after the PI's username —
`rrg-<pi-username>` for a RAC allocation, `def-<pi-username>` for a default one
— so real paths look more like `/project/rrg-jsmith/…`. Substitute your own
account and username throughout; `sacctmgr show associations user=$USER
format=account%30` lists the allocations you belong to.
:::

```ini
[defaults]
# rrg-mypi and myuser are placeholders — use your own allocation and username.
bids = /project/rrg-mypi/shared/my_study
out = /project/rrg-mypi/shared/my_study/derivatives/fmriprep
work = /scratch/myuser/fmriprep_work
runtime = singularity
container = /project/rrg-mypi/shared/bin/fmriprep_latest.sif
fs_license = /project/rrg-mypi/shared/bin/license.txt
templateflow_home = /project/rrg-mypi/shared/opt/templateflow

nprocs = 8
omp_threads = 4
mem_mb = 32000
output_spaces = MNI152NLin2009cAsym:res-2 T1w
fs_reconall = true
use_syn_sdc = true

[slurm]
partition = compute
time = 24:00:00
account = rrg-mypi
job_name = fmriprep_mystudy
script_outdir = /scratch/myuser/my_study_fmriprep_job
log_dir = /scratch/myuser/my_study_fmriprep_job/logs
subjects_per_job = 4
parallel_subjects = 2
array_concurrency = 3
```

## Config file precedence

Later files override earlier ones:

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` (user — infrastructure)
3. `~/.fmriprep.ini` (legacy user override, if present)
4. `./fmriprep.ini` (project — dataset-specific)
5. `--config path/to/file.ini` (explicit override)

## `[defaults]` keys

The table reports behavior when a key is omitted. Every path (CLI, both
`wizard` modes, the TUI and the GUI) uses the same defaults for the two keys
that change results most: `fs_reconall = true` and
`skip_bids_validation = false`. These match fMRIPrep's own defaults.

Because recon-all, BIDS validation and the container version change the
results rather than just the runtime, `print-cmd`, `slurm-array` and both
wizard modes report all three on stderr before writing anything. Boolean keys
can be overridden per run in either direction, e.g. `--no-fs-reconall` or
`--skip-bids-validation`.

:::caution[Changed default]
Before this release, `fs_reconall` defaulted to `false` on the command line
(the launcher added `--fs-no-reconall`), and generated configs and the
interactive paths skipped BIDS validation. A config that sets either key keeps
its value. A config that omits `fs_reconall` now runs recon-all, which takes
several hours per subject and changes the outputs. To keep the old behavior,
set `fs_reconall = false`.
:::

| Key | Type | Default if omitted | Description |
|---|---|---|---|
| `bids` | path | *(required)* | BIDS dataset root directory |
| `out` | path | *(required)* | Output directory (usually `<bids>/derivatives/fmriprep`) |
| `work` | path | *(required)* | Working directory (use fast scratch storage). Acts as a base: a relative `--work` is taken as a subdirectory of it — see [A base work directory](../workflow/#a-base-work-directory-with-per-run-subdirectories) |
| `runtime` | string | `auto` | Container runtime: `singularity`, `docker`, `fmriprep-docker`, or `auto` |
| `container` | path/string | `auto` | Path to `.sif` file, Docker `image:tag`, or `auto` to search `$FMRIPREP_SIF_DIR`. A directory or `auto` picks the most recently modified image and names it, and the ones it passed over, on stderr; give a file path to pin the fMRIPrep version |
| `fs_license` | path | `$FS_LICENSE` | Path to FreeSurfer `license.txt` |
| `templateflow_home` | path | `$TEMPLATEFLOW_HOME` | Path to pre-populated TemplateFlow cache |
| `nprocs` | int | auto-detect | Per-subject `--nprocs` passed unchanged to each independent fMRIPrep process |
| `omp_threads` | int | `min(8, nprocs)` | `--omp-nthreads` passed to fMRIPrep |
| `mem_mb` | int/string | ~90% of available | Per-subject fMRIPrep memory limit in MB (also accepts `32G`, `2T`) |
| `output_spaces` | string | — | Space-separated list, e.g. `MNI152NLin2009cAsym:res-2 T1w fsnative` |
| `skip_bids_validation` | bool | `false` | Pass `--skip-bids-validation`, skipping the BIDS validator (CLI: `--skip-bids-validation` / `--no-skip-bids-validation`) |
| `fs_reconall` | bool | `true` | Run FreeSurfer `recon-all`; `false` adds `--fs-no-reconall` (CLI: `--fs-reconall` / `--no-fs-reconall`) |
| `use_syn_sdc` | bool | `false` | Enable SyN-based fieldmap-less distortion correction |
| `cifti_output` | bool | `false` | Generate CIFTI outputs |
| `use_aroma` | bool | `false` | **Deprecated.** ICA-AROMA was removed in fMRIPrep ≥ 23.1.0; the launcher errors if this is set. Delete it from configs carried over from older studies |
| `extra` | string | — | Extra flags appended verbatim to the fMRIPrep command |
| `subjects` | string | — | `all` or a space-separated list (e.g. `sub-01 sub-02`) |

## `[slurm]` keys

| Key | Type | Default if omitted | Description |
|---|---|---|---|
| `partition` | string | `compute` | SLURM partition name |
| `time` | string | `24:00:00` | Walltime limit (`HH:MM:SS`) |
| `account` | string | — | SLURM account/allocation. Alliance clusters name these after the PI's username, e.g. `def-jsmith` or `rrg-jsmith` |
| `job_name` | string | `fmriprep` | SLURM job name |
| `log_dir` | path | `<script_outdir>/logs` | Directory for SLURM stdout/stderr logs |
| `script_outdir` | path | `$SCRATCH/<bids-basename>_fmriprep_job` if `$SCRATCH` is set, else `./fmriprep_job` | Where to write the generated sbatch and bundle. Must be writable from compute nodes — `status/` is mutated at runtime. |
| `subjects_per_job` | int | `1` | Subjects assigned to each array task (`B`); controls the number of lines in `subjects.txt` |
| `parallel_subjects` | int | `subjects_per_job` | Maximum independent fMRIPrep processes active inside each task (`M`); must be no greater than `subjects_per_job` |
| `array_concurrency` | int | unlimited by launcher | Maximum active array tasks (`C`); adds `%C` to the Slurm array range but does not guarantee simultaneous starts |
| `exclusive` | bool | `false` | Request an unshared physical node for each active array task; site policy may override it |
| `cpus_per_task` | int | `nprocs * parallel_subjects` | Total CPU allocation for each Slurm array task; an explicit value is not scaled again |
| `mem` | string | `mem_mb * parallel_subjects` | Total Slurm memory allocation for each task (e.g. `32G`); an explicit value is not scaled again. Use `none` to omit |
| `no_mem` | bool | `false` | Omit `--mem` entirely (for whole-node clusters like Trillium) |
| `email` | string | — | Email address for SLURM notifications |
| `mail_type` | string | — | SLURM mail events (e.g. `END,FAIL`) |
| `module_singularity` | bool | `false` | Insert `module load singularity` in the generated script |

## Syntax notes

Boolean values are case-insensitive (`true`/`True`/`TRUE`). Use `#` for inline
comments.

## Environment variables

| Variable | Effect |
|---|---|
| `FMRIPREP_SIF_DIR` | Directory to search for `.sif`/`.simg` images (used when `container = auto`). |
| `FS_LICENSE` | Path to the FreeSurfer license file (fallback if not in config). |
| `TEMPLATEFLOW_HOME` | Path to the TemplateFlow cache directory (fallback if not in config). |
| `SCRATCH` | If set, determines the default `script_outdir`. |

Config keys take precedence over the environment fallbacks, and they are easier
to share in project run notes.

For a fully isolated invocation that reads exactly one configuration file, use
the global options before the subcommand:

```bash
fmriprep_launcher.py --no-default-config --config /path/to/fmriprep.ini slurm-array
```

This skips the system, user, legacy user, and local configuration search paths.
