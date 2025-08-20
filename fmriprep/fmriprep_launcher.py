#!/usr/bin/env python3
"""
fmriprep_launcher.py

One-stop tool to build correct fMRIPrep commands and generate a Slurm array
script for a BIDS dataset. Supports Singularity/Apptainer, the fmriprep-docker
wrapper, and plain Docker. Includes an interactive "wizard" and CLI subcommands.

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
import configparser
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict


# ---------------------------- Configuration ----------------------------

def load_config(config_paths: List[str] = None) -> Dict[str, str]:
    """
    Load configuration from files. Checks in order:
    1. System config: /etc/fmriprep/config.ini
    2. User config: ~/.config/fmriprep/config.ini or ~/.fmriprep.ini
    3. Local config: ./fmriprep.ini
    4. Custom path if provided
    
    Later configs override earlier ones.
    """
    if config_paths is None:
        config_paths = []
    
    # Default config locations
    default_paths = [
        "/etc/fmriprep/config.ini",
        Path.home() / ".config" / "fmriprep" / "config.ini",
        Path.home() / ".fmriprep.ini",
        Path.cwd() / "fmriprep.ini"
    ]
    
    config = configparser.ConfigParser()
    defaults = {}
    
    for path in default_paths + [Path(p) for p in config_paths]:
        if isinstance(path, str):
            path = Path(path)
        if path.exists():
            config.read(path)
            if 'defaults' in config:
                defaults.update(dict(config['defaults']))
            # Also check for a 'slurm' section for SLURM-specific defaults
            if 'slurm' in config:
                for key, value in config['slurm'].items():
                    defaults[f'slurm_{key}'] = value
    
    return defaults

# ---------------------------- Utilities ----------------------------

def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)

def run_cmd(cmd: List[str], check=False) -> Tuple[int, str, str]:
    """Run a command and capture (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)

def parse_memory_to_mb(value: str) -> int:
    """Parse memory string (e.g., '32G', '760000', '2T') to MB."""
    if isinstance(value, int):
        return value
    
    value = str(value).strip().upper()
    
    # Try to parse with units
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$', value)
    if match:
        num = float(match.group(1))
        unit = match.group(2)
        
        if unit == 'K':
            return int(num / 1024)  # KB to MB
        elif unit == 'M' or unit == '':
            return int(num)  # Already MB or no unit means MB
        elif unit == 'G':
            return int(num * 1024)  # GB to MB  
        elif unit == 'T':
            return int(num * 1024 * 1024)  # TB to MB
    
    # Fallback: try to parse as plain number
    try:
        return int(float(value))
    except:
        raise ValueError(f"Cannot parse memory value: {value}")

def mb_to_human(mb: int) -> str:
    """Convert integer MB to Slurm-friendly string."""
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

