#!/usr/bin/env python3
"""
fmriprep_command_builder_improved.py

Interactive fMRIPrep command & Slurm script builder.

Key fixes vs. your original:
- Correct flags: --nprocs (not --nthreads), --mem-mb (not --mem_mb), --skip-bids-validation (not underscores)
- Adds --fs-license-file /opt/freesurfer/license.txt and --work-dir /work
- Removes erroneous 'singularity -w /work' (which would try to make image writable)
- Normalizes --participant-label to strip 'sub-' prefix
- Fallback when participants.tsv is missing (scan sub-* dirs)
- Creates output/work directories if needed
- Runtime selection: Singularity/Apptainer, fmriprep-docker, or Docker
- Version menu: discovers .sif/.simg in $FMRIPREP_SIF_DIR or Docker images locally
- Capacity-aware defaults from SLURM or system
- Optional Slurm ARRAY script generation
"""

import csv
import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

try:
    import questionary
    from questionary import Validator, ValidationError
except Exception as e:
    print("The 'questionary' library is required. Install it with: pip install questionary")
    sys.exit(1)


# ---------------- Utilities ----------------

def which(cmd: str):
    return shutil.which(cmd)

def run(cmd):
    try:
        return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        return e

class PathExistsValidator(Validator):
    def validate(self, document):
        if not document.text.strip():
            raise ValidationError(message="Path is required.", cursor_position=len(document.text))
        if not os.path.exists(os.path.expanduser(document.text.strip())):
            raise ValidationError(message="Path does not exist.", cursor_position=len(document.text))

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p

def default_resources_from_env():
    # CPUs
    cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", os.environ.get("SLURM_CPUS_ON_NODE", "0")) or 0)
    if cpus <= 0:
        cpus = os.cpu_count() or 4
    # Memory (MB)
    mem_mb = 0
    if "SLURM_MEM_PER_CPU" in os.environ:
        mem_mb = int(os.environ["SLURM_MEM_PER_CPU"]) * cpus
    elif "SLURM_MEM_PER_NODE" in os.environ:
        mem_mb = int(os.environ["SLURM_MEM_PER_NODE"])
    else:
        # /proc/meminfo
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_mb = kb // 1024
                        break
        except Exception:
            mem_mb = 16000
    # leave 10% headroom
    mem_mb = int(mem_mb * 0.9)
    return cpus, mem_mb

def human_mb(mb: int):
    if mb >= 1_000_000:
        tb = mb / 1_000_000
        # Check if effectively a whole number (within 0.05)
        if abs(tb - round(tb)) < 0.05:
            return f"{round(tb)}T"
        else:
            return f"{tb:.1f}T"
    if mb >= 1000:
        gb = mb / 1000
        # Check if effectively a whole number (within 0.05)
        if abs(gb - round(gb)) < 0.05:
            return f"{round(gb)}G"
        else:
            return f"{gb:.1f}G"
    return f"{mb}M"


# ---------------- BIDS helpers ----------------

def parse_participants_tsv(bids_dir: Path):
    participants_file = bids_dir / "participants.tsv"
    subs = []
    if participants_file.exists():
        with open(participants_file, "r", newline="") as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter="\t")
            col = "participant_id" if "participant_id" in reader.fieldnames else None
            if not col:
                # take the first column
                col = reader.fieldnames[0]
            for row in reader:
                raw = str(row[col]).strip()
                if not raw:
                    continue
                subs.append(raw if raw.startswith("sub-") else f"sub-{raw}")
    return sorted(list(dict.fromkeys(subs)))

def scan_sub_dirs(bids_dir: Path):
    subs = []
    for p in bids_dir.iterdir():
        if p.is_dir() and p.name.startswith("sub-"):
            subs.append(p.name)
    return sorted(subs)

def get_participants(bids_dir: Path):
    subs = parse_participants_tsv(bids_dir)
    if not subs:
        subs = scan_sub_dirs(bids_dir)
    return subs


# ---------------- Container/runtime helpers ----------------

def detect_runtime():
    if which("singularity") or which("apptainer"):
        return "singularity"
    if which("fmriprep-docker"):
        return "fmriprep-docker"
    if which("docker"):
        return "docker"
    return None

def discover_sif_images():
    images = []
    sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
    if sif_dir and os.path.isdir(os.path.expanduser(sif_dir)):
        for p in Path(os.path.expanduser(sif_dir)).iterdir():
            if p.suffix.lower() in (".sif", ".simg") and "fmriprep" in p.name.lower():
                images.append(str(p))
    return images

