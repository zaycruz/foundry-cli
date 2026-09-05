"""
Tests for the `ai-fde` command group.
"""

import json

import typer
from unittest.mock import Mock, patch
from typer.testing import CliRunner

from foundry_cli.commands.ai_fde import app

THREAD_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "8041e2bb-45d0-4ec2-bf71-530f77fa8ffa"
NEW_VERSION = "75e108de-3cd8-484b-a970-821953b8d221"

# The module app holds nested sub-apps; register it on a parent (as cli.py
# does) so the tests exercise the real `ai-fde ...` command paths.
root_app = typer.Typer()
root_app.add_typer(app, name="ai-fde")


class TestThreadsListCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_list_success(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_threads.return_value = [{"id": THREAD_ID}]

        result = self.runner.invoke(root_app, ["ai-fde", "threads", "list"])

        assert result.exit_code == 0
        mock_service.list_threads.assert_called_once_with(page_size=50)

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_list_json_format(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_threads.return_value = [{"id": THREAD_ID}]

        result = self.runner.invoke(
            root_app, ["ai-fde", "threads", "list", "--format", "json"]
        )

        assert result.exit_code == 0
        assert THREAD_ID in result.stdout

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_list_error(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_threads.side_effect = Exception("service unavailable")

        result = self.runner.invoke(root_app, ["ai-fde", "threads", "list"])

        assert result.exit_code == 1
        assert "Error listing AI FDE threads" in result.stdout


class TestThreadsGetCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_get_success(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_thread_metadata.return_value = {"id": THREAD_ID}

        result = self.runner.invoke(root_app, ["ai-fde", "threads", "get", THREAD_ID])

        assert result.exit_code == 0
        mock_service.get_thread_metadata.assert_called_once_with(THREAD_ID)


class TestThreadsItemsCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_items_success(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_thread_items.return_value = {
            "contextItems": [],
            "nextPageToken": None,
        }

        result = self.runner.invoke(
            root_app,
            [
                "ai-fde",
                "threads",
                "items",
                THREAD_ID,
                "--page-size",
                "25",
                "--page-token",
                "tok",
            ],
        )

        assert result.exit_code == 0
        mock_service.get_thread_items.assert_called_once_with(
            THREAD_ID, page_size=25, page_token="tok"
        )


class TestThreadsCreateCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_create_success(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_thread.return_value = {"id": THREAD_ID, "version": VERSION}

        result = self.runner.invoke(
            root_app,
            ["ai-fde", "threads", "create", "--name", "New session", "--format", "json"],
        )

        assert result.exit_code == 0
        mock_service.create_thread.assert_called_once_with("New session")
        assert THREAD_ID in result.stdout

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_create_error(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_thread.side_effect = Exception("mutation rejected")

        result = self.runner.invoke(
            root_app, ["ai-fde", "threads", "create", "--name", "New session"]
        )

        assert result.exit_code == 1
        assert "Error creating AI FDE thread" in result.stdout


class TestThreadsSendCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_send_prints_thread_version(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.send_user_message.return_value = {
            "contextItemId": "f890f59d-b931-40f0-a59f-aeb0f4710491",
            "threadVersion": NEW_VERSION,
            "metadata": {"threadId": THREAD_ID, "threadVersion": NEW_VERSION},
        }

        result = self.runner.invoke(
            root_app,
            [
                "ai-fde",
                "threads",
                "send",
                THREAD_ID,
                "--message",
                "hello",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        mock_service.send_user_message.assert_called_once_with(THREAD_ID, "hello")
        assert NEW_VERSION in result.stdout

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_send_error(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.send_user_message.side_effect = Exception("conflict")

        result = self.runner.invoke(
            root_app, ["ai-fde", "threads", "send", THREAD_ID, "--message", "hello"]
        )

        assert result.exit_code == 1
        assert "Error sending user message" in result.stdout


class TestThreadsMetadataCommands:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_metadata_get(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_thread_agent_state.return_value = {"agentSystemPrompt": ""}

        result = self.runner.invoke(
            root_app, ["ai-fde", "threads", "metadata", "get", THREAD_ID]
        )

        assert result.exit_code == 0
        mock_service.get_thread_agent_state.assert_called_once_with(THREAD_ID)

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_metadata_update(self, mock_service_class, tmp_path):
        modification = {"agentSystemPrompt": "", "toolConfigurations": {}}
        definition = tmp_path / "agent-state.json"
        definition.write_text(json.dumps(modification))
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_thread_metadata.return_value = {
            "metadata": {"threadVersion": NEW_VERSION}
        }

        result = self.runner.invoke(
            root_app,
            [
                "ai-fde",
                "threads",
                "metadata",
                "update",
                THREAD_ID,
                "--current-version",
                VERSION,
                "--agent-state",
                str(definition),
            ],
        )

        assert result.exit_code == 0
        mock_service.update_thread_metadata.assert_called_once_with(
            THREAD_ID, VERSION, modification
        )

    def test_metadata_update_rejects_non_object(self, tmp_path):
        definition = tmp_path / "agent-state.json"
        definition.write_text(json.dumps(["not", "an", "object"]))

        result = self.runner.invoke(
            root_app,
            [
                "ai-fde",
                "threads",
                "metadata",
                "update",
                THREAD_ID,
                "--current-version",
                VERSION,
                "--agent-state",
                str(definition),
            ],
        )

        assert result.exit_code == 1
        assert "must be a JSON object" in result.stdout


class TestSettingsCommands:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_settings_get(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_settings.return_value = {"attributionSettings": {}}

        result = self.runner.invoke(root_app, ["ai-fde", "settings", "get"])

        assert result.exit_code == 0
        mock_service.get_settings.assert_called_once_with()

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_settings_update(self, mock_service_class, tmp_path):
        body = {"attributionSettings": {"type": "unchanged", "unchanged": {}}}
        definition = tmp_path / "settings.json"
        definition.write_text(json.dumps(body))
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_settings.return_value = {}

        result = self.runner.invoke(
            root_app,
            ["ai-fde", "settings", "update", "--definition", str(definition)],
        )

        assert result.exit_code == 0
        mock_service.update_settings.assert_called_once_with(body)

    @patch("foundry_cli.commands.ai_fde.AiFdeService")
    def test_settings_update_error(self, mock_service_class, tmp_path):
        definition = tmp_path / "settings.json"
        definition.write_text(json.dumps({}))
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.update_settings.side_effect = Exception("bad request")

        result = self.runner.invoke(
            root_app,
            ["ai-fde", "settings", "update", "--definition", str(definition)],
        )

        assert result.exit_code == 1
        assert "Error updating AI FDE settings" in result.stdout
