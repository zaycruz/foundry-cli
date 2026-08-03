from unittest.mock import Mock, patch

import pytest

from pltr.services.proposal import (
    MCP_VERIFIED_CAPABILITIES,
    SDK_REACHABLE_CAPABILITIES,
    ProposalAction,
    ProposalAuthenticationError,
    ProposalConflictError,
    ProposalRemoteServiceError,
    ProposalService,
    ProposalType,
    ProposalValidationError,
    UnsupportedProposalCapabilityError,
    normalize_proposal_error,
    parse_proposal_type,
)


def test_capability_matrix_distinguishes_mcp_from_sdk_reachability():
    assert (ProposalType.CODE_PR, ProposalAction.CREATE) in MCP_VERIFIED_CAPABILITIES
    assert (
        ProposalType.GLOBAL_PROPOSAL,
        ProposalAction.CLOSE,
    ) in MCP_VERIFIED_CAPABILITIES
    assert SDK_REACHABLE_CAPABILITIES == frozenset(
        {
            (ProposalType.CODE_PR, ProposalAction.CREATE),
            (ProposalType.CODE_PR, ProposalAction.LIST),
            (ProposalType.CODE_PR, ProposalAction.GET),
            (ProposalType.CODE_PR, ProposalAction.COMMENT),
            (ProposalType.CODE_PR, ProposalAction.CLOSE),
            (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CREATE),
            (ProposalType.GLOBAL_PROPOSAL, ProposalAction.GET),
            (ProposalType.GLOBAL_PROPOSAL, ProposalAction.CLOSE),
        }
    )


@pytest.mark.parametrize(
    ("method_name", "proposal_type", "args", "kwargs", "action"),
    [
        ("approve", ProposalType.CODE_PR, ("1",), {}, ProposalAction.APPROVE),
        (
            "request_changes",
            ProposalType.CODE_PR,
            ("1",),
            {},
            ProposalAction.REQUEST_CHANGES,
        ),
        ("merge", ProposalType.CODE_PR, ("1",), {}, ProposalAction.MERGE),
        (
            "list",
            ProposalType.GLOBAL_PROPOSAL,
            (),
            {"parent_rid": "ontology"},
            ProposalAction.LIST,
        ),
        (
            "comment",
            ProposalType.GLOBAL_PROPOSAL,
            ("gp", "note"),
            {},
            ProposalAction.COMMENT,
        ),
        ("approve", ProposalType.GLOBAL_PROPOSAL, ("gp",), {}, ProposalAction.APPROVE),
        (
            "request_changes",
            ProposalType.GLOBAL_PROPOSAL,
            ("gp",),
            {},
            ProposalAction.REQUEST_CHANGES,
        ),
        ("merge", ProposalType.GLOBAL_PROPOSAL, ("gp",), {}, ProposalAction.MERGE),
        ("accept", ProposalType.GLOBAL_PROPOSAL, ("gp",), {}, ProposalAction.ACCEPT),
    ],
)
def test_every_unreachable_operation_fails_before_client_access(
    method_name, proposal_type, args, kwargs, action
):
    service = ProposalService(profile="selected")
    service.auth_manager.get_client = Mock(
        side_effect=AssertionError("client accessed")
    )

    with pytest.raises(UnsupportedProposalCapabilityError) as exc_info:
        getattr(service, method_name)(proposal_type, *args, **kwargs)

    assert exc_info.value.action is action
    assert exc_info.value.proposal_type is proposal_type
    service.auth_manager.get_client.assert_not_called()


def test_unsupported_error_payload_is_stable():
    error = UnsupportedProposalCapabilityError(
        ProposalType.CODE_PR, ProposalAction.MERGE
    )

    assert error.exit_code == 6
    assert error.to_payload() == {
        "ok": False,
        "error": {
            "category": "unsupported-capability",
            "message": str(error),
            "proposal_type": "code-pr",
            "action": "merge",
        },
    }


def test_unsupported_error_message_names_the_missing_capability():
    error = UnsupportedProposalCapabilityError(
        ProposalType.GLOBAL_PROPOSAL, ProposalAction.LIST
    )

    assert "list is unavailable for global-proposal" in str(error)
    assert "no proposal list endpoint" in str(error)
    assert "no raw endpoint fallback is permitted" in str(error)


