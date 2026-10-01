"""Unit tests for scripts/ci/pr_size.py: the budget and the waiver.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pr_size = importlib.import_module("pr_size")


def lines(n):
    return list(range(1, n + 1))


class ExclusionTests(unittest.TestCase):
    def test_tests_lockfiles_docs_snapshots_and_generated_are_free(self):
        cases = {
            "uv.lock": "lockfile",
            "sub/Cargo.lock": "lockfile",
            "tests/test_a.py": "test",
            "pkg/test_b.py": "test",
            "docs/adr.md": "docs",
            "tests/__snapshots__/x.ambr": "snapshot",
            "pkg/models_pb2.py": "generated",
            "pkg/core.py": None,
        }
        for path, reason in cases.items():
            self.assertEqual(pr_size.exclusion_reason(path, {"pkg/models_pb2.py"}), reason, path)


class MeasureTests(unittest.TestCase):
    def test_counts_production_additions_biggest_first(self):
        counted, excluded, per_file = pr_size.measure(
            {"pkg/a.py": lines(10), "pkg/b.py": lines(30), "tests/test_b.py": lines(500), "uv.lock": lines(900), "pkg/empty.py": []},
            set(),
        )
        self.assertEqual(counted, 40)
        self.assertEqual(excluded["test"], 500)
        self.assertEqual(excluded["lockfile"], 900)
        self.assertEqual(per_file, [(30, "pkg/b.py"), (10, "pkg/a.py")])


class OwnerTests(unittest.TestCase):
    def test_individual_handles_only(self):
        source = "# owners\n*.py @Alice @org/team\n.github/** @bob # trailing\nx dev@example.com\n"
        self.assertEqual(pr_size.code_owner_handles(source), {"alice", "bob"})
        self.assertEqual(pr_size.code_owner_handles(None), set())


def labeled(login):
    return {"event": "labeled", "label": {"name": "large-change"}, "actor": {"login": login}}


class WaiverTests(unittest.TestCase):
    owners = {"alice", "bob"}

    def test_requires_label_by_a_non_author_code_owner(self):
        self.assertFalse(pr_size.waiver([], [labeled("alice")], self.owners, "carol")[0])
        self.assertTrue(pr_size.waiver(["large-change"], [labeled("alice")], self.owners, "carol")[0])
        self.assertFalse(pr_size.waiver(["large-change"], [labeled("mallory")], self.owners, "carol")[0])
        waived, reason = pr_size.waiver(["large-change"], [labeled("Alice")], self.owners, "alice")
        self.assertFalse(waived)
        self.assertIn("PR author", reason)
        self.assertFalse(pr_size.waiver(["large-change"], [], self.owners, "carol")[0])

    def test_most_recent_application_decides(self):
        events = [labeled("alice"), {"event": "unlabeled", "label": {"name": "large-change"}}, labeled("mallory")]
        self.assertFalse(pr_size.waiver(["large-change"], events, self.owners, "carol")[0])


if __name__ == "__main__":
    unittest.main()
