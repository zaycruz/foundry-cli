"""
Tests for the read-only `global-proposal get` command.
"""

from unittest.mock import Mock, patch

import typer
from typer.testing import CliRunner

from pltr.commands.global_proposal import app
from pltr.services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchShapeError,
)

PROPOSAL_RID = "ri.global-proposal.main.proposal.00000000-0000-0000-0000-000000000013"

# The module app holds a single command, which Typer collapses when the app is
# invoked standalone; register it on a parent (as cli.py does) so the tests
# exercise the real `global-proposal get` command path.
root_app = typer.Typer()
root_app.add_typer(app, name="global-proposal")


class TestGlobalProposalGetCommand:
    """Test cases for `global-proposal get`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_success(self, mock_service_class):
        """Test loading a global proposal."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.return_value = {"rid": PROPOSAL_RID}

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID])

        assert result.exit_code == 0
        mock_service.get_proposal.assert_called_once_with(PROPOSAL_RID)

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_json_format(self, mock_service_class):
        """Test get with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.return_value = {"rid": PROPOSAL_RID}

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID, "--format", "json"])

        assert result.exit_code == 0
        assert PROPOSAL_RID in result.stdout

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_not_found(self, mock_service_class):
        """Test get when no proposal exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.side_effect = GlobalBranchNotFoundError(
            f"No proposal found for RID {PROPOSAL_RID}"
        )

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID])

        assert result.exit_code == 1
        assert "No proposal found" in result.stdout

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_unverified_shape(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.side_effect = GlobalBranchShapeError(
            "Unverified branch-service proposal response shape"
        )

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_error(self, mock_service_class):
        """Test get error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.side_effect = Exception("service unavailable")

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID])

        assert result.exit_code == 1
        assert "Error loading global proposal" in result.stdout

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_get_with_profile(self, mock_service_class):
        """Test get with a specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_proposal.return_value = {"rid": PROPOSAL_RID}

        result = self.runner.invoke(root_app, ["global-proposal", "get", PROPOSAL_RID, "--profile", "test"])

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")
