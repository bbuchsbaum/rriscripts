#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fmriprep_gui_tk.py

A fully graphical Tcl/Tk (Tkinter) GUI to build fMRIPrep commands and generate
a Slurm array script for a BIDS dataset. No third-party dependencies.

Features
--------
- Pick BIDS directory (auto-discovers subjects via participants.tsv or sub-*)
- Choose runtime: Singularity/Apptainer, fmriprep-docker, or Docker
- Choose container/version (discover *.sif/.simg via $FMRIPREP_SIF_DIR, or list Docker images)
- Pick output/work dirs, FS license path
- Capacity-aware defaults (from SLURM env or system); live check that nprocs*omp <= cpus-per-task
- Popular fMRIPrep flags (skip bids validation, AROMA, CIFTI, recon-all, SyN SDC, output spaces, extra flags)
- Optional TemplateFlow cache binding
- Preview per-subject commands
- Save run_fmriprep.sh
- Generate Slurm array script (+ subjects.txt + logs/)

Run
---
python fmriprep_gui_tk.py
"""

import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------- Utilities ----------------

def which(cmd: str):
    return shutil.which(cmd)

def run_cmd(cmd):
    try:
        return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        return e

def read_meminfo_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except Exception:
        pass
    return 16000

def default_resources_from_env():
    cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", os.environ.get("SLURM_CPUS_ON_NODE", "0")) or 0)
    mem_mb = 0
    if "SLURM_MEM_PER_CPU" in os.environ and cpus > 0:
        mem_mb = int(os.environ["SLURM_MEM_PER_CPU"]) * cpus
    elif "SLURM_MEM_PER_NODE" in os.environ:
        mem_mb = int(os.environ["SLURM_MEM_PER_NODE"])
    if cpus <= 0:
        cpus = os.cpu_count() or 4
    if mem_mb == 0:
        mem_mb = read_meminfo_mb()
    mem_mb = int(mem_mb * 0.9)
    return cpus, mem_mb

def mb_to_human(mb: int) -> str:
    if mb >= 1_000_000:
        return f"{mb/1_000_000:.1f}T"
    if mb >= 1000:
        return f"{mb/1000:.1f}G"
    return f"{mb}M"

def discover_sif_images():
    images = []
    sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
    if sif_dir and os.path.isdir(os.path.expanduser(sif_dir)):
        for p in Path(os.path.expanduser(sif_dir)).iterdir():
            if p.suffix.lower() in (".sif", ".simg") and "fmriprep" in p.name.lower():
                images.append(str(p))
    return sorted(images)

def docker_list_fmriprep_images():
    if not which("docker"):
        return []
    proc = run_cmd(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    out = proc.stdout if hasattr(proc, "stdout") else ""
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return [l for l in lines if re.match(r"^(nipreps|poldracklab|fmriprep)/fmriprep(:|$)", l)]

def detect_runtime_auto():
    if which("singularity") or which("apptainer"):
        return "singularity"
    if which("fmriprep-docker"):
        return "fmriprep-docker"
    if which("docker"):
        return "docker"
    return "singularity"  # default preference

# ---------------- BIDS helpers ----------------

def parse_participants_tsv(bids_dir: Path):
    f = bids_dir / "participants.tsv"
    subs = []
    if f.exists():
        with open(f, "r", newline="") as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter="\t")
            if not reader.fieldnames:
                return subs
            col = "participant_id" if "participant_id" in reader.fieldnames else reader.fieldnames[0]
            for row in reader:
                raw = str(row[col]).strip()
                if raw:
                    subs.append(raw if raw.startswith("sub-") else f"sub-{raw}")
    return sorted(list(dict.fromkeys(subs)))

def scan_sub_dirs(bids_dir: Path):
    return sorted([p.name for p in bids_dir.iterdir() if p.is_dir() and p.name.startswith("sub-")])

def discover_subjects(bids_dir: Path):
    subs = parse_participants_tsv(bids_dir)
    return subs if subs else scan_sub_dirs(bids_dir)

# ---------------- fMRIPrep command building ----------------

def build_fmriprep_cmds(
    subjects, bids_dir, out_dir, work_dir,
    runtime, container, fs_license,
    nprocs, omp, mem_mb,
    skip_val, output_spaces, aroma, cifti, reconall, syn_sdc, extra,
    bind_tf=False
):
    cmds = []
    bids_in = "/data"
    out_in = "/out"
    work_in = "/work"
    fs_in = "/opt/freesurfer/license.txt"
    tf_home = str(Path.home() / ".cache" / "templateflow")

    base_cli = [
        "participant",
        "--nprocs", str(nprocs),
        "--omp-nthreads", str(omp),
        "--mem-mb", str(mem_mb),
        "--notrack",
    ]
    if skip_val:
        base_cli += ["--skip-bids-validation"]
    if output_spaces.strip():
        base_cli += ["--output-spaces"] + output_spaces.split()
    if aroma:
        base_cli += ["--use-aroma"]
    if cifti:
        base_cli += ["--cifti-output", "91k"]
    if not reconall:
        base_cli += ["--fs-no-reconall"]
    if syn_sdc:
        base_cli += ["--use-syn-sdc"]
    if extra.strip():
        base_cli += extra.split()

    for sub in subjects:
        label = sub[4:] if sub.startswith("sub-") else sub
        cli = base_cli + ["--participant-label", label]

        if runtime == "singularity":
            rt_bin = "singularity" if which("singularity") else "apptainer"
            cmd = [rt_bin, "run", "--cleanenv",
                   "-B", f"{bids_dir}:{bids_in}:ro",
                   "-B", f"{out_dir}:{out_in}",
                   "-B", f"{work_dir}:{work_in}",
                   "-B", f"{fs_license}:{fs_in}:ro"]
            if bind_tf and os.path.isdir(tf_home):
                cmd += ["-B", f"{tf_home}:/templateflow"]
                # Set env var inside container
                cmd = ["env", "SINGULARITYENV_TEMPLATEFLOW_HOME=/templateflow"] + cmd
            cmd += [container, bids_in, out_in] + cli + ["--work-dir", work_in, "--fs-license-file", fs_in]
            cmds.append(cmd)

        elif runtime == "fmriprep-docker":
            # Wrapper handles mounts; extra container opts not added here
            cmd = ["fmriprep-docker", str(bids_dir), str(out_dir)] + cli + ["--work-dir", str(work_dir), "--fs-license-file", str(fs_license)]
            cmds.append(cmd)

        elif runtime == "docker":
            cmd = ["docker", "run", "--rm",
                   "-v", f"{bids_dir}:{bids_in}:ro",
                   "-v", f"{out_dir}:{out_in}",
                   "-v", f"{work_dir}:{work_in}",
                   "-v", f"{fs_license}:{fs_in}:ro"]
            if bind_tf and os.path.isdir(tf_home):
                cmd += ["-v", f"{tf_home}:/templateflow", "-e", "TEMPLATEFLOW_HOME=/templateflow"]
            cmd += [container, bids_in, out_in] + cli + ["--work-dir", work_in, "--fs-license-file", fs_in]
            cmds.append(cmd)
        else:
            raise ValueError(f"Unknown runtime: {runtime}")
    return cmds

SLURM_TEMPLATE = """\
#!/usr/bin/env bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --time={time}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
#SBATCH --nodes=1
#SBATCH --array=0-{array_max}
#SBATCH --output={log_dir}/%x_%A_%a.out
#SBATCH --error={log_dir}/%x_%A_%a.err
{account}{mail}{module}

