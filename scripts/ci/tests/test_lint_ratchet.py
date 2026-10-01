"""Unit tests for the pure logic in scripts/ci/lint_ratchet.py.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import ast
import importlib.util
import io
import sys
import textwrap
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "lint_ratchet.py"
sys.path.insert(0, str(SCRIPT.parent))  # the script imports its sibling ci_git.py
spec = importlib.util.spec_from_file_location("lint_ratchet", SCRIPT)
lr = importlib.util.module_from_spec(spec)
sys.modules["lint_ratchet"] = lr
spec.loader.exec_module(lr)


def source(text):
    return textwrap.dedent(text).lstrip("\n")


class SizeTests(unittest.TestCase):
    def test_file_lines_skip_blank_and_comment_lines(self):
        self.assertEqual(lr.count_file_lines("a = 1\n\n# c\n   # c\nb = 2\n"), 2)

    def test_long_functions_counts_code_lines_in_the_span(self):
        body = "\n".join("    x%d = %d" % (i, i) for i in range(81))
        text = "def big():\n" + body + "\n\ndef small():\n    return 1\n"
        self.assertEqual(lr.long_functions(text, ast.parse(text)), ["big"])
        padded = "def ok():\n" + "\n".join("    # c\n\n    y = 1" for _ in range(40)) + "\n"
        self.assertEqual(lr.long_functions(padded, ast.parse(padded)), [], "comments and blanks do not count")


class AssertionFreeTests(unittest.TestCase):
    def test_flags_tests_that_check_nothing(self):
        tree = ast.parse(source('''
            import pytest

            def test_runs():
                compute()

            def test_asserts():
                assert compute() == 2

            def test_raises():
                with pytest.raises(ValueError):
                    compute(-1)

            def test_helper():
                expect_shape(compute())

            async def test_async_nothing():
                await compute()

            def helper():
                pass

            class TestThing:
                def test_unittest_style(self):
                    self.assertEqual(compute(), 2)

                def test_mock(self, m):
                    m.assert_called_once_with(1)

                def test_nothing(self):
                    compute()

            class Helper:
                def test_not_collected(self):
                    compute()
        '''))
        self.assertEqual(lr.assertion_free_tests(tree), ["test_runs", "test_async_nothing", "test_nothing"])


class NoqaTests(unittest.TestCase):
    def test_counts_comments_not_strings(self):
        text = source('''
            import os  # noqa: F401
            x = 1  # noqa
            y = "# noqa: C901"
            def f():  # noqa: C901, PLR0913
                pass
        ''')
        self.assertEqual(lr.noqa_comments(text), [["F401"], None, ["C901", "PLR0913"]])

    def test_restricted_are_blanket_and_tier2_codes(self):
        self.assertEqual(lr.restricted_noqa([["F401"], None, ["C901", "E501"], ["PT011"]]), ["blanket", "C901", "PT011"])

    def test_complexipy_ignores_are_restricted_noqas(self):
        text = source('''
            def f():  # complexipy: ignore
                pass
            def g():  #NOQA:complexipy
                pass
        ''')
        self.assertEqual(lr.noqa_comments(text), [["complexipy"], ["complexipy"]])
        self.assertEqual(lr.restricted_noqa(lr.noqa_comments(text)), ["complexipy", "complexipy"])

    def test_unparseable_source_has_no_noqas(self):
        self.assertEqual(lr.noqa_comments('x = """unterminated\n'), [])


class CustomCountsTests(unittest.TestCase):
    def test_assertion_free_is_counted_in_test_files_only(self):
        text = "def test_x():\n    run()\n"
        self.assertEqual(lr.custom_counts("tests/test_a.py", text)[0], {lr.RULE_ASSERTION_FREE: 1})
        self.assertEqual(lr.custom_counts("pkg/a.py", text)[0], {})

    def test_syntax_error_counts_nothing(self):
        self.assertEqual(lr.custom_counts("pkg/a.py", "def (:\n"), ({}, []))


class RuffCountsTests(unittest.TestCase):
    def test_counts_per_code(self):
        diags = [{"code": "C901"}, {"code": "C901"}, {"code": "PT011"}, {"code": None}]
        self.assertEqual(lr.ruff_counts(diags), {"C901": 2, "PT011": 1})


