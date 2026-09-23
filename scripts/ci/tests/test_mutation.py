"""Unit tests for scripts/ci/mutation.py: scope, results parsing, verdict.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import importlib
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mu = importlib.import_module("mutation")

SOURCE = textwrap.dedent('''
    def untouched():
        return 1

    def touched(x):
        if x:
            return 2
        return 3

    class Seat:
        def label(self):
            return "owner"

        def other(self):
            return None
''').lstrip("\n")


class ScopeTests(unittest.TestCase):
    def test_module_name(self):
        self.assertEqual(mu.module_name("src/pkg/sub/mod.py"), "pkg.sub.mod")
        self.assertEqual(mu.module_name("pkg/__init__.py"), "pkg")
        self.assertEqual(mu.module_name("app.py"), "app")

    def test_selectors_cover_touched_functions_and_methods_only(self):
        self.assertEqual(
            mu.selectors("src/pkg/mod.py", SOURCE, [5, 10]),
            ["pkg.mod.x_touched__mutmut_*", "pkg.mod.xǁSeatǁlabel__mutmut_*"],
        )
        self.assertEqual(mu.selectors("src/pkg/mod.py", SOURCE, [9]), [], "a class line is not a function")


RESULTS = """
    pkg.mod.x_touched__mutmut_1: killed
    pkg.mod.x_touched__mutmut_2: survived
    pkg.mod.x_touched__mutmut_3: no tests
    pkg.mod.x_touched__mutmut_4: timeout
    pkg.mod.x_untouched__mutmut_1: survived
    pkg.mod.xǁSeatǁlabel__mutmut_1: survived
    pkg.mod.x_touched__mutmut_5: segfault
"""


class ResultsTests(unittest.TestCase):
    def test_parse_results(self):
        parsed = mu.parse_results(RESULTS)
        self.assertEqual(parsed["pkg.mod.x_touched__mutmut_3"], "no tests")
        self.assertEqual(len(parsed), 7)

    def test_verdict_counts_only_scoped_mutants(self):
        failed, score, undetected = mu.verdict(mu.parse_results(RESULTS), ["pkg.mod.x_touched__mutmut_*"])
        self.assertEqual(score, 25.0, "segfault counts as neither; timeout is undetected")
        self.assertEqual(
            undetected,
            ["pkg.mod.x_touched__mutmut_2", "pkg.mod.x_touched__mutmut_3", "pkg.mod.x_touched__mutmut_4"],
        )
        self.assertTrue(failed, "three undetected exceed the two free survivors at 25%")

    def test_timeouts_and_unchecked_mutants_are_not_detected(self):
        # A starved runner times out on every mutant: that must not score 100%.
        results = {"m.x_f__mutmut_%d" % i: "timeout" for i in range(12)}
        failed, score, undetected = mu.verdict(results, ["m.x_f__mutmut_*"])
        self.assertEqual((failed, score, len(undetected)), (True, 0.0, 12))
        results = {"m.x_f__mutmut_%d" % i: "not checked" for i in range(5)}
        self.assertEqual(mu.verdict(results, ["m.x_f__mutmut_*"])[:2], (True, 0.0))

    def test_a_run_where_no_mutant_got_a_verdict_cannot_pass(self):
        # macOS: mutmut's fork segfaults every mutant; that used to score 100%.
        results = {"m.x_f__mutmut_%d" % i: "segfault" for i in range(5)}
        results["m.x_g__mutmut_1"] = "killed"  # out of scope
        with self.assertRaises(ValueError):
            mu.verdict(results, ["m.x_f__mutmut_*"])

    def test_no_mutant_in_scope_passes_only_when_mutmut_ran_cleanly(self):
        # Decorated functions get no mutants: a clean run passes but says so.
        self.assertIn("Nothing was measured", mu.nothing_in_scope(0, ""))
        # A file where every function is decorated: mutmut makes no mutant and exits 1.
        stopped = "Stopping early, because we could not find any test case for any mutant. It seems ..."
        self.assertIn("Nothing was measured", mu.nothing_in_scope(1, stopped))
        # A run that crashed before making mutants must not pass.
        with self.assertRaises(ValueError):
            mu.nothing_in_scope(1, "failed to collect stats. runner returned 2")

    def test_verdict_fails_over_free_survivors_under_the_floor(self):
        results = {"m.x_f__mutmut_%d" % i: "survived" for i in range(3)}
        self.assertTrue(mu.verdict(results, ["m.x_f__mutmut_*"])[0])
        results.update({"m.x_f__mutmut_%d" % i: "killed" for i in range(3, 10)})
        self.assertFalse(mu.verdict(results, ["m.x_f__mutmut_*"])[0], "7 of 10 detected meets 70%")
        self.assertEqual(mu.verdict({}, ["m.x_f__mutmut_*"])[1], 100.0)


class PyprojectTests(unittest.TestCase):
    def test_inserts_under_existing_table_or_appends_one(self):
        text = '[project]\nname = "x"\n\n[tool.mutmut]\ntests_dir = ["tests/"]\n'
        out = mu.with_source_paths(text, ["src/pkg/a.py"])
        self.assertIn('[tool.mutmut]\nsource_paths = ["src/pkg/a.py"]\ntests_dir', out)
        self.assertTrue(mu.with_source_paths('[project]\nname = "x"\n', ["a.py"]).endswith('[tool.mutmut]\nsource_paths = ["a.py"]\n'))

    def test_refuses_a_repo_level_source_paths_or_its_old_name(self):
        for key in ("source_paths", "paths_to_mutate"):
            with self.assertRaises(ValueError):
                mu.with_source_paths('[tool.mutmut]\n%s = ["src/"]\n' % key, ["a.py"])


if __name__ == "__main__":
    unittest.main()