def read_meminfo_mb() -> int:
    """Rough system memory from /proc/meminfo in MB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    kb = int(parts[1])  # kB
                    return kb // 1024
    except Exception:
        pass
    return 16000  # fallback 16 GB

def default_resources_from_env() -> Tuple[int, int]:
    """
    Return (cpus, mem_mb) from Slurm env or system.
    Leaves ~10% headroom for safety.
    """
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

def detect_runtime(prefer: str = "auto") -> str:
    """
    Determine container runtime: 'singularity', 'fmriprep-docker', or 'docker'.
    Treat Apptainer as 'singularity'.
    """
    if prefer in ("singularity", "docker", "fmriprep-docker"):
        return prefer
    if which("singularity") or which("apptainer"):
        return "singularity"
    if which("fmriprep-docker"):
        return "fmriprep-docker"
    if which("docker"):
        return "docker"
    raise RuntimeError("No container runtime found. Install Singularity/Apptainer, fmriprep-docker, or Docker.")

def discover_sif_images(search_dir: Optional[str]) -> List[Path]:
    """Return fMRIPrep .sif/.simg images from a directory (non-recursive)."""
    candidates: List[Path] = []
    if search_dir:
        d = Path(search_dir).expanduser()
        if d.is_dir():
            for p in d.iterdir():
                if p.suffix.lower() in (".sif", ".simg") and "fmriprep" in p.name.lower():
                    candidates.append(p)
    return sorted(candidates)

def docker_list_fmriprep_images() -> List[str]:
    """Return local docker image:tag strings for fmriprep."""
    if not which("docker"):
        return []
    rc, out, _ = run_cmd(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    if rc != 0:
        return []
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return [l for l in lines if re.match(r"^(nipreps|poldracklab|fmriprep)/fmriprep(:|$)", l)]

def parse_participants_tsv(bids: Path) -> List[str]:
    tsv = bids / "participants.tsv"
    subs: List[str] = []
    if tsv.exists():
        with open(tsv, "r", newline="") as f:
            header = f.readline().strip().split("\t")
            if not header:
                return subs
            # Use 'participant_id' if present, else first column
            if "participant_id" in header:
                idx = header.index("participant_id")
            else:
                idx = 0
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) > idx:
                    sub = cols[idx].strip()
                    if not sub:
                        continue
                    subs.append(sub if sub.startswith("sub-") else f"sub-{sub}")
    return sorted(list(dict.fromkeys(subs)))

def scan_bids_for_subjects(bids: Path) -> List[str]:
    return sorted([p.name for p in bids.iterdir() if p.is_dir() and p.name.startswith("sub-")])

def discover_subjects(bids: Path) -> List[str]:
    subs = parse_participants_tsv(bids)
    return subs if subs else scan_bids_for_subjects(bids)


# ---------------------------- Command builder ----------------------------

@dataclass
class BuildConfig:
    bids: Path
    out: Path
    work: Path
    subjects: List[str]
    container_runtime: str
    container: str  # .sif path for singularity, image:tag for docker
    fs_license: Path
    templateflow_home: Optional[Path]  # TemplateFlow directory
    omp_threads: int
    nprocs: int
    mem_mb: int
    extra: str
    skip_bids_validation: bool
    output_spaces: Optional[str]
    use_aroma: bool
    cifti_output: bool
    fs_reconall: bool
    use_syn_sdc: bool

def build_fmriprep_command(cfg: BuildConfig, subjects: List[str]) -> List[str]:
    """
    Construct the full fMRIPrep command for one or more subjects.
    """
    # Handle both single subject (string) and multiple subjects (list)
    if isinstance(subjects, str):
        subjects = [subjects]
    
    labels = [s.replace("sub-", "") for s in subjects]
    base_cli = [
        "participant",
        "--participant-label"] + labels + [
        "--nprocs", str(cfg.nprocs),
        "--omp-nthreads", str(cfg.omp_threads),
        "--mem-mb", str(cfg.mem_mb),
        "--notrack",
    ]
    if cfg.skip_bids_validation:
        base_cli += ["--skip-bids-validation"]
    if cfg.output_spaces:
        base_cli += ["--output-spaces"] + cfg.output_spaces.split()
    if cfg.use_aroma:
        base_cli += ["--use-aroma"]
    if cfg.cifti_output:
        base_cli += ["--cifti-output", "91k"]
    if not cfg.fs_reconall:
        base_cli += ["--fs-no-reconall"]
    if cfg.use_syn_sdc:
        base_cli += ["--use-syn-sdc"]
    if cfg.extra:
        base_cli += cfg.extra.split()

    bids_dir_in = "/data"
    out_dir_in = "/out"
    work_dir_in = "/work"
    fs_license_in = "/opt/freesurfer/license.txt"

    if cfg.container_runtime == "singularity":
        # singularity or apptainer
        singularity_bin = "singularity" if which("singularity") else "apptainer"
        
        # Handle TemplateFlow directory
        if cfg.templateflow_home:
            templateflow_host = str(cfg.templateflow_home)
        else:
            templateflow_host = os.environ.get("TEMPLATEFLOW_HOME", 
                                              str(Path.home() / ".cache" / "templateflow"))
        templateflow_container = "/opt/templateflow"
        
        cmd = [
            singularity_bin, "run", "--cleanenv",
            "-B", f"{cfg.bids}:{bids_dir_in}:ro",
            "-B", f"{cfg.out}:{out_dir_in}",
            "-B", f"{cfg.work}:{work_dir_in}",
            "-B", f"{cfg.fs_license}:{fs_license_in}:ro",
            "-B", f"{templateflow_host}:{templateflow_container}",
        ]
        
        # Set TemplateFlow environment variable
        cmd = ["SINGULARITYENV_TEMPLATEFLOW_HOME=" + templateflow_container] + cmd
        
        cmd += [
            cfg.container,
            bids_dir_in, out_dir_in
        ] + base_cli + ["--work-dir", work_dir_in, "--fs-license-file", fs_license_in]
        return cmd

    if cfg.container_runtime == "fmriprep-docker":
        # wrapper mounts paths for us
        cmd = [
            "fmriprep-docker",
            str(cfg.bids), str(cfg.out),
        ] + base_cli + ["--work-dir", str(cfg.work), "--fs-license-file", str(cfg.fs_license)]
        return cmd

    if cfg.container_runtime == "docker":
        img = cfg.container
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{cfg.bids}:{bids_dir_in}:ro",
            "-v", f"{cfg.out}:{out_dir_in}",
            "-v", f"{cfg.work}:{work_dir_in}",
            "-v", f"{cfg.fs_license}:{fs_license_in}:ro",
            img,
            bids_dir_in, out_dir_in
        ] + base_cli + ["--work-dir", work_dir_in, "--fs-license-file", fs_license_in]
        return cmd

    raise ValueError(f"Unknown runtime: {cfg.container_runtime}")


# ---------------------------- Slurm script generation ----------------------------

SLURM_TEMPLATE = """\
#!/usr/bin/env bash
#
# Auto-generated by fmriprep_launcher.py
#
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --time={time}
#SBATCH --cpus-per-task={cpus_per_task}
{mem_line}#SBATCH --nodes=1
#SBATCH --array=0-{array_max}
#SBATCH --output={log_dir}/%x_%A_%a.out
#SBATCH --error={log_dir}/%x_%A_%a.err
{account_line}{mail_line}{module_line}

