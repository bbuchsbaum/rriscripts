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
skip_bids_validation = true
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
```

## Config file precedence

Later files override earlier ones:

1. `/etc/fmriprep/config.ini` (system-wide)
2. `~/.config/fmriprep/config.ini` (user — infrastructure)
3. `~/.fmriprep.ini` (legacy user override, if present)
4. `./fmriprep.ini` (project — dataset-specific)
5. `--config path/to/file.ini` (explicit override)

## `[defaults]` keys

The table reports behavior when a key is omitted. Generated starter configs
intentionally set some lab-friendly defaults, including
`skip_bids_validation = true` and `fs_reconall = true` — edit those for your
study.

| Key | Type | Default if omitted | Description |
|---|---|---|---|
| `bids` | path | *(required)* | BIDS dataset root directory |
| `out` | path | *(required)* | Output directory (usually `<bids>/derivatives/fmriprep`) |
| `work` | path | *(required)* | Working directory (use fast scratch storage) |
| `runtime` | string | `auto` | Container runtime: `singularity`, `docker`, `fmriprep-docker`, or `auto` |
| `container` | path/string | `auto` | Path to `.sif` file, Docker `image:tag`, or `auto` to search `$FMRIPREP_SIF_DIR` |
| `fs_license` | path | `$FS_LICENSE` | Path to FreeSurfer `license.txt` |
| `templateflow_home` | path | `$TEMPLATEFLOW_HOME` | Path to pre-populated TemplateFlow cache |
| `nprocs` | int | auto-detect | `--nprocs` passed to fMRIPrep |
| `omp_threads` | int | `min(8, nprocs)` | `--omp-nthreads` passed to fMRIPrep |
| `mem_mb` | int/string | ~90% of available | Memory limit in MB (also accepts `32G`, `2T`) |
| `output_spaces` | string | — | Space-separated list, e.g. `MNI152NLin2009cAsym:res-2 T1w fsnative` |
| `skip_bids_validation` | bool | `false` | Pass `--skip-bids-validation` |
| `fs_reconall` | bool | `false` | Run FreeSurfer `recon-all`; generated project configs set this to `true` |
| `use_syn_sdc` | bool | `false` | Enable SyN-based fieldmap-less distortion correction |
| `cifti_output` | bool | `false` | Generate CIFTI outputs |
| `use_aroma` | bool | `false` | **Deprecated** — removed in fMRIPrep ≥ 23.1.0 |
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
| `cpus_per_task` | int | from `nprocs` | Override `--cpus-per-task` in the SLURM header |
| `mem` | string | from `mem_mb` | SLURM `--mem` value (e.g. `32G`). Use `none` to omit |
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
