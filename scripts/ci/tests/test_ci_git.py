"""Unit tests for the pure parsers in scripts/ci/ci_git.py.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ci_git = importlib.import_module("ci_git")


class NameStatusTests(unittest.TestCase):
    def test_parses_adds_modifies_renames_copies_and_non_ascii(self):
        out = "A\0pkg/new.py\0M\0pkg/a.py\0R090\0pkg/old.py\0pkg/moved.py\0C100\0pkg/x.py\0pkg/y.py\0M\0pkg/café.py\0"
        files = ci_git.parse_name_status(out)
        self.assertEqual(
            [(f.status, f.head_path, f.base_path) for f in files],
            [
                ("A", "pkg/new.py", None),
                ("M", "pkg/a.py", "pkg/a.py"),
                ("R", "pkg/moved.py", "pkg/old.py"),
                ("C", "pkg/y.py", "pkg/x.py"),
                ("M", "pkg/café.py", "pkg/café.py"),
            ],
        )
        self.assertTrue(files[0].added)
        self.assertFalse(files[2].added)
        self.assertEqual(ci_git.parse_name_status(""), [])


class AddedLinesTests(unittest.TestCase):
    def test_only_plus_lines_per_head_path(self):
        diff = "\n".join([
            "--- a/pkg/a.py",
            "+++ b/pkg/a.py",
            "@@ -3,0 +4,2 @@ def f():",
            "@@ -10 +12 @@",
            "@@ -20,3 +22,0 @@",
            "--- /dev/null",
            "+++ b/pkg/new.py",
            "@@ -0,0 +1,3 @@",
            "--- a/pkg/gone.py",
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
        ])
        self.assertEqual(ci_git.parse_added_lines(diff), {"pkg/a.py": [4, 5, 12], "pkg/new.py": [1, 2, 3]})


class TestPathTests(unittest.TestCase):
    def test_recognises_test_layouts_only(self):
        for path in ["tests/test_a.py", "src/pkg/tests/helpers.py", "pkg/test_x.py", "pkg/x_test.py", "conftest.py", "benches/b.rs", "web/a.test.ts"]:
            self.assertTrue(ci_git.is_test_path(path), path)
        for path in ["src/pkg/testing.py", "src/pkg/contest.py", "src/pkg/attest/x.py", "src/lib.rs"]:
            self.assertFalse(ci_git.is_test_path(path), path)


if __name__ == "__main__":
    unittest.main()
