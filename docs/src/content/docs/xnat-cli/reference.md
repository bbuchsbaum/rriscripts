---
title: Reference
description: Every xnat_cli command and its options.
---

```text
xnat_cli.R <command> [options]
```

Running `xnat_cli.R` with no arguments, or with `help`, prints the command
summary. Running a known command with no arguments prints that command's
options.

## Command summary

| Command | Purpose | Required options |
|---|---|---|
| `init` | Initialize `~/.xnatR_config.yml` | — |
| `authenticate` | Authenticate with an XNAT server | — |
| `auth_status` | Show whether a global `xnatR` session is active | — |
| `logout` | Clear the current `xnatR` session | — |
| `token_issue` | Issue a new alias token for the authenticated user | — |
| `token_list` | List active alias tokens | — |
| `token_validate` | Validate an alias token | `--alias`, `--secret` |
| `token_invalidate` | Invalidate an alias token | `--alias`, `--secret` |
| `list_projects` | List projects | — |
| `list_subjects` | List subjects in a project | `--project_id` |
| `list_experiments` | List experiments for a subject | `--project_id`, `--subject_id` |
| `list_scans` | List scans in an experiment | `--project_id`, `--subject_id`, `--experiment_id` |
| `search_scans` | Search scans by scan/session metadata | — |
| `download_files` | Download scan-level files | `--project_id`, `--subject_id`, `--experiment_id` |
| `download_experiment` | Download an experiment archive | `--experiment_id` |
| `download_subject` | Download all data for one subject | `--project_id`, `--subject_id` |
| `download_all` | Download all subjects in a project | `--project_id` |
| `help` | Display the help message | — |

Missing a required option produces
`Error: Missing required options for <command>: --<name>`.

## `authenticate`

| Option | Effect |
|---|---|
| `--base_url URL` | Base URL of the XNAT server |
| `--username USER` | Username |
| `--password PASS` | Password |
| `--alias TOKEN_ALIAS` | Alias token, used as the username |
| `--secret TOKEN_SECRET` | Alias token secret, used as the password |
| `--ssl_verify` / `--no_ssl_verify` | Verify SSL certificates (default: verify) |
| `--verify` / `--no_verify` | Verify credentials with a test request (default: verify) |
| `--use_jsession` | Use JSESSION-based auth |

`--alias` and `--secret` must be given together. `--token` is present but
unsupported by the current `xnatR` and will error.

## `logout`

| Option | Effect |
|---|---|
| `--invalidate_session` | Also invalidate the remote session where applicable |

## `token_validate`, `token_invalidate`

| Option | Effect |
|---|---|
| `--alias TOKEN_ALIAS` | Token alias |
| `--secret TOKEN_SECRET` | Token secret |

Both are required for both commands.

## List commands

`list_projects`, `list_subjects`, `list_experiments`, and `list_scans` share
these options, adding the identifiers of each level of the hierarchy:

| Option | Effect |
|---|---|
| `--project_id PROJECT` | Project ID |
| `--subject_id SUBJECT` | Subject ID |
| `--experiment_id EXPERIMENT` | Experiment ID |
| `--columns COL1,COL2` | Comma-separated column names |
| `--limit N` | Maximum number of rows |
| `--offset N` | Number of rows to skip |

See [Browsing](../browsing/) for which identifiers each command requires.

## `search_scans`

All filters optional:

| Option | Type |
|---|---|
| `--project_id PROJECT` | string |
| `--subject_id SUBJECT` | string |
| `--experiment_id EXPERIMENT` | string |
| `--age AGE` | string |
| `--scan_type TYPE` | string |
| `--tr VALUE` | numeric |
| `--te VALUE` | numeric |
| `--ti VALUE` | numeric |
| `--flip VALUE` | numeric |
| `--voxel_res_units UNITS` | string |
| `--voxel_res_x VALUE` | numeric |
| `--voxel_res_y VALUE` | numeric |
| `--voxel_res_z VALUE` | numeric |
| `--orientation ORIENTATION` | string |

## `download_files`

| Option | Default |
|---|---|
| `--project_id PROJECT` | *(required)* |
| `--subject_id SUBJECT` | *(required)* |
| `--experiment_id EXPERIMENT` | *(required)* |
| `--scan_id SCAN_ID` | `ALL` |
| `--resource RESOURCE` | all |
| `--format zip\|tar.gz` | `zip` |
| `--dest_dir DIR` | current directory |
| `--dest_file FILE` | derived |
| `--progress` / `--no_progress` | on |

## `download_experiment`

| Option | Default |
|---|---|
| `--experiment_id EXPERIMENT` | *(required)* |
| `--scan_id SCAN_ID` | `ALL` |
| `--format zip\|tar.gz` | `zip` |
| `--dest_dir DIR` | current directory |
| `--dest_file FILE` | derived |
| `--extract` | off |
| `--progress` / `--no_progress` | on |
| `--strict` / `--no_strict` | strict |

## `download_subject`

| Option | Default |
|---|---|
| `--project_id PROJECT` | *(required)* |
| `--subject_id SUBJECT` | *(required)* |
| `--format zip\|tar.gz` | `zip` |
| `--dest_dir DIR` | current directory |
| `--progress` / `--no_progress` | on |

## `download_all`

| Option | Default |
|---|---|
| `--project_id PROJECT` | *(required)* |
| `--format zip\|tar.gz` | `zip` |
| `--dest_dir DIR` | current directory |
| `--progress` / `--no_progress` | on |

## Behavior notes

- The browse and download commands call `xnatR::authenticate_xnat()` themselves
  before issuing requests, so they work from stored config or an active session
  without an explicit `authenticate` step.
- `xnatR` is loaded on demand rather than at startup, so `help` and
  `help <command>` work without it installed. Every other command checks first
  and reports the install command if it is missing.
- The CLI also checks that the specific functions it needs exist in the
  installed `xnatR`, and fails with a clear message if the package is out of
  date: `Error: xnatR::<fn>() is not available in the installed xnatR package.`
- `download_all` determines subject identifiers from the first of `ID`, `id`,
  `label`, or `subject_id` present in the `list_subjects()` output, and errors if
  none of them are.
- An unrecognized command exits with `Unknown command: <name>`.
