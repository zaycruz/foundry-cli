"""Unit tests for scripts/ci/bench.py: the comparison, the parsers, discovery.

Run: python3 -m unittest discover -s scripts/ci/tests -v
Needs no valgrind: the instruction counter is replaced where a test runs
benchmarks.
"""

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
bench = importlib.import_module("bench")


def verdicts(base, head):
    rows, failed = bench.compare(base, head)
    return {row[0]: row[4] for row in rows}, failed


class CompareTests(unittest.TestCase):
    def test_a_2x_slowdown_regresses(self):
        found, failed = verdicts({"sort": 50_000_000}, {"sort": 100_000_000})
        self.assertEqual(found, {"sort": "REGRESSED"})
        self.assertTrue(failed)

    def test_at_the_threshold_passes_and_just_above_fails(self):
        base = 100_000_000
        self.assertFalse(verdicts({"a": base}, {"a": base + 10_000_000})[1])
        self.assertTrue(verdicts({"a": base}, {"a": base + 10_000_001})[1])

    def test_a_large_relative_change_below_min_delta_passes(self):
        # 50 % of a tiny benchmark is noise, not a regression.
        self.assertFalse(verdicts({"tiny": 100_000}, {"tiny": 150_000})[1])

    def test_faster_unchanged_new_and_removed_pass(self):
        found, failed = verdicts({"a": 9_000_000, "b": 9_000_000, "gone": 5},
                                 {"a": 4_000_000, "b": 9_000_000, "fresh": 7})
        self.assertEqual(found, {"a": "ok", "b": "ok", "gone": "removed", "fresh": "new"})
        self.assertFalse(failed)

    def test_zero_base_with_growth_regresses(self):
        self.assertTrue(verdicts({"z": 0}, {"z": 2_000_000})[1])

    def test_change_column_is_signed_percent(self):
        rows, _ = bench.compare({"a": 100_000_000}, {"a": 200_000_000})
        self.assertEqual(rows[0][1:4], ("100,000,000", "200,000,000", "+100.0%"))


