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

BRANCH_RID = "ri.branch..branch.00000000-0000-0000-0000-000000000002"
PROPOSAL_RID = "ri.branch..proposal.00000000-0000-0000-0000-000000000013"
ONTOLOGY_RID = "ri.ontology.main.ontology.00000000-0000-0000-0000-000000000003"
NAMESPACE_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000007"


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
            "description": "desc",
            "displayName": "my-branch",
            "ontologyRid": "ri.ontology.main.ontology.abc",
            "resourcesToAdd": [],
            "compassNamespaceRid": "<resolved-at-apply>",
        }
        assert "contract-verified" in plan["contract"]

    def test_plan_create_branch_with_resources(self):
        """Test the plan passes resource RID strings through as entries."""
        service = GlobalBranchService(profile="test")
        plan = service.plan_create_branch(
            "my-branch",
            "desc",
            "ri.ontology.main.ontology.abc",
            ["ri.foundry.main.dataset.aaa", "ri.foundry.main.dataset.bbb"],
        )

        assert plan["request"]["body"]["resourcesToAdd"] == [
            "ri.foundry.main.dataset.aaa",
            "ri.foundry.main.dataset.bbb",
        ]

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_resolve_compass_namespace(self, mock_client_class):
        """Test namespace resolution reads ontologies[rid].compassNamespaceRid."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
            "{...}",
        )

        service = GlobalBranchService(profile="test")
        result = service.resolve_compass_namespace(ONTOLOGY_RID)

        assert result == NAMESPACE_RID
        mock_client.conjure.assert_called_once_with(
            "POST",
            "ontology-metadata/api/ontology/v2/load/all",
            json_body={"externalMappingConfigurationFilters": []},
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_resolve_compass_namespace_missing_entry(self, mock_client_class):
        """Test a missing ontology entry fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"ontologies": {}}, "{...}")

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="compassNamespaceRid"):
            service.resolve_compass_namespace(ONTOLOGY_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_resolve_compass_namespace_missing_field(self, mock_client_class):
        """Test an entry without compassNamespaceRid fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"ontologies": {ONTOLOGY_RID: {"displayName": "x"}}},
            "{...}",
        )

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="compassNamespaceRid"):
            service.resolve_compass_namespace(ONTOLOGY_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_branch_success(self, mock_client_class):
        """Test create resolves the namespace, posts the verified body, parses the RID."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        branch_record = {
            "branchRid": BRANCH_RID,
            "displayName": "my-branch",
            "branchStatus": "OPEN",
        }
        mock_client.conjure.side_effect = [
            (
                200,
                {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
                "{...}",
            ),
            (200, {"branchRecord": branch_record}, "{...}"),
        ]

        service = GlobalBranchService(profile="test")
        result = service.create_branch("my-branch", "desc", ONTOLOGY_RID)

        assert result == {"branchRid": BRANCH_RID, "branchRecord": branch_record}
        assert mock_client.conjure.call_count == 2
        mock_client.conjure.assert_any_call(
            "POST",
            "ontology-metadata/api/ontology/v2/load/all",
            json_body={"externalMappingConfigurationFilters": []},
        )
        mock_client.conjure.assert_any_call(
            "POST",
            "branch-service/api/branch/create",
            json_body={
                "description": "desc",
                "displayName": "my-branch",
                "ontologyRid": ONTOLOGY_RID,
                "resourcesToAdd": [],
                "compassNamespaceRid": NAMESPACE_RID,
            },
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_branch_with_resources(self, mock_client_class):
        """Test create posts plain-string resourcesToAdd entries."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        branch_record = {
            "branchRid": BRANCH_RID,
            "displayName": "my-branch",
            "branchStatus": "OPEN",
        }
        mock_client.conjure.side_effect = [
            (
                200,
                {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
                "{...}",
            ),
            (200, {"branchRecord": branch_record}, "{...}"),
        ]

        service = GlobalBranchService(profile="test")
        result = service.create_branch(
            "my-branch", "desc", ONTOLOGY_RID, ["ri.foundry.main.dataset.aaa"]
        )

        assert result == {"branchRid": BRANCH_RID, "branchRecord": branch_record}
        mock_client.conjure.assert_any_call(
            "POST",
            "branch-service/api/branch/create",
            json_body={
                "description": "desc",
                "displayName": "my-branch",
                "ontologyRid": ONTOLOGY_RID,
                "resourcesToAdd": ["ri.foundry.main.dataset.aaa"],
                "compassNamespaceRid": NAMESPACE_RID,
            },
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_branch_wrong_rid_prefix_fails_loudly(self, mock_client_class):
        """Test a non ri.branch..branch. create RID is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (
                200,
                {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
                "{...}",
            ),
            (
                200,
                {
                    "branchRecord": {
                        "branchRid": "ri.global-branch.main.branch."
                        "00000000-0000-0000-0000-000000000002"
                    }
                },
                "{...}",
            ),
        ]

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="ri.branch..branch."):
            service.create_branch("my-branch", "desc", ONTOLOGY_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_branch_missing_record_fails_loudly(self, mock_client_class):
        """Test a create response without branchRecord is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (
                200,
                {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
                "{...}",
            ),
            (200, {"unexpected": True}, "{...}"),
        ]

        service = GlobalBranchService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="branchRecord.branchRid"):
            service.create_branch("my-branch", "desc", ONTOLOGY_RID)

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_branch_http_error_is_loud(self, mock_client_class):
        """Test a non-2xx create surfaces the status and error name."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (
                200,
                {"ontologies": {ONTOLOGY_RID: {"compassNamespaceRid": NAMESPACE_RID}}},
                "{...}",
            ),
            (400, {"errorName": "Default:InvalidArgument"}, "{...}"),
        ]

        service = GlobalBranchService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 400"):
            service.create_branch("my-branch", "desc", ONTOLOGY_RID)

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


