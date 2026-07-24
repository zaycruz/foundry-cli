"""
Tests for the read-only `global-branch get` command.
"""

from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from pltr.commands.global_branch import app
from pltr.services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchShapeError,
)

BRANCH_RID = "ri.global-branch.main.branch.00000000-0000-0000-0000-000000000002"

# The module app holds a single command, which Typer collapses when the app is
# invoked standalone; register it on a parent (as cli.py does) so the tests
# exercise the real `global-branch get` command path.
root_app = typer.Typer()
root_app.add_typer(app, name="global-branch")


class TestGlobalBranchGetCommand:
    """Test cases for `global-branch get`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_success(self, mock_service_class):
        """Test loading a global branch."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.return_value = {"rid": BRANCH_RID}

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID])

        assert result.exit_code == 0
        mock_service.get_branch.assert_called_once_with(BRANCH_RID)

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_json_format(self, mock_service_class):
        """Test get with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.return_value = {"rid": BRANCH_RID}

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID, "--format", "json"])

        assert result.exit_code == 0
        assert BRANCH_RID in result.stdout

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_not_found(self, mock_service_class):
        """Test get when no branch exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.side_effect = GlobalBranchNotFoundError(
            f"No branch found for RID {BRANCH_RID}"
        )

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID])

        assert result.exit_code == 1
        assert "No branch found" in result.stdout

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_unverified_shape(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.side_effect = GlobalBranchShapeError(
            "Unverified branch-service branch response shape"
        )

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_error(self, mock_service_class):
        """Test get error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.side_effect = Exception("service unavailable")

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID])

        assert result.exit_code == 1
        assert "Error loading global branch" in result.stdout

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_get_with_profile(self, mock_service_class):
        """Test get with a specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_branch.return_value = {"rid": BRANCH_RID}

        result = self.runner.invoke(root_app, ["global-branch", "get", BRANCH_RID, "--profile", "test"])

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")
