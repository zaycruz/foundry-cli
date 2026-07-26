"""Read-only introspection of the installed foundry-platform-sdk.

Enumerates and describes the platform SDK API surface from the installed
package's own source — no network, no Foundry profile required.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import typer

from ..services.platform_sdk import PlatformSdkError, PlatformSdkService
from ..utils.agent_output import buffer_agent_payload, resolve_output_format
from ..utils.completion import complete_output_format

app = typer.Typer(help="Inspect the installed foundry-platform-sdk API surface")
api_app = typer.Typer(help="List and describe platform SDK APIs")
app.add_typer(api_app, name="api")

_FORMATS = {"table", "json"}


def _service() -> PlatformSdkService:
    return PlatformSdkService()


def _check_format(format_type: str) -> None:
    if format_type not in _FORMATS:
        raise typer.BadParameter("must be table or json", param_hint="--format")


def _emit(
    result: Mapping[str, Any], format_type: str, *, result_type: str, human: str
) -> None:
    if resolve_output_format(format_type) == "agent":
        buffer_agent_payload(dict(result), meta={"result_type": result_type})
        return
    if format_type == "json":
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    typer.echo(human, nl=False)


@api_app.command("list")
def api_list(
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """List every namespace, resource, and method of the installed SDK."""
    _check_format(format)
    try:
        result = _service().list_apis()
    except PlatformSdkError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(result, format, result_type="platform-sdk-apis", human=_render_list(result))


def _render_list(result: Mapping[str, Any]) -> str:
    lines = [
        f"{result.get('sdk')}=={result.get('version')} "
        f"({result.get('namespace_count')} namespaces)",
        f"Source: {result.get('sdk_root')}",
        "",
    ]
    for namespace, data in (result.get("namespaces") or {}).items():
        lines.append(
            f"{namespace} ({data['resource_count']} resources, "
            f"{data['method_count']} methods)"
        )
        for resource, resource_data in (data.get("resources") or {}).items():
            method_names = ", ".join(
                method["name"] for method in resource_data.get("methods") or []
            )
            lines.append(f"  {resource}: {method_names}")
    return "\n".join(lines) + "\n"


@api_app.command("reference")
def api_reference(
    dotted: str = typer.Argument(
        ...,
        help="API to describe: namespace[.resource[.method]], "
        "e.g. ontologies.Ontology.get_full_metadata",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Show the verbatim docstring/signature for one SDK API."""
    _check_format(format)
    try:
        result = _service().api_reference(dotted)
    except PlatformSdkError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(
        result,
        format,
        result_type="platform-sdk-api-reference",
        human=_render_reference(result),
    )
    if result.get("status") != "ok":
        raise typer.Exit(1)


def _render_reference(result: Mapping[str, Any]) -> str:
    if result.get("status") != "ok":
        lines = [f"NOT FOUND: {result.get('reason', 'unknown')}"]
        available = result.get("available") or []
        if available:
            lines.append(
                "Available: " + ", ".join(str(item) for item in available[:20])
            )
        return "\n".join(lines) + "\n"
    kind = result.get("kind")
    if kind == "method":
        return (
            f"{result['namespace']}.{result['resource']}.{result['name']}"
            f"{result.get('signature')}\n"
            f"SDK: {result.get('sdk')}=={result.get('version')}\n"
            "---\n"
            f"{result.get('docstring') or '(no docstring)'}\n"
        )
    if kind == "resource":
        lines = [
            f"{result['namespace']}.{result['resource']} ({result.get('module')})",
            "Methods:",
        ]
        for method in result.get("methods") or []:
            summary = f" — {method['summary']}" if method.get("summary") else ""
            lines.append(f"  {method['name']}{summary}")
        return "\n".join(lines) + "\n"
    lines = [f"namespace {result['namespace']}"]
    for resource, resource_data in (result.get("resources") or {}).items():
        lines.append(
            f"  {resource} ({len(resource_data.get('methods') or [])} methods)"
        )
    return "\n".join(lines) + "\n"
