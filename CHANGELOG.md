# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

### Fixed

- `project create` / `folder` / `space` / `resource` JSON leaked Python object reprs for timestamps (`"created_time": "<built-in method time of datetime.datetime object at ...>"`). The `_format_timestamp` helpers in 5 services matched `datetime` via `hasattr(t, "time")` and returned the bound-method repr; they now serialize to ISO-8601. (Regression-tested.)
- `project list` returned empty even when projects existed: projects are `COMPASS_FOLDER` resources with a `project_rid` attribute, and the filter only accepted `type == "PROJECT"` / `ri.compass.main.project.*` RIDs. Now matches folders whose `project_rid` equals their own rid. (Live-verified: 14 projects listed.)
- Empty SDK error messages: foundry-platform-sdk error classes have empty `str()` (fields in `name`/`parameters`), so 185 `raise RuntimeError(f"... {e}")` sites produced truncated/empty errors (e.g. `Failed to create transaction ...: `). Added `BaseService._describe_error()` and applied it across 23 service files; SDK errors now surface their error name (e.g. `OpenTransactionAlreadyExists`, `MarkingNotFound`).
- `streams dataset create` / `stream create` documented and passed `{"fieldSchemaList": [...]}` but the SDK `StreamSchema` requires `{"fields": [{"name", "schema": {"nullable", "dataType"}}]}` — every documented invocation failed validation. Added `_normalize_stream_schema` accepting both shapes with a type map. (Regression-tested.)
- Stale command references in user-facing output: `sql submit`/`sql status` hints and dataset suggestions still said `foundry ...` after the rename; now `pfoundry ...`.

- `dataset preview` crashed with a pydantic ValidationError: the SDK `read_table` accepts only `ARROW`/`CSV`, and the service passed `format="pandas"`. It now requests `ARROW` and converts via `to_pandas()`. (Regression-tested.)
- Every call site that passed `preview=True` to a non-beta SDK endpoint emitted a `UserWarning` on each invocation (e.g. `project list`, `resource get`, `folder children`, `admin marking get`, `space list`, `organization create`). All non-accepting endpoints no longer receive `preview`; accepting endpoints (`Space.*` except `list`, `Project.replace`, `Folder.replace`, `Role.get_batch`, beta `widgets`) keep it. Verified with warnings-as-errors against a live stack.
- `admin user get` / `user markings` / `revoke-all-tokens` leaked raw pydantic validation errors and rejected compass user RIDs. A `_normalize_user_id` validator now accepts a bare UUID or `ri.compass.main.user.<uuid>` RID and raises a clean, actionable error naming `pfoundry admin user list`.
- `utils/completion.py` still watched the legacy `_FOUNDRY_COMPLETE` env var after the command rename, so completion-time setup never ran for `pfoundry`.
- Security: sitemap XML parsing in `docs` service used `xml.etree` on untrusted network content (XXE risk). Now uses `defusedxml` (new direct dependency + stub), with a regression test proving entity-expansion payloads are rejected.

### Changed

