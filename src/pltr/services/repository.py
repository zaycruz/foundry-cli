"""
Code repository service wrapper.

Read-only pull-request access backed by the internal ``stemma-pull-request``
API, which the 2026-07-22 gap analysis catalogues (29 endpoints) and which was
contract-verified on a live Foundry deployment:

- ``GET /stemma-pull-request/api/pulls`` returns ``{"values": [...]}``. The
  gap analysis noted a live PR read was UNVERIFIED without a repository
  argument; validation showed a ``repositoryRid`` query parameter is silently
  ignored (PRs from other repositories are still returned), so repository
  filtering is done client-side and documented as such.
- ``GET /stemma-pull-request/api/pulls/{pullRequestRid}`` returns one pull
  request object.

Responses are passed through raw (never fabricated); unexpected shapes fail
loudly instead of rendering as a result.
"""

from typing import Any, Dict, List, Mapping, Optional

from .base import BaseService
from .foundry_internal_client import FoundryInternalClient


class PullRequestNotFoundError(RuntimeError):
    """Raised when the pull-request service has no PR for a RID."""


class PullRequestShapeError(RuntimeError):
    """Raised when a pull-request response does not match the verified shape."""


class RepositoryService(BaseService):
    """Service wrapper for read-only code repository operations."""

    # Listing every pull request on a busy stack took ~60s in verification;
    # the default 30s timeout is not enough for this endpoint.
    PULL_REQUEST_LIST_TIMEOUT = 120.0

    def _get_service(self) -> Any:
        """Get the Foundry client (pull requests use the internal API)."""
        return self.client

    def list_pull_requests(
        self, repository_rid: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List pull requests, optionally filtered to one repository.

        Read-only against GET /stemma-pull-request/api/pulls. The server does
        not honor a repository query parameter (verified: it is
        silently ignored), so when ``repository_rid`` is given the filtering
        happens client-side on the verified ``baseRepositoryRid`` /
        ``headRepositoryRid`` fields.

        Args:
            repository_rid: Optional repository RID to filter by (client-side)

        Returns:
            List of raw pull request dictionaries

        Raises:
            PullRequestShapeError: If the response shape is not the verified
                ``{"values": [...]}`` envelope
            RuntimeError: If the read fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET",
                "stemma-pull-request/api/pulls",
                request_timeout=self.PULL_REQUEST_LIST_TIMEOUT,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to list pull requests: {e}") from e

        self._raise_for_status(status, payload, raw, "pull-request list")

        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("values"), list
        ):
            raise PullRequestShapeError(
                "Unverified pull-request list response shape: expected an "
                'object with a "values" array, got '
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )

        pull_requests = payload["values"]
        for entry in pull_requests:
            if not isinstance(entry, Mapping) or not isinstance(
                entry.get("rid"), str
            ):
                raise PullRequestShapeError(
                    "Unverified pull-request entry shape: expected an object "
                    f'with a string "rid", got {str(entry)[:200]!r}. '
                    "Refusing to guess at the contract."
                )

        if repository_rid is None:
            return [dict(entry) for entry in pull_requests]
        return [
            dict(entry)
            for entry in pull_requests
            if entry.get("baseRepositoryRid") == repository_rid
            or entry.get("headRepositoryRid") == repository_rid
        ]

    def get_pull_request(self, pull_request_rid: str) -> Dict[str, Any]:
        """
        Get one pull request by RID.

        Read-only against GET /stemma-pull-request/api/pulls/{pullRequestRid}
        (shape contract-verified on a live Foundry deployment).

        Args:
            pull_request_rid: Pull request Resource Identifier

        Returns:
            Raw pull request dictionary

        Raises:
            PullRequestNotFoundError: If no pull request exists for the RID
            PullRequestShapeError: If the response shape is not the verified
                pull request object
            RuntimeError: If the read fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma-pull-request/api/pulls/{pull_request_rid}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to read pull request {pull_request_rid}: {e}"
            ) from e

        if status == 404:
            raise PullRequestNotFoundError(
                f"No pull request found for RID {pull_request_rid}"
            )
        self._raise_for_status(status, payload, raw, "pull-request get")

        if not isinstance(payload, Mapping) or not payload:
            raise PullRequestNotFoundError(
                f"No pull request found for RID {pull_request_rid}"
            )
        if not isinstance(payload.get("rid"), str):
            raise PullRequestShapeError(
                "Unverified pull-request response shape: expected an object "
                f'with a string "rid", got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        return dict(payload)

    @staticmethod
    def _raise_for_status(
        status: int, payload: Any, raw: Any, operation: str
    ) -> None:
        """Fail loudly on non-2xx internal API responses."""
        if 200 <= status < 300:
            return
        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name == "Route:RouteNotMounted":
            raise RuntimeError(
                "The stemma-pull-request API is not mounted on this stack "
                f"(Route:RouteNotMounted during {operation})"
            )
        detail = f" ({error_name})" if error_name else ""
        raise RuntimeError(
            f"Pull-request {operation} failed with HTTP {status}{detail}: "
            f"{str(raw)[:200]}"
        )

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
