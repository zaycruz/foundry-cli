"""
Tests for the `compute` commands (info, logs, manage, execute).
"""

import json
from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from foundry_cli.commands.compute import app
from foundry_cli.services.compute import (
    ComputeModulesError,
    ComputeSessionNotFoundError,
    ComputeShapeError,
)

DEPLOYED_APP_RID = "ri.foundry.main.deployed-app.00000000-0000-0000-0000-000000000000"
BUILD_JOB_RID = "ri.foundry.main.job.00000000-0000-0000-0000-000000000000"
BUILD_RID = "ri.foundry.main.build.00000000-0000-0000-0000-000000000000"

# The module app holds multiple commands; register it on a parent (as cli.py
# does) so the tests exercise the real `compute <cmd>` command paths.
root_app = typer.Typer()
root_app.add_typer(app, name="compute")


class TestComputeInfoCommand:
    """Test cases for `compute info`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_success_loads_status_and_config(self, mock_service_class):
        """Test info loads both includes by default."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_status.return_value = {"state": "RUNNING"}
        mock_service.get_config.return_value = {"type": "FUNCTION"}

        result = self.runner.invoke(root_app, ["compute", "info", DEPLOYED_APP_RID])

        assert result.exit_code == 0
        mock_service.get_status.assert_called_once_with(DEPLOYED_APP_RID, "master")
        mock_service.get_config.assert_called_once_with(DEPLOYED_APP_RID)

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_include_status_only(self, mock_service_class):
        """Test --include restricts which endpoints are called."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_status.return_value = {"state": "RUNNING"}

        result = self.runner.invoke(
            root_app,
            ["compute", "info", DEPLOYED_APP_RID, "--include", "status"],
        )

        assert result.exit_code == 0
        mock_service.get_status.assert_called_once()
        mock_service.get_config.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_unknown_include_rejected(self, mock_service_class):
        """Test an unknown --include value fails before any request."""
        result = self.runner.invoke(
            root_app,
            ["compute", "info", DEPLOYED_APP_RID, "--include", "bogus"],
        )

        assert result.exit_code == 2
        assert "Unknown --include" in result.stdout
        mock_service_class.return_value.get_status.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_permission_denied_surfaces(self, mock_service_class):
        """Test the captured 403 contract surfaces honestly (exit 1, not hidden)."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_status.side_effect = ComputeModulesError(
            "status load for deployed app x failed with HTTP 403 "
            "(Contour:InsufficientPermission)"
        )

        result = self.runner.invoke(root_app, ["compute", "info", DEPLOYED_APP_RID])

        assert result.exit_code == 1
        assert "HTTP 403" in result.stdout

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_unverified_shape_fails_loudly(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_status.side_effect = ComputeShapeError(
            "Unverified compute-module status response shape"
        )

        result = self.runner.invoke(root_app, ["compute", "info", DEPLOYED_APP_RID])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_info_agent_format_marks_shape_unverified(self, mock_service_class):
        """Test the agent envelope honestly marks shape_verified false."""
        from foundry_cli.utils.agent_output import build_agent_output, reset_agent_output

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_status.return_value = {"state": "RUNNING"}
        mock_service.get_config.return_value = {"type": "FUNCTION"}

        result = self.runner.invoke(
            root_app, ["compute", "info", DEPLOYED_APP_RID, "--format", "agent"]
        )

        assert result.exit_code == 0
        envelope = build_agent_output()
        reset_agent_output()
        assert envelope is not None
        assert envelope["meta"]["operation"] == "get_compute_modules_info"
        assert envelope["meta"]["shape_verified"] is False


class TestComputeLogsCommand:
    """Test cases for `compute logs`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_logs_success(self, mock_service_class):
        """Test logs passes range and ordering through to the service."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs.return_value = {
            "session": {"containerRid": "c", "sessionId": "s"},
            "request": {},
            "response": {"logs": []},
        }

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "logs",
                BUILD_JOB_RID,
                "--from-inclusive",
                "10",
                "--to-exclusive",
                "20",
                "--page-size-limit",
                "500",
                "--reverse",
            ],
        )

        assert result.exit_code == 0
        mock_service.get_logs.assert_called_once_with(
            BUILD_JOB_RID,
            from_inclusive=10,
            to_exclusive=20,
            page_size_limit=500,
            chronological=False,
        )

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_logs_no_session_is_loud(self, mock_service_class):
        """Test a missing telemetry session exits 1 with a clear message."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs.side_effect = ComputeSessionNotFoundError(
            f"No telemetry session found for build job RID {BUILD_JOB_RID}"
        )

        result = self.runner.invoke(root_app, ["compute", "logs", BUILD_JOB_RID])

        assert result.exit_code == 1
        assert "No telemetry session" in result.stdout


class TestComputeManageCommand:
    """Test cases for `compute manage` (plan-first)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_start_defaults_to_plan(self, mock_service_class):
        """Test start without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_start.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "start",
                "--deployed-app-rid",
                DEPLOYED_APP_RID,
            ],
        )

        assert result.exit_code == 0
        mock_service.plan_start.assert_called_once_with(DEPLOYED_APP_RID, "master")
        mock_service.start.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_start_apply_sends(self, mock_service_class):
        """Test start --apply issues the submitBuild mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.start.return_value = {"buildRid": BUILD_RID}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "start",
                "--deployed-app-rid",
                DEPLOYED_APP_RID,
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.start.assert_called_once_with(DEPLOYED_APP_RID, "master")

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_start_requires_deployed_app_rid(self, mock_service_class):
        """Test start without --deployed-app-rid fails before any request."""
        result = self.runner.invoke(
            root_app, ["compute", "manage", "--action", "start"]
        )

        assert result.exit_code == 2
        mock_service_class.return_value.start.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_stop_defaults_to_plan(self, mock_service_class):
        """Test stop without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_stop.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            ["compute", "manage", "--action", "stop", "--build-rid", BUILD_RID],
        )

        assert result.exit_code == 0
        mock_service.plan_stop.assert_called_once_with(BUILD_RID)
        mock_service.stop.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_stop_apply_requires_yes(self, mock_service_class):
        """Test stop --apply without --yes asks, and 'n' cancels."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "stop",
                "--build-rid",
                BUILD_RID,
                "--apply",
            ],
            input="n\n",
        )

        assert result.exit_code == 1
        mock_service.stop.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_stop_apply_yes_sends(self, mock_service_class):
        """Test stop --apply --yes issues the cancel."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.stop.return_value = {"buildRid": BUILD_RID, "acknowledged": True}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "stop",
                "--build-rid",
                BUILD_RID,
                "--apply",
                "--yes",
            ],
        )

        assert result.exit_code == 0
        mock_service.stop.assert_called_once_with(BUILD_RID)

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_dev_mode_plan_and_apply(self, mock_service_class):
        """Test dev-mode plan by default and PUT behind --apply."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_dev_mode.return_value = {"mode": "plan"}
        mock_service.configure_dev_mode.return_value = {"acknowledged": True}

        plan_result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "dev-mode",
                "--deployed-app-rid",
                DEPLOYED_APP_RID,
                "--dev-mode-until",
                "2026-07-25T07:00:00Z",
            ],
        )
        assert plan_result.exit_code == 0
        mock_service.plan_dev_mode.assert_called_once_with(
            DEPLOYED_APP_RID, "master", "2026-07-25T07:00:00Z"
        )
        mock_service.configure_dev_mode.assert_not_called()

        apply_result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "dev-mode",
                "--deployed-app-rid",
                DEPLOYED_APP_RID,
                "--apply",
            ],
        )
        assert apply_result.exit_code == 0
        mock_service.configure_dev_mode.assert_called_once_with(
            DEPLOYED_APP_RID, "master", None
        )

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_unknown_action_rejected(self, mock_service_class):
        """Test an unknown --action fails before any request."""
        result = self.runner.invoke(
            root_app, ["compute", "manage", "--action", "bounce"]
        )

        assert result.exit_code == 2
        assert "Unknown --action" in result.stdout

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_manage_agent_plan_envelope(self, mock_service_class):
        """Test the agent plan envelope carries mode and verification flags."""
        from foundry_cli.utils.agent_output import build_agent_output, reset_agent_output

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_start.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "manage",
                "--action",
                "start",
                "--deployed-app-rid",
                DEPLOYED_APP_RID,
                "--format",
                "agent",
            ],
        )

        assert result.exit_code == 0
        envelope = build_agent_output()
        reset_agent_output()
        assert envelope is not None
        assert envelope["meta"]["operation"] == "manage_compute_modules"
        assert envelope["meta"]["mode"] == "plan"
        assert envelope["meta"]["manage_action"] == "start"
        assert envelope["meta"]["shape_verified"] is False
        assert envelope["meta"]["write_verified"] is False


