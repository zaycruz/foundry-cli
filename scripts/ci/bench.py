#!/usr/bin/env python3
"""Benchmark gate (check `bench`): a change may not make a benchmark slower.

Opt-in. The check does nothing unless the repository has a `bench/` directory.
Each file in bench/ is one benchmark, named by its file stem (files starting
with `_` are helpers, not benchmarks):

  bench/*.py                 run with the Python that runs this script
  bench/*.mjs, *.js, *.cjs,  run with node, optimizing tiers off (NODE_FLAGS);
    *.ts, *.mts              TypeScript through Node's type stripping
  bench/*.rs                 a Cargo `[[bench]]` target with `harness = false`

Every benchmark runs as its own process at the merge base and at HEAD, on the
same machine, and the script counts the CPU instructions it executes: valgrind
cachegrind on Linux (CI), the hardware counter of `/usr/bin/time -l` on macOS
(local runs). Instruction counts, not time: the same code executes the same
instructions on every run, so the gate does not flake on a busy runner. The
cost of starting an empty interpreter is subtracted (for Node, one that has
loaded Node's TypeScript stripper, which every Node run loads; see node_command).

A benchmark regresses when HEAD executes more than THRESHOLD more instructions
than the merge base AND at least MIN_DELTA more. New benchmarks are reported,
not judged. The thresholds live in this file, and CI runs the merge-base copy
of it (the merge-base action, base-gate-scripts), so a PR cannot raise them to
pass itself. Standard §10, ADR-0006.

Env: RATCHET_BASE (default origin/main).
Exit: 0 pass or skipped, 1 regression or a benchmark failed at HEAD,
2 the check could not run.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import REPO_ROOT, GitError, base_worktree, resolve_merge_base

THRESHOLD = 0.10  # +10 % instructions
MIN_DELTA = 1_000_000  # and at least this many more (about a millisecond)
BENCH_DIR = "bench"
# Interpreter only: the optimizing tiers compile on timing-dependent schedules.
# Not --jitless: it disables WebAssembly, which Node's TypeScript stripping needs.
NODE_FLAGS = ["--no-opt", "--no-maglev", "--no-sparkplug", "--no-wasm-tier-up",
              "--single-threaded", "--hash-seed=1", "--random-seed=1"]
NODE_EXT = (".mjs", ".js", ".cjs", ".ts", ".mts")

Command = List[str]


class BenchError(Exception):
    """The check could not run (no instruction counter, a build failed)."""


def parse_cachegrind(text: str) -> int:
    """Instruction count (Ir) from a cachegrind.out file."""
    for line in text.splitlines():
        if line.startswith("summary:"):
            return int(line.split()[1])
    raise BenchError("cachegrind output has no summary line")


def parse_time_l(text: str) -> int:
    """Instruction count from macOS `/usr/bin/time -l` output."""
    found = re.search(r"(\d+)\s+instructions retired", text)
    if not found:
        raise BenchError("/usr/bin/time -l printed no instruction count")
    return int(found.group(1))


def time_l(cmd: Command, cwd: Path, env: Dict[str, str]) -> int:
    done = subprocess.run(["/usr/bin/time", "-l"] + cmd, cwd=str(cwd), env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
    if done.returncode:
        raise subprocess.CalledProcessError(done.returncode, cmd, stderr=done.stderr)
    return parse_time_l(done.stderr)


def count_instructions(cmd: Command, cwd: Path, env: Dict[str, str]) -> int:
    """Run cmd once and return the instructions it executed. A non-zero exit
    raises CalledProcessError with the benchmark's stderr."""
    if sys.platform == "darwin":
        # A hardware counter also counts interrupts, so noise only ever adds:
        # the minimum of three runs is the estimate.
        return min(time_l(cmd, cwd, env) for _ in range(3))
    if not shutil.which("valgrind"):
        raise BenchError("valgrind is not installed (Linux) and this is not macOS")
    # One unmeasured run first, so one-time work is not counted: Python writes
    # .pyc files on first import (uv sync installs without them), and the side
    # measured first would pay for compiling every shared dependency.
    warm = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True, check=False)
    if warm.returncode:
        raise subprocess.CalledProcessError(warm.returncode, cmd, stderr=warm.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cachegrind.out"
        valgrind = ["valgrind", "--tool=cachegrind", "--cache-sim=no", "--cachegrind-out-file=%s" % out]
        done = subprocess.run(valgrind + cmd, cwd=str(cwd), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if done.returncode:
            raise subprocess.CalledProcessError(done.returncode, cmd, stderr=done.stderr)
        return parse_cachegrind(out.read_text())


def parse_cargo_benches(messages: str, bench_dir: Path) -> Dict[str, str]:
    """{target name: executable} for the bench targets whose source is in
    bench_dir, from `cargo bench --no-run --message-format=json`."""
    found: Dict[str, str] = {}
    for line in messages.splitlines():
        if not line.startswith("{"):
            continue
        msg = json.loads(line)
        target = msg.get("target") or {}
        if msg.get("reason") != "compiler-artifact" or "bench" not in target.get("kind", []):
            continue
        if msg.get("executable") and Path(target["src_path"]).parent == bench_dir:
            found[target["name"]] = msg["executable"]
    return found


def rust_benches(tree: Path, env: Dict[str, str]) -> Dict[str, Command]:
    done = subprocess.run(["cargo", "bench", "--no-run", "--locked", "--message-format=json"],
                          cwd=str(tree), env=env, stdout=subprocess.PIPE, text=True, check=False)
    if done.returncode:
        raise BenchError("cargo bench --no-run failed in %s" % tree)
    exes = parse_cargo_benches(done.stdout, (tree / BENCH_DIR).resolve())
    return {name: [exe] for name, exe in exes.items()}


def node_command(scratch: Path, script: str) -> Command:
    """Every Node run, benchmarks and empty runs alike, first imports an empty
    .ts file, so Node's TypeScript stripper (about 300 million instructions to
    load) is always loaded and always subtracted. Guessing which benchmarks load
    TypeScript is wrong for transitive imports, and a wrong guess on one side
    fails or passes a PR on the stripper's cost alone."""
    return ["node"] + NODE_FLAGS + ["--import", str(scratch / "empty.ts"), script]


def discover(tree: Path, env: Dict[str, str], scratch: Path) -> Dict[str, Tuple[Command, Optional[str]]]:
    """{name: (benchmark command, kind of empty run to subtract, or None)}."""
    benches: Dict[str, Tuple[Command, Optional[str]]] = {}
    files = sorted(p for p in (tree / BENCH_DIR).iterdir() if p.is_file() and not p.name.startswith("_"))
    for path in files:
        rel = str(path.relative_to(tree))
        if path.suffix == ".py":
            benches[path.stem] = ([sys.executable, rel], "python")
        elif path.suffix in NODE_EXT:
            benches[path.stem] = (node_command(scratch, rel), "node")
    if any(p.suffix == ".rs" for p in files):
        benches.update({name: (cmd, None) for name, cmd in rust_benches(tree, env).items()})
    return benches


def empty_command(kind: str, scratch: Path) -> Command:
    """The empty run for a kind: start-up only (for Node, with the stripper)."""
    if kind == "python":
        return [sys.executable, "-c", "pass"]
    (scratch / "empty.mjs").write_text("")
    return node_command(scratch, str(scratch / "empty.mjs"))


def tree_env(tree: Path) -> Dict[str, str]:
    """Environment that makes each side run its own code: Python imports come
    from this tree before the (HEAD) editable install; hashing is seeded; Cargo
    shares one target dir so dependencies build once."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = os.pathsep.join([str(tree / "src"), str(tree)])
    env["CARGO_TARGET_DIR"] = str(REPO_ROOT / "target")
    return env


def measure(tree: Path) -> Tuple[Dict[str, int], Dict[str, str]]:
    """({name: net instructions}, {name: error}) for every benchmark in tree."""
    env = tree_env(tree)
    counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    empty_cost: Dict[str, int] = {"": 0}
    with tempfile.TemporaryDirectory() as scratch:
        # A type annotation, so the stripper's first real strip (about 20 million
        # instructions) is also part of the empty run.
        (Path(scratch) / "empty.ts").write_text("export const typed: number = 1\n")
        for name, (cmd, kind) in discover(tree, env, Path(scratch)).items():
            try:
                total = count_instructions(cmd, tree, env)
            except subprocess.CalledProcessError as failed:
                errors[name] = "exit %d: %s" % (failed.returncode, (failed.stderr or "").strip()[-500:])
                continue
            kind = kind or ""
            if kind not in empty_cost:
                empty_cost[kind] = count_instructions(empty_command(kind, Path(scratch)), tree, env)
            counts[name] = max(total - empty_cost[kind], 0)
    return counts, errors


def compare(base: Dict[str, int], head: Dict[str, int]) -> Tuple[List[Tuple[str, str, str, str, str]], bool]:
    """Table rows (name, base, head, change, verdict) and whether any regressed."""
    rows = []
    failed = False
    for name in sorted(set(base) | set(head)):
        if name not in head:
            rows.append((name, "{:,}".format(base[name]), "-", "", "removed"))
            continue
        if name not in base:
            rows.append((name, "-", "{:,}".format(head[name]), "", "new"))
            continue
        delta = head[name] - base[name]
        change = delta / base[name] if base[name] else (1.0 if delta else 0.0)
        regressed = change > THRESHOLD and delta >= MIN_DELTA
        failed = failed or regressed
        verdict = "REGRESSED" if regressed else "ok"
        rows.append((name, "{:,}".format(base[name]), "{:,}".format(head[name]), "{:+.1%}".format(change), verdict))
    return rows, failed


def print_table(rows: List[Tuple[str, str, str, str, str]]) -> None:
    header = ("benchmark", "base", "head", "change", "")
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(5)]
    for row in [header] + rows:
        print("  " + "  ".join(cell.rjust(w) if i in (1, 2, 3) else cell.ljust(w)
                               for i, (cell, w) in enumerate(zip(row, widths))).rstrip())


def measure_base(merge_base: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    with base_worktree(merge_base) as tree:
        if not (tree / BENCH_DIR).is_dir():
            return {}, {}
        modules = REPO_ROOT / "node_modules"
        if modules.is_dir() and not (tree / "node_modules").exists():
            os.symlink(str(modules), str(tree / "node_modules"))
        return measure(tree)


def main() -> int:
    if not (REPO_ROOT / BENCH_DIR).is_dir():
        print("bench: no %s/ directory; nothing to measure." % BENCH_DIR)
        return 0
    base_ref = os.environ.get("RATCHET_BASE", "origin/main")
    try:
        merge_base = resolve_merge_base(base_ref)
        if not merge_base:
            raise BenchError("cannot resolve %s" % base_ref)
        head, head_errors = measure(REPO_ROOT)
        base, base_errors = measure_base(merge_base)
    except (BenchError, GitError, OSError, subprocess.CalledProcessError) as err:
        print("bench: could not run: %s" % err, file=sys.stderr)
        return 2
    # A benchmark that crashed at HEAD is reported below, not as "removed".
    rows, failed = compare({k: v for k, v in base.items() if k not in head_errors}, head)
    print("bench: %s (merge base %s) vs HEAD, instructions executed; fails above %+.0f%% and %s more"
          % (base_ref, merge_base[:12], THRESHOLD * 100, "{:,}".format(MIN_DELTA)))
    if rows:
        print_table(rows)
    for name, error in sorted(base_errors.items()):
        print("  note: %s failed at the merge base, so it is not compared (%s)" % (name, error))
    for name, error in sorted(head_errors.items()):
        print("  FAIL: %s failed at HEAD: %s" % (name, error))
    if failed or head_errors:
        print("bench: FAIL. Make the change cheaper, or explain the cost in the PR; see standard §10.")
        return 1
    print("bench: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