class CognitiveTests(unittest.TestCase):
    def test_counts_functions_over_the_limit(self):
        self.assertEqual(lr.cognitive_counts([16, 15, 0, 40]), {lr.RULE_COGNITIVE: 2})
        self.assertEqual(lr.cognitive_counts([15]), {})

    @unittest.skipUnless(importlib.util.find_spec("complexipy"), "complexipy is a project dev dependency")
    def test_complexipy_scores_nesting_and_disregards_ignores(self):
        nested = "    " + "\n    ".join("    " * i + "if x%d:" % i for i in range(6)) + "\n" + "    " * 7 + "pass\n"
        text = "def deep():  # complexipy: ignore\n" + nested
        self.assertEqual(lr.cognitive_complexities(text), [21], "1+2+...+6; the ignore comment is disregarded")
        self.assertEqual(lr.cognitive_complexities("def (:\n"), [])

    @unittest.skipUnless(importlib.util.find_spec("complexipy"), "complexipy is a project dev dependency")
    def test_functions_complexipy_skips_are_scored(self):
        nested = "".join("    " * (i + 1) + "if x:\n" for i in range(6)) + "    " * 7 + "pass\n"
        deep = "def deep(x):\n" + nested
        wrapped = [
            "try:\n    import y\nexcept ImportError:\n" + textwrap.indent(deep, "    "),
            "if X:\n" + textwrap.indent(deep, "    "),
            "class A:\n    class B:\n" + textwrap.indent(deep, "        "),
            "class A:\n    if X:\n" + textwrap.indent(deep, "        "),
        ]
        for text in wrapped:
            self.assertEqual(lr.cognitive_complexities(text), [21], text)
        ladder = "def f(x):\n    if x == 0:\n        pass\n" + "".join(
            "    " * i + "else:\n" + "    " * i + "    if x == %d:\n" % i + "    " * i + "        pass\n" for i in range(1, 5)
        )
        self.assertEqual(lr.cognitive_complexities(ladder), [19])
        self.assertEqual(lr.cognitive_complexities("if X:\n" + textwrap.indent(ladder, "\t")), [19], "not rescored as elif")
        outer = "def outer():\n" + textwrap.indent(deep, "    ") + "    class C:\n" + textwrap.indent(deep, "        ")
        self.assertEqual(len(lr.cognitive_complexities(outer)), 1, "defs inside a function stay folded into it")


class PanicException(BaseException):
    """Stands in for pyo3's, which is a BaseException, not an Exception."""


class CrashTests(unittest.TestCase):
    def test_a_complexipy_panic_exits_2_not_1(self):
        def panic(*args, **kwargs):
            raise PanicException("boom")

        stub = types.ModuleType("complexipy")
        stub.code_complexity = panic
        def run(base):
            return lr.cognitive_complexities("def f():\n    pass\n")

        with mock.patch.dict(sys.modules, {"complexipy": stub}), mock.patch.object(lr, "ratchet", run):
            with redirect_stderr(io.StringIO()) as err:
                self.assertEqual(lr.main(["--base", "origin/main"]), 2)
        self.assertIn("internal error", err.getvalue())


def side(counts=None, lines=0, noqas=None):
    return lr.Side(counts or {}, lines, noqas or [])


def regressed(rows):
    return sorted(r.rule for r in rows if r.regressed)


class CompareFileTests(unittest.TestCase):
    def test_added_file_must_be_clean(self):
        rows = lr.compare_file("pkg/new.py", lr.EMPTY, side({"C901": 1}, 10))
        self.assertEqual(regressed(rows), ["C901"])

    def test_per_rule_no_offsetting(self):
        rows = lr.compare_file("pkg/a.py", side({"C901": 2, "ANN401": 1}), side({"C901": 1, "ANN401": 2}))
        self.assertEqual(regressed(rows), ["ANN401"])

    def test_file_lines_over_limit_may_not_grow_but_may_shrink(self):
        self.assertEqual(regressed(lr.compare_file("pkg/a.py", side(lines=450), side(lines=451))), ["file-lines"])
        self.assertEqual(regressed(lr.compare_file("pkg/a.py", side(lines=450), side(lines=440))), [])
        self.assertEqual(regressed(lr.compare_file("pkg/a.py", side(lines=100), side(lines=400))), [])

    def test_tests_are_exempt_from_size_and_args_only(self):
        head = side({"PLR0913": 1, "function-lines": 1, "C901": 1, "cognitive-complexity": 1, "assertion-free-test": 1}, 900)
        rows = lr.compare_file("tests/test_a.py", lr.EMPTY, head)
        self.assertEqual(regressed(rows), ["C901", "assertion-free-test", "cognitive-complexity"])

    def test_new_noqa_and_restricted_noqa_fail(self):
        rows = lr.compare_file("pkg/a.py", side(noqas=[["F401"]]), side(noqas=[["F401"], ["E501"]]))
        self.assertEqual(regressed(rows), ["noqa-comments"])
        rows = lr.compare_file("pkg/a.py", side(noqas=[None]), side(noqas=[None]))
        self.assertEqual(regressed(rows), ["restricted-noqa (blanket)"], "an existing blanket noqa in a touched file fails")

    def test_format_table_is_aligned(self):
        table = lr.format_table([lr.Row("pkg/a.py", "C901", 0, 1, True)])
        self.assertIn("pkg/a.py  C901  0     1     +1", table)


if __name__ == "__main__":
    unittest.main()
