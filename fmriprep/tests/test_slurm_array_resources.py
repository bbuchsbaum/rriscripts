"""End-to-end checks on the sbatch that `slurm-array` generates.

These drive the launcher as a subprocess because the behavior under test lives
in the CLI glue (resource scaling, path resolution) rather than in the backend.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "fmriprep_launcher.py"

CONFIG = """[defaults]
bids = {bids}
out = {out}
work = {work}
runtime = singularity
container = {container}
fs_license = {license}
nprocs = 4
mem_mb = 8000
"""


def sbatch_directive(text: str, name: str):
    m = re.search(rf"^#SBATCH --{name}=(.+)$", text, re.MULTILINE)
    return m.group(1) if m else None


class SlurmArrayResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name).resolve()

        self.bids = self.root / "bids"
        for sub in ("sub-01", "sub-02", "sub-03", "sub-04"):
            (self.bids / sub / "anat").mkdir(parents=True)
            (self.bids / sub / "anat" / f"{sub}_T1w.nii.gz").touch()
        (self.bids / "dataset_description.json").write_text("{}")

        self.container = self.root / "fmriprep.sif"
        self.container.touch()
        self.license = self.root / "license.txt"
        self.license.touch()
        self.work = self.root / "scratch-work"

        (self.root / "fmriprep.ini").write_text(
            CONFIG.format(
                bids=self.bids,
                out=self.root / "out",
                work=self.work,
                container=self.container,
                license=self.license,
            )
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_slurm_array(self, *extra, cwd=None):
        outdir = self.root / f"bundle_{len(list(self.root.glob('bundle_*')))}"
        proc = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "slurm-array",
                "--subjects",
                "all",
                "--script-outdir",
                str(outdir),
                *extra,
            ],
            cwd=str(cwd or self.root),
            capture_output=True,
            text=True,
            env={**os.environ, "SCRATCH": str(self.root)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return (outdir / "fmriprep_array.sbatch").read_text()

    def test_memory_scales_with_subjects_per_job(self):
        """The SLURM --mem request must scale alongside --cpus-per-task.

        Regression: --mem was taken from the unscaled per-subject value while
        --cpus-per-task used the scaled one, so a batched task was told by
        fMRIPrep it had N x the memory that SLURM had actually allocated.
        """
        one = self.run_slurm_array()
        self.assertEqual(sbatch_directive(one, "cpus-per-task"), "4")
        self.assertEqual(sbatch_directive(one, "mem"), "8G")

        two = self.run_slurm_array("--subjects-per-job", "2")
        self.assertEqual(sbatch_directive(two, "cpus-per-task"), "8")
        self.assertEqual(sbatch_directive(two, "mem"), "16G")

    def test_slurm_mem_matches_what_fmriprep_is_told(self):
        """--mem and fMRIPrep's MEM_MB must describe the same allocation."""
        text = self.run_slurm_array("--subjects-per-job", "2")
        mem_mb = re.search(r'^MEM_MB="(\d+)"$', text, re.MULTILINE)
        self.assertIsNotNone(mem_mb)
        self.assertEqual(int(mem_mb.group(1)), 16000)
        self.assertEqual(sbatch_directive(text, "mem"), "16G")

    def test_explicit_mem_flag_still_wins(self):
        text = self.run_slurm_array("--subjects-per-job", "2", "--mem", "64G")
        self.assertEqual(sbatch_directive(text, "mem"), "64G")

    def test_relative_work_resolves_under_configured_base(self):
        """A bare --work names a subdirectory of the configured work dir."""
        text = self.run_slurm_array("--work", "run2")
        m = re.search(r'^WORK_DIR="(.+)"$', text, re.MULTILINE)
        self.assertIsNotNone(m)
        self.assertEqual(Path(m.group(1)), self.work / "run2")

    def test_work_defaults_to_configured_value(self):
        text = self.run_slurm_array()
        m = re.search(r'^WORK_DIR="(.+)"$', text, re.MULTILINE)
        self.assertEqual(Path(m.group(1)), self.work)

    def test_absolute_work_is_used_as_given(self):
        elsewhere = self.root / "elsewhere"
        text = self.run_slurm_array("--work", str(elsewhere))
        m = re.search(r'^WORK_DIR="(.+)"$', text, re.MULTILINE)
        self.assertEqual(Path(m.group(1)), elsewhere)

    def test_array_range_matches_subject_batches(self):
        one = self.run_slurm_array()
        self.assertEqual(sbatch_directive(one, "array"), "0-3")

        two = self.run_slurm_array("--subjects-per-job", "2")
        self.assertEqual(sbatch_directive(two, "array"), "0-1")


if __name__ == "__main__":
    unittest.main()
