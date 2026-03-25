#!/usr/bin/env python3
"""
fmriprep_command_builder.py

Legacy interactive questionary frontend for building fMRIPrep commands and
optional Slurm scripts.

This file is kept for compatibility, but the recommended entrypoint is now:

    python fmriprep_launcher.py wizard

The long-term direction is to keep shared behavior in fmriprep_launcher.py (or
shared backend helpers) and treat this file as a thin frontend only.
"""

import os
import sys
from pathlib import Path

from fmriprep_backend import BuildConfig, build_fmriprep_command, create_slurm_script, write_subject_batches
from fmriprep_shared import (
    default_resources_from_env,
    detect_runtime_optional,
    discover_sif_images,
    discover_subjects,
    docker_list_fmriprep_images,
    mb_to_human,
)

try:
    import questionary
    from questionary import Validator, ValidationError
except Exception as e:
    print("The 'questionary' library is required. Install it with: pip install questionary")
    sys.exit(1)

class PathExistsValidator(Validator):
    def validate(self, document):
        if not document.text.strip():
            raise ValidationError(message="Path is required.", cursor_position=len(document.text))
        if not os.path.exists(os.path.expanduser(document.text.strip())):
            raise ValidationError(message="Path does not exist.", cursor_position=len(document.text))

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p

# ---------------- Main interactive flow ----------------

