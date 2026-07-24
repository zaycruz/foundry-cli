"""
Code repository commands (read-only pull-request access).
"""

import typer
from typing import Optional
from rich.console import Console

from ..services.repository import (
    PullRequestNotFoundError,
    PullRequestShapeError,
    RepositoryService,
)
from ..utils.agent_output import agent_mode_enabled, buffer_agent_payload
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

app.add_typer(pull_request_app, name="pull-request", help="Inspect pull requests")


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