def test_capability_preflight_reports_requested_action_without_client_access():
    service = ProposalService(profile="selected")
    service.auth_manager.get_client = Mock(
        side_effect=AssertionError("client accessed")
    )

    with pytest.raises(UnsupportedProposalCapabilityError) as exc_info:
        service.require_capability(ProposalType.GLOBAL_PROPOSAL, ProposalAction.LIST)

    assert exc_info.value.action is ProposalAction.LIST
    service.auth_manager.get_client.assert_not_called()


def test_explicit_type_parser_accepts_only_documented_types():
    assert parse_proposal_type("code-pr") is ProposalType.CODE_PR
    assert parse_proposal_type("global-proposal") is ProposalType.GLOBAL_PROPOSAL
    with pytest.raises(ProposalValidationError):
        parse_proposal_type("infer-it")


@pytest.mark.parametrize(
    ("error", "expected_type"),
    [
        (
            type("UnauthorizedError", (Exception,), {})("no token"),
            ProposalAuthenticationError,
        ),
        (ValueError("bad provider response"), ProposalRemoteServiceError),
        (type("ConflictError", (Exception,), {})("changed"), ProposalConflictError),
    ],
)
def test_provider_errors_map_to_stable_categories(error, expected_type):
    assert isinstance(normalize_proposal_error(error), expected_type)


@pytest.fixture
def delegates():
    with (
        patch("pltr.services.proposal.RepositoryService") as repository_class,
        patch("pltr.services.proposal.GlobalProposalService") as global_proposal_class,
    ):
        yield repository_class, global_proposal_class


def test_create_code_pr_delegates_with_mapped_arguments(delegates):
    repository_class, _ = delegates
    repository_class.return_value.create_pull_request.return_value = {"rid": "pr-1"}
    service = ProposalService(profile="work")

    result = service.create(
        ProposalType.CODE_PR,
        parent_rid="repo-rid",
        title="Add feature",
        source_ref="refs/heads/feature",
        target_ref="refs/heads/main",
        description="details",
    )

    assert result == {"rid": "pr-1"}
    repository_class.assert_called_once_with(profile="work")
    repository_class.return_value.create_pull_request.assert_called_once_with(
        title="Add feature",
        base_repository_rid="repo-rid",
        head_commitish="refs/heads/feature",
        base_branch_name="refs/heads/main",
        description="details",
    )


def test_create_code_pr_defaults_target_ref_to_master(delegates):
    repository_class, _ = delegates
    service = ProposalService()

    service.create(
        ProposalType.CODE_PR,
        parent_rid="repo-rid",
        title="Add feature",
        source_ref="refs/heads/feature",
    )

    assert (
        repository_class.return_value.create_pull_request.call_args.kwargs[
            "base_branch_name"
        ]
        == "refs/heads/master"
    )


def test_create_plan_code_pr_delegates_without_mutating(delegates):
    repository_class, _ = delegates
    repository_class.return_value.create_pull_request_plan.return_value = {
        "status": "dry-run"
    }
    service = ProposalService()

    result = service.create_plan(
        ProposalType.CODE_PR,
        parent_rid="repo-rid",
        title="Add feature",
        source_ref="refs/heads/feature",
        target_ref="refs/heads/main",
        description="details",
    )

    assert result == {"status": "dry-run"}
    repository_class.return_value.create_pull_request_plan.assert_called_once_with(
        title="Add feature",
        base_repository_rid="repo-rid",
        head_commitish="refs/heads/feature",
        base_branch_name="refs/heads/main",
        description="details",
    )
    repository_class.return_value.create_pull_request.assert_not_called()