set -euo pipefail

# ===== User settings (auto-generated) =====
BIDS_DIR="{bids}"
OUT_DIR="{out}"
WORK_DIR="{work}"
FS_LICENSE="{fs_license}"
SUBJECT_LIST_FILE="{subject_file}"
RUNTIME="{runtime}"                  # singularity | fmriprep-docker | docker
CONTAINER="{container}"              # path to .sif or docker image:tag
OMP_THREADS="{omp_threads}"
NPROCS="{nprocs}"
MEM_MB="{mem_mb}"
EXTRA_FLAGS="{extra_flags}"
SKIP_BIDS_VAL="{skip_bids_val}"
OUTPUT_SPACES="{output_spaces}"
USE_AROMA="{use_aroma}"
CIFTI="{cifti}"
FS_RECONALL="{fs_reconall}"
USE_SYN_SDC="{use_syn_sdc}"

# ===== Derived settings =====
# Read subject line (may contain multiple space-separated subjects if batching)
mapfile -t SUBJECT_LINES < <(grep -v '^#' "$SUBJECT_LIST_FILE" | sed '/^$/d')
SUBJECT_LINE="${{SUBJECT_LINES[$SLURM_ARRAY_TASK_ID]}}"
if [[ -z "$SUBJECT_LINE" ]]; then
  echo "No subject(s) for index $SLURM_ARRAY_TASK_ID"; exit 1;
fi

