#!/usr/bin/env python3
"""
Shared backend for fMRIPrep command construction and SLURM script rendering.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from fmriprep_shared import discover_subjects, which


@dataclass
class BuildConfig:
    bids: Path
    out: Path
    work: Path
    subjects: List[str]
    container_runtime: str
    container: str
    fs_license: Path
    templateflow_home: Optional[Path]
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
    bind_templateflow: bool = True


def split_extra_args(extra: str) -> List[str]:
    if not extra.strip():
        return []
    return shlex.split(extra)


def build_base_cli(cfg: BuildConfig, subjects: List[str]) -> List[str]:
    labels = [s.replace("sub-", "") for s in subjects]
    base_cli = [
        "participant",
        "--participant-label",
        *labels,
        "--nprocs",
        str(cfg.nprocs),
        "--omp-nthreads",
        str(cfg.omp_threads),
        "--mem-mb",
        str(cfg.mem_mb),
        "--notrack",
    ]
    if cfg.skip_bids_validation:
        base_cli += ["--skip-bids-validation"]
    if cfg.output_spaces:
        base_cli += ["--output-spaces", *cfg.output_spaces.split()]
    if cfg.use_aroma:
        raise ValueError(
            "--use-aroma was removed in fMRIPrep >= 23.1.0. "
            "Remove use_aroma from your configuration."
        )
    if cfg.cifti_output:
        base_cli += ["--cifti-output", "91k"]
    if not cfg.fs_reconall:
        base_cli += ["--fs-no-reconall"]
    if cfg.use_syn_sdc:
        base_cli += ["--use-syn-sdc"]
    base_cli += split_extra_args(cfg.extra)
    return base_cli


def preflight_check(cfg: BuildConfig) -> List[str]:
    """Validate configuration before SLURM submission. Returns list of errors (empty = OK)."""
    errors: List[str] = []
    if cfg.container_runtime == "singularity" and not Path(cfg.container).is_file():
        errors.append(f"Container image not found: {cfg.container}")
    if not cfg.fs_license.is_file():
        errors.append(f"FreeSurfer license not found: {cfg.fs_license}")
    if not cfg.bids.is_dir():
        errors.append(f"BIDS directory not found: {cfg.bids}")
    if cfg.use_aroma:
        errors.append("use_aroma is set but ICA-AROMA was removed in fMRIPrep >= 23.1.0")
    if not cfg.subjects:
        errors.append("No subjects specified")
    return errors


def resolve_templateflow_home(cfg: BuildConfig) -> Optional[str]:
    if not cfg.bind_templateflow:
        return None
    if cfg.templateflow_home:
        return str(cfg.templateflow_home)
    return os.environ.get("TEMPLATEFLOW_HOME", str(Path.home() / ".cache" / "templateflow"))


def build_fmriprep_command(cfg: BuildConfig, subjects: List[str] | str) -> List[str]:
    """
    Construct the full fMRIPrep command for one or more subjects.
    """
    if isinstance(subjects, str):
        subjects = [subjects]

    base_cli = build_base_cli(cfg, subjects)
    bids_dir_in = "/data"
    out_dir_in = "/out"
    work_dir_in = "/work"
    fs_license_in = "/opt/freesurfer/license.txt"
    templateflow_host = resolve_templateflow_home(cfg)
    templateflow_container = "/opt/templateflow"

    if cfg.container_runtime == "singularity":
        singularity_bin = "apptainer" if which("apptainer") else "singularity"
        cmd = [
            singularity_bin,
            "run",
            "--cleanenv",
            "-B",
            f"{cfg.bids}:{bids_dir_in}:ro",
            "-B",
            f"{cfg.out}:{out_dir_in}",
            "-B",
            f"{cfg.work}:{work_dir_in}",
            "-B",
            f"{cfg.fs_license}:{fs_license_in}:ro",
        ]
        if templateflow_host:
            cmd += ["-B", f"{templateflow_host}:{templateflow_container}"]
            env_prefix = "APPTAINERENV" if singularity_bin == "apptainer" else "SINGULARITYENV"
            cmd = [f"{env_prefix}_TEMPLATEFLOW_HOME={templateflow_container}"] + cmd
        cmd += [
            cfg.container,
            bids_dir_in,
            out_dir_in,
            *base_cli,
            "--work-dir",
            work_dir_in,
            "--fs-license-file",
            fs_license_in,
        ]
        return cmd

    if cfg.container_runtime == "fmriprep-docker":
        cmd = [
            "fmriprep-docker",
            str(cfg.bids),
            str(cfg.out),
            *base_cli,
            "--work-dir",
            str(cfg.work),
            "--fs-license-file",
            str(cfg.fs_license),
        ]
        if templateflow_host:
            cmd += ["--env", f"TEMPLATEFLOW_HOME={templateflow_host}"]
        return cmd

    if cfg.container_runtime == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cfg.bids}:{bids_dir_in}:ro",
            "-v",
            f"{cfg.out}:{out_dir_in}",
            "-v",
            f"{cfg.work}:{work_dir_in}",
            "-v",
            f"{cfg.fs_license}:{fs_license_in}:ro",
        ]
        if templateflow_host:
            cmd += [
                "-v",
                f"{templateflow_host}:{templateflow_container}",
                "-e",
                f"TEMPLATEFLOW_HOME={templateflow_container}",
            ]
        cmd += [
            cfg.container,
            bids_dir_in,
            out_dir_in,
            *base_cli,
            "--work-dir",
            work_dir_in,
            "--fs-license-file",
            fs_license_in,
        ]
        return cmd

    raise ValueError(f"Unknown runtime: {cfg.container_runtime}")


SLURM_TEMPLATE = """\
#!/usr/bin/env bash
#
# Auto-generated by fmriprep backend
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

