"""
Tests for connectivity commands.
"""

import json
from unittest.mock import Mock, patch
from typer.testing import CliRunner

from foundry_cli.commands.connectivity import app
from foundry_cli.auth.base import ProfileNotFoundError


class TestConnectivityCommands:
    """Test cases for connectivity commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_connections_success(self, mock_service_class):
        """Test successful connection listing command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_connections.return_value = [
            {
                "rid": "ri.conn.main.connection.123",
                "display_name": "Test Connection",
                "connection_type": "JDBC",
                "status": "ACTIVE",
            }
        ]

        result = self.runner.invoke(app, ["connection", "list"])

        assert result.exit_code == 0
        mock_service.list_connections.assert_called_once()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_connections_empty(self, mock_service_class):
        """Test connection listing with no results."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_connections.return_value = []

        result = self.runner.invoke(app, ["connection", "list"])

        assert result.exit_code == 0
        assert "No connections found" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_connections_with_profile(self, mock_service_class):
        """Test connection listing with specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_connections.return_value = []

        result = self.runner.invoke(app, ["connection", "list", "--profile", "test"])

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_connections_auth_error(self, mock_service_class):
        """Test connection listing with authentication error."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_connections.side_effect = ProfileNotFoundError(
            "Profile not found"
        )

        result = self.runner.invoke(app, ["connection", "list"])

        assert result.exit_code == 1
        assert "Authentication error" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_connections_general_error(self, mock_service_class):
        """Test connection listing with general error."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_connections.side_effect = Exception("API Error")

        result = self.runner.invoke(app, ["connection", "list"])

        assert result.exit_code == 1
        assert "Error listing connections" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_connection_success(self, mock_service_class):
        """Test successful connection get command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_connection.return_value = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "Test Connection",
            "connection_type": "JDBC",
            "status": "ACTIVE",
        }

        result = self.runner.invoke(
            app, ["connection", "get", "ri.conn.main.connection.123"]
        )

        assert result.exit_code == 0
        mock_service.get_connection.assert_called_once_with(
            "ri.conn.main.connection.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_connection_error(self, mock_service_class):
        """Test connection get with error."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_connection.side_effect = Exception("Connection not found")

        result = self.runner.invoke(
            app, ["connection", "get", "ri.conn.main.connection.123"]
        )

        assert result.exit_code == 1
        assert "Error getting connection" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_file_imports_success(self, mock_service_class):
        """Test successful file imports listing command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_file_imports.return_value = [
            {
                "rid": "ri.import.main.file.123",
                "display_name": "Test Import",
                "status": "CREATED",
            }
        ]

        result = self.runner.invoke(
            app, ["import", "list-file", "--connection", "ri.conn.main.connection.123"]
        )

        assert result.exit_code == 0
        mock_service.list_file_imports.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_file_imports_empty(self, mock_service_class):
        """Test file imports listing with no results."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_file_imports.return_value = []

        result = self.runner.invoke(
            app, ["import", "list-file", "--connection", "ri.conn.main.connection.123"]
        )

        assert result.exit_code == 0
        assert "No file imports found" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_list_table_imports_success(self, mock_service_class):
        """Test successful table imports listing command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_table_imports.return_value = [
            {
                "rid": "ri.import.main.table.123",
                "display_name": "Test Table Import",
                "status": "CREATED",
            }
        ]

        result = self.runner.invoke(
            app, ["import", "list-table", "--connection", "ri.conn.main.connection.123"]
        )

        assert result.exit_code == 0
        mock_service.list_table_imports.assert_called_once_with(
            connection_rid="ri.conn.main.connection.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_file_import_success(self, mock_service_class):
        """Test successful file import get command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_file_import.return_value = {
            "rid": "ri.import.main.file.123",
            "display_name": "Test Import",
            "status": "CREATED",
        }

        result = self.runner.invoke(
            app,
            [
                "import",
                "get-file",
                "ri.import.main.file.123",
                "--connection",
                "ri.conn.main.connection.123",
            ],
        )

        assert result.exit_code == 0
        mock_service.get_file_import.assert_called_once_with(
            "ri.conn.main.connection.123", "ri.import.main.file.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_table_import_success(self, mock_service_class):
        """Test successful table import get command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_table_import.return_value = {
            "rid": "ri.import.main.table.123",
            "display_name": "Test Table Import",
            "status": "CREATED",
        }

        result = self.runner.invoke(
            app,
            [
                "import",
                "get-table",
                "ri.import.main.table.123",
                "--connection",
                "ri.conn.main.connection.123",
            ],
        )

        assert result.exit_code == 0
        mock_service.get_table_import.assert_called_once_with(
            "ri.conn.main.connection.123", "ri.import.main.table.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_connection_success(self, mock_service_class):
        """Test successful connection creation command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_connection.return_value = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "New Connection",
            "connection_type": "JDBC",
            "status": "ACTIVE",
        }

        result = self.runner.invoke(
            app,
            [
                "connection",
                "create",
                "New Connection",
                "ri.folder.main.123",
                '{"host": "localhost"}',
                '{"type": "direct"}',
            ],
        )

        assert result.exit_code == 0
        assert "Connection created" in result.stdout
        mock_service.create_connection.assert_called_once_with(
            display_name="New Connection",
            parent_folder_rid="ri.folder.main.123",
            configuration={"host": "localhost"},
            worker={"type": "direct"},
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_connection_with_config_file(self, mock_service_class, tmp_path):
        """Test connection creation with config files."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_connection.return_value = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "New Connection",
        }

        # Create temp config files
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "localhost", "port": 5432}')
        worker_file = tmp_path / "worker.json"
        worker_file.write_text('{"type": "direct"}')

        result = self.runner.invoke(
            app,
            [
                "connection",
                "create",
                "New Connection",
                "ri.folder.main.123",
                "--config-file",
                str(config_file),
                "--worker-file",
                str(worker_file),
            ],
        )

        assert result.exit_code == 0
        mock_service.create_connection.assert_called_once()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_connection_invalid_json(self, mock_service_class):
        """Test connection creation with invalid JSON."""
        result = self.runner.invoke(
            app,
            [
                "connection",
                "create",
                "New Connection",
                "ri.folder.main.123",
                "invalid-json",
                '{"type": "direct"}',
            ],
        )

        assert result.exit_code == 1
        assert "Invalid JSON" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_connection_error(self, mock_service_class):
        """Test connection creation error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_connection.side_effect = Exception("Creation failed")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "create",
                "New Connection",
                "ri.folder.main.123",
                '{"host": "localhost"}',
                '{"type": "direct"}',
            ],
        )

        assert result.exit_code == 1
        assert "Error creating connection" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_connection_configuration_success(self, mock_service_class):
        """Test successful connection configuration retrieval command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_connection_configuration.return_value = {
            "connection_rid": "ri.conn.main.connection.123",
            "configuration": {"host": "localhost", "port": 5432},
        }

        result = self.runner.invoke(
            app,
            ["connection", "get-config", "ri.conn.main.connection.123"],
        )

        assert result.exit_code == 0
        mock_service.get_connection_configuration.assert_called_once_with(
            "ri.conn.main.connection.123"
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_connection_configuration_error(self, mock_service_class):
        """Test connection configuration retrieval error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_connection_configuration.side_effect = Exception("Not found")

        result = self.runner.invoke(
            app,
            ["connection", "get-config", "ri.conn.main.connection.123"],
        )

        assert result.exit_code == 1
        assert "Error getting connection configuration" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_connection_secrets_success(self, mock_service_class, tmp_path):
        """Test successful connection secrets update command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_secrets.return_value = {
            "connection_rid": "ri.conn.main.connection.123",
            "status": "secrets updated",
        }

        # Create temp secrets file
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text('{"password": "newpass"}')

        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-secrets",
                "ri.conn.main.connection.123",
                "--secrets-file",
                str(secrets_file),
            ],
        )

        assert result.exit_code == 0
        assert "Secrets updated" in result.stdout
        mock_service.update_secrets.assert_called_once_with(
            "ri.conn.main.connection.123",
            {"password": "newpass"},
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_connection_secrets_file_not_found(self, mock_service_class):
        """Test secrets update with non-existent file."""
        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-secrets",
                "ri.conn.main.connection.123",
                "--secrets-file",
                "/nonexistent/secrets.json",
            ],
        )

        assert result.exit_code == 1
        assert "Secrets file not found" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_connection_secrets_invalid_json(self, mock_service_class, tmp_path):
        """Test secrets update with invalid JSON."""
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text("invalid-json")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-secrets",
                "ri.conn.main.connection.123",
                "--secrets-file",
                str(secrets_file),
            ],
        )

        assert result.exit_code == 1
        assert "Invalid JSON" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_export_settings_success(self, mock_service_class):
        """Test successful export settings update command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_export_settings.return_value = {
            "connection_rid": "ri.conn.main.connection.123",
            "status": "export settings updated",
        }

        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-export-settings",
                "ri.conn.main.connection.123",
                '{"exportsEnabled": true}',
            ],
        )

        assert result.exit_code == 0
        assert "Export settings updated" in result.stdout
        mock_service.update_export_settings.assert_called_once_with(
            "ri.conn.main.connection.123",
            {"exportsEnabled": True},
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_export_settings_with_file(self, mock_service_class, tmp_path):
        """Test export settings update with file."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_export_settings.return_value = {
            "connection_rid": "ri.conn.main.connection.123",
            "status": "export settings updated",
        }

        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"exportsEnabled": true}')

        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-export-settings",
                "ri.conn.main.connection.123",
                "--settings-file",
                str(settings_file),
            ],
        )

        assert result.exit_code == 0
        mock_service.update_export_settings.assert_called_once()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_export_settings_error(self, mock_service_class):
        """Test export settings update error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_export_settings.side_effect = Exception("Update failed")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "update-export-settings",
                "ri.conn.main.connection.123",
                '{"exportsEnabled": true}',
            ],
        )

        assert result.exit_code == 1
        assert "Error updating export settings" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_upload_jdbc_drivers_success(self, mock_service_class, tmp_path):
        """Test successful JDBC driver upload command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.upload_custom_jdbc_drivers.return_value = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "Test Connection",
        }

        # Create temp JAR file
        jar_file = tmp_path / "driver.jar"
        jar_file.write_bytes(b"fake jar content")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "upload-jdbc-drivers",
                "ri.conn.main.connection.123",
                str(jar_file),
            ],
        )

        assert result.exit_code == 0
        assert "Uploaded" in result.stdout
        mock_service.upload_custom_jdbc_drivers.assert_called_once()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_upload_jdbc_drivers_file_not_found(self, mock_service_class):
        """Test JDBC driver upload with non-existent file."""
        result = self.runner.invoke(
            app,
            [
                "connection",
                "upload-jdbc-drivers",
                "ri.conn.main.connection.123",
                "/nonexistent/driver.jar",
            ],
        )

        assert result.exit_code == 1
        assert "File not found" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_upload_jdbc_drivers_invalid_extension(self, mock_service_class, tmp_path):
        """Test JDBC driver upload with non-JAR file."""
        txt_file = tmp_path / "file.txt"
        txt_file.write_text("not a jar")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "upload-jdbc-drivers",
                "ri.conn.main.connection.123",
                str(txt_file),
            ],
        )

        assert result.exit_code == 1
        assert "must be a JAR file" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_upload_jdbc_drivers_multiple_files(self, mock_service_class, tmp_path):
        """Test JDBC driver upload with multiple files."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.upload_custom_jdbc_drivers.return_value = {
            "rid": "ri.conn.main.connection.123",
            "display_name": "Test Connection",
        }

        # Create temp JAR files
        jar_file1 = tmp_path / "driver1.jar"
        jar_file1.write_bytes(b"fake jar content 1")
        jar_file2 = tmp_path / "driver2.jar"
        jar_file2.write_bytes(b"fake jar content 2")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "upload-jdbc-drivers",
                "ri.conn.main.connection.123",
                str(jar_file1),
                str(jar_file2),
            ],
        )

        assert result.exit_code == 0
        assert mock_service.upload_custom_jdbc_drivers.call_count == 2

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_upload_jdbc_drivers_error(self, mock_service_class, tmp_path):
        """Test JDBC driver upload error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.upload_custom_jdbc_drivers.side_effect = Exception("Upload failed")

        jar_file = tmp_path / "driver.jar"
        jar_file.write_bytes(b"fake jar content")

        result = self.runner.invoke(
            app,
            [
                "connection",
                "upload-jdbc-drivers",
                "ri.conn.main.connection.123",
                str(jar_file),
            ],
        )

        assert result.exit_code == 1
        assert "Error uploading JDBC drivers" in result.stdout


class TestWebhookCommands:
    """Test cases for read-only webhook inspection commands."""

    WEBHOOK_RID = "ri.magritte..webhook.12345678-1234-1234-1234-123456789abc"

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_success(self, mock_service_class):
        """Test successful webhook get command."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.return_value = {
            "webhookRid": self.WEBHOOK_RID,
            "version": 3,
            "apiName": "my-webhook",
        }

        result = self.runner.invoke(app, ["webhook", "get", self.WEBHOOK_RID])

        assert result.exit_code == 0
        mock_service.get_webhook.assert_called_once_with(self.WEBHOOK_RID, version=None)

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_with_version(self, mock_service_class):
        """Test webhook get with a pinned version."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.return_value = {
            "webhookRid": self.WEBHOOK_RID,
            "version": 1,
        }

        result = self.runner.invoke(
            app, ["webhook", "get", self.WEBHOOK_RID, "--version", "1"]
        )

        assert result.exit_code == 0
        mock_service.get_webhook.assert_called_once_with(self.WEBHOOK_RID, version=1)

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_json_format(self, mock_service_class):
        """Test webhook get with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.return_value = {
            "webhookRid": self.WEBHOOK_RID,
            "version": 3,
        }

        result = self.runner.invoke(
            app, ["webhook", "get", self.WEBHOOK_RID, "--format", "json"]
        )

        assert result.exit_code == 0
        assert self.WEBHOOK_RID in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_not_found(self, mock_service_class):
        """Test webhook get when the registry has no webhook for the RID."""
        from foundry_cli.services.connectivity import WebhookNotFoundError

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.side_effect = WebhookNotFoundError(
            f"No webhook found for RID {self.WEBHOOK_RID}"
        )

        result = self.runner.invoke(app, ["webhook", "get", self.WEBHOOK_RID])

        assert result.exit_code == 1
        assert "No webhook found" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_error(self, mock_service_class):
        """Test webhook get error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.side_effect = Exception("registry unreachable")

        result = self.runner.invoke(app, ["webhook", "get", self.WEBHOOK_RID])

        assert result.exit_code == 1
        assert "Error getting webhook" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_get_webhook_with_profile(self, mock_service_class):
        """Test webhook get with a specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_webhook.return_value = {"webhookRid": self.WEBHOOK_RID}

        result = self.runner.invoke(
            app, ["webhook", "get", self.WEBHOOK_RID, "--profile", "test"]
        )

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")


