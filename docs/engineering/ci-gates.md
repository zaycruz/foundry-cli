# CI quality gates

This repo runs the Raava CI quality gates standard v2, Python template
(`engineering/standards/ci-quality-gates-standard.md` in the org repo; decisions in
ADR-0001, ADR-0003, ADR-0006). Adopted 2026-09-23, bead `raava-wc6.24`. This is the
first Python repo on the standard.

Every gate is deterministic, and no gate uses a stored baseline. Each ratcheted gate
compares HEAD with the **merge base of `main`**: on a pull request it uses
`origin/main`, and on a push to `main` it uses the previous tip. Actions are pinned to
full commit SHAs. Gate tools are exact pins in the `dev` group of `pyproject.toml` and
come from `uv.lock` (`uv sync --locked --dev`).

## The checks

`.github/workflows/ci.yml` runs on every pull request and on every push to `main`
(Python 3.12, `ubuntu-24.04`, unless stated):

| Check | Command | Fails when |
|---|---|---|
| `typecheck` | `uv run mypy src/foundry_cli` (`mypy.ini`) | any type error |
| `lint` | `ruff check .` (Tier 1, `ruff.toml`), `ruff format --check .`, then `regexploit-py` on every tracked `.py` file | a Tier 1 rule fires, a file is not formatted, or a regex has exponential backtracking (ReDoS) |
| `lint-ratchet` | `scripts/ci/lint_ratchet.py` (ruff `--isolated` + complexipy) | a touched file gets worse on a Tier 2 rule, an added file has any Tier 2 finding, or a touched file gains a `# noqa` |
| `test` | `pytest --cov` | any test fails. It also writes `coverage.xml` |
| `test-matrix` | `pytest tests/` on Linux, macOS, Windows x Python 3.10, 3.11, 3.12, 3.13 | any test fails on any combination (the old CI matrix) |
| `diff-coverage` | `diff-cover coverage.xml --fail-under=80` | less than 80 % of the changed executable lines in `src/foundry_cli` are covered. A file no test imports counts as 0 % |
| `build` | `uv build` | the sdist or wheel does not build |
| `dead-code` | `scripts/ci/dead_code.py` (vulture + deptry, at the base and at HEAD) | the change adds an unused function, class, variable, or import, or dependency drift (unused, missing, transitive, misplaced) |
| `duplication` | `jscpd --baseline-from-ref <merge base> --fail-on-new-clones 0` | the change adds a clone of 10 or more lines and 70 or more tokens |
| `mutation` | `scripts/ci/mutation.py` (mutmut 3.7.0 on the functions that contain added lines) | more than 2 mutants go undetected **and** the score is below 70 %. A timed-out mutant counts as undetected. Pull requests only. **Advisory** |
| `secrets` | gitleaks 8.30.1: the working tree, then `<merge base>..HEAD` | any finding |
| `deps` | `pip-audit --skip-editable` on the locked dev environment | any known vulnerability (no severity filter) |
| `bench` | `scripts/ci/bench.py` | does nothing until `bench/` exists. **Advisory** |
| `ci-ok` | aggregate | **Transitional**, see below |

`.github/workflows/pr-policy.yml` runs on pull requests. It runs again when a label or
the title changes.

| Check | Fails when |
|---|---|
| `pr-size` | more than 400 added lines outside tests, lockfiles, Markdown, and generated files, unless a code owner who is not the author applied `large-change` |
| `regression-proof` | a fix PR (label `fix`, or a title that starts `fix:`, `fix(scope):`, or `fix!:`) has no changed test that fails on the base source and passes on HEAD. Other PRs pass with "skip" |

**Required checks (target):** `typecheck`, `lint`, `lint-ratchet`, `test`,
`diff-coverage`, `build`, `dead-code`, `duplication`, `secrets`, `deps`, `pr-size`,
`regression-proof`. `test-matrix` is a matrix job; its checks are named per
combination, so it is required through `ci-ok` only. `mutation` becomes required after 2
weeks if its p90 job time is 10 minutes or less (ADR-0003 §5). `bench` becomes required
after the standard §10.2 criteria are met. Record each promotion here.