def docker_list_fmriprep_images():
    if not which("docker"):
        return []
    proc = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    out = proc.stdout if hasattr(proc, "stdout") else ""
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return [l for l in lines if re.match(r"^(nipreps|poldracklab|fmriprep)/fmriprep", l)]

def strip_sub_prefix(label: str):
    return label[4:] if label.startswith("sub-") else label


# ---------------- SLURM template ----------------

SLURM_TEMPLATE = """\
#!/usr/bin/env bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --time={time}
#SBATCH --cpus-per-task={cpus}
{mem_line}#SBATCH --nodes=1
#SBATCH --array=0-{array_max}
#SBATCH --output={log_dir}/%x_%A_%a.out
#SBATCH --error={log_dir}/%x_%A_%a.err
{account}{mail}

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

SUBS=($(grep -v '^#' "$SUBJECT_FILE" | sed '/^$/d'))
SUB="${{SUBS[$SLURM_ARRAY_TASK_ID]}}"
if [[ -z "$SUB" ]]; then echo "No subject at index $SLURM_ARRAY_TASK_ID"; exit 1; fi

mkdir -p "$OUT_DIR" "$WORK_DIR" "{log_dir}"

CLI=(participant --participant-label "${{SUB#sub-}}" --nprocs "$NPROCS" --omp-nthreads "$OMP" --mem-mb "$MEM_MB" --fs-license-file /opt/freesurfer/license.txt --notrack)

if [[ "$SKIP_VAL" == "1" ]]; then CLI+=(--skip-bids-validation); fi
if [[ -n "$OUTPUT_SPACES" ]]; then CLI+=(--output-spaces $OUTPUT_SPACES); fi
if [[ "$AROMA" == "1" ]]; then CLI+=(--use-aroma); fi
if [[ "$CIFTI" == "1" ]]; then CLI+=(--cifti-output 91k); fi
if [[ "$RECONALL" == "0" ]]; then CLI+=(--fs-no-reconall); fi
if [[ -n "$EXTRA" ]]; then CLI+=($EXTRA); fi

echo "=== fMRIPrep $SUB ==="
echo "Runtime: $RUNTIME"
echo "Container: $CONTAINER"
echo "Command: $RUNTIME ... $SUB"
echo "----------------------"

if [[ "$RUNTIME" == "singularity" ]]; then
  RT_BIN=$(command -v singularity || command -v apptainer)
  "$RT_BIN" run --cleanenv \
    -B "$BIDS_DIR:/data:ro" \
    -B "$OUT_DIR:/out" \
    -B "$WORK_DIR:/work" \
    -B "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \
    "$CONTAINER" \
    /data /out "${{CLI[@]}}" --work-dir /work

elif [[ "$RUNTIME" == "fmriprep-docker" ]]; then
  fmriprep-docker "$BIDS_DIR" "$OUT_DIR" "${{CLI[@]}}" --work-dir "$WORK_DIR" --fs-license-file "$FS_LICENSE"

elif [[ "$RUNTIME" == "docker" ]]; then
  docker run --rm \
    -v "$BIDS_DIR:/data:ro" \
    -v "$OUT_DIR:/out" \
    -v "$WORK_DIR:/work" \
    -v "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \
    "$CONTAINER" \
    /data /out "${{CLI[@]}}" --work-dir /work

else
  echo "Unknown runtime: $RUNTIME"; exit 2
fi
"""


# ---------------- Main interactive flow ----------------

