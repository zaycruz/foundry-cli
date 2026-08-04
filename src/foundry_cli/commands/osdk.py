"""Read-only Ontology SDK (OSDK) context and examples.

Context comes from the live ontology (via the installed foundry-platform-sdk)
plus the vendored OSDK package type declarations; examples quote Palantir's
public OSDK documentation verbatim and mark any generated binding snippet as
``generated: true``. Nothing here mutates Foundry state.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

import typer

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..services.osdk import OsdkService
from ..utils.agent_output import buffer_agent_payload, resolve_output_format
from ..utils.completion import complete_output_format, complete_profile

app = typer.Typer(help="Inspect Ontology SDK (OSDK) context and examples")

_FORMATS = {"markdown", "json"}


def _check_format(format_type: str) -> None:
    if format_type not in _FORMATS:
        raise typer.BadParameter("must be markdown or json", param_hint="--format")


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


@app.command("context")
def osdk_context(
    ontology: Optional[str] = typer.Option(
        None,
        "--ontology",
        "-o",
        help="Ontology RID or API name (defaults to the single visible ontology)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Show OSDK codegen context for the live ontology."""
    _check_format(format)
    try:
        result = OsdkService(profile=profile).sdk_context(ontology)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(result, format, result_type="osdk-context", human=_render_context(result))
    if result.get("status") != "ok":
        raise typer.Exit(1)


def _render_context(result: Mapping[str, Any]) -> str:
    if result.get("status") != "ok":
        lines = [f"UNAVAILABLE: {result.get('reason', 'unknown')}"]
        for choice in result.get("choices") or []:
            lines.append(
                f"  {choice.get('api_name') or 'unknown'} ({choice.get('rid')})"
            )
        return "\n".join(lines) + "\n"
    ontology = result.get("ontology") or {}
    lines = [
        f"Ontology: {ontology.get('api_name') or 'unknown'} ({ontology.get('rid')})",
        "",
        "Live ontology entities:",
    ]
    entities = result.get("entities") or {}
    for field, summary in entities.items():
        count = summary.get("count")
        names = summary.get("names") or []
        suffix = ", ".join(names[:10]) + (" ..." if summary.get("truncated") else "")
        lines.append(f"  {field}: {count}" + (f" — {suffix}" if suffix else ""))
    osdk = result.get("osdk") or {}
    lines.append("")
    lines.append("Vendored OSDK packages:")
    for package in osdk.get("packages") or []:
        lines.append(
            f"  {package['name']}@{package['version']} ({package['provenance']})"
        )
    components = osdk.get("components") or {}
    lines.append(f"  {len(components)} declared API components")
    lines.append("")
    lines.append("Sources:")
    for source in result.get("sources") or []:
        lines.append(f"  {source}")
    return "\n".join(lines) + "\n"


@app.command("examples")
def osdk_examples(
    ontology: Optional[str] = typer.Option(
        None,
        "--ontology",
        "-o",
        help="Ontology RID or API name (defaults to the single visible ontology)",
    ),
    language: str = typer.Option(
        "typescript",
        "--language",
        "-l",
        help="Example language (typescript, python)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Show real OSDK usage examples plus live-ontology bindings."""
    _check_format(format)
    if language not in {"typescript", "python"}:
        raise typer.BadParameter(
            "must be typescript or python", param_hint="--language"
        )
    try:
        result = OsdkService(profile=profile).sdk_examples(ontology, language=language)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(result, format, result_type="osdk-examples", human=_render_examples(result))
    if result.get("status") != "ok":
        raise typer.Exit(1)


def _render_examples(result: Mapping[str, Any]) -> str:
    if result.get("status") != "ok":
        return f"UNAVAILABLE: {result.get('reason', 'unknown')}\n"
    lines = [f"OSDK examples ({result.get('language')})"]
    ontology = result.get("ontology") or {}
    if ontology.get("rid"):
        lines.append(
            f"Ontology: {ontology.get('api_name') or 'unknown'} ({ontology.get('rid')})"
        )
    for warning in result.get("warnings") or []:
        lines.append(f"WARNING: {warning}")
    lines.append("")
    lines.append("Documentation examples (verbatim from Palantir docs):")
    doc_examples = result.get("documentation_examples") or []
    if not doc_examples:
        lines.append("  none retrieved")
    for example in doc_examples[:10]:
        lines.append(f"  # source: {example.get('source_url')}")
        lines.append(f"  ```{example.get('language') or ''}")
        lines.extend(f"  {line}" for line in example.get("code", "").splitlines())
        lines.append("  ```")
    bindings = result.get("binding_examples") or []
    if bindings:
        lines.append("")
        lines.append("Live-ontology bindings (generated; marked generated: true):")
        for example in bindings[:10]:
            lines.append(f"  # {example.get('kind')} — {example.get('entity')}")
            lines.append(f"  {example.get('code')}")
    return "\n".join(lines) + "\n"
