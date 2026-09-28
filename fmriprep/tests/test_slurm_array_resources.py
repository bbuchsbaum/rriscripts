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

    def launcher_env(self):
        env = os.environ.copy()
        isolated_home = self.root / "isolated-home"
        env.update(
            {
                "SCRATCH": str(self.root),
                "HOME": str(isolated_home),
                "XDG_CONFIG_HOME": str(isolated_home / ".config"),
            }
        )
        for key in ("FS_LICENSE", "TEMPLATEFLOW_HOME", "FMRIPREP_SIF_DIR"):
            env.pop(key, None)
        return env

    def run_launcher(self, *extra, cwd=None, env=None):
        outdir = self.root / f"bundle_{len(list(self.root.glob('bundle_*')))}"
        proc = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--no-default-config",
                "--config",
                str(self.config_path),
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
            env=self.launcher_env() if env is None else env,
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

    def test_explicit_config_ignores_hostile_user_config(self):
        hostile_home = self.root / "hostile-home"
        hostile_config = hostile_home / ".config" / "fmriprep" / "config.ini"
        hostile_config.parent.mkdir(parents=True)
        leaked_logs = self.root / "leaked-logs"
        hostile_config.write_text(
            f"[slurm]\nno_mem = true\nlog_dir = {leaked_logs}\n"
        )
        env = self.launcher_env()
        env["HOME"] = str(hostile_home)
        env["XDG_CONFIG_HOME"] = str(hostile_home / ".config")

        outdir, proc = self.run_launcher(env=env)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (outdir / "fmriprep_array.sbatch").read_text()
        self.assertEqual(sbatch_directive(text, "mem"), "8G")
        self.assertFalse(leaked_logs.exists())

    def test_warns_when_output_and_work_are_not_on_compute_writable_storage(self):
        output = Path("/project/rrg-test/study/derivatives/fmriprep")
        work = Path("/project/rrg-test/fmriprep-work")
        self.config_path.write_text(
            CONFIG.format(
                bids=self.bids,
                out=output,
                work=work,
                container=self.container,
                license=self.license,
            )
        )

        _, proc = self.run_launcher()

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"Output dir {output} is not under $SCRATCH", proc.stderr)
        self.assertIn(f"Work dir {work} is not under $SCRATCH", proc.stderr)
        self.assertIn(f"--out {self.root / output.name}", proc.stderr)
        self.assertIn(f"--work {self.root / work.name}", proc.stderr)

    def test_compute_writable_output_and_work_do_not_warn(self):
        _, proc = self.run_launcher()

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Output dir", proc.stderr)
        self.assertNotIn("Work dir", proc.stderr)

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
        (status_dir / "sub-04.ok").touch()

        rerun_dir = self.root / "rerun"
        rerun = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--no-default-config",
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
            env=self.launcher_env(),
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


    def run_rerun(self, manifest_path, *extra, env=None):
        return subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--no-default-config",
                "rerun-failed",
                "--manifest",
                str(manifest_path),
                "--script-outdir",
                str(self.root / "rerun"),
                *extra,
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env=self.launcher_env() if env is None else env,
        )

    def fake_squeue_env(self, output):
        bindir = self.root / "fakebin"
        bindir.mkdir(exist_ok=True)
        squeue = bindir / "squeue"
        squeue.write_text(f"#!/bin/sh\nprintf '%s' '{output}'\n")
        squeue.chmod(0o755)
        env = self.launcher_env()
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
        return env

    def test_rerun_includes_subjects_killed_by_slurm_limits(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        status_dir = outdir / "status"
        (status_dir / "sub-01.ok").touch()
        (status_dir / "sub-02.failed").touch()
        (status_dir / "sub-03.running").touch()  # shell killed at TIMEOUT/OOM

        rerun = self.run_rerun(outdir / "job_manifest.json", env=self.fake_squeue_env(""))
        self.assertEqual(rerun.returncode, 0, rerun.stderr)

        rerun_subjects = (self.root / "rerun" / "subjects.txt").read_text().split()
        self.assertEqual(rerun_subjects, ["sub-02", "sub-03", "sub-04"])
        self.assertIn("killed before finishing", rerun.stdout)
        self.assertIn("never started", rerun.stdout)
        self.assertIn("raise --time or --mem", rerun.stdout)

    def test_rerun_refuses_while_original_job_is_still_queued(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (outdir / "status" / "sub-01.running").touch()

        env = self.fake_squeue_env("123_4\n123_5\n")
        rerun = self.run_rerun(outdir / "job_manifest.json", env=env)
        self.assertNotEqual(rerun.returncode, 0)
        self.assertIn("123", rerun.stderr)
        self.assertFalse((self.root / "rerun" / "fmriprep_array.sbatch").exists())

        allowed = self.run_rerun(outdir / "job_manifest.json", "--allow-active", env=env)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_rerun_refuses_while_an_earlier_rerun_is_queued(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (outdir / "status" / "sub-01.failed").touch()
        bindir = self.root / "fakebin"
        bindir.mkdir()
        squeue = bindir / "squeue"
        # Only report jobs when asked about the rerun's name.
        squeue.write_text(
            '#!/bin/sh\ncase "$*" in *fmriprep_rerun*) echo 777_[0-3];; esac\n'
        )
        squeue.chmod(0o755)
        env = self.launcher_env()
        env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

        rerun = self.run_rerun(outdir / "job_manifest.json", env=env)
        self.assertNotEqual(rerun.returncode, 0)
        self.assertIn("777", rerun.stderr)

    def test_rerun_will_not_overwrite_an_existing_rerun_bundle(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (outdir / "status" / "sub-01.failed").touch()
        first = self.run_rerun(outdir / "job_manifest.json")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = (self.root / "rerun" / "subjects.txt").read_text()

        second = self.run_rerun(outdir / "job_manifest.json")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("rerun bundle already exists", second.stderr)
        self.assertIn(str(self.root / "rerun" / "job_manifest.json"), second.stderr)
        self.assertEqual((self.root / "rerun" / "subjects.txt").read_text(), before)

    def test_rerun_time_and_mem_overrides_reach_script_and_manifest(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (outdir / "status" / "sub-01.running").touch()

        rerun = self.run_rerun(
            outdir / "job_manifest.json", "--time", "48:00:00", "--mem", "64G",
            env=self.fake_squeue_env(""),
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        text = (self.root / "rerun" / "fmriprep_array.sbatch").read_text()
        self.assertEqual(sbatch_directive(text, "time"), "48:00:00")
        self.assertEqual(sbatch_directive(text, "mem"), "64G")
        manifest = json.loads((self.root / "rerun" / "job_manifest.json").read_text())
        self.assertEqual(manifest["slurm"]["time"], "48:00:00")
        self.assertEqual(manifest["slurm"]["mem"], "64G")
        self.assertFalse(manifest["slurm"]["mem_auto"])

    def test_rerun_reports_when_everything_finished(self):
        outdir, proc = self.run_launcher()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for sub in ("sub-01", "sub-02", "sub-03", "sub-04"):
            (outdir / "status" / f"{sub}.ok").touch()
        rerun = self.run_rerun(outdir / "job_manifest.json")
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertIn("finished successfully", rerun.stdout)
        self.assertFalse((self.root / "rerun" / "fmriprep_array.sbatch").exists())

    def run_print_cmd(self, *extra, config=None):
        return subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--no-default-config",
                "--config",
                str(config or self.config_path),
                "print-cmd",
                "--subjects",
                "01",
                *extra,
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env=self.launcher_env(),
        )

    def test_print_cmd_uses_per_subject_work_dir_and_reports_settings(self):
        proc = self.run_print_cmd("--extra", '--output-layout "bids derivative"')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"{self.work}/sub-01:/work", proc.stdout)
        self.assertIn(f"$ mkdir -p {self.work}/sub-01/.home", proc.stdout)
        self.assertIn("--home", proc.stdout)
        # Shell-quoted so the printed command can be pasted as is.
        self.assertIn("'bids derivative'", proc.stdout)
        self.assertIn("FreeSurfer recon-all: OFF", proc.stderr)
        self.assertIn("BIDS validation: on", proc.stderr)

    def test_config_booleans_can_be_overridden_on_the_command_line(self):
        cfg = self.root / "science.ini"
        cfg.write_text(
            self.config_path.read_text()
            + "fs_reconall = true\nskip_bids_validation = true\n"
        )
        on = self.run_print_cmd(config=cfg)
        self.assertEqual(on.returncode, 0, on.stderr)
        self.assertNotIn("--fs-no-reconall", on.stdout)
        self.assertIn("--skip-bids-validation", on.stdout)
        self.assertIn("BIDS validation: SKIPPED", on.stderr)

        off = self.run_print_cmd("--no-fs-reconall", "--no-skip-bids-validation", config=cfg)
        self.assertEqual(off.returncode, 0, off.stderr)
        self.assertIn("--fs-no-reconall", off.stdout)
        self.assertNotIn("--skip-bids-validation", off.stdout)

    def test_container_directory_names_the_image_it_picked(self):
        images = self.root / "images"
        images.mkdir()
        old = images / "fmriprep_23.2.0.sif"
        new = images / "fmriprep_24.1.0.sif"
        old.touch()
        new.touch()
        os.utime(old, (1_000_000, 1_000_000))
        proc = self.run_print_cmd("--container", str(images))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("using the most recently modified, fmriprep_24.1.0.sif", proc.stderr)
        self.assertIn("Others: fmriprep_23.2.0.sif", proc.stderr)
        self.assertIn(str(new), proc.stdout)

if __name__ == "__main__":
    unittest.main()
