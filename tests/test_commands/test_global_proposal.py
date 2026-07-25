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

PROPOSAL_RID = "ri.branch..proposal.00000000-0000-0000-0000-000000000013"

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

        result = self.runner.invoke(
            root_app, ["global-proposal", "get", PROPOSAL_RID, "--format", "json"]
        )

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

        result = self.runner.invoke(
            root_app, ["global-proposal", "get", PROPOSAL_RID, "--profile", "test"]
        )

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")


BRANCH_RID = "ri.branch..branch.00000000-0000-0000-0000-000000000002"


class TestGlobalProposalCreateCommand:
    """Test cases for `global-proposal create` (plan-first)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_defaults_to_plan(self, mock_service_class):
        """Test that create without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_proposal.return_value = {
            "mode": "plan",
            "request": {
                "verb": "POST",
                "path": "/branch-service/api/branch/proposal/create",
            },
        }

        result = self.runner.invoke(
            root_app,
            ["global-proposal", "create", "my-proposal", "--branch-rid", BRANCH_RID],
        )

        assert result.exit_code == 0
        mock_service.plan_create_proposal.assert_called_once_with(
            BRANCH_RID, "my-proposal", "", merge_to="main"
        )

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_apply_sends(self, mock_service_class):
        """Test that --apply issues the real create."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_proposal.return_value = {
            "proposalRid": PROPOSAL_RID,
            "proposal": {"proposalRid": PROPOSAL_RID, "proposalStatus": "OPEN"},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.create_proposal.assert_called_once_with(
            BRANCH_RID, "my-proposal", "", merge_to="main"
        )

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_apply_agent_format(self, mock_service_class):
        """Test the applied create records an agent payload with the new RID."""
        from pltr.utils.agent_output import build_agent_output, reset_agent_output

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_proposal.return_value = {
            "proposalRid": PROPOSAL_RID,
            "proposal": {"proposalRid": PROPOSAL_RID},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--apply",
                "--format",
                "agent",
            ],
        )

        assert result.exit_code == 0
        envelope = build_agent_output()
        reset_agent_output()
        assert envelope is not None
        assert not envelope["errors"]
        assert envelope["meta"]["operation"] == "create_global_proposal"
        assert envelope["meta"]["mode"] == "applied"
        assert envelope["meta"]["branch_rid"] == BRANCH_RID
        assert envelope["meta"]["proposal_rid"] == PROPOSAL_RID
        assert envelope["meta"]["write_verified"] is True

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_merge_to_branch_rid_plan(self, mock_service_class):
        """Test --merge-to <branch-rid> reaches the plan unchanged."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_proposal.return_value = {"mode": "plan"}

        target_rid = "ri.branch..branch.99999999-8888-7777-6666-555555555555"
        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--merge-to",
                target_rid,
            ],
        )

        assert result.exit_code == 0
        mock_service.plan_create_proposal.assert_called_once_with(
            BRANCH_RID, "my-proposal", "", merge_to=target_rid
        )

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_merge_to_branch_rid_apply(self, mock_service_class):
        """Test --apply --merge-to <branch-rid> reaches the create unchanged."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_proposal.return_value = {
            "proposalRid": PROPOSAL_RID,
            "proposal": {"proposalRid": PROPOSAL_RID},
        }

        target_rid = "ri.branch..branch.99999999-8888-7777-6666-555555555555"
        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--merge-to",
                target_rid,
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.create_proposal.assert_called_once_with(
            BRANCH_RID, "my-proposal", "", merge_to=target_rid
        )

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_invalid_merge_to_fails_loudly(self, mock_service_class):
        """Test an invalid merge target surfaces the validation error."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_proposal.side_effect = ValueError(
            "Invalid merge target 'bogus': expected 'main' or a global branch RID"
        )

        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--merge-to",
                "bogus",
            ],
        )

        assert result.exit_code == 1
        assert "Invalid merge target" in result.stdout

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_create_apply_error(self, mock_service_class):
        """Test create error handling on --apply."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_proposal.side_effect = Exception("HTTP 400")

        result = self.runner.invoke(
            root_app,
            [
                "global-proposal",
                "create",
                "my-proposal",
                "--branch-rid",
                BRANCH_RID,
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "Error creating global proposal" in result.stdout


class TestGlobalProposalCloseCommand:
    """Test cases for `global-proposal close` (plan-first, destructive)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_close_defaults_to_plan(self, mock_service_class):
        """Test that close without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(
            root_app, ["global-proposal", "close", PROPOSAL_RID]
        )

        assert result.exit_code == 0
        mock_service.close_proposal.assert_not_called()

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_close_apply_requires_yes(self, mock_service_class):
        """Test that --apply without --yes asks, and 'n' cancels."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(
            root_app,
            ["global-proposal", "close", PROPOSAL_RID, "--apply"],
            input="n\n",
        )

        assert result.exit_code == 1
        mock_service.close_proposal.assert_not_called()

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_close_apply_yes_sends(self, mock_service_class):
        """Test that --apply --yes issues the close."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_proposal.return_value = {
            "rid": PROPOSAL_RID,
            "acknowledged": True,
        }

        result = self.runner.invoke(
            root_app,
            ["global-proposal", "close", PROPOSAL_RID, "--apply", "--yes"],
        )

        assert result.exit_code == 0
        mock_service.close_proposal.assert_called_once_with(PROPOSAL_RID)

    @patch("pltr.commands.global_proposal.GlobalProposalService")
    def test_close_not_found(self, mock_service_class):
        """Test close when no proposal exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_proposal.side_effect = GlobalBranchNotFoundError(
            f"No proposal found for RID {PROPOSAL_RID}"
        )

        result = self.runner.invoke(
            root_app,
            ["global-proposal", "close", PROPOSAL_RID, "--apply", "--yes"],
        )

        assert result.exit_code == 1
        assert "No proposal found" in result.stdout
