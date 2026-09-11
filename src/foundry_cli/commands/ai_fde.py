"""
AI FDE thread and settings commands, plus the CLI-side agent loop.

Thread primitives (list/get/items/create/send, agent-state metadata) plus
user settings, backed by the internal ai-fde Conjure service and the
GraphQL bulk gateway (contracts captured from the live AI FDE UI via CDP,
2026-09-04; see services/ai_fde.py docstring). The AI FDE agent loop runs
client-side in the Foundry UI — ``ai-fde run`` reimplements that loop in
the CLI (LLM call -> tool execution -> thread write-back; see
services/ai_fde_loop.py docstring, tickets/TICKET-009-ai-fde.md).

Thread creation runs through the scoped GraphQL mutation exception
(``CreateThreadMutation`` only); sending a user message and updating
metadata/settings are Conjure writes. ``threads send`` and ``threads
create`` are direct writes (they only queue content / create an empty
thread), while ``threads metadata update`` and ``settings update`` take
caller-supplied JSON bodies verbatim.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..services.ai_fde import AiFdeGraphQLError, AiFdeService, AiFdeShapeError
from ..services.ai_fde_loop import (
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    AgentLoop,
    LlmResponseShapeError,
    TOOL_REGISTRY,
    UnverifiedContract,
)
from ..services.errors import FoundryApiError
from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_payload,
    non_interactive_enabled,
)
from ..utils.completion import complete_output_format, complete_profile
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker

app = typer.Typer(help="Inspect and drive AI FDE threads and settings")
threads_app = typer.Typer(help="AI FDE thread reads and writes")
metadata_app = typer.Typer(help="Thread agent-state metadata")
settings_app = typer.Typer(help="AI FDE user settings")
threads_app.add_typer(metadata_app, name="metadata")
app.add_typer(threads_app, name="threads")
app.add_typer(settings_app, name="settings")

console = Console()
err_console = Console(stderr=True)
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
    """Consistent error rendering for ai-fde commands."""
    if isinstance(e, (ProfileNotFoundError, MissingCredentialsError)):
        console.print(f"[red]Authentication error: {e}[/red]")
    elif isinstance(
        e,
        (
            AiFdeShapeError,
            AiFdeGraphQLError,
            FoundryApiError,
            UnverifiedContract,
            LlmResponseShapeError,
        ),
    ):
        console.print(f"[red]{e}[/red]")
    else:
        console.print(f"[red]Error {action}: {e}[/red]")
    raise typer.Exit(1) from e


@app.command("run")
def run_agent_loop(
    instruction: str = typer.Argument(..., help="User instruction for the agent"),
    thread: Optional[str] = typer.Option(
        None, "--thread", help="Resume an existing thread ID (plain UUID)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", help="Display name for a newly created thread"
    ),
    max_turns: int = typer.Option(
        DEFAULT_MAX_TURNS, "--max-turns", help="Stop after this many LLM turns"
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Approve every write tool call without prompting"
    ),
    all_tools: bool = typer.Option(
        False,
        "--all-tools",
        help="Expose the full 72-tool captured catalog from turn 1 "
        "regardless of mode (fail-closed tools stay fail-closed)",
    ),
    tools: Optional[str] = typer.Option(
        None,
        "--tools",
        help="CSV subset of registered tool names to offer the model "
        f"(default: the 8 base tools; {len(TOOL_REGISTRY)} registered)",
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="LLM completion model"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Drive the AI FDE agent loop from the CLI (write).

    Reimplements the Foundry UI's client-side loop: sends the instruction
    to a new or resumed thread, calls the LLM
    (streamCompletionChunk, OpenAI-Responses shape), executes the returned
    tool calls against captured internal contracts, writes tool-usage and
    assistant-message items back into the thread, and repeats until the
    model stops calling tools or --max-turns is hit.

    IDENTIFYING RESOURCES: AI FDE has no resource-search tool — not even
    in the full 72-tool catalog. The UI identifies resources through user
    @-mentions; this loop cannot. Name RIDs explicitly in the instruction
    whenever they are known (e.g. ri.evals..evaluation-suite.<uuid>,
    ri.stemma.main.repository.<uuid>), or the agent will have to ask.

    Tool exposure: by default the model sees the captured 8-tool base set
    (no mode selected) and must use change_mode to unlock richer tool
    sets — change_mode actually swaps the offered tools per the captured
    mode mapping (functionsEditing -> 51 tools). --all-tools exposes the
    full 72-tool catalog from turn 1. Tools whose endpoint mapping was
    never captured (schedules, ci_checks, logic family, documentation,
    and others) stay registered spec-only and fail closed with a typed
    error the model can react to.

    Approval gate: write tools (execute_action, run_evaluation_suite,
    container_execute_terminal_command) never run silently. Interactive
    runs prompt per write; --yes approves all; --agent / non-interactive
    runs without --yes decline writes while read tools still execute.

    Output: the final assistant text prints as Markdown to stdout;
    progress streams to stderr. Use -f json for the structured run
    report (threadId, status, turns, toolCalls, usage).
    """
    tool_names: Optional[list] = None
    if tools:
        tool_names = [t.strip() for t in tools.split(",") if t.strip()]
    if yes:
        approve = "always"
    elif non_interactive_enabled():
        approve = "never"
    else:
        approve = "interactive"

    def _progress(message: str) -> None:
        err_console.print(f"[dim]{message}[/dim]")

    def _confirm(message: str) -> bool:
        return typer.confirm(message, err=True)

    def _clarify(questions: Any) -> str:
        err_console.print("[yellow]The agent requests clarification:[/yellow]")
        answers = []
        for question in questions:
            err_console.print(json.dumps(question, default=str))
            answers.append(typer.prompt("Answer", err=True))
        return "\n".join(answers)

    try:
        loop = AgentLoop(
            profile=profile,
            model=model,
            approve=approve,
            tool_names=tool_names,
            all_tools=all_tools,
            progress=_progress,
            confirm=_confirm if approve == "interactive" else None,
            clarification_handler=(_clarify if not non_interactive_enabled() else None),
        )
        report = loop.run(
            instruction,
            thread_id=thread,
            thread_name=name,
            max_turns=max_turns,
        )

        if agent_mode_enabled() or format == "agent" or format != "table":
            _emit(
                report,
                "run_ai_fde_agent_loop",
                format,
                output,
                thread_id=report.get("threadId"),
                status=report.get("status"),
                turns=report.get("turns"),
                tools_called=report.get("toolsCalled"),
                approve=approve,
                write_verified=True,
            )
        else:
            # Human default: the assistant's final answer is the payload;
            # print it as full-width Markdown (the run report table mangles
            # long text). Run metadata goes to stderr; -f json yields the
            # structured report.
            err_console.print(
                f"[dim]thread {report.get('threadId')} — "
                f"{report.get('status')} in {report.get('turns')} turn(s), "
                f"{report.get('toolsCalled')} tool call(s)[/dim]"
            )
            final_text = report.get("finalText") or ""
            if final_text:
                from rich.markdown import Markdown

                console.print(Markdown(final_text))
            else:
                console.print("[yellow]The agent produced no final text.[/yellow]")
            if output:
                Path(output).write_text(final_text)
    except Exception as e:
        _handle_error(e, "running the AI FDE agent loop")


