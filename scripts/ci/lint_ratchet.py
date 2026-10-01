#!/usr/bin/env python3
"""Tier-2 lint ratchet for Python: the deterministic half of the CI quality gate.

`ruff check` fails on Tier-1 rules only (ruff.toml). Tier-2 rules (complexity,
cognitive complexity, size, arguments, nesting, `Any`, loop idioms, pytest misuse,
assertion-free tests) are not errors there, because an existing tree violates
them. This script makes them enforceable anyway: it measures every changed
`.py` file at the merge base and at HEAD and fails the build if a change makes
any touched file WORSE.

Same contract as the Node and Rust ratchets:
  * No baseline file. The base is always the merge base of the target branch.
  * Per (file, rule) comparison, not a repo total: no offsetting.
  * Added files are compared against zero: new code is strictly clean.
  * Deterministic: no network, no clock, no cache.
  * A config change cannot launder a regression. The Tier-2 rule set and its
    thresholds live in THIS file and are passed to ruff with `--isolated`, so
    no edit to ruff.toml or pyproject.toml changes what is measured. When a PR
    edits this script, CI runs the merge-base version of it (ci.yml).
  * Suppressions are gated. The number of `# noqa` comments in a touched file
    may not go up, and a `# noqa` that is blanket or names a Tier-2 rule fails
    the file outright. complexipy's `# complexipy: ignore` and
    `# noqa: complexipy` count as such a `# noqa`, and complexipy runs with
    `no_ignore` so they do not hide a function either.

Rules the script computes itself (ruff has no equivalent):
  function-lines        a function body over 80 non-blank, non-comment lines
  file-lines            over 400 such lines; an over-limit file may not grow
  assertion-free-test   a test function with no assert, no pytest.raises /
                        pytest.warns, and no call to an assert*/expect* helper
  cognitive-complexity  a function over 15 (complexipy's `code_complexity` on
                        the source text, so no complexipy config file applies;
                        same metric and threshold as the Node and Rust gates)

Test code (tests/, test_*.py, *_test.py, conftest.py) is exempt from the size
and argument rules only.

Usage:
  python3 scripts/ci/lint_ratchet.py            compare against RATCHET_BASE
  python3 scripts/ci/lint_ratchet.py --report   print repo-wide Tier-2 totals

Exit codes: 0 pass, 1 regression, 2 the ratchet itself could not run.
"""

import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Run as a script, so Python has already put this directory on sys.path.
from ci_git import (
    REPO_ROOT,
    ChangedFile,
    GitError,
    changed_files,
    git,
    is_test_path,
    resolve_merge_base,
)

# Tier 2, measured with `ruff check --isolated`, so these are the only rules and
# thresholds that apply, whatever the repo's ruff config says.
RUFF_SELECT = ["C901", "PLR0912", "PLR0913", "PLR0915", "PLR1702", "ANN401"]
# Work inside loops (v3): a loop that only appends or assigns is a comprehension
# (PERF401, PERF403); `.items()` with one half unused is `.keys()`/`.values()`
# (PERF102). ruff has no await-in-loop or query-in-loop rule; that is a known gap.
RUFF_SELECT += ["PERF102", "PERF401", "PERF403"]
# pytest rules that catch tests which cannot fail or pass for the wrong reason.
# Style-only PT rules (parametrize style, unittest-style asserts) are left out.
PT_SELECT = ["PT010", "PT011", "PT012", "PT015", "PT017", "PT029", "PT030", "PT031"]
RUFF_SETTINGS = [
    "lint.mccabe.max-complexity=15",
    "lint.pylint.max-branches=15",
    "lint.pylint.max-args=5",
    "lint.pylint.max-statements=50",
    "lint.pylint.max-nested-blocks=4",
]
FUNCTION_LINES_LIMIT = 80
FILE_LINES_LIMIT = 400
COGNITIVE_COMPLEXITY_LIMIT = 15

RULE_FUNCTION_LINES = "function-lines"
RULE_FILE_LINES = "file-lines"
RULE_ASSERTION_FREE = "assertion-free-test"
RULE_COGNITIVE = "cognitive-complexity"
RULE_NOQA = "noqa-comments"
RULE_RESTRICTED = "restricted-noqa"

# Size and argument rules do not apply to test code.
TEST_EXEMPT = {"PLR0913", "PLR0915", RULE_FUNCTION_LINES, RULE_FILE_LINES}
# A suppression comment naming any of these, or a blanket one, fails the file.
RESTRICTED_PREFIXES = tuple(RUFF_SELECT + PT_SELECT + ["complexipy"])

