import os
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fmriprep_shared import resolve_work_dir  # noqa: E402


class ResolveWorkDirTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name).resolve()
        self.prev_cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.tmpdir.cleanup()

    def test_relative_work_joins_configured_base(self):
        """--work run2 with a configured base means <base>/run2, not ./run2."""
        base = "/scratch/me/fmriprep-work"
        self.assertEqual(
            resolve_work_dir(Path("run2"), base),
            Path("/scratch/me/fmriprep-work/run2"),
        )

    def test_relative_multi_segment_joins_configured_base(self):
        base = "/scratch/me/fmriprep-work"
        self.assertEqual(
            resolve_work_dir(Path("study/run2"), base),
            Path("/scratch/me/fmriprep-work/study/run2"),
        )

    def test_absolute_work_overrides_configured_base(self):
        """An absolute --work is used as given, base or no base."""
        # Resolved on both sides: /tmp is a symlink to /private/tmp on macOS.
        self.assertEqual(
            resolve_work_dir(Path("/tmp/elsewhere"), "/scratch/me/fmriprep-work"),
            Path("/tmp/elsewhere").resolve(),
        )
        self.assertEqual(
            resolve_work_dir(Path("/tmp/elsewhere"), None),
            Path("/tmp/elsewhere").resolve(),
        )

    def test_omitted_work_does_not_double_the_base(self):
        """When --work is omitted the config value arrives as the argument."""
        base = "/scratch/me/fmriprep-work"
        self.assertEqual(resolve_work_dir(Path(base), base), Path(base))

    def test_omitted_relative_work_does_not_double_the_base(self):
        base = "relative-work"
        self.assertEqual(
            resolve_work_dir(Path(base), base), (self.root / base).resolve()
        )

    def test_relative_work_without_base_uses_cwd(self):
        """Backwards compatible: no configured base means CWD, as before."""
        self.assertEqual(
            resolve_work_dir(Path("run2"), None), (self.root / "run2").resolve()
        )
        self.assertEqual(
            resolve_work_dir(Path("run2"), ""), (self.root / "run2").resolve()
        )

    def test_user_expansion(self):
        self.assertEqual(
            resolve_work_dir(Path("~/w"), None), (Path.home() / "w").resolve()
        )
        self.assertEqual(
            resolve_work_dir(Path("run2"), "~/base"),
            (Path.home() / "base" / "run2").resolve(),
        )

    def test_accepts_str_input(self):
        self.assertEqual(
            resolve_work_dir("run2", "/scratch/me/w"), Path("/scratch/me/w/run2")
        )


if __name__ == "__main__":
    unittest.main()