## Transition

The repository ruleset "main protection" requires two checks that predate this
standard: `ci-ok` and `secret and environment-data scan` (`security.yml`). Both are
kept so that pull requests stay mergeable until the ruleset changes:

- `ci-ok` now fails unless every job in `ci.yml` except `mutation` and `bench` succeeds.
- `security.yml` is unchanged. `secrets` runs the same two scans (tree and PR range),
  but with the merge-base `.gitleaks.toml`.

When the ruleset requires the target checks above, delete the `ci-ok` job and
`security.yml` in one follow-up PR.

**Code-owner review.** `.github/CODEOWNERS` names `@zaycruz @King-Mayster`. Only
`@zaycruz` is a collaborator on this repository. Do not enable "Require review from
Code Owners" until a second owner has write access (or the repo moves to
`raava-solutions`): with one owner, no PR by that owner can be merged.

## Run them locally

```bash
uv sync --locked --dev
uv run mypy src/foundry_cli
uv run ruff check . && uv run ruff format --check .
git ls-files -z '*.py' | xargs -0 uv run regexploit-py     # must print no "Vulnerable regex"
uv run pytest --cov --cov-report=xml:coverage.xml
uv run python -m unittest discover -s scripts/ci/tests     # the gate scripts' own tests
uv run python scripts/ci/lint_ratchet.py
uv run python scripts/ci/dead_code.py
uv run python scripts/ci/mutation.py                       # about 3 minutes
uv run pip-audit --skip-editable
python3 scripts/ci/pr_size.py
PR_TITLE='fix: x' uv run python scripts/ci/regression_proof.py   # or --force
uv run python scripts/ci/lint_ratchet.py --report          # repo-wide Tier 2 totals (no gate)
```

The ratchets compare with `origin/main` by default. To use a different base, set
`RATCHET_BASE`. If your branch is behind `main`, merge `main` first. If you do not, the
commits on `main` appear in your diff.

## Tiers

Tier 1 (error, `lint`): ruff `E4 E7 E9 F`, `PGH004` (a bare `# noqa`), `RUF100` (a
`# noqa` that suppresses nothing), `T10` (debugger breakpoints); `ruff format`; ReDoS
(regexploit, no inline suppression: rewrite the regex).

Tier 2 (`lint-ratchet`, thresholds fixed in `scripts/ci/lint_ratchet.py`): `C901` 15,
cognitive complexity 15 (complexipy), `PLR0912` 15 branches, `PLR0913` 5 arguments,
`PLR0915` 50 statements, `PLR1702` 4 nested blocks, `ANN401` (no `Any`), `PERF401`,
`PERF403`, `PERF102`, pytest misuse `PT010 PT011 PT012 PT015 PT017 PT029 PT030 PT031`,
function length 80, file length 400, `assertion-free-test`, and the count of `# noqa`
comments. A blanket `# noqa`, one naming a Tier 2 rule, or `# complexipy: ignore` in a
touched file fails outright.

### Tier 2 totals at adoption (2026-09-23, `lint_ratchet.py --report`)

| Rule | Count |
|---|---|
| `ANN401` | 290 |
| `PLR0913` | 208 |
| `cognitive-complexity` | 137 |
| `function-lines` | 100 |
| `PERF401` | 44 |
| `file-lines` (files over 400) | 40 |
| `PLR0912` | 28 |
| `C901` | 28 |
| `PLR0915` | 26 |
| `PLR1702` | 25 |
| `noqa-comments` | 12 |
| `PT011` | 3 |
| `assertion-free-test` | 3 |
| `PERF102` | 1 |
| `PERF403` | 1 |
| **total** | **946** |

The ratchet makes sure no touched file adds to this. When a rule's count reaches zero,
move it to Tier 1 in `ruff.toml`.

## When a gate fails

- **`lint-ratchet`:** refactor the function or file you touched. You do not have to fix
  findings that were there before, but you cannot add to them.
- **`dead-code`:** delete the unused code or dependency. If vulture is wrong (a
  framework hook), add the decorator or name to `[tool.vulture]` in its own reviewed PR.
