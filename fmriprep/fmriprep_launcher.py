#!/usr/bin/env python3
"""
fmriprep_launcher.py

One-stop tool to build correct fMRIPrep commands and generate a Slurm array
script for a BIDS dataset. Supports Singularity/Apptainer, the fmriprep-docker
wrapper, and plain Docker. Includes an interactive "wizard" and CLI subcommands.

This is the canonical backend and CLI entrypoint for the tools in this
directory. Other UIs should be treated as optional frontends over the same
workflow, not separate primary tools.

For the best wizard experience with tab completion, install questionary:
  pip install --user questionary

Subcommands
-----------
- probe         : Show detected container runtime and available fMRIPrep images
- print-cmd     : Print per-subject fMRIPrep commands (no submission)
- slurm-array   : Generate Slurm array script + subject list
- wizard        : Interactive setup (questionary if available, else basic prompts)

Environment
-----------
- FMRIPREP_SIF_DIR: directory containing one or more *.sif/*.simg fMRIPrep images
- FS_LICENSE       : path to FreeSurfer license file (overrides --fs-license)
- SINGULARITY_BIND : extra bind mounts (comma-separated), if your site uses this
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

from fmriprep_backend import (
    BuildConfig,
    build_fmriprep_command,
    build_config_from_manifest,
    build_job_manifest,
    create_slurm_script,
    failed_subjects_from_status_dir,
    preflight_check,
    resolve_subjects_arg,
    write_subject_batches,
)
from fmriprep_shared import (
    default_resources_from_env,
    detect_runtime,
    discover_sif_images,
    discover_subjects,
    docker_list_fmriprep_images,
    load_config,
    mb_to_human,
    parse_memory_to_mb,
)


# ---------------------------- Argparse CLI ----------------------------

def add_common_args(p: argparse.ArgumentParser, config: Dict[str, str] = None):
    if config is None:
        config = {}
    
    # Helper to show config defaults in help text
    def help_with_default(text, key, fallback=""):
        if key in config:
            return f"{text} [config: {config[key]}]"
        elif fallback:
            return f"{text} [default: {fallback}]"
        return text
    
    p.add_argument("--bids", type=Path, default=config.get("bids"), required=not config.get("bids"), 
                   help=help_with_default("Path to BIDS dataset root", "bids"))
    p.add_argument("--out", type=Path, default=config.get("out"), required=not config.get("out"), 
                   help=help_with_default("Output directory (usually BIDS/derivatives/fmriprep)", "out"))
    p.add_argument("--work", type=Path, default=config.get("work"), required=not config.get("work"), 
                   help=help_with_default("Work directory (scratch)", "work"))
    p.add_argument("--subjects", nargs="+", default=config.get("subjects", "").split() if config.get("subjects") else None, 
                   required=not config.get("subjects"), 
                   help=help_with_default("'all' or a list like sub-01 sub-02 (sub- prefix optional)", "subjects"))
    p.add_argument("--runtime", choices=["auto","singularity","fmriprep-docker","docker"], 
                   default=config.get("runtime", "auto"), 
                   help=help_with_default("Container runtime", "runtime", "auto"))
    p.add_argument("--container", default=config.get("container", "auto"), 
                   help=help_with_default("Path to .sif (Singularity) or image:tag (Docker). If 'auto', try to pick", "container", "auto"))
    p.add_argument("--fs-license", type=Path, default=config.get("fs_license"), 
                   help=help_with_default("Path to FreeSurfer license.txt (or set FS_LICENSE env var)", "fs_license"))
    p.add_argument("--templateflow-home", type=Path, default=config.get("templateflow_home"), 
                   help=help_with_default("Path to TemplateFlow directory (or set TEMPLATEFLOW_HOME env var)", "templateflow_home"))
    p.add_argument("--nprocs", type=int, default=int(config["nprocs"]) if "nprocs" in config else None, 
                   help=help_with_default("--nprocs for fMRIPrep", "nprocs", "auto-detect from system/Slurm"))
    p.add_argument("--omp-threads", type=int, default=int(config["omp_threads"]) if "omp_threads" in config else None, 
                   help=help_with_default("--omp-nthreads", "omp_threads", "min(8, nprocs)"))
    # Parse memory with units support
    default_mem = None
    if "mem_mb" in config:
        try:
            default_mem = parse_memory_to_mb(config["mem_mb"])
        except (ValueError, TypeError) as e:
            print(f"Warning: could not parse mem_mb '{config['mem_mb']}': {e}", file=sys.stderr)
            default_mem = int(config["mem_mb"])
    p.add_argument("--mem-mb", type=parse_memory_to_mb, default=default_mem,
                   help=help_with_default("--mem-mb (supports units: 32G, 760000M)", "mem_mb", "about 90 percent of available"))
    p.add_argument("--skip-bids-validation", action="store_true", 
                   default=config.get("skip_bids_validation", "").lower() == "true", 
                   help=help_with_default("Pass --skip-bids-validation", "skip_bids_validation"))
    p.add_argument("--output-spaces", type=str, default=config.get("output_spaces"), 
                   help=help_with_default('Output spaces e.g. "MNI152NLin2009cAsym:res-2 T1w fsnative"', "output_spaces"))
    p.add_argument("--use-aroma", action="store_true",
                   default=config.get("use_aroma", "").lower() == "true",
                   help=help_with_default("Use ICA-AROMA (DEPRECATED: removed in fMRIPrep >= 23.1.0)", "use_aroma"))
    p.add_argument("--cifti-output", action="store_true", 
                   default=config.get("cifti_output", "").lower() == "true",
                   help=help_with_default("Generate CIFTI outputs", "cifti_output"))
    p.add_argument("--fs-reconall", action="store_true", 
                   default=config.get("fs_reconall", "").lower() == "true", 
                   help=help_with_default("Run FreeSurfer recon-all", "fs_reconall", "off"))
    p.add_argument("--use-syn-sdc", action="store_true", 
                   default=config.get("use_syn_sdc", "").lower() == "true", 
                   help=help_with_default("Enable SyN-based fieldmap-less distortion correction", "use_syn_sdc"))
    p.add_argument("--extra", type=str, default=config.get("extra", ""), 
                   help=help_with_default("Extra flags to append to fMRIPrep (quoted string)", "extra"))

def choose_container(runtime: str, container_arg: str) -> str:
    if container_arg != "auto":
        # For singularity, validate it's a file not a directory
        if runtime == "singularity":
            container_path = Path(container_arg).expanduser()
            if container_path.is_dir():
                # Try to find a .sif/.simg in the directory
                images = discover_sif_images(str(container_path))
                if images:
                    # Return the most recent one
                    latest = sorted(images, key=lambda p: Path(p).stat().st_mtime, reverse=True)[0]
                    return str(latest)
                else:
                    raise RuntimeError(f"No .sif/.simg files found in directory: {container_path}")
            elif not container_path.exists():
                raise RuntimeError(f"Container file does not exist: {container_path}")
        return container_arg
    
    if runtime == "singularity":
        sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
        images = discover_sif_images(sif_dir)
        if images:
            latest = sorted(images, key=lambda p: Path(p).stat().st_mtime, reverse=True)[0]
            return str(latest)
        raise RuntimeError("No fMRIPrep .sif/.simg found. Set FMRIPREP_SIF_DIR or pass --container /path/file.sif")
    elif runtime in ("docker", "fmriprep-docker"):
        imgs = docker_list_fmriprep_images()
        if imgs:
            return imgs[0]
        return "nipreps/fmriprep:latest"
    else:
        raise RuntimeError(f"Unsupported runtime: {runtime}")

def fill_defaults(args):
    bids: Path = args.bids.expanduser().resolve()
    out: Path = args.out.expanduser().resolve()
    work: Path = args.work.expanduser().resolve()

    subjects = resolve_subjects_arg(bids, args.subjects)
    if not subjects:
        raise SystemExit("No subjects detected/selected.")

    runtime = detect_runtime(args.runtime)
    container = choose_container(runtime, args.container)

    fs_license = Path(os.environ.get("FS_LICENSE", "")) if args.fs_license is None else args.fs_license
    if not fs_license or not fs_license.exists():
        raise SystemExit("FreeSurfer license not found. Set FS_LICENSE or pass --fs-license /path/to/license.txt")

    cpus_auto, mem_auto = default_resources_from_env()
    nprocs = args.nprocs or max(1, cpus_auto)
    omp_threads = args.omp_threads or max(1, min(8, nprocs))
    mem_mb = args.mem_mb or mem_auto

    return subjects, runtime, Path(container), fs_license.resolve(), omp_threads, nprocs, mem_mb

# ---------------------------- Commands ----------------------------

def _build_user_config():
    """Build a user-level config template (infrastructure only, no dataset paths)."""
    return [
        "# User-level fMRIPrep defaults",
        "# Generated by: fmriprep_launcher.py init --user",
        "#",
        "# Shared across all projects. Project-level fmriprep.ini files override",
        "# these values. Generate one with: fmriprep_launcher.py init",
        "#",
        "# Lines starting with # are comments. Delete the # to enable a setting.",
        "",
        "[defaults]",
        "# ── Paths ──",
        "# work directory on fast scratch (used by all projects)",
        "# work = /scratch/$USER/fmriprep_work",
        "",
        "# ── Container ──",
        "# 'singularity' works for both Singularity and Apptainer",
        "runtime = singularity",
        "# container = /project/def-piname/shared/bin/fmriprep_24.1.0.sif",
        "",
        "# ── FreeSurfer & TemplateFlow ──",
        "# fs_license = /project/def-piname/shared/bin/license.txt",
        "# templateflow_home = /project/def-piname/shared/opt/templateflow",
        "",
        "# ── Resources (sensible defaults for most clusters) ──",
        "nprocs = 8",
        "omp_threads = 4",
        "mem_mb = 32000",
        "",
        "# ── fMRIPrep options ──",
        "skip_bids_validation = true",
        "# output_spaces = MNI152NLin2009cAsym:res-2 T1w",
        "# fs_reconall = true",
        "# use_syn_sdc = false",
        "# cifti_output = false",
        "",
        "[slurm]",
        "partition = compute",
        "time = 24:00:00",
        "# account = def-piname",
        "# email = user@university.ca",
        "# mail_type = END,FAIL",
        "# no_mem = true  # For clusters that allocate whole nodes (e.g. Trillium)",
        "",
    ]


def _build_project_config(target_dir, global_cfg):
    """Build a project-level config template, pre-filled from global config."""
    bids_default = global_cfg.get("bids", str(target_dir))
    out_default = global_cfg.get("out", str(target_dir / "derivatives" / "fmriprep"))
    work_default = global_cfg.get("work", "")

    def val(key, fallback=""):
        return global_cfg.get(key, fallback)

    lines = [
        "# fmriprep.ini — project-specific configuration",
        "# Generated by: fmriprep_launcher.py init",
        "#",
        "# Place this file in your BIDS dataset directory and run:",
        "#   fmriprep_launcher.py wizard --quick",
        "#",
        "# Values here override user (~/.config/fmriprep/config.ini) and system defaults.",
        "# Lines starting with # are comments. Delete the # to enable a setting.",
        "",
        "[defaults]",
        "# ── Paths ──",
        f"bids = {bids_default}",
        f"out = {out_default}",
    ]
    if work_default:
        lines.append(f"work = {work_default}")
    else:
        lines.append("# work = /scratch/$USER/fmriprep_work")

    lines += [
        "",
        "# ── Container ──",
        "# 'singularity' works for both Singularity and Apptainer",
        f"runtime = {val('runtime', 'singularity')}",
    ]
    if val("container"):
        lines.append(f"container = {val('container')}")
    else:
        lines.append("# container = /path/to/fmriprep_24.x.y.sif")

    lines += [
        "",
        "# ── FreeSurfer & TemplateFlow ──",
    ]
    if val("fs_license"):
        lines.append(f"fs_license = {val('fs_license')}")
    else:
        lines.append("# fs_license = /path/to/license.txt")

    if val("templateflow_home"):
        lines.append(f"templateflow_home = {val('templateflow_home')}")
    else:
        lines.append("# templateflow_home = /project/shared/templateflow")

    lines += [
        "",
        "# ── Resources ──",
        f"nprocs = {val('nprocs', '8')}",
        f"omp_threads = {val('omp_threads', '4')}",
        f"mem_mb = {val('mem_mb', '32000')}",
        "",
        "# ── fMRIPrep options ──",
        f"output_spaces = {val('output_spaces', 'MNI152NLin2009cAsym:res-2 T1w')}",
        f"fs_reconall = {val('fs_reconall', 'true')}",
        f"skip_bids_validation = {val('skip_bids_validation', 'true')}",
        f"use_syn_sdc = {val('use_syn_sdc', 'false')}",
        f"cifti_output = {val('cifti_output', 'false')}",
        "# extra = --stop-on-first-crash",
        "",
        "# ── Subjects ──",
        "# subjects = all",
        "# subjects = sub-01 sub-02 sub-03",
    ]

    # [slurm] section
    lines += [
        "",
        "[slurm]",
        f"partition = {val('slurm_partition', 'compute')}",
        f"time = {val('slurm_time', '24:00:00')}",
    ]
    if val("slurm_account"):
        lines.append(f"account = {val('slurm_account')}")
    else:
        lines.append("# account = def-piname")

    lines.append(f"job_name = {val('slurm_job_name', 'fmriprep')}")

    if val("slurm_log_dir"):
        lines.append(f"log_dir = {val('slurm_log_dir')}")
    else:
        lines.append("# log_dir = /scratch/$USER/fmriprep_logs")

    lines += [
        "# email = user@university.ca",
        "# mail_type = END,FAIL",
        "# no_mem = true  # For clusters that allocate whole nodes (e.g. Trillium)",
        "",
    ]
    return lines


def cmd_init(args):
    """Generate a starter fmriprep config file."""
    if args.user:
        outfile = Path.home() / ".config" / "fmriprep" / "config.ini"
        if outfile.exists() and not args.force:
            print(f"Already exists: {outfile}", file=sys.stderr)
            print("Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text("\n".join(_build_user_config()))
        print(f"Wrote {outfile}")
        print("Edit this file with your cluster paths, then create per-project")
        print("configs with: fmriprep_launcher.py init /path/to/bids_dataset")
    else:
        target_dir = Path(args.dir).expanduser().resolve()
        outfile = target_dir / "fmriprep.ini"
        if outfile.exists() and not args.force:
            print(f"Already exists: {outfile}", file=sys.stderr)
            print("Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)
        global_cfg = load_config()
        target_dir.mkdir(parents=True, exist_ok=True)
        outfile.write_text("\n".join(_build_project_config(target_dir, global_cfg)))
        print(f"Wrote {outfile}")
        if global_cfg:
            sources = []
            for p in [Path.home() / ".config" / "fmriprep" / "config.ini",
                       Path.home() / ".fmriprep.ini",
                       Path("/etc/fmriprep/config.ini")]:
                if p.exists():
                    sources.append(str(p))
            if sources:
                print(f"Pre-filled from: {', '.join(sources)}")
        print("Edit the file, then run: fmriprep_launcher.py wizard --quick")


def cmd_probe(_args):
    print("=== Probe ===")

    # --- Config files ---
    config_search_paths = [
        Path("/etc/fmriprep/config.ini"),
        Path.home() / ".config" / "fmriprep" / "config.ini",
        Path.home() / ".fmriprep.ini",
        Path.cwd() / "fmriprep.ini",
    ]
    found_configs = [p for p in config_search_paths if p.exists()]
    if found_configs:
        print("Config files (in load order):")
        for p in found_configs:
            print(f"  - {p}")
    else:
        print("No config files found")

    cfg = load_config()
    if cfg:
        print("Effective config values:")
        for k, v in sorted(cfg.items()):
            print(f"  {k} = {v}")

    # --- Runtime ---
    try:
        rt = detect_runtime("auto")
        print(f"Runtime: {rt}")
    except Exception as e:
        print(f"Runtime: not found ({e})")

    # --- Container from config ---
    container_cfg = cfg.get("container", "").strip()
    if container_cfg and container_cfg != "auto":
        cp = Path(container_cfg).expanduser()
        if cp.is_file():
            print(f"Container (from config): {cp}")
        elif cp.is_dir():
            imgs = discover_sif_images(str(cp))
            if imgs:
                print(f"Container dir (from config): {cp}")
                for p in imgs:
                    print(f"  - {p.name}")
            else:
                print(f"Container dir (from config): {cp}  [no .sif/.simg found]")
        else:
            print(f"Container (from config): {container_cfg}  [NOT FOUND]")

    # --- FMRIPREP_SIF_DIR ---
    sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
    if sif_dir:
        imgs = discover_sif_images(sif_dir)
        if imgs:
            print(f"SIF images in $FMRIPREP_SIF_DIR ({sif_dir}):")
            for p in imgs:
                print(f"  - {p.name}")
        else:
            print(f"No fMRIPrep images found in $FMRIPREP_SIF_DIR ({sif_dir})")
    elif not container_cfg:
        print("No container configured (set 'container' in config or $FMRIPREP_SIF_DIR)")

    # --- Docker ---
    docker_imgs = docker_list_fmriprep_images()
    if docker_imgs:
        print("Docker images:")
        for i in docker_imgs:
            print(f"  - {i}")
    else:
        print("No local Docker fMRIPrep images found (or Docker not installed).")

def cmd_print(args):
    subjects, runtime, container, fs_license, omp_threads, nprocs, mem_mb = fill_defaults(args)
    # Use resolved paths from fill_defaults
    bids = args.bids.expanduser().resolve()
    out = args.out.expanduser().resolve()
    work = args.work.expanduser().resolve()
    
    cfg = BuildConfig(
        bids=bids, out=out, work=work, subjects=subjects,
        container_runtime=runtime, container=str(container),
        fs_license=fs_license, 
        templateflow_home=args.templateflow_home.expanduser().resolve() if args.templateflow_home else None,
        omp_threads=omp_threads, nprocs=nprocs, mem_mb=mem_mb,
        extra=args.extra, skip_bids_validation=args.skip_bids_validation,
        output_spaces=args.output_spaces, use_aroma=args.use_aroma, cifti_output=args.cifti_output,
        fs_reconall=args.fs_reconall, use_syn_sdc=args.use_syn_sdc
    )
    errors = preflight_check(cfg)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    for sub in subjects:
        cmd = build_fmriprep_command(cfg, sub)
        print("$ " + " ".join([str(c) for c in cmd]))

def cmd_slurm_array(args):
    subjects, runtime, container, fs_license, omp_threads, nprocs, mem_mb = fill_defaults(args)
    # Use resolved paths from fill_defaults
    bids = args.bids.expanduser().resolve()
    out = args.out.expanduser().resolve()
    work = args.work.expanduser().resolve()
    
    # Handle subject batching
    subjects_per_job = max(1, args.subjects_per_job)
    
    # Adjust resources if batching multiple subjects
    # Since we run subjects in parallel with xargs, we need total_resources = per_subject × num_subjects
    if subjects_per_job > 1:
        # Simple multiplication: each subject needs full resources
        adjusted_nprocs = nprocs * subjects_per_job
        adjusted_mem = mem_mb * subjects_per_job
        
        print(f"Batching {subjects_per_job} subjects per job")
        print(f"Total job resources: {adjusted_nprocs} CPUs, {adjusted_mem} MB memory")
        print(f"  ({nprocs} CPUs, {mem_mb} MB per subject)")
    else:
        adjusted_mem = mem_mb
        adjusted_nprocs = nprocs
    
    cfg = BuildConfig(
        bids=bids, out=out, work=work, subjects=subjects,
        container_runtime=runtime, container=str(container),
        fs_license=fs_license,
        templateflow_home=args.templateflow_home.expanduser().resolve() if args.templateflow_home else None,
        omp_threads=omp_threads, nprocs=adjusted_nprocs, mem_mb=adjusted_mem,
        extra=args.extra, skip_bids_validation=args.skip_bids_validation,
        output_spaces=args.output_spaces, use_aroma=args.use_aroma, cifti_output=args.cifti_output,
        fs_reconall=args.fs_reconall, use_syn_sdc=args.use_syn_sdc
    )
    errors = preflight_check(cfg)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    out_dir = args.script_outdir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create subject batches
    subj_file = out_dir / "subjects.txt"
    batches = write_subject_batches(subj_file, subjects, subjects_per_job)
    
    if subjects_per_job > 1:
        print(f"Created {len(batches)} job batches from {len(subjects)} subjects")

    # Handle log directory override
    if args.log_dir:
        log_dir = args.log_dir.expanduser().resolve()
    else:
        log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    status_dir = out_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)

    # Handle memory specification
    if args.no_mem:
        mem_spec = None
    elif args.mem and args.mem.lower() == "none":
        mem_spec = None
    else:
        mem_spec = args.mem or mb_to_human(mem_mb)

    text = create_slurm_script(
        cfg=cfg,
        subject_file=subj_file,
        partition=args.partition,
        time=args.time,
        cpus_per_task=args.cpus_per_task or adjusted_nprocs,
        mem=mem_spec,
        account=args.account,
        email=args.email,
        mail_type=args.mail_type,
        log_dir=log_dir,
        status_dir=status_dir,
        module_singularity=args.module_singularity,
        job_name=args.job_name,
    )
    script_path = out_dir / "fmriprep_array.sbatch"
    script_path.write_text(text)
    os.chmod(script_path, 0o755)
    manifest_path = out_dir / "job_manifest.json"
    manifest = build_job_manifest(
        cfg,
        script_outdir=out_dir,
        subject_file=subj_file,
        status_dir=status_dir,
        log_dir=log_dir,
        partition=args.partition,
        time=args.time,
        cpus_per_task=args.cpus_per_task or adjusted_nprocs,
        mem=mem_spec,
        account=args.account,
        email=args.email,
        mail_type=args.mail_type,
        job_name=args.job_name,
        module_singularity=args.module_singularity,
        subjects_per_job=subjects_per_job,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\nWrote Slurm script: {script_path}")
    print(f"Wrote subject list: {subj_file}")
    print(f"Wrote manifest: {manifest_path}")
    print("\nSubmit with:")
    print(f"  sbatch {script_path}")


def cmd_rerun_failed(args):
    manifest_path = args.manifest.expanduser().resolve()
    manifest = json.loads(manifest_path.read_text())
    status_dir = args.status_dir.expanduser().resolve() if args.status_dir else Path(manifest["job_bundle"]["status_dir"]).expanduser().resolve()
    failed_subjects = failed_subjects_from_status_dir(status_dir)

    if not failed_subjects:
        print(f"No failed subjects found in {status_dir}")
        return

    cfg = build_config_from_manifest(manifest, failed_subjects)
    slurm = manifest["slurm"]
    subjects_per_job = args.subjects_per_job or int(slurm.get("subjects_per_job", 1))
    out_dir = args.script_outdir.expanduser().resolve() if args.script_outdir else manifest_path.parent / "rerun_failed_job"
    out_dir.mkdir(parents=True, exist_ok=True)

    subj_file = out_dir / "subjects.txt"
    batches = write_subject_batches(subj_file, failed_subjects, subjects_per_job)
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    rerun_status_dir = out_dir / "status"
    rerun_status_dir.mkdir(parents=True, exist_ok=True)

    text = create_slurm_script(
        cfg=cfg,
        subject_file=subj_file,
        partition=slurm["partition"],
        time=slurm["time"],
        cpus_per_task=int(slurm["cpus_per_task"]),
        mem=slurm.get("mem"),
        account=slurm.get("account"),
        email=slurm.get("email"),
        mail_type=slurm.get("mail_type"),
        log_dir=log_dir,
        status_dir=rerun_status_dir,
        module_singularity=bool(slurm.get("module_singularity", False)),
        job_name=args.job_name or f'{slurm["job_name"]}_rerun',
    )
    script_path = out_dir / "fmriprep_array.sbatch"
    script_path.write_text(text)
    os.chmod(script_path, 0o755)

    rerun_manifest = build_job_manifest(
        cfg,
        script_outdir=out_dir,
        subject_file=subj_file,
        status_dir=rerun_status_dir,
        log_dir=log_dir,
        partition=slurm["partition"],
        time=slurm["time"],
        cpus_per_task=int(slurm["cpus_per_task"]),
        mem=slurm.get("mem"),
        account=slurm.get("account"),
        email=slurm.get("email"),
        mail_type=slurm.get("mail_type"),
        job_name=args.job_name or f'{slurm["job_name"]}_rerun',
        module_singularity=bool(slurm.get("module_singularity", False)),
        subjects_per_job=subjects_per_job,
    )
    rerun_manifest_path = out_dir / "job_manifest.json"
    rerun_manifest_path.write_text(json.dumps(rerun_manifest, indent=2) + "\n")

    print(f"Found {len(failed_subjects)} failed subject(s) in {status_dir}")
    print(f"Created {len(batches)} rerun batch(es)")
    print(f"Wrote Slurm script: {script_path}")
    print(f"Wrote subject list: {subj_file}")
    print(f"Wrote manifest: {rerun_manifest_path}")
    print("\nSubmit with:")
    print(f"  sbatch {script_path}")

def _validate_templateflow(tf_path: Path):
    """Warn if TemplateFlow directory looks empty or missing key templates."""
    if not tf_path.exists():
        print(f"\n⚠ TemplateFlow directory does not exist yet: {tf_path}")
        print("  It will be created, but compute nodes without internet cannot download templates.")
        print("  Pre-populate on a login node with:")
        print(f"    python -c \"import templateflow.api as tfa; tfa.get('MNI152NLin2009cAsym')\"")
        print(f"  Or copy an existing TemplateFlow cache to: {tf_path}\n")
        return
    # Check for at least one template directory
    subdirs = [p for p in tf_path.iterdir() if p.is_dir() and p.name.startswith("tpl-")]
    if not subdirs:
        print(f"\n⚠ TemplateFlow directory exists but contains no templates: {tf_path}")
        print("  fMRIPrep will fail on air-gapped compute nodes without cached templates.")
        print("  Pre-populate on a login node with:")
        print(f"    python -c \"import templateflow.api as tfa; tfa.get('MNI152NLin2009cAsym')\"")
        print(f"  Or copy an existing TemplateFlow cache to: {tf_path}\n")
    else:
        print(f"✓ TemplateFlow: {len(subdirs)} template(s) found in {tf_path}")


# -------------------- Review wizard helpers --------------------

def _format_subjects(subjects, all_subjects):
    """Compact subject display string."""
    if not subjects:
        return "(none detected)"
    if subjects == all_subjects:
        return f"all ({len(subjects)} subjects)"
    if len(subjects) <= 4:
        return f"{', '.join(subjects)} ({len(subjects)} of {len(all_subjects)})"
    return f"{subjects[0]}, ..., {subjects[-1]} ({len(subjects)} of {len(all_subjects)})"


def _print_review_table(fields):
    """Print numbered summary table with section headers."""
    groups = {0: "Paths", 4: "Container & Environment", 8: "Resources",
              11: "fMRIPrep Flags", 17: "SLURM Settings"}
    w = 70
    print(f"\n{'=' * w}")
    print("  fMRIPrep Configuration Review")
    print(f"{'=' * w}")
    for i, (key, label, value, ftype, _) in enumerate(fields):
        if i in groups:
            print(f"\n  --- {groups[i]} ---")
        marker = " "
        if ftype in ('dir', 'file') and value and not Path(value).expanduser().exists():
            marker = "!"
        if key in ('bids', 'container', 'fs_license') and not value:
            marker = "!"
        if key == 'subjects' and '(none' in value:
            marker = "!"
        # truncate long paths for display
        if len(value) > 48:
            display = "..." + value[-(48-3):]
        else:
            display = value
        print(f"  {marker}{i+1:>2}. {label:<24s} {display}")
    print(f"\n{'-' * w}")


def cmd_wizard_review(args, config):
    """Review & Go wizard: auto-detect everything, show summary, edit by number."""

    # --- Phase 1: Resolve all defaults silently ---

    # BIDS directory
    bids_str = config.get('bids', '')
    if bids_str:
        bids = Path(bids_str).expanduser().resolve()
    else:
        bids = Path.cwd()
    # If CWD doesn't look like BIDS, prompt once
    if not bids.is_dir() or not any(p.name.startswith('sub-') for p in bids.iterdir() if p.is_dir()):
        raw = input(f"BIDS directory [{bids}]: ").strip()
        if raw:
            bids = Path(raw).expanduser().resolve()

    out = Path(config.get('out', str(bids / "derivatives" / "fmriprep"))).expanduser().resolve()
    work = Path(config.get('work', str(bids / "work_fmriprep"))).expanduser().resolve()

    # Subjects
    all_subjects = discover_subjects(bids) if bids.is_dir() else []
    cfg_subs = config.get('subjects', '').strip()
    if cfg_subs and cfg_subs.lower() != 'all':
        try:
            subjects = resolve_subjects_arg(bids, cfg_subs.split())
        except Exception:
            subjects = all_subjects
    else:
        subjects = all_subjects

    # Runtime + container
    runtime_cfg = config.get('runtime', 'auto')
    try:
        runtime = detect_runtime(runtime_cfg)
    except RuntimeError:
        runtime = 'singularity'

    container_cfg = config.get('container', 'auto')
    container = ''
    if container_cfg and container_cfg != 'auto':
        cp = Path(container_cfg).expanduser()
        if cp.is_file():
            container = str(cp)
        elif cp.is_dir():
            imgs = discover_sif_images(str(cp))
            container = str(sorted(imgs, key=lambda p: p.stat().st_mtime, reverse=True)[0]) if imgs else ''
    if not container:
        try:
            container = choose_container(runtime, 'auto')
        except RuntimeError:
            container = ''

    # FreeSurfer license
    fs_str = config.get('fs_license', os.environ.get('FS_LICENSE', ''))
    fs_license = str(Path(fs_str).expanduser()) if fs_str else ''

    # TemplateFlow
    tf_str = config.get('templateflow_home',
                        os.environ.get('TEMPLATEFLOW_HOME',
                                       str(Path.home() / ".cache" / "templateflow")))
    templateflow_home = str(Path(tf_str).expanduser())

    # Resources
    cpus_auto, mem_auto = default_resources_from_env()
    nprocs = int(config.get('nprocs', str(cpus_auto)))
    omp_threads = int(config.get('omp_threads', str(min(8, nprocs))))
    mem_mb = parse_memory_to_mb(config['mem_mb']) if 'mem_mb' in config else mem_auto

    # fMRIPrep flags
    output_spaces = config.get('output_spaces', 'MNI152NLin2009cAsym:res-2 T1w')
    skip_bids = config.get('skip_bids_validation', 'true').lower() == 'true'
    cifti_output = config.get('cifti_output', 'false').lower() == 'true'
    fs_reconall = config.get('fs_reconall', 'true').lower() == 'true'
    use_syn_sdc = config.get('use_syn_sdc', 'false').lower() == 'true'
    extra = config.get('extra', '')

    # SLURM
    partition = config.get('slurm_partition', 'compute')
    time_limit = config.get('slurm_time', '24:00:00')
    account = config.get('slurm_account', '')
    job_name = config.get('slurm_job_name', 'fmriprep')
    email = config.get('slurm_email', '')
    mail_type = config.get('slurm_mail_type', '')
    no_mem = config.get('slurm_no_mem', config.get('no_mem', 'false')).lower().startswith('true')
    log_dir = config.get('slurm_log_dir', '')

    # --- Phase 2: Build mutable field table ---
    # (key, label, value, type, choices)
    fields = [
        # Paths 0-3
        ('bids',              'BIDS directory',        str(bids),                  'dir',      None),
        ('out',               'Output directory',      str(out),                   'dir',      None),
        ('work',              'Work directory',         str(work),                  'dir',      None),
        ('subjects',          'Subjects',              _format_subjects(subjects, all_subjects), 'subjects', None),
        # Container 4-7
        ('runtime',           'Container runtime',     runtime,                    'choice',   ['singularity','docker','fmriprep-docker']),
        ('container',         'Container image',       container,                  'file',     None),
        ('fs_license',        'FS license',            fs_license,                 'file',     None),
        ('templateflow_home', 'TemplateFlow dir',      templateflow_home,          'dir',      None),
        # Resources 8-10
        ('nprocs',            'nprocs',                str(nprocs),                'int',      None),
        ('omp_threads',       'omp-nthreads',          str(omp_threads),           'int',      None),
        ('mem_mb',            'mem-mb',                str(mem_mb),                'int',      None),
        # Flags 11-16
        ('output_spaces',     'Output spaces',         output_spaces,              'str',      None),
        ('skip_bids',         'Skip BIDS validation',  str(skip_bids).lower(),     'bool',     None),
        ('cifti_output',      'CIFTI output 91k',      str(cifti_output).lower(),  'bool',     None),
        ('fs_reconall',       'FreeSurfer recon-all',   str(fs_reconall).lower(),   'bool',     None),
        ('use_syn_sdc',       'SyN SDC',               str(use_syn_sdc).lower(),   'bool',     None),
        ('extra',             'Extra flags',            extra,                      'str',      None),
        # SLURM 17-24
        ('partition',         'SLURM partition',       partition,                  'str',      None),
        ('time_limit',        'SLURM walltime',        time_limit,                 'str',      None),
        ('account',           'SLURM account',         account,                    'str',      None),
        ('job_name',          'SLURM job name',        job_name,                   'str',      None),
        ('email',             'Notification email',    email,                      'str',      None),
        ('mail_type',         'Mail type',             mail_type,                  'str',      None),
        ('no_mem',            'Omit SLURM --mem',      str(no_mem).lower(),        'bool',     None),
        ('log_dir',           'Log directory',         log_dir,                    'dir',      None),
    ]

    def fval(key):
        for k, _, v, _, _ in fields:
            if k == key:
                return v
        return ''

    def fset(key, new_val):
        for i, (k, label, _, ftype, choices) in enumerate(fields):
            if k == key:
                fields[i] = (k, label, new_val, ftype, choices)
                return

    # --- Phase 3: Display + edit loop ---
    while True:
        _print_review_table(fields)

        # Flag critical missing values
        missing = []
        for i, (key, label, value, ftype, _) in enumerate(fields):
            if key == 'bids' and (not value or not Path(value).expanduser().is_dir()):
                missing.append(f"  {i+1}. {label}")
            elif key == 'container' and not value:
                missing.append(f"  {i+1}. {label}")
            elif key == 'fs_license' and (not value or not Path(value).expanduser().exists()):
                missing.append(f"  {i+1}. {label}")
            elif key == 'subjects' and '(none' in value:
                missing.append(f"  {i+1}. {label}")
        if missing:
            print("  [!] Needs attention:")
            for m in missing:
                print(f"      {m}")

        raw = input("\n  Edit field numbers (e.g. '5 9'), or Enter to proceed: ").strip()
        if not raw:
            break

        try:
            nums = [int(x) for x in raw.split()]
        except ValueError:
            print("  Enter field numbers separated by spaces.")
            continue

        for num in nums:
            if num < 1 or num > len(fields):
                print(f"  {num} is out of range (1-{len(fields)}).")
                continue
            idx = num - 1
            key, label, old_val, ftype, choices = fields[idx]

            if ftype == 'bool':
                new_val = 'false' if old_val == 'true' else 'true'
                print(f"  {label}: {old_val} -> {new_val}")
            elif ftype == 'choice':
                print(f"  {label}:")
                for ci, c in enumerate(choices, 1):
                    star = " *" if c == old_val else ""
                    print(f"    {ci}. {c}{star}")
                ch = input(f"  Choice (1-{len(choices)}) [{old_val}]: ").strip()
                if ch.isdigit() and 1 <= int(ch) <= len(choices):
                    new_val = choices[int(ch) - 1]
                else:
                    new_val = old_val
            elif ftype == 'dir':
                new_val = input(f"  {label} [{old_val}]: ").strip() or old_val
            elif ftype == 'file':
                new_val = input(f"  {label} [{old_val}]: ").strip() or old_val
                p = Path(new_val).expanduser()
                if p.is_dir():
                    imgs = discover_sif_images(str(p))
                    if imgs:
                        print(f"  Found {len(imgs)} image(s):")
                        for ci, img in enumerate(imgs, 1):
                            print(f"    {ci}. {img.name}")
                        ch = input(f"  Pick (1-{len(imgs)}): ").strip()
                        if ch.isdigit() and 1 <= int(ch) <= len(imgs):
                            new_val = str(imgs[int(ch) - 1])
                elif not p.exists():
                    print(f"  Warning: {new_val} does not exist")
            elif ftype == 'int':
                v = input(f"  {label} [{old_val}]: ").strip() or old_val
                try:
                    new_val = str(int(v))
                except ValueError:
                    print(f"  Invalid integer, keeping {old_val}")
                    new_val = old_val
            elif ftype == 'subjects':
                print(f"  Available: {len(all_subjects)} subjects")
                print("  Enter: 'all', space-separated sub-IDs, or range '1-10'")
                v = input("  Subjects [all]: ").strip() or "all"
                if v.lower() == 'all':
                    subjects = all_subjects
                elif '-' in v and not v.startswith('sub-'):
                    try:
                        start, end = v.split('-', 1)
                        subjects = all_subjects[int(start)-1:int(end)]
                    except (ValueError, IndexError):
                        print("  Invalid range, keeping all.")
                        subjects = all_subjects
                else:
                    sel = []
                    for tok in v.split():
                        if tok.isdigit():
                            idx2 = int(tok) - 1
                            if 0 <= idx2 < len(all_subjects):
                                sel.append(all_subjects[idx2])
                        else:
                            t = tok if tok.startswith('sub-') else f'sub-{tok}'
                            if t in all_subjects:
                                sel.append(t)
                    subjects = sel if sel else all_subjects
                new_val = _format_subjects(subjects, all_subjects)
            else:  # str
                new_val = input(f"  {label} [{old_val}]: ").strip() or old_val

            fields[idx] = (key, label, new_val, ftype, choices)

            # Cascade: bids change -> re-discover subjects
            if key == 'bids':
                new_bids = Path(new_val).expanduser().resolve()
                if new_bids.is_dir():
                    all_subjects = discover_subjects(new_bids)
                    subjects = all_subjects
                    fset('subjects', _format_subjects(subjects, all_subjects))
                    # update default out
                    fset('out', str(new_bids / "derivatives" / "fmriprep"))

    # --- Phase 4: Build config, preview, generate ---
    final_bids = Path(fval('bids')).expanduser().resolve()
    final_out = Path(fval('out')).expanduser().resolve()
    final_work = Path(fval('work')).expanduser().resolve()
    final_fs = Path(fval('fs_license')).expanduser().resolve() if fval('fs_license') else Path('')
    final_tf = Path(fval('templateflow_home')).expanduser() if fval('templateflow_home') else None

    if not subjects:
        print("Error: no subjects selected.", file=sys.stderr)
        sys.exit(1)

    cfg = BuildConfig(
        bids=final_bids, out=final_out, work=final_work,
        subjects=subjects,
        container_runtime=fval('runtime'),
        container=fval('container'),
        fs_license=final_fs,
        templateflow_home=final_tf,
        omp_threads=int(fval('omp_threads')),
        nprocs=int(fval('nprocs')),
        mem_mb=int(fval('mem_mb')),
        extra=fval('extra'),
        skip_bids_validation=fval('skip_bids') == 'true',
        output_spaces=fval('output_spaces') or None,
        use_aroma=False,
        cifti_output=fval('cifti_output') == 'true',
        fs_reconall=fval('fs_reconall') == 'true',
        use_syn_sdc=fval('use_syn_sdc') == 'true',
    )

    errors = preflight_check(cfg)
    if errors:
        print("\nPreflight issues:")
        for e in errors:
            print(f"  - {e}")
        if input("Continue anyway? (y/N): ").strip().lower() != 'y':
            sys.exit(1)

    if final_tf and final_tf.exists():
        _validate_templateflow(final_tf)

    # Preview
    preview_cmd = build_fmriprep_command(cfg, subjects[0])
    print(f"\nExample command ({subjects[0]}):")
    print(f"$ {' '.join(str(c) for c in preview_cmd)}")

    # SLURM generation
    gen = input("\nGenerate SLURM array script? (Y/n): ").strip().lower()
    if gen in ('', 'y', 'yes'):
        outdir = Path(config.get('slurm_script_outdir', str(Path.cwd() / "fmriprep_job"))).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)
        final_out.mkdir(parents=True, exist_ok=True)
        final_work.mkdir(parents=True, exist_ok=True)

        subj_file = outdir / "subjects.txt"
        write_subject_batches(subj_file, subjects)

        slurm_log = Path(fval('log_dir')).expanduser() if fval('log_dir') else outdir / "logs"
        slurm_log.mkdir(parents=True, exist_ok=True)

        status_dir = outdir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)

        cpus_per_task = int(fval('nprocs'))
        omit_mem = fval('no_mem') == 'true'
        mem = None if omit_mem else mb_to_human(int(fval('mem_mb')))
        module_sing = fval('runtime') == 'singularity'

        script_text = create_slurm_script(
            cfg=cfg, subject_file=subj_file,
            partition=fval('partition'), time=fval('time_limit'),
            cpus_per_task=cpus_per_task, mem=mem,
            account=fval('account') or None, email=fval('email') or None,
            mail_type=fval('mail_type') or None,
            log_dir=slurm_log, status_dir=status_dir,
            module_singularity=module_sing, job_name=fval('job_name'),
        )
        script_path = outdir / "fmriprep_array.sbatch"
        script_path.write_text(script_text)
        os.chmod(script_path, 0o755)

        manifest = build_job_manifest(
            cfg, script_outdir=outdir, subject_file=subj_file,
            status_dir=status_dir, log_dir=slurm_log,
            partition=fval('partition'), time=fval('time_limit'),
            cpus_per_task=cpus_per_task, mem=mem,
            account=fval('account') or None, email=fval('email') or None,
            mail_type=fval('mail_type') or None,
            job_name=fval('job_name'), module_singularity=module_sing,
            subjects_per_job=1,
        )
        manifest_path = outdir / "job_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        print(f"\nWrote SLURM script:  {script_path}")
        print(f"Wrote subject list:  {subj_file}")
        print(f"Wrote manifest:      {manifest_path}")
        print(f"\nSubmit with:\n  sbatch {script_path}")

    print("\nDone!")


def cmd_wizard_quick(args, config):
    """Express wizard: only ask essentials, derive everything else from config/env."""

    # Minimal imports for interactive prompts
    try:
        import questionary
    except ImportError:
        questionary = None

    def ask(prompt, default=None, choices=None, path=False):
        if questionary:
            if choices:
                return questionary.select(prompt, choices=choices).ask()
            if path:
                return questionary.path(prompt, default=default).ask()
            return questionary.text(prompt, default=default).ask()
        else:
            if choices:
                for i, c in enumerate(choices, 1):
                    print(f"  {i}. {c}")
                val = input(f"Enter choice (1-{len(choices)}) [{default or ''}]: ").strip()
                if val.isdigit() and 1 <= int(val) <= len(choices):
                    return choices[int(val) - 1]
                return default or choices[0]
            val = input(f"{prompt} [{default or ''}]: ").strip()
            return val or default

    print("=" * 60)
    print("fMRIPrep Express Setup")
    print("Uses config file defaults for most settings.")
    print("Run 'wizard' (without --quick) for full control.")
    print("=" * 60 + "\n")

    # 1. BIDS path
    default_bids = config.get('bids', str(Path.cwd()))
    bids = Path(ask("BIDS dataset path", default=default_bids, path=True)).expanduser()
    while not bids.exists():
        print("Path does not exist.")
        bids = Path(ask("BIDS dataset path", default=str(Path.cwd()), path=True)).expanduser()

    # 2. Subjects
    subs = discover_subjects(bids)
    if not subs:
        print("No subjects found in BIDS directory. Exiting.")
        return
    print(f"Found {len(subs)} subjects.")
    selection = ask("Which subjects?", choices=["all"] + (["select"] if len(subs) > 1 else []))
    if selection == "select":
        for i, s in enumerate(subs, 1):
            print(f"  {i}. {s}")
        sel_input = input("Enter numbers separated by spaces (e.g., '1 3 5'), or range '1-10': ").strip()
        if '-' in sel_input and not sel_input.startswith('sub-'):
            try:
                start, end = sel_input.split('-')
                selected_subjects = subs[int(start)-1:int(end)]
            except (ValueError, IndexError):
                print("Invalid range, using all.")
                selected_subjects = subs
        else:
            selected_subjects = []
            for n in sel_input.split():
                try:
                    selected_subjects.append(subs[int(n)-1])
                except (ValueError, IndexError):
                    pass
            if not selected_subjects:
                selected_subjects = subs
    else:
        selected_subjects = subs

    print(f"Selected {len(selected_subjects)} subjects.")

    # 3. Resolve runtime + container (from config, ask only if missing)
    runtime = config.get('runtime', 'auto')
    if runtime == 'auto':
        try:
            runtime = detect_runtime("auto")
            print(f"Auto-detected runtime: {runtime}")
        except (FileNotFoundError, RuntimeError, OSError) as e:
            print(f"Runtime auto-detection failed: {e}", file=sys.stderr)
            runtime = ask("Runtime?", choices=["singularity", "fmriprep-docker", "docker"])

    container = config.get('container', 'auto')
    if container == 'auto' or not container:
        if runtime == "singularity":
            sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
            images = discover_sif_images(sif_dir)
            if images:
                container = str(images[0]) if len(images) == 1 else ask("Choose container", choices=[str(p) for p in images])
            else:
                container = ask("Path to fMRIPrep .sif/.simg", path=True)
        else:
            imgs = docker_list_fmriprep_images()
            container = imgs[0] if imgs else ask("Docker image:tag", default="nipreps/fmriprep:latest")
    else:
        container_path = Path(container).expanduser()
        if container_path.is_dir():
            dir_images = discover_sif_images(str(container_path))
            if dir_images:
                container = str(dir_images[0]) if len(dir_images) == 1 else ask("Choose container", choices=[str(p) for p in dir_images])
        print(f"Using container: {container}")

    # 4. FS license (from config/env, ask only if missing)
    fs_license_str = config.get('fs_license', os.environ.get("FS_LICENSE", ""))
    if not fs_license_str or not Path(fs_license_str).expanduser().exists():
        fs_license_str = ask("Path to FreeSurfer license.txt", default=fs_license_str or str(Path.home() / "license.txt"), path=True)
    fs_license = Path(fs_license_str).expanduser()
    print(f"Using FS license: {fs_license}")

    # 5. TemplateFlow (from config/env, validate)
    tf_str = config.get('templateflow_home',
                        os.environ.get("TEMPLATEFLOW_HOME",
                                      str(Path.home() / ".cache" / "templateflow")))
    templateflow_home = Path(tf_str).expanduser()
    templateflow_home.mkdir(parents=True, exist_ok=True)
    _validate_templateflow(templateflow_home)

    # 6. Derive all other settings from config
    cpus_auto, mem_auto = default_resources_from_env()
    nprocs = int(config.get('nprocs', str(cpus_auto)))
    omp_threads = int(config.get('omp_threads', str(min(8, nprocs))))
    mem_mb = int(config.get('mem_mb', str(mem_auto)))
    output_spaces = config.get('output_spaces', "MNI152NLin2009cAsym:res-2 T1w")
    skip_bids_validation = config.get('skip_bids_validation', 'true').lower() == 'true'
    use_aroma = config.get('use_aroma', 'false').lower() == 'true'
    cifti_output = config.get('cifti_output', 'false').lower() == 'true'
    fs_reconall = config.get('fs_reconall', 'true').lower() == 'true'
    use_syn_sdc = config.get('use_syn_sdc', 'false').lower() == 'true'
    extra = config.get('extra', '')

    cfg = BuildConfig(
        bids=bids, out=Path(config.get('out', str(bids / "derivatives" / "fmriprep"))),
        work=Path(config.get('work', str(bids / "work_fmriprep"))),
        subjects=selected_subjects,
        container_runtime=runtime, container=container,
        fs_license=fs_license, templateflow_home=templateflow_home,
        omp_threads=omp_threads, nprocs=nprocs, mem_mb=mem_mb,
        extra=extra, skip_bids_validation=skip_bids_validation,
        output_spaces=output_spaces or None,
        use_aroma=use_aroma, cifti_output=cifti_output,
        fs_reconall=fs_reconall, use_syn_sdc=use_syn_sdc
    )

    # Create output dirs
    cfg.out.mkdir(parents=True, exist_ok=True)
    cfg.work.mkdir(parents=True, exist_ok=True)

    # Preview
    preview_cmd = build_fmriprep_command(cfg, selected_subjects[0])
    print(f"\nExample command:\n$ {' '.join(preview_cmd)}")

    # Generate SLURM script
    gen = ask("Generate SLURM array script?", choices=["y", "n"])
    if gen == "y":
        outdir = Path(config.get('slurm_script_outdir', str(Path.cwd() / "fmriprep_job"))).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)

        subj_file = outdir / "subjects.txt"
        write_subject_batches(subj_file, selected_subjects)

        partition = config.get('slurm_partition', os.environ.get("SLURM_JOB_PARTITION", "compute"))
        time = config.get('slurm_time', "24:00:00")
        cpus_per_task = int(config.get('slurm_cpus_per_task', str(nprocs)))
        account = config.get('slurm_account') or None
        email = config.get('slurm_email') or None
        mail_type = config.get('slurm_mail_type') or None
        job_name = config.get('slurm_job_name', "fmriprep")
        no_mem = config.get('slurm_no_mem', config.get('no_mem', 'false')).lower() == 'true'
        log_dir = Path(config.get('slurm_log_dir', str(outdir / "logs"))).expanduser()
        mem = None if no_mem else config.get('slurm_mem', mb_to_human(mem_mb))
        module_sing = runtime == "singularity"

        status_dir = outdir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)

        script_text = create_slurm_script(
            cfg=cfg, subject_file=subj_file, partition=partition, time=time,
            cpus_per_task=cpus_per_task, mem=mem, account=account, email=email,
            mail_type=mail_type, log_dir=log_dir, status_dir=status_dir,
            module_singularity=module_sing, job_name=job_name
        )
        script_path = outdir / "fmriprep_array.sbatch"
        log_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text)
        os.chmod(script_path, 0o755)
        print(f"\nWrote SLURM script: {script_path}")
        print(f"Wrote subject list: {subj_file}")
        print(f"\nSubmit with:\n  sbatch {script_path}")
    print("\nDone!")


def cmd_wizard(args):
    # Load config for defaults
    config = load_config([args.config] if hasattr(args, 'config') and args.config else [])

    # Quick mode: express wizard with minimal questions
    if getattr(args, 'quick', False):
        return cmd_wizard_quick(args, config)

    # Default: review mode (unless --classic explicitly requested)
    if not getattr(args, 'classic', False):
        return cmd_wizard_review(args, config)

    # Optional interactive flow; Questionary if available, else text input.
    try:
        import questionary
    except ImportError:
        questionary = None
        print("=" * 60)
        print("📦 'questionary' package not found!")
        print("This provides a better interface with tab completion.")
        print("\nTo install it:")
        
        # Check which package managers are available
        import subprocess
        import sys
        from shutil import which
        
        install_methods = []
        if which("pip") or which("pip3"):
            install_methods.append("  pip install --user questionary")
        if which("conda"):
            install_methods.append("  conda install -c conda-forge questionary")
        if which("mamba"):
            install_methods.append("  mamba install -c conda-forge questionary")
        
        # Check if we're on Compute Canada / Digital Research Alliance
        if "/cvmfs/" in sys.executable or "computecanada" in sys.executable.lower():
            print("\n🍁 Detected Compute Canada/Alliance environment:")
            print("  1. Load Python module: module load python/3.x")
            print("  2. Create virtual env: python -m venv ~/myenv")
            print("  3. Activate it: source ~/myenv/bin/activate")
            print("  4. Install: pip install questionary")
            print("\n  OR use conda:")
            print("  1. module load conda (or miniconda)")
            print("  2. conda create -n fmriprep python=3.9")
            print("  3. conda activate fmriprep")
            print("  4. conda install -c conda-forge questionary")
        elif install_methods:
            print("\nAvailable installation methods:")
            for method in install_methods:
                print(method)
        else:
            print("\n⚠️  No package manager found (pip/conda/mamba)")
            print("Please install Python packages according to your")
            print("system's documentation.")
        
        # Only try auto-install if pip is actually available
        if which("pip") or which("pip3"):
            print("\nTrying automatic installation...")
            print("=" * 60)
            try:
                pip_cmd = "pip3" if which("pip3") else "pip"
                subprocess.check_call([pip_cmd, "install", "--user", "questionary"], 
                                    stderr=subprocess.DEVNULL)
                print("✅ Successfully installed questionary!")
                print("Please restart the wizard to use the improved interface.")
                sys.exit(0)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("\n⚠️  Automatic installation failed.")
        
        print("\nContinuing with basic interface (no tab completion)...")
        print("=" * 60 + "\n")
        questionary = None

    def ask(prompt, default=None, validate=None, choices=None, path=False):
        if questionary:
            if choices:
                return questionary.select(prompt, choices=choices).ask()
            if path:
                return questionary.path(prompt, default=default).ask()
            if validate:
                return questionary.text(prompt, default=default, validate=validate).ask()
            return questionary.text(prompt, default=default).ask()
        else:
            # Without questionary, provide basic choice display and input
            if choices:
                print(f"\n{prompt}")
                for i, choice in enumerate(choices, 1):
                    print(f"  {i}. {choice}")
                while True:
                    val = input(f"Enter choice number (1-{len(choices)}) [{default if default else ''}]: ").strip()
                    if not val and default:
                        return default
                    try:
                        idx = int(val) - 1
                        if 0 <= idx < len(choices):
                            return choices[idx]
                    except (ValueError, IndexError):
                        pass
                    print(f"Invalid choice. Please enter a number between 1 and {len(choices)}")
            else:
                val = input(f"{prompt} [{default if default else ''}]: ").strip()
                return val or default

    # BIDS
    default_bids = config.get('bids', str(Path.cwd()))
    bids = Path(ask("BIDS dataset path", default=default_bids, path=True)).expanduser()
    while not bids.exists():
        print("Path does not exist.")
        bids = Path(ask("BIDS dataset path", default=str(Path.cwd()), path=True)).expanduser()

    # OUT/WORK
    default_out = config.get('out', str(bids / "derivatives" / "fmriprep"))
    default_work = config.get('work', str(bids / "work_fmriprep"))
    out = Path(ask("Output dir (derivatives/fmriprep)", default=default_out, path=True)).expanduser()
    work = Path(ask("Work dir (scratch)", default=default_work, path=True)).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    # Subjects
    subs = discover_subjects(bids)
    if not subs:
        print("No subjects found in BIDS. Exiting.")
        return
    
    # Ask for subject selection method
    selection_method = ask("How would you like to select subjects?", 
                          choices=["all", "single", "multiple", "range"])
    
    if selection_method == "all":
        subjects = ["all"]
    elif selection_method == "single":
        sel = ask("Select a subject", choices=subs)
        subjects = [sel]
    elif selection_method == "multiple":
        print("\nAvailable subjects:")
        for i, sub in enumerate(subs, 1):
            print(f"  {i}. {sub}")
        selected_nums = input("Enter subject numbers separated by spaces (e.g., '1 3 5'): ").strip()
        subjects = []
        for num_str in selected_nums.split():
            try:
                idx = int(num_str) - 1
                if 0 <= idx < len(subs):
                    subjects.append(subs[idx])
            except (ValueError, IndexError):
                print(f"Skipping invalid selection: {num_str}")
        if not subjects:
            print("No valid subjects selected, using all")
            subjects = ["all"]
    else:  # range
        print("\nAvailable subjects:")
        for i, sub in enumerate(subs, 1):
            print(f"  {i}. {sub}")
        range_input = input("Enter range (e.g., '1-5' or '3-10'): ").strip()
        try:
            start_str, end_str = range_input.split('-')
            start = int(start_str) - 1
            end = int(end_str)
            subjects = subs[start:end]
            if not subjects:
                print("Invalid range, using all")
                subjects = ["all"]
        except (ValueError, IndexError):
            print("Invalid range format, using all")
            subjects = ["all"]

    # Runtime detection/choice
    # First check config, then auto-detect if not specified
    runtime = config.get('runtime', 'auto')
    if runtime == 'auto':
        try:
            runtime = detect_runtime("auto")
        except Exception as e:
            print(f"Runtime detection failed: {e}")
            runtime = ask("Pick a runtime", choices=["singularity", "fmriprep-docker", "docker"])

    # Container selection
    container = config.get('container', 'auto')
    
    if runtime == "singularity":
        if container != 'auto':
            # Container specified in config - check if it's a directory
            container_path = Path(container).expanduser()
            if container_path.is_dir():
                # Scan directory for .sif/.simg files
                dir_images = discover_sif_images(str(container_path))
                if dir_images:
                    # If only one image, use it; otherwise ask
                    if len(dir_images) == 1:
                        container = str(dir_images[0])
                        print(f"Using container from config: {container}")
                    else:
                        container = ask("Multiple images found in config directory. Choose one:", choices=[str(p) for p in dir_images])
                else:
                    print(f"No .sif/.simg files found in config directory: {container_path}")
                    container = ask("Enter full path to fMRIPrep .sif/.simg file", default=str(Path.cwd()), path=True)
            else:
                # Use the file path directly
                print(f"Using container from config: {container}")
        else:
            # Auto mode - look for containers
            sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
            images = discover_sif_images(sif_dir)
            if images:
                container = ask("Choose fMRIPrep .sif/.simg", choices=[str(p) for p in images])
            else:
                # Ask for path - could be file or directory
                path_input = ask("No .sif found. Enter path to fMRIPrep .sif/.simg or directory containing them", default=str(Path.cwd()), path=True)
                path_obj = Path(path_input).expanduser()
                
                # If it's a directory, scan for .sif/.simg files
                if path_obj.is_dir():
                    dir_images = discover_sif_images(str(path_obj))
                    if dir_images:
                        container = ask("Found fMRIPrep images. Choose one:", choices=[str(p) for p in dir_images])
                    else:
                        print(f"No .sif/.simg files found in {path_obj}")
                        container = ask("Enter full path to fMRIPrep .sif/.simg file", default=str(Path.cwd()), path=True)
                else:
                    container = path_input
    elif runtime in ["docker", "fmriprep-docker"]:
        if container != 'auto':
            # Container specified in config
            print(f"Using Docker image from config: {container}")
        else:
            # Auto mode - list Docker images
            imgs = docker_list_fmriprep_images()
            if imgs:
                container = ask("Choose Docker image:tag", choices=imgs)
            else:
                container = ask("No local Docker images found. Enter image:tag", default="nipreps/fmriprep:latest")

    # FS license
    default_fs_license = config.get('fs_license', os.environ.get("FS_LICENSE", str(Path.home() / "license.txt")))
    fs_license = Path(ask("Path to FS license", default=default_fs_license, path=True)).expanduser()
    
    # TemplateFlow directory
    default_templateflow = config.get('templateflow_home', 
                                     os.environ.get("TEMPLATEFLOW_HOME", 
                                                   str(Path.home() / ".cache" / "templateflow")))
    templateflow_home = Path(ask("TemplateFlow directory (will be created if needed)", default=default_templateflow, path=True)).expanduser()
    templateflow_home.mkdir(parents=True, exist_ok=True)
    _validate_templateflow(templateflow_home)

    # Resources
    cpus_auto, mem_auto = default_resources_from_env()
    nprocs = int(ask("nprocs (threads for parallel tasks)", 
                     default=config.get('nprocs', str(cpus_auto))))
    omp_threads = int(ask("omp-nthreads (per-process thread pool)", 
                         default=config.get('omp_threads', str(min(8, nprocs)))))
    mem_str = ask("mem-mb (e.g., 32000 or 32G)", 
                  default=config.get('mem_mb', str(mem_auto)))
    try:
        mem_mb = parse_memory_to_mb(mem_str)
    except (ValueError, TypeError) as e:
        print(f"Warning: could not parse memory '{mem_str}': {e}", file=sys.stderr)
        mem_mb = int(mem_str)

    # fMRIPrep flags
    output_spaces = ask('Output spaces (e.g. "MNI152NLin2009cAsym:res-2 T1w fsnative"; blank for defaults)', 
                       default=config.get('output_spaces', ""))
    
    default_skip = "y" if config.get('skip_bids_validation', '').lower() == 'true' else "n"
    skip_bids_validation = ask("Skip BIDS validation? (y/n)", choices=["y","n"], default=default_skip) == "y"
    
    default_aroma = "y" if config.get('use_aroma', '').lower() == 'true' else "n"
    use_aroma = ask("Use ICA-AROMA? (y/n)", choices=["y","n"], default=default_aroma) == "y"
    
    default_cifti = "y" if config.get('cifti_output', '').lower() == 'true' else "n"
    cifti_output = ask("CIFTI output 91k? (y/n)", choices=["y","n"], default=default_cifti) == "y"
    
    default_reconall = "y" if config.get('fs_reconall', '').lower() == 'true' else "n"
    fs_reconall = ask("Run FreeSurfer recon-all? (y/n)", choices=["y","n"], default=default_reconall) == "y"
    
    default_syn = "y" if config.get('use_syn_sdc', '').lower() == 'true' else "n"
    use_syn_sdc = ask("Enable SyN SDC? (y/n)", choices=["y","n"], default=default_syn) == "y"
    
    extra = ask('Any extra flags? (e.g. "--stop-on-first-crash")', 
               default=config.get('extra', ""))

    # Prepare cfg & preview command
    selected_subjects = discover_subjects(bids) if subjects == ["all"] else subjects
    cfg = BuildConfig(
        bids=bids, out=out, work=work, subjects=selected_subjects,
        container_runtime=runtime, container=container,
        fs_license=fs_license, templateflow_home=templateflow_home,
        omp_threads=omp_threads, nprocs=nprocs, mem_mb=mem_mb,
        extra=extra, skip_bids_validation=skip_bids_validation, output_spaces=output_spaces or None,
        use_aroma=use_aroma, cifti_output=cifti_output, fs_reconall=fs_reconall, use_syn_sdc=use_syn_sdc
    )

    # Preview one command
    preview_sub = selected_subjects[0]
    cmd = build_fmriprep_command(cfg, preview_sub)
    print("\nExample command:\n$ " + " ".join(cmd))

    # Generate Slurm?
    gen = ask("Generate Slurm array script now? (y/n)", choices=["y","n"])
    if gen == "y":
        outdir = Path(ask("Output directory for script", default=str(Path.cwd() / "fmriprep_job"), path=True)).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)

        partition = ask("Slurm partition", 
                       default=config.get('slurm_partition', os.environ.get("SLURM_JOB_PARTITION", "compute")))
        time = ask("Walltime (HH:MM:SS)", 
                  default=config.get('slurm_time', "24:00:00"))
        
        # Ask about subject batching
        subjects_per_job = int(ask("Subjects per job (1=one job per subject, >1=batch multiple)", default="1"))
        
        # Create subject batch file
        subj_file = outdir / "subjects.txt"
        batches = write_subject_batches(subj_file, selected_subjects, subjects_per_job)
        
        if subjects_per_job > 1:
            print(f"Will batch {subjects_per_job} subjects per job")
            print(f"Total jobs: {len(batches)}")
            # Adjust resources for batching - simple multiplication
            # Since we run subjects in parallel with xargs, each needs full resources
            adjusted_nprocs = nprocs * subjects_per_job
            adjusted_mem = mem_mb * subjects_per_job
            
            print(f"Total job resources: {adjusted_nprocs} CPUs, {adjusted_mem} MB memory")
            print(f"  ({nprocs} CPUs, {mem_mb} MB per subject)")
            cpus_per_task = int(ask("cpus-per-task", default=str(adjusted_nprocs)))
            mem_mb = adjusted_mem  # Update for later use
            nprocs = adjusted_nprocs
        else:
            cpus_per_task = int(ask("cpus-per-task", default=str(nprocs)))
        
        # Ask about memory specification
        use_mem = ask("Specify memory limit? (y/n - select 'n' for Trillium)", choices=["y","n"]) == "y"
        if use_mem:
            mem = ask("Slurm mem (e.g. 32G)", default=mb_to_human(mem_mb))
        else:
            mem = None
            
        account = ask("Slurm account (optional)", 
                     default=config.get('slurm_account', "")) or None
        email = ask("Email for notifications (optional)", 
                   default=config.get('slurm_email', "")) or None
        mail_type = ask("Mail type (e.g. END,FAIL) (optional)", 
                       default=config.get('slurm_mail_type', "")) or None
        job_name = ask("Job name", 
                      default=config.get('slurm_job_name', "fmriprep"))
        
        # Ask about log directory
        default_log = config.get('slurm_log_dir', str(outdir / "logs"))
        log_dir_str = ask("Log directory (use scratch path for Trillium)", default=default_log, path=True)
        log_dir = Path(log_dir_str).expanduser()
        
        module_singularity = ask("Insert 'module load singularity'? (y/n)", choices=["y","n"]) == "y"

        status_dir = outdir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)

        script_text = create_slurm_script(
            cfg=cfg, subject_file=subj_file, partition=partition, time=time,
            cpus_per_task=cpus_per_task, mem=mem, account=account, email=email,
            mail_type=mail_type, log_dir=log_dir, status_dir=status_dir,
            module_singularity=module_singularity, job_name=job_name
        )
        script_path = outdir / "fmriprep_array.sbatch"
        log_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text)
        os.chmod(script_path, 0o755)
        print(f"\nWrote Slurm script: {script_path}\nSubmit with:\n  sbatch {script_path}")


# -------------------- UI launcher commands --------------------

def _find_sibling_script(name: str) -> Path:
    """Locate a script in the same directory as this launcher."""
    here = Path(__file__).resolve().parent
    path = here / name
    if path.exists():
        return path
    raise SystemExit(f"Cannot find {name} (expected at {path})")


def cmd_tui(_args):
    """Launch the Textual terminal UI."""
    try:
        import textual  # noqa: F401
    except ImportError:
        print("The Textual TUI requires the 'textual' package.\n"
              "Install it with:\n  pip install textual\n"
              "Then re-run:  fmriprep_launcher.py tui", file=sys.stderr)
        sys.exit(1)
    script = _find_sibling_script("fmriprep_tui_autocomplete.py")
    os.execv(sys.executable, [sys.executable, str(script)])


def cmd_gui(_args):
    """Launch the Tkinter graphical UI."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Tkinter is not available in this Python installation.\n"
              "On HPC clusters, try loading a different Python module:\n"
              "  module load python/3.11  (or similar)\n"
              "Or use the TUI instead:  fmriprep_launcher.py tui", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("DISPLAY"):
        print("No DISPLAY set. The Tk GUI needs X11 forwarding.\n"
              "Connect with:  ssh -X user@cluster\n"
              "Or use the TUI instead:  fmriprep_launcher.py tui", file=sys.stderr)
        sys.exit(1)
    script = _find_sibling_script("fmriprep_gui_tk.py")
    os.execv(sys.executable, [sys.executable, str(script)])


