#!/usr/bin/env python3
"""Dead-code ratchet for Python (check `dead-code`). YAGNI, enforced.

Runs vulture (unused functions, classes, methods, variables, imports,
unreachable code) and deptry (unused, missing, transitive, and misplaced
dependencies) at the merge base and at HEAD, and fails when HEAD has a
finding the base did not. Existing dead code is debt; new dead code blocks.

Findings are keyed without line numbers, so moving code does not create new
findings: vulture by (file, message), deptry by (code, module). Renamed files
keep their vulture findings.

Config: `[tool.vulture]` and `[tool.deptry]` in pyproject.toml. vulture
measures BOTH sides with the BASE `[tool.vulture]` (the head one only when the
base has none yet, i.e. the adoption PR), so a same-PR `ignore_names` cannot
launder a finding. deptry always reads each side's own pyproject.toml, because
that is where the dependency list lives; its `[tool.deptry]` ignores are
guarded by CODEOWNERS only.

Same contract as the Node template's scripts/ci/dead-code.mjs (ADR-0003).

Env: RATCHET_BASE (default origin/main).
Exit: 0 pass, 1 new dead code, 2 the check could not run.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import REPO_ROOT, GitError, base_worktree, changed_files, git, resolve_merge_base

VULTURE_LINE = re.compile(r"^(?P<file>[^:]+):\d+: (?P<message>.+?) \(\d+% confidence\)$")
Finding = Tuple[str, str, str]  # (tool, where, what)


def vulture_findings(output: str) -> Set[Finding]:
    found: Set[Finding] = set()
    for line in output.splitlines():
        match = VULTURE_LINE.match(line.strip())
        if match:
            found.add(("vulture", match.group("file"), match.group("message")))
    return found


def deptry_findings(report: List[dict]) -> Set[Finding]:
    return {("deptry", (item.get("error") or {}).get("code", "?"), item.get("module", "?")) for item in report}


def new_findings(base: Set[Finding], head: Set[Finding], renames: Dict[str, str]) -> List[Finding]:
    """HEAD findings absent from the base, after mapping renamed files."""
    moved = {(tool, renames.get(where, where) if tool == "vulture" else where, what) for tool, where, what in base}
    return sorted(head - moved)


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def tool(name: str) -> str:
    """The tool from the interpreter's own environment (the repo's pinned one)."""
    return str(Path(sys.executable).parent / name)


def run_vulture(cwd: Path, config: str) -> Set[Finding]:
    command = [tool("vulture"), "--config", config]
    done = subprocess.run(command, cwd=str(cwd), stdout=subprocess.PIPE, text=True, check=False)
    # vulture exits 3 when it finds dead code; 1 and 2 are its own errors.
    if done.returncode not in (0, 3):
        raise RuntimeError("vulture exited %d in %s" % (done.returncode, cwd))
    return vulture_findings(done.stdout)


def run_deptry(cwd: Path) -> Set[Finding]:
    with tempfile.TemporaryDirectory(prefix="deptry-") as directory:
        report = Path(directory) / "deptry.json"
        subprocess.run([tool("deptry"), ".", "--json-output", str(report)], cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if not report.exists():
            raise RuntimeError("deptry wrote no report in %s" % cwd)
        return deptry_findings(json.loads(report.read_text()))


def vulture_config(merge_base: str) -> Tuple[str, bool]:
    """(config path both sides use, whether it is a temp file to delete)."""
    source = git(["show", "%s:pyproject.toml" % merge_base], allow_failure=True)
    if source is None or not re.search(r"^\[tool\.vulture\]", source, re.MULTILINE):
        print("dead-code: the base has no [tool.vulture]; measuring both sides with HEAD's.")
        return str(REPO_ROOT / "pyproject.toml"), False
    handle, path = tempfile.mkstemp(prefix="dead-code-base-", suffix=".toml")
    with os.fdopen(handle, "w") as out:
        out.write(source)
    return path, True


def main() -> int:
    base_ref = os.environ.get("RATCHET_BASE") or "origin/main"
    merge_base = resolve_merge_base(base_ref)
    if not merge_base:
        print('dead-code: cannot resolve base ref "%s".' % base_ref, file=sys.stderr)
        return 2
    files = changed_files(merge_base)
    renames = {f.base_path: f.head_path for f in files if f.status == "R" and f.base_path}
    config, temporary = vulture_config(merge_base)
    try:
        head = run_vulture(REPO_ROOT, config) | run_deptry(REPO_ROOT)
        with base_worktree(merge_base) as directory:
            base = run_vulture(directory, config) | run_deptry(directory)
    finally:
        if temporary:
            os.unlink(config)
    fresh = new_findings(base, head, renames)
    print("dead-code: %d finding(s) at base, %d at HEAD." % (len(base), len(head)))
    if not fresh:
        print("dead-code: PASS; the change adds no dead code or dependency drift.")
        return 0
    print("\ndead-code: FAIL; the change adds:\n", file=sys.stderr)
    for tool_name, where, what in fresh:
        print("  %-8s %s  %s" % (tool_name, where, what), file=sys.stderr)
    print(
        "\nDelete it. A function nothing calls, an import nothing uses, and a dependency nothing imports are\n"
        "YAGNI. If the tool is wrong (a framework hook, a plugin entry point), whitelist it in pyproject.toml\n"
        "in its own reviewed PR; pyproject.toml is CODEOWNERS-protected.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GitError, RuntimeError, ValueError) as error:
        print("dead-code: %s" % error, file=sys.stderr)
        sys.exit(2)
