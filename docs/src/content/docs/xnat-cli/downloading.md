---
title: Downloading data
description: Pull down scan files, whole experiments, whole subjects, or an entire project.
---

Four commands, differing in how much they pull at once:

| Command | Grain | Requires |
|---|---|---|
| `download_files` | Files within a scan | project, subject, experiment |
| `download_experiment` | One experiment archive | experiment |
| `download_subject` | Everything for one subject | project, subject |
| `download_all` | Every subject in a project | project |

All four accept `--format` (`zip` or `tar.gz`, default `zip`), `--dest_dir`
(default: current directory), and `--progress` / `--no_progress`.

## Scan-level files

```bash
Rscript xnat_cli.R download_files \
    --project_id MYPROJECT \
    --subject_id sub-01 \
    --experiment_id MYPROJECT_E00123 \
    --scan_id 5 \
    --dest_dir ./raw
```

| Option | Effect | Default |
|---|---|---|
| `--project_id PROJECT` | Project ID | *(required)* |
| `--subject_id SUBJECT` | Subject ID | *(required)* |
| `--experiment_id EXPERIMENT` | Experiment ID | *(required)* |
| `--scan_id SCAN_ID` | Scan to fetch | `ALL` |
| `--resource RESOURCE` | Resource name (e.g. `DICOM`, `NIFTI`) | all |
| `--format zip\|tar.gz` | Archive format | `zip` |
| `--dest_dir DIR` | Destination directory | current directory |
| `--dest_file FILE` | Explicit destination file path | derived |
| `--progress` / `--no_progress` | Progress output | on |

`--scan_id` defaults to `ALL`, so omitting it downloads every scan in the
experiment. Use `--resource` to take only one representation — usually the
difference between pulling NIfTIs and pulling the full DICOM set.

## One experiment

```bash
Rscript xnat_cli.R download_experiment \
    --experiment_id MYPROJECT_E00123 \
    --dest_dir ./sessions \
    --extract
```

| Option | Effect | Default |
|---|---|---|
| `--experiment_id EXPERIMENT` | Experiment ID | *(required)* |
| `--scan_id SCAN_ID` | Restrict to one scan | `ALL` |
| `--format zip\|tar.gz` | Archive format | `zip` |
| `--dest_dir DIR` | Destination directory | current directory |
| `--dest_file FILE` | Explicit destination file path | derived |
| `--extract` | Extract the archive after download | off |
| `--progress` / `--no_progress` | Progress output | on |
| `--strict` / `--no_strict` | Strict error handling | strict |

This is the only download command that does not need a project ID — the
experiment ID is globally unique.

## One subject

```bash
Rscript xnat_cli.R download_subject \
    --project_id MYPROJECT \
    --subject_id sub-01 \
    --dest_dir ./subjects
```

| Option | Effect | Default |
|---|---|---|
| `--project_id PROJECT` | Project ID | *(required)* |
| `--subject_id SUBJECT` | Subject ID | *(required)* |
| `--format zip\|tar.gz` | Archive format | `zip` |
| `--dest_dir DIR` | Destination directory | current directory |
| `--progress` / `--no_progress` | Progress output | on |

## A whole project

```bash
Rscript xnat_cli.R download_all \
    --project_id MYPROJECT \
    --dest_dir ./project_data
```

| Option | Effect | Default |
|---|---|---|
| `--project_id PROJECT` | Project ID | *(required)* |
| `--format zip\|tar.gz` | Archive format | `zip` |
| `--dest_dir DIR` | Destination directory | current directory |
| `--progress` / `--no_progress` | Progress output | on |

`download_all` is implemented in this CLI by calling `list_subjects()` and then
`download_subject()` for each one — `xnatR` no longer exports
`download_all_subjects()`. It prints `Downloading subject <id> ...` as it goes.

:::caution
Because it is a loop rather than a single server-side archive request, a failure
partway through leaves you with some subjects downloaded and some not, and there
is no resume flag. For large projects, prefer driving `download_subject` from
your own loop over a subject list so you can restart where it stopped:

```bash
Rscript xnat_cli.R list_subjects --project_id MYPROJECT --columns ID \
  | awk 'NR>1 {print $2}' > subjects.txt

while read -r s; do
  [ -e "./project_data/${s}.zip" ] && continue
  Rscript xnat_cli.R download_subject --project_id MYPROJECT \
      --subject_id "$s" --dest_dir ./project_data
done < subjects.txt
```

Check the column layout of your `list_subjects` output before trusting the
`awk` field number.
:::

## Downloading on a cluster

Compute nodes usually cannot reach external hosts, so run downloads on a login
node or a dedicated data-transfer node rather than inside a SLURM job. If your
site does allow outbound access from compute nodes, a download is still I/O
bound rather than CPU bound — request one core and be considerate about
parallelism against a shared XNAT server.
