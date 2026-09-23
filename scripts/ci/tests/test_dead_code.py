"""Unit tests for scripts/ci/dead_code.py: parsing and the ratchet's set arithmetic.

Run: python3 -m unittest discover -s scripts/ci/tests -v
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dc = importlib.import_module("dead_code")

# Captured from vulture 2.16 on products/foundry-cli.
VULTURE = """src/pkg/a.py:12: unused function 'helper' (60% confidence)
src/pkg/a.py:40: unused import 'os' (90% confidence)
tests/test_a.py:51: unused variable 'mock_admin_service' (100% confidence)
not a finding line
"""

# Shape of deptry 0.25 --json-output.
DEPTRY = [
    {"error": {"code": "DEP002", "message": "'left-pad' defined as a dependency but not used"}, "module": "left-pad", "location": {"file": "pyproject.toml", "line": None, "column": None}},
    {"error": {"code": "DEP001", "message": "'websockets' imported but missing"}, "module": "websockets", "location": {"file": "src/pkg/a.py", "line": 1, "column": 1}},
    {"error": {"code": "DEP001", "message": "'websockets' imported but missing"}, "module": "websockets", "location": {"file": "src/pkg/b.py", "line": 9, "column": 1}},
]


class ParseTests(unittest.TestCase):
    def test_vulture_findings_drop_line_and_confidence(self):
        self.assertEqual(
            dc.vulture_findings(VULTURE),
            {
                ("vulture", "src/pkg/a.py", "unused function 'helper'"),
                ("vulture", "src/pkg/a.py", "unused import 'os'"),
                ("vulture", "tests/test_a.py", "unused variable 'mock_admin_service'"),
            },
        )

    def test_deptry_findings_are_per_code_and_module(self):
        self.assertEqual(dc.deptry_findings(DEPTRY), {("deptry", "DEP002", "left-pad"), ("deptry", "DEP001", "websockets")})


class NewFindingsTests(unittest.TestCase):
    def test_only_head_additions_count(self):
        base = {("vulture", "src/a.py", "unused function 'old'")}
        head = base | {("vulture", "src/a.py", "unused function 'new'"), ("deptry", "DEP002", "left-pad")}
        self.assertEqual(dc.new_findings(base, head, {}), [("deptry", "DEP002", "left-pad"), ("vulture", "src/a.py", "unused function 'new'")])

    def test_renamed_file_keeps_its_findings(self):
        base = {("vulture", "src/old.py", "unused function 'f'")}
        head = {("vulture", "src/new.py", "unused function 'f'")}
        self.assertEqual(dc.new_findings(base, head, {"src/old.py": "src/new.py"}), [])
        self.assertEqual(len(dc.new_findings(base, head, {})), 1)


if __name__ == "__main__":
    unittest.main()
