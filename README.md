# rriscripts

Tools for neuroimaging and SLURM-based HPC workflows.

📖 **Documentation: <https://bbuchsbaum.github.io/rriscripts/>**

The repository has three independent parts. Each is useful on its own, and you
can install just the one you need.

| Toolkit | What it does | Guide |
|---|---|---|
| [`qexec/`](qexec/) | SLURM job submission and command expansion | [qexec guide](https://bbuchsbaum.github.io/rriscripts/qexec/) |
| [`fmriprep/`](fmriprep/) | Building and submitting fMRIPrep jobs for BIDS datasets | [fmriprep guide](https://bbuchsbaum.github.io/rriscripts/fmriprep/) |
| [`xnat_cli/`](xnat_cli/) | Working with XNAT repositories from R | [xnat_cli guide](https://bbuchsbaum.github.io/rriscripts/xnat-cli/) |

## Install

### qexec

General-purpose SLURM helpers — `qexec.sh`, `batch_exec.sh`, `bexec.sh`,
`cmd_expand.sh`, `send_slurm.sh`, `rjobtop.py`.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash
```

Installs to `~/bin` by default. To install elsewhere:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/qexec/install.sh | bash -s -- --prefix /path/to/bin
```

### fmriprep

The fMRIPrep launcher and its frontends.

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash
```

Installs the launcher bundle under `~/.local/share/fmriprep` and symlinks entry
points into `~/bin`. To customize:

```bash
curl -fsSL https://raw.githubusercontent.com/bbuchsbaum/rriscripts/main/fmriprep/install.sh | bash -s -- --lib-dir /path/to/lib --bin-dir /path/to/bin
```

### The full repository

For everything, including `xnat_cli` and the full source tree:

```bash
git clone https://github.com/bbuchsbaum/rriscripts.git
cd rriscripts
```

If `~/bin` is not already on your `PATH`:

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
```

## Requirements

- **qexec** — Bash 3.2+, Python 3, SLURM, and GNU Parallel for the batched-array
  workflow
- **fmriprep** — Python 3.10+, SLURM, and a container runtime
  (Apptainer/Singularity or Docker)
- **xnat_cli** — R with `optparse` and `xnatR`
- Tcl/Tk is only needed for the optional GUI frontends

## Documentation

The full guide is at <https://bbuchsbaum.github.io/rriscripts/>, built with
[Astro Starlight](https://starlight.astro.build/) from the sources in
[`docs/`](docs/). To work on it locally:

```bash
cd docs
npm install
npm run dev
```

It deploys to GitHub Pages automatically on push to `main`.

## License

[Mozilla Public License 2.0](LICENSE)