set -euo pipefail

BIDS_DIR="{bids}"
OUT_DIR="{out}"
WORK_DIR="{work}"
FS_LICENSE="{fs_license}"
SUBJECT_FILE="{subject_file}"
RUNTIME="{runtime}"
CONTAINER="{container}"
NPROCS="{nprocs}"
OMP="{omp}"
MEM_MB="{mem_mb}"
EXTRA="{extra}"
SKIP_VAL="{skip_val}"
OUTPUT_SPACES="{output_spaces}"
AROMA="{aroma}"
CIFTI="{cifti}"
RECONALL="{reconall}"
SYN_SDC="{syn_sdc}"
BIND_TF="{bind_tf}"

SUBS=($(grep -v '^#' "$SUBJECT_FILE" | sed '/^$/d'))
SUB="${{SUBS[$SLURM_ARRAY_TASK_ID]}}"
if [[ -z "$SUB" ]]; then echo "No subject at index $SLURM_ARRAY_TASK_ID"; exit 1; fi

mkdir -p "$OUT_DIR" "$WORK_DIR" "{log_dir}"

CLI=(participant --participant-label "${{SUB#sub-}}" --nprocs "$NPROCS" --omp-nthreads "$OMP" --mem-mb "$MEM_MB" --notrack)

if [[ "$SKIP_VAL" == "1" ]]; then CLI+=(--skip-bids-validation); fi
if [[ -n "$OUTPUT_SPACES" ]]; then CLI+=(--output-spaces $OUTPUT_SPACES); fi
if [[ "$AROMA" == "1" ]]; then CLI+=(--use-aroma); fi
if [[ "$CIFTI" == "1" ]]; then CLI+=(--cifti-output 91k); fi
if [[ "$RECONALL" == "0" ]]; then CLI+=(--fs-no-reconall); fi
if [[ "$SYN_SDC" == "1" ]]; then CLI+=(--use-syn-sdc); fi
if [[ -n "$EXTRA" ]]; then CLI+=($EXTRA); fi

