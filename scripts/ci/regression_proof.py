#!/usr/bin/env python3
"""Regression proof for fix PRs (check `regression-proof`), pytest edition.

A fix PR (label `fix`, or a title starting `fix:` / `fix(scope):` / `fix!:`)
must ship a test that reproduces the bug: its new or changed test files are
copied onto the BASE source and run there, and at least one test case must
FAIL; the same files must then all PASS on HEAD. A collection or fixture
error at the base is not proof (the test only imports something the fix
adds). Every other PR reports success with "skip", so this can be required.

The base run puts the base worktree's `src/` (and root) first on PYTHONPATH,
so an editable install of HEAD cannot shadow the base code.

Same rules as the Node template's scripts/ci/regression-proof.mjs (ADR-0003).

Env: RATCHET_BASE (default origin/main), PR_TITLE, PR_LABELS (JSON array).
Local: `python3 scripts/ci/regression_proof.py --force`.
`--detect` prints `fix=true|false` (CI skips the install for non-fix PRs).
Exit: 0 pass or skip, 1 no proof, 2 the check could not run.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import REPO_ROOT, GitError, base_worktree, changed_files, is_test_path, resolve_merge_base

RUNNABLE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def is_fix_pr(title: str, labels: List[str]) -> bool:
    return "fix" in labels or bool(re.match(r"^fix(\([^)]*\))?!?:", title.strip(), re.IGNORECASE))


def select_test_files(paths: List[str]) -> Tuple[List[str], List[str]]:
    """(test-path files to carry onto the base, the runnable test modules)."""
    carried = sorted(p for p in paths if is_test_path(p))
    return carried, [p for p in carried if RUNNABLE.search(p)]


def parse_junit(xml: str) -> Dict[str, int]:
    """Case outcomes from pytest's JUnit XML. <error> is a collection or
    fixture error: not a test case failing on its assertion."""
    result = {"passed": 0, "failed": 0, "load_failures": 0}
    for case in ET.fromstring(xml).iter("testcase"):
        tags = {child.tag for child in case}
        if "error" in tags:
            result["load_failures"] += 1
        elif "failure" in tags:
            result["failed"] += 1
        elif "skipped" not in tags:
            result["passed"] += 1
    return result


def verdict(base: Dict[str, int], head: Dict[str, int]) -> Tuple[bool, str]:
    if head["failed"] or head["load_failures"]:
        return False, "the changed tests do not pass on HEAD (%d failed, %d errors)" % (head["failed"], head["load_failures"])
    if not head["passed"]:
        return False, "the changed test files ran no tests on HEAD"
    if not base["failed"]:
        load = " (%d only errored at collection/setup, which is not proof)" % base["load_failures"] if base["load_failures"] else ""
        return False, "no changed test fails on the base source%s; the test does not reproduce the bug" % load
    return True, "%d test(s) fail on the base and pass on HEAD" % base["failed"]


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def run_pytest(root: Path, files: List[str]) -> Dict[str, int]:
    out_dir = Path(tempfile.mkdtemp(prefix="regression-proof-"))
    report = out_dir / "junit.xml"
    env = dict(os.environ)
    paths = [str(root / "src")] if (root / "src").is_dir() else []
    env["PYTHONPATH"] = os.pathsep.join(paths + [str(root)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml", str(report)] + files
    try:
        subprocess.run(command, cwd=str(root), env=env, stdout=subprocess.DEVNULL, check=False)
        if not report.exists():
            return {"passed": 0, "failed": 0, "load_failures": len(files)}
        return parse_junit(report.read_text())
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def main(argv: List[str]) -> int:
    title = os.environ.get("PR_TITLE", "")
    labels = json.loads(os.environ.get("PR_LABELS") or "[]")
    if "--detect" in argv:
        print("fix=%s" % str(is_fix_pr(title, labels)).lower())
        return 0
    if "--force" not in argv and not is_fix_pr(title, labels):
        print("regression-proof: skip (not a fix PR: no `fix` label, title does not start with `fix:`).")
        return 0
    base_ref = os.environ.get("RATCHET_BASE") or "origin/main"
    merge_base = resolve_merge_base(base_ref)
    if not merge_base:
        print('regression-proof: cannot resolve base ref "%s".' % base_ref, file=sys.stderr)
        return 2
    carried, runnable = select_test_files([f.head_path for f in changed_files(merge_base)])
    if not runnable:
        print("regression-proof: FAIL; a fix PR must add or change a test that reproduces the bug.", file=sys.stderr)
        return 1
    print("regression-proof: running %s on base %s and on HEAD" % (", ".join(runnable), merge_base[:12]))
    with base_worktree(merge_base) as directory:
        for path in carried:
            (directory / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(REPO_ROOT / path), str(directory / path))
        base = run_pytest(directory, runnable)
    head = run_pytest(REPO_ROOT, runnable)
    print("regression-proof: base %s; HEAD %s" % (base, head))
    ok, reason = verdict(base, head)
    if ok:
        print("regression-proof: PASS; %s." % reason)
        return 0
    print("regression-proof: FAIL; %s.\nWrite the test first: it must fail before the fix and pass after it." % reason, file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (GitError, ValueError) as error:
        print("regression-proof: %s" % error, file=sys.stderr)
        sys.exit(2)
