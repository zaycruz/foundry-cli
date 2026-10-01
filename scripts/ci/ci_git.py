"""Git helpers shared by the Python gate scripts (stdlib only).

The parsers are pure and unit-tested (tests/test_ci_git.py). The rest shells
out to git. Used by lint_ratchet.py, dead_code.py, pr_size.py,
regression_proof.py and mutation.py; the Rust template copies this file with
pr_size.py.
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterator, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]


class GitError(Exception):
    """A git command that had to succeed did not."""


class ChangedFile:
    """One row of `git diff --name-status`."""

    def __init__(self, status: str, head_path: str, base_path: Optional[str]):
        self.status = status
        self.head_path = head_path
        self.base_path = base_path

    @property
    def added(self) -> bool:
        return self.status == "A" or self.base_path is None


def parse_name_status(output: str) -> List[ChangedFile]:
    """Parse `git diff --name-status -M -z` output (NUL-separated). Renames
    and copies keep the old path so the base side reads from where it was."""
    fields = output.split("\0")
    files: List[ChangedFile] = []
    i = 0
    while i < len(fields):
        status = fields[i].strip()[:1]
        if not status:
            i += 1
        elif status in ("R", "C") and i + 2 < len(fields):
            files.append(ChangedFile(status, fields[i + 2], fields[i + 1]))
            i += 3
        elif i + 1 < len(fields):
            path = fields[i + 1]
            files.append(ChangedFile(status, path, None if status == "A" else path))
            i += 2
        else:
            break
    return files


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_added_lines(diff: str) -> Dict[str, List[int]]:
    """Added line numbers per head path from `git diff --unified=0` output."""
    added: Dict[str, List[int]] = {}
    current: Optional[str] = None
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            if current is not None:
                added.setdefault(current, [])
            continue
        hunk = HUNK_RE.match(line)
        if hunk and current is not None:
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            added[current].extend(range(start, start + count))
    return added


def is_test_path(path: str) -> bool:
    """pytest layouts, plus the JS/Rust conventions for mixed repos."""
    name = path.rsplit("/", 1)[-1]
    return bool(
        re.search(r"(^|/)(tests?|__tests__|benches|fixtures|e2e)/", path)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name)
    )


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def git(args: List[str], allow_failure: bool = False, cwd: Path = REPO_ROOT) -> Optional[str]:
    done = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if allow_failure else None,
        text=True,
        check=False,
    )
    if done.returncode == 0:
        return done.stdout
    if allow_failure:
        return None
    raise GitError("git %s failed with exit %d" % (" ".join(args), done.returncode))


def resolve_merge_base(base_ref: str) -> Optional[str]:
    """Merge base of `base_ref` and HEAD; the ref itself for shallow clones."""
    merged = git(["merge-base", base_ref, "HEAD"], allow_failure=True)
    if merged:
        return merged.strip()
    resolved = git(["rev-parse", "--verify", "%s^{commit}" % base_ref], allow_failure=True)
    return resolved.strip() if resolved else None


def untracked() -> List[str]:
    return [p for p in (git(["ls-files", "--others", "--exclude-standard", "-z"]) or "").split("\0") if p]


def changed_files(merge_base: str) -> List[ChangedFile]:
    """Changed files against the WORKING TREE; untracked files count as added."""
    files = parse_name_status(git(["diff", "--name-status", "-M", "-z", "--diff-filter=ACMR", merge_base]) or "")
    seen = {f.head_path for f in files}
    files += [ChangedFile("A", p, None) for p in untracked() if p not in seen]
    return files


def added_lines(merge_base: str) -> Dict[str, List[int]]:
    """Added lines per file against the working tree, untracked files whole."""
    diff = git(["-c", "core.quotePath=off", "diff", "--unified=0", "--no-color", "--no-ext-diff", "-M", merge_base])
    added = parse_added_lines(diff or "")
    for path in untracked():
        if path not in added:
            try:
                count = len((REPO_ROOT / path).read_text(errors="replace").splitlines())
            except OSError:
                continue
            added[path] = list(range(1, count + 1))
    return added


@contextlib.contextmanager
def base_worktree(merge_base: str) -> Iterator[Path]:
    """The merge base checked out in a temporary worktree. A `.venv` at the
    repo root is symlinked in so tools resolve without a second install."""
    directory = Path(tempfile.mkdtemp(prefix="ci-base-"))
    try:
        git(["worktree", "add", "--detach", "--quiet", str(directory), merge_base])
        venv = REPO_ROOT / ".venv"
        if venv.exists() and not (directory / ".venv").exists():
            os.symlink(str(venv), str(directory / ".venv"))
        yield directory
    finally:
        git(["worktree", "remove", "--force", str(directory)], allow_failure=True)
        git(["worktree", "prune"], allow_failure=True)
        shutil.rmtree(directory, ignore_errors=True)
