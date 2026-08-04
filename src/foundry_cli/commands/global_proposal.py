"""
Ontology Global Proposal commands (read-only loads; plan-first writes).
"""

import typer
from typing import Optional
from rich.console import Console

from ..services.global_branching import (
    GlobalBranchNotFoundError,
    GlobalBranchShapeError,
    GlobalProposalService,
)
from ..utils.agent_output import (
    agent_mode_enabled,
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

app = typer.Typer(help="Inspect Ontology Global Proposals")
console = Console()
formatter = OutputFormatter(console)


@app.command("get")
def get_proposal(
    proposal_rid: str = typer.Argument(
        ..., help="Global Proposal Resource Identifier", autocompletion=complete_rid
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
    """Load one Ontology Global Proposal by RID (read-only).

    Reads the internal branch-service API
    (PUT /branch/proposal/load/{proposalRid}, an empty-body load). There is no
    list endpoint; load-by-RID only. The success response shape was
    contract-verified against a live deployment and is passed through raw.
    """
    try:
        cache_rid(proposal_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Loading global proposal {proposal_rid}..."
        ):
            service = GlobalProposalService(profile=profile)
            proposal = service.get_proposal(proposal_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                proposal,
                meta={
                    "operation": "view_global_proposal",
                    "proposal_rid": proposal_rid,
                    "shape_verified": True,
                },
            )
        else:
            formatter.format_output([proposal], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (GlobalBranchNotFoundError, GlobalBranchShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error loading global proposal: {e}[/red]")
        raise typer.Exit(1)


@app.command("create")
def create_proposal(
    display_name: str = typer.Argument(..., help="Proposal display name"),
    branch_rid: str = typer.Option(
        ...,
        "--branch-rid",
        help="Global Branch RID the proposal belongs to",
        autocompletion=complete_rid,
    ),
    description: str = typer.Option("", "--description", help="Proposal description"),
    merge_to: str = typer.Option(
        "main",
        "--merge-to",
        help="Proposal merge target: 'main' or a global branch RID "
        "(ri.branch..branch.<uuid>)",
        autocompletion=complete_rid,
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the mutation (default: dry-run plan only)",
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
    """Create an Ontology Global Proposal (plan-first; --apply issues the real mutation).

    Backed by branch-service ``POST /branch/proposal/create``, with the
    contract verified against a live deployment. The create sends
    ``{branchRid, displayName, description, mergeTo}`` where ``mergeTo`` is
    the ``ProposalMergeTo`` Conjure union with two arms (generated
    ``@palantir/branch-service-api`` evidence): ``--merge-to main`` sends
    ``{"main": {}, "type": "main"}`` (default, contract-verified); a global
    branch RID sends ``{"branchRid": <rid>, "type": "branchRid"}`` (encoding
    accepted by the server, which validates the target semantically and
    answers ``Branch:InvalidMergeTo`` when invalid). Returns the new
    proposal RID (``ri.branch..proposal.<uuid>`` — double dot).

    Without ``--apply`` the command prints the dry-run plan and issues no
    network request.
    """
    try:
        service = GlobalProposalService(profile=profile)

        if not apply:
            plan = service.plan_create_proposal(
                branch_rid, display_name, description, merge_to=merge_to
            )
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "create_global_proposal",
                        "mode": "plan",
                        "branch_rid": branch_rid,
                        "write_verified": True,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        with SpinnerProgressTracker().track_spinner(
            f"Creating global proposal {display_name}..."
        ):
            result = service.create_proposal(
                branch_rid, display_name, description, merge_to=merge_to
            )

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_global_proposal",
                    "mode": "applied",
                    "branch_rid": branch_rid,
                    "proposal_rid": result["proposalRid"],
                    "write_verified": True,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (GlobalBranchNotFoundError, GlobalBranchShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating global proposal: {e}[/red]")
        raise typer.Exit(1)


@app.command("close")
def close_proposal(
    proposal_rid: str = typer.Argument(
        ..., help="Global Proposal Resource Identifier", autocompletion=complete_rid
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the mutation (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the destructive close (required with --apply)"
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
    """Close an Ontology Global Proposal (DESTRUCTIVE; plan-first).

    Backed by branch-service ``PUT /branch/proposal/close/{proposalRid}``
    (empty-body write returning ``200 {}``; contract-verified against a live deployment). Without ``--apply`` the
    command prints the dry-run plan and issues no network request. The real
    close requires both ``--apply`` and ``--yes``.
    """
    try:
        cache_rid(proposal_rid)
        service = GlobalProposalService(profile=profile)

        if not apply:
            plan = {
                "mode": "plan",
                "request": {
                    "verb": "PUT",
                    "path": f"/branch-service/api/branch/proposal/close/{proposal_rid}",
                    "body": {},
                },
                "contract": GlobalProposalService.CLOSE_CONTRACT,
            }
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "close_global_proposal",
                        "proposal_rid": proposal_rid,
                        "mode": "plan",
                        "shape_verified": True,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        if not require_confirmation(
            f"Close global proposal {proposal_rid}? This is destructive.",
            confirmed=yes,
            option_name="--yes",
        ):
            console.print("[yellow]Close cancelled[/yellow]")
            raise typer.Exit(1)
        with SpinnerProgressTracker().track_spinner(
            f"Closing global proposal {proposal_rid}..."
        ):
            result = service.close_proposal(proposal_rid)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "close_global_proposal",
                    "proposal_rid": proposal_rid,
                    "mode": "applied",
                    "shape_verified": True,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except (GlobalBranchNotFoundError, GlobalBranchShapeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error closing global proposal: {e}[/red]")
        raise typer.Exit(1)