- **`duplication`:** extract the copied block into a shared function.
- **`diff-coverage` / `mutation`:** write tests that check the result, not only that
  the code ran. `mutmut show <name>` prints a surviving mutant.
- **`deps`:** upgrade the package (`uv lock --upgrade-package <name>`) and run the suite.
- **`pr-size`:** split the PR. If you cannot, a code owner who is not the author applies
  `large-change`.

## Changing a gate

The gate files (`pyproject.toml`, `uv.lock`, `ruff.toml`, `mypy.ini`, `.jscpd.json`,
`.gitleaks.toml`, `.gitleaksignore`, `.gitattributes`, `.github/**`, `scripts/ci/**`,
`bench/**`, `tests/conftest.py`, and the gate docs `AGENTS.md`, `CLAUDE.md`, and this
file) are code-owned (`.github/CODEOWNERS`).

Some gates measure a PR with merge-base files, so a change to them does not apply to the
PR that makes it.

When a PR edits `scripts/ci/`, these gates run the merge-base scripts: `lint-ratchet`,
`dead-code`, `mutation`, `bench`, `pr-size`, and `regression-proof` (including its
`--detect` step, so a PR cannot make itself "not a fix"). The Tier 2 rules and thresholds
live in `lint_ratchet.py` and are passed to ruff with `--isolated`, so `ruff.toml` and
`pyproject.toml` do not change what the ratchet measures.

These gates read a merge-base config:

- `dead-code`: vulture uses the base `[tool.vulture]` on both sides.
- `duplication` uses the base `.jscpd.json`.
- `secrets` uses the base `.gitleaks.toml` and `.gitleaksignore`; a PR cannot add them.
- `pr-size` uses the base `.gitattributes` (`linguist-generated`).

The other gates use the PR's own files. For these, code-owner review is the only
control:

- The workflows themselves (`ci.yml`, `pr-policy.yml`, and the merge-base action):
  `pull_request` runs the PR's versions.
- Tool versions: every gate that installs from `uv.lock` (all but `pr-size`,
  `duplication`, and `secrets`) uses the PR's lockfile, so a PR could pin an older ruff,
  complexipy, vulture, deptry, mutmut, or pip-audit.
- `typecheck` uses the PR's `mypy.ini`. `lint` uses the PR's `ruff.toml` (Tier 1 rules,
  the format excludes).
- `test` and `diff-coverage` use the PR's `[tool.pytest.ini_options]` and
  `[tool.coverage.run]`, and `diff-coverage`'s flags are in the PR's `ci.yml`.
- `dead-code`: deptry reads each side's own `pyproject.toml`, including
  `[tool.deptry]` ignores.
- `mutation` reads the PR's `[tool.mutmut]` (`also_copy`, test selection).
- `deps` audits the PR's `uv.lock`.

## Repo-specific choices

- `ruff format --check` stays in `lint` (it was in the old `lint-and-format` job).
  `ruff.toml` excludes `scripts/ci/**` from the formatter only: those files are verbatim
  template copies.
- `test-matrix` keeps the old 3-OS x 4-Python matrix because the CLI is published with
  those classifiers. Coverage and every gate run once, in `test`.
- `mypy.ini` targets Python 3.10 (`requires-python >= 3.10`); mypy 2.x no longer
  accepts 3.9.
- `[tool.mutmut] also_copy` holds everything the tests read: `src/ scripts/ skills/
  llms.txt README.md`.
- `docs/` is untracked (`.gitignore`) except this file.
- `.gitignore` ignores root `*.json` files, so it un-ignores `/.jscpd.json`; without it
  jscpd would run with its defaults.
- mutmut is pinned to 3.7.0: 3.8.0 needs `click>=8.4.2`, and this project pins
  `click<8.4`.
- The old `ci.yml` uploaded coverage to Codecov only when a `CODECOV_TOKEN` secret was
  set. The repo has no such secret (2026-09-23), so the upload is dropped.
- `ontology-e2e.yml`, `publish.yml`, `claude.yml`, and `claude-code-review.yml` are not
  part of the gates and were not changed.
