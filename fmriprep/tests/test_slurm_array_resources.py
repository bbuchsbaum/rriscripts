"""End-to-end checks on the sbatch that `slurm-array` generates.

These drive the launcher as a subprocess because the behavior under test lives
in the CLI glue (resource scaling, path resolution) rather than in the backend.
"""

import json
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

        self.config_path = self.root / "fmriprep.ini"
        self.config_path.write_text(
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

    def run_launcher(self, *extra, cwd=None):
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
        return outdir, proc

    def run_slurm_array(self, *extra, cwd=None):
        outdir, proc = self.run_launcher(*extra, cwd=cwd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return (outdir / "fmriprep_array.sbatch").read_text()

    def test_default_parallelism_matches_batch_size(self):
        one = self.run_slurm_array()
        self.assertEqual(sbatch_directive(one, "cpus-per-task"), "4")
        self.assertEqual(sbatch_directive(one, "mem"), "8G")
        self.assertIn('PARALLEL_SUBJECTS="1"', one)

        two = self.run_slurm_array("--subjects-per-job", "2")
        self.assertEqual(sbatch_directive(two, "cpus-per-task"), "8")
        self.assertEqual(sbatch_directive(two, "mem"), "16G")
        self.assertIn('PARALLEL_SUBJECTS="2"', two)

    def test_per_subject_limits_are_not_scaled(self):
        """Each child gets per-subject limits; only its task allocation scales."""
        text = self.run_slurm_array("--subjects-per-job", "2")

        self.assertIn('NPROCS="4"', text)
        self.assertIn('MEM_MB="8000"', text)
        self.assertIn('PARALLEL_SUBJECTS="2"', text)
        self.assertIn('xargs -P "$PARALLEL_SUBJECTS"', text)
        self.assertEqual(sbatch_directive(text, "cpus-per-task"), "8")
        self.assertEqual(sbatch_directive(text, "mem"), "16G")

    def test_batch_size_and_within_task_parallelism_are_independent(self):
        text = self.run_slurm_array(
            "--subjects-per-job", "4", "--parallel-subjects", "2"
        )

        self.assertEqual(sbatch_directive(text, "array"), "0-0")
        self.assertEqual(sbatch_directive(text, "cpus-per-task"), "8")
        self.assertEqual(sbatch_directive(text, "mem"), "16G")
        self.assertIn('NPROCS="4"', text)
        self.assertIn('MEM_MB="8000"', text)
        self.assertIn('PARALLEL_SUBJECTS="2"', text)

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

    def test_array_concurrency_and_exclusive_are_rendered(self):
        text = self.run_slurm_array(
            "--array-concurrency", "2", "--exclusive"
        )
        self.assertEqual(sbatch_directive(text, "array"), "0-3%2")
        self.assertIn("#SBATCH --exclusive", text)

    def test_ini_controls_all_three_counts_and_exclusivity(self):
        with self.config_path.open("a") as config:
            config.write(
                "\n[slurm]\n"
                "subjects_per_job = 4\n"
                "parallel_subjects = 2\n"
                "array_concurrency = 3\n"
                "exclusive = true\n"
            )

        text = self.run_slurm_array()

        self.assertEqual(sbatch_directive(text, "array"), "0-0%3")
        self.assertEqual(sbatch_directive(text, "cpus-per-task"), "8")
        self.assertEqual(sbatch_directive(text, "mem"), "16G")
        self.assertIn('PARALLEL_SUBJECTS="2"', text)
        self.assertIn("#SBATCH --exclusive", text)

    def test_parallel_subjects_cannot_exceed_batch_size(self):
        _, proc = self.run_launcher(
            "--subjects-per-job", "2", "--parallel-subjects", "3"
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(
            "--parallel-subjects cannot exceed --subjects-per-job", proc.stderr
        )

    def test_counts_must_be_positive(self):
        _, proc = self.run_launcher("--subjects-per-job", "0")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("expected a positive integer", proc.stderr)

    def test_manifest_records_both_levels_of_concurrency(self):
        outdir, proc = self.run_launcher(
            "--subjects-per-job", "4",
            "--parallel-subjects", "2",
            "--array-concurrency", "3",
            "--exclusive",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads((outdir / "job_manifest.json").read_text())

        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["build_config"]["nprocs"], 4)
        self.assertEqual(manifest["build_config"]["mem_mb"], 8000)
        self.assertEqual(manifest["slurm"]["subjects_per_job"], 4)
        self.assertEqual(manifest["slurm"]["parallel_subjects"], 2)
        self.assertEqual(manifest["slurm"]["array_concurrency"], 3)
        self.assertTrue(manifest["slurm"]["exclusive"])
        self.assertTrue(manifest["slurm"]["cpus_per_task_auto"])
        self.assertTrue(manifest["slurm"]["mem_auto"])

    def test_rerun_inherits_concurrency_and_recalculates_auto_resources(self):
        outdir, proc = self.run_launcher(
            "--subjects-per-job", "4",
            "--parallel-subjects", "2",
            "--array-concurrency", "3",
            "--exclusive",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest_path = outdir / "job_manifest.json"
        status_dir = outdir / "status"
        for subject in ("sub-01", "sub-02", "sub-03"):
            (status_dir / f"{subject}.failed").touch()

        rerun_dir = self.root / "rerun"
        rerun = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "rerun-failed",
                "--manifest",
                str(manifest_path),
                "--script-outdir",
                str(rerun_dir),
                "--subjects-per-job",
                "2",
                "--parallel-subjects",
                "1",
                "--array-concurrency",
                "1",
                "--no-exclusive",
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)

        text = (rerun_dir / "fmriprep_array.sbatch").read_text()
        self.assertEqual(sbatch_directive(text, "array"), "0-1%1")
        self.assertEqual(sbatch_directive(text, "cpus-per-task"), "4")
        self.assertEqual(sbatch_directive(text, "mem"), "8G")
        self.assertIn('NPROCS="4"', text)
        self.assertIn('MEM_MB="8000"', text)
        self.assertIn('PARALLEL_SUBJECTS="1"', text)
        self.assertNotIn("#SBATCH --exclusive", text)

        rerun_manifest = json.loads((rerun_dir / "job_manifest.json").read_text())
        self.assertEqual(rerun_manifest["slurm"]["subjects_per_job"], 2)
        self.assertEqual(rerun_manifest["slurm"]["parallel_subjects"], 1)
        self.assertEqual(rerun_manifest["slurm"]["array_concurrency"], 1)
        self.assertFalse(rerun_manifest["slurm"]["exclusive"])


if __name__ == "__main__":
    unittest.main()