# Parse subjects from line (space-separated if batching)
IFS=' ' read -ra SUBJECTS <<< "$SUBJECT_LINE"
NUM_SUBJECTS=${{#SUBJECTS[@]}}
echo "=== Processing $NUM_SUBJECTS subject(s) in this job ==="
for SUB in "${{SUBJECTS[@]}}"; do
  echo "  - $SUB"
done

mkdir -p "$OUT_DIR" "$WORK_DIR" "{log_dir}"

# When batching, each parallel process gets the full per-subject resources
# The SLURM job should have been allocated total_resources = per_subject × num_subjects
if [[ $NUM_SUBJECTS -gt 1 ]]; then
  echo "Running $NUM_SUBJECTS subjects in parallel"
  echo "Resources per subject: $NPROCS CPUs, $MEM_MB MB memory"
fi

# Build base CLI (without participant label, will be added per subject)
# Note: NPROCS and MEM_MB are already per-subject values from the config
CLI_BASE=(participant --nprocs "$NPROCS" --omp-nthreads "$OMP_THREADS" --mem-mb "$MEM_MB" --notrack)

if [[ "$SKIP_BIDS_VAL" == "1" ]]; then
  CLI_BASE+=(--skip-bids-validation)
fi
if [[ -n "$OUTPUT_SPACES" ]]; then
  CLI_BASE+=(--output-spaces $OUTPUT_SPACES)
fi
if [[ "$USE_AROMA" == "1" ]]; then
  CLI_BASE+=(--use-aroma)
fi
if [[ "$CIFTI" == "1" ]]; then
  CLI_BASE+=(--cifti-output 91k)
fi
if [[ "$FS_RECONALL" == "0" ]]; then
  CLI_BASE+=(--fs-no-reconall)
fi
if [[ "$USE_SYN_SDC" == "1" ]]; then
  CLI_BASE+=(--use-syn-sdc)
fi
if [[ -n "$EXTRA_FLAGS" ]]; then
  CLI_BASE+=($EXTRA_FLAGS)
fi

echo "=== Running fMRIPrep on $HOSTNAME ==="
echo "Runtime: $RUNTIME"
echo "Container: $CONTAINER"
echo "Subjects: ${{SUBJECTS[@]}}"
echo "----------------------------------------------"

# Setup TemplateFlow directory (use TEMPLATEFLOW_HOME if set, otherwise default)
# Can be overridden by setting TEMPLATEFLOW_HOME environment variable
TEMPLATEFLOW_HOST="${{TEMPLATEFLOW_HOME:-{templateflow_home}}}"
mkdir -p "$TEMPLATEFLOW_HOST"
echo "TemplateFlow directory: $TEMPLATEFLOW_HOST"

if [[ "$RUNTIME" == "singularity" ]]; then
  RT_BIN=$(command -v singularity || command -v apptainer)
  
  # Detect if using Apptainer vs Singularity for environment variable prefix
  if [[ "$RT_BIN" == *"apptainer"* ]]; then
    ENV_PREFIX="APPTAINERENV"
  else
    ENV_PREFIX="SINGULARITYENV"
  fi
  
  # Export environment variables for Singularity/Apptainer
  export ${{ENV_PREFIX}}_TEMPLATEFLOW_HOME=/opt/templateflow
  
  # Set additional environment variables for newer fMRIPrep versions
  # Create directories for matplotlib and other configs
  mkdir -p "$WORK_DIR/.matplotlib" "$WORK_DIR/.cache"
  export ${{ENV_PREFIX}}_MPLCONFIGDIR=/work/.matplotlib
  export ${{ENV_PREFIX}}_HOME=/work/.home
  export ${{ENV_PREFIX}}_NUMEXPR_MAX_THREADS=$OMP_THREADS
  
  # Function to run fMRIPrep for a single subject
  run_subject() {{
    local SUBJECT_ID="${{1#sub-}}"
    echo "Starting fMRIPrep for sub-${{SUBJECT_ID}}..."
    
    # Create unique work directory for this subject to avoid conflicts
    local SUBJECT_WORK_DIR="${{WORK_DIR}}/sub-${{SUBJECT_ID}}"
    mkdir -p "$SUBJECT_WORK_DIR"
    
    # Create cache directories for matplotlib and home
    mkdir -p "$SUBJECT_WORK_DIR/.matplotlib" "$SUBJECT_WORK_DIR/.cache" "$SUBJECT_WORK_DIR/.home"
    
    "$RT_BIN" run --containall \\
      -B "$BIDS_DIR:/data:ro" \\
      -B "$OUT_DIR:/out" \\
      -B "$SUBJECT_WORK_DIR:/work" \\
      -B "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \\
      -B "$TEMPLATEFLOW_HOST:/opt/templateflow" \\
      -B /etc/passwd:/etc/passwd:ro \\
      -B /etc/group:/etc/group:ro \\
      "$CONTAINER" \\
      /data /out $CLI_BASE_STR --participant-label "${{SUBJECT_ID}}" --work-dir /work --fs-license-file /opt/freesurfer/license.txt
    
    local EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 0 ]]; then
      echo "✓ Successfully completed sub-${{SUBJECT_ID}}"
    else
      echo "✗ Failed sub-${{SUBJECT_ID}} with exit code $EXIT_CODE"
    fi
    return $EXIT_CODE
  }}
  
  export -f run_subject
  export RT_BIN BIDS_DIR OUT_DIR WORK_DIR FS_LICENSE TEMPLATEFLOW_HOST CONTAINER
  # Export CLI_BASE array elements individually
  CLI_BASE_STR="${{CLI_BASE[@]}}"
  export CLI_BASE_STR
  
  # Run subjects in parallel
  if [[ $NUM_SUBJECTS -gt 1 ]]; then
    echo "Running $NUM_SUBJECTS subjects in parallel..."
    printf '%s\\n' "${{SUBJECTS[@]}}" | xargs -P $NUM_SUBJECTS -I {{}} bash -c 'run_subject "$@"' _ {{}}
    echo "All parallel jobs completed"
  else
    # Single subject - run directly
    run_subject "${{SUBJECTS[0]}}"
  fi

