"""
Global Branching service wrapper.

Load-by-RID reads and plan-first writes backed by the internal
``branch-service`` API (base ``/branch-service/api``). There is no list
endpoint; load-by-RID only.

Write contracts, verified end-to-end against a live deployment, derived from
``@palantir/mcp`` 0.408.0 client contract):

- ``POST /branch/create`` takes ``{description, displayName, ontologyRid,
  resourcesToAdd, compassNamespaceRid}``; ``compassNamespaceRid`` is resolved
  first from ``POST /ontology-metadata/api/ontology/v2/load/all`` (body
  ``{"externalMappingConfigurationFilters": []}``, read
  ``ontologies[ontologyRid].compassNamespaceRid``). The success response is
  ``{"branchRecord": {"branchRid": "ri.branch..branch.<uuid>", ...}}`` —
  note the DOUBLE DOT in the rid (empty service segment). ``resourcesToAdd``
  entries are plain ResourceRid strings (server-evidenced:
  string entries deserialize and are branchability-checked; object entries
  are rejected with ``422 Conjure:UnprocessableEntity``).
- ``POST /branch/proposal/create`` takes ``{branchRid, displayName,
  description, mergeTo}`` where ``mergeTo`` is the ``ProposalMergeTo``
  Conjure union with exactly two arms (generated
  ``@palantir/branch-service-api`` ``proposalMergeTo.js``, recovered from
  the ``@palantir/mcp`` 0.408.0 dist published contract): ``{"main": {}, "type":
  "main"}`` (contract-verified 200) and ``{"branchRid": <rid>, "type":
  "branchRid"}`` (encoding accepted by the server, which answers a typed
  ``400 Branch:InvalidMergeTo`` for semantically invalid targets). The
  success response is ``{"proposal": {"proposalRid":
  "ri.branch..proposal.<uuid>", ...}}``.
- ``PUT /branch/close/{branchRid}`` and
  ``PUT /branch/proposal/close/{proposalRid}`` take an empty body with the
  RID in the path and return ``200 {}``.

Earlier validation never
got the creates past ``400 Default:InvalidArgument`` because it guessed
``namespaceRid`` instead of ``compassNamespaceRid`` and omitted
``resourcesToAdd``/``mergeTo``; the MCP capture recovered the exact bodies.

Reads and writes pass responses through raw with strict shape-checking:
anything that is not a non-empty JSON object fails loudly instead of
rendering as a result.
"""

import re
from typing import Any, Dict, List, Mapping, Optional

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

        # Require a non-empty JSON object and pass it through raw rather than
        # projecting fields that may not exist.
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

    def _write(self, verb: str, path: str, rid: str, entity: str) -> Dict[str, Any]:
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

        # A 2xx with an empty body is an acknowledgment (the close endpoints
        # return 200 {}); a non-object body is a contract surprise and fails
        # loudly.
        if payload is None or payload == "" or payload == {}:
            return {"rid": rid, "acknowledged": True, "response_empty": True}
        if not isinstance(payload, Mapping):
            raise GlobalBranchShapeError(
                f"Unverified branch-service {entity} write response shape: "
                f"expected a JSON object or an empty body, got "
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )
        return dict(payload)

    def _post(self, path: str, body: Mapping[str, Any], entity: str) -> Dict[str, Any]:
        """Issue a JSON-body POST, failing loud on surprises."""
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure("POST", path, json_body=body)
        except Exception as e:
            raise RuntimeError(f"Failed to POST {entity}: {e}") from e

        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name in {
            "Branch:BranchNotFound",
            "Branch:ProposalNotFound",
        } or (status == 404 and error_name != "Route:RouteNotMounted"):
            raise GlobalBranchNotFoundError(f"No {entity} found: {error_name}")
        if not 200 <= status < 300:
            if error_name == "Route:RouteNotMounted":
                raise RuntimeError(
                    "The branch-service API is not mounted on this stack "
                    f"(Route:RouteNotMounted for /{path})"
                )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"branch-service {entity} POST failed with HTTP {status}{detail}: "
                f"{str(raw)[:200]}"
            )

        if not isinstance(payload, Mapping) or not payload:
            raise GlobalBranchShapeError(
                f"Unexpected branch-service {entity} POST response shape: expected "
                f"a non-empty JSON object, got {str(raw)[:200]!r}. Refusing to "
                "guess at the contract."
            )
        return dict(payload)

    @staticmethod
    def _extract_rid(
        payload: Mapping[str, Any],
        record_key: str,
        rid_key: str,
        rid_prefix: str,
    ) -> str:
        """Pull a RID out of a create response, failing loud on surprises."""
        record = payload.get(record_key)
        rid = record.get(rid_key) if isinstance(record, Mapping) else None
        if (
            not isinstance(rid, str)
            or not rid.startswith(rid_prefix)
            or not _RID_SUFFIX_RE.fullmatch(rid[len(rid_prefix) :])
        ):
            raise GlobalBranchShapeError(
                f"Unexpected branch-service create response: expected "
                f"{record_key}.{rid_key} to be a {rid_prefix}<uuid> RID, got "
                f"{rid!r}. Refusing to guess at the contract."
            )
        return rid


