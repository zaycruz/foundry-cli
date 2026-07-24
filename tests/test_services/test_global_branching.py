"""
Tests for the read-only Global Branching (branch-service) services.
"""

import pytest
from unittest.mock import Mock, patch

from pltr.services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchService,
    GlobalBranchShapeError,
    GlobalProposalService,
)

BRANCH_RID = "ri.global-branch.main.branch.00000000-0000-0000-0000-000000000002"
PROPOSAL_RID = "ri.global-proposal.main.proposal.00000000-0000-0000-0000-000000000013"


class TestGlobalBranchService:
    """Test cases for read-only Global Branch loads."""

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_success(self, mock_client_class):
        """Test loading a branch returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"rid": BRANCH_RID, "name": "my-branch"}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = GlobalBranchService(profile="test")
        result = service.get_branch(BRANCH_RID)

        assert result == payload
        mock_client_class.assert_called_once_with("test")
        mock_client.conjure.assert_called_once_with(
            "PUT", f"branch-service/api/branch/load/{BRANCH_RID}", json_body={}
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_not_found_error_name(self, mock_client_class):
        """Test that a Branch:BranchNotFound error maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Branch:BranchNotFound"},
            "{}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchNotFoundError, match="No branch found"):
            service.get_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_permission_denied_is_loud(self, mock_client_class):
        """Test that the verified 403 contract surfaces as a loud error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Branch:PermissionDeniedError"},
            "{}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.get_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_unverified_shape(self, mock_client_class):
        """Test that a non-object success payload fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["not", "an", "object"], "[...]")

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="Unverified"):
            service.get_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_empty_object_fails_loudly(self, mock_client_class):
        """Test that an empty object is not rendered as a result."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "")

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="Unverified"):
            service.get_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_route_not_mounted(self, mock_client_class):
        """Test a clear error when branch-service is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            "{}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.get_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_branch_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to load branch"):
            service.get_branch(BRANCH_RID)


class TestGlobalProposalService:
    """Test cases for read-only Global Proposal loads."""

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_proposal_success(self, mock_client_class):
        """Test loading a proposal returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"rid": PROPOSAL_RID, "title": "my-proposal"}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = GlobalProposalService(profile="test")
        result = service.get_proposal(PROPOSAL_RID)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"branch-service/api/branch/proposal/load/{PROPOSAL_RID}",
            json_body={},
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_proposal_not_found_error_name(self, mock_client_class):
        """Test that a Branch:ProposalNotFound error maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Branch:ProposalNotFound"},
            "{}",
        )

        service = GlobalProposalService(profile="test")
        with pytest.raises(GlobalBranchNotFoundError, match="No proposal found"):
            service.get_proposal(PROPOSAL_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_get_proposal_unverified_shape(self, mock_client_class):
        """Test that a non-object success payload fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, "a string", '"a string"')

        service = GlobalProposalService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="Unverified"):
            service.get_proposal(PROPOSAL_RID)

    def test_without_profile_raises_before_network(self):
        """Test that a missing profile fails before any network call."""
        from pltr.auth.base import ProfileNotFoundError

        service = GlobalProposalService()
        with patch(
            "pltr.config.profiles.ProfileManager.get_active_profile",
            return_value=None,
        ):
            with pytest.raises(ProfileNotFoundError, match="No profile specified"):
                service.get_proposal(PROPOSAL_RID)