- Console command renamed from `foundry` to `pfoundry` to avoid clashing with the official Palantir Foundry CLI (`foundry`, installed via the stack's install script). The package name `foundry-cli`, module `foundry_cli`, config dir `~/.config/foundry`, and keyring service name are unchanged. All docs, skills, completion scripts, error hints, and the Hermes plugin now reference `pfoundry`.

### Added

- `ontology object-type-guarded-upsert` — the first composite mutation command: preflight state load → dependency impact gate (same engine as `foundry dependency object-type`, with `--change`/`--change-type` and a retained `--graph-output` artifact) → plan-first upsert → authoritative read-back, in one invocation. `--yes` is required when `must_verify_before_merge` items are unresolved; net-new types and `--skip-impact-gate` record explicit caveats; coverage gaps are carried as caveats, never treated as "no impact". Motivated by Langfuse trace evidence of agents hand-assembling get→dependency×3-5→upsert→read-back chains.
- `ontology object-type-guarded-delete` — the delete counterpart: preflight load (typed not-found aborts before planning) → impact gate (`--change-type` defaults to `remove-delete`) → plan-first delete → verified-removed read-back. Always double-gated (`--apply --yes`).
- Self-correcting agent error envelopes (`src/foundry_cli/utils/error_hints.py`): recognized failure classes now carry an additive `error.hint` field in the agent/JSON envelope — dependency `--branch` name-vs-RID misuse, ontology get not-found name probing (points to `foundry ontology resolve`), and upsert argument errors (names required flags, points to the guarded upsert). Human/table output is unchanged; hint command/flag references are pinned against the live app in tests.
- `proposal` group is no longer fail-closed: code-pr `create`/`list`/`get`/`comment`/`close` delegate to `RepositoryService` and global-proposal `create`/`get`/`close` delegate to `GlobalProposalService`. `create` and `comment` are dry-run plan by default with `--apply` to execute. Still fail-closed with exit 6 `unsupported-capability` (per-pair reasons): code-pr `approve`/`request-changes`/`merge`, global-proposal `list`/`comment`/`approve`/`request-changes`/`merge`/`accept`.
- Skill bundle: nine new workflow skills under `skills/foundry-cli/workflows/` — `ontology-authoring`, `proposal-review`, `data-ingestion`, `build-triage`, `osdk-app-development`, `compute-module-ops`, `media-management`, `admin-audit`, and `ai-workloads` — so every command group now has a step-through operating procedure. All commands verified against the live CLI grammar; SDK capability gaps are documented explicitly instead of worked around.
- Skill bundle: "Choosing the right tool" section in `SKILL.md` mapping agent situations (name→RID resolution, pre-mutation gating, unsupported capabilities, scripting) to the correct entry-point command or workflow.
- `dataset schema update` — intentional additive schema migration: `--add-field name:TYPE[:nullable[:default]]` / `--fields-json`, `--branch`, client-side optimistic concurrency via `--expected-schema-version`, dry-run default with `--apply`, authoritative schema read-back. Additive-only: type changes on existing fields are rejected.
- `dataset schema set` is now manifest-visible (`--format`/`--output`) and accepts `--expected-schema-version`.
- `ontology object-type-add-property` — add a property to an existing object type with backing-column mapping via modifyOntology; dry-run default, `--branch-rid` targets a non-default ontology branch, read-back returns the created property RID.
- `ontology action-type-update` — evolve an existing action type (function rules, parameter add/remove/reorder, protected `currentUser` binding, submission criteria, write authorization, status EXPERIMENTAL→ACTIVE); dry-run default, full-metadata read-back on apply.
- `ontology resolve` (risk `read`) — typed identifier resolver: API name ↔ RID ↔ internal IDs for object types, properties, action types, and functions.
- `foundry.services.errors.FoundryApiError` — typed API errors preserving Foundry's `errorName`/`errorCode`/`errorInstanceId`/safe parameters/validation details through to the agent envelope (`buffer_agent_exception`).
- Value-level credential redaction in the agent envelope: URL userinfo (git remotes, registry URLs), Bearer/Basic headers, `_authToken` registry lines, argv-style `--token` flags, and `KEY=value` env dumps are scrubbed before output reaches the model or logs.

### Fixed

- `ontology resolve` / `object-type-add-property` / `action-type-update` API-name paths: the bulk-load `ObjectTypeIdentifier`/`ActionTypeIdentifier` unions have no API-name variant (leniently dropped server-side, yielding null entries or 400s); API names are now resolved to RIDs through the SDK before loading. Contract-verified against a live deployment.
- `action-type-update` wire encoding: `validationsOrdering` entries are emitted as the `ValidationRuleIdentifier` union (`{"type":"rid",...}` / `{"type":"validationRuleIdInRequest",...}` — plain strings 422), and loaded `logicRuleRid` maps to `logicRuleIdentifier` so rules keep their identity. Dry-run contract-verified against a live deployment, including an EXPERIMENTAL→ACTIVE status transition.
- `--output FILE` in agent mode no longer strands the result: the payload is buffered, so the single stdout envelope carries the data (previously surfaced as an `unstructured` error — the harness `invalid_json` false positives).
- Status chatter (`print_success`/`print_error`/...) moves to stderr when stdout is piped, keeping `--format json` stdout parseable.

### Removed
- The `palantir_expert` benchmark corpus, scorer, and tests. The CLI is the subject
  of that benchmark, not its owner; it now lives with the rest of the evaluation
  harness. Nothing the CLI ships depended on it.

## [0.29.1] - 2026-07-26

### Changed
- Release path is gated: a `v*` tag now runs the test suite before building, and
  publishing waits on the `pypi` environment reviewer.
- CI reports every matrix leg (`fail-fast: false`) behind a single `ci-ok` status
  check, and cancels superseded runs.
- Test suite no longer depends on terminal colour: `GITHUB_ACTIONS`, `FORCE_COLOR`
  and `PY_COLORS` are neutralised before collection, so assertions on flag strings
  behave the same locally and in CI.
- Test fixtures are platform-agnostic: file writes pin UTF-8, path comparisons are
  normalised, and symlink creation is guarded. Windows and Linux now run in CI.
- `scripts/release.py` pushes only the tag; `main` is protected, so the version
  commit travels through a pull request. `RELEASE.md` describes the real flow.
- Capability and service descriptions no longer cite documents this package does
  not ship, and no longer name a credential-reading endpoint the CLI never calls.


## [0.28.0] - 2026-07-25

### Added

- `repository pull-request close` — closes a PR via `PUT /stemma-pull-request/api/pulls/{rid}/update` (fetch-then-close, plan default, `--apply --yes`, read-back verification; already-closed short-circuits, server confirmed idempotent). Contract-verified: disposable test PR created, closed, and confirmed CLOSED/merged=false against a live deployment.
- `global-proposal create --merge-to main|<branch-rid>` — full `ProposalMergeTo` union support (both arms evidenced from recovered generated types: `main` and `branchRid`). Invalid targets fail loud with the server's typed `Branch:InvalidMergeTo`.
- `global-branch create --add-resource <rid>` (repeatable) — non-empty `resourcesToAdd` entries (plain ResourceRid strings; live-verified shape). Unbranchable resources surface the server's typed `Branch:ResourcesUnableToBranchError`.
- `preview_transform` remains a documented gap; the local-dev-access preview endpoint is mounted but exposes no usable grant.

## [0.27.0] - 2026-07-25

### Added

- MCP gap-closure cycle: all six areas unblocked by the `@palantir/mcp` client-contract investigation are now real, contract-verified implementations. Scorecard: **72 implemented / 1 blocked** (only `preview_transform`, which does not exist in any published MCP version).
- New `compute` command group: `compute info`, `compute logs`, `compute manage` (start/stop/dev-mode), `compute execute`. Compute calls route through the mounted `contour-backend-multiplexer` + `build2` + `foundry-telemetry-service` surfaces (the old `/module-group/api/*` path was the wrong prefix). Mutations are plan-first with `--apply`; success shapes our token cannot reach are passed through raw with `shape_verified: false`.
- `dev-console sdk generate` is now real (was blocked-with-evidence): reads `applicationVersion`, POSTs `{"applicationVersion": N, "npm": {}}` to `application-sdks/v2/{rid}`, polls to terminal status. Contract-verified end-to-end (real SDK versions minted on the designated disposable tutorial app).
- `repository create-python-transforms` is now real (was blocked-with-evidence): the captured two-call chain (`POST /stemma/api/repos {"path"}` + `POST /repository-bootstrapper/api/repos/{rid}/bootstrap`). Contract-verified create → content check → permanent delete.
- `connectivity webhook update` now really publishes (`{"spec": ...}` body, `queryParamsV2` array-wrap quirk, domain→domainId resolution), and `connectivity rest-source create` now really creates (the magritte `/v3` envelope). Both contract-verified with disposable entities, cleaned up.
- `global-branch create` and `global-proposal create` upgraded from plan-only to real (`resourcesToAdd` + auto-resolved `compassNamespaceRid`; `mergeTo` union). Contract-verified create → load → close cycles; everything closed.

### Fixed

- Re-pinned the palantir_expert benchmark corpus to 0.27.0.

## [0.26.0] - 2026-07-24

### Added

- `ontology object-type-upsert` now performs real merge-delta updates on existing object types: loads current state via the internal `bulkLoadEntities` endpoint, applies caller-provided fields (display name, description), dry-run validates, then modifies. No-op updates skip the modify (no ontology version bump). Fail-closed guards refuse primary-key changes, backing-dataset changes, and types with interface implementations or shared property types that cannot be faithfully reconstructed. Link/action type upserts keep the explicit create-only refusal.

## [0.25.0] - 2026-07-24

### Added

- MCP parity cycle ("the parity milestone"): the CLI now covers 68 of the 73 tools in Palantir's official Foundry MCP catalog (was 19), with the remaining 5 marked `blocked` with live evidence in `foundry capabilities`.
- Ontology authoring via the contract-verified internal `modifyOntology` contract: `ontology object-type-upsert`, `object-type-delete`, `link-type-upsert`, `link-type-delete`, `action-type-upsert`, `action-type-delete`. All default to a dry-run validation plan; real mutations require `--apply` (deletes also `--yes`) and are read-back verified. Upserts document the required publication order and emit pointed hints when validation errors signal an out-of-order change.
- New command groups: `repository` (pull-request list/get/create/comment, context, clone, create-python-transforms), `global-branch` and `global-proposal` (create/get/close), `dev-console` (connect, osdk definition, sdk generate, sdk install, convert-osdk-react), `docs` (11 documentation subcommands backed by Palantir's public docs site), `osdk` (context, examples), `platform-sdk` (api list, api reference).
- New reads: `ontology rid`, `ontology link-type-get`, `ontology action-type-get`, `functions search`, `namespace list` (real Compass namespaces, replacing the Space fallback), `project templates list`, `connectivity webhook get`, `connectivity egress ensure` (read-or-refuse; never creates policies).
- Connectivity writes: `webhook create` (contract verified to the stack permission boundary), plus plan-only `webhook update` and `rest-source create` that refuse `--apply` until their write contracts are verified.
- Honest no-mutation postures where contracts are unverifiable without mutating: `dev-console sdk generate` and `repository create-python-transforms` exit with probe evidence instead of guessing.

### Fixed

- Re-verified the palantir_expert benchmark corpus against the 0.25.0 command surface and bumped its version gate.

## [0.24.0] - 2026-07-24

### Added

- Added bounded, paginated cross-resource discovery to `foundry search` with verified path-prefix filtering, page tokens, and explicit page-local text/type filter coverage.
- Added `foundry notepad list` to enumerate notepad resources from an explicit Compass path prefix.
- Added the `foundry-agent-v1` envelope and registered command manifest for reliable agent-facing CLI use.

### Fixed

- `foundry configure list` now honors global `--agent` output and redacts credentials.
- `foundry configure delete` now rejects prompt-dependent execution under `--non-interactive` unless `--force` is supplied.
- Repaired SDK call paths and added contract coverage for the current Foundry SDK surface.

### Documentation

- Updated the README, command reference, troubleshooting guide, and agent skill documentation for the agent-first CLI contracts.

## [0.23.0] - 2026-07-23

### Added

- Added optional, failure-safe Langfuse tracing for CLI invocations. When Langfuse credentials are present, each invocation emits a span with sensitive environment variables and flags redacted; otherwise tracing is a no-op. Enabled via the optional `langfuse` extra.


## [0.22.0] - 2026-07-23

### Added

- Added `foundry folder move` for relocating a folder to a new parent.

### Documentation

- Documented the release-script metadata-version fix.


## [0.21.0] - 2026-07-23

### Added

- Added `foundry search <text>` for cross-resource search across Foundry, returning matching resources with their type and path.


## [0.20.0] - 2026-07-23

### Added

- Completed full-lifecycle change-impact analysis: `foundry dependency` now answers "what breaks downstream if I change this" across the whole Foundry lifecycle, both above and below the ontology.
- Added transport selection with `--providers sdk,conjure,graphql` and a configuration-gated `--positive-controls` flag for firing endpoint canaries, alongside the existing `--no-internal` public-SDK-only fallback.
- Added degraded-mode reporting. An unreachable, permission-denied, or drifted internal endpoint records a coverage gap and the command still exits successfully with the public-SDK graph intact. Only target resolution, artifact writes, and authentication remain fatal.

### Changed

- Internal transport failures now report as inconclusive rather than partial. A partial result implies some data was obtained; no internal response means absence was never tested, and the two must not be confused.

### Fixed

- The fail-toward-false-safety contract is now mechanically enforced rather than conventional. Every internal operation is characterized against empty, truncated, and permission-denied responses and must not report verified-empty coverage. The single sanctioned exception, a build specification proving a dataset has no producing transform, requires both a passing endpoint canary and independent confirmation that the dataset exists.
- Added registry-completeness, canary-contract, and provenance-resolution checks, plus permanent regression guards for out-of-order streamed responses, omitted branch fallbacks, and resources absent from the lineage index.

### Known limitations

- Workshop variables remain unreadable on the verified stack.
- Notepad object-reference widget configurations remain bundle-derived and are not resolved to ontology bindings.

## [0.19.1] - 2026-07-22

### Added

- Added reverse dependency analysis over Foundry's internal APIs: object types to the Workshop modules and third-party applications that consume them, per-application SDK version ranges for consumers, code repository to transform to dataset lineage, and property to dataset column mapping.
- Added `foundry notepad get` for reading a notepad's latest body and its embedded resource references.
- Added a Palantir expert benchmark corpus and scorer for grading command-contract knowledge.

### Changed

- Upgraded runtime and development dependencies, and hardened continuous integration with a locked dependency sync and a runtime dependency audit.

### Fixed

- Fixed `foundry notepad get` reporting an inconclusive read for every notepad, caused by requesting a composite metadata field without a subselection.
- Restored the ontology action and object read commands after platform SDK drift.

### Known limitations

- Internal-API coverage degrades explicitly. Empty, truncated, permission-denied, and expired-token results are reported as inconclusive, never as verified absence.

## [0.18.0] - 2026-07-20

### Added

- Added Compass discovery commands for namespace-like Foundry Space listing, project imports, and bounded project search.
- Added dataset statistics with file and transaction aggregates, pagination limits, and coverage metadata.
- Added bounded resource graphs with stable RID-based identities for filesystem hierarchy and project-reference relationships.

### Changed

- Added a native agent output contract and capability manifest with pagination metadata, redaction, explicit errors, and safety gates.
- Removed the MCP launcher integration; native `foundry` commands are the supported agent interface.

### Known limitations

- Project-template listing remains explicitly unsupported because the pinned SDK exposes template creation but no public template catalog operation.
- Namespace discovery is namespace-like Space discovery; no separate public Namespace API is exposed by the pinned SDK.
- Resource graphs do not represent full transformation lineage and report incomplete coverage when applicable.

## [0.4.0] - 2025-01-31

### Added
- Comprehensive folder management functionality
- Preview mode support for folder API operations

### Fixed
- CI pipeline issues
- Code style and formatting improvements

## [0.3.0] - 2024-12-XX

### Added
- Initial release with core CLI functionality
- Palantir Foundry API integration
- Command-line interface for data operations

[0.18.0]: https://github.com/zaycruz/foundry-cli/compare/v0.17.1...v0.18.0
[0.4.0]: https://github.com/zaycruz/foundry-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/zaycruz/foundry-cli/releases/tag/v0.3.0
