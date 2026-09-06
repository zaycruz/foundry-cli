"""
Evaluation suite (AIP Evals) commands.

Read-only config and execution reads plus a plan-first run trigger, backed
by the internal foundry-evals Conjure service (contracts captured from the
live AIP Evals UI via CDP, 2026-09-04; see services/evals.py docstring).
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..services.errors import FoundryApiError
from ..services.evals import EvalsService, EvalsShapeError
from ..utils.agent_output import agent_mode_enabled, buffer_agent_payload
from ..utils.completion import (
    cache_rid,
    complete_output_format,
    complete_profile,
    complete_rid,
)
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker

app = typer.Typer(help="Inspect and run AIP evaluation suites")
suite_app = typer.Typer(help="Evaluation suite config reads")
run_app = typer.Typer(help="Evaluation run reads and triggers")
app.add_typer(suite_app, name="suite")
app.add_typer(run_app, name="run")

console = Console()
formatter = OutputFormatter(console)


def _profile_option() -> Any:
    return typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    )


def _format_option() -> Any:
    return typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv, agent)",
        autocompletion=complete_output_format,
    )


def _output_option() -> Any:
    return typer.Option(None, "--output", "-o", help="Output file path")


def _emit(
    payload: Any, operation: str, format: str, output: Optional[str], **meta: Any
) -> None:
    """Route one result through the agent envelope or the human formatter."""
    if agent_mode_enabled() or format == "agent":
        buffer_agent_payload(payload, meta={"operation": operation, **meta})
    else:
        items = payload if isinstance(payload, list) else [payload]
        formatter.format_output(items, format, output)


def _load_json_definition(definition: str, what: str) -> Dict[str, Any]:
    """Load a JSON object from a file path ('-' reads stdin)."""
    if definition == "-":
        raw_definition = sys.stdin.read()
    else:
        raw_definition = Path(definition).read_text()
    try:
        parsed = json.loads(raw_definition)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in {what}: {e}[/red]")
        raise typer.Exit(1) from e
    if not isinstance(parsed, dict):
        console.print(f"[red]{what} must be a JSON object[/red]")
        raise typer.Exit(1)
    return parsed


def _handle_error(e: Exception, action: str) -> None:
    """Consistent error rendering for evals commands."""
    if isinstance(e, (ProfileNotFoundError, MissingCredentialsError)):
        console.print(f"[red]Authentication error: {e}[/red]")
    elif isinstance(e, (EvalsShapeError, FoundryApiError)):
        console.print(f"[red]{e}[/red]")
    else:
        console.print(f"[red]Error {action}: {e}[/red]")
    raise typer.Exit(1) from e


@suite_app.command("list")
def list_suites(
    target: str = typer.Option(
        ...,
        "--target",
        help="Target function RID (ri.function-registry.main.function.<uuid>)",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """List evaluation suites linked to a target function (read-only).

    Backed by foundry-evals PUT
    /evals/config/v2/target/get-evaluation-suites with body
    ``{"linkedTarget": {"function": rid, "type": "function"}}`` (captured
    contract; only the function target arm was observed). Returns the raw
    suite RID list.
    """
    try:
        cache_rid(target)
        with SpinnerProgressTracker().track_spinner(
            f"Listing evaluation suites for {target}..."
        ):
            service = EvalsService(profile=profile)
            suite_rids = service.list_evaluation_suites_for_target(target)

        _emit(
            {"target": target, "evaluationSuiteRids": suite_rids},
            "list_evaluation_suites",
            format,
            output,
            target=target,
            count=len(suite_rids),
        )
    except Exception as e:
        _handle_error(e, "listing evaluation suites")


@suite_app.command("get")
def get_suite(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        help="Suite version to pin the read to (uses the version endpoints)",
    ),
    legacy: bool = typer.Option(
        False,
        "--legacy",
        help="Use the legacy (pre-metrics) config endpoints instead of v2",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load one evaluation suite's full config (read-only).

    Default: v2 config (PUT /evals/config/v2/get, body
    ``{"requests": [{"rid": ...}]}``) — metrics, test case definitions,
    execution backend. ``--version`` pins the read via the version
    endpoints; ``--legacy`` switches to the pre-metrics config endpoints.
    All four variants were captured live with HTTP 200.
    """
    try:
        cache_rid(suite_rid)
        with SpinnerProgressTracker().track_spinner(
            f"Loading evaluation suite {suite_rid}..."
        ):
            service = EvalsService(profile=profile)
            if version and legacy:
                config = service.get_evaluation_suite_config_version(suite_rid, version)
            elif version:
                config = service.get_evaluation_suite_config_v2_version(
                    suite_rid, version
                )
            elif legacy:
                config = service.get_evaluation_suite_config(suite_rid)
            else:
                config = service.get_evaluation_suite_config_v2(suite_rid)

        _emit(
            config,
            "view_evaluation_suite",
            format,
            output,
            suite_rid=suite_rid,
            version=version,
            legacy=legacy,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading evaluation suite {suite_rid}")


@suite_app.command("evaluators")
def list_evaluators(
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """List the evaluator catalog (read-only).

    Backed by foundry-evals PUT /evals/config/evaluators/get with an empty
    body (captured contract; no suite scoping was observed).
    """
    try:
        with SpinnerProgressTracker().track_spinner("Loading evaluators..."):
            service = EvalsService(profile=profile)
            evaluators = service.get_evaluators()

        _emit(evaluators, "list_evaluators", format, output, shape_verified=True)
    except Exception as e:
        _handle_error(e, "loading evaluators")


@suite_app.command("auto-metrics")
def list_auto_metrics(
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """List auto-generated metrics (read-only).

    Backed by foundry-evals PUT /evals/config/auto-generated-metric/get
    with an empty body (captured contract).
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            "Loading auto-generated metrics..."
        ):
            service = EvalsService(profile=profile)
            metrics = service.get_auto_generated_metrics()

        _emit(
            metrics, "list_auto_generated_metrics", format, output, shape_verified=True
        )
    except Exception as e:
        _handle_error(e, "loading auto-generated metrics")


@suite_app.command("suggested-scope")
def suggested_scope(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    execution_target: str = typer.Option(
        ...,
        "--execution-target",
        help="Path to a JSON file with one ExecutionTarget object "
        "('-' reads stdin); same shape as the run body's executionTarget",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load the suggested execution scope for a candidate run (read-only).

    Backed by foundry-evals PUT
    /evals/execute/v3/{suiteRid}/suggestedExecutionScope with body
    ``{"executionTargets": [target], "extraResources": []}`` (captured
    contract).
    """
    try:
        cache_rid(suite_rid)
        target = _load_json_definition(execution_target, "execution target")
        with SpinnerProgressTracker().track_spinner(
            f"Loading suggested execution scope for {suite_rid}..."
        ):
            service = EvalsService(profile=profile)
            scope = service.get_suggested_execution_scope(suite_rid, [target])

        _emit(
            scope,
            "view_evaluation_suggested_scope",
            format,
            output,
            suite_rid=suite_rid,
            shape_verified=True,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e, f"loading suggested execution scope for {suite_rid}")


@run_app.command("list")
def list_runs(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    page_size: int = typer.Option(
        20, "--page-size", help="Number of executions per page"
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """List run history for one suite (read-only).

    Backed by foundry-evals PUT /evals/execute/v3/{suiteRid}/history with
    body ``{"executionTarget": null, "pageSize": N}`` (captured contract).
    """
    try:
        cache_rid(suite_rid)
        with SpinnerProgressTracker().track_spinner(
            f"Loading run history for {suite_rid}..."
        ):
            service = EvalsService(profile=profile)
            history = service.get_execution_history(suite_rid, page_size=page_size)

        _emit(
            history,
            "list_evaluation_runs",
            format,
            output,
            suite_rid=suite_rid,
            page_size=page_size,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading run history for {suite_rid}")


@run_app.command("summary")
def run_summary(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    execution_id: str = typer.Argument(..., help="Execution ID (UUID)"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load one run's summary and aggregated scores (read-only).

    Backed by foundry-evals PUT /evals/execute/execution/{suiteRid}/summary
    with body ``{"executionId": ...}`` (captured contract).
    """
    try:
        cache_rid(suite_rid)
        with SpinnerProgressTracker().track_spinner(
            f"Loading summary for execution {execution_id}..."
        ):
            service = EvalsService(profile=profile)
            summary = service.get_execution_summary(suite_rid, execution_id)

        _emit(
            summary,
            "view_evaluation_run_summary",
            format,
            output,
            suite_rid=suite_rid,
            execution_id=execution_id,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading summary for execution {execution_id}")


@run_app.command("test-cases")
def run_test_cases(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    execution_id: str = typer.Argument(..., help="Execution ID (UUID)"),
    page_size: int = typer.Option(
        1000, "--page-size", help="Number of test case results per page"
    ),
    v3: bool = typer.Option(
        False,
        "--v3",
        help="Use the v3 testCases endpoint (v3 result shape, captured "
        "with pageSize 50)",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load per-test-case results for one run (read-only).

    Default: PUT /evals/execute/execution/{suiteRid}/testCases; ``--v3``
    switches to PUT /evals/execute/v3/execution/{suiteRid}/testCases. Both
    take ``{"executionId", "pageSize"}`` and both were captured live with
    HTTP 200; the per-result shapes differ between the two variants.
    """
    try:
        cache_rid(suite_rid)
        with SpinnerProgressTracker().track_spinner(
            f"Loading test case results for execution {execution_id}..."
        ):
            service = EvalsService(profile=profile)
            if v3:
                results = service.get_execution_test_cases_v3(
                    suite_rid, execution_id, page_size=page_size
                )
            else:
                results = service.get_execution_test_cases(
                    suite_rid, execution_id, page_size=page_size
                )

        _emit(
            results,
            "view_evaluation_run_test_cases",
            format,
            output,
            suite_rid=suite_rid,
            execution_id=execution_id,
            v3=v3,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading test case results for execution {execution_id}")


@run_app.command("trigger")
def trigger_run(
    suite_rid: str = typer.Argument(
        ...,
        help="Evaluation suite RID (ri.evals..evaluation-suite.<uuid>)",
        autocompletion=complete_rid,
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Path to a JSON file with the run body ({executionTarget, "
        "backendParameters, reportMetadata}); '-' reads stdin",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the run (default: dry-run plan only)",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Trigger one evaluation run (plan-first; --apply issues the run).

    The run body is sent verbatim to foundry-evals PUT
    /evals/execute/v3/{suiteRid}/run (captured contract: ``{executionTarget,
    backendParameters, reportMetadata}`` → ``{buildRid, jobRid,
    executionId}``).

    Without ``--apply`` the command issues no mutation: it prints the
    resolved run body plus the read-only suggestedExecutionScope for the
    body's executionTarget. With ``--apply`` it triggers the run and prints
    the returned build/job/execution identifiers.
    """
    try:
        cache_rid(suite_rid)
        run_body = _load_json_definition(definition, "run definition")
        service = EvalsService(profile=profile)

        if not apply:
            plan = service.plan_run(suite_rid, run_body)
            execution_target = run_body.get("executionTarget")
            if isinstance(execution_target, dict):
                with SpinnerProgressTracker().track_spinner(
                    "Loading suggested execution scope..."
                ):
                    plan["suggestedExecutionScope"] = (
                        service.get_suggested_execution_scope(
                            suite_rid, [execution_target]
                        )
                    )
            else:
                plan["suggestedExecutionScope"] = None
            _emit(
                plan,
                "execute_evaluation_run",
                format,
                output,
                suite_rid=suite_rid,
                mode="plan",
                write_verified=True,
            )
            return

        with SpinnerProgressTracker().track_spinner(
            f"Triggering evaluation run for {suite_rid}..."
        ):
            result = service.trigger_run(suite_rid, run_body)

        _emit(
            result,
            "execute_evaluation_run",
            format,
            output,
            suite_rid=suite_rid,
            mode="applied",
            execution_id=result.get("executionId"),
            write_verified=True,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e, f"triggering evaluation run for {suite_rid}")
