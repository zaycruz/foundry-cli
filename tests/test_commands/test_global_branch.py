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

BRANCH_RID = "ri.branch..branch.00000000-0000-0000-0000-000000000002"

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

        result = self.runner.invoke(
            root_app, ["global-branch", "get", BRANCH_RID, "--format", "json"]
        )

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

        result = self.runner.invoke(
            root_app, ["global-branch", "get", BRANCH_RID, "--profile", "test"]
        )

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")


class TestGlobalBranchCreateCommand:
    """Test cases for `global-branch create` (plan-first)."""

    ONTOLOGY_RID = "ri.ontology.main.ontology.00000000-0000-0000-0000-000000000002"

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_defaults_to_plan(self, mock_service_class):
        """Test that create without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_branch.return_value = {
            "mode": "plan",
            "request": {"verb": "POST", "path": "/branch-service/api/branch/create"},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
            ],
        )

        assert result.exit_code == 0
        mock_service.plan_create_branch.assert_called_once_with(
            "my-branch", "", self.ONTOLOGY_RID, None
        )

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_apply_sends(self, mock_service_class):
        """Test that --apply issues the real create."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_branch.return_value = {
            "branchRid": BRANCH_RID,
            "branchRecord": {"branchRid": BRANCH_RID, "branchStatus": "OPEN"},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.create_branch.assert_called_once_with(
            "my-branch", "", self.ONTOLOGY_RID, None
        )

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_apply_agent_format(self, mock_service_class):
        """Test the applied create records an agent payload with the new RID."""
        from pltr.utils.agent_output import build_agent_output, reset_agent_output

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_branch.return_value = {
            "branchRid": BRANCH_RID,
            "branchRecord": {"branchRid": BRANCH_RID},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
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
        assert envelope["meta"]["operation"] == "create_global_branch"
        assert envelope["meta"]["mode"] == "applied"
        assert envelope["meta"]["branch_rid"] == BRANCH_RID
        assert envelope["meta"]["write_verified"] is True

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_add_resource_plan(self, mock_service_class):
        """Test repeatable --add-resource reaches the plan as a list."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_create_branch.return_value = {"mode": "plan"}

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
                "--add-resource",
                "ri.foundry.main.dataset.aaa",
                "--add-resource",
                "ri.foundry.main.dataset.bbb",
            ],
        )

        assert result.exit_code == 0
        mock_service.plan_create_branch.assert_called_once_with(
            "my-branch",
            "",
            self.ONTOLOGY_RID,
            ["ri.foundry.main.dataset.aaa", "ri.foundry.main.dataset.bbb"],
        )

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_add_resource_apply(self, mock_service_class):
        """Test --apply --add-resource reaches the create as a list."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_branch.return_value = {
            "branchRid": BRANCH_RID,
            "branchRecord": {"branchRid": BRANCH_RID},
        }

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
                "--add-resource",
                "ri.foundry.main.dataset.aaa",
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.create_branch.assert_called_once_with(
            "my-branch", "", self.ONTOLOGY_RID, ["ri.foundry.main.dataset.aaa"]
        )

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_create_apply_error(self, mock_service_class):
        """Test create error handling on --apply."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_branch.side_effect = Exception("HTTP 400")

        result = self.runner.invoke(
            root_app,
            [
                "global-branch",
                "create",
                "my-branch",
                "--ontology-rid",
                self.ONTOLOGY_RID,
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "Error creating global branch" in result.stdout


class TestGlobalBranchCloseCommand:
    """Test cases for `global-branch close` (plan-first, destructive)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_close_defaults_to_plan(self, mock_service_class):
        """Test that close without --apply prints the plan, no mutation."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(root_app, ["global-branch", "close", BRANCH_RID])

        assert result.exit_code == 0
        mock_service.close_branch.assert_not_called()

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_close_apply_requires_yes(self, mock_service_class):
        """Test that --apply without --yes asks, and 'n' cancels."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(
            root_app,
            ["global-branch", "close", BRANCH_RID, "--apply"],
            input="n\n",
        )

        assert result.exit_code == 1
        mock_service.close_branch.assert_not_called()

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_close_apply_yes_sends(self, mock_service_class):
        """Test that --apply --yes issues the close."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_branch.return_value = {
            "rid": BRANCH_RID,
            "acknowledged": True,
        }

        result = self.runner.invoke(
            root_app,
            ["global-branch", "close", BRANCH_RID, "--apply", "--yes"],
        )

        assert result.exit_code == 0
        mock_service.close_branch.assert_called_once_with(BRANCH_RID)

    @patch("pltr.commands.global_branch.GlobalBranchService")
    def test_close_not_found(self, mock_service_class):
        """Test close when no branch exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_branch.side_effect = GlobalBranchNotFoundError(
            f"No branch found for RID {BRANCH_RID}"
        )

        result = self.runner.invoke(
            root_app,
            ["global-branch", "close", BRANCH_RID, "--apply", "--yes"],
        )

        assert result.exit_code == 1
        assert "No branch found" in result.stdout
