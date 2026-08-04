"""
Code repository commands (pull-request access, repository context, local
clone, and Python-transforms repository creation).
"""

import os

import typer
from typing import Optional
from rich.console import Console

from ..services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
    RepositoryCloneError,
    RepositoryNotFoundError,
    RepositoryService,
    RepositoryShapeError,
)
from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_message,
    buffer_agent_payload,
    require_confirmation,
)
from ..utils.completion import (
    complete_rid,
    complete_profile,
    complete_output_format,
    cache_rid,
)
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker
from ..auth.base import ProfileNotFoundError, MissingCredentialsError

app = typer.Typer(help="Code repository operations")
pull_request_app = typer.Typer()
console = Console()
formatter = OutputFormatter(console)

app.add_typer(
    pull_request_app, name="pull-request", help="Inspect and manage pull requests"
)


@pull_request_app.command("list")
def list_pull_requests(
    repository_rid: Optional[str] = typer.Argument(
        None,
        help="Repository Resource Identifier to filter by (client-side; the "
        "internal API does not honor a server-side repository filter)",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List code repository pull requests (read-only).

    Reads the internal stemma-pull-request API (GET /pulls). Note the list
    endpoint enumerates pull requests across repositories; a repository RID
    argument filters client-side.
    """
    try:
        if repository_rid:
            cache_rid(repository_rid)

        with SpinnerProgressTracker().track_spinner("Fetching pull requests..."):
            service = RepositoryService(profile=profile)
            pull_requests = service.list_pull_requests(repository_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                pull_requests,
                meta={
                    "operation": "list_code_repository_pull_requests",
                    "repository_rid": repository_rid,
                    "count": len(pull_requests),
                },
            )
        else:
            formatter.format_output(pull_requests, format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (PullRequestShapeError,) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing pull requests: {e}[/red]")
        raise typer.Exit(1)


@pull_request_app.command("get")
def get_pull_request(
    pull_request_rid: str = typer.Argument(
        ..., help="Pull request Resource Identifier", autocompletion=complete_rid
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get one code repository pull request by RID (read-only).

    Reads the internal stemma-pull-request API (GET /pulls/{pullRequestRid}).
    """
    try:
        cache_rid(pull_request_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching pull request {pull_request_rid}..."
        ):
            service = RepositoryService(profile=profile)
            pull_request = service.get_pull_request(pull_request_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                pull_request,
                meta={
                    "operation": "get_code_repository_pull_request",
                    "pull_request_rid": pull_request_rid,
                },
            )
        else:
            formatter.format_output([pull_request], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (PullRequestNotFoundError, PullRequestShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting pull request: {e}[/red]")
        raise typer.Exit(1)


@pull_request_app.command("create")
def create_pull_request(
    title: str = typer.Argument(..., help="Pull request title"),
    base_repository_rid: str = typer.Option(
        ...,
        "--base-repository-rid",
        help="Repository RID the pull request targets",
        autocompletion=complete_rid,
    ),
    head_commitish: str = typer.Option(
        ...,
        "--head-commitish",
        help="Head branch ref to merge from (e.g. refs/heads/feature-x)",
    ),
    head_repository_rid: Optional[str] = typer.Option(
        None,
        "--head-repository-rid",
        help="Repository RID the head branch lives in (default: same as base)",
        autocompletion=complete_rid,
    ),
    base_branch: str = typer.Option(
        "refs/heads/master",
        "--base-branch",
        help="Base branch ref the pull request merges into",
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Pull request description"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real POST /stemma-pull-request/api/pulls "
        "(default: dry-run plan only)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a code repository pull request (dry-run plan by default).

    Writes the internal stemma-pull-request API (POST /pulls) whose request
    contract was contract-verified against a live deployment (strict
    strict deserialization; the captured contract). Without
    --apply the command prints the exact intended write and changes
    nothing; with --apply it posts that body verbatim and passes the
    created pull request through raw.
    """
    try:
        service = RepositoryService(profile=profile)

        if apply:
            with SpinnerProgressTracker().track_spinner("Creating pull request..."):
                result = service.create_pull_request(
                    title=title,
                    base_repository_rid=base_repository_rid,
                    head_commitish=head_commitish,
                    head_repository_rid=head_repository_rid,
                    base_branch_name=base_branch,
                    description=description,
                )
            warnings = []
        else:
            result = service.create_pull_request_plan(
                title=title,
                base_repository_rid=base_repository_rid,
                head_commitish=head_commitish,
                head_repository_rid=head_repository_rid,
                base_branch_name=base_branch,
                description=description,
            )
            warnings = [result["evidence"]]

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_code_repository_pull_request",
                    "status": result.get("status", "created"),
                    "pull_request_rid": result.get("rid"),
                },
                warnings=warnings,
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (PullRequestShapeError,) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating pull request: {e}[/red]")
        raise typer.Exit(1)


@pull_request_app.command("comment")
def comment_pull_request(
    pull_request_rid: str = typer.Argument(
        ..., help="Pull request Resource Identifier", autocompletion=complete_rid
    ),
    content: str = typer.Argument(..., help="Comment body (markdown)"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real POST /pulls/{rid}/comments/global "
        "(default: dry-run plan only)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Comment on a code repository pull request (dry-run plan by default).

    Writes the internal stemma-pull-request API (POST
    /pulls/{pullRequestRid}/comments/global) whose request contract was
    contract-verified against a live deployment (strict deserialization;
    the captured contract). Without --apply the command prints
    the exact intended write and changes nothing; with --apply it posts
    that body verbatim and passes the created comment through raw.
    """
    try:
        cache_rid(pull_request_rid)
        service = RepositoryService(profile=profile)

        if apply:
            with SpinnerProgressTracker().track_spinner(
                f"Commenting on pull request {pull_request_rid}..."
            ):
                result = service.create_pull_request_comment(pull_request_rid, content)
            warnings = []
        else:
            result = service.create_pull_request_comment_plan(pull_request_rid, content)
            warnings = [result["evidence"]]

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_code_repository_pull_request_comment",
                    "pull_request_rid": pull_request_rid,
                    "status": result.get("status", "created"),
                },
                warnings=warnings,
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (PullRequestShapeError,) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error commenting on pull request: {e}[/red]")
        raise typer.Exit(1)


@pull_request_app.command("close")
def close_pull_request(
    pull_request_rid: str = typer.Argument(
        ..., help="Pull request Resource Identifier", autocompletion=complete_rid
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real PUT /pulls/{rid}/update (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the close (required with --apply)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Close a code repository pull request (dry-run plan by default).

    Writes the internal stemma-pull-request API (PUT
    /pulls/{pullRequestRid}/update) whose close contract was contract-verified
     against a live deployment: the body is {"title": <current title>,
    "status": "CLOSED"} with both fields required, so the pull request is
    read first to obtain its title. Without --apply the command prints the
    exact intended write and changes nothing; the real close requires both
    --apply and --yes. An already-CLOSED pull request is reported honestly
    instead of being re-closed.
    """
    try:
        cache_rid(pull_request_rid)
        service = RepositoryService(profile=profile)

        if apply:
            if not require_confirmation(
                f"Close pull request {pull_request_rid}?",
                confirmed=yes,
                option_name="--yes",
            ):
                console.print("[yellow]Close cancelled[/yellow]")
                raise typer.Exit(1)
            with SpinnerProgressTracker().track_spinner(
                f"Closing pull request {pull_request_rid}..."
            ):
                result = service.close_pull_request(pull_request_rid)
            warnings = []
        else:
            with SpinnerProgressTracker().track_spinner(
                f"Fetching pull request {pull_request_rid}..."
            ):
                result = service.close_pull_request_plan(pull_request_rid)
            warnings = [result["evidence"]]

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "close_code_repository_pull_request",
                    "pull_request_rid": pull_request_rid,
                    "status": result.get("status"),
                },
                warnings=warnings,
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (PullRequestNotFoundError, PullRequestShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error closing pull request: {e}[/red]")
        raise typer.Exit(1)


@app.command("context")
def get_repository_context(
    repository_rid: str = typer.Argument(
        ..., help="Repository Resource Identifier", autocompletion=complete_rid
    ),
    path: str = typer.Option(
        "", "--path", help="Subtree path for the file tree (default: root)"
    ),
    ref: Optional[str] = typer.Option(
        None,
        "--ref",
        help="Commitish for the file tree (default: the repository's default "
        "branch). Note: stemma silently falls back to the default branch for "
        "unresolvable refs.",
    ),
    no_tree: bool = typer.Option(
        False, "--no-tree", help="Skip the file tree (metadata and refs only)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get headless repository context (read-only).

    Aggregates the contract-verified internal stemma reads: repository metadata
    (stemma + Compass name/path), the default branch (HEAD), branch and tag
    refs, and the recursive file tree at a ref.
    """
    try:
        cache_rid(repository_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching repository context for {repository_rid}..."
        ):
            service = RepositoryService(profile=profile)
            context = service.get_repository_context(
                repository_rid, path=path, ref=ref, include_tree=not no_tree
            )

        warnings = []
        tree = context.get("tree")
        if tree:
            warnings.append(tree["ref_note"])

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                context,
                meta={
                    "operation": "get_repository_context",
                    "repository_rid": repository_rid,
                    "path": path,
                },
                warnings=warnings,
            )
        else:
            formatter.format_output([context], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (RepositoryNotFoundError, RepositoryShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting repository context: {e}[/red]")
        raise typer.Exit(1)


@app.command("clone")
def clone_repository(
    repository_rid: str = typer.Argument(
        ..., help="Repository Resource Identifier", autocompletion=complete_rid
    ),
    target_dir: str = typer.Argument(..., help="Local directory to clone into"),
    branch: Optional[str] = typer.Option(
        None, "--branch", "-b", help="Branch to check out (default: HEAD)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete a non-empty target directory and re-clone into it",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Resolve and print the clone plan without cloning",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Clone a Foundry code repository to a local path.

    Resolves the repository's git URL from the contract-verified stemma smart-HTTP
    endpoint (https://<host>/stemma/git/<repositoryRid>) and runs `git clone`
    with the profile bearer token passed via environment-injected
    http.extraHeader — the token is never printed, never on the command line,
    and never persisted in the clone's config (later fetches need fresh
    credentials). Refuses to overwrite a non-empty target without --force.
    """
    try:
        cache_rid(repository_rid)

        if force and os.path.isdir(target_dir) and os.listdir(target_dir):
            require_confirmation(
                f"Target directory {target_dir} is not empty and will be "
                "deleted before cloning. Continue?",
                confirmed=force,
            )

        with SpinnerProgressTracker().track_spinner(
            f"Cloning {repository_rid} into {target_dir}..."
        ):
            service = RepositoryService(profile=profile)
            result = service.clone_repository(
                repository_rid,
                target_dir,
                branch=branch,
                force=force,
                dry_run=dry_run,
            )

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "clone_code_repository_locally",
                    "repository_rid": repository_rid,
                    "target_dir": target_dir,
                    "status": result.get("status"),
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (RepositoryCloneError, RepositoryNotFoundError, RepositoryShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error cloning repository: {e}[/red]")
        raise typer.Exit(1)


@app.command("create-python-transforms")
def create_python_transforms(
    name: str = typer.Argument(
        ..., help="Name for the new Python transforms repository"
    ),
    parent_rid: str = typer.Option(
        ...,
        "--parent-rid",
        help="Compass folder RID to create the repository under (resolved "
        "to its enclosing project; the repository lands in the project "
        "root)",
        autocompletion=complete_rid,
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real creation (POST /stemma/api/repos + "
        "repository-bootstrapper bootstrap; default: dry-run plan only)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a Python transforms code repository (dry-run plan by default).

    Uses the two-call chain derived from the published client contract
     against a live deployment: the folder RID is
    resolved to its enclosing project and Compass path via read-only
    hierarchy batch endpoints, then POST /stemma/api/repos {"path":
    "<projectPath>/<name>"} creates the repository and POST
    /repository-bootstrapper/api/repos/{rid}/bootstrap applies the Python
    transforms template (master branch + 0.0.1 tag). Without --apply the
    command runs only the read-only preflight and prints the exact
    intended writes; with --apply it posts them and reads the refs back.
    """
    try:
        service = RepositoryService(profile=profile)

        if apply:
            with SpinnerProgressTracker().track_spinner(
                f"Creating Python transforms repository {name}..."
            ):
                result = service.create_python_transforms_repository(name, parent_rid)
            warnings = []
        else:
            with SpinnerProgressTracker().track_spinner(
                "Resolving repository target path..."
            ):
                result = service.create_python_transforms_plan(name, parent_rid)
            warnings = [result["evidence"]]

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_python_transforms_code_repository",
                    "name": name,
                    "status": result["status"],
                    "repository_rid": result.get("repository", {}).get("rid"),
                },
                warnings=warnings,
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (RepositoryNotFoundError, RepositoryShapeError) as e:
        if agent_mode_enabled() or format == "agent":
            buffer_agent_message(str(e), level="error")
        else:
            console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating Python transforms repository: {e}[/red]")
        raise typer.Exit(1)