class TestEgressCommands:
    """Test cases for read-only network egress commands."""

    HOSTNAME = "api.example.com"
    POLICY_RID = (
        "ri.resource-policy-manager.global.network-egress-policy."
        "00000000-0000-0000-0000-000000000026"
    )

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_match(self, mock_service_class):
        """Test ensure when a matching policy exists."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.return_value = {
            "policy_rid": self.POLICY_RID,
            "hostname": self.HOSTNAME,
            "status": "exists",
            "policy": {"targets": [{"hostname": self.HOSTNAME}]},
        }

        result = self.runner.invoke(app, ["egress", "ensure", self.HOSTNAME])

        assert result.exit_code == 0
        mock_service.ensure_egress_policy.assert_called_once_with(self.HOSTNAME)

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_match_json(self, mock_service_class):
        """Test ensure with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.return_value = {
            "policy_rid": self.POLICY_RID,
            "hostname": self.HOSTNAME,
            "status": "exists",
            "policy": {},
        }

        result = self.runner.invoke(
            app, ["egress", "ensure", self.HOSTNAME, "--format", "json"]
        )

        assert result.exit_code == 0
        assert self.POLICY_RID in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_would_create(self, mock_service_class):
        """Test ensure exits loudly when no policy matches."""
        from foundry_cli.services.connectivity import EgressPolicyNotFoundError

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.side_effect = EgressPolicyNotFoundError(
            f"No existing network egress policy covers hostname '{self.HOSTNAME}'; "
            "one would be created, but mutations are not enabled."
        )

        result = self.runner.invoke(app, ["egress", "ensure", self.HOSTNAME])

        assert result.exit_code == 1
        assert "mutations are not enabled" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_unverified_shape(self, mock_service_class):
        """Test ensure fails loudly on unverified response shapes."""
        from foundry_cli.services.connectivity import EgressPolicyShapeError

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.side_effect = EgressPolicyShapeError(
            "Unverified get-all-policies response shape"
        )

        result = self.runner.invoke(app, ["egress", "ensure", self.HOSTNAME])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_error(self, mock_service_class):
        """Test ensure error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.side_effect = Exception("read timed out")

        result = self.runner.invoke(app, ["egress", "ensure", self.HOSTNAME])

        assert result.exit_code == 1
        assert "Error ensuring network egress policy" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_egress_ensure_with_profile(self, mock_service_class):
        """Test ensure with a specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.ensure_egress_policy.return_value = {
            "policy_rid": self.POLICY_RID,
            "hostname": self.HOSTNAME,
            "status": "exists",
            "policy": {},
        }

        result = self.runner.invoke(
            app, ["egress", "ensure", self.HOSTNAME, "--profile", "test"]
        )

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")