# Spelled with character classes so linters do not read this line as a directive.
NOQA_RE = re.compile(r"#\s*[nN][oO][qQ][aA](?::\s*(?P<codes>[A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*))?", re.IGNORECASE)
# complexipy's own two spellings of an inline ignore.
COMPLEXIPY_IGNORE_RE = re.compile(r"#\s*(complexipy\s*:\s*ignore|[nN][oO][qQ][aA]\s*:\s*complexipy)", re.IGNORECASE)
ASSERT_HELPER_RE = re.compile(r"^(assert|expect)", re.IGNORECASE)
RAISES_RE = re.compile(r"^(raises|warns|deprecated_call|assertRaises\w*|assertWarns\w*)$")

Counts = Dict[str, int]


# --------------------------------------------------------------------------
# Pure logic. No I/O below this line until the "I/O" banner.
# --------------------------------------------------------------------------


def code_lines(source: str) -> List[int]:
    """1-based numbers of lines that are neither blank nor comment-only."""
    return [n for n, line in enumerate(source.splitlines(), 1) if line.strip() and not line.strip().startswith("#")]


def count_file_lines(source: str) -> int:
    return len(code_lines(source))


def _functions(tree: ast.AST) -> List[ast.AST]:
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def long_functions(source: str, tree: ast.AST, limit: int = FUNCTION_LINES_LIMIT) -> List[str]:
    """Names of functions whose span holds more than `limit` code lines."""
    counted = set(code_lines(source))
    long: List[str] = []
    for node in _functions(tree):
        span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
        if sum(1 for n in span if n in counted) > limit:
            long.append(node.name)
    return long


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _asserts(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            name = _call_name(child)
            if ASSERT_HELPER_RE.match(name) or RAISES_RE.match(name):
                return True
    return False


def _test_functions(tree: ast.Module) -> List[ast.AST]:
    found: List[ast.AST] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            found.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            found += [
                item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test")
            ]
    return found


def assertion_free_tests(tree: ast.Module) -> List[str]:
    """Test functions that assert nothing: no `assert`, no pytest.raises/warns,
    no call to a helper named assert*/expect* (self.assertEqual,
    mock.assert_called_once_with, expect_shape, ...)."""
    return [node.name for node in _test_functions(tree) if not _asserts(node)]


def noqa_comments(source: str) -> List[Optional[List[str]]]:
    """Every `# noqa` comment: None for a blanket one, else its codes.
    A complexipy ignore comment counts as `["complexipy"]`.
    Comments only: a `# noqa` inside a string literal is not counted."""
    found: List[Optional[List[str]]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return found
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        if COMPLEXIPY_IGNORE_RE.search(token.string):
            found.append(["complexipy"])
            continue
        match = NOQA_RE.search(token.string)
        if match:
            codes = match.group("codes")
            found.append(re.split(r"[\s,]+", codes.strip().upper()) if codes else None)
    return found


def restricted_noqa(noqas: List[Optional[List[str]]]) -> List[str]:
    """Blanket `# noqa`s and codes that name a Tier-2 rule."""
    out: List[str] = []
    for codes in noqas:
        if codes is None:
            out.append("blanket")
        else:
            out += [code for code in codes if code.startswith(RESTRICTED_PREFIXES)]
    return out


def custom_counts(path: str, source: str) -> Tuple[Counts, List[Optional[List[str]]]]:
    """Counts for the rules this script computes, plus the file's noqas."""
    counts: Counts = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return counts, []
    over = long_functions(source, tree)
    if over:
        counts[RULE_FUNCTION_LINES] = len(over)
    if is_test_path(path):
        free = assertion_free_tests(tree)
        if free:
            counts[RULE_ASSERTION_FREE] = len(free)
    return counts, noqa_comments(source)


def unscored_functions(tree: ast.Module) -> List[ast.AST]:
    """Outermost functions complexipy does not report: those under a
    module-level if/try/with/for/match, and methods of nested classes.
    (It reports module-level functions and methods of module-level classes,
    and folds nested functions into the enclosing one.) The caller scores each
    one as a method of a module-level class."""
    scored = set()
    for node in tree.body:
        items = node.body if isinstance(node, ast.ClassDef) else [node]
        scored.update(id(item) for item in items)
    found: List[ast.AST] = []
    pending = list(ast.iter_child_nodes(tree))
    while pending:
        node = pending.pop()
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pending += ast.iter_child_nodes(node)
        elif id(node) not in scored:
            found.append(node)
    return found


def cognitive_counts(complexities: List[int], limit: int = COGNITIVE_COMPLEXITY_LIMIT) -> Counts:
    over = sum(1 for c in complexities if c > limit)
    return {RULE_COGNITIVE: over} if over else {}


def ruff_counts(diagnostics: List[dict]) -> Counts:
    counts: Counts = {}
    for d in diagnostics:
        code = d.get("code") or ""
        if code:
            counts[code] = counts.get(code, 0) + 1
    return counts


class Row:
    def __init__(self, path: str, rule: str, base: int, head: int, regressed: bool):
        self.path, self.rule, self.base, self.head, self.regressed = path, rule, base, head, regressed

    @property
    def delta(self) -> int:
        return self.head - self.base


class Side:
    """One file measured at one revision."""

    def __init__(self, counts: Counts, lines: int, noqas: List[Optional[List[str]]]):
        self.counts, self.lines, self.noqas = counts, lines, noqas


EMPTY = Side({}, 0, [])


def compare_file(path: str, base: Side, head: Side) -> List[Row]:
    """Rows for one file. Pass EMPTY as `base` for an added file."""
    test = is_test_path(path)
    rows: List[Row] = []
    for rule in sorted(set(base.counts) | set(head.counts)):
        if test and rule in TEST_EXEMPT:
            continue
        b, h = base.counts.get(rule, 0), head.counts.get(rule, 0)
        rows.append(Row(path, rule, b, h, h > b))
    if not test:
        grew_over = head.lines > FILE_LINES_LIMIT and head.lines > base.lines
        rows.append(Row(path, RULE_FILE_LINES, base.lines, head.lines, grew_over))
    rows.append(Row(path, RULE_NOQA, len(base.noqas), len(head.noqas), len(head.noqas) > len(base.noqas)))
    restricted = restricted_noqa(head.noqas)
    if restricted:
        rows.append(Row(path, "%s (%s)" % (RULE_RESTRICTED, ", ".join(sorted(set(restricted)))), 0, len(restricted), True))
    return rows


def format_table(rows: List[Row]) -> str:
    header = ("file", "rule", "base", "head", "delta")
    body = [(r.path, r.rule, str(r.base), str(r.head), "%+d" % r.delta) for r in rows]
    widths = [max(len(col[i]) for col in [header] + body) for i in range(5)]
    return "\n".join("  " + "  ".join(col[i].ljust(widths[i]) for i in range(5)).rstrip() for col in [header] + body)


FIX_HINTS = """The fix is to refactor the function or file you touched, not to suppress the rule:
  C901 / PLR0912 / PLR1702    extract the branchy part into a named helper; return early
  PLR0913                     group the parameters into a dataclass
  PLR0915 / function-lines    split the function
  cognitive-complexity        flatten it: guard clauses, extract nested loops into helpers
  file-lines                  split the module
  ANN401                      write the type
  PERF401 / PERF403 / PERF102 use the comprehension (or .keys()/.values()) ruff names
  PT0xx                       see `ruff rule <code>`
  assertion-free-test         assert the behaviour, or delete the test
  noqa-comments               do not add `# noqa` to a file you touch
Thresholds live in scripts/ci/lint_ratchet.py and change only in a reviewed PR."""


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


class RatchetError(Exception):
    """A condition that must stop the run with exit 2."""


def changed_python_files(merge_base: str) -> List[ChangedFile]:
    return [f for f in changed_files(merge_base) if f.head_path.endswith(".py")]


def run_ruff(paths: List[str], stdin: Optional[str] = None) -> List[dict]:
    command = [sys.executable, "-m", "ruff", "check", "--isolated", "--preview", "--no-cache", "--exit-zero"]
    command += ["--output-format", "json", "--select", ",".join(RUFF_SELECT + PT_SELECT)]
    for setting in RUFF_SETTINGS:
        command += ["--config", setting]
    if stdin is not None:
        command += ["--stdin-filename", paths[0], "-"]
    else:
        command += paths
    done = subprocess.run(command, cwd=str(REPO_ROOT), input=stdin, stdout=subprocess.PIPE, text=True, check=False)
    if done.returncode != 0:
        raise RatchetError("ruff exited %d" % done.returncode)
    return json.loads(done.stdout or "[]")


def cognitive_complexities(source: str) -> List[int]:
    """complexipy's score for every function, inline ignores disregarded."""
    from complexipy import code_complexity  # the project's pinned dev dependency

    def score(text: str) -> List[int]:
        return [f.complexity for f in code_complexity(text, no_ignore=True).functions]

    try:
        tree = ast.parse(source)
        scores = score(source)
    except (SyntaxError, ValueError):  # unparseable: the Tier-1 `ruff check` job fails the file
        return []
    # A skipped function's own lines, verbatim (so `else: if` stays `else: if`),
    # under a module-level class: complexipy then scores it as it would in place.
    lines = io.StringIO(source, newline=None).readlines()  # ast's line numbering
    for node in unscored_functions(tree):
        try:
            scores += score("class _:\n" + "".join(lines[node.lineno - 1 : node.end_lineno]))
        except ValueError as error:
            raise RatchetError("complexipy cannot score %s at line %d: %s" % (node.name, node.lineno, error))
    return scores


def relative(filename: str) -> str:
    path = Path(filename)
    return str(path.relative_to(REPO_ROOT)) if path.is_absolute() else filename


def ruff_by_file(paths: List[str]) -> Dict[str, List[dict]]:
    by_file: Dict[str, List[dict]] = {path: [] for path in paths}
    for d in run_ruff(paths) if paths else []:
        by_file.setdefault(relative(d["filename"]), []).append(d)
    return by_file


def measure(path: str, source: str, diagnostics: List[dict]) -> Side:
    counts = ruff_counts(diagnostics)
    extra, noqas = custom_counts(path, source)
    counts.update(extra)
    counts.update(cognitive_counts(cognitive_complexities(source)))
    return Side(counts, count_file_lines(source), noqas)


def ratchet(base_ref: str) -> int:
    merge_base = resolve_merge_base(base_ref)
    if not merge_base:
        print('lint-ratchet: cannot resolve base ref "%s". Fetch it or set RATCHET_BASE.' % base_ref, file=sys.stderr)
        return 2
    print("lint-ratchet: base %s (%s)" % (base_ref, merge_base[:12]))
    files = changed_python_files(merge_base)
    if not files:
        print("lint-ratchet: no changed Python files; nothing to ratchet.")
        return 0

    head_diagnostics = ruff_by_file([f.head_path for f in files])
    rows: List[Row] = []
    for f in files:
        head_source = (REPO_ROOT / f.head_path).read_text(errors="replace")
        head = measure(f.head_path, head_source, head_diagnostics.get(f.head_path, []))
        base_source = None if f.added else git(["show", "%s:%s" % (merge_base, f.base_path)], allow_failure=True)
        base = EMPTY if base_source is None else measure(f.head_path, base_source, run_ruff([f.head_path], base_source))
        rows += compare_file(f.head_path, base, head)

    print("lint-ratchet: checked %d changed file(s)." % len(files))
    improved = [r for r in rows if r.delta < 0]
    if improved:
        print("\nImproved:\n" + format_table(improved))
    regressions = [r for r in rows if r.regressed]
    if not regressions:
        print("\nlint-ratchet: PASS; no Tier-2 regressions in the touched files.")
        return 0
    print("\nlint-ratchet: FAIL; these changes make touched files worse:\n", file=sys.stderr)
    print(format_table(regressions), file=sys.stderr)
    print("\n" + FIX_HINTS, file=sys.stderr)
    return 1


def report() -> int:
    paths = [p for p in (git(["ls-files", "-co", "--exclude-standard", "--", "*.py"]) or "").split("\n") if p]
    by_file = ruff_by_file(paths)
    totals: Counts = {}
    over = 0
    for path in paths:
        source = (REPO_ROOT / path).read_text(errors="replace")
        side = measure(path, source, by_file.get(path, []))
        for rule, n in side.counts.items():
            if not (is_test_path(path) and rule in TEST_EXEMPT):
                totals[rule] = totals.get(rule, 0) + n
        over += int(not is_test_path(path) and side.lines > FILE_LINES_LIMIT)
        totals[RULE_NOQA] = totals.get(RULE_NOQA, 0) + len(side.noqas)
    totals[RULE_FILE_LINES + " (files over %d)" % FILE_LINES_LIMIT] = over
    print("Tier-2 totals across the repo (the ratchet gates the delta per touched file):\n")
    width = max(len(rule) for rule in totals) if totals else 10
    for rule in sorted(totals):
        print("  %s  %5d" % (rule.ljust(width), totals[rule]))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tier-2 lint ratchet (Python).")
    parser.add_argument("--base", default=os.environ.get("RATCHET_BASE") or "origin/main")
    parser.add_argument("--report", action="store_true", help="print repo-wide Tier-2 totals instead of gating")
    args = parser.parse_args(argv)
    try:
        return report() if args.report else ratchet(args.base)
    except (RatchetError, GitError) as error:
        print("lint-ratchet: %s" % error, file=sys.stderr)
        return 2
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as error:  # a crash, pyo3's PanicException included, must never read as a regression (exit 1)
        print("lint-ratchet: internal error: %r" % (error,), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
