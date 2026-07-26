# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.28.0] - 2026-07-25

### Added

- `repository pull-request close` — closes a PR via `PUT /stemma-pull-request/api/pulls/{rid}/update` (fetch-then-close, plan default, `--apply --yes`, read-back verification; already-closed short-circuits, server confirmed idempotent). contract-verified: disposable test PR created, closed, and confirmed CLOSED/merged=false on a live Foundry deployment.
- `global-proposal create --merge-to main|<branch-rid>` — full `ProposalMergeTo` union support (both arms evidenced from recovered generated types: `main` and `branchRid`). Invalid targets fail loud with the server's typed `Branch:InvalidMergeTo`.
- `global-branch create --add-resource <rid>` (repeatable) — non-empty `resourcesToAdd` entries (plain ResourceRid strings; live-verified shape). Unbranchable resources surface the server's typed `Branch:ResourcesUnableToBranchError`.
- `preview_transform` remains a documented gap; the local-dev-access preview endpoint is mounted but exposes no usable grant.

## [0.27.0] - 2026-07-25

### Added

- MCP gap-closure cycle: all six areas unblocked by the `@palantir/mcp` client-contract investigation are now real, contract-verified implementations. Scorecard: **72 implemented / 1 blocked** (only `preview_transform`, which does not exist in any published MCP version).
- New `compute` command group: `compute info`, `compute logs`, `compute manage` (start/stop/dev-mode), `compute execute`. Compute calls route through the mounted `contour-backend-multiplexer` + `build2` + `foundry-telemetry-service` surfaces (the old `/module-group/api/*` path was the wrong prefix). Mutations are plan-first with `--apply`; success shapes our token cannot reach are passed through raw with `shape_verified: false`.
- `dev-console sdk generate` is now real (was blocked-with-evidence): reads `applicationVersion`, POSTs `{"applicationVersion": N, "npm": {}}` to `application-sdks/v2/{rid}`, polls to terminal status. contract-verified end-to-end (real SDK versions minted on the designated disposable tutorial app).
- `repository create-python-transforms` is now real (was blocked-with-evidence): the captured two-call chain (`POST /stemma/api/repos {"path"}` + `POST /repository-bootstrapper/api/repos/{rid}/bootstrap`). contract-verified create → content check → permanent delete.
- `connectivity webhook update` now really publishes (`{"spec": ...}` body, `queryParamsV2` array-wrap quirk, domain→domainId resolution), and `connectivity rest-source create` now really creates (the magritte `/v3` envelope). Both contract-verified with disposable entities, cleaned up.
- `global-branch create` and `global-proposal create` upgraded from plan-only to real (`resourcesToAdd` + auto-resolved `compassNamespaceRid`; `mergeTo` union). contract-verified create → load → close cycles; everything closed.

### Fixed

- Re-pinned the palantir_expert benchmark corpus to 0.27.0.

## [0.26.0] - 2026-07-24

### Added

- `ontology object-type-upsert` now performs real merge-delta updates on existing object types: loads current state via the internal `bulkLoadEntities` endpoint, applies caller-provided fields (display name, description), dry-run validates, then modifies. No-op updates skip the modify (no ontology version bump). Fail-closed guards refuse primary-key changes, backing-dataset changes, and types with interface implementations or shared property types that cannot be faithfully reconstructed. Link/action type upserts keep the explicit create-only refusal.

## [0.25.0] - 2026-07-24

### Added

- MCP parity cycle ("the parity milestone"): the CLI now covers 68 of the 73 tools in Palantir's official Foundry MCP catalog (was 19), with the remaining 5 marked `blocked` with live evidence in `pltr capabilities`.
- Ontology authoring via the contract-verified internal `modifyOntology` contract: `ontology object-type-upsert`, `object-type-delete`, `link-type-upsert`, `link-type-delete`, `action-type-upsert`, `action-type-delete`. All default to a dry-run validation plan; real mutations require `--apply` (deletes also `--yes`) and are read-back verified. Upserts document the required publication order and emit pointed hints when validation errors signal an out-of-order change.
- New command groups: `repository` (pull-request list/get/create/comment, context, clone, create-python-transforms), `global-branch` and `global-proposal` (create/get/close), `dev-console` (connect, osdk definition, sdk generate, sdk install, convert-osdk-react), `docs` (11 documentation subcommands backed by Palantir's public docs site), `osdk` (context, examples), `platform-sdk` (api list, api reference).
- New reads: `ontology rid`, `ontology link-type-get`, `ontology action-type-get`, `functions search`, `namespace list` (real Compass namespaces, replacing the Space fallback), `project templates list`, `connectivity webhook get`, `connectivity egress ensure` (read-or-refuse; never creates policies).
- Connectivity writes: `webhook create` (contract verified to the stack permission boundary), plus plan-only `webhook update` and `rest-source create` that refuse `--apply` until their write contracts are verified.
- Honest no-mutation postures where contracts are unverifiable without mutating: `dev-console sdk generate` and `repository create-python-transforms` exit with probe evidence instead of guessing.

### Fixed

- Re-verified the palantir_expert benchmark corpus against the 0.25.0 command surface and bumped its version gate.

## [0.24.0] - 2026-07-24

### Added

- Added bounded, paginated cross-resource discovery to `pltr search` with verified path-prefix filtering, page tokens, and explicit page-local text/type filter coverage.
- Added `pltr notepad list` to enumerate notepad resources from an explicit Compass path prefix.
- Added the `pltr-agent-v1` envelope and registered command manifest for reliable agent-facing CLI use.

### Fixed

- `pltr configure list` now honors global `--agent` output and redacts credentials.
- `pltr configure delete` now rejects prompt-dependent execution under `--non-interactive` unless `--force` is supplied.
- Repaired SDK call paths and added contract coverage for the current Foundry SDK surface.

### Documentation

- Updated the README, command reference, troubleshooting guide, and agent skill documentation for the agent-first CLI contracts.

## [0.23.0] - 2026-07-23

### Added

- Added optional, failure-safe Langfuse tracing for CLI invocations. When Langfuse credentials are present, each invocation emits a span with sensitive environment variables and flags redacted; otherwise tracing is a no-op. Enabled via the optional `langfuse` extra.


## [0.22.0] - 2026-07-23

### Added

- Added `pltr folder move` for relocating a folder to a new parent.

### Documentation

- Documented the release-script metadata-version fix under `docs/solutions/runtime-errors/`.


## [0.21.0] - 2026-07-23

### Added

- Added `pltr search <text>` for cross-resource search across Foundry, returning matching resources with their type and path.


## [0.20.0] - 2026-07-23

### Added

- Completed full-lifecycle change-impact analysis: `pltr dependency` now answers "what breaks downstream if I change this" across the whole Foundry lifecycle, both above and below the ontology.
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
- Added `pltr notepad get` for reading a notepad's latest body and its embedded resource references.
- Added a Palantir expert benchmark corpus and scorer for grading command-contract knowledge.

### Changed

- Upgraded runtime and development dependencies, and hardened continuous integration with a locked dependency sync and a runtime dependency audit.

### Fixed

- Fixed `pltr notepad get` reporting an inconclusive read for every notepad, caused by requesting a composite metadata field without a subselection.
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
- Removed the MCP launcher integration; native `pltr` commands are the supported agent interface.

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
[0.4.0]: https://github.com/anjor/pltr-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/anjor/pltr-cli/releases/tag/v0.3.0