class TestWebhookCreateCommand:
    """Test cases for `connectivity webhook create` (plan-first)."""

    SOURCE_RID = "ri.magritte..source.00000000-0000-0000-0000-000000000021"

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_defaults_to_plan(self, mock_service_class):
        """Test that create without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.build_create_webhook_body.return_value = {"name": "wh"}

        result = self.runner.invoke(
            app, ["webhook", "create", "wh", "--source-rid", self.SOURCE_RID]
        )

        assert result.exit_code == 0
        mock_service.build_create_webhook_body.assert_called_once_with(
            "wh", "wh", "", self.SOURCE_RID, None
        )
        mock_service.create_webhook.assert_not_called()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_apply_sends(self, mock_service_class):
        """Test that --apply issues the verified create body."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.build_create_webhook_body.return_value = {"name": "wh"}
        mock_service.create_webhook.return_value = {
            "metadata": {"rid": "ri.webhooks.main.webhook.abc"}
        }

        result = self.runner.invoke(
            app,
            ["webhook", "create", "wh", "--source-rid", self.SOURCE_RID, "--apply"],
        )

        assert result.exit_code == 0
        mock_service.create_webhook.assert_called_once_with(
            "wh", "wh", "", self.SOURCE_RID, None
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_apply_permission_error(self, mock_service_class):
        """Test that a 403 from the registry surfaces as a loud failure."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.build_create_webhook_body.return_value = {"name": "wh"}
        mock_service.create_webhook.side_effect = RuntimeError(
            "Webhook registry create failed with HTTP 403 "
            "(Compass:InsufficientPermissions)"
        )

        result = self.runner.invoke(
            app,
            ["webhook", "create", "wh", "--source-rid", self.SOURCE_RID, "--apply"],
        )

        assert result.exit_code == 1
        assert "Error creating webhook" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_spec_file_override(self, mock_service_class, tmp_path):
        """Test that --spec-file replaces the default spec."""
        spec_path = tmp_path / "spec.json"
        spec_path.write_text('{"config": {"type": "custom"}, "inputs": []}')
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.build_create_webhook_body.return_value = {"name": "wh"}

        result = self.runner.invoke(
            app,
            [
                "webhook",
                "create",
                "wh",
                "--source-rid",
                self.SOURCE_RID,
                "--spec-file",
                str(spec_path),
            ],
        )

        assert result.exit_code == 0
        assert mock_service.build_create_webhook_body.call_args[0][4] == {
            "config": {"type": "custom"},
            "inputs": [],
        }


class TestWebhookUpdateCommand:
    """Test cases for `connectivity webhook update` (plan-first)."""

    WEBHOOK_RID = "ri.webhooks.main.webhook.12345678-1234-1234-1234-123456789abc"
    SOURCE_RID = "ri.magritte..source.00000000-0000-0000-0000-000000000022"

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_defaults_to_plan(self, mock_service_class):
        """Test that update without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_update_webhook.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            app, ["webhook", "update", self.WEBHOOK_RID, '{"inputs": []}']
        )

        assert result.exit_code == 0
        mock_service.plan_update_webhook.assert_called_once_with(
            self.WEBHOOK_RID, {"inputs": []}
        )
        mock_service.update_webhook.assert_not_called()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_apply_sends(self, mock_service_class):
        """Test that --apply publishes the new webhook version."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_webhook.return_value = {
            "webhookRid": self.WEBHOOK_RID,
            "version": 2,
        }

        result = self.runner.invoke(
            app,
            ["webhook", "update", self.WEBHOOK_RID, '{"inputs": []}', "--apply"],
        )

        assert result.exit_code == 0
        mock_service.update_webhook.assert_called_once_with(
            self.WEBHOOK_RID, {"inputs": []}
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_apply_permission_error(self, mock_service_class):
        """Test that a resource-scoped 403 surfaces as a loud failure."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_webhook.side_effect = RuntimeError(
            "Webhook registry update failed with HTTP 403 "
            "(Compass:InsufficientPermissions)"
        )

        result = self.runner.invoke(
            app,
            ["webhook", "update", self.WEBHOOK_RID, '{"inputs": []}', "--apply"],
        )

        assert result.exit_code == 1
        assert "Error updating webhook" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_requires_spec(self, mock_service_class):
        """Test that a missing spec argument fails before any service call."""
        result = self.runner.invoke(app, ["webhook", "update", self.WEBHOOK_RID])

        assert result.exit_code == 1
        assert "Must specify either spec or --spec-file" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_assembly_mode_builds_spec(self, mock_service_class):
        """Test --source-rid/--domain/--calls assembles the spec via the service."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.resolve_source_domain_id.return_value = (
            "00000000-0000-0000-0000-000000000028"
        )
        mock_service.build_webhook_spec.return_value = {"config": {}}
        mock_service.plan_update_webhook.return_value = {"mode": "plan"}

        calls = json.dumps(
            [
                {
                    "httpMethod": "GET",
                    "httpPath": ["multipass/api/users", {"input": "userId"}],
                    "httpQueryParams": {"realm": [{"input": "realm"}]},
                }
            ]
        )
        result = self.runner.invoke(
            app,
            [
                "webhook",
                "update",
                self.WEBHOOK_RID,
                "--source-rid",
                self.SOURCE_RID,
                "--domain",
                "example.invalid",
                "--calls",
                calls,
            ],
        )

        assert result.exit_code == 0
        mock_service.resolve_source_domain_id.assert_called_once_with(
            self.SOURCE_RID, "example.invalid"
        )
        mock_service.build_webhook_spec.assert_called_once_with(
            self.SOURCE_RID,
            domain_id="00000000-0000-0000-0000-000000000028",
            calls=[
                {
                    "httpMethod": "GET",
                    "httpPath": ["multipass/api/users", {"input": "userId"}],
                    "httpQueryParams": {"realm": [{"input": "realm"}]},
                }
            ],
            inputs=[],
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_assembly_requires_source_rid_and_domain(self, mock_service_class):
        """Test assembly mode without --domain fails before any lookup."""
        result = self.runner.invoke(
            app,
            [
                "webhook",
                "update",
                self.WEBHOOK_RID,
                "--source-rid",
                self.SOURCE_RID,
                "--calls",
                "[]",
            ],
        )

        assert result.exit_code == 1
        assert "requires both --source-rid and --domain" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_update_spec_and_assembly_conflict(self, mock_service_class):
        """Test that a verbatim spec cannot be combined with assembly options."""
        result = self.runner.invoke(
            app,
            [
                "webhook",
                "update",
                self.WEBHOOK_RID,
                '{"inputs": []}',
                "--source-rid",
                self.SOURCE_RID,
            ],
        )

        assert result.exit_code == 1
        assert "Cannot combine" in result.stdout


class TestRestSourceCreateCommand:
    """Test cases for `connectivity rest-source create` (plan-first)."""

    PARENT_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000004"
    EGRESS_RID = (
        "ri.resource-policy-manager.global.network-egress-policy."
        "00000000-0000-0000-0000-000000000027"
    )

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def _args(self, *extra):
        return [
            "rest-source",
            "create",
            "src",
            "--host",
            "example.invalid",
            "--parent-rid",
            self.PARENT_RID,
            "--egress-policy-rid",
            self.EGRESS_RID,
            *extra,
        ]

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_defaults_to_plan(self, mock_service_class):
        """Test that create without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_rest_source.return_value = {"mode": "plan"}

        result = self.runner.invoke(app, self._args())

        assert result.exit_code == 0
        mock_service.plan_create_rest_source.assert_called_once_with(
            "src",
            "example.invalid",
            "HTTPS",
            443,
            self.PARENT_RID,
            [self.EGRESS_RID],
            "",
        )
        mock_service.create_rest_source.assert_not_called()

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_apply_sends(self, mock_service_class):
        """Test that --apply issues the verified addSourceV3 create."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_rest_source.return_value = {
            "source_rid": "ri.magritte..source.abc",
            "status": "created",
        }

        result = self.runner.invoke(app, self._args("--apply"))

        assert result.exit_code == 0
        mock_service.create_rest_source.assert_called_once_with(
            "src",
            "example.invalid",
            "HTTPS",
            443,
            self.PARENT_RID,
            [self.EGRESS_RID],
            "",
        )

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_apply_permission_error(self, mock_service_class):
        """Test that a magritte:write-resource 403 surfaces loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_rest_source.side_effect = RuntimeError(
            "REST source create failed with HTTP 403 (Default:PermissionDenied)"
        )

        result = self.runner.invoke(app, self._args("--apply"))

        assert result.exit_code == 1
        assert "Error creating REST API data source" in result.stdout

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_requires_parent_rid(self, mock_service_class):
        """Test that --parent-rid is mandatory."""
        result = self.runner.invoke(
            app,
            [
                "rest-source",
                "create",
                "src",
                "--host",
                "example.invalid",
                "--egress-policy-rid",
                self.EGRESS_RID,
            ],
        )

        assert result.exit_code != 0

    @patch("foundry_cli.commands.connectivity.ConnectivityService")
    def test_create_requires_egress_policy_rid(self, mock_service_class):
        """Test that at least one --egress-policy-rid is mandatory."""
        result = self.runner.invoke(
            app,
            [
                "rest-source",
                "create",
                "src",
                "--host",
                "example.invalid",
                "--parent-rid",
                self.PARENT_RID,
            ],
        )

        assert result.exit_code != 0
