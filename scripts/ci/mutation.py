#!/usr/bin/env python3
"""Mutation testing on the diff for Python (check `mutation`), with mutmut 3.

mutmut mutates whole functions, so the scope is every top-level function and
method that contains a line the change adds (coarser than the Node gate's line
ranges: an untested line elsewhere in a function you touch counts too).
`source_paths` is set to the changed files only, so mutmut does not generate
mutants for the whole package (measured on products/foundry-cli: the whole
package did not finish generating in 5 minutes; one file took 3 minutes end
to end, most of it two full test-suite runs mutmut makes before mutating).

Verdict, same as the Node gate (ADR-0003):
  fail  when  undetected > FREE_SURVIVORS  and  score < MIN_SCORE
  detected = killed; undetected = survived + no tests + timeout + not checked
  (segfault / suspicious / skipped / caught by type check count as neither)

Timeout is NOT detected, though mutmut's own score counts it: a suite that is
slow or starved of CPU times out on every mutant, and counting that as
"detected" passes a change whose tests assert nothing (the Node gate's
pi-palantir case, 2026-09-23: 12/12 Timeout, a false 100 %). A real
infinite-loop mutant is rare on a diff; FREE_SURVIVORS absorbs a few.
"not checked" (mutmut stopped before it ran the mutant) is undetected for the
same reason: a crashed run must not score 100 %. When no mutant in scope gets
a verdict at all (every one segfault / suspicious / skipped), the check exits 2.

The repo's [tool.mutmut] must not set source_paths (or the deprecated
paths_to_mutate): this script inserts it for the run and restores
pyproject.toml afterwards, also on SIGTERM (a cancelled CI run). mutmut's
`mutants/` working copy is deleted before and after each run: a stale one
carries results from another branch, and pytest collects it.

Env: RATCHET_BASE (default origin/main).
Exit: 0 pass, 1 too many survivors, 2 the check could not run.
"""

import ast
import os
import re
import shutil
import signal
import subprocess
import sys
from typing import Dict, List, Set, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import REPO_ROOT, GitError, added_lines, is_test_path, resolve_merge_base

MIN_SCORE = 70.0
FREE_SURVIVORS = 2
DETECTED = {"killed"}
UNDETECTED = {"survived", "no tests", "timeout", "not checked"}
RESULT_LINE = re.compile(r"^\s*(?P<name>\S+__mutmut_\d+):\s*(?P<status>.+?)\s*$")


def module_name(path: str) -> str:
    """`src/pkg/sub/mod.py` -> `pkg.sub.mod`; `pkg/__init__.py` -> `pkg`."""
    parts = path[:-3].split("/")
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _touches(node: ast.AST, lines: Set[int]) -> bool:
    return any(node.lineno <= n <= (node.end_lineno or node.lineno) for n in lines)


def selectors(path: str, source: str, lines: List[int]) -> List[str]:
    """mutmut name globs for the functions and methods containing `lines`."""
    module, wanted, found = module_name(path), set(lines), []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.parse(source).body:
        if isinstance(node, functions) and _touches(node, wanted):
            found.append("%s.x_%s__mutmut_*" % (module, node.name))
        elif isinstance(node, ast.ClassDef):
            found += [
                "%s.xǁ%sǁ%s__mutmut_*" % (module, node.name, item.name)
                for item in node.body
                if isinstance(item, functions) and _touches(item, wanted)
            ]
    return found


def parse_results(output: str) -> Dict[str, str]:
    """`mutmut results --all true` lines -> {mutant name: status}."""
    results = {}
    for line in output.splitlines():
        match = RESULT_LINE.match(line)
        if match:
            results[match.group("name")] = match.group("status").lower()
    return results


def matches(name: str, globs: List[str]) -> bool:
    return any(name.startswith(glob[:-1]) for glob in globs)


