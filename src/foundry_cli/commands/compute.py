"""
Compute Module commands (reads; plan-first writes).

Backed by the internal gateways used by the Palantir MCP compute-module
tools:
``contour-backend-multiplexer`` for info/dev-mode/execute, ``build2`` for
start/stop, and ``foundry-telemetry-service`` for logs. The unmounted
``/module-group/api/...`` prefix is deliberately never called.
"""

import json
from typing import Any, List, Optional

import typer
from rich.console import Console

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..services.compute import (
    DEFAULT_BRANCH,
    DEFAULT_PAGE_SIZE_LIMIT,
    MAX_PAGE_SIZE_LIMIT,
    ComputeService,
    ComputeSessionNotFoundError,
    ComputeShapeError,
)
from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_payload,
    require_confirmation,
)
from ..utils.completion import (
    cache_rid,
    complete_output_format,
    complete_profile,
    complete_rid,
)
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker

app = typer.Typer(help="Inspect and manage Foundry Compute Modules")
console = Console()
formatter = OutputFormatter(console)

_INFO_OPERATIONS = {"status", "config"}
_MANAGE_ACTIONS = ("start", "stop", "dev-mode")


def _emit(
    payload: Any, meta: dict[str, Any], format: str, output: Optional[str]
) -> None:
    """Route one result to the agent buffer or the human formatter."""
    if agent_mode_enabled() or format == "agent":
        buffer_agent_payload(payload, meta=meta)
    else:
        formatter.format_output([payload], format, output)


def _fail(e: Exception, prefix: str) -> None:
    """Render a service failure in the shared style and exit 1."""
    if isinstance(e, (ProfileNotFoundError, MissingCredentialsError)):
        console.print(f"[red]Authentication error: {e}[/red]")
    elif isinstance(e, (ComputeSessionNotFoundError, ComputeShapeError)):
        console.print(f"[red]{e}[/red]")
    else:
        console.print(f"[red]{prefix}: {e}[/red]")
    raise typer.Exit(1)