elif [[ "$RUNTIME" == "fmriprep-docker" ]]; then
  fmriprep-docker "$BIDS_DIR" "$OUT_DIR" "${{CLI[@]}}" --work-dir "$WORK_DIR" --fs-license-file "$FS_LICENSE"

elif [[ "$RUNTIME" == "docker" ]]; then
  # Function to run fMRIPrep for a single subject with Docker
  run_subject_docker() {{
    local SUBJECT_ID="${{1#sub-}}"
    echo "Starting fMRIPrep for sub-${{SUBJECT_ID}} with Docker..."
    
    # Create unique work directory for this subject to avoid conflicts
    local SUBJECT_WORK_DIR="${{WORK_DIR}}/sub-${{SUBJECT_ID}}"
    mkdir -p "$SUBJECT_WORK_DIR"
    
    # Create cache directories for matplotlib and home
    mkdir -p "$SUBJECT_WORK_DIR/.matplotlib" "$SUBJECT_WORK_DIR/.cache" "$SUBJECT_WORK_DIR/.home"
    
    docker run --rm \\
      -e MPLCONFIGDIR=/work/.matplotlib \\
      -e HOME=/work/.home \\
      -e NUMEXPR_MAX_THREADS=$OMP_THREADS \\
      -v "$BIDS_DIR:/data:ro" \\
      -v "$OUT_DIR:/out" \\
      -v "$SUBJECT_WORK_DIR:/work" \\
      -v "$FS_LICENSE:/opt/freesurfer/license.txt:ro" \\
      "$CONTAINER" \\
      /data /out $CLI_BASE_STR --participant-label "${{SUBJECT_ID}}" --fs-license-file /opt/freesurfer/license.txt --work-dir /work
    
    local EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 0 ]]; then
      echo "✓ Successfully completed sub-${{SUBJECT_ID}}"
    else
      echo "✗ Failed sub-${{SUBJECT_ID}} with exit code $EXIT_CODE"
    fi
    return $EXIT_CODE
  }}
  
  export -f run_subject_docker
  export BIDS_DIR OUT_DIR WORK_DIR FS_LICENSE CONTAINER
  # Export CLI_BASE array elements 
  CLI_BASE_STR="${{CLI_BASE[@]}}"
  export CLI_BASE_STR
  
  # Run subjects in parallel
  if [[ $NUM_SUBJECTS -gt 1 ]]; then
    echo "Running $NUM_SUBJECTS subjects in parallel with Docker..."
    printf '%s\\n' "${{SUBJECTS[@]}}" | xargs -P $NUM_SUBJECTS -I {{}} bash -c 'run_subject_docker "$@"' _ {{}}
    echo "All parallel jobs completed"
  else
    # Single subject - run directly
    run_subject_docker "${{SUBJECTS[0]}}"
  fi

else
  echo "Unknown runtime: $RUNTIME" >&2; exit 2
