#!/usr/bin/env python3
"""
Shared backend helpers for the fMRIPrep tools in this directory.

This module centralizes the duplicated logic that was previously spread across
the launcher, Textual frontend, Tk frontend, and legacy questionary builder.
"""

from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def load_config(config_paths: List[str] | None = None) -> Dict[str, str]:
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

    default_paths = [
        "/etc/fmriprep/config.ini",
        Path.home() / ".config" / "fmriprep" / "config.ini",
        Path.home() / ".fmriprep.ini",
        Path.cwd() / "fmriprep.ini",
    ]

    config = configparser.ConfigParser(inline_comment_prefixes=('#',))
    defaults: Dict[str, str] = {}

    for path in default_paths + [Path(p) for p in config_paths]:
        if isinstance(path, str):
            path = Path(path)
        if path.exists():
            config.read(path)
            if "defaults" in config:
                defaults.update(dict(config["defaults"]))
            if "slurm" in config:
                for key, value in config["slurm"].items():
                    defaults[f"slurm_{key}"] = value

    # Expand $VAR and ~ in all values
    return {k: os.path.expandvars(os.path.expanduser(v)) for k, v in defaults.items()}


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def run_cmd(cmd: List[str], check: bool = False) -> Tuple[int, str, str]:
    """Run a command and capture (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:
        return 1, "", str(exc)


def parse_memory_to_mb(value: str | int) -> int:
    """Parse memory string (e.g., '32G', '760000', '2T') to MB."""
    if isinstance(value, int):
        return value

    value = str(value).strip().upper()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$", value)
    if match:
        num = float(match.group(1))
        unit = match.group(2)

        if unit == "K":
            return int(num / 1024)
        if unit in ("M", ""):
            return int(num)
        if unit == "G":
            return int(num * 1024)
        if unit == "T":
            return int(num * 1024 * 1024)

    try:
        return int(float(value))
    except Exception as exc:
        raise ValueError(f"Cannot parse memory value: {value}") from exc


def mb_to_human(mb: int) -> str:
    """Convert integer MB to a compact Slurm-friendly string."""
    if mb >= 1_000_000:
        tb = mb / 1_000_000
        if abs(tb - round(tb)) < 0.05:
            return f"{round(tb)}T"
        return f"{tb:.1f}T"
    if mb >= 1000:
        gb = mb / 1000
        if abs(gb - round(gb)) < 0.05:
            return f"{round(gb)}G"
        return f"{gb:.1f}G"
    return f"{mb}M"


def read_meminfo_mb() -> int:
    """Rough system memory from /proc/meminfo in MB."""
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 16000


def default_resources_from_env() -> Tuple[int, int]:
    """
    Return (cpus, mem_mb) from Slurm env or system.
    Leaves ~10% headroom for safety.
    """
    import os

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


def detect_runtime_optional() -> Optional[str]:
    """Best-effort runtime detection without raising."""
    if which("singularity") or which("apptainer"):
        return "singularity"
    if which("fmriprep-docker"):
        return "fmriprep-docker"
    if which("docker"):
        return "docker"
    return None


def detect_runtime(prefer: str = "auto") -> str:
    """
    Determine container runtime: 'singularity', 'fmriprep-docker', or 'docker'.
    Treat Apptainer as 'singularity'.
    """
    if prefer in ("singularity", "docker", "fmriprep-docker"):
        return prefer

    detected = detect_runtime_optional()
    if detected:
        return detected

    raise RuntimeError(
        "No container runtime found. Install Singularity/Apptainer, "
        "fmriprep-docker, or Docker."
    )


def detect_runtime_auto(default: str = "singularity") -> str:
    """Best-effort runtime detection with a caller-chosen fallback."""
    return detect_runtime_optional() or default


def discover_sif_images(search_dir: Optional[str] = None) -> List[Path]:
    """Return fMRIPrep .sif/.simg images from a directory (non-recursive)."""
    import os

    candidates: List[Path] = []
    chosen_dir = search_dir if search_dir is not None else os.environ.get("FMRIPREP_SIF_DIR")
    if chosen_dir:
        directory = Path(chosen_dir).expanduser()
        if directory.is_dir():
            for path in directory.iterdir():
                if path.suffix.lower() in (".sif", ".simg") and "fmriprep" in path.name.lower():
                    candidates.append(path)
    return sorted(candidates)


def docker_list_fmriprep_images() -> List[str]:
    """Return local docker image:tag strings for fMRIPrep."""
    if not which("docker"):
        return []
    rc, out, _ = run_cmd(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    if rc != 0:
        return []
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return [line for line in lines if re.match(r"^(nipreps|poldracklab|fmriprep)/fmriprep(:|$)", line)]


def parse_participants_tsv(bids_dir: Path) -> List[str]:
    participants_file = bids_dir / "participants.tsv"
    subjects: List[str] = []
    if participants_file.exists():
        with open(participants_file, "r", newline="") as tsvfile:
            import csv

            reader = csv.DictReader(tsvfile, delimiter="\t")
            if not reader.fieldnames:
                return subjects
            column = "participant_id" if "participant_id" in reader.fieldnames else reader.fieldnames[0]
            for row in reader:
                raw = str(row[column]).strip()
                if raw:
                    subjects.append(raw if raw.startswith("sub-") else f"sub-{raw}")
    return sorted(list(dict.fromkeys(subjects)))


def scan_bids_for_subjects(bids_dir: Path) -> List[str]:
    return sorted(path.name for path in bids_dir.iterdir() if path.is_dir() and path.name.startswith("sub-"))


def discover_subjects(bids_dir: Path) -> List[str]:
    subjects = parse_participants_tsv(bids_dir)
    return subjects if subjects else scan_bids_for_subjects(bids_dir)
