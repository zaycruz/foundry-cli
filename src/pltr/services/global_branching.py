"""
Global Branching service wrapper.

Read-only load-by-RID access backed by the internal ``branch-service`` API
(23 endpoints, base ``/branch-service/api``), per the 2026-07-22 gap analysis.

CAUTION carried over from the gap analysis: branch-service is enabled but
UNUSED on a live Foundry deployment, and the success response shapes are UNVERIFIED.
2026-07-24 live validation confirmed only the mount and the error contract:
``PUT /branch/load/{branchRid}`` and ``PUT /branch/proposal/load/{proposalRid}``
with an empty body return a structured ``Branch:PermissionDeniedError`` (403)
for an inaccessible RID. No live branch or proposal RID exists on the stack,
so a 2xx payload has never been observed.

Write surface (2026-07-24 contract-recovery validation, logged in
``the captured contract``):

- branch-service rejects unknown JSON keys with
  ``422 Conjure:UnprocessableEntity`` and fails missing required fields with
  ``400 Default:InvalidArgument``, so single-key probes identify real fields.
- ``POST /branch/create`` deserialized the oracle-derived field set
  ``{displayName, description, ontologyRid}`` but never progressed past
  ``400 Default:InvalidArgument`` (no field named in the error), so the
  create contract is NOT VERIFIED end-to-end. The CLI ships it plan-first
  and refuses ``--apply`` rather than guessing further.
- ``POST /branch/proposal/create`` is in the same state with
  ``{branchRid, description, displayName}``.
- ``PUT /branch/close/{branchRid}`` and
  ``PUT /branch/proposal/close/{proposalRid}`` take an empty body with the
  RID in the path; the error contract is contract-verified
  (``Branch:PermissionDeniedError`` naming ``branch:edit-branch`` /
  ``branch:edit-proposal``). The success shape is UNVERIFIED.

Reads and verified writes pass responses through raw with strict
shape-checking: anything that is not a non-empty JSON object fails loudly
instead of rendering as a result.
"""

from typing import Any, Dict, Mapping

from .base import BaseService
from .foundry_internal_client import FoundryInternalClient


class GlobalBranchNotFoundError(RuntimeError):
    """Raised when branch-service has no branch or proposal for a RID."""


class GlobalBranchShapeError(RuntimeError):
    """Raised when a branch-service response is not a loadable JSON object."""