# ---------------------------- Main ----------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="fmriprep_launcher", 
        description="One-stop fMRIPrep command & Slurm script generator",
        epilog="""Run '<subcommand> --help' for subcommand-specific options.

Getting started:
  %(prog)s init --user           Create user-level config (~/.config/fmriprep/config.ini)
  %(prog)s init                  Create project config (./fmriprep.ini) in current directory
  %(prog)s probe                 Show detected runtimes and containers
  %(prog)s wizard --quick        Interactive setup (asks only what's missing from config)

Config files are read in priority order (later overrides earlier):
  1. /etc/fmriprep/config.ini    2. ~/.config/fmriprep/config.ini
  3. ./fmriprep.ini              4. --config FILE

  [defaults]                          [slurm]
  bids, out, work        (paths)      partition    (default: compute)
  runtime                (singularity/docker/auto)  time  (default: 24:00:00)
  container              (path or auto)             account
  fs_license             (path)       job_name     (default: fmriprep)
  templateflow_home      (path)       log_dir, script_outdir
  nprocs, omp_threads    (int)        cpus_per_task, mem
  mem_mb                 (int/32G)    email, mail_type
  output_spaces          (string)     no_mem       (bool, for Trillium)
  skip_bids_validation   (bool)       module_singularity (bool)
  fs_reconall, use_syn_sdc (bool)
  cifti_output           (bool)
  subjects, extra

Environment variables: FMRIPREP_SIF_DIR, FS_LICENSE, TEMPLATEFLOW_HOME
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", type=str, help="Path to additional config file (overrides defaults)")

    # Pre-scan sys.argv for --config so we can load defaults before building
    # subparsers. This avoids parse_known_args() which swallows --help.
    config_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--config" and i + 1 < len(sys.argv):
            config_path = sys.argv[i + 1]
            break
        if arg.startswith("--config="):
            config_path = arg.split("=", 1)[1]
            break

    # Load configuration defaults
    config = load_config([config_path] if config_path else [])
    
    # Now add subparsers
    sub = ap.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help="Generate a starter fmriprep config file",
                            epilog="Examples:\n"
                                   "  %(prog)s --user          # Create ~/.config/fmriprep/config.ini\n"
                                   "  %(prog)s                 # Create ./fmriprep.ini for this dataset\n"
                                   "  %(prog)s /path/to/bids   # Create fmriprep.ini in a BIDS directory\n",
                            formatter_class=argparse.RawDescriptionHelpFormatter)
    p_init.add_argument("dir", nargs="?", default=".",
                        help="Target directory for project config (default: current directory)")
    p_init.add_argument("--user", action="store_true",
                        help="Create a user-level config at ~/.config/fmriprep/config.ini "
                             "(infrastructure defaults shared across all projects)")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing config file")
    p_init.set_defaults(func=cmd_init)

    # probe
    p_probe = sub.add_parser("probe", help="Show detected runtimes and available containers")
    p_probe.set_defaults(func=cmd_probe)

    # print-cmd
    p_print = sub.add_parser("print-cmd", help="Print per-subject fMRIPrep command(s)")
    add_common_args(p_print, config)
    p_print.set_defaults(func=cmd_print)

    # slurm-array
    p_slurm = sub.add_parser("slurm-array", help="Generate a Slurm array script and subject list")
    add_common_args(p_slurm, config)
    p_slurm.add_argument("--script-outdir", type=Path, 
                        default=Path(config.get("slurm_script_outdir", "./fmriprep_job")), 
                        help="Where to write sbatch and logs/")
    p_slurm.add_argument("--partition", default=config.get("slurm_partition", "compute"))
    p_slurm.add_argument("--time", default=config.get("slurm_time", "24:00:00"), help="Walltime, e.g. 24:00:00")
    p_slurm.add_argument("--cpus-per-task", type=int, 
                        default=int(config["slurm_cpus_per_task"]) if "slurm_cpus_per_task" in config else None)
    p_slurm.add_argument("--mem", default=config.get("slurm_mem"), 
                        help="Slurm memory request (e.g. 32G). Default: based on mem-mb. Use 'none' to omit --mem")
    p_slurm.add_argument("--account", default=config.get("slurm_account"))
    p_slurm.add_argument("--email", default=config.get("slurm_email"))
    p_slurm.add_argument("--mail-type", default=config.get("slurm_mail_type"))
    p_slurm.add_argument("--job-name", default=config.get("slurm_job_name", "fmriprep"))
    p_slurm.add_argument("--module-singularity", action="store_true", help="Insert 'module load singularity' in script")
    p_slurm.add_argument("--log-dir", type=Path,
                        default=Path(config["slurm_log_dir"]) if "slurm_log_dir" in config else None,
                        help="Override log directory (default: script-outdir/logs)")
    p_slurm.add_argument("--no-mem", action="store_true",
                        default=config.get("slurm_no_mem", config.get("no_mem", "false")).lower() == "true",
                        help="Omit --mem specification (for whole-node clusters)")
    p_slurm.add_argument("--subjects-per-job", type=int, default=1, 
                        help="Number of subjects to process per job (default: 1). "
                             "Values >1 batch multiple subjects together, reducing total jobs but requiring more resources per job.")
    p_slurm.set_defaults(func=cmd_slurm_array)

    # rerun-failed
    p_rerun = sub.add_parser("rerun-failed", help="Generate a new Slurm bundle for subjects marked failed in a previous job")
    p_rerun.add_argument("--manifest", type=Path, required=True, help="Path to a prior job_manifest.json")
    p_rerun.add_argument("--status-dir", type=Path, default=None, help="Override the status directory instead of using the one from the manifest")
    p_rerun.add_argument("--script-outdir", type=Path, default=None, help="Where to write the rerun bundle (default: <manifest dir>/rerun_failed_job)")
    p_rerun.add_argument("--subjects-per-job", type=int, default=None, help="Override batching for the rerun bundle")
    p_rerun.add_argument("--job-name", default=None, help="Override the rerun Slurm job name")
    p_rerun.set_defaults(func=cmd_rerun_failed)

    # wizard
    p_wiz = sub.add_parser("wizard", help="Interactive setup (questionary if available, else basic prompts)")
    p_wiz.add_argument("--quick", action="store_true",
                       help="Express mode: only ask essential questions, derive everything else from config/env/defaults")
    p_wiz.add_argument("--classic", action="store_true",
                       help="Use the old sequential Q&A wizard (requires questionary for best experience)")
    p_wiz.set_defaults(func=cmd_wizard)

    # tui
    p_tui = sub.add_parser("tui", help="Textual terminal UI with tabs and path completion (requires: pip install textual)")
    p_tui.set_defaults(func=cmd_tui)

    # gui
    p_gui = sub.add_parser("gui", help="Tkinter graphical UI (requires X11/display)")
    p_gui.set_defaults(func=cmd_gui)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
