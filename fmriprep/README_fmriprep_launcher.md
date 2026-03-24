# fmriprep_launcher.py

This file is kept as a compatibility stub.

The canonical documentation now lives in [README.md](./README.md).

Use [fmriprep_launcher.py](./fmriprep_launcher.py) as the primary entrypoint:

```bash
python fmriprep_launcher.py probe
python fmriprep_launcher.py wizard --quick
python fmriprep_launcher.py slurm-array --help
python fmriprep_launcher.py print-cmd --help
```

Notes:

- `fmriprep_launcher.py` is the supported backend and CLI.
- `fmriprep_tui_autocomplete.py` and `fmriprep_gui_tk.py` are optional frontends.
- `fmriprep_command_builder.py` is retained as a legacy interactive frontend.
- INI is the supported config format; the `config_*.json` files are legacy examples.
