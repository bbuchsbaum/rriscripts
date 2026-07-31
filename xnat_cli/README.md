# xnat_cli — XNAT command-line interface

An R-based command-line interface for [XNAT](https://www.xnat.org/)
repositories, built on the `xnatR` package. Handles authentication and alias
tokens, browsing projects down to individual scans, and downloading anything
from one scan's files to an entire project.

📖 **Full documentation: <https://bbuchsbaum.github.io/rriscripts/xnat-cli/>**

## Requirements

R with the `optparse` and `xnatR` packages. There is no installer — this is a
single script used from a clone:

```bash
Rscript xnat_cli/xnat_cli.R help
```

To use it as a bare command:

```bash
chmod +x xnat_cli/xnat_cli.R
ln -s "$PWD/xnat_cli/xnat_cli.R" ~/bin/xnat_cli
```

## Commands

| Group | Commands |
|---|---|
| Core | `init`, `authenticate`, `auth_status`, `logout` |
| Tokens | `token_issue`, `token_list`, `token_validate`, `token_invalidate` |
| Browse | `list_projects`, `list_subjects`, `list_experiments`, `list_scans`, `search_scans` |
| Download | `download_files`, `download_experiment`, `download_subject`, `download_all` |

## A typical session

```bash
Rscript xnat_cli.R init
Rscript xnat_cli.R authenticate --base_url https://xnat.example.org --alias ABC --secret DEF
Rscript xnat_cli.R list_subjects --project_id MYPROJECT
Rscript xnat_cli.R download_subject --project_id MYPROJECT --subject_id sub-01
```

Run `xnat_cli.R <command>` with no arguments to see that command's options, or
see the [xnat_cli guide](https://bbuchsbaum.github.io/rriscripts/xnat-cli/) for
the full reference.

## Notes

- Targets the current `xnatR` API.
- `authenticate_xnat()` does not accept `--token` in `xnatR` 0.2.0 — use
  `--alias`/`--secret` or `--username`/`--password`.
- `download_all` iterates over `list_subjects()`, because `xnatR` no longer
  exports `download_all_subjects()`.
