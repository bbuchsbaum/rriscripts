---
title: xnat_cli
description: An R command-line interface for XNAT repositories, built on xnatR.
---

`xnat_cli/xnat_cli.R` is an R-based command-line interface for
[XNAT](https://www.xnat.org/) repositories, built on the `xnatR` package. It
covers authentication and token management, browsing projects down to individual
scans, and downloading anything from a single scan's files to an entire project.

```bash
Rscript xnat_cli/xnat_cli.R <command> [options]
```

## Requirements

R with the `optparse` and `xnatR` packages:

```r
install.packages("optparse")
# xnatR: install from wherever your lab hosts it
```

Unlike `qexec` and `fmriprep`, this tool has no installer — it is a single
script used directly from a clone of the repository:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
Rscript rriscripts/xnat_cli/xnat_cli.R help
```

To use it as a bare command, make it executable and put it on your `PATH`:

```bash
chmod +x rriscripts/xnat_cli/xnat_cli.R
ln -s "$PWD/rriscripts/xnat_cli/xnat_cli.R" ~/bin/xnat_cli
xnat_cli help
```

Examples throughout this guide use `xnat_cli.R` for brevity.

## The commands

| Group | Commands |
|---|---|
| Core | `init`, `authenticate`, `auth_status`, `logout` |
| Tokens | `token_issue`, `token_list`, `token_validate`, `token_invalidate` |
| Browse | `list_projects`, `list_subjects`, `list_experiments`, `list_scans`, `search_scans` |
| Download | `download_files`, `download_experiment`, `download_subject`, `download_all` |
| Help | `help` |

Run `xnat_cli.R help` for the summary, or `xnat_cli.R <command>` with no
arguments to see that command's options.

## A typical session

```bash
# One-time: create the config file
Rscript xnat_cli.R init

# Authenticate (see the Authentication page for token-based auth)
Rscript xnat_cli.R authenticate --base_url https://xnat.example.org --username me

# Find what you're after
Rscript xnat_cli.R list_projects
Rscript xnat_cli.R list_subjects --project_id MYPROJECT

# Pull it down
Rscript xnat_cli.R download_subject --project_id MYPROJECT --subject_id sub-01
```

## Start here

- [Authentication](./authentication/) — config, passwords, and alias tokens
- [Browsing a repository](./browsing/) — projects, subjects, experiments, scans
- [Downloading data](./downloading/) — files, experiments, subjects, projects
- [Reference](./reference/) — every command and option

## Notes from the tool itself

- This CLI targets the current `xnatR` API.
- `authenticate_xnat()` does not accept a `--token` argument in `xnatR` 0.2.0 —
  use `--alias`/`--secret` or `--username`/`--password` instead.
- `download_all` is implemented in this CLI by iterating over `list_subjects()`,
  because `xnatR` no longer exports `download_all_subjects()`.