BIDS_DIR="{bids}"
OUT_DIR="{out}"
WORK_DIR="{work}"
FS_LICENSE="{fs_license}"
SUBJECT_LIST_FILE="{subject_file}"
STATUS_DIR="{status_dir}"
RUNTIME="{runtime}"
CONTAINER="{container}"
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
BIND_TEMPLATEFLOW="{bind_templateflow}"
TEMPLATEFLOW_FALLBACK="{templateflow_home}"

mapfile -t SUBJECT_LINES < <(grep -v '^#' "$SUBJECT_LIST_FILE" | sed '/^$/d')
SUBJECT_LINE="${{SUBJECT_LINES[$SLURM_ARRAY_TASK_ID]}}"
if [[ -z "$SUBJECT_LINE" ]]; then
  echo "No subject(s) for index $SLURM_ARRAY_TASK_ID"; exit 1
fi

IFS=' ' read -ra SUBJECTS <<< "$SUBJECT_LINE"
NUM_SUBJECTS=${{#SUBJECTS[@]}}
echo "=== Processing $NUM_SUBJECTS subject(s) in this job ==="
for SUB in "${{SUBJECTS[@]}}"; do
  echo "  - $SUB"
done

mkdir -p "$OUT_DIR" "$WORK_DIR" "{log_dir}" "$STATUS_DIR"

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
  read -ra _EXTRA <<< "$EXTRA_FLAGS"
  CLI_BASE+=("${{_EXTRA[@]}}")
fi

if [[ "$BIND_TEMPLATEFLOW" == "1" ]]; then
  TEMPLATEFLOW_HOST="${{TEMPLATEFLOW_HOME:-$TEMPLATEFLOW_FALLBACK}}"
  mkdir -p "$TEMPLATEFLOW_HOST"
  echo "TemplateFlow directory: $TEMPLATEFLOW_HOST"
else
  TEMPLATEFLOW_HOST=""
fi

if [[ "$RUNTIME" == "singularity" ]]; then
  # Prefer apptainer when present; fall back to singularity. Detect which one
  # is actually in use via --version output, since `singularity` is often a
  # symlink to apptainer (e.g. on Trillium) and a path-string check would
  # incorrectly pick the SINGULARITYENV_* prefix.
  RT_BIN=$(command -v apptainer || command -v singularity)
  if "$RT_BIN" --version 2>/dev/null | grep -qi apptainer; then
    ENV_PREFIX="APPTAINERENV"
  else
    ENV_PREFIX="SINGULARITYENV"
  fi

  if [[ "$BIND_TEMPLATEFLOW" == "1" ]]; then
    export ${{ENV_PREFIX}}_TEMPLATEFLOW_HOME=/opt/templateflow
  fi
  mkdir -p "$WORK_DIR/.matplotlib" "$WORK_DIR/.cache"
  export ${{ENV_PREFIX}}_MPLCONFIGDIR=/work/.matplotlib
  export ${{ENV_PREFIX}}_NUMEXPR_MAX_THREADS=$OMP_THREADS
  # HOME is set via --home flag below; Apptainer rejects ${{ENV_PREFIX}}_HOME.

  run_subject() {{
    local SUBJECT_ID="${{1#sub-}}"
    local SUBJECT_WORK_DIR="${{WORK_DIR}}/sub-${{SUBJECT_ID}}"
    local -a bind_args

    echo "Starting fMRIPrep for sub-${{SUBJECT_ID}}..."
    rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok" "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
    : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
    mkdir -p "$SUBJECT_WORK_DIR/.matplotlib" "$SUBJECT_WORK_DIR/.cache" "$SUBJECT_WORK_DIR/.home"

    bind_args+=(-B "$BIDS_DIR:/data:ro")
    bind_args+=(-B "$OUT_DIR:/out")
    bind_args+=(-B "$SUBJECT_WORK_DIR:/work")
    bind_args+=(-B "$FS_LICENSE:/opt/freesurfer/license.txt:ro")
    if [[ "$BIND_TEMPLATEFLOW" == "1" ]]; then
      bind_args+=(-B "$TEMPLATEFLOW_HOST:/opt/templateflow")
    fi

    if "$RT_BIN" run --cleanenv \
      --home "$SUBJECT_WORK_DIR/.home" \
      --pwd /work \
      "${{bind_args[@]}}" \
      "$CONTAINER" \
      /data /out ${{CLI_BASE_STR}} --participant-label "${{SUBJECT_ID}}" --work-dir /work --fs-license-file /opt/freesurfer/license.txt; then
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok"
    else
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
      return 1
    fi
  }}

  export -f run_subject
  export RT_BIN BIDS_DIR OUT_DIR WORK_DIR FS_LICENSE TEMPLATEFLOW_HOST CONTAINER OMP_THREADS BIND_TEMPLATEFLOW STATUS_DIR
  CLI_BASE_STR=$(printf '%q ' "${{CLI_BASE[@]}}")
  export CLI_BASE_STR

  if [[ $NUM_SUBJECTS -gt 1 ]]; then
    printf '%s\n' "${{SUBJECTS[@]}}" | xargs -P $NUM_SUBJECTS -I {{}} bash -c 'run_subject "$@"' _ {{}}
  else
    run_subject "${{SUBJECTS[0]}}"
  fi

elif [[ "$RUNTIME" == "fmriprep-docker" ]]; then
  run_subject_wrapper() {{
    local SUBJECT_ID="${{1#sub-}}"
    local SUBJECT_WORK_DIR="${{WORK_DIR}}/sub-${{SUBJECT_ID}}"

    echo "Starting fMRIPrep for sub-${{SUBJECT_ID}} with fmriprep-docker..."
    rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok" "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
    : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
    mkdir -p "$SUBJECT_WORK_DIR"

    if [[ "$BIND_TEMPLATEFLOW" == "1" ]]; then
      export TEMPLATEFLOW_HOME="$TEMPLATEFLOW_HOST"
    fi

    if fmriprep-docker "$BIDS_DIR" "$OUT_DIR" "${{CLI_BASE[@]}}" --participant-label "${{SUBJECT_ID}}" --work-dir "$SUBJECT_WORK_DIR" --fs-license-file "$FS_LICENSE"; then
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok"
    else
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
      return 1
    fi
  }}

  export -f run_subject_wrapper
  export BIDS_DIR OUT_DIR WORK_DIR FS_LICENSE TEMPLATEFLOW_HOST BIND_TEMPLATEFLOW STATUS_DIR

  if [[ $NUM_SUBJECTS -gt 1 ]]; then
    printf '%s\n' "${{SUBJECTS[@]}}" | xargs -P $NUM_SUBJECTS -I {{}} bash -c 'run_subject_wrapper "$@"' _ {{}}
  else
    run_subject_wrapper "${{SUBJECTS[0]}}"
  fi

elif [[ "$RUNTIME" == "docker" ]]; then
  run_subject_docker() {{
    local SUBJECT_ID="${{1#sub-}}"
    local SUBJECT_WORK_DIR="${{WORK_DIR}}/sub-${{SUBJECT_ID}}"
    local -a docker_args

    echo "Starting fMRIPrep for sub-${{SUBJECT_ID}} with Docker..."
    rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok" "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
    : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
    mkdir -p "$SUBJECT_WORK_DIR/.matplotlib" "$SUBJECT_WORK_DIR/.cache" "$SUBJECT_WORK_DIR/.home"

    docker_args+=(-e MPLCONFIGDIR=/work/.matplotlib)
    docker_args+=(-e HOME=/work/.home)
    docker_args+=(-e NUMEXPR_MAX_THREADS=$OMP_THREADS)
    docker_args+=(-v "$BIDS_DIR:/data:ro")
    docker_args+=(-v "$OUT_DIR:/out")
    docker_args+=(-v "$SUBJECT_WORK_DIR:/work")
    docker_args+=(-v "$FS_LICENSE:/opt/freesurfer/license.txt:ro")
    if [[ "$BIND_TEMPLATEFLOW" == "1" ]]; then
      docker_args+=(-e TEMPLATEFLOW_HOME=/opt/templateflow)
      docker_args+=(-v "$TEMPLATEFLOW_HOST:/opt/templateflow")
    fi

    if docker run --rm \
      "${{docker_args[@]}}" \
      "$CONTAINER" \
      /data /out ${{CLI_BASE_STR}} --participant-label "${{SUBJECT_ID}}" --fs-license-file /opt/freesurfer/license.txt --work-dir /work; then
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.ok"
    else
      rm -f "$STATUS_DIR/sub-${{SUBJECT_ID}}.running"
      : > "$STATUS_DIR/sub-${{SUBJECT_ID}}.failed"
      return 1
    fi
  }}

  export -f run_subject_docker
  export BIDS_DIR OUT_DIR WORK_DIR FS_LICENSE CONTAINER OMP_THREADS TEMPLATEFLOW_HOST BIND_TEMPLATEFLOW STATUS_DIR
  CLI_BASE_STR=$(printf '%q ' "${{CLI_BASE[@]}}")
  export CLI_BASE_STR

  if [[ $NUM_SUBJECTS -gt 1 ]]; then
    printf '%s\n' "${{SUBJECTS[@]}}" | xargs -P $NUM_SUBJECTS -I {{}} bash -c 'run_subject_docker "$@"' _ {{}}
  else
    run_subject_docker "${{SUBJECTS[0]}}"
  fi

else
  echo "Unknown runtime: $RUNTIME" >&2
  exit 2
fi
"""


def create_slurm_script(
    cfg: BuildConfig,
    subject_file: Path,
    partition: str,
    time: str,
    cpus_per_task: int,
    mem: Optional[str],
    account: Optional[str],
    email: Optional[str],
    mail_type: Optional[str],
    log_dir: Path,
    status_dir: Path,
    module_singularity: bool = True,
    job_name: str = "fmriprep",
) -> str:
    try:
        n = len([l for l in subject_file.read_text().splitlines() if l.strip() and not l.strip().startswith("#")])
    except OSError:
        n = 0
    if n == 0:
        raise ValueError(f"No subjects found in {subject_file}. Cannot generate SLURM array script with zero subjects.")

    account_line = f"#SBATCH --account={account}\n" if account else ""
    mail_line = ""
    if email:
        mail_line = f"#SBATCH --mail-user={email}\n"
        if mail_type:
            mail_line += f"#SBATCH --mail-type={mail_type}\n"
    module_line = "module load singularity\n" if module_singularity and cfg.container_runtime == "singularity" else ""
    mem_line = f"#SBATCH --mem={mem}\n" if mem and mem.lower() != "none" else ""
    templateflow_path = resolve_templateflow_home(cfg) or ""

    return SLURM_TEMPLATE.format(
        job_name=job_name,
        partition=partition,
        time=time,
        cpus_per_task=cpus_per_task,
        mem_line=mem_line,
        array_max=n - 1,
        log_dir=str(log_dir),
        account_line=account_line,
        mail_line=mail_line,
        module_line=module_line,
        bids=str(cfg.bids),
        out=str(cfg.out),
        work=str(cfg.work),
        fs_license=str(cfg.fs_license),
        subject_file=str(subject_file),
        status_dir=str(status_dir),
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
        bind_templateflow="1" if cfg.bind_templateflow else "0",
        templateflow_home=templateflow_path,
    )


def resolve_subjects_arg(bids: Path, subjects_arg: List[str]) -> List[str]:
    if len(subjects_arg) == 1 and subjects_arg[0] == "all":
        return discover_subjects(bids)
    subs = []
    for subject in subjects_arg:
        subject = subject.strip()
        if not subject:
            continue
        if not subject.startswith("sub-"):
            subject = f"sub-{subject}"
        subs.append(subject)
    return sorted(list(dict.fromkeys(subs)))


def create_subject_batches(subjects: List[str], subjects_per_job: int = 1) -> List[str]:
    size = max(1, subjects_per_job)
    return [" ".join(subjects[i:i + size]) for i in range(0, len(subjects), size)]


def write_subject_batches(path: Path, subjects: List[str], subjects_per_job: int = 1) -> List[str]:
    batches = create_subject_batches(subjects, subjects_per_job)
    path.write_text("\n".join(batches) + "\n")
    return batches


def build_job_manifest(
    cfg: BuildConfig,
    *,
    script_outdir: Path,
    subject_file: Path,
    status_dir: Path,
    log_dir: Path,
    partition: str,
    time: str,
    cpus_per_task: int,
    mem: Optional[str],
    account: Optional[str],
    email: Optional[str],
    mail_type: Optional[str],
    job_name: str,
    module_singularity: bool,
    subjects_per_job: int,
) -> dict:
    return {
        "schema_version": 1,
        "build_config": {
            "bids": str(cfg.bids),
            "out": str(cfg.out),
            "work": str(cfg.work),
            "subjects": list(cfg.subjects),
            "container_runtime": cfg.container_runtime,
            "container": cfg.container,
            "fs_license": str(cfg.fs_license),
            "templateflow_home": str(cfg.templateflow_home) if cfg.templateflow_home else None,
            "omp_threads": cfg.omp_threads,
            "nprocs": cfg.nprocs,
            "mem_mb": cfg.mem_mb,
            "extra": cfg.extra,
            "skip_bids_validation": cfg.skip_bids_validation,
            "output_spaces": cfg.output_spaces,
            "use_aroma": cfg.use_aroma,
            "cifti_output": cfg.cifti_output,
            "fs_reconall": cfg.fs_reconall,
            "use_syn_sdc": cfg.use_syn_sdc,
            "bind_templateflow": cfg.bind_templateflow,
        },
        "job_bundle": {
            "script_outdir": str(script_outdir),
            "subject_file": str(subject_file),
            "status_dir": str(status_dir),
            "log_dir": str(log_dir),
        },
        "slurm": {
            "partition": partition,
            "time": time,
            "cpus_per_task": cpus_per_task,
            "mem": mem,
            "account": account,
            "email": email,
            "mail_type": mail_type,
            "job_name": job_name,
            "module_singularity": module_singularity,
            "subjects_per_job": subjects_per_job,
        },
    }


def build_config_from_manifest(manifest: dict, subjects: Optional[List[str]] = None) -> BuildConfig:
    cfg = manifest["build_config"]
    return BuildConfig(
        bids=Path(cfg["bids"]),
        out=Path(cfg["out"]),
        work=Path(cfg["work"]),
        subjects=list(subjects if subjects is not None else cfg["subjects"]),
        container_runtime=cfg["container_runtime"],
        container=cfg["container"],
        fs_license=Path(cfg["fs_license"]),
        templateflow_home=Path(cfg["templateflow_home"]) if cfg.get("templateflow_home") else None,
        omp_threads=int(cfg["omp_threads"]),
        nprocs=int(cfg["nprocs"]),
        mem_mb=int(cfg["mem_mb"]),
        extra=cfg.get("extra", ""),
        skip_bids_validation=bool(cfg.get("skip_bids_validation", False)),
        output_spaces=cfg.get("output_spaces"),
        use_aroma=bool(cfg.get("use_aroma", False)),
        cifti_output=bool(cfg.get("cifti_output", False)),
        fs_reconall=bool(cfg.get("fs_reconall", False)),
        use_syn_sdc=bool(cfg.get("use_syn_sdc", False)),
        bind_templateflow=bool(cfg.get("bind_templateflow", True)),
    )


def failed_subjects_from_status_dir(status_dir: Path) -> List[str]:
    if not status_dir.exists():
        return []
    subjects = [path.stem.rsplit(".", 1)[0] for path in status_dir.glob("*.failed")]
    return sorted(list(dict.fromkeys(subjects)))