def main():
    print("Welcome to the fMRIPrep Interactive Command & Slurm Builder\n")

    # BIDS root
    bids_dir = Path(questionary.path("Enter the path to your BIDS dataset:", validate=PathExistsValidator()).ask()).expanduser()
    if not bids_dir:
        print("BIDS directory is required."); sys.exit(1)

    # Subjects
    subs = discover_subjects(bids_dir)
    if not subs:
        print("No subjects found in participants.tsv or sub-* directories."); sys.exit(1)
    selected = questionary.checkbox(
        "Select participants to process (space to toggle, enter to accept):",
        choices=subs,
        validate=lambda a: True if len(a) > 0 else "Pick at least one subject."
    ).ask()
    if not selected:
        print("No participants selected."); sys.exit(1)

    # Output/work
    default_out = str(bids_dir / "derivatives" / "fmriprep")
    out_dir = Path(questionary.path("Output directory for fMRIPrep results:", default=default_out).ask()).expanduser()
    work_dir = Path(questionary.path("Work directory (--work-dir):", default=str(bids_dir / "work_fmriprep")).ask()).expanduser()
    ensure_dir(out_dir); ensure_dir(work_dir)

    # Runtime selection
    detected = detect_runtime_optional()
    runtime = questionary.select(
        "Pick a runtime:",
        choices=[
            ("Singularity/Apptainer", "singularity"),
            ("fmriprep-docker (wrapper)", "fmriprep-docker"),
            ("Docker", "docker")
        ],
        default=("Singularity/Apptainer" if detected == "singularity" else ("fmriprep-docker" if detected == "fmriprep-docker" else "Docker"))
    ).ask()

    # Container selection
    if runtime == "singularity":
        images = discover_sif_images()
        if images:
            container = questionary.select("Choose fMRIPrep .sif/.simg", choices=[str(p) for p in images]).ask()
        else:
            # Ask for path - could be file or directory
            path_input = questionary.path(
                "Enter path to fMRIPrep .sif/.simg or directory containing them:", 
                validate=PathExistsValidator()
            ).ask()
            path_obj = Path(path_input).expanduser()
            
            # If it's a directory, scan for .sif/.simg files
            if path_obj.is_dir():
                dir_images = discover_sif_images(str(path_obj))
                if dir_images:
                    container = questionary.select("Found fMRIPrep images. Choose one:", choices=[str(p) for p in dir_images]).ask()
                else:
                    print(f"No .sif/.simg files found in {path_obj}")
                    container = questionary.path(
                        "Enter full path to fMRIPrep .sif/.simg file:", 
                        validate=PathExistsValidator()
                    ).ask()
            else:
                container = path_input
    elif runtime == "docker":
        imgs = docker_list_fmriprep_images()
        if imgs:
            container = questionary.select("Choose fMRIPrep Docker image:tag", choices=imgs).ask()
        else:
            container = questionary.text("Enter image:tag (default nipreps/fmriprep:latest):", default="nipreps/fmriprep:latest").ask()
    else:  # fmriprep-docker
        # Wrapper pulls images as needed; allow override
        container = questionary.text("Docker image for wrapper (default nipreps/fmriprep:latest):", default="nipreps/fmriprep:latest").ask()

    # FS license
    fs_license = Path(questionary.path(
        "Path to the FreeSurfer license (license.txt):",
        default=os.environ.get("FS_LICENSE", str(Path.home() / "license.txt")),
        validate=PathExistsValidator()
    ).ask()).expanduser()

    # Resource defaults
    cpus_auto, mem_auto = default_resources_from_env()
    nprocs = int(questionary.text("nprocs (parallel workers):", default=str(cpus_auto)).ask())
    omp_threads = int(questionary.text("omp-nthreads (per-process thread pool):", default=str(min(8, nprocs))).ask())
    mem_mb = int(questionary.text("mem-mb (memory for fMRIPrep):", default=str(mem_auto)).ask())

    # fMRIPrep flags
    output_spaces = questionary.text('Output spaces (e.g., "MNI152NLin2009cAsym:res-2 T1w fsnative"):', default="MNI152NLin2009cAsym:res-2 T1w").ask()
    use_aroma = questionary.confirm("Use ICA-AROMA (--use-aroma)?", default=False).ask()
    cifti_output = questionary.confirm("CIFTI output 91k (--cifti-output 91k)?", default=False).ask()
    fs_reconall = questionary.confirm("Run FreeSurfer recon-all? (No will pass --fs-no-reconall)", default=False).ask()
    skip_bids_val = questionary.confirm("Skip BIDS validation (--skip-bids-validation)?", default=True).ask()
    use_syn_sdc = questionary.confirm("Enable SyN SDC (--use-syn-sdc)?", default=False).ask()
    extra = questionary.text('Any extra flags? (e.g. "--stop-on-first-crash --output-layout bids")', default="").ask()

    tf_home = ensure_dir(Path.home() / ".cache" / "templateflow")
    cfg = BuildConfig(
        bids=bids_dir,
        out=out_dir,
        work=work_dir,
        subjects=selected,
        container_runtime=runtime,
        container=container,
        fs_license=fs_license,
        templateflow_home=tf_home,
        omp_threads=omp_threads,
        nprocs=nprocs,
        mem_mb=mem_mb,
        extra=extra,
        skip_bids_validation=skip_bids_val,
        output_spaces=output_spaces,
        use_aroma=use_aroma,
        cifti_output=cifti_output,
        fs_reconall=fs_reconall,
        use_syn_sdc=use_syn_sdc,
    )
    commands = [build_fmriprep_command(cfg, subject) for subject in selected]

    # Write a simple runner script
    script_path = Path.cwd() / "run_fmriprep.sh"
    script = f"""#!/usr/bin/env bash
set -euo pipefail

# Generated by fMRIPrep Interactive Builder
echo "Running fMRIPrep on {len(selected)} subject(s): {' '.join(selected)}"
{"\n".join(" ".join(cmd) for cmd in commands)}
"""
    script_path.write_text(script)
    os.chmod(script_path, 0o755)
    print(f"\nSaved runner script: {script_path}")

    # Offer to generate SLURM array script
    if questionary.confirm("Generate a Slurm ARRAY script?", default=True).ask():
        job_dir = ensure_dir(Path.cwd() / "fmriprep_job")
        subj_file = job_dir / "subjects.txt"
        write_subject_batches(subj_file, selected)

        partition = questionary.text("Slurm partition:", default=os.environ.get("SLURM_JOB_PARTITION", "compute")).ask()
        walltime = questionary.text("Walltime (HH:MM:SS):", default="24:00:00").ask()
        
        # Ask about memory specification
        use_mem = questionary.confirm("Specify memory limit? (select No for Trillium cluster)", default=True).ask()
        if use_mem:
            mem_slurm = questionary.text("Slurm --mem (e.g., 32G):", default=mb_to_human(mem_mb)).ask()
            mem_line = f"#SBATCH --mem={mem_slurm}\n"
        else:
            mem_line = ""
            
        # Ask about log directory  
        default_log_dir = str(job_dir / "logs")
        log_dir_path = questionary.path(
            "Log directory (use scratch path for Trillium, not /project):", 
            default=default_log_dir
        ).ask()
        log_dir = Path(log_dir_path).expanduser()
        ensure_dir(log_dir)
        status_dir = ensure_dir(job_dir / "status")
        
        account = questionary.text("Slurm account (optional):", default="").ask()
        email = questionary.text("Notification email (optional):", default="").ask()
        mail_type = questionary.text("Mail type (e.g. END,FAIL) (optional):", default="").ask()
        job_name = questionary.text("Job name:", default="fmriprep").ask()

        slurm_text = create_slurm_script(
            cfg=cfg,
            subject_file=subj_file,
            partition=partition,
            time=walltime,
            cpus_per_task=nprocs,
            mem=mem_slurm if use_mem else None,
            account=account or None,
            email=email or None,
            mail_type=mail_type or None,
            log_dir=log_dir,
            status_dir=status_dir,
            module_singularity=runtime == "singularity",
            job_name=job_name,
        )
        sbatch_path = job_dir / "fmriprep_array.sbatch"
        sbatch_path.write_text(slurm_text)
        os.chmod(sbatch_path, 0o755)
        print(f"Saved Slurm script: {sbatch_path}")
        print(f"Saved subject list: {subj_file}")
        print("Submit with:")
        print(f"  sbatch {sbatch_path}")


if __name__ == "__main__":
    main()