def test_create_global_proposal_maps_source_ref_and_target_ref(delegates):
    _, global_proposal_class = delegates
    global_proposal_class.return_value.create_proposal.return_value = {
        "proposalRid": "gp-1"
    }
    service = ProposalService(profile="work")

    result = service.create(
        ProposalType.GLOBAL_PROPOSAL,
        parent_rid="ontology-rid",
        title="Change schema",
        source_ref="ri.branch..branch.00000000-0000-0000-0000-000000000002",
        target_ref="main",
        description=None,
    )

    assert result == {"proposalRid": "gp-1"}
    global_proposal_class.assert_called_once_with(profile="work")
    global_proposal_class.return_value.create_proposal.assert_called_once_with(
        branch_rid="ri.branch..branch.00000000-0000-0000-0000-000000000002",
        display_name="Change schema",
        description="",
        merge_to="main",
    )


def test_create_global_proposal_defaults_merge_target_to_main(delegates):
    _, global_proposal_class = delegates
    service = ProposalService()

    service.create(
        ProposalType.GLOBAL_PROPOSAL,
        parent_rid="ontology-rid",
        title="Change schema",
        source_ref="branch-rid",
    )

    assert (
        global_proposal_class.return_value.create_proposal.call_args.kwargs["merge_to"]
        == "main"
    )


def test_create_plan_global_proposal_delegates_without_mutating(delegates):
    _, global_proposal_class = delegates
    global_proposal_class.return_value.plan_create_proposal.return_value = {
        "mode": "plan"
    }
    service = ProposalService()

    result = service.create_plan(
        ProposalType.GLOBAL_PROPOSAL,
        parent_rid="ontology-rid",
        title="Change schema",
        source_ref="branch-rid",
        description="details",
    )

    assert result == {"mode": "plan"}
    global_proposal_class.return_value.plan_create_proposal.assert_called_once_with(
        branch_rid="branch-rid",
        display_name="Change schema",
        description="details",
        merge_to="main",
    )
    global_proposal_class.return_value.create_proposal.assert_not_called()


def test_list_code_pr_delegates_with_repository_filter(delegates):
    repository_class, _ = delegates
    repository_class.return_value.list_pull_requests.return_value = [{"rid": "pr-1"}]
    service = ProposalService()

    result = service.list(ProposalType.CODE_PR, parent_rid="repo-rid")

    assert result == [{"rid": "pr-1"}]
    repository_class.return_value.list_pull_requests.assert_called_once_with("repo-rid")


@pytest.mark.parametrize("proposal_type", list(ProposalType))
def test_get_delegates_to_the_matching_sibling(delegates, proposal_type):
    repository_class, global_proposal_class = delegates
    service = ProposalService()

    service.get(proposal_type, "proposal-rid", parent_rid="ignored")

    if proposal_type is ProposalType.CODE_PR:
        repository_class.return_value.get_pull_request.assert_called_once_with(
            "proposal-rid"
        )
        global_proposal_class.assert_not_called()
    else:
        global_proposal_class.return_value.get_proposal.assert_called_once_with(
            "proposal-rid"
        )
        repository_class.assert_not_called()


def test_comment_code_pr_delegates(delegates):
    repository_class, _ = delegates
    service = ProposalService()

    service.comment(ProposalType.CODE_PR, "pr-1", "Looks good", parent_rid="repo")

    repository_class.return_value.create_pull_request_comment.assert_called_once_with(
        "pr-1", "Looks good"
    )


def test_comment_plan_code_pr_delegates_without_mutating(delegates):
    repository_class, _ = delegates
    service = ProposalService()

    service.comment_plan(ProposalType.CODE_PR, "pr-1", "Looks good")

    repository_class.return_value.create_pull_request_comment_plan.assert_called_once_with(
        "pr-1", "Looks good"
    )
    repository_class.return_value.create_pull_request_comment.assert_not_called()


@pytest.mark.parametrize("proposal_type", list(ProposalType))
def test_close_delegates_to_the_matching_sibling(delegates, proposal_type):
    repository_class, global_proposal_class = delegates
    service = ProposalService()

    service.close(proposal_type, "proposal-rid")

    if proposal_type is ProposalType.CODE_PR:
        repository_class.return_value.close_pull_request.assert_called_once_with(
            "proposal-rid"
        )
        global_proposal_class.assert_not_called()
    else:
        global_proposal_class.return_value.close_proposal.assert_called_once_with(
            "proposal-rid"
        )
        repository_class.assert_not_called()
