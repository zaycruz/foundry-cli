"""
Compute Modules service wrapper.

Backed by the internal gateways the Palantir MCP compute-module tools use,
per the  published client contract against a live deployment. The MCP does NOT call the
module-group service at its own mount (``/module-group/api/...`` is
``Route:RouteNotMounted`` on every stack verified); everything goes
through gateways that ARE mounted:

- ``contour-backend-multiplexer/api/...`` (DeployedAppsService and
  ModuleGroupMultiplexingService) for info, dev-mode, and function execution
- ``build2/api/...`` (BuildManagerService) for start/stop
- ``foundry-telemetry-service/api/...`` (TelemetryInfoService +
  LogsQueryService) for logs

Route mounts are contract-verified: every endpoint answered a real 403
(``Contour:InsufficientPermission``) or 400 (``Build2:...``) instead of
``Route:RouteNotMounted`` when verified with an inert RID. The verification token lacks
``deployed-apps:view/edit/submit``, so no success payload has ever been
observed for the contour-backend-multiplexer or build2 endpoints; those
success shapes are UNVERIFIED and passed through raw with strict
shape-checking.

The ``logs/read/v3`` request/response shape is bundle-derived (step 1 of the
logs flow was captured live returning 200; step 2 was never reached with an
inert RID), so it is marked ``shape_verified: false`` honestly at the command
layer.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional

from .base import BaseService
from .foundry_internal_client import FoundryInternalClient

DEFAULT_BRANCH = "master"
DEFAULT_PAGE_SIZE_LIMIT = 100
MAX_PAGE_SIZE_LIMIT = 1000
DEFAULT_LOG_WINDOW_MICROS = 24 * 60 * 60 * 1_000_000


class ComputeModulesError(RuntimeError):
    """Raised when a compute-module request fails or surprises the contract."""


class ComputeShapeError(ComputeModulesError):
    """Raised when an unverified success response is not a loadable object."""


class ComputeSessionNotFoundError(ComputeModulesError):
    """Raised when telemetry has no session for a build job RID."""


class ComputeService(BaseService):
    """Service wrapper for Compute Module operations."""

    STATUS_CONTRACT = (
        "route contract-verified against a live deployment (403 "
        "Contour:InsufficientPermission, not RouteNotMounted); success shape "
        "UNVERIFIED, passed through raw"
    )
    CONFIG_CONTRACT = STATUS_CONTRACT
    LOGS_CONTRACT = (
        "step 1 (sessions/by-run-rids/get-batch) contract-verified on "
        "a live Foundry deployment (200); step 2 (logs/read/v3, microsecond timestamps) is "
        "bundle-derived and NOT contract-verified"
    )
    START_CONTRACT = (
        "route contract-verified against a live deployment: POST "
        "/build2/api/manager/submitBuild with the deployed-app RID passed as "
        "a datasets jobSpecSelection (isRequired: true) fails 400 "
        "Build2:JobSpecsForDatasetsNotFoundInGraph for an inert RID; success "
        "shape {buildRid, buildGroupRid, jobsCreated} UNVERIFIED"
    )
    STOP_CONTRACT = (
        "route contract-verified against a live deployment: DELETE "
        "/build2/api/manager/builds/{buildRid} fails 400 "
        "Build2:BuildNotFound for an inert RID; success shape UNVERIFIED"
    )
    DEV_MODE_CONTRACT = (
        "route contract-verified against a live deployment: PUT "
        "/contour-backend-multiplexer/api/deployed-apps/{rid}/{branch}/"
        "dev-mode fails 403 Contour:InsufficientPermission "
        "(deployed-apps:edit); body {automaticUpgradesUntil: ISO-8601, max "
        "+5h}, omit the field to disable; success shape UNVERIFIED"
    )
    EXECUTE_CONTRACT = (
        "route contract-verified against a live deployment: POST "
        "/contour-backend-multiplexer/api/module-group-multiplexer/"
        "compute-modules/jobs/execute fails 403 "
        "Contour:InsufficientPermission (deployed-apps:submit); response is "
        "a raw octet-stream (the function return value), success shape "
        "UNVERIFIED"
    )

    def _get_service(self) -> Any:
        """Get the Foundry client (compute modules use internal APIs)."""
        return self.client

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

    def _checked(
        self,
        verb: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        operation: str,
    ) -> tuple[Any, str]:
        """Issue one internal request, failing loud on mount and HTTP errors."""
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(verb, path, json_body=json_body)
        except Exception as e:
            raise ComputeModulesError(f"Failed to {operation}: {e}") from e

        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name == "Route:RouteNotMounted":
            raise ComputeModulesError(
                f"The API backing {operation} is not mounted on this stack "
                f"(Route:RouteNotMounted for /{path})"
            )
        if not 200 <= status < 300:
            detail = f" ({error_name})" if error_name else ""
            raise ComputeModulesError(
                f"{operation} failed with HTTP {status}{detail}: {str(raw)[:200]}"
            )
        return payload, raw

    @staticmethod
    def _require_object(payload: Any, raw: str, operation: str) -> Dict[str, Any]:
        """Pass a success payload through raw, requiring a non-empty object."""
        if not isinstance(payload, Mapping) or not payload:
            raise ComputeShapeError(
                f"Unverified compute-module {operation} response shape: "
                f"expected a non-empty JSON object, got {str(raw)[:200]!r}. "
                "Refusing to guess at the contract."
            )
        return dict(payload)

    @staticmethod
    def _status_path(deployed_app_rid: str, branch: str) -> str:
        return (
            "contour-backend-multiplexer/api/deployed-apps/"
            f"{deployed_app_rid}/{branch}/status"
        )

    @staticmethod
    def _config_path(deployed_app_rid: str) -> str:
        return f"contour-backend-multiplexer/api/deployed-apps/{deployed_app_rid}/v2"

    @staticmethod
    def _dev_mode_path(deployed_app_rid: str, branch: str) -> str:
        return (
            "contour-backend-multiplexer/api/deployed-apps/"
            f"{deployed_app_rid}/{branch}/dev-mode"
        )

    @staticmethod
    def _start_body(deployed_app_rid: str, branch: str) -> Dict[str, Any]:
        """The captured submitBuild body: deployed-app RID as a datasets job spec."""
        return {
            "branch": branch,
            "branchFallbacks": {"branches": []},
            "buildParameters": {},
            "jobSpecSelections": [
                {
                    "type": "datasets",
                    "datasets": {
                        "datasetRids": [deployed_app_rid],
                        "isRequired": True,
                    },
                }
            ],
            "inputFailureStrategies": [],
            "inputSpecOverrides": [],
            "forceBuild": False,
        }

    @staticmethod
    def _dev_mode_body(automatic_upgrades_until: Optional[str]) -> Dict[str, Any]:
        """Dev-mode body: omitting the field (empty body) disables dev mode."""
        if automatic_upgrades_until is None:
            return {}
        return {"automaticUpgradesUntil": automatic_upgrades_until}

    @staticmethod
    def _execute_body(
        deployed_app_rid: str,
        branch: str,
        query_type: str,
        query: Optional[Any],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "deployedAppRid": deployed_app_rid,
            "deployedAppBranch": branch,
            "queryType": query_type,
        }
        if query is not None:
            body["query"] = query
        return body

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_status(self, deployed_app_rid: str, branch: str) -> Dict[str, Any]:
        """
        Load the deployed-app status (read-only).

        Internal ``GET /contour-backend-multiplexer/api/deployed-apps/
        {deployedAppRid}/{branch}/status``; route contract-verified,
        success shape UNVERIFIED and passed through raw.

        Args:
            deployed_app_rid: Deployed app Resource Identifier
            branch: Deployed app branch

        Returns:
            Raw status dictionary

        Raises:
            ComputeShapeError: If the response is not a non-empty JSON object
            ComputeModulesError: If the read fails or the API is not mounted
        """
        payload, raw = self._checked(
            "GET",
            self._status_path(deployed_app_rid, branch),
            operation=f"status load for deployed app {deployed_app_rid}",
        )
        return self._require_object(payload, raw, "status")

    def get_config(self, deployed_app_rid: str) -> Dict[str, Any]:
        """
        Load the deployed-app config (read-only).

        Internal ``GET /contour-backend-multiplexer/api/deployed-apps/
        {deployedAppRid}/v2``; route contract-verified, success shape
        UNVERIFIED and passed through raw.

        Args:
            deployed_app_rid: Deployed app Resource Identifier

        Returns:
            Raw config dictionary

        Raises:
            ComputeShapeError: If the response is not a non-empty JSON object
            ComputeModulesError: If the read fails or the API is not mounted
        """
        payload, raw = self._checked(
            "GET",
            self._config_path(deployed_app_rid),
            operation=f"config load for deployed app {deployed_app_rid}",
        )
        return self._require_object(payload, raw, "config")

    def get_logs(
        self,
        build_job_rid: str,
        *,
        from_inclusive: Optional[int] = None,
        to_exclusive: Optional[int] = None,
        page_size_limit: int = DEFAULT_PAGE_SIZE_LIMIT,
        chronological: bool = True,
    ) -> Dict[str, Any]:
        """
        Read compute-module logs for one build job RID (read-only).

        Two-step telemetry flow (per the  capture):

        1. ``POST /foundry-telemetry-service/api/info/sessions/
           by-run-rids/get-batch`` with ``{"runRids": [buildJobRid]}`` to
           resolve the container RID and session ID (contract-verified, 200).
        2. ``POST /foundry-telemetry-service/api/containers/{containerRid}/
           sessions/{sessionId}/logs/read/v3`` with microsecond-since-epoch
           timestamps (bundle-derived, NOT contract-verified).

        With no time range given, defaults to the last 24 hours.

        Args:
            build_job_rid: Build job (run) Resource Identifier
            from_inclusive: Range start, microseconds since epoch
            to_exclusive: Range end, microseconds since epoch
            page_size_limit: Max log entries (server maximum 1000)
            chronological: Oldest-first when True, newest-first when False

        Returns:
            Dictionary with the resolved session, the issued request body,
            and the raw logs response

        Raises:
            ComputeSessionNotFoundError: If telemetry has no session for the RID
            ComputeModulesError: If either step fails or the API is not mounted
        """
        if not 1 <= page_size_limit <= MAX_PAGE_SIZE_LIMIT:
            raise ComputeModulesError(
                f"page_size_limit must be between 1 and {MAX_PAGE_SIZE_LIMIT}, "
                f"got {page_size_limit}"
            )

        resolved_to = (
            to_exclusive if to_exclusive is not None else int(time.time() * 1_000_000)
        )
        resolved_from = (
            from_inclusive
            if from_inclusive is not None
            else resolved_to - DEFAULT_LOG_WINDOW_MICROS
        )

        sessions_payload, sessions_raw = self._checked(
            "POST",
            "foundry-telemetry-service/api/info/sessions/by-run-rids/get-batch",
            json_body={"runRids": [build_job_rid]},
            operation=f"telemetry session resolution for run {build_job_rid}",
        )
        mapping = (
            sessions_payload.get("runRidsToContainerAndSessionIds")
            if isinstance(sessions_payload, Mapping)
            else None
        )
        if not isinstance(mapping, Mapping):
            raise ComputeShapeError(
                "Unverified telemetry session response shape: expected "
                "'runRidsToContainerAndSessionIds' object, got "
                f"{str(sessions_raw)[:200]!r}. Refusing to guess at the contract."
            )
        session = mapping.get(build_job_rid)
        if not isinstance(session, Mapping) or not session.get("containerRid"):
            raise ComputeSessionNotFoundError(
                f"No telemetry session found for build job RID {build_job_rid}"
            )
        container_rid = str(session["containerRid"])
        session_id = str(session.get("sessionId", ""))

        request_body = {
            "fromInclusive": resolved_from,
            "toExclusive": resolved_to,
            "pageSizeLimit": page_size_limit,
            "chronological": chronological,
        }
        logs_payload, _ = self._checked(
            "POST",
            "foundry-telemetry-service/api/containers/"
            f"{container_rid}/sessions/{session_id}/logs/read/v3",
            json_body=request_body,
            operation=f"logs read for run {build_job_rid}",
        )
        # logs/read/v3 response shape is bundle-derived and NOT contract-verified;
        # pass it through raw rather than projecting fields never observed.
        return {
            "session": {"containerRid": container_rid, "sessionId": session_id},
            "request": request_body,
            "response": logs_payload,
        }

    # ------------------------------------------------------------------
    # Plans (dry-run payloads; no network)
    # ------------------------------------------------------------------

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

    def plan_start(self, deployed_app_rid: str, branch: str) -> Dict[str, Any]:
        """Describe a compute-module start without issuing it."""
        return self._plan(
            "POST",
            "build2/api/manager/submitBuild",
            self._start_body(deployed_app_rid, branch),
            self.START_CONTRACT,
        )

    def plan_stop(self, build_rid: str) -> Dict[str, Any]:
        """Describe a compute-module stop without issuing it."""
        return self._plan(
            "DELETE",
            f"build2/api/manager/builds/{build_rid}",
            {},
            self.STOP_CONTRACT,
        )

    def plan_dev_mode(
        self,
        deployed_app_rid: str,
        branch: str,
        automatic_upgrades_until: Optional[str],
    ) -> Dict[str, Any]:
        """Describe a dev-mode configure without issuing it."""
        return self._plan(
            "PUT",
            self._dev_mode_path(deployed_app_rid, branch),
            self._dev_mode_body(automatic_upgrades_until),
            self.DEV_MODE_CONTRACT,
        )

    def plan_execute(
        self,
        deployed_app_rid: str,
        branch: str,
        query_type: str,
        query: Optional[Any],
    ) -> Dict[str, Any]:
        """Describe a function execution without issuing it."""
        return self._plan(
            "POST",
            "contour-backend-multiplexer/api/module-group-multiplexer/"
            "compute-modules/jobs/execute",
            self._execute_body(deployed_app_rid, branch, query_type, query),
            self.EXECUTE_CONTRACT,
        )

    # ------------------------------------------------------------------
    # Writes (only ever invoked behind --apply at the command layer)
    # ------------------------------------------------------------------

    def start(self, deployed_app_rid: str, branch: str) -> Dict[str, Any]:
        """
        Start a compute module by submitting a build (MUTATING).

        Internal ``POST /build2/api/manager/submitBuild`` with the
        deployed-app RID passed as a ``datasets`` jobSpecSelection
        (``isRequired: true``), exactly as the MCP client contract defines. Success
        shape (``{buildRid, buildGroupRid, jobsCreated}``) UNVERIFIED, passed
        through raw.
        """
        payload, raw = self._checked(
            "POST",
            "build2/api/manager/submitBuild",
            json_body=self._start_body(deployed_app_rid, branch),
            operation=f"start of deployed app {deployed_app_rid}",
        )
        return self._require_object(payload, raw, "start")

    def stop(self, build_rid: str) -> Dict[str, Any]:
        """
        Stop a compute module by cancelling the jobs in its build (MUTATING).

        Internal ``DELETE /build2/api/manager/builds/{buildRid}`` (no body).
        Success shape UNVERIFIED; an empty 2xx body maps to an explicit
        acknowledgment, a non-object body fails loudly.
        """
        payload, raw = self._checked(
            "DELETE",
            f"build2/api/manager/builds/{build_rid}",
            operation=f"stop of build {build_rid}",
        )
        if payload is None or payload == "" or payload == {}:
            return {"buildRid": build_rid, "acknowledged": True, "response_empty": True}
        if not isinstance(payload, Mapping):
            raise ComputeShapeError(
                "Unverified compute-module stop response shape: expected a "
                f"JSON object or an empty body, got {str(raw)[:200]!r}. "
                "Refusing to guess at the contract."
            )
        return dict(payload)

    def configure_dev_mode(
        self,
        deployed_app_rid: str,
        branch: str,
        automatic_upgrades_until: Optional[str],
    ) -> Dict[str, Any]:
        """
        Configure dev mode on a deployed app (MUTATING).

        Internal ``PUT /contour-backend-multiplexer/api/deployed-apps/
        {deployedAppRid}/{branch}/dev-mode`` with
        ``{"automaticUpgradesUntil": "<ISO-8601>"}`` (max +5h), or an empty
        body to disable dev mode. Success shape UNVERIFIED; an empty 2xx body
        maps to an explicit acknowledgment.
        """
        payload, raw = self._checked(
            "PUT",
            self._dev_mode_path(deployed_app_rid, branch),
            json_body=self._dev_mode_body(automatic_upgrades_until),
            operation=f"dev-mode configure for deployed app {deployed_app_rid}",
        )
        if payload is None or payload == "" or payload == {}:
            return {
                "deployedAppRid": deployed_app_rid,
                "acknowledged": True,
                "response_empty": True,
            }
        if not isinstance(payload, Mapping):
            raise ComputeShapeError(
                "Unverified compute-module dev-mode response shape: expected "
                f"a JSON object or an empty body, got {str(raw)[:200]!r}. "
                "Refusing to guess at the contract."
            )
        return dict(payload)

    def execute(
        self,
        deployed_app_rid: str,
        branch: str,
        query_type: str,
        query: Optional[Any],
    ) -> Dict[str, Any]:
        """
        Execute a function on a running FUNCTION-mode compute module.

        Internal ``POST /contour-backend-multiplexer/api/
        module-group-multiplexer/compute-modules/jobs/execute``; the response
        is a raw octet-stream carrying the function's return value (expected
        JSON). The success shape is UNVERIFIED: a JSON-parsable body is
        returned under ``result``, anything else under ``resultText``.
        """
        payload, _ = self._checked(
            "POST",
            "contour-backend-multiplexer/api/module-group-multiplexer/"
            "compute-modules/jobs/execute",
            json_body=self._execute_body(deployed_app_rid, branch, query_type, query),
            operation=(
                f"function execute ({query_type}) on deployed app {deployed_app_rid}"
            ),
        )
        if isinstance(payload, str):
            return {"resultText": payload}
        return {"result": payload}
