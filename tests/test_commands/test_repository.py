"""
Tests for the read-only repository pull-request commands.
"""

from unittest.mock import Mock, patch
from typer.testing import CliRunner

from pltr.commands.repository import app
from pltr.services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
    RepositoryCloneError,
    RepositoryNotFoundError,
    RepositoryShapeError,
)

REPO_RID = "ri.stemma.main.repository.00000000-0000-0000-0000-000000000014"
PR_RID = "ri.pull-request.main.pull-request.00000000-0000-0000-0000-000000000012"
FOLDER_RID = "ri.compass.main.folder.00000000-0000-0000-0000-000000000011"


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


def _sample_context():
    return {
        "repository": {
            "rid": REPO_RID,
            "sourceRid": None,
            "compass": {"name": "example_repo", "path": "/Example/Apps/example_repo"},
        },
        "default_branch": {"commitish": "refs/heads/master"},
        "refs": {"branches": [], "tags": []},
        "tree": {
            "path": "",
            "requested_ref": "refs/heads/master",
            "ref_note": "stemma silently falls back to the default-branch tree",
            "entries": [],
        },
    }


class TestContextCommand:
    """Test cases for `repository context`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_context_success(self, mock_service_class):
        """Test getting repository context."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_repository_context.return_value = _sample_context()

        result = self.runner.invoke(app, ["context", REPO_RID])

        assert result.exit_code == 0
        mock_service.get_repository_context.assert_called_once_with(
            REPO_RID, path="", ref=None, include_tree=True
        )

    @patch("pltr.commands.repository.RepositoryService")
    def test_context_json_format(self, mock_service_class):
        """Test context with JSON output."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_repository_context.return_value = _sample_context()

        result = self.runner.invoke(app, ["context", REPO_RID, "--format", "json"])

        assert result.exit_code == 0
        assert REPO_RID in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_context_options_forwarded(self, mock_service_class):
        """Test --path/--ref/--no-tree reach the service."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        context = _sample_context()
        del context["tree"]
        mock_service.get_repository_context.return_value = context

        result = self.runner.invoke(
            app,
            ["context", REPO_RID, "--path", "src", "--ref", "refs/tags/0.3.0",
             "--no-tree"],
        )

        assert result.exit_code == 0
        mock_service.get_repository_context.assert_called_once_with(
            REPO_RID, path="src", ref="refs/tags/0.3.0", include_tree=False
        )

    @patch("pltr.commands.repository.RepositoryService")
    def test_context_not_found(self, mock_service_class):
        """Test context when no repository exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_repository_context.side_effect = RepositoryNotFoundError(
            f"No repository found for RID {REPO_RID}"
        )

        result = self.runner.invoke(app, ["context", REPO_RID])

        assert result.exit_code == 1
        assert "No repository found" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_context_shape_error(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_repository_context.side_effect = RepositoryShapeError(
            "Unverified head response shape"
        )

        result = self.runner.invoke(app, ["context", REPO_RID])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout


class TestCloneCommand:
    """Test cases for `repository clone`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_clone_success(self, mock_service_class, tmp_path):
        """Test cloning into a fresh target directory."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.clone_repository.return_value = {
            "repository_rid": REPO_RID,
            "git_url": f"https://foundry.example.com/stemma/git/{REPO_RID}",
            "target_dir": str(tmp_path / "target"),
            "status": "cloned",
        }

        result = self.runner.invoke(
            app, ["clone", REPO_RID, str(tmp_path / "target")]
        )

        assert result.exit_code == 0
        mock_service.clone_repository.assert_called_once_with(
            REPO_RID,
            str(tmp_path / "target"),
            branch=None,
            force=False,
            dry_run=False,
        )

    @patch("pltr.commands.repository.RepositoryService")
    def test_clone_dry_run(self, mock_service_class, tmp_path):
        """Test --dry-run forwards and reports the plan."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.clone_repository.return_value = {
            "repository_rid": REPO_RID,
            "status": "dry-run",
            "would_overwrite": False,
        }

        result = self.runner.invoke(
            app,
            ["clone", REPO_RID, str(tmp_path / "target"), "--dry-run",
             "--format", "json"],
        )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        _, kwargs = mock_service.clone_repository.call_args
        assert kwargs["dry_run"] is True

    @patch("pltr.commands.repository.RepositoryService")
    def test_clone_refuses_overwrite(self, mock_service_class, tmp_path):
        """Test a non-empty target without --force fails loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.clone_repository.side_effect = RepositoryCloneError(
            "Target directory /x exists and is not empty; refusing to "
            "overwrite without --force"
        )
        (tmp_path / "keep.txt").write_text("data")

        result = self.runner.invoke(app, ["clone", REPO_RID, str(tmp_path)])

        assert result.exit_code == 1
        assert "refusing to overwrite" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_clone_error(self, mock_service_class, tmp_path):
        """Test generic clone error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.clone_repository.side_effect = Exception("network down")

        result = self.runner.invoke(
            app, ["clone", REPO_RID, str(tmp_path / "target")]
        )

        assert result.exit_code == 1
        assert "Error cloning repository" in result.stdout