class TestComputeExecuteCommand:
    """Test cases for `compute execute` (plan-first)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_execute_defaults_to_plan(self, mock_service_class):
        """Test execute without --apply prints the plan, no execution."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_execute.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "execute",
                DEPLOYED_APP_RID,
                "--query-type",
                "my-query",
                "--query",
                '{"probe": true}',
            ],
        )

        assert result.exit_code == 0
        mock_service.plan_execute.assert_called_once_with(
            DEPLOYED_APP_RID, "master", "my-query", {"probe": True}
        )
        mock_service.execute.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_execute_apply_sends(self, mock_service_class):
        """Test execute --apply issues the execution with parsed query JSON."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.execute.return_value = {"result": {"answer": 42}}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "execute",
                DEPLOYED_APP_RID,
                "--query-type",
                "my-query",
                "--query",
                '{"x": 1}',
                "--apply",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        mock_service.execute.assert_called_once_with(
            DEPLOYED_APP_RID, "master", "my-query", {"x": 1}
        )
        assert '"answer": 42' in result.stdout

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_execute_invalid_query_json_rejected(self, mock_service_class):
        """Test malformed --query JSON fails before any request."""
        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "execute",
                DEPLOYED_APP_RID,
                "--query-type",
                "my-query",
                "--query",
                "{not json",
            ],
        )

        assert result.exit_code == 2
        assert "not valid JSON" in result.stdout
        mock_service_class.return_value.execute.assert_not_called()

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_execute_captured_403_surfaces(self, mock_service_class):
        """Test the captured submit-permission 403 surfaces honestly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.execute.side_effect = ComputeModulesError(
            "function execute (my-query) on deployed app x failed with HTTP 403 "
            "(Contour:InsufficientPermission)"
        )

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "execute",
                DEPLOYED_APP_RID,
                "--query-type",
                "my-query",
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "HTTP 403" in result.stdout

    @patch("foundry_cli.commands.compute.ComputeService")
    def test_execute_agent_plan_envelope(self, mock_service_class):
        """Test the agent plan envelope carries the operation and flags."""
        from foundry_cli.utils.agent_output import build_agent_output, reset_agent_output

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_execute.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            [
                "compute",
                "execute",
                DEPLOYED_APP_RID,
                "--query-type",
                "my-query",
                "--format",
                "agent",
            ],
        )

        assert result.exit_code == 0
        envelope = build_agent_output()
        reset_agent_output()
        assert envelope is not None
        assert envelope["meta"]["operation"] == "execute_compute_modules_function"
        assert envelope["meta"]["mode"] == "plan"
        assert envelope["meta"]["shape_verified"] is False
        assert envelope["meta"]["write_verified"] is False
        assert json.dumps(envelope["data"])  # data is JSON-serializable
