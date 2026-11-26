"""The rename lint is part of this suite."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINT = HERE / "legacy_names_lint.py"


class LegacyNamesLintTest(unittest.TestCase):
    def test_tree_and_self_test(self):
        for args in ([sys.executable, str(LINT)], [sys.executable, str(LINT), "--self-test"]):
            done = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr or done.stdout)


if __name__ == "__main__":
    unittest.main()
