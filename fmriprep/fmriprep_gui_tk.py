#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fmriprep_gui_tk.py

Tk frontend for the fMRIPrep launcher workflow.

Use this when you want a GUI and Textual is unavailable. The canonical backend
entrypoint remains `fmriprep_launcher.py`.

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

import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from fmriprep_backend import BuildConfig, build_fmriprep_command, create_slurm_script, write_subject_batches
from fmriprep_shared import (
    default_resources_from_env,
    detect_runtime_auto,
    discover_sif_images,
    discover_subjects,
    docker_list_fmriprep_images,
    mb_to_human,
)

def build_fmriprep_cmds(cfg: BuildConfig):
    return [build_fmriprep_command(cfg, sub) for sub in cfg.subjects]

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
            img_values = [str(p) for p in imgs]
            # Choose via a simple selector
            top = tk.Toplevel(self); top.title("Select container")
            lb = tk.Listbox(top, width=80, height=8); lb.pack(fill="both", expand=True, padx=6, pady=6)
            for i in img_values: lb.insert(tk.END, i)
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

        cfg = BuildConfig(
            bids=bids,
            out=out,
            work=work,
            subjects=subs,
            container_runtime=runtime,
            container=container,
            fs_license=fs,
            templateflow_home=Path.home() / ".cache" / "templateflow" if bool(self.bind_tf.get()) else None,
            omp_threads=int(self.omp.get()),
            nprocs=int(self.nprocs.get()),
            mem_mb=int(self.mem_mb.get()),
            extra=self.extra.get(),
            skip_bids_validation=bool(self.skip_val.get()),
            output_spaces=self.output_spaces.get(),
            use_aroma=bool(self.aroma.get()),
            cifti_output=bool(self.cifti.get()),
            fs_reconall=bool(self.reconall.get()),
            use_syn_sdc=bool(self.synsdc.get()),
            bind_templateflow=bool(self.bind_tf.get()),
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
        cmds = build_fmriprep_cmds(cfg)
        self.txt.delete("1.0", tk.END)
        for c in cmds:
            self.txt.insert(tk.END, "$ " + " ".join([str(x) for x in c]) + "\n")

    def save_runner(self):
        cfg = self._validate_inputs()
        if not cfg:
            return
        cmds = build_fmriprep_cmds(cfg)
        if not cmds:
            return
        script_path = filedialog.asksaveasfilename(title="Save run_fmriprep.sh", defaultextension=".sh", initialfile="run_fmriprep.sh")
        if not script_path:
            return
        with open(script_path, "w") as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n\n")
            f.write(f'echo "Running fMRIPrep for {len(cfg.subjects)} subject(s)"\n')
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
        status_dir = outdir / "status"; status_dir.mkdir(exist_ok=True)
        subj_file = outdir / "subjects.txt"
        write_subject_batches(subj_file, cfg.subjects)

        if len(cfg.subjects) == 0:
            messagebox.showerror("Error", "No subjects selected. Cannot generate SLURM script.")
            return

        slurm_text = create_slurm_script(
            cfg=cfg,
            subject_file=subj_file,
            partition=sl["partition"],
            time=sl["time"],
            cpus_per_task=self.cpus_per_task.get(),
            mem=sl["mem"],
            account=sl["account"] or None,
            email=sl["email"] or None,
            mail_type=sl["mail_type"] or None,
            log_dir=log_dir,
            status_dir=status_dir,
            module_singularity=sl["module_sing"],
            job_name=sl["job_name"],
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