class _BranchServiceBase(BaseService):
    """Shared branch-service read plumbing."""

    def _get_service(self) -> Any:
        """Get the Foundry client (branch loads use the internal API)."""
        return self.client

    def _load(self, path: str, rid: str, entity: str) -> Dict[str, Any]:
        """Load one branch-service entity by RID, failing loud on surprises."""
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure("PUT", path, json_body={})
        except Exception as e:
            raise RuntimeError(f"Failed to load {entity} {rid}: {e}") from e

        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name in {
            "Branch:BranchNotFound",
            "Branch:ProposalNotFound",
        } or (status == 404 and error_name != "Route:RouteNotMounted"):
            raise GlobalBranchNotFoundError(f"No {entity} found for RID {rid}")
        if not 200 <= status < 300:
            if error_name == "Route:RouteNotMounted":
                raise RuntimeError(
                    "The branch-service API is not mounted on this stack "
                    f"(Route:RouteNotMounted for /{path})"
                )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"branch-service {entity} load failed with HTTP {status}{detail}: "
                f"{str(raw)[:200]}"
            )

        # Success shape UNVERIFIED (no live branch/proposal exists on the
        # verified stack): require a non-empty JSON object and pass it through
        # raw rather than projecting fields that may not exist.
        if not isinstance(payload, Mapping) or not payload:
            raise GlobalBranchShapeError(
                f"Unverified branch-service {entity} response shape: expected a "
                f"non-empty JSON object, got {str(raw)[:200]!r}. Refusing to "
                "guess at the contract."
            )
        return dict(payload)

    def _internal_client(self) -> FoundryInternalClient:
        """Build an internal API client for the active profile."""
        from ..auth.base import ProfileNotFoundError
        from ..config.profiles import ProfileManager

        profile_name = self.profile or ProfileManager().get_active_profile()
        if not profile_name:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'pltr configure configure' to set up authentication."
            )
        return FoundryInternalClient(profile_name)

    @staticmethod
    def _plan(
        verb: str, path: str, body: Mapping[str, Any], contract: str
    ) -> Dict[str, Any]:
        """Describe a write without issuing it (dry-run payload)."""
        return {
            "mode": "plan",
            "request": {"verb": verb, "path": f"/{path}", "body": dict(body)},
            "contract": contract,
        }

    def _write(
        self, verb: str, path: str, rid: str, entity: str
    ) -> Dict[str, Any]:
        """Issue a contract-verified empty-body write, failing loud on surprises."""
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(verb, path, json_body={})
        except Exception as e:
            raise RuntimeError(f"Failed to {verb} {entity} {rid}: {e}") from e

        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name in {
            "Branch:BranchNotFound",
            "Branch:ProposalNotFound",
        } or (status == 404 and error_name != "Route:RouteNotMounted"):
            raise GlobalBranchNotFoundError(f"No {entity} found for RID {rid}")
        if not 200 <= status < 300:
            if error_name == "Route:RouteNotMounted":
                raise RuntimeError(
                    "The branch-service API is not mounted on this stack "
                    f"(Route:RouteNotMounted for /{path})"
                )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"branch-service {entity} write failed with HTTP {status}{detail}: "
                f"{str(raw)[:200]}"
            )

        # Success shape UNVERIFIED (no live branch/proposal exists on the
        # verified stack). A 2xx with an empty body is an acknowledgment;
        # a non-object body is a contract surprise and fails loudly.
        if payload is None or payload == "" or payload == {}:
            return {"rid": rid, "acknowledged": True, "response_empty": True}
        if not isinstance(payload, Mapping):
            raise GlobalBranchShapeError(
                f"Unverified branch-service {entity} write response shape: "
                f"expected a JSON object or an empty body, got "
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )
        return dict(payload)


class GlobalBranchService(_BranchServiceBase):
    """Service wrapper for Global Branch operations."""

    CREATE_CONTRACT = (
        "UNVERIFIED: oracle-recovered fields {displayName, description, "
        "ontologyRid} deserialize but never progress past "
        "400 Default:InvalidArgument on a live Foundry deployment (verified; "
        "no field named in the error). Refusing to guess further."
    )
    CLOSE_CONTRACT = (
        "contract-verified: PUT /branch/close/{branchRid}, empty "
        "body; error contract contract-verified (403 Branch:PermissionDeniedError "
        "naming branch:edit-branch). Success shape UNVERIFIED."
    )

    def get_branch(self, branch_rid: str) -> Dict[str, Any]:
        """
        Load one Global Branch by RID.

        Read-only against branch-service ``PUT /branch/load/{branchRid}``
        (empty-body load; contract verified, success shape
        UNVERIFIED — there is no list endpoint, load-by-RID only).

        Args:
            branch_rid: Global Branch Resource Identifier

        Returns:
            Raw branch dictionary

        Raises:
            GlobalBranchNotFoundError: If no branch exists for the RID
            GlobalBranchShapeError: If the response is not a JSON object
            RuntimeError: If the read fails or the API is not mounted
        """
        return self._load(
            f"branch-service/api/branch/load/{branch_rid}", branch_rid, "branch"
        )

    def plan_create_branch(
        self, display_name: str, description: str, ontology_rid: str
    ) -> Dict[str, Any]:
        """
        Describe a Global Branch create without issuing it.

        The create contract is UNVERIFIED (see CREATE_CONTRACT), so the CLI
        never sends this body; the plan is the deliverable.

        Args:
            display_name: Branch display name
            description: Branch description
            ontology_rid: Ontology RID the branch forks

        Returns:
            Plan dictionary with the would-be request and contract status
        """
        return self._plan(
            "POST",
            "branch-service/api/branch/create",
            {
                "displayName": display_name,
                "description": description,
                "ontologyRid": ontology_rid,
            },
            self.CREATE_CONTRACT,
        )

    def close_branch(self, branch_rid: str) -> Dict[str, Any]:
        """
        Close one Global Branch (DESTRUCTIVE).

        Contract-verified empty-body write against branch-service
        ``PUT /branch/close/{branchRid}``; success shape UNVERIFIED, passed
        through raw with strict shape-checking.

        Args:
            branch_rid: Global Branch Resource Identifier

        Returns:
            Raw close response, or an acknowledgment for an empty 2xx body

        Raises:
            GlobalBranchNotFoundError: If no branch exists for the RID
            GlobalBranchShapeError: If the response is a non-object surprise
            RuntimeError: If the write fails or the API is not mounted
        """
        return self._write(
            "PUT", f"branch-service/api/branch/close/{branch_rid}", branch_rid, "branch"
        )