class ParserTests(unittest.TestCase):
    def test_cachegrind_summary(self):
        text = "desc: I1 cache: ...\ncmd: node x.mjs\nevents: Ir\nfl=x\n1 2\nsummary: 123456789\n"
        self.assertEqual(bench.parse_cachegrind(text), 123456789)

    def test_cachegrind_without_summary_is_an_error(self):
        with self.assertRaises(bench.BenchError):
            bench.parse_cachegrind("events: Ir\n")

    def test_time_l_instructions(self):
        text = "        0.10 real  0.08 user\n          1209383002  instructions retired\n  4733099  cycles elapsed\n"
        self.assertEqual(bench.parse_time_l(text), 1209383002)

    def test_cargo_messages_keep_only_bench_targets_in_bench_dir(self):
        bench_dir = Path("/repo/bench")

        def artifact(name, kind, src, exe):
            return json.dumps({"reason": "compiler-artifact", "executable": exe,
                               "target": {"name": name, "kind": [kind], "src_path": src}})

        messages = "\n".join([
            artifact("parse", "bench", "/repo/bench/parse.rs", "/t/parse-1"),
            artifact("criterion_old", "bench", "/repo/benches/old.rs", "/t/old-1"),
            artifact("app", "bin", "/repo/src/main.rs", "/t/app"),
            artifact("lib", "lib", "/repo/src/lib.rs", None),
            json.dumps({"reason": "build-finished", "success": True}),
            "   Compiling x v0.1.0",
        ])
        self.assertEqual(bench.parse_cargo_benches(messages, bench_dir), {"parse": "/t/parse-1"})


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.tree = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tree, True)
        (self.tree / "bench").mkdir()
        for name in ("load.py", "render.mjs", "_helpers.py", "notes.md"):
            (self.tree / "bench" / name).write_text("")
        (self.tree / "bench" / "board.mjs").write_text("import { group } from '../lib/board.ts'\n")

    def test_discovery_skips_helpers_and_unknown_files(self):
        scratch = Path("/scratch")
        found = bench.discover(self.tree, {}, scratch)
        self.assertEqual(sorted(found), ["board", "load", "render"])
        preload = ["--import", "/scratch/empty.ts"]
        self.assertEqual(found["render"], (["node"] + bench.NODE_FLAGS + preload + ["bench/render.mjs"], "node"))
        self.assertEqual(found["load"], ([sys.executable, "bench/load.py"], "python"))

    def test_node_keeps_webassembly_so_typescript_imports_work(self):
        # --jitless disables WebAssembly, and Node's type stripping runs on it.
        self.assertNotIn("--jitless", bench.NODE_FLAGS)
        (self.tree / "bench" / "direct.mts").write_text("const n: number = 1\n")
        self.assertEqual(bench.discover(self.tree, {}, Path("/s"))["direct"][1], "node")

    def test_every_node_run_and_its_empty_run_preload_the_stripper(self):
        # No guessing which benchmarks load TypeScript: a benchmark whose helper
        # moves from .js to .ts must not change what is subtracted.
        with tempfile.TemporaryDirectory() as scratch:
            empty = bench.empty_command("node", Path(scratch))
            self.assertEqual(Path(empty[-1]).read_text(), "")
            bench_cmd = bench.discover(self.tree, {}, Path(scratch))["render"][0]
            self.assertEqual(empty[:-1], bench_cmd[:-1])
            self.assertEqual(bench_cmd[-3:-1], ["--import", str(Path(scratch) / "empty.ts")])

    def test_empty_interpreter_cost_is_subtracted_once_per_runtime(self):
        costs = {"load.py": 900, "pass": 100, "render.mjs": 5000, "empty.mjs": 1000,
                 "board.mjs": 9000}
        calls = []

        def fake(cmd, cwd, env):
            calls.append(Path(cmd[-1]).name)
            return costs[Path(cmd[-1]).name]

        with mock.patch.object(bench, "count_instructions", fake):
            counts, errors = bench.measure(self.tree)
        self.assertEqual(counts, {"board": 8000, "load": 800, "render": 4000})
        self.assertEqual(errors, {})
        self.assertEqual(sorted(calls), sorted(costs))

    def test_a_crashing_benchmark_is_an_error_not_a_count(self):
        def fake(cmd, cwd, env):
            if cmd[-1] == "bench/load.py":
                raise subprocess.CalledProcessError(3, cmd, stderr="Traceback\nKeyError: 'x'")
            return 10

        with mock.patch.object(bench, "count_instructions", fake):
            counts, errors = bench.measure(self.tree)
        self.assertEqual(sorted(counts), ["board", "render"])
        self.assertIn("exit 3", errors["load"])
        self.assertIn("KeyError", errors["load"])

    def test_linux_counts_after_one_unmeasured_warm_up_run(self):
        # The first run writes .pyc files; counting it would charge HEAD (measured
        # first) for compiling every shared dependency.
        runs = []

        def fake_run(cmd, **kwargs):
            runs.append(cmd)
            if cmd[0] == "valgrind":
                out = next(a for a in cmd if a.startswith("--cachegrind-out-file="))
                Path(out.split("=", 1)[1]).write_text("events: Ir\nsummary: 42\n")
            return subprocess.CompletedProcess(cmd, 0, stderr="")

        with mock.patch.object(bench.sys, "platform", "linux"), \
                mock.patch.object(bench.shutil, "which", return_value="/usr/bin/valgrind"), \
                mock.patch.object(bench.subprocess, "run", fake_run):
            self.assertEqual(bench.count_instructions(["python", "bench/load.py"], self.tree, {}), 42)
        self.assertEqual(runs[0], ["python", "bench/load.py"])
        self.assertEqual(runs[1][0], "valgrind")

    def test_each_side_imports_its_own_tree_first(self):
        env = bench.tree_env(self.tree)
        self.assertEqual(env["PYTHONPATH"].split(":")[0], str(self.tree / "src"))
        self.assertEqual(env["PYTHONHASHSEED"], "0")


if __name__ == "__main__":
    unittest.main()