if [[ "$RUNTIME" == "singularity" ]]; then
  RT_BIN=$(command -v singularity || command -v apptainer)
  TF_ENV=""
  TF_BIND=""
  if [[ "$BIND_TF" == "1" ]]; then
    if [[ -d "$HOME/.cache/templateflow" ]]; then
      TF_BIND="-B $HOME/.cache/templateflow:/templateflow"
      TF_ENV="SINGULARITYENV_TEMPLATEFLOW_HOME=/templateflow"
    fi
  fi
  env $TF_ENV "$RT_BIN" run --cleanenv \
    -B "$BIDS_DIR:/data:ro" \
    -B "$OUT_DIR:/out" \
    -B "$WORK_DIR:/work" \
    -B "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \
    $TF_BIND \
    "$CONTAINER" \
    /data /out "${{CLI[@]}}" --work-dir /work --fs-license-file /opt/freesurfer/license.txt

elif [[ "$RUNTIME" == "fmriprep-docker" ]]; then
  fmriprep-docker "$BIDS_DIR" "$OUT_DIR" "${{CLI[@]}}" --work-dir "$WORK_DIR" --fs-license-file "$FS_LICENSE"

elif [[ "$RUNTIME" == "docker" ]]; then
  TF_ENV=""
  TF_BIND=""
  if [[ "$BIND_TF" == "1" ]]; then
    if [[ -d "$HOME/.cache/templateflow" ]]; then
      TF_BIND="-v $HOME/.cache/templateflow:/templateflow -e TEMPLATEFLOW_HOME=/templateflow"
    fi
  fi
  docker run --rm \
    -v "$BIDS_DIR:/data:ro" \
    -v "$OUT_DIR:/out" \
    -v "$WORK_DIR:/work" \
    -v "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \
    $TF_BIND \
    "$CONTAINER" \
    /data /out "${{CLI[@]}}" --fs-license-file /opt/freesurfer/license.txt --work-dir /work

else
  echo "Unknown runtime: $RUNTIME"; exit 2
