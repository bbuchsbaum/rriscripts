---
title: Browsing a repository
description: List projects, subjects, experiments, and scans, and search scans by acquisition metadata.
---

XNAT's hierarchy is **project → subject → experiment (session) → scan**, and the
list commands follow it exactly. Each level needs the identifiers of the levels
above it.

All list commands print an R data frame to stdout.

## Projects

```bash
Rscript xnat_cli.R list_projects
```

| Option | Effect |
|---|---|
| `--columns COL1,COL2` | Comma-separated column names to return |
| `--limit N` | Maximum number of rows |
| `--offset N` | Number of rows to skip |

## Subjects

```bash
Rscript xnat_cli.R list_subjects --project_id MYPROJECT
```

Requires `--project_id`. Also accepts `--columns`, `--limit`, `--offset`.

## Experiments

```bash
Rscript xnat_cli.R list_experiments \
    --project_id MYPROJECT \
    --subject_id sub-01
```

Requires `--project_id` and `--subject_id`. Also accepts `--columns`, `--limit`,
`--offset`.

## Scans

```bash
Rscript xnat_cli.R list_scans \
    --project_id MYPROJECT \
    --subject_id sub-01 \
    --experiment_id MYPROJECT_E00123
```

Requires `--project_id`, `--subject_id`, and `--experiment_id`. Also accepts
`--columns`, `--limit`, `--offset`.

## Paging and columns

`--limit` and `--offset` page through large repositories:

```bash
Rscript xnat_cli.R list_subjects --project_id MYPROJECT --limit 50
Rscript xnat_cli.R list_subjects --project_id MYPROJECT --limit 50 --offset 50
```

`--columns` narrows the output, which matters on projects with many custom
fields:

```bash
Rscript xnat_cli.R list_subjects --project_id MYPROJECT --columns ID,label,group
```

## Searching scans

`search_scans` is the one command that cuts across the hierarchy. Instead of
walking down level by level, it filters scans by acquisition metadata:

```bash
Rscript xnat_cli.R search_scans \
    --project_id MYPROJECT \
    --scan_type BOLD \
    --tr 2.0
```

All filters are optional and combine:

| Option | Filters on |
|---|---|
| `--project_id PROJECT` | Project |
| `--subject_id SUBJECT` | Subject |
| `--experiment_id EXPERIMENT` | Experiment |
| `--age AGE` | Subject age |
| `--scan_type TYPE` | Scan type |
| `--tr VALUE` | Repetition time |
| `--te VALUE` | Echo time |
| `--ti VALUE` | Inversion time |
| `--flip VALUE` | Flip angle |
| `--voxel_res_units UNITS` | Voxel resolution units |
| `--voxel_res_x VALUE` | Voxel resolution, X |
| `--voxel_res_y VALUE` | Voxel resolution, Y |
| `--voxel_res_z VALUE` | Voxel resolution, Z |
| `--orientation ORIENTATION` | Slice orientation |

`--tr`, `--te`, `--ti`, `--flip`, and the three `--voxel_res_*` options are
numeric; the rest are strings.

This is the fastest way to answer questions like *which sessions in this project
actually have a 2-second-TR BOLD run at 3 mm isotropic?* — useful before
committing to a large download.

## Finding IDs for the download commands

The download commands need exact identifiers, and the list commands are how you
get them. A common sequence:

```bash
Rscript xnat_cli.R list_projects
Rscript xnat_cli.R list_subjects --project_id MYPROJECT --columns ID,label
Rscript xnat_cli.R list_experiments --project_id MYPROJECT --subject_id sub-01
Rscript xnat_cli.R list_scans --project_id MYPROJECT --subject_id sub-01 \
    --experiment_id MYPROJECT_E00123
```

Then hand the resulting IDs to [the download commands](../downloading/).