def verdict(results: Dict[str, str], globs: List[str]) -> Tuple[bool, float, List[str]]:
    """(failed, score, undetected mutant names) over the mutants in scope."""
    scoped = {n: s for n, s in results.items() if matches(n, globs)}
    detected = sum(1 for s in scoped.values() if s in DETECTED)
    undetected = sorted(n for n, s in scoped.items() if s in UNDETECTED)
    valid = detected + len(undetected)
    if scoped and valid == 0:
        # Every mutant crashed or was skipped: the run measured nothing. Fail
        # closed (exit 2) instead of scoring 100 %. Seen on macOS, where mutmut's
        # fork after pandas/pyarrow start threads segfaults every mutant.
        statuses = ", ".join(sorted(set(scoped.values())))
        raise ValueError("no verdict for any of the %d mutants in scope (%s); the run did not measure anything" % (len(scoped), statuses))
    score = 100.0 if valid == 0 else round(detected * 1000.0 / valid) / 10
    return len(undetected) > FREE_SURVIVORS and score < MIN_SCORE, score, undetected


def with_source_paths(pyproject: str, files: List[str]) -> str:
    """pyproject.toml text with source_paths set under [tool.mutmut]."""
    if re.search(r"^\s*(source_paths|paths_to_mutate)\s*=", pyproject, re.MULTILINE):
        raise ValueError("pyproject.toml sets [tool.mutmut] source_paths; remove it (the gate sets it per run)")
    line = "source_paths = [%s]" % ", ".join('"%s"' % f for f in files)
    if re.search(r"^\[tool\.mutmut\]\s*$", pyproject, re.MULTILINE):
        return re.sub(r"^\[tool\.mutmut\]\s*$", "[tool.mutmut]\n" + line, pyproject, count=1, flags=re.MULTILINE)
    return pyproject.rstrip("\n") + "\n\n[tool.mutmut]\n" + line + "\n"


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def mutmut(args: List[str]) -> str:
    done = subprocess.run([sys.executable, "-m", "mutmut"] + args, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, text=True, check=False)
    return done.stdout


def report(results: Dict[str, str], score: float, undetected: List[str]) -> None:
    print("mutation: score %.1f%% on changed functions; %d undetected" % (score, len(undetected)))
    for name in undetected:
        print("  %s: %s" % (name, results[name]))
    timeouts = sum(1 for name in undetected if results[name] == "timeout")
    if timeouts:
        print(
            "mutation: %d mutant(s) timed out and count as undetected. Unless the mutant makes a real\n"
            "infinite loop, the run was overloaded or the suite is too slow for mutmut's timeout." % timeouts
        )


def main() -> int:
    base_ref = os.environ.get("RATCHET_BASE") or "origin/main"
    merge_base = resolve_merge_base(base_ref)
    if not merge_base:
        print('mutation: cannot resolve base ref "%s".' % base_ref, file=sys.stderr)
        return 2
    scope: Dict[str, List[str]] = {}
    for path, lines in sorted(added_lines(merge_base).items()):
        if path.endswith(".py") and lines and not is_test_path(path) and not path.startswith("scripts/ci/"):
            globs = selectors(path, (REPO_ROOT / path).read_text(), lines)
            if globs:
                scope[path] = globs
    globs = [g for gs in scope.values() for g in gs]
    if not globs:
        print("mutation: PASS; the change adds no lines inside a function to mutate.")
        return 0
    print("mutation: mutating %d function(s) in %s" % (len(globs), ", ".join(scope)))
    pyproject = REPO_ROOT / "pyproject.toml"
    original = pyproject.read_text()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # run the finally below
    shutil.rmtree(REPO_ROOT / "mutants", ignore_errors=True)
    try:
        pyproject.write_text(with_source_paths(original, list(scope)))
        mutmut(["run"] + globs)
        results = parse_results(mutmut(["results", "--all", "true"]))
    finally:
        pyproject.write_text(original)
        shutil.rmtree(REPO_ROOT / "mutants", ignore_errors=True)
    failed, score, undetected = verdict(results, globs)
    report(results, score, undetected)
    if not failed:
        print("mutation: PASS (floor %d%%, %d free survivors)." % (MIN_SCORE, FREE_SURVIVORS))
        return 0
    print(
        "\nmutation: FAIL; mutants in the functions you changed survive the tests. `mutmut show <name>`\n"
        "prints each one. Add an assertion that fails for it, or delete the code if nothing needs it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GitError, SyntaxError, ValueError, OSError) as error:
        print("mutation: %s" % error, file=sys.stderr)
        sys.exit(2)
