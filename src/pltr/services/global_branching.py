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

These are load endpoints (reads) despite the PUT verb; no mutation is issued.
Responses are passed through raw with strict shape-checking: anything that is
not a non-empty JSON object fails loudly instead of rendering as a result.
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


class GlobalBranchService(_BranchServiceBase):
    """Service wrapper for read-only Global Branch operations."""

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


class GlobalProposalService(_BranchServiceBase):
    """Service wrapper for read-only Ontology Global Proposal operations."""

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
