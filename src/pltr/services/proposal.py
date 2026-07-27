"""Typed proposal lifecycle service over the verified internal APIs.

The pinned ``foundry-platform-sdk`` client has no namespace for either
proposal system, but both are reachable through the internal APIs already
wrapped by sibling services:

- ``code-pr`` delegates to :class:`~pltr.services.repository.RepositoryService`
  (internal ``stemma-pull-request`` API): list, get, create, comment, close.
- ``global-proposal`` delegates to
  :class:`~pltr.services.global_branching.GlobalProposalService` (internal
  ``branch-service`` API): get, create, close. There is no list endpoint;
  load-by-RID only.

Actions with no contract-verified sibling implementation stay fail-closed
with :class:`UnsupportedProposalCapabilityError` (exit 6); no raw endpoint
fallback is invented for them.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from .base import BaseService
from .global_branching import GlobalProposalService
from .repository import RepositoryService


class ProposalType(str, Enum):
    """Proposal systems supported by the unified command contract."""

    CODE_PR = "code-pr"
    GLOBAL_PROPOSAL = "global-proposal"


class ProposalAction(str, Enum):
    """Lifecycle actions exposed by the proposal command group."""

    CREATE = "create"
    LIST = "list"
    GET = "get"
    COMMENT = "comment"
    APPROVE = "approve"
    REQUEST_CHANGES = "request-changes"
    MERGE = "merge"
    ACCEPT = "accept"
    CLOSE = "close"


class ProposalError(Exception):
    """Base error with a stable category and CLI exit code."""

    category = "remote-service"
    exit_code = 7

    def to_payload(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "category": self.category,
                "message": str(self),
            },
        }


class ProposalAuthenticationError(ProposalError):
    category = "authentication"
    exit_code = 2


class ProposalAuthorizationError(ProposalError):
    category = "authorization"
    exit_code = 3


class ProposalValidationError(ProposalError):
    category = "validation"
    exit_code = 4


class ProposalConflictError(ProposalError):
    category = "conflict"
    exit_code = 5


#: Why each still-unsupported (type, action) pair stays fail-closed.
UNSUPPORTED_CAPABILITY_REASONS: Dict[tuple, str] = {
    (ProposalType.CODE_PR, ProposalAction.APPROVE): (
        "the internal stemma-pull-request API wrapped by RepositoryService "
        "has no contract-verified approve operation"
    ),
    (ProposalType.CODE_PR, ProposalAction.REQUEST_CHANGES): (
        "the internal stemma-pull-request API wrapped by RepositoryService "
        "has no contract-verified request-changes operation"
    ),
    (ProposalType.CODE_PR, ProposalAction.MERGE): (
        "the internal stemma-pull-request API wrapped by RepositoryService "
        "has no contract-verified merge operation"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.LIST): (
        "the internal branch-service API has no proposal list endpoint "
        "(load-by-RID only)"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.COMMENT): (
        "the internal branch-service API wrapped by GlobalProposalService "
        "has no contract-verified comment operation"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.APPROVE): (
        "the internal branch-service API wrapped by GlobalProposalService "
        "has no contract-verified approve operation"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.REQUEST_CHANGES): (
        "the internal branch-service API wrapped by GlobalProposalService "
        "has no contract-verified request-changes operation"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.MERGE): (
        "the internal branch-service API wrapped by GlobalProposalService "
        "has no contract-verified merge operation"
    ),
    (ProposalType.GLOBAL_PROPOSAL, ProposalAction.ACCEPT): (
        "the internal branch-service API wrapped by GlobalProposalService "
        "has no contract-verified accept operation"
    ),
}

_UNSUPPORTED_FALLBACK_REASON = (
    "no contract-verified implementation exists in RepositoryService or "
    "GlobalProposalService"
)


class UnsupportedProposalCapabilityError(ProposalError):
    category = "unsupported-capability"
    exit_code = 6

    def __init__(self, proposal_type: ProposalType, action: ProposalAction):
        reason = UNSUPPORTED_CAPABILITY_REASONS.get(
            (proposal_type, action), _UNSUPPORTED_FALLBACK_REASON
        )
        super().__init__(
            f"{action.value} is unavailable for {proposal_type.value}: "
            f"{reason}; no raw endpoint fallback is permitted"
        )
        self.proposal_type = proposal_type
        self.action = action

    def to_payload(self) -> Dict[str, Any]:
        payload = super().to_payload()
        payload["error"].update(
            {
                "proposal_type": self.proposal_type.value,
                "action": self.action.value,
            }
        )
        return payload


class ProposalRemoteServiceError(ProposalError):
    category = "remote-service"
    exit_code = 7


# Verified through the authenticated MCP catalog supplied with the approved
# plan. These operations are provider capabilities, not SDK reachability.
MCP_VERIFIED_CAPABILITIES = frozenset(
    {
        (ProposalType.CODE_PR, ProposalAction.CREATE),
        (ProposalType.CODE_PR, ProposalAction.LIST),
        (ProposalType.CODE_PR, ProposalAction.GET),
        (ProposalType.CODE_PR, ProposalAction.COMMENT),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CREATE),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.GET),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CLOSE),
    }
)

# Reachable through the sibling services wrapping the internal
# stemma-pull-request and branch-service APIs (see the module docstring).
SDK_REACHABLE_CAPABILITIES: frozenset[tuple[ProposalType, ProposalAction]] = frozenset(
    {
        (ProposalType.CODE_PR, ProposalAction.CREATE),
        (ProposalType.CODE_PR, ProposalAction.LIST),
        (ProposalType.CODE_PR, ProposalAction.GET),
        (ProposalType.CODE_PR, ProposalAction.COMMENT),
        (ProposalType.CODE_PR, ProposalAction.CLOSE),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CREATE),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.GET),
        (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CLOSE),
    }
)


def parse_proposal_type(value: str) -> ProposalType:
    """Parse an explicit proposal type without letting Typer infer it."""

    try:
        return ProposalType(value)
    except ValueError as exc:
        choices = ", ".join(item.value for item in ProposalType)
        raise ProposalValidationError(
            f"Unknown proposal type '{value}'. Choose one of: {choices}"
        ) from exc


def normalize_proposal_error(error: Exception) -> ProposalError:
    """Map authentication and provider failures into stable categories."""

    if isinstance(error, ProposalError):
        return error
    if isinstance(error, (ProfileNotFoundError, MissingCredentialsError)):
        return ProposalAuthenticationError(str(error))

    error_name = type(error).__name__
    if error_name in {"NotAuthenticated", "UnauthorizedError"}:
        return ProposalAuthenticationError(str(error))
    if "PermissionDenied" in error_name or error_name == "ForbiddenError":
        return ProposalAuthorizationError(str(error))
    if error_name in {
        "ValidationError",
        "BadRequestError",
        "UnprocessableEntityError",
    }:
        return ProposalValidationError(str(error))
    if "Conflict" in error_name:
        return ProposalConflictError(str(error))
    return ProposalRemoteServiceError(str(error))


class ProposalService(BaseService):
    """Capability-gated proposal service delegating to sibling services."""

    def __init__(self, profile: Optional[str] = None):
        super().__init__(profile=profile)
        self._repository_service: Optional[RepositoryService] = None
        self._global_proposal_service: Optional[GlobalProposalService] = None

    def _get_service(self) -> Any:
        """Return the root client only after a capability has been verified."""

        return self.client

    def _repository(self) -> RepositoryService:
        """Lazily build the code-PR delegate for the same profile."""

        if self._repository_service is None:
            self._repository_service = RepositoryService(profile=self.profile)
        return self._repository_service

    def _global_proposals(self) -> GlobalProposalService:
        """Lazily build the global-proposal delegate for the same profile."""

        if self._global_proposal_service is None:
            self._global_proposal_service = GlobalProposalService(
                profile=self.profile
            )
        return self._global_proposal_service

    @staticmethod
    def _unsupported(
        proposal_type: ProposalType, action: ProposalAction
    ) -> UnsupportedProposalCapabilityError:
        return UnsupportedProposalCapabilityError(proposal_type, action)

    def _require_reachable(
        self, proposal_type: ProposalType, action: ProposalAction
    ) -> None:
        if (proposal_type, action) not in SDK_REACHABLE_CAPABILITIES:
            raise self._unsupported(proposal_type, action)

    def require_capability(
        self, proposal_type: ProposalType, action: ProposalAction
    ) -> None:
        """Fail before reads, prompts, or writes when an action is unreachable."""

        self._require_reachable(proposal_type, action)

    def _create_kwargs(
        self,
        proposal_type: ProposalType,
        *,
        parent_rid: str,
        title: str,
        source_ref: str,
        target_ref: Optional[str],
        description: Optional[str],
    ) -> Dict[str, Any]:
        """Map the unified create arguments onto the sibling call.

        code-pr: ``parent_rid`` is the base repository RID, ``source_ref``
        the head commitish, ``target_ref`` the base branch (default
        ``refs/heads/master``).

        global-proposal: ``source_ref`` is the Global Branch RID the
        proposal belongs to, ``target_ref`` the merge target (``main`` or a
        Global Branch RID; default ``main``). ``parent_rid`` is not used by
        ``GlobalProposalService.create_proposal`` — the branch RID carries
        the target — and is accepted only for CLI symmetry.
        """

        if proposal_type is ProposalType.CODE_PR:
            return {
                "title": title,
                "base_repository_rid": parent_rid,
                "head_commitish": source_ref,
                "base_branch_name": target_ref or "refs/heads/master",
                "description": description,
            }
        return {
            "branch_rid": source_ref,
            "display_name": title,
            "description": description or "",
            "merge_to": target_ref or "main",
        }

    def create_plan(
        self,
        proposal_type: ProposalType,
        *,
        parent_rid: str,
        title: str,
        source_ref: str,
        target_ref: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dry-run plan for ``create`` (no network write is issued)."""

        self._require_reachable(proposal_type, ProposalAction.CREATE)
        kwargs = self._create_kwargs(
            proposal_type,
            parent_rid=parent_rid,
            title=title,
            source_ref=source_ref,
            target_ref=target_ref,
            description=description,
        )
        if proposal_type is ProposalType.CODE_PR:
            return self._repository().create_pull_request_plan(**kwargs)
        return self._global_proposals().plan_create_proposal(**kwargs)

    def create(
        self,
        proposal_type: ProposalType,
        *,
        parent_rid: str,
        title: str,
        source_ref: str,
        target_ref: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a proposal (REAL mutation; see ``create_plan``)."""

        self._require_reachable(proposal_type, ProposalAction.CREATE)
        kwargs = self._create_kwargs(
            proposal_type,
            parent_rid=parent_rid,
            title=title,
            source_ref=source_ref,
            target_ref=target_ref,
            description=description,
        )
        if proposal_type is ProposalType.CODE_PR:
            return self._repository().create_pull_request(**kwargs)
        return self._global_proposals().create_proposal(**kwargs)

    def list(
        self, proposal_type: ProposalType, *, parent_rid: str
    ) -> List[Dict[str, Any]]:
        """List proposals (code-pr only; client-side repository filter)."""

        self._require_reachable(proposal_type, ProposalAction.LIST)
        return self._repository().list_pull_requests(parent_rid)

    def get(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load one proposal by RID (``parent_rid`` is not needed)."""

        self._require_reachable(proposal_type, ProposalAction.GET)
        if proposal_type is ProposalType.CODE_PR:
            return self._repository().get_pull_request(proposal_id)
        return self._global_proposals().get_proposal(proposal_id)

    def comment_plan(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        message: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dry-run plan for ``comment`` (code-pr only)."""

        self._require_reachable(proposal_type, ProposalAction.COMMENT)
        return self._repository().create_pull_request_comment_plan(
            proposal_id, message
        )

    def comment(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        message: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Comment on a proposal (REAL mutation; code-pr only)."""

        self._require_reachable(proposal_type, ProposalAction.COMMENT)
        return self._repository().create_pull_request_comment(proposal_id, message)

    def approve(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_reachable(proposal_type, ProposalAction.APPROVE)
        raise self._unsupported(proposal_type, ProposalAction.APPROVE)

    def request_changes(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_reachable(proposal_type, ProposalAction.REQUEST_CHANGES)
        raise self._unsupported(proposal_type, ProposalAction.REQUEST_CHANGES)

    def merge(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_reachable(proposal_type, ProposalAction.MERGE)
        raise self._unsupported(proposal_type, ProposalAction.MERGE)

    def accept(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_reachable(proposal_type, ProposalAction.ACCEPT)
        raise self._unsupported(proposal_type, ProposalAction.ACCEPT)

    def close(
        self,
        proposal_type: ProposalType,
        proposal_id: str,
        *,
        parent_rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close a proposal (REAL mutation for both proposal systems)."""

        self._require_reachable(proposal_type, ProposalAction.CLOSE)
        if proposal_type is ProposalType.CODE_PR:
            return self._repository().close_pull_request(proposal_id)
        return self._global_proposals().close_proposal(proposal_id)