fi
"""

def create_slurm_script(
    cfg: BuildConfig,
    subject_file: Path,
    partition: str,
    time: str,
    cpus_per_task: int,
    mem: Optional[str],  # Make mem optional
    account: Optional[str],
    email: Optional[str],
    mail_type: Optional[str],
    log_dir: Path,
    module_singularity: bool = True,
    job_name: str = "fmriprep",
    subjects_per_job: int = 1,  # New parameter for batching
) -> str:
    try:
        n = len([l for l in subject_file.read_text().splitlines() if l.strip() and not l.strip().startswith("#")])
        array_max = max(0, n - 1)
    except Exception:
        array_max = 0

    account_line = f"#SBATCH --account={account}\n" if account else ""
    mail_line = ""
    if email:
        mail_line = f"#SBATCH --mail-user={email}\n"
        if mail_type:
            mail_line += f"#SBATCH --mail-type={mail_type}\n"
    module_line = "module load singularity\n" if module_singularity and cfg.container_runtime == "singularity" else ""
    
    # Handle memory line - omit if mem is None or "none"
    mem_line = ""
    if mem and mem.lower() != "none":
        mem_line = f"#SBATCH --mem={mem}\n"

    # Use provided templateflow_home or default
    if cfg.templateflow_home:
        templateflow_path = str(cfg.templateflow_home)
    else:
        templateflow_path = "$HOME/.cache/templateflow"
    
    text = SLURM_TEMPLATE.format(
        job_name=job_name,
        partition=partition,
        time=time,
        cpus_per_task=cpus_per_task,
        mem_line=mem_line,  # Use mem_line instead of mem
        array_max=array_max,
        log_dir=str(log_dir),
        account_line=account_line,
        mail_line=mail_line,
        module_line=module_line,
        bids=str(cfg.bids),
        out=str(cfg.out),
        work=str(cfg.work),
        fs_license=str(cfg.fs_license),
        subject_file=str(subject_file),
        runtime=cfg.container_runtime,
        container=cfg.container,
        omp_threads=cfg.omp_threads,
        nprocs=cfg.nprocs,
        mem_mb=cfg.mem_mb,
        extra_flags=cfg.extra,
        skip_bids_val="1" if cfg.skip_bids_validation else "0",
        output_spaces=cfg.output_spaces or "",
        use_aroma="1" if cfg.use_aroma else "0",
        cifti="1" if cfg.cifti_output else "0",
        fs_reconall="1" if cfg.fs_reconall else "0",
        use_syn_sdc="1" if cfg.use_syn_sdc else "0",
        templateflow_home=templateflow_path,
    )
    return text


# ---------------------------- Subject helpers ----------------------------

def resolve_subjects_arg(bids: Path, subjects_arg: List[str]) -> List[str]:
    if len(subjects_arg) == 1 and subjects_arg[0] == "all":
        return discover_subjects(bids)
    subs = []
    for s in subjects_arg:
        s = s.strip()
        if not s:
            continue
        if not s.startswith("sub-"):
            s = f"sub-{s}"
        subs.append(s)
    return sorted(list(dict.fromkeys(subs)))


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
        except:
            default_mem = int(config["mem_mb"])
    p.add_argument("--mem-mb", type=parse_memory_to_mb, default=default_mem,
                   help=help_with_default("--mem-mb (supports units: 32G, 760000M)", "mem_mb", "~90% of available"))
    p.add_argument("--skip-bids-validation", action="store_true", 
                   default=config.get("skip_bids_validation", "").lower() == "true", 
                   help=help_with_default("Pass --skip-bids-validation", "skip_bids_validation"))
    p.add_argument("--output-spaces", type=str, default=config.get("output_spaces"), 
                   help=help_with_default('Output spaces e.g. "MNI152NLin2009cAsym:res-2 T1w fsnative"', "output_spaces"))
    p.add_argument("--use-aroma", action="store_true", 
                   default=config.get("use_aroma", "").lower() == "true",
                   help=help_with_default("Use ICA-AROMA", "use_aroma"))
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

def cmd_probe(_args):
    print("=== Probe ===")
    try:
        rt = detect_runtime("auto")
        print(f"Runtime: {rt}")
    except Exception as e:
        print(f"Runtime: not found ({e})")

    sif_dir = os.environ.get("FMRIPREP_SIF_DIR")
    if sif_dir:
        imgs = discover_sif_images(sif_dir)
        if imgs:
            print(f"SIF images in {sif_dir}:")
            for p in imgs:
                print(f"  - {p.name}")
        else:
            print(f"No fMRIPrep images found in {sif_dir}")
    else:
        print("FMRIPREP_SIF_DIR not set")

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
    out_dir = args.script_outdir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create subject batches
    batches = []
    for i in range(0, len(subjects), subjects_per_job):
        batch = subjects[i:i + subjects_per_job]
        batches.append(" ".join(batch))  # Space-separated subjects per line
    
    subj_file = out_dir / "subjects.txt"
    subj_file.write_text("\n".join(batches) + "\n")
    
    if subjects_per_job > 1:
        print(f"Created {len(batches)} job batches from {len(subjects)} subjects")

    # Handle log directory override
    if args.log_dir:
        log_dir = args.log_dir.expanduser().resolve()
    else:
        log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

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
        module_singularity=args.module_singularity,
        job_name=args.job_name,
        subjects_per_job=subjects_per_job
    )
    script_path = out_dir / "fmriprep_array.sbatch"
    script_path.write_text(text)
    os.chmod(script_path, 0o755)

    print(f"\nWrote Slurm script: {script_path}")
    print(f"Wrote subject list: {subj_file}")
    print("\nSubmit with:")
    print(f"  sbatch {script_path}")

def cmd_wizard(args):
    # Load config for defaults
    config = load_config([args.config] if hasattr(args, 'config') and args.config else [])
    
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
        except:
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
    except:
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
        batches = []
        for i in range(0, len(selected_subjects), subjects_per_job):
            batch = selected_subjects[i:i + subjects_per_job]
            batches.append(" ".join(batch))  # Space-separated subjects per line
        
        subj_file = outdir / "subjects.txt"
        subj_file.write_text("\n".join(batches) + "\n")
        
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

        script_text = create_slurm_script(
            cfg=cfg, subject_file=subj_file, partition=partition, time=time,
            cpus_per_task=cpus_per_task, mem=mem, account=account, email=email,
            mail_type=mail_type, log_dir=log_dir, module_singularity=module_singularity,
            job_name=job_name, subjects_per_job=subjects_per_job
        )
        script_path = outdir / "fmriprep_array.sbatch"
        log_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text)
        os.chmod(script_path, 0o755)
        print(f"\nWrote Slurm script: {script_path}\nSubmit with:\n  sbatch {script_path}")


# ---------------------------- Main ----------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="fmriprep_launcher", 
        description="One-stop fMRIPrep command & Slurm script generator",
        epilog="""
