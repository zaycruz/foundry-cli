"""Verified Compass discovery operations.

The pinned SDK (foundry-platform-sdk 1.95.0) exposes neither a Namespace
resource nor a project-template catalog.  Both enumerations exist on the
internal Compass Conjure service and were verified live (read-only) on
 against a live deployment:

- ``GET /compass/api/hierarchy/v2/all-namespace-rids`` returns a JSON array
  of namespace RIDs (folder-typed RIDs; the hydrated resource carries
  ``urlVariables["compass:folderType"] == "namespace"``).
- ``PUT /compass/api/hierarchy/v2/batch/namespaces`` is a read-PUT batch get:
  the request body is a bare JSON array of namespace RIDs and the response is
  a ``{rid: {"resource": {...}, ...}}`` map.  Unknown or unauthorized RIDs
  are silently omitted from the map, so unhydrated records are flagged
  rather than dropped.
- ``GET /compass/api/templates/namespace/{namespaceRid}`` returns a JSON
  array of project-template objects (``rid``, ``name``, ``description``,
  ``definition``, ``namespaceRid``, ``principalsAllowedToUseTemplate``).

All three endpoints were previously catalog-only rows read from the
``@palantir/mcp`` v0.397.0 published contract.  Neither endpoint paginates, so this
service applies an honest client-side offset cursor.
"""

from typing import Any, Dict, List, Mapping, Optional

from ..auth.base import ProfileNotFoundError
from ..utils.pagination import PaginationMetadata, PaginationResult
from .base import BaseService
from .foundry_internal_client import FoundryInternalClient

_ALL_NAMESPACE_RIDS_PATH = "/compass/api/hierarchy/v2/all-namespace-rids"
_BATCH_NAMESPACES_PATH = "/compass/api/hierarchy/v2/batch/namespaces"
_TEMPLATES_FOR_NAMESPACE_PATH = "/compass/api/templates/namespace/{namespace_rid}"

_ERROR_SNIPPET_LIMIT = 200


