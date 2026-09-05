# TICKET-008: Ontology object writes — upsert via actions, transaction `postEdits` lead

**Status**: Upsert-via-actions implemented 2026-09-03; `postEdits` remains a watch item
**Priority**: High — user-requested use case (upserts on ontology objects and actions)
**Found**: 2026-09-03 reverse-engineering session

## Summary

Object instances have no direct write endpoint in any published client —
writes go through **actions** or the experimental **ontology transactions**
API. The actionable contracts are already published; no UI capture needed.

## Evidence

Published client contract (strong), from two independent Palantir-published
clients:

- Installed `foundry-platform-python` SDK:
  - `Action.apply_with_overrides` / `apply_batch_with_overrides` →
    `POST /v2/ontologies/{o}/actions/{a}/applyWithOverrides`
    (`foundry_sdk/v2/ontologies/action.py:308`). Overrides cover
    `UniqueIdentifier` and `CurrentTime` generated parameters — the enabler
    for deterministic upsert-by-primary-key when the PK is generated.
  - `OntologyTransaction.post_edits` →
    `POST /v2/ontologies/{o}/transactions/{id}/edits`, preview-gated,
    `List[TransactionEdit]` body (`foundry_sdk/v2/ontologies/ontology_transaction.py:59`).
- `@palantir/mcp` 0.445.0 sourcemap (`/tmp/mcp-inspect/`, re-extract from npm
  cacache if purged): `@osdk/foundry.ontologies` `Action.js` and
  `OntologyTransaction.js` contain the identical paths.

## Shipped (2026-09-03)

- `ActionService.apply_action_with_overrides` / batch variant, and the
  plan-first object-upsert composite (`prepare_object_upsert` /
  `apply_object_upsert` with read-back verification) — see
  `src/foundry_cli/services/ontology.py` and `services/guarded_upsert.py`.
- Commands: `action-apply-with-overrides`, `object-upsert`,
  `object-upsert-batch` (dry-run plan default, `--apply` executes).

## Remaining leads / watch items

1. **Transaction lifecycle gap**: `postEdits` exists in both published
   clients, but **no begin/commit/abort endpoint** appears in either. Direct
   object edits (addObjects/modifyObjects without an action type) are
   therefore not shippable. Watch future `@palantir/mcp` dists and SDK
   releases for `beginTransaction`/`commitTransaction`; diff tool lists each
   release (same watch protocol as TICKET-005).
2. **Live verification checklist** for the shipped commands (required before
   `--apply` is treated as contract-verified, per `tickets/README.md`):
   - Mandatory change-impact preflight: `pfoundry dependency` with
     `--output-mode agent` and a retained `--graph-output` artifact against
     the target object type before any live mutation.
   - On a disposable object type + disposable upsert action type:
     VALIDATE_ONLY → apply → read-back for both create and update paths.
   - applyWithOverrides against a UniqueIdentifier-generated PK.
   - Record evidence in the service docstring (`global_branching.py:1-43`
     style). Until this passes, `--apply` stays fail-closed where the
     contract is unverified (precedent: `upsert_action_type`).

## Out of scope

- Bulk writes beyond the 20-request applyBatch cap (chunking only).
- Direct `postEdits` object writes — blocked on the transaction lifecycle gap.
