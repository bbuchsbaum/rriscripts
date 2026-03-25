import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fmriprep_backend import (  # noqa: E402
    BuildConfig,
    build_config_from_manifest,
    build_job_manifest,
    build_fmriprep_command,
    create_slurm_script,
    create_subject_batches,
    failed_subjects_from_status_dir,
    preflight_check,
    resolve_subjects_arg,
    write_subject_batches,
)


class FMRIPrepBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.bids = self.root / "bids"
        self.out = self.root / "out"
        self.work = self.root / "work"
        self.fs_license = self.root / "license.txt"
        self.templateflow = self.root / "templateflow"
        self.bids.mkdir()
        self.out.mkdir()
        self.work.mkdir()
        self.templateflow.mkdir()
        self.fs_license.write_text("license")

    def tearDown(self):
        self.tmpdir.cleanup()

    def build_cfg(self, **overrides):
        cfg = BuildConfig(
            bids=self.bids,
            out=self.out,
            work=self.work,
            subjects=["sub-01", "sub-02"],
            container_runtime="singularity",
            container="/containers/fmriprep.sif",
            fs_license=self.fs_license,
            templateflow_home=self.templateflow,
            omp_threads=4,
            nprocs=8,
            mem_mb=32000,
            extra='--output-layout "bids derivative"',
            skip_bids_validation=True,
            output_spaces="MNI152NLin2009cAsym:res-2 T1w",
            use_aroma=False,
            cifti_output=False,
            fs_reconall=True,
            use_syn_sdc=True,
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

    def test_build_singularity_command_uses_shared_options(self):
        cfg = self.build_cfg()
        with mock.patch("fmriprep_backend.which", side_effect=lambda cmd: "/usr/bin/singularity" if cmd == "singularity" else None):
            cmd = build_fmriprep_command(cfg, ["sub-01", "sub-02"])

        self.assertEqual(cmd[0], "SINGULARITYENV_TEMPLATEFLOW_HOME=/opt/templateflow")
        self.assertEqual(cmd[1:4], ["singularity", "run", "--cleanenv"])
        self.assertIn("--participant-label", cmd)
        self.assertIn("01", cmd)
        self.assertIn("02", cmd)
        self.assertIn("--use-syn-sdc", cmd)
        self.assertIn("bids derivative", cmd)

    def test_build_docker_command_skips_templateflow_when_disabled(self):
        cfg = self.build_cfg(
            container_runtime="docker",
            container="nipreps/fmriprep:latest",
            bind_templateflow=False,
            templateflow_home=None,
        )
        cmd = build_fmriprep_command(cfg, "sub-01")
        joined = " ".join(cmd)
        self.assertIn("docker run --rm", joined)
        self.assertNotIn("/opt/templateflow", joined)

    def test_write_subject_batches_groups_subjects(self):
        subject_file = self.root / "subjects.txt"
        batches = write_subject_batches(subject_file, ["sub-01", "sub-02", "sub-03"], subjects_per_job=2)
        self.assertEqual(batches, ["sub-01 sub-02", "sub-03"])
        self.assertEqual(subject_file.read_text(), "sub-01 sub-02\nsub-03\n")

    def test_create_slurm_script_reflects_batch_file(self):
        cfg = self.build_cfg()
        subject_file = self.root / "subjects.txt"
        write_subject_batches(subject_file, ["sub-01", "sub-02", "sub-03"], subjects_per_job=2)
        status_dir = self.root / "status"
        status_dir.mkdir()

        script = create_slurm_script(
            cfg=cfg,
            subject_file=subject_file,
            partition="compute",
            time="24:00:00",
            cpus_per_task=16,
            mem="64G",
            account="rrg-demo",
            email=None,
            mail_type=None,
            log_dir=self.root / "logs",
            status_dir=status_dir,
            module_singularity=True,
            job_name="fmriprep_test",
        )

        self.assertIn("#SBATCH --array=0-1", script)
        self.assertIn('BIND_TEMPLATEFLOW="1"', script)
        self.assertIn('STATUS_DIR="' + str(status_dir) + '"', script)
        self.assertIn('TEMPLATEFLOW_FALLBACK="' + str(self.templateflow) + '"', script)
        self.assertIn('SUBJECT_LIST_FILE="' + str(subject_file) + '"', script)

    def test_resolve_subjects_arg_discovers_all(self):
        (self.bids / "sub-01").mkdir()
        (self.bids / "sub-02").mkdir()
        resolved = resolve_subjects_arg(self.bids, ["all"])
        self.assertEqual(resolved, ["sub-01", "sub-02"])

    def test_build_job_manifest_round_trips_back_to_config(self):
        cfg = self.build_cfg(bind_templateflow=False, templateflow_home=None)
        subject_file = self.root / "subjects.txt"
        status_dir = self.root / "status"
        log_dir = self.root / "logs"
        write_subject_batches(subject_file, cfg.subjects)
        status_dir.mkdir()
        log_dir.mkdir()

        manifest = build_job_manifest(
            cfg,
            script_outdir=self.root / "job",
            subject_file=subject_file,
            status_dir=status_dir,
            log_dir=log_dir,
            partition="compute",
            time="12:00:00",
            cpus_per_task=8,
            mem="32G",
            account=None,
            email=None,
            mail_type=None,
            job_name="demo",
            module_singularity=False,
            subjects_per_job=1,
        )
        restored = build_config_from_manifest(manifest, ["sub-02"])

        self.assertEqual(restored.subjects, ["sub-02"])
        self.assertFalse(restored.bind_templateflow)
        self.assertEqual(restored.container_runtime, "singularity")
        self.assertEqual(restored.mem_mb, 32000)

    def test_failed_subjects_discovery_reads_marker_files(self):
        status_dir = self.root / "status"
        status_dir.mkdir()
        (status_dir / "sub-03.failed").write_text("")
        (status_dir / "sub-01.failed").write_text("")
        (status_dir / "sub-02.ok").write_text("")

        self.assertEqual(failed_subjects_from_status_dir(status_dir), ["sub-01", "sub-03"])

    # --- Preflight checks ---

    def test_preflight_passes_when_everything_exists(self):
        container = self.root / "fmriprep.sif"
        container.write_text("fake")
        cfg = self.build_cfg(container=str(container))
        errors = preflight_check(cfg)
        self.assertEqual(errors, [])

    def test_preflight_catches_missing_container(self):
        cfg = self.build_cfg(container="/nonexistent/fmriprep.sif")
        errors = preflight_check(cfg)
        self.assertTrue(any("Container image not found" in e for e in errors))

    def test_preflight_catches_missing_fs_license(self):
        self.fs_license.unlink()
        cfg = self.build_cfg()
        errors = preflight_check(cfg)
        self.assertTrue(any("FreeSurfer license" in e for e in errors))

    def test_preflight_catches_missing_bids_dir(self):
        import shutil
        shutil.rmtree(self.bids)
        cfg = self.build_cfg()
        errors = preflight_check(cfg)
        self.assertTrue(any("BIDS directory" in e for e in errors))

    def test_preflight_catches_use_aroma(self):
        container = self.root / "fmriprep.sif"
        container.write_text("fake")
        cfg = self.build_cfg(container=str(container), use_aroma=True)
        errors = preflight_check(cfg)
        self.assertTrue(any("use_aroma" in e for e in errors))

    def test_preflight_catches_no_subjects(self):
        container = self.root / "fmriprep.sif"
        container.write_text("fake")
        cfg = self.build_cfg(container=str(container), subjects=[])
        errors = preflight_check(cfg)
        self.assertTrue(any("No subjects" in e for e in errors))

    def test_preflight_skips_container_check_for_docker(self):
        cfg = self.build_cfg(
            container_runtime="docker",
            container="nipreps/fmriprep:latest",
        )
        errors = preflight_check(cfg)
        self.assertFalse(any("Container image not found" in e for e in errors))

    # --- Docker and fmriprep-docker commands ---

    def test_build_docker_command_includes_volumes(self):
        cfg = self.build_cfg(
            container_runtime="docker",
            container="nipreps/fmriprep:23.2.0",
        )
        cmd = build_fmriprep_command(cfg, "sub-01")
        joined = " ".join(cmd)
        self.assertIn("docker run --rm", joined)
        self.assertIn("-v", joined)
        self.assertIn("/data:ro", joined)
        self.assertIn("--participant-label", joined)
        self.assertIn("01", cmd)

    def test_build_fmriprep_docker_command(self):
        cfg = self.build_cfg(
            container_runtime="fmriprep-docker",
            container="",
            bind_templateflow=False,
            templateflow_home=None,
        )
        cmd = build_fmriprep_command(cfg, "sub-01")
        self.assertEqual(cmd[0], "fmriprep-docker")
        self.assertIn("--participant-label", cmd)
        self.assertIn("--work-dir", cmd)

    def test_build_command_unknown_runtime_raises(self):
        cfg = self.build_cfg(container_runtime="podman")
        with self.assertRaises(ValueError):
            build_fmriprep_command(cfg, "sub-01")

    # --- use_aroma hard error ---

    def test_build_command_raises_on_use_aroma(self):
        cfg = self.build_cfg(use_aroma=True)
        with mock.patch("fmriprep_backend.which", return_value="/usr/bin/singularity"):
            with self.assertRaises(ValueError) as ctx:
                build_fmriprep_command(cfg, "sub-01")
            self.assertIn("removed", str(ctx.exception))

    # --- Subject resolution edge cases ---

    def test_resolve_subjects_arg_normalizes_prefix(self):
        resolved = resolve_subjects_arg(self.bids, ["01", "sub-02", "03"])
        self.assertEqual(resolved, ["sub-01", "sub-02", "sub-03"])

    def test_resolve_subjects_arg_deduplicates(self):
        resolved = resolve_subjects_arg(self.bids, ["sub-01", "01", "sub-01"])
        self.assertEqual(resolved, ["sub-01"])

    def test_resolve_subjects_arg_skips_blank(self):
        resolved = resolve_subjects_arg(self.bids, ["sub-01", "", "  ", "sub-02"])
        self.assertEqual(resolved, ["sub-01", "sub-02"])

    # --- Subject batching edge cases ---

    def test_create_subject_batches_single(self):
        batches = create_subject_batches(["sub-01", "sub-02", "sub-03"], 1)
        self.assertEqual(batches, ["sub-01", "sub-02", "sub-03"])

    def test_create_subject_batches_larger_than_list(self):
        batches = create_subject_batches(["sub-01", "sub-02"], 5)
        self.assertEqual(batches, ["sub-01 sub-02"])

    def test_create_subject_batches_zero_treated_as_one(self):
        batches = create_subject_batches(["sub-01", "sub-02"], 0)
        self.assertEqual(batches, ["sub-01", "sub-02"])

    # --- SLURM script edge cases ---

    def test_slurm_script_omits_mem_when_none(self):
        cfg = self.build_cfg()
        subject_file = self.root / "subjects.txt"
        write_subject_batches(subject_file, ["sub-01"])
        status_dir = self.root / "status"
        status_dir.mkdir()

        script = create_slurm_script(
            cfg=cfg, subject_file=subject_file,
            partition="compute", time="8:00:00",
            cpus_per_task=8, mem=None, account=None,
            email=None, mail_type=None,
            log_dir=self.root / "logs",
            status_dir=status_dir,
        )
        self.assertNotIn("#SBATCH --mem=", script)
        self.assertNotIn("#SBATCH --account=", script)

    def test_slurm_script_includes_email_when_set(self):
        cfg = self.build_cfg()
        subject_file = self.root / "subjects.txt"
        write_subject_batches(subject_file, ["sub-01"])
        status_dir = self.root / "status"
        status_dir.mkdir()

        script = create_slurm_script(
            cfg=cfg, subject_file=subject_file,
            partition="compute", time="8:00:00",
            cpus_per_task=8, mem="16G", account="rrg-test",
            email="user@example.com", mail_type="END",
            log_dir=self.root / "logs",
            status_dir=status_dir,
        )
        self.assertIn("#SBATCH --mail-user=user@example.com", script)
        self.assertIn("#SBATCH --mail-type=END", script)
        self.assertIn("#SBATCH --account=rrg-test", script)

    def test_slurm_script_empty_subject_file_raises(self):
        cfg = self.build_cfg()
        subject_file = self.root / "subjects.txt"
        subject_file.write_text("")
        status_dir = self.root / "status"
        status_dir.mkdir()

        with self.assertRaises(ValueError):
            create_slurm_script(
                cfg=cfg, subject_file=subject_file,
                partition="compute", time="8:00:00",
                cpus_per_task=8, mem="16G", account=None,
                email=None, mail_type=None,
                log_dir=self.root / "logs",
                status_dir=status_dir,
            )


if __name__ == "__main__":
    unittest.main()
