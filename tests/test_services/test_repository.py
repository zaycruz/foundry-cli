"""
Tests for the read-only repository (pull-request) service.
"""

import pytest
from unittest.mock import Mock, patch

from pltr.services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
    RepositoryCloneError,
    RepositoryNotFoundError,
    RepositoryService,
    RepositoryShapeError,
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


REPO_GET = {"rid": REPO_RID, "sourceRid": None}
COMPASS_GET = {"rid": REPO_RID, "name": "example_repo", "path": "/example/Apps/example_repo"}
HEAD_GET = {
    "commitish": "refs/heads/master",
    "peeledCommitHash": "1c4aa0d9eb1fbbe1da28cece1eac08434432467c",
}
BRANCHES_GET = {
    "values": [
        {
            "commitHash": "1c4aa0d9eb1fbbe1da28cece1eac08434432467c",
            "name": "refs/heads/master",
            "globalBranch": None,
        }
    ]
}
TAGS_GET = [{"name": "refs/tags/0.3.0", "commitHash": "0c5737f2", "message": ""}]
TREE_GET = {
    "metadata": {
        "": {"type": "DIRECTORY", "name": "", "path": ""},
        "README.md": {"type": "FILE", "name": "README.md", "path": "README.md"},
    }
}


def _context_responses(tree=TREE_GET):
    """Ordered conjure responses for get_repository_context."""
    return [
        (200, REPO_GET, "{}"),
        (200, COMPASS_GET, "{}"),
        (200, HEAD_GET, "{}"),
        (200, BRANCHES_GET, "{}"),
        (200, TAGS_GET, "[]"),
        (200, tree, "{}"),
    ]


class TestGetRepositoryContext:
    """Test cases for read-only repository context."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_context_success(self, mock_client_class):
        """Test the composed context aggregates all verified reads."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = _context_responses()

        service = RepositoryService(profile="test")
        context = service.get_repository_context(REPO_RID)

        assert context["repository"]["rid"] == REPO_RID
        assert context["repository"]["compass"]["name"] == "example_repo"
        assert context["default_branch"]["commitish"] == "refs/heads/master"
        assert context["refs"]["branches"][0]["name"] == "refs/heads/master"
        assert context["refs"]["tags"][0]["name"] == "refs/tags/0.3.0"
        tree = context["tree"]
        assert tree["requested_ref"] == "refs/heads/master"
        assert "silently falls back" in tree["ref_note"]
        assert [entry["path"] for entry in tree["entries"]] == ["", "README.md"]
        # Tree at the default branch forwards the head commitish as ?ref=
        tree_call = mock_client.conjure.call_args_list[-1]
        assert tree_call.args[1].endswith(
            "paths/tree/?ref=refs/heads/master"
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_context_explicit_ref_and_path(self, mock_client_class):
        """Test that an explicit ref and subtree path reach the endpoint."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = _context_responses()

        service = RepositoryService(profile="test")
        context = service.get_repository_context(
            REPO_RID, path="src", ref="refs/tags/0.3.0"
        )

        assert context["tree"]["requested_ref"] == "refs/tags/0.3.0"
        tree_call = mock_client.conjure.call_args_list[-1]
        assert "paths/tree/src?ref=refs/tags/0.3.0" in tree_call.args[1]

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_context_no_tree(self, mock_client_class):
        """Test that include_tree=False skips the tree read."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = _context_responses()[:5]

        service = RepositoryService(profile="test")
        context = service.get_repository_context(REPO_RID, include_tree=False)

        assert "tree" not in context
        assert mock_client.conjure.call_count == 5

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_context_repository_404_is_not_found(self, mock_client_class):
        """Test that a 404 on the repository get maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (404, "", "")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryNotFoundError, match="No repository found"):
            service.get_repository(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_repository_bad_shape_fails_loudly(self, mock_client_class):
        """Test that a repository object without a rid fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"unexpected": True}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.get_repository(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_head_bad_shape_fails_loudly(self, mock_client_class):
        """Test that a head object without a commitish fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"head": "master"}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.get_head(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_branches_non_envelope_fails_loudly(self, mock_client_class):
        """Test that a bare-array branches response fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, [{"name": "refs/heads/x"}], "[]")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.list_branches(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_tags_non_array_fails_loudly(self, mock_client_class):
        """Test that an enveloped tags response fails loudly (tags is bare)."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"values": []}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.list_tags(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_tree_entry_without_type_fails_loudly(self, mock_client_class):
        """Test that a tree entry without a type fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"metadata": {"x": {"name": "x"}}},
            "{}",
        )

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.get_path_tree(REPO_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_tree_404_is_not_found(self, mock_client_class):
        """Test that a 404 tree read maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (404, "", "")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryNotFoundError, match="No path"):
            service.get_path_tree(REPO_RID, path="missing")

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_context_route_not_mounted(self, mock_client_class):
        """Test a clear error when the internal API is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            "{}",
        )

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="not mounted"):
            service.get_repository(REPO_RID)