@app.command("info")
def get_info(
    deployed_app_rid: str = typer.Argument(
        ..., help="Deployed app Resource Identifier", autocompletion=complete_rid
    ),
    branch: str = typer.Option(
        DEFAULT_BRANCH, "--branch", "-b", help="Deployed app branch"
    ),
    include: Optional[List[str]] = typer.Option(
        None,
        "--include",
        help="Info to load: status, config (repeatable; default: both)",
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
    """Load compute-module status and/or config (read-only).

    One internal GET per include entry against contour-backend-multiplexer:
    ``/deployed-apps/{rid}/{branch}/status`` and ``/deployed-apps/{rid}/v2``.
    Routes are contract-verified (403 Contour:InsufficientPermission proves the
    mount); success shapes are UNVERIFIED and passed through raw.
    """
    try:
        cache_rid(deployed_app_rid)
        includes = include if include else ["status", "config"]
        unknown = sorted(set(includes) - _INFO_OPERATIONS)
        if unknown:
            console.print(
                f"[red]Unknown --include value(s): {', '.join(unknown)} "
                f"(choose from: {', '.join(sorted(_INFO_OPERATIONS))})[/red]"
            )
            raise typer.Exit(2)

        service = ComputeService(profile=profile)
        result: dict[str, Any] = {"deployedAppRid": deployed_app_rid, "branch": branch}
        with SpinnerProgressTracker().track_spinner(
            f"Loading compute module info for {deployed_app_rid}..."
        ):
            if "status" in includes:
                result["status"] = service.get_status(deployed_app_rid, branch)
            if "config" in includes:
                result["config"] = service.get_config(deployed_app_rid)

        _emit(
            result,
            {
                "operation": "get_compute_modules_info",
                "deployed_app_rid": deployed_app_rid,
                "branch": branch,
                "include": includes,
                "shape_verified": False,
            },
            format,
            output,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _fail(e, "Error loading compute module info")


@app.command("logs")
def get_logs(
    build_job_rid: str = typer.Argument(
        ..., help="Build job (run) Resource Identifier", autocompletion=complete_rid
    ),
    from_inclusive: Optional[int] = typer.Option(
        None,
        "--from-inclusive",
        help="Range start, microseconds since epoch (default: 24h ago)",
    ),
    to_exclusive: Optional[int] = typer.Option(
        None,
        "--to-exclusive",
        help="Range end, microseconds since epoch (default: now)",
    ),
    page_size_limit: int = typer.Option(
        DEFAULT_PAGE_SIZE_LIMIT,
        "--page-size-limit",
        help=f"Max log entries (1-{MAX_PAGE_SIZE_LIMIT})",
    ),
    reverse: bool = typer.Option(
        False, "--reverse", help="Newest-first instead of chronological order"
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
    """Read compute-module logs for one build job RID (read-only).

    Two-step telemetry flow: resolve the container/session via
    ``foundry-telemetry-service`` ``sessions/by-run-rids/get-batch``, then
    read ``logs/read/v3`` with microsecond timestamps. Step 2's shape is
    bundle-derived and NOT contract-verified; the response is passed through raw.
    """
    try:
        cache_rid(build_job_rid)
        service = ComputeService(profile=profile)
        with SpinnerProgressTracker().track_spinner(
            f"Reading logs for build job {build_job_rid}..."
        ):
            result = service.get_logs(
                build_job_rid,
                from_inclusive=from_inclusive,
                to_exclusive=to_exclusive,
                page_size_limit=page_size_limit,
                chronological=not reverse,
            )

        _emit(
            result,
            {
                "operation": "get_compute_modules_logs",
                "build_job_rid": build_job_rid,
                "shape_verified": False,
            },
            format,
            output,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _fail(e, "Error reading compute module logs")


@app.command("manage")
def manage(
    action: str = typer.Option(
        ..., "--action", help=f"One of: {', '.join(_MANAGE_ACTIONS)}"
    ),
    deployed_app_rid: Optional[str] = typer.Option(
        None,
        "--deployed-app-rid",
        help="Deployed app RID (start, dev-mode)",
        autocompletion=complete_rid,
    ),
    build_rid: Optional[str] = typer.Option(
        None,
        "--build-rid",
        help="Build RID to cancel (stop)",
        autocompletion=complete_rid,
    ),
    branch: str = typer.Option(
        DEFAULT_BRANCH, "--branch", "-b", help="Deployed app branch"
    ),
    dev_mode_until: Optional[str] = typer.Option(
        None,
        "--dev-mode-until",
        help="ISO-8601 automaticUpgradesUntil (max +5h); omit to disable dev mode",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the mutation (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the stop (required with stop --apply)"
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
    """Start, stop, or configure dev mode on a compute module (plan-first).

    - start: build2 ``POST /manager/submitBuild`` with the deployed-app RID
      as a ``datasets`` jobSpecSelection (``isRequired: true``)
    - stop: build2 ``DELETE /manager/builds/{buildRid}``
    - dev-mode: contour-backend-multiplexer ``PUT
      /deployed-apps/{rid}/{branch}/dev-mode`` with
      ``{automaticUpgradesUntil: ISO-8601}`` (max +5h), or an empty body to
      disable

    Routes are contract-verified via their 400/403 error contracts; success
    shapes are UNVERIFIED and passed through raw. Without ``--apply`` the
    command prints the dry-run plan and issues no network request. ``stop``
    additionally requires ``--yes``.
    """
    try:
        service = ComputeService(profile=profile)

        if action == "start":
            if not deployed_app_rid:
                console.print("[red]--deployed-app-rid is required for start[/red]")
                raise typer.Exit(2)
            plan = service.plan_start(deployed_app_rid, branch)
            meta = {
                "operation": "manage_compute_modules",
                "manage_action": "start",
                "deployed_app_rid": deployed_app_rid,
                "branch": branch,
                "shape_verified": False,
                "write_verified": False,
            }
            if not apply:
                _emit(plan, {**meta, "mode": "plan"}, format, output)
                return
            with SpinnerProgressTracker().track_spinner(
                f"Starting compute module {deployed_app_rid}..."
            ):
                result = service.start(deployed_app_rid, branch)
            _emit(result, {**meta, "mode": "applied"}, format, output)
            return

        if action == "stop":
            if not build_rid:
                console.print("[red]--build-rid is required for stop[/red]")
                raise typer.Exit(2)
            plan = service.plan_stop(build_rid)
            meta = {
                "operation": "manage_compute_modules",
                "manage_action": "stop",
                "build_rid": build_rid,
                "shape_verified": False,
                "write_verified": False,
            }
            if not apply:
                _emit(plan, {**meta, "mode": "plan"}, format, output)
                return
            if not require_confirmation(
                f"Stop compute module build {build_rid}? This cancels its jobs.",
                confirmed=yes,
                option_name="--yes",
            ):
                console.print("[yellow]Stop cancelled[/yellow]")
                raise typer.Exit(1)
            with SpinnerProgressTracker().track_spinner(
                f"Stopping compute module build {build_rid}..."
            ):
                result = service.stop(build_rid)
            _emit(result, {**meta, "mode": "applied"}, format, output)
            return

        if action == "dev-mode":
            if not deployed_app_rid:
                console.print("[red]--deployed-app-rid is required for dev-mode[/red]")
                raise typer.Exit(2)
            plan = service.plan_dev_mode(deployed_app_rid, branch, dev_mode_until)
            meta = {
                "operation": "manage_compute_modules",
                "manage_action": "dev-mode",
                "deployed_app_rid": deployed_app_rid,
                "branch": branch,
                "dev_mode_enabled": dev_mode_until is not None,
                "shape_verified": False,
                "write_verified": False,
            }
            if not apply:
                _emit(plan, {**meta, "mode": "plan"}, format, output)
                return
            with SpinnerProgressTracker().track_spinner(
                f"Configuring dev mode on {deployed_app_rid}..."
            ):
                result = service.configure_dev_mode(
                    deployed_app_rid, branch, dev_mode_until
                )
            _emit(result, {**meta, "mode": "applied"}, format, output)
            return

        console.print(
            f"[red]Unknown --action {action!r} "
            f"(choose from: {', '.join(_MANAGE_ACTIONS)})[/red]"
        )
        raise typer.Exit(2)
    except typer.Exit:
        raise
    except Exception as e:
        _fail(e, f"Error managing compute module ({action})")


@app.command("execute")
def execute_function(
    deployed_app_rid: str = typer.Argument(
        ..., help="Deployed app Resource Identifier", autocompletion=complete_rid
    ),
    query_type: str = typer.Option(
        ..., "--query-type", help="Function query type to execute"
    ),
    query: Optional[str] = typer.Option(
        None, "--query", help="Function input as a JSON value (optional)"
    ),
    branch: str = typer.Option(
        DEFAULT_BRANCH, "--branch", "-b", help="Deployed app branch"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the execution (default: dry-run plan only)",
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
    """Execute a function on a running FUNCTION-mode compute module (plan-first).

    Backed by contour-backend-multiplexer ``POST
    /module-group-multiplexer/compute-modules/jobs/execute``. The route is
    contract-verified (403 Contour:InsufficientPermission proves the mount); the
    response is a raw octet-stream whose success shape is UNVERIFIED and is
    passed through raw. Without ``--apply`` the command prints the dry-run
    plan and issues no network request.
    """
    try:
        cache_rid(deployed_app_rid)
        parsed_query: Optional[Any] = None
        if query is not None:
            try:
                parsed_query = json.loads(query)
            except json.JSONDecodeError as e:
                console.print(f"[red]--query is not valid JSON: {e}[/red]")
                raise typer.Exit(2)

        service = ComputeService(profile=profile)
        meta = {
            "operation": "execute_compute_modules_function",
            "deployed_app_rid": deployed_app_rid,
            "branch": branch,
            "query_type": query_type,
            "shape_verified": False,
            "write_verified": False,
        }
        if not apply:
            plan = service.plan_execute(
                deployed_app_rid, branch, query_type, parsed_query
            )
            _emit(plan, {**meta, "mode": "plan"}, format, output)
            return

        with SpinnerProgressTracker().track_spinner(
            f"Executing {query_type} on {deployed_app_rid}..."
        ):
            result = service.execute(deployed_app_rid, branch, query_type, parsed_query)
        _emit(result, {**meta, "mode": "applied"}, format, output)
    except typer.Exit:
        raise
    except Exception as e:
        _fail(e, "Error executing compute module function")
