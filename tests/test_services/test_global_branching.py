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


class TestGlobalBranchWriteService:
    """Test cases for Global Branch create-plan and close."""

    def test_plan_create_branch_no_network(self):
        """Test the create plan describes the request without a client."""
        service = GlobalBranchService(profile="test")
        plan = service.plan_create_branch(
            "my-branch", "desc", "ri.ontology.main.ontology.abc"
        )

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "POST"
        assert plan["request"]["path"] == "/branch-service/api/branch/create"
        assert plan["request"]["body"] == {
            "displayName": "my-branch",
            "description": "desc",
            "ontologyRid": "ri.ontology.main.ontology.abc",
        }
        assert "UNVERIFIED" in plan["contract"]

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_success(self, mock_client_class):
        """Test closing a branch returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"rid": BRANCH_RID, "status": "closed"}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = GlobalBranchService(profile="test")
        result = service.close_branch(BRANCH_RID)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "PUT", f"branch-service/api/branch/close/{BRANCH_RID}", json_body={}
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_empty_2xx_is_acknowledgment(self, mock_client_class):
        """Test an empty 2xx body maps to an explicit acknowledgment."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (204, "", "")

        service = GlobalBranchService(profile="test")
        result = service.close_branch(BRANCH_RID)

        assert result == {
            "rid": BRANCH_RID,
            "acknowledged": True,
            "response_empty": True,
        }

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_permission_denied_is_loud(self, mock_client_class):
        """Test that the verified 403 error contract surfaces loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Branch:PermissionDeniedError"},
            "{}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.close_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_not_found(self, mock_client_class):
        """Test that Branch:BranchNotFound maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Branch:BranchNotFound"},
            "{}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchNotFoundError, match="No branch found"):
            service.close_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_non_object_2xx_fails_loudly(self, mock_client_class):
        """Test that a non-object success payload is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["closed"], "[...]")

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="Unverified"):
            service.close_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_route_not_mounted(self, mock_client_class):
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
            service.close_branch(BRANCH_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_branch_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to PUT branch"):
            service.close_branch(BRANCH_RID)


class TestGlobalProposalWriteService:
    """Test cases for Global Proposal create-plan and close."""

    def test_plan_create_proposal_no_network(self):
        """Test the create plan describes the request without a client."""
        service = GlobalProposalService(profile="test")
        plan = service.plan_create_proposal(BRANCH_RID, "my-proposal", "desc")

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "POST"
        assert plan["request"]["path"] == "/branch-service/api/branch/proposal/create"
        assert plan["request"]["body"] == {
            "branchRid": BRANCH_RID,
            "description": "desc",
            "displayName": "my-proposal",
        }
        assert "UNVERIFIED" in plan["contract"]

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_proposal_success(self, mock_client_class):
        """Test closing a proposal returns the raw payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"rid": PROPOSAL_RID, "status": "closed"}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = GlobalProposalService(profile="test")
        result = service.close_proposal(PROPOSAL_RID)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"branch-service/api/branch/proposal/close/{PROPOSAL_RID}",
            json_body={},
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_proposal_not_found(self, mock_client_class):
        """Test that Branch:ProposalNotFound maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Branch:ProposalNotFound"},
            "{}",
        )

        service = GlobalProposalService(profile="test")
        with pytest.raises(GlobalBranchNotFoundError, match="No proposal found"):
            service.close_proposal(PROPOSAL_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_close_proposal_permission_denied_is_loud(self, mock_client_class):
        """Test that the verified 403 error contract surfaces loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Branch:PermissionDeniedError"},
            "{}",
        )

        service = GlobalProposalService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.close_proposal(PROPOSAL_RID)