class TestCloneRepository:
    """Test cases for local repository clone."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_resolve_clone_plan_verified_url(self, mock_client_class):
        """Test the clone plan uses the verified smart-HTTP URL form."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ):
            plan = service.resolve_clone_plan(REPO_RID, "/tmp/target")

        assert plan["git_url"] == f"https://foundry.example.com/stemma/git/{REPO_RID}"
        assert ".git" not in plan["git_url"]
        assert plan["default_branch"] == "refs/heads/master"
        assert plan["repository_name"] == "example_repo"

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_clone_dry_run_never_touches_subprocess(self, mock_client_class):
        """Test dry-run resolves the plan without running git."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ), patch("subprocess.run") as mock_run:
            plan = service.clone_repository(REPO_RID, "/tmp/target", dry_run=True)

        assert plan["status"] == "dry-run"
        assert plan["would_overwrite"] is False
        mock_run.assert_not_called()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_clone_refuses_nonempty_target_without_force(
        self, mock_client_class, tmp_path
    ):
        """Test a non-empty target is refused without force."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]
        (tmp_path / "existing.txt").write_text("keep me")

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ), patch("subprocess.run") as mock_run:
            with pytest.raises(RepositoryCloneError, match="refusing to overwrite"):
                service.clone_repository(REPO_RID, str(tmp_path))

        mock_run.assert_not_called()
        assert (tmp_path / "existing.txt").exists()

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_clone_success_passes_token_via_env_not_argv(
        self, mock_client_class, tmp_path
    ):
        """Test the token rides GIT_CONFIG_* env, never the command line."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]
        target = tmp_path / "clone-target"

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="", stdout="")
            plan = service.clone_repository(
                REPO_RID, str(target), branch="master"
            )

        assert plan["status"] == "cloned"
        cmd, kwargs = mock_run.call_args.args[0], mock_run.call_args.kwargs
        assert "secret-token" not in " ".join(cmd)
        assert cmd[:2] == ["git", "clone"]
        assert "--branch" in cmd and "master" in cmd
        env = kwargs["env"]
        assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
        assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer secret-token"
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_clone_failure_redacts_token(self, mock_client_class, tmp_path):
        """Test git stderr is redacted before surfacing."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]
        target = tmp_path / "clone-target"

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=128, stderr="fatal: auth failed for secret-token", stdout=""
            )
            with pytest.raises(RepositoryCloneError) as exc_info:
                service.clone_repository(REPO_RID, str(target))

        message = str(exc_info.value)
        assert "secret-token" not in message
        assert "[REDACTED]" in message

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_clone_requires_git_on_path(self, mock_client_class, tmp_path):
        """Test a missing git binary fails before any clone attempt."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, REPO_GET, "{}"),
            (200, COMPASS_GET, "{}"),
            (200, HEAD_GET, "{}"),
        ]

        service = RepositoryService(profile="test")
        with patch.object(
            RepositoryService,
            "_git_credentials",
            return_value=("https://foundry.example.com", "secret-token"),
        ), patch("shutil.which", return_value=None):
            with pytest.raises(RepositoryCloneError, match="git is not available"):
                service.clone_repository(REPO_RID, str(tmp_path / "t"))


FOLDER_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000011"
PROJECT_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000009"
PROJECT_PATH = "/example-111111/Shared Ontology"
NEW_REPO_RID = "ri.stemma.main.repository.00000000-0000-0000-0000-000000000010"

RESOLVE_PROJECT = (200, {FOLDER_RID: PROJECT_RID}, "{}")
PROJECT_V3 = (
    200,
    {
        PROJECT_RID: {
            "resource": {
                "rid": PROJECT_RID,
                "name": "Shared Ontology",
                "path": PROJECT_PATH,
            }
        }
    },
    "{}",
)
STEMMA_CREATE = (200, {"rid": NEW_REPO_RID, "sourceRid": None}, "{}")
BOOTSTRAP_DONE = (204, "", "")
NEW_HEAD = (
    200,
    {
        "commitish": "refs/heads/master",
        "peeledCommitHash": "9e376f7a08f35451e88079ac3e82ca5c76412397",
    },
    "{}",
)
NEW_BRANCHES = (
    200,
    {
        "values": [
            {
                "name": "refs/heads/master",
                "commitHash": "9e376f7a08f35451e88079ac3e82ca5c76412397",
                "globalBranch": None,
            }
        ]
    },
    "{}",
)
NEW_TAGS = (
    200,
    [
        {
            "name": "refs/tags/0.0.1",
            "commitHash": "9e376f7a08f35451e88079ac3e82ca5c76412397",
        }
    ],
    "[]",
)


class TestCreatePythonTransforms:
    """Test cases for Python transforms repository creation (verified)."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_plan_runs_read_only_preflight(self, mock_client_class):
        """Test the dry-run plan resolves the exact verified write."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [RESOLVE_PROJECT, PROJECT_V3]

        service = RepositoryService(profile="test")
        plan = service.create_python_transforms_plan(
            "test-pull-request-1", FOLDER_RID
        )

        assert plan["status"] == "dry-run"
        assert plan["project_rid"] == PROJECT_RID
        stemma_call, bootstrap_call = plan["intended_calls"]
        assert stemma_call == {
            "endpoint": "POST /stemma/api/repos",
            "body": {"path": f"{PROJECT_PATH}/test-pull-request-1"},
        }
        assert bootstrap_call["body"] == {
            "parentTemplateId": "transforms",
            "childTemplateIdsByPath": {"transforms-python": "python"},
            "templateTokens": {},
        }
        assert plan["contract"] == "VERIFIED"
        assert "repo-create.md" in plan["evidence"]
        resolve_call, path_call = mock_client.conjure.call_args_list
        assert resolve_call.args[0] == "PUT"
        assert resolve_call.args[1] == (
            "compass/api/hierarchy/v2/batch/resources/projects"
        )
        assert resolve_call.kwargs["json_body"] == [FOLDER_RID]
        assert path_call.args[1] == "compass/api/hierarchy/v2/batch/projects-v3"
        assert path_call.kwargs["json_body"] == {
            "decorations": ["path"],
            "includeOperations": False,
            "rids": [PROJECT_RID],
        }

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_create_posts_verified_chain_and_verifies_refs(self, mock_client_class):
        """Test --apply posts stemma + bootstrap, then reads the refs back."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            PROJECT_V3,
            STEMMA_CREATE,
            BOOTSTRAP_DONE,
            NEW_HEAD,
            NEW_BRANCHES,
            NEW_TAGS,
        ]

        service = RepositoryService(profile="test")
        result = service.create_python_transforms_repository(
            "test-pull-request-1", FOLDER_RID
        )

        assert result["status"] == "created"
        assert result["repository"] == {"rid": NEW_REPO_RID, "sourceRid": None}
        assert result["compass_path"] == f"{PROJECT_PATH}/test-pull-request-1"
        assert result["bootstrap"]["status"] == "applied"
        assert result["verification"]["bootstrap_verified"] is True
        assert result["verification"]["default_branch"]["commitish"] == (
            "refs/heads/master"
        )

        calls = mock_client.conjure.call_args_list
        stemma_call = calls[2]
        assert stemma_call.args[:2] == ("POST", "stemma/api/repos")
        assert stemma_call.kwargs["json_body"] == {
            "path": f"{PROJECT_PATH}/test-pull-request-1"
        }
        bootstrap_call = calls[3]
        assert bootstrap_call.args[0] == "POST"
        assert bootstrap_call.args[1] == (
            f"repository-bootstrapper/api/repos/{NEW_REPO_RID}/bootstrap"
        )
        assert bootstrap_call.kwargs["json_body"] == (
            RepositoryService.PYTHON_TRANSFORMS_BOOTSTRAP_BODY
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_folder_without_enclosing_project_fails_loudly(self, mock_client_class):
        """Test a folder with no project mapping fails before any write."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="No enclosing project"):
            service.create_python_transforms_plan("x", FOLDER_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_resolve_non_mapping_fails_loudly(self, mock_client_class):
        """Test a non-object resolve response fails as unverified shape."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, [PROJECT_RID], "[]")

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.resolve_enclosing_project(FOLDER_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_project_v3_without_path_fails_loudly(self, mock_client_class):
        """Test a projects-v3 entry without resource.path fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            (200, {PROJECT_RID: {"resource": {"rid": PROJECT_RID}}}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="Unverified"):
            service.create_python_transforms_plan("x", FOLDER_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_stemma_create_http_error_fails_loudly(self, mock_client_class):
        """Test a non-2xx stemma create surfaces the HTTP status."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            PROJECT_V3,
            (403, {"errorName": "Compass:InsufficientPermissions"}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.create_python_transforms_repository("x", FOLDER_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_stemma_create_bad_shape_fails_loudly(self, mock_client_class):
        """Test a create response without a rid fails with reconcile guidance."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            PROJECT_V3,
            (200, {"unexpected": True}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RepositoryShapeError, match="reconcile"):
            service.create_python_transforms_repository("x", FOLDER_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_bootstrap_failure_reports_created_repo(self, mock_client_class):
        """Test a bootstrap failure names the already-created repository."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            PROJECT_V3,
            STEMMA_CREATE,
            (500, {"errorName": "Default:Internal"}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="bootstrapper call failed") as exc_info:
            service.create_python_transforms_repository("x", FOLDER_RID)

        assert NEW_REPO_RID in str(exc_info.value)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_verification_read_failure_does_not_hide_created_repo(
        self, mock_client_class
    ):
        """Test a failed read-back still returns the created repository."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            RESOLVE_PROJECT,
            PROJECT_V3,
            STEMMA_CREATE,
            BOOTSTRAP_DONE,
            NEW_HEAD,
            NEW_BRANCHES,
            Exception("read timed out"),
        ]

        service = RepositoryService(profile="test")
        result = service.create_python_transforms_repository("x", FOLDER_RID)

        assert result["status"] == "created"
        assert result["repository"]["rid"] == NEW_REPO_RID
        verification = result["verification"]
        assert verification["bootstrap_verified"] is None
        assert "read timed out" in verification["verification_error"]


class TestCreatePullRequest:
    """Test cases for pull-request creation (verified contract)."""

    def test_plan_is_dry_run_with_verified_body(self):
        """Test the plan shows the exact verified write without posting."""
        service = RepositoryService(profile="test")
        plan = service.create_pull_request_plan(
            title="test-pull-request-1",
            base_repository_rid=REPO_RID,
            head_commitish="refs/heads/feat/x",
        )

        assert plan["status"] == "dry-run"
        assert plan["intended_endpoint"] == "POST /stemma-pull-request/api/pulls"
        body = plan["intended_body"]
        assert body == {
            "title": "test-pull-request-1",
            "baseRepositoryRid": REPO_RID,
            "headRepositoryRid": REPO_RID,
            "baseBranchName": "refs/heads/master",
            "headCommitish": "refs/heads/feat/x",
        }
        assert plan["contract"] == "VERIFIED"
        assert "pr-write-probes.jsonl" in plan["evidence"]

    def test_plan_forwards_optional_fields(self):
        """Test head repository, base branch, and description reach the body."""
        service = RepositoryService(profile="test")
        plan = service.create_pull_request_plan(
            title="t",
            base_repository_rid=REPO_RID,
            head_commitish="refs/heads/feat/x",
            head_repository_rid=OTHER_REPO_RID,
            base_branch_name="refs/heads/main",
            description="disposable",
        )

        body = plan["intended_body"]
        assert body["headRepositoryRid"] == OTHER_REPO_RID
        assert body["baseBranchName"] == "refs/heads/main"
        assert body["description"] == "disposable"

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_create_posts_plan_body_verbatim(self, mock_client_class):
        """Test the real create posts exactly the dry-run body."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, _sample_pr(), "{...}")

        service = RepositoryService(profile="test")
        result = service.create_pull_request(
            title="test-pull-request-1",
            base_repository_rid=REPO_RID,
            head_commitish="refs/heads/feat/x",
        )

        assert result == _sample_pr()
        mock_client.conjure.assert_called_once_with(
            "POST",
            "stemma-pull-request/api/pulls",
            json_body={
                "title": "test-pull-request-1",
                "baseRepositoryRid": REPO_RID,
                "headRepositoryRid": REPO_RID,
                "baseBranchName": "refs/heads/master",
                "headCommitish": "refs/heads/feat/x",
            },
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_create_unverified_shape_fails_loudly(self, mock_client_class):
        """Test a response without a rid fails loudly with reconcile guidance."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"unexpected": True}, "{}")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="reconcile"):
            service.create_pull_request(
                title="t",
                base_repository_rid=REPO_RID,
                head_commitish="refs/heads/feat/x",
            )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_create_http_error_fails_loudly(self, mock_client_class):
        """Test a non-2xx create response fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "StemmaPullRequest:CannotCreatePullRequest"},
            "{}",
        )

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.create_pull_request(
                title="t",
                base_repository_rid=REPO_RID,
                head_commitish="refs/heads/feat/x",
            )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_create_transport_error_wrapped(self, mock_client_class):
        """Test transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("read timed out")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to create pull request"):
            service.create_pull_request(
                title="t",
                base_repository_rid=REPO_RID,
                head_commitish="refs/heads/feat/x",
            )


class TestCreatePullRequestComment:
    """Test cases for pull-request global comments (verified contract)."""

    def test_plan_is_dry_run_with_verified_body(self):
        """Test the plan shows the exact verified write without posting."""
        service = RepositoryService(profile="test")
        plan = service.create_pull_request_comment_plan(PR_RID, "hello")

        assert plan["status"] == "dry-run"
        assert plan["intended_endpoint"] == (
            f"POST /stemma-pull-request/api/pulls/{PR_RID}/comments/global"
        )
        assert plan["intended_body"] == {"content": "hello"}
        assert plan["contract"] == "VERIFIED"
        assert "pr-write-probes.jsonl" in plan["evidence"]

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_comment_posts_verified_body(self, mock_client_class):
        """Test the real comment create posts {"content": ...} verbatim."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        created = {
            "rid": "ri.pull-request.main.pull-request-comment.abc",
            "content": "hello",
        }
        mock_client.conjure.return_value = (200, created, "{...}")

        service = RepositoryService(profile="test")
        result = service.create_pull_request_comment(PR_RID, "hello")

        assert result == created
        mock_client.conjure.assert_called_once_with(
            "POST",
            f"stemma-pull-request/api/pulls/{PR_RID}/comments/global",
            json_body={"content": "hello"},
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_comment_unverified_shape_fails_loudly(self, mock_client_class):
        """Test a response without a rid fails loudly with reconcile guidance."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["not", "an", "object"], "[]")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="reconcile"):
            service.create_pull_request_comment(PR_RID, "hello")

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_comment_http_error_fails_loudly(self, mock_client_class):
        """Test a non-2xx comment response fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            403,
            {"errorName": "Comments:NotPermittedToWriteComment"},
            "{}",
        )

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 403"):
            service.create_pull_request_comment(PR_RID, "hello")

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_comment_transport_error_wrapped(self, mock_client_class):
        """Test transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("read timed out")

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to comment on pull request"):
            service.create_pull_request_comment(PR_RID, "hello")


def _open_pr(rid=PR_RID, title="test-pull-request-1"):
    return {
        "rid": rid,
        "baseRepositoryRid": REPO_RID,
        "headRepositoryRid": REPO_RID,
        "baseBranchName": "refs/heads/master",
        "headCommitish": "refs/heads/feat/x",
        "currentRecord": {
            "status": "OPEN",
            "merged": False,
            "title": title,
        },
    }


class TestClosePullRequest:
    """Test cases for pull-request close (verified contract)."""

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_plan_reads_pr_and_shows_verified_body(self, mock_client_class):
        """Test the plan reads the PR for its title and never PUTs."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, _open_pr(), "{...}")

        service = RepositoryService(profile="test")
        plan = service.close_pull_request_plan(PR_RID)

        assert plan["status"] == "dry-run"
        assert plan["current_status"] == "OPEN"
        assert plan["already_closed"] is False
        assert plan["intended_endpoint"] == (
            f"PUT /stemma-pull-request/api/pulls/{PR_RID}/update"
        )
        assert plan["intended_body"] == {
            "title": "test-pull-request-1",
            "status": "CLOSED",
        }
        assert plan["contract"] == "VERIFIED"
        assert "pr-write-verification.md" in plan["evidence"]
        mock_client.conjure.assert_called_once_with(
            "GET", f"stemma-pull-request/api/pulls/{PR_RID}"
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_gets_then_puts_exact_body(self, mock_client_class):
        """Test the real close reads the PR, PUTs the verified body, reads back."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        closed_pr = _open_pr()
        closed_pr["currentRecord"] = {
            "status": "CLOSED",
            "merged": False,
            "title": "test-pull-request-1",
        }
        mock_client.conjure.side_effect = [
            (200, _open_pr(), "{...}"),
            (200, closed_pr, "{...}"),
            (200, closed_pr, "{...}"),
        ]

        service = RepositoryService(profile="test")
        result = service.close_pull_request(PR_RID)

        assert result["status"] == "closed"
        assert result["pull_request"]["rid"] == PR_RID
        assert result["verification"] == {
            "status": "CLOSED",
            "merged": False,
            "close_verified": True,
        }
        calls = mock_client.conjure.call_args_list
        assert calls[0].args[:2] == (
            "GET",
            f"stemma-pull-request/api/pulls/{PR_RID}",
        )
        assert calls[1].args[:2] == (
            "PUT",
            f"stemma-pull-request/api/pulls/{PR_RID}/update",
        )
        assert calls[1].kwargs["json_body"] == {
            "title": "test-pull-request-1",
            "status": "CLOSED",
        }
        assert calls[2].args[:2] == (
            "GET",
            f"stemma-pull-request/api/pulls/{PR_RID}",
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_already_closed_never_puts(self, mock_client_class):
        """Test an already-CLOSED pull request is reported, not re-closed."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, _sample_pr(), "{...}")

        service = RepositoryService(profile="test")
        result = service.close_pull_request(PR_RID)

        assert result["status"] == "already-closed"
        assert result["current_status"] == "CLOSED"
        assert "no update was issued" in result["note"]
        mock_client.conjure.assert_called_once_with(
            "GET", f"stemma-pull-request/api/pulls/{PR_RID}"
        )

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_plan_flags_already_closed(self, mock_client_class):
        """Test the dry-run plan flags an already-CLOSED pull request."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, _sample_pr(), "{...}")

        service = RepositoryService(profile="test")
        plan = service.close_pull_request_plan(PR_RID)

        assert plan["already_closed"] is True
        assert plan["current_status"] == "CLOSED"
        assert plan["intended_body"] == {
            "title": "fix: example",
            "status": "CLOSED",
        }

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_missing_title_fails_loudly(self, mock_client_class):
        """Test a PR without currentRecord.title fails as unverified shape."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"rid": PR_RID}, "{...}")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="Unverified"):
            service.close_pull_request_plan(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_http_error_fails_loudly(self, mock_client_class):
        """Test a non-2xx close PUT surfaces the HTTP status."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, _open_pr(), "{...}"),
            (400, {"errorName": "Default:InvalidArgument"}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="HTTP 400"):
            service.close_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_unverified_shape_fails_loudly(self, mock_client_class):
        """Test a close response without a rid fails with reconcile guidance."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, _open_pr(), "{...}"),
            (200, {"unexpected": True}, "{}"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestShapeError, match="reconcile"):
            service.close_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_transport_error_wrapped(self, mock_client_class):
        """Test transport failures on the PUT are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (200, _open_pr(), "{...}"),
            Exception("read timed out"),
        ]

        service = RepositoryService(profile="test")
        with pytest.raises(RuntimeError, match="Failed to close pull request"):
            service.close_pull_request(PR_RID)

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_read_back_failure_does_not_hide_close(self, mock_client_class):
        """Test a failed read-back still reports the successful close."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        closed_pr = _open_pr()
        closed_pr["currentRecord"]["status"] = "CLOSED"
        mock_client.conjure.side_effect = [
            (200, _open_pr(), "{...}"),
            (200, closed_pr, "{...}"),
            Exception("read timed out"),
        ]

        service = RepositoryService(profile="test")
        result = service.close_pull_request(PR_RID)

        assert result["status"] == "closed"
        verification = result["verification"]
        assert verification["close_verified"] is None
        assert "read timed out" in verification["verification_error"]

    @patch("pltr.services.repository.FoundryInternalClient")
    def test_close_unknown_pr_is_not_found(self, mock_client_class):
        """Test closing a non-existent pull request maps to not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (404, "", "")

        service = RepositoryService(profile="test")
        with pytest.raises(PullRequestNotFoundError, match="No pull request found"):
            service.close_pull_request(PR_RID)
