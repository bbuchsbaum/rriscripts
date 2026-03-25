# fmriprep_launcher.py

This file is kept as a compatibility stub.

The canonical documentation now lives in [README.md](./README.md).

Use [fmriprep_launcher.py](./fmriprep_launcher.py) as the primary entrypoint:

```bash
python3 fmriprep_launcher.py probe
python3 fmriprep_launcher.py wizard --quick
python3 fmriprep_launcher.py slurm-array --help
python3 fmriprep_launcher.py print-cmd --help
python3 fmriprep_launcher.py rerun-failed --help
```

Notes:

- `fmriprep_launcher.py` is the supported backend and CLI.
- `fmriprep_tui_autocomplete.py` and `fmriprep_gui_tk.py` are optional frontends.
- `fmriprep_command_builder.py` is retained as a legacy interactive frontend.
- `slurm-array` now writes `job_manifest.json` and per-subject `status/` markers.
- `rerun-failed` rebuilds a new job bundle containing only subjects marked `.failed`.
- INI is the supported config format; the `config_*.json` files are legacy examples.