class CompassService(BaseService):
    """Service wrapper for verified Compass namespace and template reads."""

    def __init__(
        self,
        profile: Optional[str] = None,
        *,
        internal_client: Optional[FoundryInternalClient] = None,
    ) -> None:
        super().__init__(profile=profile)
        self._internal_client = internal_client

    def _get_service(self) -> Any:
        return self.client.filesystem

    def _get_internal_client(self) -> FoundryInternalClient:
        """Lazily resolve the internal API client for the effective profile."""
        if self._internal_client is None:
            effective_profile = self.profile or self.auth_manager.get_current_profile()
            if not effective_profile:
                raise ProfileNotFoundError(
                    "No profile specified and no default profile configured. "
                    "Run 'foundry configure configure' to set up authentication."
                )
            self._internal_client = FoundryInternalClient(effective_profile)
        return self._internal_client

    def list_namespaces(
        self,
        *,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> PaginationResult:
        """List Compass namespaces via the verified internal hierarchy API.

        Records keep ``type: namespace`` with ``source_type:
        compass-namespace``.  A namespace the batch hydration silently omits
        (permissions filter at HTTP 200, never 403) is returned unhydrated
        with ``hydrated: False`` instead of being dropped.  Records are sorted
        by RID so the client-side offset cursor is stable across invocations.
        """
        rids = self._all_namespace_rids()
        hydrated = self._hydrate_namespaces(rids)
        records = [self._format_namespace(rid, hydrated.get(rid)) for rid in rids]
        records.sort(key=lambda record: str(record.get("rid") or ""))
        return self._paginate(records, page_size, page_token)

    def list_project_templates(
        self,
        *,
        namespace_rid: Optional[str] = None,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> PaginationResult:
        """List project templates across one or all visible namespaces.

        Templates are scoped to a namespace in Compass; without an explicit
        ``namespace_rid`` every namespace from ``all-namespace-rids`` is
        queried and the results are combined.  A namespace the caller cannot
        read surfaces as a loud error naming that namespace.  Records are
        sorted by RID so the client-side offset cursor is stable across
        invocations.
        """
        namespace_rids = (
            [namespace_rid] if namespace_rid else self._all_namespace_rids()
        )
        records: List[Dict[str, Any]] = []
        for rid in namespace_rids:
            path = _TEMPLATES_FOR_NAMESPACE_PATH.format(namespace_rid=rid)
            status, parsed, raw = self._get_internal_client().conjure("GET", path)
            if status != 200:
                raise RuntimeError(
                    "Failed to list project templates for namespace "
                    f"{rid}: GET {path} returned HTTP {status}: "
                    f"{self._error_snippet(raw)}"
                )
            if not isinstance(parsed, list):
                raise RuntimeError(
                    "Failed to list project templates for namespace "
                    f"{rid}: unexpected response shape "
                    f"({type(parsed).__name__}, expected list)"
                )
            records.extend(
                self._format_template(template)
                for template in parsed
                if isinstance(template, Mapping)
            )
        records.sort(key=lambda record: str(record.get("rid") or ""))
        return self._paginate(records, page_size, page_token)

    def _all_namespace_rids(self) -> List[str]:
        status, parsed, raw = self._get_internal_client().conjure(
            "GET", _ALL_NAMESPACE_RIDS_PATH
        )
        if status != 200:
            raise RuntimeError(
                "Failed to list Foundry namespaces: GET "
                f"{_ALL_NAMESPACE_RIDS_PATH} returned HTTP {status}: "
                f"{self._error_snippet(raw)}"
            )
        if not isinstance(parsed, list) or not all(
            isinstance(rid, str) for rid in parsed
        ):
            raise RuntimeError(
                "Failed to list Foundry namespaces: unexpected response shape "
                f"from {_ALL_NAMESPACE_RIDS_PATH} (expected a list of RIDs)"
            )
        return list(parsed)

    def _hydrate_namespaces(self, rids: List[str]) -> Mapping[str, Any]:
        if not rids:
            return {}
        status, parsed, raw = self._get_internal_client().conjure(
            "PUT", _BATCH_NAMESPACES_PATH, json_body=list(rids)
        )
        if status != 200:
            raise RuntimeError(
                "Failed to hydrate Foundry namespaces: PUT "
                f"{_BATCH_NAMESPACES_PATH} returned HTTP {status}: "
                f"{self._error_snippet(raw)}"
            )
        if not isinstance(parsed, Mapping):
            raise RuntimeError(
                "Failed to hydrate Foundry namespaces: unexpected response "
                f"shape from {_BATCH_NAMESPACES_PATH} "
                f"({type(parsed).__name__}, expected object)"
            )
        return parsed

    @staticmethod
    def _paginate(
        records: List[Dict[str, Any]],
        page_size: Optional[int],
        page_token: Optional[str],
    ) -> PaginationResult:
        """Apply a client-side offset cursor over a fully fetched list."""
        offset = 0
        if page_token is not None:
            try:
                offset = int(page_token)
            except ValueError:
                raise RuntimeError(
                    f"Invalid page token {page_token!r}: this operation uses a "
                    "client-side offset cursor"
                )
            if offset < 0:
                raise RuntimeError(
                    f"Invalid page token {page_token!r}: offset must be >= 0"
                )
        if page_size is None:
            window = records[offset:]
            next_token = None
        else:
            window = records[offset : offset + page_size]
            next_offset = offset + page_size
            next_token = str(next_offset) if next_offset < len(records) else None
        return PaginationResult(
            data=window,
            metadata=PaginationMetadata(
                current_page=1,
                items_fetched=len(window),
                next_page_token=next_token,
                has_more=next_token is not None,
                total_pages_fetched=1,
            ),
        )

    @staticmethod
    def _format_namespace(rid: str, entry: Any) -> Dict[str, Any]:
        resource: Mapping[str, Any] = {}
        if isinstance(entry, Mapping):
            candidate = entry.get("resource")
            if isinstance(candidate, Mapping):
                resource = candidate
        created = resource.get("created")
        modified = resource.get("modified")
        return {
            "rid": rid,
            "display_name": resource.get("name"),
            "description": resource.get("description"),
            "path": resource.get("path"),
            "alias": resource.get("alias"),
            "created_time": (
                created.get("time") if isinstance(created, Mapping) else None
            ),
            "modified_time": (
                modified.get("time") if isinstance(modified, Mapping) else None
            ),
            "hydrated": bool(resource),
            "type": "namespace",
            "source_type": "compass-namespace",
        }

    @staticmethod
    def _format_template(template: Mapping[str, Any]) -> Dict[str, Any]:
        definition = template.get("definition")
        variables = (
            definition.get("variables") if isinstance(definition, Mapping) else None
        )
        return {
            "rid": template.get("rid"),
            "display_name": template.get("name"),
            "description": template.get("description"),
            "namespace_rid": template.get("namespaceRid"),
            "variables": (
                sorted(variables.keys()) if isinstance(variables, Mapping) else []
            ),
            "principals_allowed_to_use_template": template.get(
                "principalsAllowedToUseTemplate"
            ),
            "type": "project-template",
            "source_type": "compass-template",
        }

    @staticmethod
    def _error_snippet(raw: Any) -> str:
        text = raw if isinstance(raw, str) else str(raw)
        return text[:_ERROR_SNIPPET_LIMIT]
