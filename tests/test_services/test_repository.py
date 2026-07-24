"""
Tests for the read-only repository (pull-request) service.
"""

import pytest
from unittest.mock import Mock, patch

from pltr.services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
    RepositoryService,
)

REPO_RID = "ri.stemma.main.repository.00000000-0000-0000-0000-000000000014"
OTHER_REPO_RID = "ri.stemma.main.repository.00000000-0000-0000-0000-000000000005"
PR_RID = "ri.pull-request.main.pull-request.00000000-0000-0000-0000-000000000012"


def _sample_pr(rid=PR_RID, repo=REPO_RID):
    return {
        "rid": rid,
        "baseRepositoryRid": repo,
        "headRepositoryRid": repo,
        "baseBranchName": "refs/heads/master",
        "headCommitish": "refs/heads/fix/example",
        "author": "dev@example.com",
        "createdAt": "2020-01-01T00:00:00.000Z",
        "currentRecord": {
            "status": "CLOSED",
            "merged": True,
            "title": "fix: example",
        },
    }


class TestListPullRequests:
    """Test cases for read-only pull-request listing."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_all_pull_requests(self, mock_client_class):
        """Test listing pull requests without a repository filter."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"values": [_sample_pr()]},
            '{"values": [...]}',
        )

        service = RepositoryService(profile="test")
        result = service.list_pull_requests()

        assert result == [_sample_pr()]
        mock_client_class.assert_called_once_with("test")
        mock_client.conjure.assert_called_once_with(
            "GET",
            "stemma-pull-request/api/pulls",
            request_timeout=RepositoryService.PULL_REQUEST_LIST_TIMEOUT,
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_filters_client_side_by_repository(self, mock_client_class):
        """Test client-side repository filtering (server ignores the param)."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {
                "values": [
                    _sample_pr(rid="ri.pull-request.main.pull-request.aaa"),
                    _sample_pr(
                        rid="ri.pull-request.main.pull-request.bbb",
                        repo=OTHER_REPO_RID,
                    ),
                ]
            },
            "{}",
        )

        service = RepositoryService(profile="test")
        result = service.list_pull_requests(REPO_RID)

        assert [entry["rid"] for entry in result] == [
            "ri.pull-request.main.pull-request.aaa"
        ]

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_unverified_shape_fails_loudly(self, mock_client_class):
        """Test that a non-envelope list response fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, [_sample_pr()], "[...]")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="Unverified"):
            service.list_pull_requests()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_entry_without_rid_fails_loudly(self, mock_client_class):
        """Test that a malformed entry fails loudly instead of rendering."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"values": [{"noRid": True}]}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="Unverified"):
            service.list_pull_requests()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_route_not_mounted(self, mock_client_class):
        """Test a clear error when the API is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            '{"errorName": "Route:RouteNotMounted"}',
        )

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.list_pull_requests()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_http_error(self, mock_client_class):
        """Test that non-2xx responses fail loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (500, "boom", "boom")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 500"):
            service.list_pull_requests()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_list_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("read timed out")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to list pull requests"):
            service.list_pull_requests()


class TestGetPullRequest:
    """Test cases for read-only pull-request get."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_get_pull_request_success(self, mock_client_class):
        """Test fetching one pull request by RID."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = _sample_pr()
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = RepositoryService(profile="test")
        result = service.get_pull_request(PR_RID)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "GET", f"stemma-pull-request/api/pulls/{PR_RID}"
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_get_pull_request_404_is_not_found(self, mock_client_class):
        """Test that a 404 maps to a not-found error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (404, "", "")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestNotFoundError, match="No pull request found"):
            service.get_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_get_pull_request_empty_payload_is_not_found(self, mock_client_class):
        """Test that an empty 2xx payload fails as not found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestNotFoundError, match="No pull request found"):
            service.get_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_get_pull_request_unverified_shape(self, mock_client_class):
        """Test that an object without a rid fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"unexpected": True}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="Unverified"):
            service.get_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_get_pull_request_http_error(self, mock_client_class):
        """Test that non-2xx responses fail loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (403, {"errorName": "Stemma:Denied"}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.get_pull_request(PR_RID)

    def test_without_profile_raises_before_network(self):
        """Test that a missing profile fails before any network call."""
        from pltr.auth.base import ProfileNotFoundError

        service = RepositoryService()
        with patch(
            "pltr.config.profiles.ProfileManager.get_active_profile",
            return_value=None,
        ):
            with pytest.raises(ProfileNotFoundError, match="No profile specified"):
                service.get_pull_request(PR_RID)
