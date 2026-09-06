"""Developer Console OSDK reads and SDK package installation.

Backed by the internal ``third-party-application-service`` application-sdks
endpoints, VERIFIED in
the internal capability analysis:

- ``GET /third-party-application-service/api/application-sdks/{applicationRid}``
- ``GET /third-party-application-service/api/application-sdks/{applicationRid}/latest``
- ``GET /third-party-application-service/api/application-sdks/{applicationRid}/{sdkVersion}``
- ``GET /third-party-application-service/api/application-sdks/{applicationRid}/repository``

SDK generation uses the contract-derived, contract-verified createSdkV2 contract
():
``POST /third-party-application-service/api/application-sdks/v2/{applicationRid}``
with exactly ``{"applicationVersion": <int>, "npm": {}}``, after reading
``metadata.applicationVersion`` from the getApplication endpoint.

The exact SDK definition payload shape is not contract-pinned anywhere in the
repo, so the service validates only the fields it actually relies on and fails
loudly (``SdkDefinitionDriftError``) when those drift, instead of silently
rendering a degraded result.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import quote

from ..auth.base import ProfileNotFoundError
from ..auth.manager import AuthManager
from ..auth.storage import CredentialStorage
from .foundry_internal_client import FoundryInternalClient

APPLICATION_SDKS_BASE = "/third-party-application-service/api/application-sdks"
APPLICATIONS_BASE = "/third-party-application-service/api/applications"

# SDK generation contract, derived from the vendor MCP 0.408.0 client contract and verified
# end-to-end against a live deployment:
# POST /application-sdks/v2/{applicationRid} with exactly
# {"applicationVersion": <int>, "npm": {}} mints a new SDK version from that
# app version (verified: 0.8.0 minted from applicationVersion 6). Unknown
# top-level keys are rejected with 422 Conjure:UnprocessableEntity, so the
# allowed field set is exactly {applicationVersion, npm}. Generation is async
# server-side; npm.status.type flips requested -> success (~24s observed).
SDK_GENERATE_CONTRACT = (
    "contract-verified against a live deployment: "
    "POST "
    "/third-party-application-service/api/application-sdks/v2/{applicationRid} "
    'with exactly {"applicationVersion": <int>, "npm": {}}; unknown top-level '
    "keys -> 422 Conjure:UnprocessableEntity. The MCP's scope-patch PUT is "
    "not needed for a pure regenerate from the current app version."
)
SDK_GENERATE_TIMEOUT_REASON = (
    "sdk-generation-timeout: npm.status.type stayed non-terminal past the "
    "polling deadline; the SDK version was minted server-side but generation "
    "did not finish in time."
)
# Observed live: npm.status.type walks requested -> inProgress ->
# success; the /latest?sdkStatus=REQUESTED confirmation read 204s as soon as
# the record leaves "requested", so polling tracks listSdks instead.
_SDK_GENERATION_PENDING_STATUSES = frozenset({"requested", "inProgress"})

CONNECT_READ_ONLY_DIVERGENCE = (
    "headless read-only form: the vendor MCP connect_to_dev_console_app is an "
    "interactive workspace action; this command only resolves and validates "
    "the application's connection context and establishes no session."
)

# Registry URL pattern for stack-hosted Artifacts repositories. Documented in
# the parity milestone scope; NOT verified end-to-end against a live stack, so
# every plan that emits these URLs carries a warning instead of pretending the
# install path is proven.
ARTIFACTS_RELEASE_PATH = "/artifacts/api/repositories/{repository_rid}/contents/release"

_ECOSYSTEM_ALIASES = {
    "npm": "npm",
    "typescript": "npm",
    "pypi": "pypi",
    "python": "pypi",
}

# Residual gap: the Artifacts registry URL pattern above is derived, not
# verified against a live stack, and SDK-definition package coordinates are
# extracted only from explicitly recognized shapes.
REGISTRY_UNVERIFIED_WARNING = (
    "Artifacts registry URLs follow the documented "
    "/artifacts/api/repositories/{repoRid}/contents/release/{npm|pypi} pattern "
    "but have not been verified end-to-end against a live stack."
)
COORDINATES_UNRESOLVED_REASON = (
    "package-coordinates-unresolved: the SDK definition did not contain a "
    "recognized package shape (a `packages` list with type/ecosystem npm|pypi, "
    "or npmPackage/pypiPackage entries); refusing to guess an install target."
)


class SdkDefinitionDriftError(RuntimeError):
    """The application-sdks response no longer matches the relied-upon shape."""


class DeveloperConsoleService:
    """Read OSDK definitions, generate SDK versions, and install packages."""

    def __init__(
        self,
        profile: Optional[str] = None,
        *,
        client: Optional[FoundryInternalClient] = None,
    ) -> None:
        if client is not None:
            self.client = client
            return
        effective_profile = profile or AuthManager().get_current_profile()
        if not effective_profile:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'foundry configure configure' to set up authentication."
            )
        self.client = FoundryInternalClient(effective_profile)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_sdks(self, application_rid: str) -> Any:
        """Return the raw listSdks payload (shape is not contract-pinned)."""

        return self._conjure_get(
            f"{APPLICATION_SDKS_BASE}/{application_rid}", "listSdks"
        )

    def get_sdk(
        self, application_rid: str, version: Optional[str] = None
    ) -> dict[str, Any]:
        """Return one SDK definition, latest unless ``version`` is given.

        Fails loud on drift: the payload must be a non-empty JSON object.
        """

        if version is None:
            path = f"{APPLICATION_SDKS_BASE}/{application_rid}/latest"
            operation = "getLatestSdk"
        else:
            path = f"{APPLICATION_SDKS_BASE}/{application_rid}/{version}"
            operation = "getSdk"
        payload = self._conjure_get(path, operation)
        if not isinstance(payload, Mapping) or not payload:
            raise SdkDefinitionDriftError(
                f"{operation} for {application_rid} returned a non-object or "
                f"empty payload; expected an SDK definition object, got: "
                f"{str(payload)[:200]}"
            )
        definition = dict(payload)
        return {
            "application_rid": application_rid,
            "version": self._extract_version(definition) or version,
            "definition": definition,
        }

    def get_sdk_repository_rid(self, application_rid: str) -> str:
        """Resolve the Artifacts repository RID hosting the app's SDKs."""

        payload = self._conjure_get(
            f"{APPLICATION_SDKS_BASE}/{application_rid}/repository",
            "getSdkRepositoryRid",
        )
        if not isinstance(payload, Mapping):
            raise SdkDefinitionDriftError(
                "getSdkRepositoryRid for "
                f"{application_rid} returned a non-object payload: "
                f"{str(payload)[:200]}"
            )
        for key in ("repositoryRid", "rid"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        raise SdkDefinitionDriftError(
            "getSdkRepositoryRid for "
            f"{application_rid} returned no repositoryRid/rid field; "
            f"payload keys: {sorted(str(key) for key in payload)}"
        )

    # ------------------------------------------------------------------
    # Connection context (read-only form of connect_to_dev_console_app)
    # ------------------------------------------------------------------

    def _get_application(self, application_rid: str) -> Mapping[str, Any]:
        """Fetch and shape-check the ``getApplication`` payload."""

        payload = self._conjure_get(
            f"{APPLICATIONS_BASE}/{application_rid}", "getApplication"
        )
        if not isinstance(payload, Mapping):
            raise SdkDefinitionDriftError(
                f"getApplication for {application_rid} returned a non-object "
                f"payload: {str(payload)[:200]}"
            )
        application = payload.get("application")
        if not isinstance(application, Mapping):
            raise SdkDefinitionDriftError(
                f"getApplication for {application_rid} returned no "
                f"'application' object; payload keys: "
                f"{sorted(str(key) for key in payload)}"
            )
        rid = application.get("rid")
        name = application.get("name")
        if not isinstance(rid, str) or not rid or not isinstance(name, str):
            raise SdkDefinitionDriftError(
                f"getApplication for {application_rid} returned an "
                "'application' object without string rid/name; keys: "
                f"{sorted(str(key) for key in application)}"
            )
        return application

    def get_connection_context(self, application_rid: str) -> dict[str, Any]:
        """Resolve and validate an app's dev-console connection context.

        READ-ONLY: uses the VERIFIED ``getApplication`` endpoint. Fails loud
        on drift: the payload must carry an ``application`` object with
        string ``rid``/``name``; everything else is extracted only when it
        matches the live-observed shape (verified against a live Foundry deployment).
        """

        application = self._get_application(application_rid)
        rid = application["rid"]
        name = application["name"]

        grants: dict[str, Any] = {}
        redirect_urls: list[str] = []
        client_type: Optional[str] = None
        client_spec = application.get("clientSpecification")
        if isinstance(client_spec, Mapping):
            spec_type = client_spec.get("type")
            if isinstance(spec_type, str) and spec_type:
                client_type = spec_type
                variant = client_spec.get(spec_type)
                if isinstance(variant, Mapping):
                    auth_code = variant.get("authorizationCodeGrant")
                    if isinstance(auth_code, Mapping):
                        grants["authorization_code"] = bool(auth_code.get("enabled"))
                        urls = auth_code.get("redirectUrls")
                        if isinstance(urls, list):
                            redirect_urls = [
                                url for url in urls if isinstance(url, str)
                            ]
                    refresh = variant.get("refreshTokenGrant")
                    if isinstance(refresh, Mapping):
                        grants["refresh_token"] = bool(refresh.get("enabled"))

        data_scope: dict[str, Any] = {}
        scopes = application.get("scopes")
        if isinstance(scopes, Mapping):
            scope = scopes.get("dataScope")
            if isinstance(scope, Mapping):
                ontology_rid = scope.get("ontologyRid")
                if isinstance(ontology_rid, str) and ontology_rid:
                    data_scope["ontology_rid"] = ontology_rid
                for key in ("objectTypes", "linkTypes", "actionTypes"):
                    entries = scope.get(key)
                    if isinstance(entries, list):
                        data_scope[key] = len(entries)

        organization_rid = application.get("organizationRid")
        return {
            "application_rid": rid,
            "name": name,
            "organization_rid": organization_rid
            if isinstance(organization_rid, str)
            else None,
            "client_type": client_type,
            "grants": grants,
            "redirect_urls": redirect_urls,
            "data_scope": data_scope,
            "status": "connected",
            "mode": "read-only",
            "warnings": [CONNECT_READ_ONLY_DIVERGENCE],
        }

    # ------------------------------------------------------------------
    # SDK generation (createSdkV2, contract-derived verified contract)
    # ------------------------------------------------------------------

    def get_current_application_version(self, application_rid: str) -> int:
        """Read ``metadata.applicationVersion`` via VERIFIED getApplication.

        Fails loud on drift: the metadata object must carry an integer
        ``applicationVersion`` (bools are rejected explicitly).
        """

        payload = self._conjure_get(
            f"{APPLICATIONS_BASE}/{application_rid}", "getApplication"
        )
        metadata = payload.get("metadata") if isinstance(payload, Mapping) else None
        version = (
            metadata.get("applicationVersion")
            if isinstance(metadata, Mapping)
            else None
        )
        if not isinstance(version, int) or isinstance(version, bool):
            raise SdkDefinitionDriftError(
                f"getApplication for {application_rid} returned no integer "
                f"metadata.applicationVersion; metadata: {str(metadata)[:200]}"
            )
        return version

    @staticmethod
    def _sdk_generate_request(
        application_rid: str, application_version: int
    ) -> dict[str, Any]:
        """The exact createSdkV2 request; the body key set is contract-fixed."""

        return {
            "verb": "POST",
            "path": f"{APPLICATION_SDKS_BASE}/v2/{application_rid}",
            "body": {"applicationVersion": application_version, "npm": {}},
        }

    def plan_sdk_generation(self, application_rid: str) -> dict[str, Any]:
        """Dry-run plan: resolve the app version and show the exact body.

        Never mutates; ``generate_sdk(apply=True)`` sends this request.
        """

        application_version = self.get_current_application_version(application_rid)
        return {
            "application_rid": application_rid,
            "status": "dry-run",
            "application_version": application_version,
            "request": self._sdk_generate_request(application_rid, application_version),
            "contract": SDK_GENERATE_CONTRACT,
            "warnings": [],
        }

    def generate_sdk(
        self,
        application_rid: str,
        *,
        apply: bool = False,
        wait: bool = True,
        timeout_seconds: float = 180.0,
        poll_interval_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Mint a new SDK version from the current app version (plan-first).

        Without ``apply`` this returns the dry-run plan and sends nothing
        mutating. With ``apply`` the contract-verified createSdkV2 POST is
        issued; when ``wait`` is set listSdks is then polled until the
        minted record's ``npm.status.type`` turns terminal (``success``,
        or anything else outside requested/inProgress, which is reported
        as ``failed``) or the timeout lapses (reported as ``timeout``).
        """

        if not apply:
            return self.plan_sdk_generation(application_rid)

        application_version = self.get_current_application_version(application_rid)
        request = self._sdk_generate_request(application_rid, application_version)
        payload = self._conjure_write(
            str(request["verb"]),
            str(request["path"]),
            "createSdkV2",
            json_body=request["body"],
        )
        record = self._expect_sdk_record(payload, "createSdkV2", application_rid)
        result: dict[str, Any] = {
            "application_rid": application_rid,
            "application_version": application_version,
            "request": request,
            "contract": SDK_GENERATE_CONTRACT,
            "warnings": [],
            **record,
        }
        if not wait:
            return {**result, "status": "requested"}
        return self._poll_sdk_generation(
            application_rid,
            result,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    def _poll_sdk_generation(
        self,
        application_rid: str,
        result: dict[str, Any],
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, Any]:
        """Poll listSdks until the minted record's npm status is terminal.

        The ``/latest?sdkType=NPM&sdkStatus=REQUESTED`` confirmation read
        from the MCP capture cannot be used as the completion poll: it
        returns 204 No Content the moment the record leaves ``requested``
        (observed live; the status union includes an
        ``inProgress`` intermediate state). So this polls the VERIFIED
        listSdks endpoint and tracks the minted ``sdk_version`` instead.
        Non-terminal statuses are ``requested`` and ``inProgress``; any
        other terminal status but ``success`` is reported as ``failed``.
        A minted version missing from a poll page is treated as transient
        (the POST already returned the record) and retried until the
        deadline.
        """

        started = time.monotonic()
        deadline = started + timeout_seconds
        attempts = 0
        minted_version = result["sdk_version"]
        while True:
            attempts += 1
            payload = self._conjure_get(
                f"{APPLICATION_SDKS_BASE}/{application_rid}", "listSdks"
            )
            if not isinstance(payload, Mapping) or not isinstance(
                payload.get("sdks"), list
            ):
                raise SdkDefinitionDriftError(
                    f"listSdks for {application_rid} returned a payload "
                    f"without a 'sdks' list while polling SDK generation: "
                    f"{str(payload)[:200]}"
                )
            record = self._find_sdk_record(
                payload["sdks"], minted_version, application_rid
            )
            if record is not None:
                npm_status = record["npm_status"]
                if npm_status is None:
                    raise SdkDefinitionDriftError(
                        f"listSdks for {application_rid} returned the minted "
                        f"record {minted_version} without npm.status.type"
                    )
                result.update(record)
                if npm_status not in _SDK_GENERATION_PENDING_STATUSES:
                    return {
                        **result,
                        "status": "success" if npm_status == "success" else "failed",
                        "poll": {
                            "attempts": attempts,
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                        },
                    }
            now = time.monotonic()
            if now >= deadline:
                return {
                    **result,
                    "status": "timeout",
                    "reason": SDK_GENERATE_TIMEOUT_REASON,
                    "poll": {
                        "attempts": attempts,
                        "elapsed_seconds": round(now - started, 3),
                    },
                }
            time.sleep(poll_interval_seconds)

    def _find_sdk_record(
        self, sdks: list[Any], minted_version: str, application_rid: str
    ) -> Optional[dict[str, Any]]:
        """Locate the minted version in a listSdks page; None when absent."""

        for entry in sdks:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("version") == minted_version:
                return self._expect_sdk_record(entry, "listSdks", application_rid)
        return None

    @staticmethod
    def _expect_sdk_record(
        payload: Any, operation: str, application_rid: str
    ) -> dict[str, Any]:
        """Shape-check one SDK record; fail loud when ``version`` drifts."""

        if not isinstance(payload, Mapping):
            raise SdkDefinitionDriftError(
                f"{operation} for {application_rid} returned a non-object "
                f"payload: {str(payload)[:200]}"
            )
        version = payload.get("version")
        if not isinstance(version, str) or not version:
            raise SdkDefinitionDriftError(
                f"{operation} for {application_rid} returned no string "
                f"'version'; payload keys: "
                f"{sorted(str(key) for key in payload)}"
            )
        record: dict[str, Any] = {
            "sdk_version": version,
            "repository_rid": None,
            "npm_package_name": None,
            "npm_status": None,
        }
        repository_rid = payload.get("repositoryRid")
        if isinstance(repository_rid, str) and repository_rid:
            record["repository_rid"] = repository_rid
        npm = payload.get("npm")
        if isinstance(npm, Mapping):
            package_name = npm.get("npmPackageName")
            if isinstance(package_name, str) and package_name:
                record["npm_package_name"] = package_name
            status = npm.get("status")
            if isinstance(status, Mapping):
                status_type = status.get("type")
                if isinstance(status_type, str) and status_type:
                    record["npm_status"] = status_type
        return record

    # ------------------------------------------------------------------
    # OSDK -> React scaffold (local codegen, never network-mutating)
    # ------------------------------------------------------------------

    def generate_react_scaffold(
        self,
        application_rid: str,
        output_dir: Path,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Emit typed React presentational components for an app's OSDK.

        Reads the app's data scope (VERIFIED ``getApplication``) and the
        ontology's object types (public ``GET
        /api/v2/ontologies/{ontologyRid}/objectTypes``, contract-verified
        ), then writes one ``<ApiName>Card.tsx`` per in-scope
        object type plus an ``index.ts`` barrel into ``output_dir``.
        Never overwrites existing files without ``force``; all-or-nothing.
        """

        application = self._get_application(application_rid)
        scopes = application.get("scopes")
        scope = scopes.get("dataScope") if isinstance(scopes, Mapping) else None
        ontology_rid = scope.get("ontologyRid") if isinstance(scope, Mapping) else None
        raw_rids = scope.get("objectTypes") if isinstance(scope, Mapping) else None
        if (
            not isinstance(ontology_rid, str)
            or not ontology_rid
            or not isinstance(raw_rids, list)
        ):
            return {
                "application_rid": application_rid,
                "output_dir": str(output_dir),
                "status": "unresolved",
                "reason": (
                    "data-scope-unresolved: the application's scopes did not "
                    "expose an ontologyRid and object-type list; refusing to "
                    "scaffold the whole ontology unscoped."
                ),
                "object_types": [],
                "files": [],
                "warnings": [],
            }
        scoped_rids = {rid for rid in raw_rids if isinstance(rid, str)}

        object_types, warnings = self._list_scoped_object_types(
            ontology_rid, scoped_rids
        )
        rendered = [
            (
                output_dir / f"{object_type['api_name']}Card.tsx",
                _render_object_card(object_type),
            )
            for object_type in object_types
        ]
        rendered.append(
            (
                output_dir / "index.ts",
                _render_barrel([ot["api_name"] for ot in object_types]),
            )
        )

        conflicts = [str(path) for path, _ in rendered if path.exists()]
        if conflicts and not force:
            return {
                "application_rid": application_rid,
                "ontology_rid": ontology_rid,
                "output_dir": str(output_dir),
                "status": "conflict",
                "reason": (
                    "output-files-exist: refusing to overwrite without "
                    "--force; conflicts: " + ", ".join(sorted(conflicts))
                ),
                "conflicts": sorted(conflicts),
                "object_types": [ot["api_name"] for ot in object_types],
                "files": [],
                "warnings": warnings,
            }

        output_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for path, content in rendered:
            path.write_text(content, encoding="utf-8")
            written.append(str(path))
        return {
            "application_rid": application_rid,
            "ontology_rid": ontology_rid,
            "output_dir": str(output_dir),
            "status": "generated",
            "reason": None,
            "object_types": [ot["api_name"] for ot in object_types],
            "files": written,
            "warnings": warnings,
        }

    def _list_scoped_object_types(
        self, ontology_rid: str, scoped_rids: set[str]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """List the app's in-scope object types via the public v2 API."""

        object_types: list[dict[str, Any]] = []
        warnings: list[str] = []
        page_token: Optional[str] = None
        while True:
            path = f"/api/v2/ontologies/{ontology_rid}/objectTypes?pageSize=100"
            if page_token:
                path += f"&pageToken={quote(page_token, safe='')}"
            page = self._conjure_get(path, "listObjectTypes")
            if not isinstance(page, Mapping) or not isinstance(page.get("data"), list):
                raise SdkDefinitionDriftError(
                    f"listObjectTypes for {ontology_rid} returned a payload "
                    f"without a 'data' list: {str(page)[:200]}"
                )
            for raw_object in page["data"]:
                parsed = _parse_v2_object_type(raw_object, scoped_rids, warnings)
                if parsed is not None:
                    object_types.append(parsed)
            token = page.get("nextPageToken")
            if not isinstance(token, str) or not token:
                break
            page_token = token
        return object_types, warnings

    # ------------------------------------------------------------------
    # Install planning and execution
    # ------------------------------------------------------------------

    def build_install_plan(
        self, application_rid: str, version: Optional[str] = None
    ) -> dict[str, Any]:
        """Resolve repository + SDK definition into an executable plan.

        Package coordinates are extracted only from explicitly recognized
        definition shapes; anything unrecognized yields ``status:
        unresolved`` with the residual gap spelled out.
        """

        repository_rid = self.get_sdk_repository_rid(application_rid)
        sdk = self.get_sdk(application_rid, version)
        sdk_version = sdk["version"]
        definition = sdk["definition"]
        coordinates = _extract_package_coordinates(definition, sdk_version)

        base_url = self._stack_base_url()
        steps = [
            self._install_step(coordinate, repository_rid, base_url)
            for coordinate in coordinates
        ]
        return {
            "application_rid": application_rid,
            "sdk_version": sdk_version,
            "repository_rid": repository_rid,
            "base_url": base_url,
            "coordinates": coordinates,
            "steps": steps,
            "warnings": [REGISTRY_UNVERIFIED_WARNING],
            "status": "planned" if steps else "unresolved",
            "reason": None if steps else COORDINATES_UNRESOLVED_REASON,
        }

    def install_sdk_package(
        self,
        application_rid: str,
        *,
        version: Optional[str] = None,
        yes: bool = False,
        target: Optional[Path] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Install the generated OSDK package, dry-run unless told otherwise.

        Non-destructive by default: without ``yes`` or ``target`` (or with
        ``dry_run``) nothing is executed and the plan is returned with status
        ``dry-run``. Execution never uses sudo and never targets the system
        Python; pip without ``--target`` is allowed only inside an active
        virtualenv, and npm always requires ``--target``.
        """

        plan = self.build_install_plan(application_rid, version)
        if plan["status"] == "unresolved":
            return plan

        execute = (yes or target is not None) and not dry_run
        if not execute:
            return {**plan, "status": "dry-run", "executed": []}

        executed = []
        for step in plan["steps"]:
            executed.append(self._execute_step(step, yes=yes, target=target))
        failures = [entry for entry in executed if entry["returncode"] != 0]
        return {
            **plan,
            "status": "failed" if failures else "installed",
            "executed": executed,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _conjure_get(self, path: str, operation: str) -> Any:
        return self._conjure_call("GET", path, operation)

    def _conjure_write(
        self,
        verb: str,
        path: str,
        operation: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        return self._conjure_call(verb, path, operation, json_body=json_body)

    def _conjure_call(
        self,
        verb: str,
        path: str,
        operation: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        if json_body is None:
            status, payload, raw = self.client.conjure(verb, path)
        else:
            status, payload, raw = self.client.conjure(verb, path, json_body=json_body)
        if not 200 <= status < 300:
            error_name = (
                payload.get("errorName") if isinstance(payload, Mapping) else None
            )
            if error_name == "Route:RouteNotMounted":
                raise RuntimeError(
                    "The third-party-application-service API is not mounted on "
                    f"this stack (Route:RouteNotMounted for {path})"
                )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"{operation} failed with HTTP {status}{detail}: {str(raw)[:200]}"
            )
        return payload

    def _stack_base_url(self) -> str:
        credentials = CredentialStorage().get_profile(self.client.profile)
        return FoundryInternalClient._base_url(credentials.get("host", ""))

    @staticmethod
    def _extract_version(definition: Mapping[str, Any]) -> Optional[str]:
        for key in ("version", "sdkVersion"):
            value = definition.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _install_step(
        coordinate: Mapping[str, Any], repository_rid: str, base_url: str
    ) -> dict[str, Any]:
        ecosystem = coordinate["ecosystem"]
        name = coordinate["name"]
        version = coordinate.get("version")
        release_base = ARTIFACTS_RELEASE_PATH.format(repository_rid=repository_rid)
        if ecosystem == "pypi":
            registry_url = f"{base_url}{release_base}/pypi/simple"
            requirement = f"{name}=={version}" if version else name
            command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--index-url",
                registry_url,
                requirement,
            ]
        else:
            registry_url = f"{base_url}{release_base}/npm"
            requirement = f"{name}@{version}" if version else name
            command = [
                "npm",
                "install",
                "--registry",
                registry_url,
                requirement,
            ]
        return {
            "ecosystem": ecosystem,
            "package": requirement,
            "registry_url": registry_url,
            "command": command,
        }

    def _execute_step(
        self,
        step: Mapping[str, Any],
        *,
        yes: bool,
        target: Optional[Path],
    ) -> dict[str, Any]:
        command = list(step["command"])
        refusal = self._execution_refusal(step["ecosystem"], yes=yes, target=target)
        if refusal is not None:
            return {**dict(step), "returncode": None, "refused": refusal}
        if target is not None:
            if step["ecosystem"] == "pypi":
                command.extend(["--target", str(target)])
            else:
                command.extend(["--prefix", str(target)])
        completed = subprocess.run(  # nosec B603 - list argv, no shell; command from package-manager plan
            command,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {
            **dict(step),
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }

    @staticmethod
    def _execution_refusal(
        ecosystem: str, *, yes: bool, target: Optional[Path]
    ) -> Optional[str]:
        if ecosystem == "npm" and target is None:
            return (
                "npm installs require --target <project-dir>; a global or "
                "system-wide npm install is never performed."
            )
        if ecosystem == "pypi" and target is None:
            if not yes:
                return "pip installs outside a --target dir require --yes."
            if sys.prefix == sys.base_prefix:
                return (
                    "refusing to install into the system Python "
                    "(sys.prefix == sys.base_prefix); use --target or run "
                    "inside a virtualenv."
                )
        return None


def _extract_package_coordinates(
    definition: Mapping[str, Any], sdk_version: Optional[str]
) -> list[dict[str, Any]]:
    """Extract npm/pypi coordinates from explicitly recognized shapes only."""

    coordinates: list[dict[str, Any]] = []

    packages = definition.get("packages")
    if isinstance(packages, list):
        for item in packages:
            if not isinstance(item, Mapping):
                continue
            ecosystem = _ECOSYSTEM_ALIASES.get(
                str(item.get("type") or item.get("ecosystem") or "").lower()
            )
            name = item.get("name") or item.get("packageName")
            if ecosystem and isinstance(name, str) and name:
                item_version = item.get("version")
                coordinates.append(
                    {
                        "ecosystem": ecosystem,
                        "name": name,
                        "version": item_version
                        if isinstance(item_version, str) and item_version
                        else sdk_version,
                    }
                )

    for key, ecosystem in (
        ("npmPackage", "npm"),
        ("pypiPackage", "pypi"),
        ("pythonPackage", "pypi"),
    ):
        entry = definition.get(key)
        package_name: Optional[str] = None
        entry_version: Optional[str] = None
        if isinstance(entry, str) and entry:
            package_name = entry
        elif isinstance(entry, Mapping):
            candidate = entry.get("name") or entry.get("packageName")
            if isinstance(candidate, str) and candidate:
                package_name = candidate
                candidate_version = entry.get("version")
                if isinstance(candidate_version, str) and candidate_version:
                    entry_version = candidate_version
        if package_name:
            coordinates.append(
                {
                    "ecosystem": ecosystem,
                    "name": package_name,
                    "version": entry_version or sdk_version,
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for coordinate in coordinates:
        marker = (coordinate["ecosystem"], coordinate["name"])
        if marker not in seen:
            seen.add(marker)
            deduped.append(coordinate)
    return deduped


# ---------------------------------------------------------------------------
# React scaffold rendering (convert-osdk-react)
# ---------------------------------------------------------------------------

# Public v2 ObjectType dataType.type -> TypeScript type. Grounded in the
# live-observed values and the vendored OntologyIrType union in
# derived from the published client contract (@osdk/client.unstable ontology-metadata
# types); anything unrecognized becomes `unknown` with a warning instead of a
# guessed type.
_TS_TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "byte": "number",
    "short": "number",
    "integer": "number",
    "long": "number",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "date": "string",
    "timestamp": "string",
    "array": "unknown[]",
}


def _parse_v2_object_type(
    raw_object: Any,
    scoped_rids: set[str],
    warnings: list[str],
) -> Optional[dict[str, Any]]:
    """Parse one public-v2 ObjectType entry; None when out of scope.

    Fails loud on the relied-upon fields (string ``apiName``, object
    ``properties``); per-property oddities degrade to ``unknown`` with a
    warning rather than aborting the whole scaffold.
    """

    if not isinstance(raw_object, Mapping):
        raise SdkDefinitionDriftError(
            f"listObjectTypes returned a non-object entry: {str(raw_object)[:200]}"
        )
    rid = raw_object.get("rid")
    if isinstance(rid, str) and rid not in scoped_rids:
        return None
    api_name = raw_object.get("apiName")
    properties = raw_object.get("properties")
    if (
        not isinstance(api_name, str)
        or not api_name
        or not isinstance(properties, Mapping)
    ):
        raise SdkDefinitionDriftError(
            "listObjectTypes entry missing string apiName or object "
            f"properties; keys: {sorted(str(key) for key in raw_object)}"
        )

    parsed_properties = []
    for prop_api_name, raw_property in properties.items():
        ts_type = "unknown"
        display_name: Optional[str] = None
        if isinstance(raw_property, Mapping):
            prop_display = raw_property.get("displayName")
            if isinstance(prop_display, str) and prop_display:
                display_name = prop_display
            data_type = raw_property.get("dataType")
            if isinstance(data_type, Mapping):
                type_name = data_type.get("type")
                if isinstance(type_name, str):
                    ts_type = _TS_TYPE_MAP.get(type_name, "unknown")
                    if type_name not in _TS_TYPE_MAP:
                        warnings.append(
                            f"{api_name}.{prop_api_name}: unrecognized "
                            f"dataType '{type_name}', rendered as unknown."
                        )
        else:
            warnings.append(
                f"{api_name}.{prop_api_name}: property entry is not an "
                "object, rendered as unknown."
            )
        parsed_properties.append(
            {
                "api_name": str(prop_api_name),
                "display_name": display_name or str(prop_api_name),
                "ts_type": ts_type,
            }
        )

    title_property = raw_object.get("titleProperty")
    return {
        "api_name": api_name,
        "display_name": raw_object.get("displayName")
        if isinstance(raw_object.get("displayName"), str)
        else api_name,
        "title_property": title_property
        if isinstance(title_property, str) and title_property
        else None,
        "properties": parsed_properties,
    }


def _ts_key(api_name: str) -> str:
    """Render a property key as an identifier, quoted only when needed."""

    if api_name.isidentifier():
        return api_name
    return json.dumps(api_name)


def _render_object_card(object_type: Mapping[str, Any]) -> str:
    """Render one typed presentational ``<ApiName>Card.tsx`` component."""

    api_name = object_type["api_name"]
    properties = object_type["properties"]
    title_property = object_type["title_property"]

    lines = [
        "// Generated by `foundry dev-console convert-osdk-react`. Regenerate",
        "// instead of editing by hand. Presentational scaffold: wire data",
        "// fetching with the app's generated OSDK package as needed.",
        'import type { ReactElement } from "react";',
        "",
        f"export interface {api_name}Object {{",
    ]
    for prop in properties:
        lines.append(f"  {_ts_key(prop['api_name'])}: {prop['ts_type']};")
    lines += [
        "}",
        "",
        f"export function {api_name}Card(",
        f"  {{ object }}: {{ object: {api_name}Object }},",
        "): ReactElement {",
        "  return (",
        f'    <section data-object-type="{api_name}">',
    ]
    if title_property:
        lines.append(
            f"      <h2>{{String(object.{_ts_key(title_property)})}}</h2>"
            if _ts_key(title_property) == title_property
            else f"      <h2>{{String(object[{json.dumps(title_property)}])}}</h2>"
        )
    lines.append("      <dl>")
    for prop in properties:
        key = _ts_key(prop["api_name"])
        access = (
            f"object.{key}"
            if key == prop["api_name"]
            else f"object[{json.dumps(prop['api_name'])}]"
        )
        lines.append(f"        <dt>{prop['display_name']}</dt>")
        lines.append(f"        <dd>{{String({access})}}</dd>")
    lines += [
        "      </dl>",
        "    </section>",
        "  );",
        "}",
        "",
    ]
    return "\n".join(lines)


def _render_barrel(api_names: list[str]) -> str:
    """Render the ``index.ts`` barrel for the generated components."""

    lines = [
        "// Generated by `foundry dev-console convert-osdk-react`. Regenerate",
        "// instead of editing by hand.",
    ]
    for api_name in api_names:
        lines.append(f'export {{ {api_name}Card }} from "./{api_name}Card";')
        lines.append(f'export type {{ {api_name}Object }} from "./{api_name}Card";')
    return "\n".join(lines) + "\n"
