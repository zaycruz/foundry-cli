#!/usr/bin/env python3
"""PR size budget (check `pr-size`). Small PRs get real review; big ones get skimmed.

Counts ADDED lines against the merge base, excluding tests, lockfiles,
snapshots, Markdown, and files marked `linguist-generated` in the BASE
.gitattributes. Deletions are free. Over BUDGET, the check fails unless the PR
carries the `large-change` label and the label was last applied by a code owner
(an `@handle` in the BASE .github/CODEOWNERS) who is not the PR author.

Same rules as the Node template's scripts/ci/pr-size.mjs (ADR-0003).

Env: RATCHET_BASE (default origin/main); in CI also PR_NUMBER, PR_AUTHOR,
PR_LABELS (JSON array of names), GITHUB_REPOSITORY, GH_TOKEN.
Exit: 0 pass or waived, 1 over budget, 2 the check could not run.
"""

import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import REPO_ROOT, GitError, added_lines, git, is_test_path, resolve_merge_base

BUDGET = 400
WAIVER_LABEL = "large-change"
LOCKFILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "Package.resolved",
    "go.sum",
}
REASONS = ("lockfile", "generated", "docs", "snapshot", "test")


def exclusion_reason(path: str, generated: Set[str]) -> Optional[str]:
    """Why a path is outside the budget, or None when it counts."""
    if path.rsplit("/", 1)[-1] in LOCKFILES:
        return "lockfile"
    if path in generated:
        return "generated"
    if re.search(r"\.mdx?$", path, re.IGNORECASE):
        return "docs"
    if path.endswith(".snap") or path.endswith(".ambr"):
        return "snapshot"
    if is_test_path(path):
        return "test"
    return None


def measure(added: Dict[str, List[int]], generated: Set[str]) -> Tuple[int, Dict[str, int], List[Tuple[int, str]]]:
    """(counted lines, excluded lines per reason, counted files biggest first)."""
    counted = 0
    excluded = {reason: 0 for reason in REASONS}
    per_file: List[Tuple[int, str]] = []
    for path, lines in added.items():
        reason = exclusion_reason(path, generated)
        if reason:
            excluded[reason] += len(lines)
        elif lines:
            counted += len(lines)
            per_file.append((len(lines), path))
    per_file.sort(key=lambda item: (-item[0], item[1]))
    return counted, excluded, per_file


def code_owner_handles(source: Optional[str]) -> Set[str]:
    """Individual `@handle`s in CODEOWNERS; teams (`@org/team`) are skipped."""
    handles: Set[str] = set()
    for raw in (source or "").splitlines():
        tokens = raw.split("#", 1)[0].split()
        handles |= {t[1:].lower() for t in tokens[1:] if re.fullmatch(r"@[A-Za-z0-9-]+", t)}
    return handles


def waiver(labels: List[str], events: List[dict], owners: Set[str], author: str) -> Tuple[bool, str]:
    """Whether the label is present and was last applied by a non-author code owner."""
    if WAIVER_LABEL not in labels:
        return False, "no `%s` label" % WAIVER_LABEL
    applied = [e for e in events if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == WAIVER_LABEL]
    actor = ((applied[-1].get("actor") or {}).get("login") or "").lower() if applied else ""
    if not actor:
        return False, "label present but no labeling event found"
    if actor == (author or "").lower():
        return False, "label applied by the PR author (@%s); another code owner must apply it" % actor
    if actor not in owners:
        return False, "label applied by @%s, who is not in CODEOWNERS" % actor
    return True, "label applied by code owner @%s" % actor


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def generated_paths(paths: List[str], merge_base: str) -> Set[str]:
    """Paths the BASE .gitattributes marks linguist-generated (`--source`),
    so a PR cannot mark its own code generated."""
    if not paths:
        return set()
    done = subprocess.run(
        ["git", "check-attr", "--source=%s" % merge_base, "-z", "--stdin", "linguist-generated"],
        cwd=str(REPO_ROOT),
        input="\0".join(paths) + "\0",
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    fields = done.stdout.split("\0")
    return {fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] in ("true", "set")}


def label_events(repo: str, number: str) -> List[dict]:
    out = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", "repos/%s/issues/%s/events?per_page=100" % (repo, number)],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout
    return [event for page in json.loads(out) for event in page]


def main() -> int:
    base_ref = os.environ.get("RATCHET_BASE") or "origin/main"
    merge_base = resolve_merge_base(base_ref)
    if not merge_base:
        print('pr-size: cannot resolve base ref "%s".' % base_ref, file=sys.stderr)
        return 2
    added = added_lines(merge_base)
    counted, excluded, per_file = measure(added, generated_paths(list(added), merge_base))
    parts = ", ".join("%s %d" % (k, v) for k, v in excluded.items() if v) or "none"
    print("pr-size: %d counted added line(s) (budget %d); excluded: %s" % (counted, BUDGET, parts))
    if counted <= BUDGET:
        print("pr-size: PASS")
        return 0
    for lines, path in per_file[:15]:
        print("  %6d  %s" % (lines, path))
    if os.environ.get("PR_NUMBER") and os.environ.get("GITHUB_REPOSITORY"):
        waived, reason = waiver(
            json.loads(os.environ.get("PR_LABELS") or "[]"),
            label_events(os.environ["GITHUB_REPOSITORY"], os.environ["PR_NUMBER"]),
            code_owner_handles(git(["show", "%s:.github/CODEOWNERS" % merge_base], allow_failure=True)),
            os.environ.get("PR_AUTHOR", ""),
        )
        if waived:
            print("pr-size: over budget, WAIVED (%s)." % reason)
            return 0
        print("pr-size: waiver not granted: %s." % reason, file=sys.stderr)
    print(
        "\npr-size: FAIL; %d added lines outside tests/docs/lockfiles/generated exceed %d.\n"
        "Split the change: land the refactor, then the feature; or the schema, then its use.\n"
        "If it cannot be split, a code owner other than the author applies the `%s` label." % (counted, BUDGET, WAIVER_LABEL),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GitError, subprocess.CalledProcessError, ValueError) as error:
        print("pr-size: %s" % error, file=sys.stderr)
        sys.exit(2)