class TestCreatePythonTransformsCommand:
    """Test cases for `repository create-python-transforms`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_default_is_dry_run_plan(self, mock_service_class):
        """Test the default posture prints the dry-run plan, never posts."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_python_transforms_plan.return_value = {
            "status": "dry-run",
            "name": "test-pull-request-1",
            "intended_calls": [
                {"endpoint": "POST /stemma/api/repos", "body": {"path": "/p/x"}}
            ],
            "contract": "VERIFIED",
            "evidence": "derived from the client contract 2026-07-25",
        }

        result = self.runner.invoke(
            app,
            [
                "create-python-transforms",
                "test-pull-request-1",
                "--parent-rid",
                FOLDER_RID,
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        mock_service.create_python_transforms_plan.assert_called_once_with(
            "test-pull-request-1", FOLDER_RID
        )
        mock_service.create_python_transforms_repository.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_apply_creates_and_reports_repository(self, mock_service_class):
        """Test --apply forwards to the real create and reports the rid."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_python_transforms_repository.return_value = {
            "status": "created",
            "name": "test-pull-request-1",
            "repository": {"rid": REPO_RID, "sourceRid": None},
            "verification": {"bootstrap_verified": True},
            "contract": "VERIFIED",
            "evidence": "derived from the client contract 2026-07-25",
        }

        result = self.runner.invoke(
            app,
            [
                "create-python-transforms",
                "test-pull-request-1",
                "--parent-rid",
                FOLDER_RID,
                "--apply",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert REPO_RID in result.stdout
        mock_service.create_python_transforms_repository.assert_called_once_with(
            "test-pull-request-1", FOLDER_RID
        )
        mock_service.create_python_transforms_plan.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_shape_error_fails_loudly(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_python_transforms_repository.side_effect = (
            RepositoryShapeError("Unverified repository create response shape")
        )

        result = self.runner.invoke(
            app,
            ["create-python-transforms", "x", "--parent-rid", FOLDER_RID, "--apply"],
        )

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_create_error(self, mock_service_class):
        """Test create error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_python_transforms_repository.side_effect = Exception(
            "HTTP 403"
        )

        result = self.runner.invoke(
            app,
            ["create-python-transforms", "x", "--parent-rid", FOLDER_RID, "--apply"],
        )

        assert result.exit_code == 1
        assert "Error creating Python transforms repository" in result.stdout

    def test_parent_rid_is_required(self):
        """Test the command refuses to run without a parent folder RID."""
        result = self.runner.invoke(app, ["create-python-transforms", "x"])

        assert result.exit_code == 2
        assert "--parent-rid" in result.output


class TestPullRequestCreateCommand:
    """Test cases for `repository pull-request create`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_default_is_dry_run_plan(self, mock_service_class):
        """Test the default posture prints the dry-run plan, never posts."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request_plan.return_value = {
            "status": "dry-run",
            "operation": "create_code_repository_pull_request",
            "intended_endpoint": "POST /stemma-pull-request/api/pulls",
            "intended_body": {"title": "t"},
            "contract": "VERIFIED",
            "evidence": "strict deserialization",
        }

        result = self.runner.invoke(
            app,
            [
                "pull-request",
                "create",
                "test-pull-request-1",
                "--base-repository-rid",
                REPO_RID,
                "--head-commitish",
                "refs/heads/feat/x",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        mock_service.create_pull_request_plan.assert_called_once_with(
            title="test-pull-request-1",
            base_repository_rid=REPO_RID,
            head_commitish="refs/heads/feat/x",
            head_repository_rid=None,
            base_branch_name="refs/heads/master",
            description=None,
        )
        mock_service.create_pull_request.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_apply_posts_verified_body(self, mock_service_class):
        """Test --apply forwards every option to the real create."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request.return_value = _sample_pr()

        result = self.runner.invoke(
            app,
            [
                "pull-request",
                "create",
                "test-pull-request-1",
                "--base-repository-rid",
                REPO_RID,
                "--head-commitish",
                "refs/heads/feat/x",
                "--head-repository-rid",
                REPO_RID,
                "--base-branch",
                "refs/heads/main",
                "--description",
                "disposable",
                "--apply",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert PR_RID in result.stdout
        mock_service.create_pull_request.assert_called_once_with(
            title="test-pull-request-1",
            base_repository_rid=REPO_RID,
            head_commitish="refs/heads/feat/x",
            head_repository_rid=REPO_RID,
            base_branch_name="refs/heads/main",
            description="disposable",
        )
        mock_service.create_pull_request_plan.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_create_shape_error(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request.side_effect = PullRequestShapeError(
            "Unverified pull-request create response shape"
        )

        result = self.runner.invoke(
            app,
            [
                "pull-request",
                "create",
                "t",
                "--base-repository-rid",
                REPO_RID,
                "--head-commitish",
                "refs/heads/feat/x",
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_create_error(self, mock_service_class):
        """Test create error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request.side_effect = Exception("HTTP 403")

        result = self.runner.invoke(
            app,
            [
                "pull-request",
                "create",
                "t",
                "--base-repository-rid",
                REPO_RID,
                "--head-commitish",
                "refs/heads/feat/x",
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "Error creating pull request" in result.stdout


class TestPullRequestCommentCommand:
    """Test cases for `repository pull-request comment`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pltr.commands.repository.RepositoryService")
    def test_default_is_dry_run_plan(self, mock_service_class):
        """Test the default posture prints the dry-run plan, never posts."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request_comment_plan.return_value = {
            "status": "dry-run",
            "operation": "create_code_repository_pull_request_comment",
            "pull_request_rid": PR_RID,
            "intended_body": {"content": "hello"},
            "contract": "VERIFIED",
            "evidence": "strict deserialization",
        }

        result = self.runner.invoke(
            app,
            ["pull-request", "comment", PR_RID, "hello", "--format", "json"],
        )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        mock_service.create_pull_request_comment_plan.assert_called_once_with(
            PR_RID, "hello"
        )
        mock_service.create_pull_request_comment.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_apply_posts_comment(self, mock_service_class):
        """Test --apply forwards to the real comment create."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request_comment.return_value = {
            "rid": "ri.pull-request.main.pull-request-comment.abc",
            "content": "hello",
        }

        result = self.runner.invoke(
            app,
            ["pull-request", "comment", PR_RID, "hello", "--apply", "--format", "json"],
        )

        assert result.exit_code == 0
        assert "pull-request-comment" in result.stdout
        mock_service.create_pull_request_comment.assert_called_once_with(
            PR_RID, "hello"
        )
        mock_service.create_pull_request_comment_plan.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_comment_shape_error(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request_comment.side_effect = PullRequestShapeError(
            "Unverified pull-request comment response shape"
        )

        result = self.runner.invoke(
            app, ["pull-request", "comment", PR_RID, "hello", "--apply"]
        )

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_comment_error(self, mock_service_class):
        """Test comment error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.create_pull_request_comment.side_effect = Exception("HTTP 500")

        result = self.runner.invoke(
            app, ["pull-request", "comment", PR_RID, "hello", "--apply"]
        )

        assert result.exit_code == 1
        assert "Error commenting on pull request" in result.stdout


class TestPullRequestCloseCommand:
    """Test cases for `repository pull-request close`."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def _plan(self):
        return {
            "status": "dry-run",
            "operation": "close_code_repository_pull_request",
            "pull_request_rid": PR_RID,
            "current_status": "OPEN",
            "already_closed": False,
            "intended_endpoint": (
                f"PUT /stemma-pull-request/api/pulls/{PR_RID}/update"
            ),
            "intended_body": {"title": "t", "status": "CLOSED"},
            "contract": "VERIFIED",
            "evidence": "contract-verified",
        }

    @patch("pltr.commands.repository.RepositoryService")
    def test_default_is_dry_run_plan(self, mock_service_class):
        """Test the default posture prints the dry-run plan, never PUTs."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request_plan.return_value = self._plan()

        result = self.runner.invoke(
            app, ["pull-request", "close", PR_RID, "--format", "json"]
        )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        mock_service.close_pull_request_plan.assert_called_once_with(PR_RID)
        mock_service.close_pull_request.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_apply_requires_yes(self, mock_service_class):
        """Test --apply without --yes prompts and honours a refusal."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(
            app, ["pull-request", "close", PR_RID, "--apply"], input="n\n"
        )

        assert result.exit_code == 1
        assert "Close cancelled" in result.stdout
        mock_service.close_pull_request.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_apply_yes_closes(self, mock_service_class):
        """Test --apply --yes forwards to the real close."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request.return_value = {
            "status": "closed",
            "operation": "close_code_repository_pull_request",
            "pull_request_rid": PR_RID,
            "verification": {"status": "CLOSED", "merged": False},
            "contract": "VERIFIED",
            "evidence": "contract-verified",
        }

        result = self.runner.invoke(
            app,
            ["pull-request", "close", PR_RID, "--apply", "--yes", "--format", "json"],
        )

        assert result.exit_code == 0
        assert "closed" in result.stdout
        mock_service.close_pull_request.assert_called_once_with(PR_RID)
        mock_service.close_pull_request_plan.assert_not_called()

    @patch("pltr.commands.repository.RepositoryService")
    def test_already_closed_reported(self, mock_service_class):
        """Test an already-closed pull request is reported honestly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request.return_value = {
            "status": "already-closed",
            "operation": "close_code_repository_pull_request",
            "pull_request_rid": PR_RID,
            "note": "Pull request is already CLOSED; no update was issued.",
            "contract": "VERIFIED",
            "evidence": "contract-verified",
        }

        result = self.runner.invoke(
            app,
            ["pull-request", "close", PR_RID, "--apply", "--yes", "--format", "json"],
        )

        assert result.exit_code == 0
        assert "already-closed" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_close_not_found(self, mock_service_class):
        """Test close when no pull request exists for the RID."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request_plan.side_effect = PullRequestNotFoundError(
            f"No pull request found for RID {PR_RID}"
        )

        result = self.runner.invoke(app, ["pull-request", "close", PR_RID])

        assert result.exit_code == 1
        assert "No pull request found" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_close_shape_error(self, mock_service_class):
        """Test that unverified response shapes fail loudly."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request.side_effect = PullRequestShapeError(
            "Unverified pull-request close response shape"
        )

        result = self.runner.invoke(
            app, ["pull-request", "close", PR_RID, "--apply", "--yes"]
        )

        assert result.exit_code == 1
        assert "Unverified" in result.stdout

    @patch("pltr.commands.repository.RepositoryService")
    def test_close_error(self, mock_service_class):
        """Test close error handling."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.close_pull_request.side_effect = Exception("HTTP 400")

        result = self.runner.invoke(
            app, ["pull-request", "close", PR_RID, "--apply", "--yes"]
        )

        assert result.exit_code == 1
        assert "Error closing pull request" in result.stdout