def main():
    print("Welcome to the fMRIPrep Interactive Command & Slurm Builder\n")

    # BIDS root
    bids_dir = Path(questionary.path("Enter the path to your BIDS dataset:", validate=PathExistsValidator()).ask()).expanduser()
    if not bids_dir:
        print("BIDS directory is required."); sys.exit(1)

    # Subjects
    subs = get_participants(bids_dir)
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
    detected = detect_runtime()
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
            container = questionary.select("Choose fMRIPrep .sif/.simg", choices=images).ask()
        else:
            container = questionary.path("Enter path to fMRIPrep .sif/.simg:", validate=PathExistsValidator()).ask()
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

    # Build base CLI (common across runtimes)
    labels_sans = [strip_sub_prefix(s) for s in selected]
    label_str = " ".join(labels_sans)

    base_cli = f"participant --participant-label {label_str} --nprocs {nprocs} --omp-nthreads {omp_threads} --mem-mb {mem_mb} --notrack"
    if skip_bids_val:
        base_cli += " --skip-bids-validation"
    if output_spaces.strip():
        base_cli += f" --output-spaces {output_spaces}"
    if use_aroma:
        base_cli += " --use-aroma"
    if cifti_output:
        base_cli += " --cifti-output 91k"
    if not fs_reconall:
        base_cli += " --fs-no-reconall"
    if use_syn_sdc:
        base_cli += " --use-syn-sdc"
    if extra.strip():
        base_cli += f" {extra.strip()}"

    # TemplateFlow cache
    tf_home = Path.home() / ".cache" / "templateflow"
    ensure_dir(tf_home)

    # Build full command
    if runtime == "singularity":
        rt = "$(command -v singularity || command -v apptainer)"
        full_cmd = (
            f'{rt} run --cleanenv '
            f'-B "{bids_dir}:/data:ro" '
            f'-B "{out_dir}:/out" '
            f'-B "{work_dir}:/work" '
            f'-B "{fs_license}:/opt/freesurfer/license.txt:ro" '
            f'-B "{tf_home}:/templateflow" '
            f'"{container}" '
            f'/data /out {base_cli} --work-dir /work --fs-license-file /opt/freesurfer/license.txt'
        )
    elif runtime == "fmriprep-docker":
        full_cmd = (
            f'fmriprep-docker "{bids_dir}" "{out_dir}" '
            f'{base_cli} --work-dir "{work_dir}" --fs-license-file "{fs_license}"'
        )
    else:  # docker
        full_cmd = (
            f'docker run --rm '
            f'-v "{bids_dir}:/data:ro" '
            f'-v "{out_dir}:/out" '
            f'-v "{work_dir}:/work" '
            f'-v "{fs_license}:/opt/freesurfer/license.txt:ro" '
            f'-v "{tf_home}:/templateflow" '
            f'"{container}" '
            f'/data /out {base_cli} --work-dir /work --fs-license-file /opt/freesurfer/license.txt'
        )

    # Write a simple runner script
    script_path = Path.cwd() / "run_fmriprep.sh"
    script = f"""#!/usr/bin/env bash
set -euo pipefail

# Generated by fMRIPrep Interactive Builder
echo "Running fMRIPrep on {len(selected)} subject(s): {' '.join(selected)}"
{full_cmd}
"""
    script_path.write_text(script)
    os.chmod(script_path, 0o755)
    print(f"\nSaved runner script: {script_path}")

    # Offer to generate SLURM array script
    if questionary.confirm("Generate a Slurm ARRAY script?", default=True).ask():
        job_dir = ensure_dir(Path.cwd() / "fmriprep_job")
        subj_file = job_dir / "subjects.txt"
        subj_file.write_text("\n".join(selected) + "\n")

        partition = questionary.text("Slurm partition:", default=os.environ.get("SLURM_JOB_PARTITION", "compute")).ask()
        walltime = questionary.text("Walltime (HH:MM:SS):", default="24:00:00").ask()
        
        # Ask about memory specification
        use_mem = questionary.confirm("Specify memory limit? (select No for Trillium cluster)", default=True).ask()
        if use_mem:
            mem_slurm = questionary.text("Slurm --mem (e.g., 32G):", default=human_mb(mem_mb)).ask()
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
        
        account = questionary.text("Slurm account (optional):", default="").ask()
        email = questionary.text("Notification email (optional):", default="").ask()
        mail_type = questionary.text("Mail type (e.g. END,FAIL) (optional):", default="").ask()
        job_name = questionary.text("Job name:", default="fmriprep").ask()

        mail_block = ""
        if email:
            mail_block += f"#SBATCH --mail-user={email}\n"
            if mail_type:
                mail_block += f"#SBATCH --mail-type={mail_type}\n"

        slurm_text = SLURM_TEMPLATE.format(
            job_name=job_name,
            partition=partition,
            time=walltime,
            cpus=nprocs,
            mem_line=mem_line,  # Use mem_line instead of mem
            array_max=max(0, len(selected)-1),
            log_dir=str(log_dir),  # Use the selected log_dir
            account=(f"#SBATCH --account={account}\n" if account else ""),
            mail=mail_block,
            bids=str(bids_dir),
            out=str(out_dir),
            work=str(work_dir),
            fs_license=str(fs_license),
            subject_file=str(subj_file),
            runtime=runtime,
            container=container,
            nprocs=nprocs,
            omp=omp_threads,
            mem_mb=mem_mb,
            extra=extra,
            skip_val="1" if skip_bids_val else "0",
            output_spaces=output_spaces,
            aroma="1" if use_aroma else "0",
            cifti="1" if cifti_output else "0",
            reconall="1" if fs_reconall else "0",
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