_RID_SUFFIX_RE = re.compile(r"[0-9a-fA-F-]{36}")


class GlobalBranchService(_BranchServiceBase):
    """Service wrapper for Global Branch operations."""

    BRANCH_RID_PREFIX = "ri.branch..branch."
    CREATE_CONTRACT = (
        "contract-verified via @palantir/mcp published client contract "
        ": POST "
        "/branch/create with {description, displayName, ontologyRid, "
        "resourcesToAdd, compassNamespaceRid}; compassNamespaceRid resolved "
        "from POST /ontology-metadata/api/ontology/v2/load/all. Success "
        "response branchRecord.branchRid is ri.branch..branch.<uuid>. "
        "resourcesToAdd entries are plain ResourceRid strings "
        "(server-evidenced: object entries are rejected with "
        "422 Conjure:UnprocessableEntity; string entries are "
        "branchability-checked server-side)."
    )
    CLOSE_CONTRACT = (
        "contract-verified: PUT /branch/close/{branchRid}, empty "
        "body, 200 {} (contract-verified against a live deployment)."
    )

    def get_branch(self, branch_rid: str) -> Dict[str, Any]:
        """
        Load one Global Branch by RID.

        Read-only against branch-service ``PUT /branch/load/{branchRid}``
        (empty-body load; contract verified — there is no list
        endpoint, load-by-RID only).

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
        self,
        display_name: str,
        description: str,
        ontology_rid: str,
        resources_to_add: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Describe a Global Branch create without issuing it.

        Shows the verified request body; ``compassNamespaceRid`` is resolved
        from ontology-metadata only when the create is applied.

        Args:
            display_name: Branch display name
            description: Branch description
            ontology_rid: Ontology RID the branch forks
            resources_to_add: Resource RIDs (plain strings) to add to the
                branch at create; defaults to the verified empty array

        Returns:
            Plan dictionary with the would-be request and contract status
        """
        return self._plan(
            "POST",
            "branch-service/api/branch/create",
            {
                "description": description,
                "displayName": display_name,
                "ontologyRid": ontology_rid,
                "resourcesToAdd": list(resources_to_add or []),
                "compassNamespaceRid": "<resolved-at-apply>",
            },
            self.CREATE_CONTRACT,
        )

    def resolve_compass_namespace(self, ontology_rid: str) -> str:
        """
        Resolve the Compass namespace RID for an ontology.

        Verified: ``POST
        /ontology-metadata/api/ontology/v2/load/all`` with
        ``{"externalMappingConfigurationFilters": []}``, read
        ``ontologies[ontology_rid].compassNamespaceRid``.

        Args:
            ontology_rid: Ontology RID to resolve the namespace for

        Returns:
            The ontology's compassNamespaceRid

        Raises:
            GlobalBranchShapeError: If the response lacks the namespace RID
            RuntimeError: If the read fails
        """
        payload = self._post(
            "ontology-metadata/api/ontology/v2/load/all",
            {"externalMappingConfigurationFilters": []},
            "ontology namespace resolution",
        )
        ontologies = payload.get("ontologies")
        record = (
            ontologies.get(ontology_rid) if isinstance(ontologies, Mapping) else None
        )
        namespace_rid = (
            record.get("compassNamespaceRid") if isinstance(record, Mapping) else None
        )
        if not isinstance(namespace_rid, str) or not namespace_rid:
            raise GlobalBranchShapeError(
                "Unexpected ontology-metadata load/all response: expected "
                f"ontologies[{ontology_rid!r}].compassNamespaceRid to be a "
                "non-empty string. Refusing to guess at the contract."
            )
        return namespace_rid

    def create_branch(
        self,
        display_name: str,
        description: str,
        ontology_rid: str,
        resources_to_add: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Global Branch (REAL mutation).

        Resolves the Compass namespace first, then issues the verified
        ``POST /branch/create`` body. Returns the branchRecord plus the
        parsed branch RID (``ri.branch..branch.<uuid>`` — double dot).

        Args:
            display_name: Branch display name
            description: Branch description
            ontology_rid: Ontology RID the branch forks
            resources_to_add: Resource RIDs (plain strings) to add to the
                branch at create; defaults to the verified empty array. The
                server rejects resources it cannot branch with a typed
                ``Branch:ResourcesUnableToBranchError``.

        Returns:
            Dictionary with ``branchRid`` and the raw ``branchRecord``

        Raises:
            GlobalBranchShapeError: If a response misses the expected fields
            RuntimeError: If a request fails or the API is not mounted
        """
        namespace_rid = self.resolve_compass_namespace(ontology_rid)
        payload = self._post(
            "branch-service/api/branch/create",
            {
                "description": description,
                "displayName": display_name,
                "ontologyRid": ontology_rid,
                "resourcesToAdd": list(resources_to_add or []),
                "compassNamespaceRid": namespace_rid,
            },
            "branch",
        )
        branch_rid = self._extract_rid(
            payload, "branchRecord", "branchRid", self.BRANCH_RID_PREFIX
        )
        return {"branchRid": branch_rid, "branchRecord": payload["branchRecord"]}

    def close_branch(self, branch_rid: str) -> Dict[str, Any]:
        """
        Close one Global Branch (DESTRUCTIVE).

        Contract-verified empty-body write against branch-service
        ``PUT /branch/close/{branchRid}`` (200 {} contract-verified),
        passed through raw with strict shape-checking.

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

    PROPOSAL_RID_PREFIX = "ri.branch..proposal."
    MERGE_TO_MAIN: Dict[str, Any] = {"main": {}, "type": "main"}
    CREATE_CONTRACT = (
        "contract-verified via @palantir/mcp published client contract "
        ": POST "
        "/branch/proposal/create with {branchRid, displayName, description, "
        "mergeTo}; mergeTo is the ProposalMergeTo Conjure union with two "
        'arms: {"main": {}, "type": "main"} (contract-verified 200) and '
        '{"branchRid": <rid>, "type": "branchRid"} (generated '
        "@palantir/branch-service-api proposalMergeTo.js; encoding "
        "accepted by the server, semantic target validity enforced "
        "server-side with Branch:InvalidMergeTo). Success response "
        "proposal.proposalRid is ri.branch..proposal.<uuid>."
    )
    CLOSE_CONTRACT = (
        "contract-verified: PUT /branch/proposal/close/{proposalRid}, "
        "empty body, 200 {} (contract-verified against a live deployment)."
    )

    def get_proposal(self, proposal_rid: str) -> Dict[str, Any]:
        """
        Load one Ontology Global Proposal by RID.

        Read-only against branch-service
        ``PUT /branch/proposal/load/{proposalRid}`` (empty-body load; contract
        contract-verified — there is no list endpoint, load-by-RID only).

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

    @staticmethod
    def build_merge_to(merge_to: str) -> Dict[str, Any]:
        """
        Encode the ``ProposalMergeTo`` Conjure union for a merge target.

        The generated ``@palantir/branch-service-api`` union has exactly two
        arms: ``main`` (empty payload) and ``branchRid`` (a global branch
        RID). Anything else fails loudly before any network request.

        Args:
            merge_to: ``"main"`` or a ``ri.branch..branch.<uuid>`` RID

        Returns:
            The union encoding, e.g. ``{"main": {}, "type": "main"}``

        Raises:
            ValueError: If the target is neither ``main`` nor a branch RID
        """
        if merge_to == "main":
            # Fresh dict each call: callers must not mutate MERGE_TO_MAIN.
            return {"main": {}, "type": "main"}
        if merge_to.startswith(GlobalBranchService.BRANCH_RID_PREFIX):
            return {"branchRid": merge_to, "type": "branchRid"}
        raise ValueError(
            f"Invalid merge target {merge_to!r}: expected 'main' or a "
            f"global branch RID ({GlobalBranchService.BRANCH_RID_PREFIX}<uuid>)"
        )

    def plan_create_proposal(
        self,
        branch_rid: str,
        display_name: str,
        description: str,
        merge_to: str = "main",
    ) -> Dict[str, Any]:
        """
        Describe a Global Proposal create without issuing it.

        Shows the verified request body, including the ``mergeTo``
        ``ProposalMergeTo`` Conjure union encoding.

        Args:
            branch_rid: Global Branch RID the proposal belongs to
            display_name: Proposal display name
            description: Proposal description
            merge_to: Merge target: ``"main"`` or a global branch RID

        Returns:
            Plan dictionary with the would-be request and contract status

        Raises:
            ValueError: If ``merge_to`` is not a valid union target
        """
        return self._plan(
            "POST",
            "branch-service/api/branch/proposal/create",
            {
                "branchRid": branch_rid,
                "displayName": display_name,
                "description": description,
                "mergeTo": self.build_merge_to(merge_to),
            },
            self.CREATE_CONTRACT,
        )

    def create_proposal(
        self,
        branch_rid: str,
        display_name: str,
        description: str,
        merge_to: str = "main",
    ) -> Dict[str, Any]:
        """
        Create an Ontology Global Proposal (REAL mutation).

        Issues the verified ``POST /branch/proposal/create`` body with the
        ``mergeTo`` ``ProposalMergeTo`` Conjure union encoding. Returns the
        proposal record plus the parsed proposal RID
        (``ri.branch..proposal.<uuid>`` — double dot).

        Args:
            branch_rid: Global Branch RID the proposal belongs to
            display_name: Proposal display name
            description: Proposal description
            merge_to: Merge target: ``"main"`` or a global branch RID

        Returns:
            Dictionary with ``proposalRid`` and the raw ``proposal`` record

        Raises:
            ValueError: If ``merge_to`` is not a valid union target
            GlobalBranchShapeError: If the response misses the expected fields
            RuntimeError: If the request fails or the API is not mounted
        """
        payload = self._post(
            "branch-service/api/branch/proposal/create",
            {
                "branchRid": branch_rid,
                "displayName": display_name,
                "description": description,
                "mergeTo": self.build_merge_to(merge_to),
            },
            "proposal",
        )
        proposal_rid = self._extract_rid(
            payload, "proposal", "proposalRid", self.PROPOSAL_RID_PREFIX
        )
        return {"proposalRid": proposal_rid, "proposal": payload["proposal"]}

    def close_proposal(self, proposal_rid: str) -> Dict[str, Any]:
        """
        Close one Ontology Global Proposal (DESTRUCTIVE).

        Contract-verified empty-body write against branch-service
        ``PUT /branch/proposal/close/{proposalRid}`` (200 {} contract-verified),
        passed through raw with strict shape-checking.

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