@threads_app.command("list")
def list_threads(
    page_size: int = typer.Option(50, "--page-size", help="Threads per page"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """List available AI FDE threads (read-only).

    Backed by the pinned GraphQL AvailableThreadsQuery
    (``aiFdeThreadsV2``, captured contract).
    """
    try:
        with SpinnerProgressTracker().track_spinner("Listing AI FDE threads..."):
            service = AiFdeService(profile=profile)
            threads = service.list_threads(page_size=page_size)

        _emit(
            threads,
            "list_ai_fde_threads",
            format,
            output,
            page_size=page_size,
            count=len(threads),
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, "listing AI FDE threads")


@threads_app.command("get")
def get_thread(
    thread_id: str = typer.Argument(..., help="Thread ID (plain UUID, not a RID)"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load one thread's metadata (read-only).

    Backed by the pinned GraphQL ThreadMetadataQuery
    (``aiFdeThreadV2.metadataV3``): id, name, version, agentState, and
    contextItemsOrder for full threads; redacted threads return the
    reduced captured shape.
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Loading AI FDE thread {thread_id}..."
        ):
            service = AiFdeService(profile=profile)
            metadata = service.get_thread_metadata(thread_id)

        _emit(
            metadata,
            "get_ai_fde_thread",
            format,
            output,
            thread_id=thread_id,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading AI FDE thread {thread_id}")


@threads_app.command("items")
def get_thread_items(
    thread_id: str = typer.Argument(..., help="Thread ID (plain UUID, not a RID)"),
    page_size: int = typer.Option(50, "--page-size", help="Context items per page"),
    page_token: Optional[str] = typer.Option(
        None, "--page-token", help="Page token from a previous response"
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load one page of thread context items (read-only).

    Backed by the pinned GraphQL ThreadContextItemsPageQuery
    (``aiFdeThreadV2.contextItemsV2.contextItems``, captured contract).
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Loading context items for thread {thread_id}..."
        ):
            service = AiFdeService(profile=profile)
            page = service.get_thread_items(
                thread_id, page_size=page_size, page_token=page_token
            )

        _emit(
            page,
            "list_ai_fde_thread_items",
            format,
            output,
            thread_id=thread_id,
            page_size=page_size,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading context items for thread {thread_id}")


@threads_app.command("create")
def create_thread(
    name: str = typer.Option(..., "--name", help="Thread display name"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Create one AI FDE thread (write).

    Backed by the captured CreateThreadMutation — a GraphQL mutation
    allowed through the client's scoped exception (registered operation
    name + per-call opt-in only; the general mutation ban stands). The
    captured document creates the thread with ``contextItems: []`` and
    returns ``{id, version}``.
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Creating AI FDE thread '{name}'..."
        ):
            service = AiFdeService(profile=profile)
            created = service.create_thread(name)

        _emit(
            created,
            "create_ai_fde_thread",
            format,
            output,
            thread_name=name,
            thread_id=created.get("id"),
            write_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"creating AI FDE thread '{name}'")


@threads_app.command("send")
def send_message(
    thread_id: str = typer.Argument(..., help="Thread ID (plain UUID, not a RID)"),
    message: str = typer.Option(..., "--message", "-m", help="User message text"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Append a user message to a thread (write).

    Fetches the current thread metadata, appends one captured-shape
    ``user-message`` context item via PUT /ai-fde/api/threads/{id}/update,
    and prints the resulting ``threadVersion``. The message is queued in
    the thread document; the AI FDE agent loop itself runs client-side in
    the Foundry UI and is not driven by this command.

    NOTE: the delta behavior of ``itemsToWrite`` was never captured (only
    a full-thread write was observed); this sends a minimal delta — see
    the services/ai_fde.py docstring.
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Sending user message to thread {thread_id}..."
        ):
            service = AiFdeService(profile=profile)
            result = service.send_user_message(thread_id, message)

        _emit(
            result,
            "send_ai_fde_message",
            format,
            output,
            thread_id=thread_id,
            context_item_id=result.get("contextItemId"),
            thread_version=result.get("threadVersion"),
            write_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"sending user message to thread {thread_id}")


@metadata_app.command("get")
def get_thread_agent_state(
    thread_id: str = typer.Argument(..., help="Thread ID (plain UUID, not a RID)"),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load one thread's agent state (read-only).

    The agentState from the pinned ThreadMetadataQuery: system prompt,
    tool configurations, mode config, and model configuration. Redacted
    threads carry no agent state and fail loudly.
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Loading agent state for thread {thread_id}..."
        ):
            service = AiFdeService(profile=profile)
            agent_state = service.get_thread_agent_state(thread_id)

        _emit(
            agent_state,
            "get_ai_fde_thread_agent_state",
            format,
            output,
            thread_id=thread_id,
            shape_verified=True,
        )
    except Exception as e:
        _handle_error(e, f"loading agent state for thread {thread_id}")


@metadata_app.command("update")
def update_thread_metadata(
    thread_id: str = typer.Argument(..., help="Thread ID (plain UUID, not a RID)"),
    current_version: str = typer.Option(
        ...,
        "--current-version",
        help="threadVersion this modification applies to (from 'threads get')",
    ),
    agent_state: str = typer.Option(
        ...,
        "--agent-state",
        help="Path to a JSON file with the agentStateModification document "
        "('-' reads stdin); sent verbatim",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Set a thread's agent state (write).

    PUT /ai-fde/api/threads/{threadId}/metadata with body
    ``{currentVersion, agentStateModification}`` (captured contract). The
    captured modification is a full agent-state document
    (agentSystemPrompt, toolConfigurations, modeConfig,
    modelConfiguration, ...). Response carries the new ``threadVersion``.
    """
    try:
        modification = _load_json_definition(agent_state, "agent state modification")
        with SpinnerProgressTracker().track_spinner(
            f"Updating agent state for thread {thread_id}..."
        ):
            service = AiFdeService(profile=profile)
            result = service.update_thread_metadata(
                thread_id, current_version, modification
            )

        _emit(
            result,
            "update_ai_fde_thread_metadata",
            format,
            output,
            thread_id=thread_id,
            current_version=current_version,
            write_verified=True,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e, f"updating agent state for thread {thread_id}")


@settings_app.command("get")
def get_settings(
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Load the caller's AI FDE settings (read-only).

    GET /ai-fde/api/settings (captured contract): attribution settings,
    skill enablement, bulk tool approval, and model selection settings.
    """
    try:
        with SpinnerProgressTracker().track_spinner("Loading AI FDE settings..."):
            service = AiFdeService(profile=profile)
            settings = service.get_settings()

        _emit(settings, "get_ai_fde_settings", format, output, shape_verified=True)
    except Exception as e:
        _handle_error(e, "loading AI FDE settings")


@settings_app.command("update")
def update_settings(
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Path to a JSON file with the settings modification document "
        "('-' reads stdin); sent verbatim",
    ),
    profile: Optional[str] = _profile_option(),
    format: str = _format_option(),
    output: Optional[str] = _output_option(),
):
    """Update AI FDE settings (write).

    POST /ai-fde/api/settings. The body is a settings modification
    document sent verbatim; the captured shape wraps each section in an
    unchanged/modification union (only the skillEnablementSettings
    modification arm was observed). Success response is ``{}``.
    """
    try:
        body = _load_json_definition(definition, "settings modification")
        with SpinnerProgressTracker().track_spinner("Updating AI FDE settings..."):
            service = AiFdeService(profile=profile)
            result = service.update_settings(body)

        _emit(
            result,
            "update_ai_fde_settings",
            format,
            output,
            write_verified=True,
        )
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e, "updating AI FDE settings")
