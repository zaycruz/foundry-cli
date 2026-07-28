"""Composite guarded-mutation orchestration for ontology object types.

Composes the sequence agents previously hand-assembled across several CLI
invocations: read the current object type state, run the read-only
dependency/impact preflight (DependencyGraphService), build the
modifyOntology dry-run plan (ObjectTypeService.upsert_object_type /
delete_object_type), and — only when the command layer applies — issue the
real modification and verify it with an authoritative read-back.

The service never mutates in the ``prepare_*`` methods; mutation is
confined to the ``apply_*`` methods. Impact-gate uncertainty (partial /
inaccessible / unsupported / unresolved / budget-exhausted coverage) is
carried into the result's ``caveats`` and is never converted to "no impact".
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..utils.dependency_artifacts import (
    serialize_dependency_result,
    write_dependency_artifact,
)
from .base import BaseService
from .dependency import DependencyGraphService, DiscoveryBudget
from .ontology import ObjectTypeNotFoundError, ObjectTypeService

# Coverage statuses that mean the dependency gate could not fully see the
# blast radius. They are uncertainty, never proof of no impact.
UNCERTAIN_COVERAGE_STATUSES = frozenset(
    {
        "partial",
        "inconclusive",
        "token-expired",
        "inaccessible",
        "unsupported",
        "unresolved",
        "budget-exhausted",
    }
)


def _is_object_type_not_found(error: BaseException) -> bool:
    """Return whether the wrapped failure is the SDK ObjectTypeNotFound error.

    ``ObjectTypeService.get_object_type`` wraps SDK failures in RuntimeError
    with explicit chaining, so walk the cause/context chain and match the
    typed SDK error (with a class-name fallback for SDK variants).
    """
    seen: set[int] = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if type(current).__name__ == "ObjectTypeNotFound":
            return True
        current = current.__cause__ or current.__context__
    return False


class GuardedMutationService(BaseService):
    """Compose preflight reads, the impact gate, and mutation plan/apply."""

    def _get_service(self) -> Any:
        return self.client

    def _resolve_profile_host(self) -> tuple[str, str]:
        """Resolve the effective profile and its host for gate provenance."""
        effective_profile = self.profile or self.auth_manager.get_current_profile()
        if not effective_profile:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'pltr configure configure' to set up authentication."
            )
        credentials = self.auth_manager.storage.get_profile(effective_profile)
        host = credentials.get("host")
        if not host:
            raise MissingCredentialsError(
                f"Host URL not specified in credentials for profile "
                f"'{effective_profile}'"
            )
        return effective_profile, str(host)

    def _load_current_state(
        self,
        object_types: ObjectTypeService,
        ontology_rid: str,
        api_name: str,
        caveats: List[str],
    ) -> Dict[str, Any]:
        """Read the current object type, tolerating not-found as net-new."""
        try:
            current = object_types.get_object_type(ontology_rid, api_name)
        except RuntimeError as error:
            if not _is_object_type_not_found(error):
                raise
            caveats.append(
                f"object type '{api_name}' does not exist yet (net-new); the "
                "impact gate ran against no existing dependents. A net-new "
                "type can have no downstream dependents, but consumer "
                "surfaces were not assessed — record this substitution as a "
                "coverage gap per workflows/ontology-authoring.md."
            )
            return {"state": "net-new", "current": None}
        return {"state": "existing", "current": current}

    def _run_impact_gate(
        self,
        *,
        ontology_rid: str,
        api_name: str,
        change: Optional[str],
        change_type: Optional[str],
        graph_output: Optional[str],
        caveats: List[str],
    ) -> Dict[str, Any]:
        """Run the read-only dependency assessment via DependencyGraphService."""
        from .dependency_providers import ConjureRestProvider
        from .foundry_internal_client import FoundryInternalClient

        effective_profile, host = self._resolve_profile_host()
        internal_client = FoundryInternalClient(profile=effective_profile)
        provider = ConjureRestProvider(internal_client)
        service = DependencyGraphService(
            profile=effective_profile, conjure_provider=provider
        )
        context = service.create_context(
            host=host,
            ontology_rid=ontology_rid,
            budget=DiscoveryBudget(),
        )
        target = service.resolve_object_type(context, ontology_rid, api_name)
        raw_result = service.analyze(
            target,
            context,
            direction="both",
            change=change,
            change_type=change_type,
        )
        result = serialize_dependency_result(raw_result)
        artifact = write_dependency_artifact(
            result, Path(graph_output) if graph_output else None
        )

        for gap in result.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            coverage = gap.get("coverage")
            if coverage in UNCERTAIN_COVERAGE_STATUSES:
                caveats.append(
                    f"dependency coverage gap [{coverage}] on "
                    f"{gap.get('surface', 'unknown surface')} for "
                    f"{gap.get('target', api_name)}: "
                    f"{gap.get('message', 'no detail')}. Treat the impact "
                    "assessment as uncertain, not as no impact."
                )

        agent = result.get("agent") or {}
        return {
            "skipped": False,
            "status": agent.get("status", "clean"),
            "summary": agent.get("summary"),
            "change": agent.get("change"),
            "blast_radius": agent.get("blast_radius"),
            "release_risk": agent.get("release_risk"),
            "verification": agent.get("verification"),
            "coverage_completeness": agent.get("coverage_completeness"),
            "artifact": artifact,
        }

    def prepare_object_type_upsert(
        self,
        *,
        ontology_rid: str,
        api_name: str,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str] = None,
        change: Optional[str] = None,
        change_type: Optional[str] = None,
        skip_impact_gate: bool = False,
        graph_output: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the composite plan without mutating anything.

        Loads current state, runs the impact gate (unless net-new or
        explicitly skipped), and validates the upsert through the existing
        dry-run path. The returned composite carries preflight state, the
        compact impact agent block, the validated plan, and caveats.
        """
        caveats: List[str] = []
        object_types = ObjectTypeService(profile=self.profile)
        preflight = self._load_current_state(
            object_types, ontology_rid, api_name, caveats
        )

        if skip_impact_gate:
            caveats.append(
                "impact gate explicitly skipped via --skip-impact-gate; no "
                "dependency preflight was performed for this change"
            )
            impact: Dict[str, Any] = {
                "skipped": True,
                "status": "skipped",
                "reason": "--skip-impact-gate",
            }
            gate_mode = "skipped-requested"
        elif preflight["state"] == "net-new":
            impact = {
                "skipped": True,
                "status": "skipped",
                "reason": "net-new object type has no existing dependents",
            }
            gate_mode = "skipped-net-new"
        else:
            impact = self._run_impact_gate(
                ontology_rid=ontology_rid,
                api_name=api_name,
                change=change,
                change_type=change_type,
                graph_output=graph_output,
                caveats=caveats,
            )
            gate_mode = "run"

        plan = object_types.upsert_object_type(
            ontology_rid=ontology_rid,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
            apply=False,
        )

        verification = impact.get("verification") or {}
        must_verify = verification.get("must_verify_before_merge") or []
        return {
            "operation": "object-type-guarded-upsert",
            "request": {
                "ontologyRid": ontology_rid,
                "apiName": api_name,
                "displayName": display_name,
                "primaryKey": primary_key,
                "backingDataset": backing_dataset,
                "description": description,
                "change": change,
                "changeType": change_type,
            },
            "preflight": preflight,
            "impact": impact,
            "plan": plan,
            "gate": {
                "impact_gate": gate_mode,
                "verification_required": bool(
                    impact.get("status") == "needs-verification" and must_verify
                ),
                "verification_accepted": False,
            },
            "applied": False,
            "readback": None,
            "caveats": caveats,
        }

    def apply_object_type_upsert(
        self,
        prepared: Dict[str, Any],
        *,
        verification_accepted: bool = False,
    ) -> Dict[str, Any]:
        """Apply a prepared composite: upsert, then authoritative read-back.

        ``prepared`` must come from ``prepare_object_type_upsert``; the
        original request is replayed through the existing service path with
        ``apply=True``. The gate's acceptance decision is recorded on the
        result, never inferred.
        """
        request = prepared.get("request") or {}
        object_types = ObjectTypeService(profile=self.profile)
        upsert_result = object_types.upsert_object_type(
            ontology_rid=request["ontologyRid"],
            api_name=request["apiName"],
            display_name=request["displayName"],
            primary_key=request["primaryKey"],
            backing_dataset=request["backingDataset"],
            description=request.get("description"),
            apply=True,
        )

        try:
            current = object_types.get_object_type(
                request["ontologyRid"], request["apiName"]
            )
            readback: Dict[str, Any] = {
                "status": "verified",
                "object_type": current,
            }
        except Exception as error:
            readback = {
                "status": "not-verified",
                "detail": (
                    "read-back via SDK ontologies ObjectType.get failed: "
                    f"{error}"
                ),
            }

        gate = prepared.setdefault("gate", {})
        gate["verification_accepted"] = verification_accepted
        if verification_accepted:
            must_verify = (
                (prepared.get("impact") or {}).get("verification") or {}
            ).get("must_verify_before_merge") or []
            prepared.setdefault("caveats", []).append(
                f"operator explicitly accepted {len(must_verify)} unresolved "
                "must_verify_before_merge item(s) via --yes"
            )
        prepared["upsert"] = upsert_result
        prepared["applied"] = True
        prepared["readback"] = readback
        return prepared

    @staticmethod
    def _summarize_loaded_state(
        object_type_id: str, entry: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Project the bulk-loaded state entry to a compact summary."""
        object_type = entry.get("objectType") or {}
        display = object_type.get("displayMetadata") or {}
        return {
            "objectTypeId": object_type_id,
            "apiName": object_type.get("apiName"),
            "displayName": display.get("displayName"),
            "status": object_type.get("status"),
        }

    def prepare_object_type_delete(
        self,
        *,
        ontology_rid: str,
        object_type_id: str,
        change: Optional[str] = None,
        change_type: Optional[str] = None,
        skip_impact_gate: bool = False,
        graph_output: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the composite delete plan without mutating anything.

        Resolves the internal ObjectTypeId to the current state (a missing
        type fails with the typed ``ObjectTypeNotFoundError`` — a delete is
        never planned for something that does not exist), runs the impact
        gate against the resolved API name, and validates the delete through
        the existing dry-run path.
        """
        change = change or "delete object type"
        change_type = change_type or "remove-delete"
        caveats: List[str] = []
        object_types = ObjectTypeService(profile=self.profile)
        entry = object_types.load_object_type_state(object_type_id)
        preflight: Dict[str, Any] = {
            "state": "existing",
            "current": self._summarize_loaded_state(object_type_id, entry),
        }
        api_name = preflight["current"].get("apiName") or object_type_id

        if skip_impact_gate:
            caveats.append(
                "impact gate explicitly skipped via --skip-impact-gate; no "
                "dependency preflight was performed for this change"
            )
            impact: Dict[str, Any] = {
                "skipped": True,
                "status": "skipped",
                "reason": "--skip-impact-gate",
            }
            gate_mode = "skipped-requested"
        else:
            impact = self._run_impact_gate(
                ontology_rid=ontology_rid,
                api_name=api_name,
                change=change,
                change_type=change_type,
                graph_output=graph_output,
                caveats=caveats,
            )
            gate_mode = "run"

        plan = object_types.delete_object_type(
            ontology_rid=ontology_rid,
            object_type_id=object_type_id,
            apply=False,
        )

        verification = impact.get("verification") or {}
        must_verify = verification.get("must_verify_before_merge") or []
        return {
            "operation": "object-type-guarded-delete",
            "request": {
                "ontologyRid": ontology_rid,
                "objectTypeId": object_type_id,
                "apiName": api_name,
                "change": change,
                "changeType": change_type,
            },
            "preflight": preflight,
            "impact": impact,
            "plan": plan,
            "gate": {
                "impact_gate": gate_mode,
                "verification_required": bool(
                    impact.get("status") == "needs-verification" and must_verify
                ),
                "verification_accepted": False,
            },
            "applied": False,
            "readback": None,
            "caveats": caveats,
        }

    def apply_object_type_delete(
        self,
        prepared: Dict[str, Any],
        *,
        verification_accepted: bool = False,
    ) -> Dict[str, Any]:
        """Apply a prepared composite delete, then verify removal by read-back.

        ``prepared`` must come from ``prepare_object_type_delete``; the
        original request is replayed through the existing delete path with
        ``apply=True``. The read-back loads the type again: a typed not-found
        is the positive removal signal (``verified-removed``); a type that
        still loads is reported ``not-verified``, never raised over.
        """
        request = prepared.get("request") or {}
        object_types = ObjectTypeService(profile=self.profile)
        delete_result = object_types.delete_object_type(
            ontology_rid=request["ontologyRid"],
            object_type_id=request["objectTypeId"],
            apply=True,
        )

        try:
            object_types.load_object_type_state(request["objectTypeId"])
            readback: Dict[str, Any] = {
                "status": "not-verified",
                "detail": (
                    "object type still loads after the delete was applied"
                ),
            }
        except ObjectTypeNotFoundError:
            readback = {
                "status": "verified-removed",
                "detail": (
                    "post-delete load reports the object type as not found"
                ),
            }

        gate = prepared.setdefault("gate", {})
        gate["verification_accepted"] = verification_accepted
        if verification_accepted:
            must_verify = (
                (prepared.get("impact") or {}).get("verification") or {}
            ).get("must_verify_before_merge") or []
            prepared.setdefault("caveats", []).append(
                f"operator explicitly accepted {len(must_verify)} unresolved "
                "must_verify_before_merge item(s) via --yes"
            )
        prepared["delete"] = delete_result
        prepared["applied"] = True
        prepared["readback"] = readback
        return prepared


# Backwards-compatible alias: the guarded-upsert command and its tests were
# committed against this name before the service grew the delete counterpart.
GuardedUpsertService = GuardedMutationService