class TestBuildMergeTo:
    """Test cases for the ProposalMergeTo union encoding."""

    TARGET_RID = "ri.branch..branch.99999999-8888-7777-6666-555555555555"

    def test_main_arm(self):
        """Test 'main' encodes as {"main": {}, "type": "main"}."""
        assert GlobalProposalService.build_merge_to("main") == {
            "main": {},
            "type": "main",
        }

    def test_main_arm_returns_a_copy(self):
        """Test the shared MERGE_TO_MAIN dict is not leaked to callers."""
        encoded = GlobalProposalService.build_merge_to("main")
        encoded["main"]["mutated"] = True
        assert GlobalProposalService.MERGE_TO_MAIN == {"main": {}, "type": "main"}

    def test_branch_rid_arm(self):
        """Test a branch RID encodes as {"branchRid": rid, "type": "branchRid"}."""
        assert GlobalProposalService.build_merge_to(self.TARGET_RID) == {
            "branchRid": self.TARGET_RID,
            "type": "branchRid",
        }

    def test_invalid_target_fails_loudly(self):
        """Test anything else raises before any network request."""
        with pytest.raises(ValueError, match="Invalid merge target"):
            GlobalProposalService.build_merge_to("bogus")

    def test_wrong_rid_prefix_fails_loudly(self):
        """Test a non-branch RID is rejected as a merge target."""
        with pytest.raises(ValueError, match="Invalid merge target"):
            GlobalProposalService.build_merge_to(
                "ri.ontology.main.ontology.00000000-0000-0000-0000-000000000003"
            )


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
            "displayName": "my-proposal",
            "description": "desc",
            "mergeTo": {"main": {}, "type": "main"},
        }
        assert "contract-verified" in plan["contract"]

    def test_plan_create_proposal_merge_to_branch_rid(self):
        """Test the plan encodes a branch-RID merge target as the union arm."""
        service = GlobalProposalService(profile="test")
        target_rid = "ri.branch..branch.99999999-8888-7777-6666-555555555555"
        plan = service.plan_create_proposal(
            BRANCH_RID, "my-proposal", "desc", merge_to=target_rid
        )

        assert plan["request"]["body"]["mergeTo"] == {
            "branchRid": target_rid,
            "type": "branchRid",
        }

    def test_plan_create_proposal_invalid_merge_to(self):
        """Test an invalid merge target fails before any network request."""
        service = GlobalProposalService(profile="test")
        with pytest.raises(ValueError, match="Invalid merge target"):
            service.plan_create_proposal(
                BRANCH_RID, "my-proposal", "desc", merge_to="bogus"
            )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_proposal_success(self, mock_client_class):
        """Test create posts the verified union body and parses the RID."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        proposal_record = {
            "proposalRid": PROPOSAL_RID,
            "proposalBranchRid": BRANCH_RID,
            "proposalStatus": "OPEN",
        }
        mock_client.conjure.return_value = (
            200,
            {"proposal": proposal_record},
            "{...}",
        )

        service = GlobalProposalService(profile="test")
        result = service.create_proposal(BRANCH_RID, "my-proposal", "desc")

        assert result == {"proposalRid": PROPOSAL_RID, "proposal": proposal_record}
        mock_client.conjure.assert_called_once_with(
            "POST",
            "branch-service/api/branch/proposal/create",
            json_body={
                "branchRid": BRANCH_RID,
                "displayName": "my-proposal",
                "description": "desc",
                "mergeTo": {"main": {}, "type": "main"},
            },
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_proposal_merge_to_branch_rid(self, mock_client_class):
        """Test create posts the branchRid union arm for a branch target."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        proposal_record = {
            "proposalRid": PROPOSAL_RID,
            "proposalBranchRid": BRANCH_RID,
            "proposalStatus": "OPEN",
        }
        mock_client.conjure.return_value = (
            200,
            {"proposal": proposal_record},
            "{...}",
        )

        target_rid = "ri.branch..branch.99999999-8888-7777-6666-555555555555"
        service = GlobalProposalService(profile="test")
        result = service.create_proposal(
            BRANCH_RID, "my-proposal", "desc", merge_to=target_rid
        )

        assert result == {"proposalRid": PROPOSAL_RID, "proposal": proposal_record}
        mock_client.conjure.assert_called_once_with(
            "POST",
            "branch-service/api/branch/proposal/create",
            json_body={
                "branchRid": BRANCH_RID,
                "displayName": "my-proposal",
                "description": "desc",
                "mergeTo": {"branchRid": target_rid, "type": "branchRid"},
            },
        )

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_proposal_wrong_rid_prefix_fails_loudly(self, mock_client_class):
        """Test a non ri.branch..proposal. create RID is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"proposal": {"proposalRid": "ri.global-proposal.main.proposal.abc"}},
            "{...}",
        )

        service = GlobalProposalService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="ri.branch..proposal."):
            service.create_proposal(BRANCH_RID, "my-proposal", "desc")

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_proposal_missing_record_fails_loudly(self, mock_client_class):
        """Test a create response without proposal is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"unexpected": True}, "{...}")

        service = GlobalProposalService(profile="test")
        with pytest.raises(GlobalBranchShapeError, match="proposal.proposalRid"):
            service.create_proposal(BRANCH_RID, "my-proposal", "desc")

    @patch("pltr.services.global_branching.FoundryInternalClient")
    def test_create_proposal_http_error_is_loud(self, mock_client_class):
        """Test a non-2xx create surfaces the status and error name."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            400,
            {"errorName": "Default:InvalidArgument"},
            "{...}",
        )

        service = GlobalProposalService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 400"):
            service.create_proposal(BRANCH_RID, "my-proposal", "desc")

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
