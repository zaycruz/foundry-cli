"""Unit tests for scripts/ci/regression_proof.py.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
rp = importlib.import_module("regression_proof")

# Shape of `pytest --junitxml` output (pytest 9): a failing case, a passing
# case, a skipped case, and a collection error.
JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4">
<testcase classname="tests.test_a" name="test_fails" time="0.001"><failure message="assert 49 == 50">x</failure></testcase>
<testcase classname="tests.test_a" name="test_passes" time="0.001" />
<testcase classname="tests.test_a" name="test_skipped" time="0.001"><skipped message="later" /></testcase>
<testcase classname="" name="tests.test_b" time="0.000"><error message="collection failure">ImportError</error></testcase>
</testsuite></testsuites>"""


class FixPrTests(unittest.TestCase):
    def test_label_or_conventional_title(self):
        self.assertTrue(rp.is_fix_pr("fix: rounding", []))
        self.assertTrue(rp.is_fix_pr("fix(cli)!: rounding", []))
        self.assertTrue(rp.is_fix_pr("Rounding", ["fix"]))
        self.assertFalse(rp.is_fix_pr("feat: fix later", ["bug"]))
        self.assertFalse(rp.is_fix_pr("fixture: data", []))


class SelectTests(unittest.TestCase):
    def test_carries_test_paths_and_runs_test_modules(self):
        carried, runnable = rp.select_test_files(
            ["src/pkg/core.py", "tests/test_core.py", "tests/conftest.py", "tests/fixtures/row.json", "pkg/io_test.py"]
        )
        self.assertEqual(carried, ["pkg/io_test.py", "tests/conftest.py", "tests/fixtures/row.json", "tests/test_core.py"])
        self.assertEqual(runnable, ["pkg/io_test.py", "tests/test_core.py"])


class JunitTests(unittest.TestCase):
    def test_counts_failures_passes_and_collection_errors_apart(self):
        self.assertEqual(rp.parse_junit(JUNIT), {"passed": 1, "failed": 1, "load_failures": 1})


def r(passed, failed, load=0):
    return {"passed": passed, "failed": failed, "load_failures": load}


class VerdictTests(unittest.TestCase):
    def test_proof_is_a_case_failing_on_base_and_all_passing_on_head(self):
        self.assertTrue(rp.verdict(r(0, 1), r(1, 0))[0])
        self.assertFalse(rp.verdict(r(1, 0), r(1, 0))[0], "passes on base")
        ok, reason = rp.verdict(r(0, 0, 1), r(1, 0))
        self.assertFalse(ok, "a collection error is not proof")
        self.assertIn("not proof", reason)
        self.assertFalse(rp.verdict(r(0, 1), r(1, 1))[0], "must pass on HEAD")
        self.assertFalse(rp.verdict(r(0, 1), r(0, 0))[0], "must run something on HEAD")


if __name__ == "__main__":
    unittest.main()
