# fmriprep_launcher.py

**What this is**: a one‑stop tool to build correct fMRIPrep commands and generate a Slurm array job for a BIDS dataset.

## Quick start

### Discover what you have
```bash
python fmriprep_launcher.py probe
```

### Generate array script for *all* subjects
```bash
python fmriprep_launcher.py slurm-array   --bids /path/to/BIDS   --out  /path/to/BIDS/derivatives/fmriprep   --work /scratch/fmriprep_work   --subjects all   --runtime auto   --container auto   --fs-license /path/to/license.txt   --partition compute --time 24:00:00   --cpus-per-task 8 --mem 32G   --email you@uni.edu --mail-type END,FAIL
```
This writes `fmriprep_job/fmriprep_array.sbatch`, `fmriprep_job/subjects.txt`, and a `logs/` folder.  
Submit it:
```bash
sbatch fmriprep_job/fmriprep_array.sbatch
```

### Print the exact fMRIPrep commands (no submission)
```bash
python fmriprep_launcher.py print-cmd   --bids /path/to/BIDS   --out  /path/to/BIDS/derivatives/fmriprep   --work /scratch/fmriprep_work   --subjects sub-01 sub-02   --runtime singularity   --container /containers/nipreps-fmriprep-23.2.0.sif   --fs-license /path/to/license.txt   --skip-bids-validation   --output-spaces "MNI152NLin2009cAsym:res-2 T1w"   --cifti-output   --use-syn-sdc   --extra "--stop-on-first-crash"
```

### Wizard (interactive)
```bash
python fmriprep_launcher.py wizard
```

## Notes & defaults

- Runtimes: **Singularity/Apptainer**, **fmriprep-docker**, or **Docker** (auto-detected; override with `--runtime`).
- Container version: auto‑picked from `$FMRIPREP_SIF_DIR` (for Singularity) or local Docker images; falls back to `nipreps/fmriprep:latest`.
- Resources: `--nprocs` from SLURM or CPU count; `--omp-nthreads` defaults to `min(8, nprocs)`; `--mem-mb` ~= 90% of node memory.
- License: mounted to `/opt/freesurfer/license.txt` and passed as `--fs-license-file` in all runtimes.
- BIDS participants: reads `participants.tsv` (column `participant_id`) if present, else scans `sub-*` folders.
- Output/work mounts: consistent `/data`, `/out`, `/work` across runtimes.
