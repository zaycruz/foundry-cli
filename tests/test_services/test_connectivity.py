"""
Tests for connectivity service wrapper.
"""

import pytest
import uuid
from unittest.mock import Mock, patch
from types import SimpleNamespace

from pltr.services.connectivity import (
    ConnectivityService,
    EgressPolicyNotFoundError,
    EgressPolicyShapeError,
    WebhookNotFoundError,
)


class TestConnectivityService:
    """Test cases for ConnectivityService."""

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def setup_method(self, method, mock_client):
        """Set up test fixtures."""
        self.mock_client = mock_client
        self.service = ConnectivityService(profile="test")

    def test_init_with_profile(self):
        """Test service initialization with profile."""
        service = ConnectivityService(profile="test-profile")
        assert service.profile == "test-profile"

    def test_init_without_profile(self):
        """Test service initialization without profile."""
        service = ConnectivityService()
        assert service.profile is None

    def test_connections_service_with_connectivity_namespace(self):
        """Test connections_service with modern SDK client namespace."""
        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(connectivity="connectivity-client")

        assert service.connections_service == "connectivity-client"

    def test_connections_service_missing_namespace_raises(self):
        """Test connections_service raises when no supported namespace exists."""
        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace()

        with pytest.raises(RuntimeError, match="Connectivity service is not available"):
            _ = service.connections_service

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_service(self, mock_client):
        """Test _get_service returns client."""
        service = ConnectivityService(profile="test")
        result = service._get_service()
        assert result == mock_client

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_connections_service(self, mock_client):
        """Test connections_service property."""
        service = ConnectivityService(profile="test")
        result = service.connections_service
        assert result == mock_client.connections

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_file_imports_service(self, mock_client):
        """Test file_imports_service property."""
        service = ConnectivityService(profile="test")
        result = service.file_imports_service
        assert result == mock_client.connectivity.Connection.FileImport

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_table_imports_service(self, mock_client):
        """Test table_imports_service property."""
        service = ConnectivityService(profile="test")
        result = service.table_imports_service
        assert result == mock_client.connectivity.Connection.TableImport

    def test_list_connections_filesystem_fallback(self):
        """Test connection listing fallback when SDK list() is unavailable."""
        folder_child = Mock()
        folder_child.rid = "ri.compass.main.folder.abc"
        folder_child.type = "folder"

        connection_child = Mock()
        connection_child.rid = "ri.magritte.main.connection.123"
        connection_child.type = "connection"
        connection_child.display_name = "Warehouse Connection"
        connection_child.description = "Test connection"
        connection_child.status = "ACTIVE"
        connection_child.created_time = "2024-01-01T00:00:00Z"
        connection_child.modified_time = "2024-01-02T00:00:00Z"

        folder_client = Mock()
        folder_client.children.side_effect = [
            [folder_child, connection_child],
            [],
        ]

        connection_client = Mock(spec=["get"])
        connectivity = SimpleNamespace(Connection=connection_client)
        filesystem = SimpleNamespace(Folder=folder_client)

        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(
            connectivity=connectivity, filesystem=filesystem
        )

        result = service.list_connections()

        assert len(result) == 1
        assert result[0]["rid"] == "ri.magritte.main.connection.123"
        assert result[0]["display_name"] == "Warehouse Connection"
        assert result[0]["connection_type"] == "connection"
        folder_client.children.assert_any_call("ri.compass.main.folder.0", preview=True)

    def test_list_connections_filesystem_fallback_respects_env_start_folder(
        self, monkeypatch
    ):
        """Test filesystem fallback starts at env-configured folder RID."""
        monkeypatch.setenv(
            "PLTR_CONNECTIONS_FALLBACK_START_FOLDER_RID",
            "ri.compass.main.folder.custom-start",
        )

        folder_client = Mock()
        folder_client.children.return_value = []

        connection_client = Mock(spec=["get"])
        connectivity = SimpleNamespace(Connection=connection_client)
        filesystem = SimpleNamespace(Folder=folder_client)

        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(
            connectivity=connectivity, filesystem=filesystem
        )

        result = service.list_connections()

        assert result == []
        folder_client.children.assert_called_once_with(
            "ri.compass.main.folder.custom-start", preview=True
        )

    def test_list_connections_filesystem_fallback_requires_filesystem(self):
        """Test filesystem fallback raises when filesystem namespace is unavailable."""
        connection_client = Mock(spec=["get"])
        connectivity = SimpleNamespace(Connection=connection_client)

        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(connectivity=connectivity, filesystem=None)

        with pytest.raises(
            RuntimeError,
            match="Connection.list\\(\\) is unavailable and filesystem fallback is not supported",
        ):
            service.list_connections()

    def test_list_connections_filesystem_fallback_raises_on_scan_limit(self):
        """Test filesystem fallback raises when traversal exceeds folder scan cap."""
        folder_child = Mock()
        folder_child.rid = "ri.compass.main.folder.child"
        folder_child.type = "folder"

        folder_client = Mock()
        folder_client.children.return_value = [folder_child]

        connection_client = Mock(spec=["get"])
        connectivity = SimpleNamespace(Connection=connection_client)
        filesystem = SimpleNamespace(Folder=folder_client)

        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(
            connectivity=connectivity, filesystem=filesystem
        )
        service.MAX_FALLBACK_FOLDERS = 1

        with pytest.raises(
            RuntimeError, match="Connection discovery exceeded folder scan limit"
        ):
            service.list_connections()

    def test_list_connections_filesystem_fallback_raises_on_start_folder_error(self):
        """Test filesystem fallback raises when starting folder cannot be listed."""
        folder_client = Mock()
        folder_client.children.side_effect = Exception("Permission denied")

        connection_client = Mock(spec=["get"])
        connectivity = SimpleNamespace(Connection=connection_client)
        filesystem = SimpleNamespace(Folder=folder_client)

        service = ConnectivityService(profile="test")
        service._client = SimpleNamespace(
            connectivity=connectivity, filesystem=filesystem
        )

        with pytest.raises(RuntimeError, match="Unable to list fallback start folder"):
            service.list_connections()

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_connection_success(self, mock_client):
        """Test successful connection retrieval."""
        mock_connection = Mock()
        mock_connection.rid = "ri.conn.main.connection.123"
        mock_connection.display_name = "Test Connection"
        mock_connection.description = "Test Description"
        mock_connection.connection_type = "JDBC"
        mock_connection.status = "ACTIVE"

        mock_client.connections.Connection.get.return_value = mock_connection

        service = ConnectivityService(profile="test")
        result = service.get_connection("ri.conn.main.connection.123")

        assert result["rid"] == "ri.conn.main.connection.123"
        assert result["display_name"] == "Test Connection"
        mock_client.connections.Connection.get.assert_called_once_with(
            "ri.conn.main.connection.123"
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_connection_error(self, mock_client):
        """Test connection retrieval error handling."""
        mock_client.connections.Connection.get.side_effect = Exception("Not found")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to get connection"):
            service.get_connection("ri.conn.main.connection.123")

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_execute_file_import_success(self, mock_client):
        """Test successful file import execution."""
        mock_client.connectivity.Connection.FileImport.execute.return_value = (
            "ri.foundry.main.build.123"
        )

        service = ConnectivityService(profile="test")
        result = service.execute_file_import(
            "ri.conn.main.connection.123", "ri.import.main.file.123"
        )

        assert result == {"build_rid": "ri.foundry.main.build.123"}
        mock_client.connectivity.Connection.FileImport.execute.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            file_import_rid="ri.import.main.file.123",
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_execute_table_import_success(self, mock_client):
        """Test successful table import execution."""
        mock_client.connectivity.Connection.TableImport.execute.return_value = (
            "ri.foundry.main.build.456"
        )
        service = ConnectivityService(profile="test")
        result = service.execute_table_import(
            "ri.conn.main.connection.123", "ri.import.main.table.123"
        )

        assert result == {"build_rid": "ri.foundry.main.build.456"}
        mock_client.connectivity.Connection.TableImport.execute.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            table_import_rid="ri.import.main.table.123",
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_list_file_imports_success(self, mock_client):
        """Test successful file imports listing."""
        mock_import = Mock()
        mock_import.rid = "ri.import.main.file.123"
        mock_import.display_name = "Test Import"

        mock_client.connectivity.Connection.FileImport.list.return_value = [mock_import]

        service = ConnectivityService(profile="test")
        result = service.list_file_imports("ri.conn.main.connection.123")

        assert len(result) == 1
        assert result[0]["rid"] == "ri.import.main.file.123"
        mock_client.connectivity.Connection.FileImport.list.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123"
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_file_import_success(self, mock_client):
        """Test getting a file import with its parent connection RID."""
        mock_import = Mock()
        mock_import.rid = "ri.import.main.file.123"
        mock_client.connectivity.Connection.FileImport.get.return_value = mock_import

        service = ConnectivityService(profile="test")
        result = service.get_file_import(
            "ri.conn.main.connection.123", "ri.import.main.file.123"
        )

        assert result["rid"] == "ri.import.main.file.123"
        mock_client.connectivity.Connection.FileImport.get.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            file_import_rid="ri.import.main.file.123",
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_list_table_imports_success(self, mock_client):
        """Test listing table imports for a connection."""
        mock_import = Mock()
        mock_import.rid = "ri.import.main.table.123"
        mock_client.connectivity.Connection.TableImport.list.return_value = [
            mock_import
        ]

        service = ConnectivityService(profile="test")
        result = service.list_table_imports("ri.conn.main.connection.123")

        assert len(result) == 1
        assert result[0]["rid"] == "ri.import.main.table.123"
        mock_client.connectivity.Connection.TableImport.list.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123"
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_table_import_success(self, mock_client):
        """Test getting a table import with its parent connection RID."""
        mock_import = Mock()
        mock_import.rid = "ri.import.main.table.123"
        mock_client.connectivity.Connection.TableImport.get.return_value = mock_import

        service = ConnectivityService(profile="test")
        result = service.get_table_import(
            "ri.conn.main.connection.123", "ri.import.main.table.123"
        )

        assert result["rid"] == "ri.import.main.table.123"
        mock_client.connectivity.Connection.TableImport.get.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            table_import_rid="ri.import.main.table.123",
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_format_connection_info_complete(self, mock_client):
        """Test connection info formatting with complete data."""
        mock_connection = Mock()
        mock_connection.rid = "ri.conn.main.connection.123"
        mock_connection.display_name = "Test Connection"
        mock_connection.description = "Test Description"
        mock_connection.connection_type = "JDBC"
        mock_connection.status = "ACTIVE"
        mock_connection.created_time = "2023-01-01T00:00:00Z"
        mock_connection.modified_time = "2023-01-01T00:00:00Z"

        service = ConnectivityService(profile="test")
        result = service._format_connection_info(mock_connection)

        expected = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "Test Connection",
            "description": "Test Description",
            "connection_type": "JDBC",
            "status": "ACTIVE",
            "created_time": "2023-01-01T00:00:00Z",
            "modified_time": "2023-01-01T00:00:00Z",
        }
        assert result == expected

    @patch("pltr.services.connectivity.ConnectivityService.client")
    @patch("pltr.services.connectivity.getattr")
    def test_format_connection_info_error(self, mock_getattr, mock_client):
        """Test connection info formatting error fallback."""
        mock_connection = Mock()
        # Make getattr raise an exception
        mock_getattr.side_effect = Exception("Getattr failed")

        service = ConnectivityService(profile="test")
        result = service._format_connection_info(mock_connection)

        # Should fallback to raw format when exception occurs
        assert "raw" in result
        assert str(mock_connection) in result["raw"]

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_format_import_info_complete(self, mock_client):
        """Test import info formatting with complete data."""
        mock_import = Mock()
        mock_import.rid = "ri.import.main.file.123"
        mock_import.display_name = "Test Import"
        mock_import.connection_rid = "ri.conn.main.connection.123"
        mock_import.target_dataset_rid = "ri.foundry.main.dataset.456"
        mock_import.status = "CREATED"
        mock_import.import_type = "FILE"
        mock_import.source = "/path/to/file.csv"
        mock_import.created_time = "2023-01-01T00:00:00Z"
        mock_import.modified_time = "2023-01-01T00:00:00Z"

        service = ConnectivityService(profile="test")
        result = service._format_import_info(mock_import)

        expected = {
            "rid": "ri.import.main.file.123",
            "display_name": "Test Import",
            "connection_rid": "ri.conn.main.connection.123",
            "target_dataset_rid": "ri.foundry.main.dataset.456",
            "status": "CREATED",
            "import_type": "FILE",
            "source": "/path/to/file.csv",
            "created_time": "2023-01-01T00:00:00Z",
            "modified_time": "2023-01-01T00:00:00Z",
        }
        assert result == expected

    def test_looks_like_connection_resource_true_by_rid(self):
        """Test RID-based connection detection heuristic."""
        assert ConnectivityService._looks_like_connection_resource(
            "ri.magritte.main.connection.123", "dataset"
        )

    def test_looks_like_connection_resource_true_by_type(self):
        """Test type-based connection detection heuristic."""
        assert ConnectivityService._looks_like_connection_resource(
            "ri.compass.main.dataset.123", "connection"
        )

    def test_looks_like_connection_resource_false_for_folder(self):
        """Test non-connection resources are not misidentified."""
        assert not ConnectivityService._looks_like_connection_resource(
            "ri.compass.main.folder.123", "folder"
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_create_connection_success(self, mock_client):
        """Test successful connection creation."""
        mock_connection = Mock()
        mock_connection.rid = "ri.conn.main.connection.123"
        mock_connection.display_name = "New Connection"
        mock_connection.description = "Description"
        mock_connection.connection_type = "JDBC"
        mock_connection.status = "ACTIVE"
        mock_connection.created_time = "2023-01-01T00:00:00Z"
        mock_connection.modified_time = "2023-01-01T00:00:00Z"

        mock_client.connections.Connection.create.return_value = mock_connection

        service = ConnectivityService(profile="test")
        result = service.create_connection(
            display_name="New Connection",
            parent_folder_rid="ri.folder.main.123",
            configuration={"host": "localhost"},
            worker={"type": "direct"},
        )

        assert result["rid"] == "ri.conn.main.connection.123"
        assert result["display_name"] == "New Connection"
        mock_client.connections.Connection.create.assert_called_once_with(
            configuration={"host": "localhost"},
            display_name="New Connection",
            parent_folder_rid="ri.folder.main.123",
            worker={"type": "direct"},
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_create_connection_error(self, mock_client):
        """Test connection creation error handling."""
        mock_client.connections.Connection.create.side_effect = Exception(
            "Creation failed"
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to create connection"):
            service.create_connection(
                display_name="New Connection",
                parent_folder_rid="ri.folder.main.123",
                configuration={"host": "localhost"},
                worker={"type": "direct"},
            )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_connection_configuration_success(self, mock_client):
        """Test successful connection configuration retrieval."""
        mock_config = {"host": "localhost", "port": 5432}
        mock_client.connections.Connection.get_configuration.return_value = mock_config

        service = ConnectivityService(profile="test")
        result = service.get_connection_configuration("ri.conn.main.connection.123")

        assert result["connection_rid"] == "ri.conn.main.connection.123"
        assert result["configuration"] == mock_config
        mock_client.connections.Connection.get_configuration.assert_called_once_with(
            "ri.conn.main.connection.123"
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_get_connection_configuration_error(self, mock_client):
        """Test connection configuration retrieval error handling."""
        mock_client.connections.Connection.get_configuration.side_effect = Exception(
            "Not found"
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to get configuration"):
            service.get_connection_configuration("ri.conn.main.connection.123")

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_update_export_settings_success(self, mock_client):
        """Test successful export settings update."""
        mock_client.connections.Connection.update_export_settings.return_value = None

        service = ConnectivityService(profile="test")
        result = service.update_export_settings(
            "ri.conn.main.connection.123",
            {"exportsEnabled": True},
        )

        assert result["connection_rid"] == "ri.conn.main.connection.123"
        assert result["status"] == "export settings updated"
        mock_client.connections.Connection.update_export_settings.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            export_settings={"exportsEnabled": True},
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_update_export_settings_error(self, mock_client):
        """Test export settings update error handling."""
        mock_client.connections.Connection.update_export_settings.side_effect = (
            Exception("Update failed")
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to update export settings"):
            service.update_export_settings(
                "ri.conn.main.connection.123",
                {"exportsEnabled": True},
            )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_update_secrets_success(self, mock_client):
        """Test successful secrets update."""
        mock_client.connections.Connection.update_secrets.return_value = None

        service = ConnectivityService(profile="test")
        result = service.update_secrets(
            "ri.conn.main.connection.123",
            {"password": "newpass"},
        )

        assert result["connection_rid"] == "ri.conn.main.connection.123"
        assert result["status"] == "secrets updated"
        mock_client.connections.Connection.update_secrets.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123",
            secrets={"password": "newpass"},
        )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_update_secrets_error(self, mock_client):
        """Test secrets update error handling."""
        mock_client.connections.Connection.update_secrets.side_effect = Exception(
            "Update failed"
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to update secrets"):
            service.update_secrets(
                "ri.conn.main.connection.123",
                {"password": "newpass"},
            )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_upload_custom_jdbc_drivers_success(self, mock_client, tmp_path):
        """Test successful JDBC driver upload."""
        # Create a temporary JAR file
        jar_file = tmp_path / "driver.jar"
        jar_file.write_bytes(b"fake jar content")

        mock_connection = Mock()
        mock_connection.rid = "ri.conn.main.connection.123"
        mock_connection.display_name = "Test Connection"
        mock_connection.description = ""
        mock_connection.connection_type = "JDBC"
        mock_connection.status = "ACTIVE"
        mock_connection.created_time = "2023-01-01T00:00:00Z"
        mock_connection.modified_time = "2023-01-01T00:00:00Z"

        mock_client.connections.Connection.upload_custom_jdbc_drivers.return_value = (
            mock_connection
        )

        service = ConnectivityService(profile="test")
        result = service.upload_custom_jdbc_drivers(
            "ri.conn.main.connection.123",
            str(jar_file),
        )

        assert result["rid"] == "ri.conn.main.connection.123"
        mock_client.connections.Connection.upload_custom_jdbc_drivers.assert_called_once()

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_upload_custom_jdbc_drivers_file_not_found(self, mock_client):
        """Test JDBC driver upload with non-existent file."""
        service = ConnectivityService(profile="test")
        with pytest.raises(FileNotFoundError, match="File not found"):
            service.upload_custom_jdbc_drivers(
                "ri.conn.main.connection.123",
                "/nonexistent/path/driver.jar",
            )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_upload_custom_jdbc_drivers_invalid_extension(self, mock_client, tmp_path):
        """Test JDBC driver upload with non-JAR file."""
        # Create a temporary non-JAR file
        txt_file = tmp_path / "file.txt"
        txt_file.write_text("not a jar file")

        service = ConnectivityService(profile="test")
        with pytest.raises(ValueError, match="File must be a JAR file"):
            service.upload_custom_jdbc_drivers(
                "ri.conn.main.connection.123",
                str(txt_file),
            )

    @patch("pltr.services.connectivity.ConnectivityService.client")
    def test_upload_custom_jdbc_drivers_api_error(self, mock_client, tmp_path):
        """Test JDBC driver upload API error handling."""
        # Create a temporary JAR file
        jar_file = tmp_path / "driver.jar"
        jar_file.write_bytes(b"fake jar content")

        mock_client.connections.Connection.upload_custom_jdbc_drivers.side_effect = (
            Exception("Upload failed")
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to upload JDBC driver"):
            service.upload_custom_jdbc_drivers(
                "ri.conn.main.connection.123",
                str(jar_file),
            )


class TestWebhookRegistryReads:
    """Test cases for read-only webhook registry access."""

    WEBHOOK_RID = "ri.magritte..webhook.12345678-1234-1234-1234-123456789abc"

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_latest_success(self, mock_client_class):
        """Test fetching the latest webhook version."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {
            "webhookRid": self.WEBHOOK_RID,
            "version": 3,
            "apiName": "my-webhook",
        }
        mock_client.conjure.return_value = (200, payload, '{"webhookRid": "..."}')

        service = ConnectivityService(profile="test")
        result = service.get_webhook(self.WEBHOOK_RID)

        assert result == payload
        mock_client_class.assert_called_once_with("test")
        mock_client.conjure.assert_called_once_with(
            "GET", f"webhooks/api/registry/v0/{self.WEBHOOK_RID}/latest"
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_specific_version(self, mock_client_class):
        """Test fetching a pinned webhook version."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"webhookRid": self.WEBHOOK_RID, "version": 1}
        mock_client.conjure.return_value = (200, payload, "{}")

        service = ConnectivityService(profile="test")
        result = service.get_webhook(self.WEBHOOK_RID, version=1)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "GET", f"webhooks/api/registry/v0/{self.WEBHOOK_RID}/version/1"
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_empty_response_is_not_found(self, mock_client_class):
        """Test that an empty (HTTP 204) registry response fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (204, "", "")

        service = ConnectivityService(profile="test")
        with pytest.raises(WebhookNotFoundError, match="No webhook found"):
            service.get_webhook(self.WEBHOOK_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_route_not_mounted(self, mock_client_class):
        """Test a clear error when the webhooks API is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            '{"errorName": "Route:RouteNotMounted"}',
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.get_webhook(self.WEBHOOK_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_http_error(self, mock_client_class):
        """Test that non-2xx registry responses fail loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (500, "boom", "boom")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 500"):
            service.get_webhook(self.WEBHOOK_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_get_webhook_transport_error(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to read webhook"):
            service.get_webhook(self.WEBHOOK_RID)

    def test_get_webhook_without_profile_raises(self):
        """Test that a missing profile fails before any network call."""
        from pltr.auth.base import ProfileNotFoundError

        service = ConnectivityService()
        with patch(
            "pltr.config.profiles.ProfileManager.get_active_profile",
            return_value=None,
        ):
            with pytest.raises(ProfileNotFoundError, match="No profile specified"):
                service.get_webhook(self.WEBHOOK_RID)


class TestEgressPolicyEnsure:
    """Test cases for read-only network egress policy ensure."""

    HOSTNAME = "api.example.com"
    POLICY_RID = (
        "ri.resource-policy-manager.global.network-egress-policy."
        "00000000-0000-0000-0000-000000000026"
    )

    def _mock_client(self, mock_client_class, responses):
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = responses
        return mock_client

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_finds_matching_policy(self, mock_client_class):
        """Test that an existing policy covering the hostname is returned."""
        self._mock_client(
            mock_client_class,
            [
                (200, {self.POLICY_RID: None}, "{...}"),
                (
                    200,
                    {self.POLICY_RID: {"targets": [{"hostname": "api.example.com"}]}},
                    "{...}",
                ),
            ],
        )

        service = ConnectivityService(profile="test")
        result = service.ensure_egress_policy(self.HOSTNAME)

        assert result["policy_rid"] == self.POLICY_RID
        assert result["status"] == "exists"
        assert result["policy"] == {"targets": [{"hostname": "api.example.com"}]}

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_matches_hostname_case_insensitively(self, mock_client_class):
        """Test hostname matching is case-insensitive."""
        self._mock_client(
            mock_client_class,
            [
                (200, {self.POLICY_RID: None}, "{...}"),
                (200, {self.POLICY_RID: {"host": "API.Example.COM"}}, "{...}"),
            ],
        )

        service = ConnectivityService(profile="test")
        result = service.ensure_egress_policy(self.HOSTNAME)

        assert result["policy_rid"] == self.POLICY_RID

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_no_match_would_create(self, mock_client_class):
        """Test a missing match raises the loud 'would create' error."""
        self._mock_client(
            mock_client_class,
            [
                (200, {self.POLICY_RID: None}, "{...}"),
                (200, {self.POLICY_RID: {"host": "other.example.org"}}, "{...}"),
            ],
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(
            EgressPolicyNotFoundError, match="would be created, but mutations"
        ):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_no_policies_would_create(self, mock_client_class):
        """Test an empty policy inventory raises the 'would create' error."""
        self._mock_client(mock_client_class, [(200, {}, "{}")])

        service = ConnectivityService(profile="test")
        with pytest.raises(
            EgressPolicyNotFoundError, match="mutations are not enabled"
        ):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_skips_null_policy_details(self, mock_client_class):
        """Test that null policy detail entries do not crash matching."""
        self._mock_client(
            mock_client_class,
            [
                (200, {self.POLICY_RID: None}, "{...}"),
                (200, {self.POLICY_RID: None}, "{...}"),
            ],
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(EgressPolicyNotFoundError):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_list_unverified_shape(self, mock_client_class):
        """Test that a non-map get-all-policies response fails loudly."""
        self._mock_client(mock_client_class, [(200, ["not-a-map"], "[...]")])

        service = ConnectivityService(profile="test")
        with pytest.raises(EgressPolicyShapeError, match="Unverified"):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_batch_unverified_shape(self, mock_client_class):
        """Test that a non-map get-batch response fails loudly."""
        self._mock_client(
            mock_client_class,
            [
                (200, {self.POLICY_RID: None}, "{...}"),
                (200, "not-a-map", '"not-a-map"'),
            ],
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(EgressPolicyShapeError, match="Unverified"):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_route_not_mounted(self, mock_client_class):
        """Test a clear error when resource-policy-manager is not mounted."""
        self._mock_client(
            mock_client_class,
            [(404, {"errorName": "Route:RouteNotMounted"}, "{}")],
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_http_error(self, mock_client_class):
        """Test that non-2xx reads fail loudly."""
        self._mock_client(mock_client_class, [(500, "boom", "boom")])

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 500"):
            service.ensure_egress_policy(self.HOSTNAME)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_ensure_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("read timed out")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to list network egress"):
            service.ensure_egress_policy(self.HOSTNAME)

    def test_ensure_empty_hostname_rejected(self):
        """Test that an empty hostname fails before any network call."""
        service = ConnectivityService(profile="test")
        with pytest.raises(ValueError, match="hostname is required"):
            service.ensure_egress_policy("  ")


from pltr.services.connectivity import WebhookShapeError  # noqa: E402

SOURCE_RID = "ri.magritte..source.00000000-0000-0000-0000-000000000021"


class TestWebhookWriteService:
    """Test cases for webhook create (verified body) and update plan."""

    def test_build_create_webhook_body_minimal(self):
        """Test the verified create body shape with the default spec."""
        service = ConnectivityService(profile="test")
        body = service.build_create_webhook_body(
            "my-webhook", "MyWebhook", "desc", SOURCE_RID
        )

        assert body["name"] == "my-webhook"
        assert body["apiName"] == "MyWebhook"
        assert body["description"] == "desc"
        assert body["spec"]["config"] == {
            "type": "magritteRestWebhook",
            "magritteRestWebhook": {"sourceRid": SOURCE_RID, "calls": []},
        }
        assert body["spec"]["inputs"] == []
        assert body["spec"]["outputs"] == []
        assert body["spec"]["storagePolicy"] == {}
        # The 2026-07-25 capture shows the MCP sending executionPolicy: {}.
        assert body["executionPolicy"] == {}

    def test_build_create_webhook_body_spec_override(self):
        """Test that a caller-supplied spec replaces the default."""
        service = ConnectivityService(profile="test")
        override = {"config": {"type": "custom"}, "inputs": []}
        body = service.build_create_webhook_body(
            "my-webhook", "MyWebhook", "desc", SOURCE_RID, override
        )

        assert body["spec"] == override

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_webhook_success(self, mock_client_class):
        """Test creating a webhook returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"metadata": {"rid": "ri.webhooks.main.webhook.abc"}}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = ConnectivityService(profile="test")
        result = service.create_webhook("my-webhook", "MyWebhook", "desc", SOURCE_RID)

        assert result == payload
        args, kwargs = mock_client.conjure.call_args
        assert args[0] == "POST"
        assert args[1] == "webhooks/api/registry/v0"
        assert (
            kwargs["json_body"]["spec"]["config"]["magritteRestWebhook"]["sourceRid"]
            == SOURCE_RID
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_webhook_permission_denied_is_loud(self, mock_client_class):
        """Test the verified 403 permission boundary surfaces loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Compass:InsufficientPermissions"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.create_webhook("my-webhook", "MyWebhook", "desc", SOURCE_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_webhook_route_not_mounted(self, mock_client_class):
        """Test a clear error when the webhooks API is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.create_webhook("my-webhook", "MyWebhook", "desc", SOURCE_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_webhook_empty_2xx_fails_loudly(self, mock_client_class):
        """Test that an empty success payload is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "")

        service = ConnectivityService(profile="test")
        with pytest.raises(WebhookShapeError, match="Unverified"):
            service.create_webhook("my-webhook", "MyWebhook", "desc", SOURCE_RID)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_webhook_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to create webhook"):
            service.create_webhook("my-webhook", "MyWebhook", "desc", SOURCE_RID)

    def test_plan_update_webhook_no_network(self):
        """Test the update plan describes the request without a client."""
        service = ConnectivityService(profile="test")
        plan = service.plan_update_webhook(
            "ri.webhooks.main.webhook.abc", {"inputs": []}
        )

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "POST"
        assert plan["request"]["path"] == (
            "/webhooks/api/registry/v0/ri.webhooks.main.webhook.abc"
        )
        assert plan["request"]["body"] == {"spec": {"inputs": []}}
        assert "VERIFIED" in plan["contract"]

    def test_plan_create_rest_source_no_network(self):
        """Test the rest-source plan matches the verified v3 envelope."""
        service = ConnectivityService(profile="test")
        plan = service.plan_create_rest_source(
            "my-source",
            "example.invalid",
            "HTTPS",
            443,
            "ri.compass.main.folder.abc",
            ["ri.resource-policy-manager.global.network-egress-policy.abc"],
        )

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "POST"
        assert plan["request"]["path"].endswith("/source-store/source/v3")
        body = plan["request"]["body"]
        domain = body["config"]["source"]["config"]["domains"][0]
        assert domain["host"] == "example.invalid"
        assert domain["scheme"] == "HTTPS"
        assert domain["port"] == 443
        assert body["description"] == {"name": "my-source", "description": ""}
        assert body["runtimePlatformRequest"] == {
            "cloud": {
                "networkEgresses": [
                    "ri.resource-policy-manager.global.network-egress-policy.abc"
                ]
            },
            "type": "cloud",
        }
        assert body["parentRid"] == "ri.compass.main.folder.abc"
        assert "VERIFIED" in plan["contract"]


EGRESS_POLICY_RID = (
    "ri.resource-policy-manager.global.network-egress-policy."
    "00000000-0000-0000-0000-000000000027"
)
PARENT_FOLDER_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000004"
WEBHOOK_RID = "ri.webhooks.main.webhook.00000000-0000-0000-0000-000000000011"
DOMAIN_ID = "00000000-0000-0000-0000-000000000028"


class TestWebhookSpecAssembly:
    """Test cases for the captured MCP spec-assembly transform."""

    def test_build_call_query_params_v2_extra_array_wrap(self):
        """httpQueryParams values land in queryParamsV2 with an extra wrap."""
        call = ConnectivityService.build_magritte_rest_call(
            {
                "httpMethod": "GET",
                "httpPath": ["multipass/api/users", {"input": "userId"}],
                "httpQueryParams": {"realm": [{"input": "realm"}]},
            },
            DOMAIN_ID,
        )

        basic = call["call"]["basic"]
        # Captured quirk: the value gets an EXTRA array wrap.
        assert basic["queryParamsV2"] == {
            "realm": [[{"input": {"name": "realm"}, "type": "input"}]]
        }
        assert basic["queryParams"] == {}

    def test_build_call_headers_not_wrapped(self):
        """Headers keep a single array -- no extra wrap."""
        call = ConnectivityService.build_magritte_rest_call(
            {
                "httpMethod": "GET",
                "httpPath": [],
                "headers": {"x-parity-probe": [{"static": "v2"}]},
            },
            DOMAIN_ID,
        )

        basic = call["call"]["basic"]
        assert basic["headers"] == {
            "x-parity-probe": [{"static": "v2", "type": "static"}]
        }

    def test_build_call_wire_shape(self):
        """Method/path union shapes, fresh callId, safe-method flag."""
        call = ConnectivityService.build_magritte_rest_call(
            {
                "httpMethod": "get",
                "httpPath": ["multipass/api/users", {"input": "userId"}],
            },
            DOMAIN_ID,
        )

        uuid.UUID(call["callId"])  # raises unless a valid UUID
        assert call["call"]["type"] == "basic"
        basic = call["call"]["basic"]
        assert basic["domainId"] == DOMAIN_ID
        assert basic["method"] == {"static": "GET", "type": "static"}
        assert basic["path"] == [
            {"static": "multipass/api/users", "type": "static"},
            {"input": {"name": "userId"}, "type": "input"},
        ]
        assert basic["isHttpMethodSafe"] is True

    def test_build_call_unsafe_method_flag(self):
        """Non-safe HTTP methods set isHttpMethodSafe to False."""
        call = ConnectivityService.build_magritte_rest_call(
            {"httpMethod": "POST", "httpPath": []}, DOMAIN_ID
        )

        assert call["call"]["basic"]["isHttpMethodSafe"] is False

    def test_build_call_unique_call_ids(self):
        """Each assembled call gets a fresh client-generated callId."""
        first = ConnectivityService.build_magritte_rest_call({}, DOMAIN_ID)
        second = ConnectivityService.build_magritte_rest_call({}, DOMAIN_ID)

        assert first["callId"] != second["callId"]

    def test_build_call_bad_segment_fails_loudly(self):
        """Unrecognized segments raise a shape error instead of guessing."""
        with pytest.raises(WebhookShapeError, match="Unrecognized webhook segment"):
            ConnectivityService.build_magritte_rest_call(
                {"httpPath": [{"bogus": "x"}]}, DOMAIN_ID
            )

    def test_build_webhook_spec_with_calls_and_inputs(self):
        """Full spec assembly matches the captured update spec shape."""
        spec = ConnectivityService.build_webhook_spec(
            SOURCE_RID,
            domain_id=DOMAIN_ID,
            calls=[
                {
                    "httpMethod": "GET",
                    "httpPath": ["multipass/api/users", {"input": "userId"}],
                    "headers": {"x-parity-probe": [{"static": "v2"}]},
                    "httpQueryParams": {"realm": [{"input": "realm"}]},
                }
            ],
            inputs=[
                {
                    "name": "userId",
                    "dataType": {"type": "string"},
                    "description": "User id to look up",
                },
                {"name": "realm", "dataType": {"type": "string"}},
            ],
        )

        assert spec["config"] == {
            "type": "magritteRestWebhook",
            "magritteRestWebhook": {
                "sourceRid": SOURCE_RID,
                "calls": spec["config"]["magritteRestWebhook"]["calls"],
            },
        }
        calls = spec["config"]["magritteRestWebhook"]["calls"]
        assert len(calls) == 1
        basic = calls[0]["call"]["basic"]
        assert basic["queryParamsV2"] == {
            "realm": [[{"input": {"name": "realm"}, "type": "input"}]]
        }
        assert spec["inputs"] == [
            {
                "name": "userId",
                "dataType": {"string": {}, "type": "string"},
                "description": "User id to look up",
            },
            {
                "name": "realm",
                "dataType": {"string": {}, "type": "string"},
                "description": "",
            },
        ]
        assert spec["outputs"] == []
        assert spec["storagePolicy"] == {}

    def test_normalize_data_type_passthrough_union_shape(self):
        """An already union-shaped dataType passes through unchanged."""
        union = {"string": {}, "type": "string"}
        assert ConnectivityService._normalize_data_type(union) == union

    def test_normalize_data_type_missing_type_fails_loudly(self):
        """A dataType without a type key raises a shape error."""
        with pytest.raises(WebhookShapeError, match="dataType"):
            ConnectivityService._normalize_data_type({"string": {}})


class TestWebhookUpdateService:
    """Test cases for the real publishWebhookVersion write."""

    SPEC = {
        "config": {
            "type": "magritteRestWebhook",
            "magritteRestWebhook": {"sourceRid": SOURCE_RID, "calls": []},
        },
        "inputs": [],
        "outputs": [],
        "storagePolicy": {},
    }

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_update_webhook_success(self, mock_client_class):
        """Test publish sends {spec} only and returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"webhookRid": WEBHOOK_RID, "version": 2}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = ConnectivityService(profile="test")
        result = service.update_webhook(WEBHOOK_RID, self.SPEC)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "POST",
            f"webhooks/api/registry/v0/{WEBHOOK_RID}",
            json_body={"spec": self.SPEC},
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_update_webhook_permission_denied_is_loud(self, mock_client_class):
        """Test a resource-scoped 403 surfaces loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Compass:InsufficientPermissions"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.update_webhook(WEBHOOK_RID, self.SPEC)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_update_webhook_route_not_mounted(self, mock_client_class):
        """Test a clear error when the webhooks API is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.update_webhook(WEBHOOK_RID, self.SPEC)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_update_webhook_empty_2xx_fails_loudly(self, mock_client_class):
        """Test that an empty success payload is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "")

        service = ConnectivityService(profile="test")
        with pytest.raises(WebhookShapeError, match="Unexpected webhook update"):
            service.update_webhook(WEBHOOK_RID, self.SPEC)

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_update_webhook_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to update webhook"):
            service.update_webhook(WEBHOOK_RID, self.SPEC)


class TestResolveSourceDomainId:
    """Test cases for the domain host -> domainId config lookup."""

    CONFIG = {
        "config": {
            "source": {
                "type": "webhooks-rest",
                "config": {
                    "domains": [
                        {
                            "host": "example.invalid",
                            "scheme": "HTTPS",
                            "domainId": DOMAIN_ID,
                            "port": 443,
                        }
                    ]
                },
            }
        }
    }

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_resolve_matches_host(self, mock_client_class):
        """Test the full-RID config GET maps host to domainId."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, self.CONFIG, "{...}")

        service = ConnectivityService(profile="test")
        result = service.resolve_source_domain_id(SOURCE_RID, "example.invalid")

        assert result == DOMAIN_ID
        mock_client.conjure.assert_called_once_with(
            "GET",
            f"magritte-coordinator/api/source-store/source/{SOURCE_RID}/config",
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_resolve_matches_host_case_insensitively(self, mock_client_class):
        """Test host matching is case-insensitive."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, self.CONFIG, "{...}")

        service = ConnectivityService(profile="test")
        assert (
            service.resolve_source_domain_id(SOURCE_RID, "Example.INVALID") == DOMAIN_ID
        )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_resolve_no_match_lists_available_hosts(self, mock_client_class):
        """Test a missing host fails loudly with the available hosts."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, self.CONFIG, "{...}")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="example.invalid"):
            service.resolve_source_domain_id(SOURCE_RID, "other.invalid")

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_resolve_http_error_is_loud(self, mock_client_class):
        """Test a non-2xx config read fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            400,
            {"errorName": "Default:InvalidArgument"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 400"):
            service.resolve_source_domain_id(SOURCE_RID, "example.invalid")

    def test_resolve_empty_host_rejected(self):
        """Test that an empty host fails before any network call."""
        service = ConnectivityService(profile="test")
        with pytest.raises(ValueError, match="host is required"):
            service.resolve_source_domain_id(SOURCE_RID, "  ")


class TestRestSourceCreateService:
    """Test cases for the real addSourceV3 create."""

    def test_build_body_matches_captured_envelope(self):
        """Test the body shape, uppercase scheme, and random domainId."""
        service = ConnectivityService(profile="test")
        body = service.build_create_rest_source_body(
            "my-source",
            "example.invalid",
            "https",
            443,
            PARENT_FOLDER_RID,
            [EGRESS_POLICY_RID],
            "desc",
        )

        assert body["config"]["source"]["type"] == "webhooks-rest"
        domain = body["config"]["source"]["config"]["domains"][0]
        assert domain["host"] == "example.invalid"
        assert domain["scheme"] == "HTTPS"
        assert domain["port"] == 443
        uuid.UUID(domain["domainId"])  # random UUID per call
        assert body["description"] == {"name": "my-source", "description": "desc"}
        assert body["runtimePlatformRequest"] == {
            "cloud": {"networkEgresses": [EGRESS_POLICY_RID]},
            "type": "cloud",
        }
        assert body["parentRid"] == PARENT_FOLDER_RID

    def test_build_body_random_domain_id_per_call(self):
        """Test domainId is a fresh random UUID, not a fixed constant."""
        service = ConnectivityService(profile="test")
        first = service.build_create_rest_source_body(
            "a", "example.invalid", "HTTPS", 443, PARENT_FOLDER_RID, []
        )
        second = service.build_create_rest_source_body(
            "a", "example.invalid", "HTTPS", 443, PARENT_FOLDER_RID, []
        )

        first_id = first["config"]["source"]["config"]["domains"][0]["domainId"]
        second_id = second["config"]["source"]["config"]["domains"][0]["domainId"]
        assert first_id != second_id

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_rest_source_bare_string_response(self, mock_client_class):
        """Test the bare-string source RID response is unwrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        source_rid = "ri.magritte..source.00000000-0000-0000-0000-000000000023"
        mock_client.conjure.return_value = (200, source_rid, f'"{source_rid}"')

        service = ConnectivityService(profile="test")
        result = service.create_rest_source(
            "my-source",
            "example.invalid",
            "HTTPS",
            443,
            PARENT_FOLDER_RID,
            [EGRESS_POLICY_RID],
        )

        assert result["source_rid"] == source_rid
        assert result["status"] == "created"
        assert source_rid in result["setup_path"]
        args, kwargs = mock_client.conjure.call_args
        assert args[0] == "POST"
        assert args[1] == "magritte-coordinator/api/source-store/source/v3"
        assert kwargs["json_body"]["parentRid"] == PARENT_FOLDER_RID

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_rest_source_object_response_fails_loudly(self, mock_client_class):
        """Test that a non-bare-string 2xx payload is a shape error."""
        from pltr.services.connectivity import RestSourceShapeError

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"rid": "x"}, "{...}")

        service = ConnectivityService(profile="test")
        with pytest.raises(RestSourceShapeError, match="bare-string"):
            service.create_rest_source(
                "my-source",
                "example.invalid",
                "HTTPS",
                443,
                PARENT_FOLDER_RID,
                [EGRESS_POLICY_RID],
            )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_rest_source_permission_denied_is_loud(self, mock_client_class):
        """Test a magritte:write-resource 403 surfaces loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Default:PermissionDenied"},
            "{}",
        )

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="magritte:write-resource"):
            service.create_rest_source(
                "my-source",
                "example.invalid",
                "HTTPS",
                443,
                PARENT_FOLDER_RID,
                [EGRESS_POLICY_RID],
            )

    @patch("pltr.services.connectivity.FoundryInternalClient")
    def test_create_rest_source_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = ConnectivityService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to create REST source"):
            service.create_rest_source(
                "my-source",
                "example.invalid",
                "HTTPS",
                443,
                PARENT_FOLDER_RID,
                [EGRESS_POLICY_RID],
            )
