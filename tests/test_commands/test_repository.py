"""
Tests for the read-only repository pull-request commands.
"""

from unittest.mock import Mock, patch
from typer.testing import CliRunner

from pltr.commands.repository import app
from pltr.services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
)

REPO_RID = "ri.stemma.main.repository.00000000-0000-0000-0000-000000000014"
PR_RID = "ri.pull-request.main.pull-request.00000000-0000-0000-0000-000000000012"


def _sample_pr():
    return {
        "rid": PR_RID,
        "baseRepositoryRid": REPO_RID,
        "currentRecord": {"status": "CLOSED", "title": "fix: example"},
    }


class TestPullRequestListCommand:
    """Test cases for `repository pull-request list`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_success(self, mock_service_class):
        """Test listing pull requests."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.return_value = [_sample_pr()]

        result = self.runner.invoke(app, ["pull-request", "list"])

        assert result.exit_code == 0
        mock_service.list_pull_requests.assert_called_once_with(None)

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_with_repository_filter(self, mock_service_class):
        """Test listing with a repository RID filter."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.return_value = [_sample_pr()]

        result = self.runner.invoke(app, ["pull-request", "list", REPO_RID])

        assert result.exit_code == 0
        mock_service.list_pull_requests.assert_called_once_with(REPO_RID)

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_json_format(self, mock_service_class):
        """Test listing with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.return_value = [_sample_pr()]

        result = self.runner.invoke(app, ["pull-request", "list", "--format", "json"])

        assert result.exit_code == 0
        assert PR_RID in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_shape_error(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.side_effect = PullRequestShapeError(
            "Unverified pull-request list response shape"
        )

        result = self.runner.invoke(app, ["pull-request", "list"])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_error(self, mock_service_class):
        """Test list error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.side_effect = Exception("read timed out")

        result = self.runner.invoke(app, ["pull-request", "list"])

        assert result.exit_code == 1
        assert "Error listing pull requests" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_list_with_profile(self, mock_service_class):
        """Test listing with a specific profile."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_pull_requests.return_value = []

        result = self.runner.invoke(
            app, ["pull-request", "list", "--profile", "test"]
        )

        assert result.exit_code == 0
        mock_service_class.assert_called_once_with(profile="test")


class TestPullRequestGetCommand:
    """Test cases for `repository pull-request get`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_get_success(self, mock_service_class):
        """Test getting one pull request."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_pull_request.return_value = _sample_pr()

        result = self.runner.invoke(app, ["pull-request", "get", PR_RID])

        assert result.exit_code == 0
        mock_service.get_pull_request.assert_called_once_with(PR_RID)

    @patch("pltr.commands.repository.RepositoryService")
    def test_get_json_format(self, mock_service_class):
        """Test get with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_pull_request.return_value = _sample_pr()

        result = self.runner.invoke(
            app, ["pull-request", "get", PR_RID, "--format", "json"]
        )

        assert result.exit_code == 0
        assert PR_RID in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_get_not_found(self, mock_service_class):
        """Test get when no pull request exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_pull_request.side_effect = PullRequestNotFoundError(
            f"No pull request found for RID {PR_RID}"
        )

        result = self.runner.invoke(app, ["pull-request", "get", PR_RID])

        assert result.exit_code == 1
        assert "No pull request found" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_get_error(self, mock_service_class):
        """Test get error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_pull_request.side_effect = Exception("service unavailable")

        result = self.runner.invoke(app, ["pull-request", "get", PR_RID])

        assert result.exit_code == 1
        assert "Error getting pull request" in result.stdout
