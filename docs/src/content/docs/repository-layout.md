---
title: Repository layout
description: What every file in the repository is, for people modifying the tools rather than using them.
---

You do not need this page to use any of the tools — the guides cover the
commands you actually run. This is the map for reading or modifying the source.

Everything lives in one repository, [`bbuchsbaum/rriscripts`](https://github.com/bbuchsbaum/rriscripts),
with one directory per toolkit.

## `qexec/`

The commands you run are documented in the [qexec reference](../qexec/reference/).
The rest:

| File | What it is |
|---|---|
| `command_distributor.sh` | Runs *inside* a SLURM array task. Selects that task's slice of a command file and executes it with GNU Parallel. The submitters build this call for you. |
| `install.sh` | One-shot installer; copies the scripts to `~/bin` or `--prefix`. |
| `qexec_gui.tcl`, `batch_exec_gui.tcl` | Tcl/Tk frontends for `qexec.sh` and `batch_exec.sh`. |
| `batch_exec_gui` | Launcher shim for `batch_exec_gui.tcl`. |
| `qexec.hs`, `cmd_expand.hs`, `bexec.hs`, `command_distributor.hs` | Haskell implementations of the corresponding shell tools. Not built or installed by `install.sh`. |
| `rjobtop.py` | The job monitor. Reads `/proc`, so it only runs on Linux compute nodes. |
| `tests/` | [bats-core](https://github.com/bats-core/bats-core) tests. No SLURM needed — they use dry runs and mocks. Run with `bats qexec/tests`. |

## `fmriprep/`

`fmriprep_launcher.py` is the only entry point you invoke directly. The TUI and
GUI are reached through it (`fmriprep_launcher.py tui`), not run as scripts.

| File | What it is |
|---|---|
| `fmriprep_launcher.py` | CLI entry point: argument parsing, config merging, and the subcommands. |
| `fmriprep_backend.py` | `BuildConfig`, fMRIPrep command construction, the SLURM script template, and manifest I/O. |
| `fmriprep_shared.py` | INI loading, runtime detection, subject discovery, memory parsing, work-directory resolution. |
| `fmriprep_tui_autocomplete.py` | Optional Textual TUI (`pip install textual`). |
| `fmriprep_gui_tk.py` | Optional Tk GUI; needs Tk and an X11 display. |
| `fmriprep.ini.example` | Annotated example config covering user-level and project-level keys. Worth reading even if you never copy it — see [Configuration reference](../fmriprep/configuration/). |
| `run_fmriprep_wizard.sh` | Activates a likely virtualenv, then runs `fmriprep_launcher.py wizard`. |
| `install.sh` | Installs the bundle to `~/.local/share/fmriprep` and symlinks entry points. |
| `tests/` | `python3 -m unittest discover -s fmriprep/tests`. |

## `xnat_cli/`

| File | What it is |
|---|---|
| `xnat_cli.R` | The entire CLI — one script, no installer. Uses `optparse` for parsing and calls `xnatR::` for everything else. |

## Repository root

| File | What it is |
|---|---|
| `docs/` | This site. Astro + Starlight; see below. |
| `.github/workflows/ci.yml` | Runs the bats tests, Python compile checks, the fMRIPrep unit tests, and an `xnat_cli` smoke test. |
| `.github/workflows/docs.yml` | Builds and deploys this site to GitHub Pages on pushes touching `docs/`. |
| `LICENSE` | Mozilla Public License 2.0. |

## Working on the docs

```bash
cd docs
npm install
npm run dev      # local preview with hot reload
npm run build    # production build into docs/dist
```

Pages are Markdown under `docs/src/content/docs/`, and the sidebar is defined in
`docs/astro.config.mjs`. A push to `main` that touches `docs/` redeploys the
site.