Configuration Files:
  Defaults can be set in INI-format config files. Files are read in order:
    1. /etc/fmriprep/config.ini (system-wide)
    2. ~/.config/fmriprep/config.ini or ~/.fmriprep.ini (user)
    3. ./fmriprep.ini (project-specific)
    4. File specified with --config (highest priority)
  
  Config file format:
    [defaults]
    bids = /path/to/bids
    work = /scratch/work
    container = /path/to/fmriprep.sif
    fs_license = /path/to/license.txt
    runtime = singularity
    nprocs = 8
    omp_threads = 2
    mem_mb = 32000
    skip_bids_validation = true
    output_spaces = MNI152NLin2009cAsym:res-2 T1w
    use_aroma = false
    cifti_output = false
    fs_reconall = false
    use_syn_sdc = false
    extra = --stop-on-first-crash
    subjects = sub-01 sub-02  # or 'all'
    
    [slurm]
    partition = compute
    time = 24:00:00
    cpus_per_task = 8
    mem = 32G
    account = rrg-mylab
    email = user@university.edu
    mail_type = END,FAIL
    job_name = fmriprep
    script_outdir = ./fmriprep_job
    log_dir = /scratch/logs

Environment Variables:
  FMRIPREP_SIF_DIR - Directory containing .sif/.simg files
  FS_LICENSE - FreeSurfer license path (fallback if not in config)
  SLURM_* - Various SLURM variables for resource detection
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", type=str, help="Path to additional config file (overrides defaults)")
    
    # Parse just the config arg first
    config_args, remaining = ap.parse_known_args()
    
    # Load configuration defaults
    config = load_config([config_args.config] if config_args.config else [])
    
    # Now add subparsers
    sub = ap.add_subparsers(dest="cmd", required=True)

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
    p_slurm.add_argument("--log-dir", type=Path, default=None, help="Override log directory (default: script-outdir/logs)")
    p_slurm.add_argument("--no-mem", action="store_true", help="Omit --mem specification (for Trillium cluster)")
    p_slurm.add_argument("--subjects-per-job", type=int, default=1, 
                        help="Number of subjects to process per job (default: 1). "
                             "Values >1 batch multiple subjects together, reducing total jobs but requiring more resources per job.")
    p_slurm.set_defaults(func=cmd_slurm_array)

    # wizard
    p_wiz = sub.add_parser("wizard", help="Interactive setup (questionary if available, else basic prompts)")
    p_wiz.set_defaults(func=cmd_wizard)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