fi
"""

# ---------------- GUI ----------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("fMRIPrep GUI (Tk)")
        self.geometry("1000x740")
        self.minsize(900, 680)

        self._build_vars()
        self._build_ui()
        self._auto_defaults()

    def _build_vars(self):
        # Paths & dataset
        self.bids_dir = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.work_dir = tk.StringVar()
        self.fs_license = tk.StringVar()
        self.runtime = tk.StringVar(value=detect_runtime_auto())
        self.container = tk.StringVar()
        self.bind_tf = tk.BooleanVar(value=True)

        # Resources
        self.cpus_per_task = tk.IntVar(value=4)
        self.nprocs = tk.IntVar(value=4)
        self.omp = tk.IntVar(value=2)
        self.mem_mb = tk.IntVar(value=8000)

        # Flags
        self.skip_val = tk.BooleanVar(value=True)
        self.aroma = tk.BooleanVar(value=False)
        self.cifti = tk.BooleanVar(value=False)
        self.reconall = tk.BooleanVar(value=False)
        self.synsdc = tk.BooleanVar(value=False)
        self.output_spaces = tk.StringVar(value="MNI152NLin2009cAsym:res-2 T1w")
        self.extra = tk.StringVar(value="")

        # Slurm
        self.slurm_partition = tk.StringVar(value="compute")
        self.slurm_time = tk.StringVar(value="24:00:00")
        self.slurm_mem = tk.StringVar(value="")  # if blank, use mem_mb->human
        self.slurm_account = tk.StringVar(value="")
        self.slurm_email = tk.StringVar(value="")
        self.slurm_mail_type = tk.StringVar(value="END,FAIL")
        self.slurm_job_name = tk.StringVar(value="fmriprep")
        self.slurm_module_sing = tk.BooleanVar(value=True)
        self.script_outdir = tk.StringVar(value="fmriprep_job")

        # Derived/warnings
        self.threads_label = tk.StringVar(value="Effective threads: nprocs × omp = 0 (<= cpus-per-task?)")
        self.subjects = []

    def _build_ui(self):
        pad = {'padx': 6, 'pady': 4}

        # --- Dataset frame ---
        frm_ds = ttk.LabelFrame(self, text="Dataset")
        frm_ds.pack(fill="x", **pad)

        ttk.Label(frm_ds, text="BIDS directory:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_ds, textvariable=self.bids_dir, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(frm_ds, text="Browse", command=self._pick_bids).grid(row=0, column=2, sticky="w")
        ttk.Button(frm_ds, text="Discover subjects", command=self._discover_subjects).grid(row=0, column=3, sticky="w")

        self.lst_subjects = tk.Listbox(frm_ds, selectmode=tk.EXTENDED, height=6)
        self.lst_subjects.grid(row=1, column=0, columnspan=3, sticky="we", pady=(6, 2))
        btns = ttk.Frame(frm_ds)
        btns.grid(row=1, column=3, sticky="n")
        ttk.Button(btns, text="Select All", command=self._select_all_subjects).pack(fill="x")
        ttk.Button(btns, text="Clear", command=self._clear_subjects).pack(fill="x", pady=(4,0))

        for i in range(4):
            frm_ds.grid_columnconfigure(i, weight=1)

        # --- Paths & runtime ---
        frm_paths = ttk.LabelFrame(self, text="Paths & Runtime")
        frm_paths.pack(fill="x", **pad)

        # Output
        ttk.Label(frm_paths, text="Output dir:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_paths, textvariable=self.out_dir, width=50).grid(row=0, column=1, sticky="we")
        ttk.Button(frm_paths, text="Browse", command=lambda: self._pick_dir(self.out_dir)).grid(row=0, column=2, sticky="w")

        # Work
        ttk.Label(frm_paths, text="Work dir:").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm_paths, textvariable=self.work_dir, width=50).grid(row=1, column=1, sticky="we")
        ttk.Button(frm_paths, text="Browse", command=lambda: self._pick_dir(self.work_dir)).grid(row=1, column=2, sticky="w")

        # FS license
        ttk.Label(frm_paths, text="FS license:").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm_paths, textvariable=self.fs_license, width=50).grid(row=2, column=1, sticky="we")
        ttk.Button(frm_paths, text="Browse", command=lambda: self._pick_file(self.fs_license)).grid(row=2, column=2, sticky="w")

        # Runtime
        ttk.Label(frm_paths, text="Runtime:").grid(row=0, column=3, sticky="w")
        ttk.OptionMenu(frm_paths, self.runtime, self.runtime.get(), "singularity", "fmriprep-docker", "docker").grid(row=0, column=4, sticky="we")

        # Container
        ttk.Label(frm_paths, text="Container (SIF or image:tag):").grid(row=1, column=3, sticky="w")
        ttk.Entry(frm_paths, textvariable=self.container, width=40).grid(row=1, column=4, sticky="we")
        ttk.Button(frm_paths, text="Browse", command=self._browse_container).grid(row=1, column=5, sticky="w")
        ttk.Button(frm_paths, text="Discover", command=self._discover_containers).grid(row=1, column=6, sticky="w")

        # TemplateFlow binding
        ttk.Checkbutton(frm_paths, text="Bind TemplateFlow cache", variable=self.bind_tf).grid(row=2, column=3, columnspan=2, sticky="w")

        for i in range(7):
            frm_paths.grid_columnconfigure(i, weight=1)

        # --- Resources ---
        frm_res = ttk.LabelFrame(self, text="Resources")
        frm_res.pack(fill="x", **pad)

        ttk.Label(frm_res, text="cpus-per-task (Slurm)").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_res, textvariable=self.cpus_per_task, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(frm_res, text="nprocs").grid(row=0, column=2, sticky="w")
        ttk.Entry(frm_res, textvariable=self.nprocs, width=10).grid(row=0, column=3, sticky="w")
        ttk.Label(frm_res, text="omp-nthreads").grid(row=0, column=4, sticky="w")
        ttk.Entry(frm_res, textvariable=self.omp, width=10).grid(row=0, column=5, sticky="w")
        ttk.Label(frm_res, text="mem-mb").grid(row=0, column=6, sticky="w")
        ttk.Entry(frm_res, textvariable=self.mem_mb, width=12).grid(row=0, column=7, sticky="w")
        ttk.Button(frm_res, text="Auto-fill", command=self._auto_defaults).grid(row=0, column=8, sticky="e")

        ttk.Label(frm_res, textvariable=self.threads_label, foreground="#555").grid(row=1, column=0, columnspan=9, sticky="w", pady=(4,0))

        for i in range(9):
            frm_res.grid_columnconfigure(i, weight=1)

        # --- Flags ---
        frm_flags = ttk.LabelFrame(self, text="fMRIPrep Options")
        frm_flags.pack(fill="x", **pad)

        ttk.Label(frm_flags, text="Output spaces").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_flags, textvariable=self.output_spaces, width=60).grid(row=0, column=1, columnspan=6, sticky="we")

        ttk.Checkbutton(frm_flags, text="Skip BIDS validation", variable=self.skip_val).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(frm_flags, text="Use ICA-AROMA", variable=self.aroma).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(frm_flags, text="CIFTI 91k", variable=self.cifti).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(frm_flags, text="Run FreeSurfer recon-all", variable=self.reconall).grid(row=1, column=3, sticky="w")
        ttk.Checkbutton(frm_flags, text="Enable SyN SDC", variable=self.synsdc).grid(row=1, column=4, sticky="w")

        ttk.Label(frm_flags, text="Extra flags").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm_flags, textvariable=self.extra, width=80).grid(row=2, column=1, columnspan=6, sticky="we")

        for i in range(7):
            frm_flags.grid_columnconfigure(i, weight=1)

        # --- Slurm ---
        frm_slurm = ttk.LabelFrame(self, text="Slurm Array Script")
        frm_slurm.pack(fill="x", **pad)

        ttk.Label(frm_slurm, text="partition").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_partition, width=12).grid(row=0, column=1, sticky="w")

        ttk.Label(frm_slurm, text="time").grid(row=0, column=2, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_time, width=12).grid(row=0, column=3, sticky="w")

        ttk.Label(frm_slurm, text="--mem").grid(row=0, column=4, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_mem, width=10).grid(row=0, column=5, sticky="w")
        ttk.Label(frm_slurm, text="(leave blank to auto from mem-mb)").grid(row=0, column=6, sticky="w")

        ttk.Label(frm_slurm, text="account").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_account, width=12).grid(row=1, column=1, sticky="w")
        ttk.Label(frm_slurm, text="email").grid(row=1, column=2, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_email, width=18).grid(row=1, column=3, sticky="w")
        ttk.Label(frm_slurm, text="mail-type").grid(row=1, column=4, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_mail_type, width=12).grid(row=1, column=5, sticky="w")
        ttk.Label(frm_slurm, text="job-name").grid(row=1, column=6, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.slurm_job_name, width=12).grid(row=1, column=7, sticky="w")
        ttk.Checkbutton(frm_slurm, text="module load singularity", variable=self.slurm_module_sing).grid(row=1, column=8, sticky="w")

        ttk.Label(frm_slurm, text="Script output dir").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm_slurm, textvariable=self.script_outdir, width=30).grid(row=2, column=1, columnspan=3, sticky="we")
        ttk.Button(frm_slurm, text="Browse", command=lambda: self._pick_dir(self.script_outdir)).grid(row=2, column=4, sticky="w")

        for i in range(9):
            frm_slurm.grid_columnconfigure(i, weight=1)

        # --- Actions & Output ---
        frm_actions = ttk.Frame(self)
        frm_actions.pack(fill="x", **pad)
        ttk.Button(frm_actions, text="Preview Commands", command=self.preview_commands).pack(side="left")
        ttk.Button(frm_actions, text="Save run_fmriprep.sh", command=self.save_runner).pack(side="left", padx=(6,0))
        ttk.Button(frm_actions, text="Generate Slurm Array Script", command=self.generate_slurm).pack(side="left", padx=(6,0))

        self.txt = tk.Text(self, height=14, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=6, pady=(0,6))

        # Trace changes to update the thread warning
        for var in (self.cpus_per_task, self.nprocs, self.omp):
            var.trace_add("write", lambda *args: self._update_threads_label())

    # --- UI callbacks ---

    def _pick_bids(self):
        d = filedialog.askdirectory(title="Select BIDS root")
        if d:
            self.bids_dir.set(d)
            # Auto-set out/work under BIDS
            self.out_dir.set(str(Path(d) / "derivatives" / "fmriprep"))
            self.work_dir.set(str(Path(d) / "work_fmriprep"))
            self._discover_subjects()

    def _pick_dir(self, var: tk.StringVar):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _pick_file(self, var: tk.StringVar):
        f = filedialog.askopenfilename()
        if f:
            var.set(f)

    def _browse_container(self):
        if self.runtime.get() == "singularity":
            f = filedialog.askopenfilename(title="Select fMRIPrep .sif/.simg", filetypes=[("Singularity image", "*.sif *.simg"), ("All files","*.*")])
            if f:
                self.container.set(f)
        else:
            # plain text entry for docker image
            messagebox.showinfo("Container", "For Docker/fmriprep-docker, enter an image like 'nipreps/fmriprep:latest' in the text field.")

    def _discover_subjects(self):
        bids = Path(self.bids_dir.get()).expanduser()
        if not bids.exists():
            messagebox.showerror("Error", "BIDS directory does not exist."); return
        subs = discover_subjects(bids)
        self.subjects = subs
        self.lst_subjects.delete(0, tk.END)
        for s in subs:
            self.lst_subjects.insert(tk.END, s)

    def _select_all_subjects(self):
        self.lst_subjects.select_set(0, tk.END)

    def _clear_subjects(self):
        self.lst_subjects.selection_clear(0, tk.END)

    def _discover_containers(self):
        if self.runtime.get() == "singularity":
            imgs = discover_sif_images()
            if not imgs:
                messagebox.showinfo("Discover", "No fMRIPrep .sif/.simg found in $FMRIPREP_SIF_DIR."); return
            # Choose via a simple selector
            top = tk.Toplevel(self); top.title("Select container")
            lb = tk.Listbox(top, width=80, height=8); lb.pack(fill="both", expand=True, padx=6, pady=6)
            for i in imgs: lb.insert(tk.END, i)
            def choose():
                sel = lb.curselection()
                if sel:
                    self.container.set(lb.get(sel[0]))
                    top.destroy()
            ttk.Button(top, text="Choose", command=choose).pack(pady=6)
        else:
            imgs = docker_list_fmriprep_images()
            if not imgs:
                messagebox.showinfo("Discover", "No local Docker images found (or Docker unavailable)."); return
            top = tk.Toplevel(self); top.title("Select Docker image:tag")
            lb = tk.Listbox(top, width=60, height=8); lb.pack(fill="both", expand=True, padx=6, pady=6)
            for i in imgs: lb.insert(tk.END, i)
            def choose():
                sel = lb.curselection()
                if sel:
                    self.container.set(lb.get(sel[0]))
                    top.destroy()
            ttk.Button(top, text="Choose", command=choose).pack(pady=6)

    def _auto_defaults(self):
        cpus, mem = default_resources_from_env()
        self.cpus_per_task.set(cpus)
        self.nprocs.set(cpus)
        self.omp.set(min(8, max(1, cpus//8)) if cpus>8 else 1)
        self.mem_mb.set(mem)
        self._update_threads_label()

    def _update_threads_label(self):
        try:
            eff = int(self.nprocs.get()) * int(self.omp.get())
            cap = int(self.cpus_per_task.get())
            msg = f"Effective threads: nprocs × omp = {eff}"
            if cap > 0:
                msg += f" (cpus-per-task={cap})"
                if eff > cap:
                    msg += "  ⚠ oversubscribed — lower nprocs or omp"
            self.threads_label.set(msg)
        except Exception:
            self.threads_label.set("Effective threads: nprocs × omp = ?")

    def _selected_subjects(self):
        sel = [self.lst_subjects.get(i) for i in self.lst_subjects.curselection()]
        return sel if sel else list(self.subjects)

    def _validate_inputs(self, for_slurm=False):
        bids = Path(self.bids_dir.get()).expanduser()
        if not bids.exists():
            messagebox.showerror("Error", "BIDS directory does not exist."); return None
        out = Path(self.out_dir.get()).expanduser()
        work = Path(self.work_dir.get()).expanduser()
        fs = Path(self.fs_license.get()).expanduser()
        if not fs.exists():
            messagebox.showerror("Error", "FS license does not exist."); return None

        runtime = self.runtime.get()
        container = self.container.get().strip()
        if runtime == "singularity":
            if not container or not Path(os.path.expanduser(container)).exists():
                messagebox.showerror("Error", "Container .sif/.simg path is required for Singularity."); return None
        else:
            if not container:
                container = "nipreps/fmriprep:latest"

        subs = self._selected_subjects()
        if not subs:
            messagebox.showerror("Error", "No subjects selected or discovered."); return None

        # Ensure dirs
        out.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)

        cfg = dict(
            bids_dir=bids, out_dir=out, work_dir=work,
            runtime=runtime, container=container, fs_license=fs,
            nprocs=int(self.nprocs.get()), omp=int(self.omp.get()), mem_mb=int(self.mem_mb.get()),
            skip_val=bool(self.skip_val.get()), output_spaces=self.output_spaces.get(),
            aroma=bool(self.aroma.get()), cifti=bool(self.cifti.get()), reconall=bool(self.reconall.get()),
            syn_sdc=bool(self.synsdc.get()), extra=self.extra.get(), bind_tf=bool(self.bind_tf.get()),
            subjects=subs
        )

        if for_slurm:
            slurm = dict(
                partition=self.slurm_partition.get().strip() or "compute",
                time=self.slurm_time.get().strip() or "24:00:00",
                mem=self.slurm_mem.get().strip() or mb_to_human(int(self.mem_mb.get())),
                account=self.slurm_account.get().strip(),
                email=self.slurm_email.get().strip(),
                mail_type=self.slurm_mail_type.get().strip(),
                job_name=self.slurm_job_name.get().strip() or "fmriprep",
                module_sing=bool(self.slurm_module_sing.get()),
                script_outdir=Path(self.script_outdir.get()).expanduser()
            )
            return cfg, slurm
        return cfg

    # --- Actions ---

    def preview_commands(self):
        cfg = self._validate_inputs()
        if not cfg:
            return
        cmds = build_fmriprep_cmds(**cfg)
        self.txt.delete("1.0", tk.END)
        for c in cmds:
            self.txt.insert(tk.END, "$ " + " ".join([str(x) for x in c]) + "\n")

    def save_runner(self):
        cfg = self._validate_inputs()
        if not cfg:
            return
        cmds = build_fmriprep_cmds(**cfg)
        if not cmds:
            return
        script_path = filedialog.asksaveasfilename(title="Save run_fmriprep.sh", defaultextension=".sh", initialfile="run_fmriprep.sh")
        if not script_path:
            return
        with open(script_path, "w") as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n\n")
            f.write(f'echo "Running fMRIPrep for {len(cfg["subjects"])} subject(s)"\n')
            for c in cmds:
                f.write(" ".join([str(x) for x in c]) + "\n")
        os.chmod(script_path, 0o755)
        messagebox.showinfo("Saved", f"Saved: {script_path}")

    def generate_slurm(self):
        vals = self._validate_inputs(for_slurm=True)
        if not vals:
            return
        cfg, sl = vals
        outdir = sl["script_outdir"]
        outdir.mkdir(parents=True, exist_ok=True)
        log_dir = outdir / "logs"; log_dir.mkdir(exist_ok=True)
        subj_file = outdir / "subjects.txt"
        subj_file.write_text("\n".join(cfg["subjects"]) + "\n")

        account_line = f"#SBATCH --account={sl['account']}\n" if sl["account"] else ""
        mail_line = ""
        if sl["email"]:
            mail_line = f"#SBATCH --mail-user={sl['email']}\n"
            if sl["mail_type"]:
                mail_line += f"#SBATCH --mail-type={sl['mail_type']}\n"
        module_line = "module load singularity\n" if sl["module_sing"] and cfg["runtime"] == "singularity" else ""

        slurm_text = SLURM_TEMPLATE.format(
            job_name=sl["job_name"],
            partition=sl["partition"],
            time=sl["time"],
            cpus=self.cpus_per_task.get(),
            mem=sl["mem"],
            array_max=max(0, len(cfg["subjects"]) - 1),
            log_dir=str(log_dir),
            account=account_line,
            mail=mail_line,
            module=module_line,
            bids=str(cfg["bids_dir"]),
            out=str(cfg["out_dir"]),
            work=str(cfg["work_dir"]),
            fs_license=str(cfg["fs_license"]),
            subject_file=str(subj_file),
            runtime=cfg["runtime"],
            container=cfg["container"],
            nprocs=cfg["nprocs"],
            omp=cfg["omp"],
            mem_mb=cfg["mem_mb"],
            extra=cfg["extra"],
            skip_val="1" if cfg["skip_val"] else "0",
            output_spaces=cfg["output_spaces"],
            aroma="1" if cfg["aroma"] else "0",
            cifti="1" if cfg["cifti"] else "0",
            reconall="1" if cfg["reconall"] else "0",
            syn_sdc="1" if cfg["syn_sdc"] else "0",
            bind_tf="1" if cfg["bind_tf"] else "0",
        )
        script_path = outdir / "fmriprep_array.sbatch"
        script_path.write_text(slurm_text)
        os.chmod(script_path, 0o755)

        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, f"Wrote: {script_path}\nWrote: {subj_file}\nSubmit with:\n  sbatch {script_path}\n")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