class GlobalProposalService(_BranchServiceBase):
    """Service wrapper for Ontology Global Proposal operations."""

    CREATE_CONTRACT = (
        "UNVERIFIED: oracle-recovered fields {branchRid, description, "
        "displayName} deserialize but never progress past "
        "400 Default:InvalidArgument on a live Foundry deployment (verified; "
        "no live branch exists to reference). Refusing to guess further."
    )
    CLOSE_CONTRACT = (
        "contract-verified: PUT /branch/proposal/close/{proposalRid}, "
        "empty body; error contract contract-verified (403 "
        "Branch:PermissionDeniedError naming branch:edit-proposal). Success "
        "shape UNVERIFIED."
    )

    def get_proposal(self, proposal_rid: str) -> Dict[str, Any]:
        """
        Load one Ontology Global Proposal by RID.

        Read-only against branch-service
        ``PUT /branch/proposal/load/{proposalRid}`` (empty-body load; contract
        verified, success shape UNVERIFIED — there is no list
        endpoint, load-by-RID only).

        Args:
            proposal_rid: Global Proposal Resource Identifier

        Returns:
            Raw proposal dictionary

        Raises:
            GlobalBranchNotFoundError: If no proposal exists for the RID
            GlobalBranchShapeError: If the response is not a JSON object
            RuntimeError: If the read fails or the API is not mounted
        """
        return self._load(
            f"branch-service/api/branch/proposal/load/{proposal_rid}",
            proposal_rid,
            "proposal",
        )

    def plan_create_proposal(
        self, branch_rid: str, display_name: str, description: str
    ) -> Dict[str, Any]:
        """
        Describe a Global Proposal create without issuing it.

        The create contract is UNVERIFIED (see CREATE_CONTRACT), so the CLI
        never sends this body; the plan is the deliverable.

        Args:
            branch_rid: Global Branch RID the proposal belongs to
            display_name: Proposal display name
            description: Proposal description

        Returns:
            Plan dictionary with the would-be request and contract status
        """
        return self._plan(
            "POST",
            "branch-service/api/branch/proposal/create",
            {
                "branchRid": branch_rid,
                "description": description,
                "displayName": display_name,
            },
            self.CREATE_CONTRACT,
        )

    def close_proposal(self, proposal_rid: str) -> Dict[str, Any]:
        """
        Close one Ontology Global Proposal (DESTRUCTIVE).

        Contract-verified empty-body write against branch-service
        ``PUT /branch/proposal/close/{proposalRid}``; success shape
        UNVERIFIED, passed through raw with strict shape-checking.

        Args:
            proposal_rid: Global Proposal Resource Identifier

        Returns:
            Raw close response, or an acknowledgment for an empty 2xx body

        Raises:
            GlobalBranchNotFoundError: If no proposal exists for the RID
            GlobalBranchShapeError: If the response is a non-object surprise
            RuntimeError: If the write fails or the API is not mounted
        """
        return self._write(
            "PUT",
            f"branch-service/api/branch/proposal/close/{proposal_rid}",
            proposal_rid,
            "proposal",
        )
