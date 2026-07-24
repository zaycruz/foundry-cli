"""
Connectivity service wrapper for Foundry SDK.
"""

import json
import logging
import os
from collections import deque
from typing import Any, Dict, List, Mapping, Optional

from .base import BaseService
from .foundry_internal_client import FoundryInternalClient

logger = logging.getLogger(__name__)


class WebhookNotFoundError(RuntimeError):
    """Raised when the webhook registry returns no webhook for a RID."""


class EgressPolicyNotFoundError(RuntimeError):
    """Raised when no existing egress policy matches a requested target.

    The CLI never creates network egress policies (mutations are not
    enabled), so a missing match is a loud, explicit failure carrying the
    "would create" intent rather than a silent create.
    """


class EgressPolicyShapeError(RuntimeError):
    """Raised when an egress policy read does not match the verified shape."""


class ConnectivityService(BaseService):
    """Service wrapper for Foundry connectivity operations."""

    DEFAULT_FILESYSTEM_FALLBACK_START_FOLDER_RID = "ri.compass.main.folder.0"
    MAX_FALLBACK_FOLDERS = 1000

    def _get_service(self) -> Any:
        """Get the Foundry client for connectivity operations."""
        return self.client

    @property
    def connections_service(self) -> Any:
        """Get the connections service from the client."""
        # Prefer legacy namespace first for backward compatibility with older SDKs.
        legacy_connections = getattr(self.client, "connections", None)
        if legacy_connections is not None:
            return legacy_connections

        connectivity = getattr(self.client, "connectivity", None)
        if connectivity is None:
            raise RuntimeError("Connectivity service is not available on the client")
        return connectivity

    @property
    def file_imports_service(self) -> Any:
        """Get the file imports service from the client."""
        return self.client.connectivity.Connection.FileImport

    @property
    def table_imports_service(self) -> Any:
        """Get the table imports service from the client."""
        return self.client.connectivity.Connection.TableImport

    def list_connections(self) -> List[Dict[str, Any]]:
        """
        List available connections.

        Returns:
            List of connection information dictionaries
        """
        try:
            logger.warning(
                "The SDK has no Connection.list(); scanning the filesystem instead. "
                "Set PLTR_CONNECTIONS_FALLBACK_START_FOLDER_RID to a narrower folder "
                "if this is slow."
            )
            return self._list_connections_from_filesystem()
        except Exception as e:
            raise RuntimeError(f"Failed to list connections: {e}")

    def get_connection(self, connection_rid: str) -> Dict[str, Any]:
        """
        Get information about a specific connection.

        Args:
            connection_rid: Connection Resource Identifier

        Returns:
            Connection information dictionary
        """
        try:
            connection = self.connections_service.Connection.get(connection_rid)
            return self._format_connection_info(connection)
        except Exception as e:
            raise RuntimeError(f"Failed to get connection {connection_rid}: {e}")

    def create_connection(
        self,
        display_name: str,
        parent_folder_rid: str,
        configuration: Dict[str, Any],
        worker: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new connection.

        Args:
            display_name: Display name for the connection
            parent_folder_rid: Parent folder Resource Identifier
            configuration: Connection configuration dictionary
            worker: Worker configuration dictionary

        Returns:
            Created connection information dictionary
        """
        try:
            connection = self.connections_service.Connection.create(
                configuration=configuration,
                display_name=display_name,
                parent_folder_rid=parent_folder_rid,
                worker=worker,
            )
            return self._format_connection_info(connection)
        except Exception as e:
            raise RuntimeError(f"Failed to create connection '{display_name}': {e}")

    def get_connection_configuration(self, connection_rid: str) -> Dict[str, Any]:
        """
        Get connection configuration.

        Args:
            connection_rid: Connection Resource Identifier

        Returns:
            Connection configuration dictionary
        """
        try:
            config = self.connections_service.Connection.get_configuration(
                connection_rid
            )
            return {"connection_rid": connection_rid, "configuration": config}
        except Exception as e:
            raise RuntimeError(
                f"Failed to get configuration for connection {connection_rid}: {e}"
            )

    def update_export_settings(
        self, connection_rid: str, export_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update connection export settings.

        Args:
            connection_rid: Connection Resource Identifier
            export_settings: Export settings dictionary

        Returns:
            Status dictionary
        """
        try:
            self.connections_service.Connection.update_export_settings(
                connection_rid=connection_rid,
                export_settings=export_settings,
            )
            return {
                "connection_rid": connection_rid,
                "status": "export settings updated",
            }
        except Exception as e:
            raise RuntimeError(
                f"Failed to update export settings for connection {connection_rid}: {e}"
            )

    def update_secrets(
        self, connection_rid: str, secrets: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Update connection secrets.

        Args:
            connection_rid: Connection Resource Identifier
            secrets: Dictionary mapping secret names to values

        Returns:
            Status dictionary
        """
        try:
            self.connections_service.Connection.update_secrets(
                connection_rid=connection_rid,
                secrets=secrets,
            )
            return {"connection_rid": connection_rid, "status": "secrets updated"}
        except Exception as e:
            raise RuntimeError(
                f"Failed to update secrets for connection {connection_rid}: {e}"
            )

    def upload_custom_jdbc_drivers(
        self, connection_rid: str, file_path: str
    ) -> Dict[str, Any]:
        """
        Upload custom JDBC drivers to a connection.

        Args:
            connection_rid: Connection Resource Identifier
            file_path: Path to the JAR file

        Returns:
            Updated connection information dictionary
        """
        from pathlib import Path

        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path_obj.suffix.lower() == ".jar":
            raise ValueError(f"File must be a JAR file: {file_path}")

        try:
            with open(file_path_obj, "rb") as f:
                file_content = f.read()

            connection = self.connections_service.Connection.upload_custom_jdbc_drivers(
                connection_rid=connection_rid,
                body=file_content,
                file_name=file_path_obj.name,
            )
            return self._format_connection_info(connection)
        except Exception as e:
            raise RuntimeError(
                f"Failed to upload JDBC driver to connection {connection_rid}: {e}"
            )

    def get_file_import(self, connection_rid: str, import_rid: str) -> Dict[str, Any]:
        """
        Get information about a specific file import.

        Args:
            connection_rid: Connection Resource Identifier
            import_rid: File import Resource Identifier

        Returns:
            File import information dictionary
        """
        try:
            file_import = self.file_imports_service.get(
                connection_rid=connection_rid,
                file_import_rid=import_rid,
            )
            return self._format_import_info(file_import)
        except Exception as e:
            raise RuntimeError(f"Failed to get file import {import_rid}: {e}")

    def execute_file_import(
        self, connection_rid: str, import_rid: str
    ) -> Dict[str, Any]:
        """Execute a file import and return the asynchronous build RID."""
        try:
            build_rid = self.file_imports_service.execute(
                connection_rid=connection_rid,
                file_import_rid=import_rid,
            )
            return {"build_rid": build_rid}
        except Exception as e:
            raise RuntimeError(f"Failed to execute file import {import_rid}: {e}")

    def get_table_import(self, connection_rid: str, import_rid: str) -> Dict[str, Any]:
        """
        Get information about a specific table import.

        Args:
            connection_rid: Connection Resource Identifier
            import_rid: Table import Resource Identifier

        Returns:
            Table import information dictionary
        """
        try:
            table_import = self.table_imports_service.get(
                connection_rid=connection_rid,
                table_import_rid=import_rid,
            )
            return self._format_import_info(table_import)
        except Exception as e:
            raise RuntimeError(f"Failed to get table import {import_rid}: {e}")

    def execute_table_import(
        self, connection_rid: str, import_rid: str
    ) -> Dict[str, Any]:
        """Execute a table import and return the asynchronous build RID."""
        try:
            build_rid = self.table_imports_service.execute(
                connection_rid=connection_rid,
                table_import_rid=import_rid,
            )
            return {"build_rid": build_rid}
        except Exception as e:
            raise RuntimeError(f"Failed to execute table import {import_rid}: {e}")

    def list_file_imports(self, connection_rid: str) -> List[Dict[str, Any]]:
        """
        List file imports for a connection.

        Args:
            connection_rid: Connection Resource Identifier

        Returns:
            List of file import information dictionaries
        """
        try:
            imports = self.file_imports_service.list(connection_rid=connection_rid)
            return [self._format_import_info(imp) for imp in imports]
        except Exception as e:
            raise RuntimeError(f"Failed to list file imports: {e}")

    def list_table_imports(self, connection_rid: str) -> List[Dict[str, Any]]:
        """
        List table imports for a connection.

        Args:
            connection_rid: Connection Resource Identifier

        Returns:
            List of table import information dictionaries
        """
        try:
            imports = self.table_imports_service.list(connection_rid=connection_rid)
            return [self._format_import_info(imp) for imp in imports]
        except Exception as e:
            raise RuntimeError(f"Failed to list table imports: {e}")

    def get_webhook(
        self, webhook_rid: str, version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get a data-source webhook definition from the webhook registry.

        Read-only against the internal webhooks API, which the 2026-07-22 gap
        analysis marks VERIFIED: GET /webhooks/api/registry/v0/{webhookRid}/latest
        and GET /webhooks/api/registry/v0/{webhookRid}/version/{version}.

        Args:
            webhook_rid: Webhook Resource Identifier
            version: Specific webhook version to fetch (default: latest)

        Returns:
            Webhook definition dictionary

        Raises:
            WebhookNotFoundError: If the registry returns no webhook for the RID
            RuntimeError: If the registry read fails or is unreachable
        """
        if version is None:
            path = f"webhooks/api/registry/v0/{webhook_rid}/latest"
        else:
            path = f"webhooks/api/registry/v0/{webhook_rid}/version/{version}"

        client = self._internal_client()
        try:
            status, payload, raw = client.conjure("GET", path)
        except Exception as e:
            raise RuntimeError(f"Failed to read webhook {webhook_rid}: {e}") from e

        if not 200 <= status < 300:
            error_name = (
                payload.get("errorName") if isinstance(payload, Mapping) else None
            )
            if error_name == "Route:RouteNotMounted":
                raise RuntimeError(
                    "The webhooks registry API is not mounted on this stack "
                    f"(Route:RouteNotMounted for /{path})"
                )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"Webhook registry read failed with HTTP {status}{detail}: "
                f"{str(raw)[:200]}"
            )

        # A missing webhook yields an empty body (HTTP 204), not an error, so
        # an empty payload must fail loudly instead of rendering as a result.
        if not isinstance(payload, Mapping) or not payload:
            raise WebhookNotFoundError(
                f"No webhook found for RID {webhook_rid}"
                + (f" version {version}" if version is not None else "")
            )

        return dict(payload)

    EGRESS_BATCH_SIZE = 50
    # get-all-policies took ~60s in live verification; the default 30s
    # internal-client timeout is not enough for these reads.
    EGRESS_READ_TIMEOUT = 120.0

    def ensure_egress_policy(self, hostname: str) -> Dict[str, Any]:
        """
        Find an existing network egress policy covering a hostname.

        READ-ONLY "ensure": this implements the read half of the MCP
        ``get_or_create_network_egress_policy`` tool against the internal
        resource-policy-manager API (verified on a live Foundry deployment):

        - ``POST /network-egress-policies/get-all-policies`` (read-POST;
          returns a map of policy RID -> summary, values may be null)
        - ``POST /network-egress-policies/get-batch`` (read-POST; bare JSON
          array of policy RIDs, returns a map of policy RID -> policy)

        If no existing policy mentions the hostname, nothing is created:
        EgressPolicyNotFoundError is raised with a "would create, mutations
        not enabled" message. The detailed policy shape is UNVERIFIED (the
        a live Foundry deployment's get-batch returns an empty map), so matching is
        defensive: the hostname is searched case-insensitively in the raw
        policy payload rather than projected from guessed fields.

        Args:
            hostname: Hostname the egress policy must cover

        Returns:
            Dictionary with the matched policy RID and its raw policy payload

        Raises:
            EgressPolicyNotFoundError: If no existing policy covers the
                hostname (the CLI never creates one)
            EgressPolicyShapeError: If a read response is not the verified
                RID map shape
            RuntimeError: If a read fails or the API is not mounted
        """
        if not hostname or not hostname.strip():
            raise ValueError("hostname is required")
        hostname = hostname.strip().lower()

        client = self._internal_client()
        policy_rids = self._list_egress_policy_rids(client)
        if not policy_rids:
            raise EgressPolicyNotFoundError(
                f"No network egress policies exist on this stack; one would be "
                f"created for hostname '{hostname}', but mutations are not "
                "enabled. Create the policy in Foundry and re-run."
            )

        for chunk_start in range(0, len(policy_rids), self.EGRESS_BATCH_SIZE):
            chunk = policy_rids[chunk_start : chunk_start + self.EGRESS_BATCH_SIZE]
            policies = self._get_egress_policies_batch(client, chunk)
            for policy_rid, policy in policies.items():
                if not isinstance(policy, Mapping):
                    continue
                if hostname in json.dumps(policy, default=str).lower():
                    return {
                        "policy_rid": policy_rid,
                        "hostname": hostname,
                        "status": "exists",
                        "policy": dict(policy),
                    }

        raise EgressPolicyNotFoundError(
            f"No existing network egress policy covers hostname '{hostname}'; "
            "one would be created, but mutations are not enabled. Create the "
            "policy in Foundry and re-run."
        )

    def _list_egress_policy_rids(self, client: FoundryInternalClient) -> List[str]:
        """Read all network egress policy RIDs, failing loud on surprises."""
        try:
            status, payload, raw = client.conjure(
                "POST",
                "resource-policy-manager/api/network-egress-policies/get-all-policies",
                json_body={},
                request_timeout=self.EGRESS_READ_TIMEOUT,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to list network egress policies: {e}") from e
        self._raise_egress_for_status(status, payload, raw, "get-all-policies")
        if not isinstance(payload, Mapping):
            raise EgressPolicyShapeError(
                "Unverified get-all-policies response shape: expected a JSON "
                f"object keyed by policy RID, got {str(raw)[:200]!r}. "
                "Refusing to guess at the contract."
            )
        return [str(rid) for rid in payload]

    def _get_egress_policies_batch(
        self, client: FoundryInternalClient, policy_rids: List[str]
    ) -> Dict[str, Any]:
        """Read one batch of egress policies by RID (bare-array read-POST)."""
        try:
            status, payload, raw = client.conjure(
                "POST",
                "resource-policy-manager/api/network-egress-policies/get-batch",
                json_body=policy_rids,
                request_timeout=self.EGRESS_READ_TIMEOUT,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to read network egress policies: {e}") from e
        self._raise_egress_for_status(status, payload, raw, "get-batch")
        if not isinstance(payload, Mapping):
            raise EgressPolicyShapeError(
                "Unverified get-batch response shape: expected a JSON object "
                f"keyed by policy RID, got {str(raw)[:200]!r}. Refusing to "
                "guess at the contract."
            )
        return dict(payload)

    @staticmethod
    def _raise_egress_for_status(
        status: int, payload: Any, raw: Any, operation: str
    ) -> None:
        """Fail loudly on non-2xx resource-policy-manager responses."""
        if 200 <= status < 300:
            return
        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name == "Route:RouteNotMounted":
            raise RuntimeError(
                "The resource-policy-manager API is not mounted on this stack "
                f"(Route:RouteNotMounted during {operation})"
            )
        detail = f" ({error_name})" if error_name else ""
        raise RuntimeError(
            f"Network egress policy {operation} failed with HTTP "
            f"{status}{detail}: {str(raw)[:200]}"
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

    def _format_connection_info(self, connection: Any) -> Dict[str, Any]:
        """
        Format connection information for display.

        Args:
            connection: Connection object from SDK

        Returns:
            Formatted connection dictionary
        """
        try:
            if isinstance(connection, dict):
                return {
                    "rid": connection.get("rid", "N/A"),
                    "display_name": connection.get("display_name", "N/A"),
                    "description": connection.get("description", ""),
                    "connection_type": connection.get("connection_type", "N/A"),
                    "status": connection.get("status", "N/A"),
                    "created_time": connection.get("created_time", "N/A"),
                    "modified_time": connection.get("modified_time", "N/A"),
                }

            return {
                "rid": getattr(connection, "rid", "N/A"),
                "display_name": getattr(connection, "display_name", "N/A"),
                "description": getattr(connection, "description", ""),
                "connection_type": getattr(connection, "connection_type", "N/A"),
                "status": getattr(connection, "status", "N/A"),
                "created_time": getattr(connection, "created_time", "N/A"),
                "modified_time": getattr(connection, "modified_time", "N/A"),
            }
        except Exception:
            return {"raw": str(connection)}

    def _list_connections_from_filesystem(self) -> List[Dict[str, Any]]:
        """
        Discover connection resources from filesystem when SDK list() is unavailable.

        Notes:
            - Uses Folder.children(preview=True), which requires preview access.
            - Traversal starts from PLTR_CONNECTIONS_FALLBACK_START_FOLDER_RID when set,
              otherwise defaults to ri.compass.main.folder.0.
        """
        filesystem = getattr(self.client, "filesystem", None)
        if filesystem is None or not hasattr(filesystem, "Folder"):
            raise RuntimeError(
                "Connection.list() is unavailable and filesystem fallback is not supported"
            )

        folder_client = filesystem.Folder
        start_folder_rid = os.environ.get(
            "PLTR_CONNECTIONS_FALLBACK_START_FOLDER_RID",
            self.DEFAULT_FILESYSTEM_FALLBACK_START_FOLDER_RID,
        )
        pending_folders = deque([start_folder_rid])
        visited_folders: set[str] = set()
        discovered_connections: List[Dict[str, Any]] = []

        while pending_folders and len(visited_folders) < self.MAX_FALLBACK_FOLDERS:
            folder_rid = pending_folders.popleft()
            if folder_rid in visited_folders:
                continue
            visited_folders.add(folder_rid)

            try:
                children = folder_client.children(folder_rid, preview=True)
            except Exception as error:
                if folder_rid == start_folder_rid:
                    raise RuntimeError(
                        f"Unable to list fallback start folder '{start_folder_rid}': {error}"
                    ) from error
                logger.debug(
                    "Skipping folder '%s' during connection discovery due to error: %s",
                    folder_rid,
                    error,
                )
                continue

            for child in children:
                child_rid = getattr(child, "rid", None)
                if not child_rid:
                    continue

                child_type = str(getattr(child, "type", "") or "").lower()
                if self._looks_like_connection_resource(child_rid, child_type):
                    discovered_connections.append(
                        {
                            "rid": child_rid,
                            "display_name": getattr(child, "display_name", "N/A"),
                            "description": getattr(child, "description", ""),
                            "connection_type": child_type or "connection",
                            "status": getattr(child, "status", "N/A"),
                            "created_time": getattr(child, "created_time", "N/A"),
                            "modified_time": getattr(child, "modified_time", "N/A"),
                        }
                    )
                    continue

                if child_type in {"folder", "compass_folder", "project", "space"}:
                    pending_folders.append(child_rid)

        if pending_folders:
            raise RuntimeError(
                "Connection discovery exceeded folder scan limit "
                f"({self.MAX_FALLBACK_FOLDERS}). "
                "Set PLTR_CONNECTIONS_FALLBACK_START_FOLDER_RID to a narrower folder "
                "and retry."
            )

        return discovered_connections

    @staticmethod
    def _looks_like_connection_resource(resource_rid: str, resource_type: str) -> bool:
        """Best-effort detection for connection resources from filesystem entries."""
        return "connection" in resource_type or ".connection." in resource_rid

    def _format_import_info(self, import_obj: Any) -> Dict[str, Any]:
        """
        Format import information for display.

        Args:
            import_obj: Import object from SDK

        Returns:
            Formatted import dictionary
        """
        try:
            return {
                "rid": getattr(import_obj, "rid", "N/A"),
                "display_name": getattr(import_obj, "display_name", "N/A"),
                "connection_rid": getattr(import_obj, "connection_rid", "N/A"),
                "target_dataset_rid": getattr(import_obj, "target_dataset_rid", "N/A"),
                "status": getattr(import_obj, "status", "N/A"),
                "import_type": getattr(import_obj, "import_type", "N/A"),
                "source": getattr(import_obj, "source", "N/A"),
                "created_time": getattr(import_obj, "created_time", "N/A"),
                "modified_time": getattr(import_obj, "modified_time", "N/A"),
            }
        except Exception:
            return {"raw": str(import_obj)}
