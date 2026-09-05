"""
AI FDE thread and settings commands.

Thread primitives (list/get/items/create/send, agent-state metadata) plus
user settings, backed by the internal ai-fde Conjure service and the
GraphQL bulk gateway (contracts captured from the live AI FDE UI via CDP,
2026-09-04; see services/ai_fde.py docstring). The AI FDE agent loop runs
client-side in the Foundry UI — these commands manage the thread document,
not the LLM loop (see tickets/TICKET-009-ai-fde.md).

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
from ..services.errors import FoundryApiError
from ..utils.agent_output import agent_mode_enabled, buffer_agent_payload
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


def _emit(payload: Any, operation: str, format: str, output: Optional[str], **meta: Any) -> None:
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
    elif isinstance(e, (AiFdeShapeError, AiFdeGraphQLError, FoundryApiError)):
        console.print(f"[red]{e}[/red]")
    else:
        console.print(f"[red]Error {action}: {e}[/red]")
    raise typer.Exit(1) from e


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
        with SpinnerProgressTracker().track_spinner(f"Creating AI FDE thread '{name}'..."):
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
