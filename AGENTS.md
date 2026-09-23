# Repository Agent Instructions

These instructions are model-agnostic and apply to every coding agent working in this repository.

## Development

- Use `uv` for dependency management and to run Python commands.
- The wrapped SDK is `foundry-platform-python`; its upstream development branch is `develop`, not `main`.
- Be exact about what the Foundry SDK exposes. Preserve explicit gaps instead of guessing.
- Prefer removing unsupported behavior over returning misleading results.
- Treat Foundry identifiers as RIDs unless a command explicitly accepts an API name.

## Quality gates

CI runs the Raava CI quality gates (details, local commands, and which gates use
merge-base config: `docs/engineering/ci-gates.md`). Before you open a pull request:

- Run `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src/foundry_cli`,
  `uv run pytest`, and `uv run python scripts/ci/lint_ratchet.py`.
- A touched file may not get worse on a Tier 2 rule (complexity, cognitive complexity,
  arguments, nesting, `Any`, length, assertion-free tests). Refactor; do not add `# noqa`.
- New code needs tests that check results: 80 % of changed lines covered, and mutants in
  the functions you change must be caught.
- Do not add unused code, dependencies, copied blocks, or a regex with exponential
  backtracking.
- A fix PR (`fix:` title or `fix` label) needs a test that fails before the fix.
- Keep a PR under 400 added non-test lines. Only a code owner who is not the author may
  apply `large-change`.
- Do not edit a gate file (`.github/CODEOWNERS` lists them) to make your own PR pass.

## Mandatory Foundry change-impact gate

Before planning, proposing, or applying a change to a Foundry ontology resource, action, query, dataset, application, or other Compass resource:

1. Read `skills/foundry-cli/SKILL.md` and `skills/foundry-cli/workflows/change-impact-assessment.md`.
2. Run the matching read-only `pfoundry dependency` command with the intended `--change`, an explicit `--change-type` when one matches, `--output-mode agent`, and a retained `--graph-output` artifact.
3. Use the returned `agent` block to identify direct and transitive impact paths, action/query contracts, coverage gaps, `must_verify_before_merge`, and `should_verify_before_deploy`.
4. Treat `partial`, `inaccessible`, `unsupported`, `unresolved`, and `budget-exhausted` coverage as uncertainty—not proof that no dependency exists.
5. Do not merge a Foundry change while `agent.status` is `needs-verification` until every relevant `must_verify_before_merge` item is resolved or explicitly accepted by the operator.
6. After the change, rerun the same target with `--compare-artifact <baseline>` and `--output-mode ci`. Exit `0` is clean, `2` needs verification, and `1` is fatal.

The assessment is read-only. It does not authorize or execute a Foundry mutation.

## Skill source of truth

`skills/foundry-cli/` is the single canonical skill bundle for all agent clients. Do not create provider-specific copies. Client-specific instruction files may point here for compatibility but must not duplicate these rules.

## Documented knowledge

`CONCEPTS.md` defines shared project vocabulary. Consult it when the current work touches a documented term.
