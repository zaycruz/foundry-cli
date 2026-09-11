"""Developer Console commands: OSDK reads, SDK generation, and installs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import typer

from ..auth.base import MissingCredentialsError, ProfileNotFoundError
from ..services.dev_console import DeveloperConsoleService, SdkDefinitionDriftError
from ..services.foundry_internal_client import TokenExpiredError
from ..utils.agent_output import buffer_agent_payload, resolve_output_format
from ..utils.completion import complete_output_format, complete_profile, complete_rid

app = typer.Typer(
    help="Developer Console operations for generated OSDK packages",
    no_args_is_help=True,
)
osdk_app = typer.Typer(help="Inspect generated OSDK definitions", no_args_is_help=True)
sdk_app = typer.Typer(help="Generate and install SDK packages", no_args_is_help=True)
app.add_typer(osdk_app, name="osdk")
app.add_typer(sdk_app, name="sdk")


@app.command("connect")
def dev_console_connect(
    application_rid: str = typer.Argument(
        ...,
        help="Third-party application Resource Identifier",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name",
        autocompletion=complete_profile,
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format (json, table)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Resolve and validate an app's dev-console connection context.

    Divergence from the vendor MCP: connect_to_dev_console_app is an
    interactive IDE/workspace action with no headless equivalent, so this
    command is its honest READ-ONLY form. It reads the application via the
    VERIFIED TPAS getApplication endpoint and reports the connection context
    (client/credentials type, OAuth grants, redirect URLs, data scope). No
    session is established and nothing is mutated.
    """

    if format not in {"json", "table"}:
        raise typer.BadParameter("must be json or table", param_hint="--format")
    try:
        result = DeveloperConsoleService(profile=profile).get_connection_context(
            application_rid
        )
    except TokenExpiredError:
        typer.echo(
            "DEGRADED [token-expired]: Foundry session token expired; "
            "re-authenticate before retrying this connection-context read"
        )
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except SdkDefinitionDriftError as exc:
        typer.echo(f"DRIFT [application-shape]: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)

    rendered = _render_connect(result, format)
    if rendered:
        typer.echo(rendered, nl=False)


@app.command("convert-osdk-react")
def convert_osdk_react(
    application_rid: str = typer.Argument(
        ...,
        help="Third-party application Resource Identifier",
        autocompletion=complete_rid,
    ),
    output_dir: Path = typer.Option(
        ...,
        "--output-dir",
        "-o",
        help="Directory to write the generated React components into",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing generated files (default: refuse)",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name",
        autocompletion=complete_profile,
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Generate typed React component scaffolds from an app's OSDK.

    Local codegen, never network-mutating: reads the app's data scope via
    the VERIFIED TPAS getApplication endpoint and the ontology's object
    types via the public v2 API, then writes one typed presentational
    <ApiName>Card.tsx per in-scope object type plus an index.ts barrel.
    Existing files are never overwritten without --force.
    """

    if format not in {"table", "json"}:
        raise typer.BadParameter("must be table or json", param_hint="--format")
    try:
        result = DeveloperConsoleService(profile=profile).generate_react_scaffold(
            application_rid, output_dir, force=force
        )
    except TokenExpiredError:
        typer.echo(
            "DEGRADED [token-expired]: Foundry session token expired; "
            "re-authenticate before retrying this scaffold generation"
        )
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except SdkDefinitionDriftError as exc:
        typer.echo(f"DRIFT [object-type-shape]: {exc}")
        raise typer.Exit(1)
    except OSError as exc:
        typer.echo(f"Error writing scaffold into '{output_dir}': {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)

    rendered = _render_convert(result, format)
    if rendered:
        typer.echo(rendered, nl=False)

    status = result.get("status")
    if status == "unresolved":
        raise typer.Exit(2)
    if status == "conflict":
        raise typer.Exit(1)


@sdk_app.command("generate")
def sdk_generate(
    application_rid: str = typer.Argument(
        ...,
        help="Third-party application Resource Identifier",
        autocompletion=complete_rid,
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Mint a real SDK version (default: dry-run plan only)",
    ),
    no_wait: bool = typer.Option(
        False,
        "--no-wait",
        help="Return after the createSdkV2 POST without polling for completion",
    ),
    timeout: float = typer.Option(
        180.0,
        "--timeout",
        help="Max seconds to poll for npm generation to finish (default: 180)",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name",
        autocompletion=complete_profile,
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Mint a new OSDK version for an app (plan-first; --apply mutates).

    Backed by the contract-derived, contract-verified createSdkV2 contract: the current
    metadata.applicationVersion is read via the VERIFIED getApplication
    endpoint, then POST /application-sdks/v2/{applicationRid} with exactly
    {"applicationVersion": N, "npm": {}} mints the next SDK version.
    Without --apply the command prints the dry-run plan (resolved version
    and exact body) and sends nothing mutating. With --apply the POST is
    issued and npm.status.type is polled from 'requested' to a terminal
    state (~24s observed) unless --no-wait is given.
    """

    if format not in {"table", "json"}:
        raise typer.BadParameter("must be table or json", param_hint="--format")
    try:
        result = DeveloperConsoleService(profile=profile).generate_sdk(
            application_rid,
            apply=apply,
            wait=not no_wait,
            timeout_seconds=timeout,
        )
    except TokenExpiredError:
        typer.echo(
            "DEGRADED [token-expired]: Foundry session token expired; "
            "re-authenticate before retrying this SDK generation"
        )
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except SdkDefinitionDriftError as exc:
        typer.echo(f"DRIFT [sdk-generate-shape]: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)

    rendered = _render_generate(result, format)
    if rendered:
        typer.echo(rendered, nl=False)

    status = result.get("status")
    if status == "failed":
        raise typer.Exit(1)
    if status == "timeout":
        raise typer.Exit(2)


@osdk_app.command("definition")
def osdk_definition(
    application_rid: str = typer.Argument(
        ...,
        help="Third-party application Resource Identifier",
        autocompletion=complete_rid,
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        "-v",
        help="Specific SDK version (default: latest)",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name",
        autocompletion=complete_profile,
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format (json, table)",
        autocompletion=complete_output_format,
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Read an application's generated OSDK definition (read-only)."""

    if format not in {"json", "table"}:
        raise typer.BadParameter("must be json or table", param_hint="--format")
    try:
        result = DeveloperConsoleService(profile=profile).get_sdk(
            application_rid, version
        )
    except TokenExpiredError:
        typer.echo(
            "DEGRADED [token-expired]: Foundry session token expired; "
            "re-authenticate before retrying this OSDK definition read"
        )
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except SdkDefinitionDriftError as exc:
        typer.echo(f"DRIFT [sdk-definition-shape]: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)

    rendered = _render_definition(result, format)
    if rendered:
        if output is not None:
            try:
                output.write_text(rendered, encoding="utf-8")
            except OSError as exc:
                typer.echo(f"Error writing output file '{output}': {exc}")
                raise typer.Exit(1)
        else:
            typer.echo(rendered, nl=False)


@sdk_app.command("install")
def sdk_install(
    application_rid: str = typer.Argument(
        ...,
        help="Third-party application Resource Identifier",
        autocompletion=complete_rid,
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        "-v",
        help="Specific SDK version (default: latest)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Execute the install into the active virtualenv (pip only)",
    ),
    target: Optional[Path] = typer.Option(
        None,
        "--target",
        help="Directory to install into (pip --target / npm --prefix)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Resolve and print the install plan without executing it",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name",
        autocompletion=complete_profile,
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Install a generated OSDK package into the local environment.

    Resolves the app's SDK repository via the verified getSdkRepositoryRid
    endpoint and installs from the stack's Artifacts npm/pypi registry.
    Non-destructive by default: without --yes or --target the command prints
    the resolved plan (dry-run) and changes nothing.
    """

    if format not in {"table", "json"}:
        raise typer.BadParameter("must be table or json", param_hint="--format")
    try:
        result = DeveloperConsoleService(profile=profile).install_sdk_package(
            application_rid,
            version=version,
            yes=yes,
            target=target,
            dry_run=dry_run,
        )
    except TokenExpiredError:
        typer.echo(
            "DEGRADED [token-expired]: Foundry session token expired; "
            "re-authenticate before retrying this SDK install"
        )
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as exc:
        typer.echo(f"Authentication Error: {exc}")
        raise typer.Exit(1)
    except SdkDefinitionDriftError as exc:
        typer.echo(f"DRIFT [sdk-definition-shape]: {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)

    rendered = _render_install(result, format)
    if rendered:
        typer.echo(rendered, nl=False)

    status = result.get("status")
    if status == "unresolved":
        # Residual gap: coordinates could not be verified, nothing executed.
        raise typer.Exit(2)
    if status == "failed":
        raise typer.Exit(1)


def _render_definition(result: Mapping[str, Any], format_type: str) -> str:
    if resolve_output_format(format_type) == "agent":
        # Buffered, not returned: the caller echoes this string, and a second
        # document on stdout is exactly what the agent contract forbids.
        buffer_agent_payload(result, meta={"result_type": "osdk-definition"})
        return ""
    if format_type == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"
    definition = result.get("definition")
    keys = (
        sorted(str(key) for key in definition)
        if isinstance(definition, Mapping)
        else []
    )
    lines = [
        f"Application: {result.get('application_rid') or 'unknown'}",
        f"SDK version: {result.get('version') or 'unknown'}",
        f"Definition keys: {', '.join(keys) if keys else 'none'}",
    ]
    return "\n".join(lines) + "\n"


def _render_install(result: Mapping[str, Any], format_type: str) -> str:
    status = result.get("status")
    if resolve_output_format(format_type) == "agent":
        warnings = list(result.get("warnings") or [])
        errors = (
            [{"type": "unresolved", "message": str(result.get("reason"))}]
            if status == "unresolved"
            else None
        )
        buffer_agent_payload(
            result,
            meta={"result_type": "sdk-install", "status": status},
            warnings=warnings,
            errors=errors,
        )
        return ""
    if format_type == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"

    lines = [
        f"SDK INSTALL [{status}]",
        f"Application: {result.get('application_rid') or 'unknown'}",
        f"SDK version: {result.get('sdk_version') or 'unknown'}",
        f"Repository: {result.get('repository_rid') or 'unknown'}",
    ]
    for warning in result.get("warnings") or []:
        lines.append(f"WARNING: {warning}")
    if status == "unresolved":
        lines.append(f"RESIDUAL GAP: {result.get('reason')}")
        return "\n".join(lines) + "\n"
    steps = result.get("steps") or []
    if status == "dry-run":
        lines.append("Dry-run: nothing was executed. Re-run with --yes or --target.")
    lines.append("Steps:")
    for step in steps:
        lines.append(f"  [{' '.join(str(part) for part in step.get('command') or [])}]")
    for entry in result.get("executed") or []:
        if entry.get("refused"):
            lines.append(f"REFUSED: {entry['refused']}")
        elif entry.get("returncode") != 0:
            lines.append(
                f"FAILED (rc={entry.get('returncode')}): {entry.get('package')}"
            )
    return "\n".join(lines) + "\n"


def _render_connect(result: Mapping[str, Any], format_type: str) -> str:
    if resolve_output_format(format_type) == "agent":
        buffer_agent_payload(
            result,
            meta={"result_type": "dev-console-connect", "status": result.get("status")},
            warnings=list(result.get("warnings") or []),
        )
        return ""
    if format_type == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"
    grants = result.get("grants") or {}
    grant_text = (
        ", ".join(
            f"{name}={'on' if enabled else 'off'}"
            for name, enabled in sorted(grants.items())
        )
        or "none reported"
    )
    data_scope = result.get("data_scope") or {}
    lines = [
        f"CONNECTION [{result.get('status')}] ({result.get('mode')})",
        f"Application: {result.get('name') or 'unknown'} "
        f"({result.get('application_rid') or 'unknown'})",
        f"Organization: {result.get('organization_rid') or 'unknown'}",
        f"Client type: {result.get('client_type') or 'unknown'}",
        f"Grants: {grant_text}",
        f"Redirect URLs: {len(result.get('redirect_urls') or [])}",
        f"Data scope: ontology {data_scope.get('ontology_rid') or 'unknown'}, "
        f"object types {data_scope.get('objectTypes', '?')}, "
        f"link types {data_scope.get('linkTypes', '?')}, "
        f"action types {data_scope.get('actionTypes', '?')}",
    ]
    for warning in result.get("warnings") or []:
        lines.append(f"NOTE: {warning}")
    return "\n".join(lines) + "\n"


def _render_generate(result: Mapping[str, Any], format_type: str) -> str:
    status = result.get("status")
    if resolve_output_format(format_type) == "agent":
        errors = None
        if status == "failed":
            errors = [
                {
                    "type": "generation-failed",
                    "message": (
                        "npm.status.type reached a terminal state other "
                        f"than success: {result.get('npm_status')}"
                    ),
                }
            ]
        elif status == "timeout":
            errors = [{"type": "timeout", "message": str(result.get("reason"))}]
        buffer_agent_payload(
            result,
            meta={"result_type": "sdk-generate", "status": status},
            warnings=list(result.get("warnings") or []),
            errors=errors,
        )
        return ""
    if format_type == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"

    request = result.get("request") or {}
    application_version = result.get("application_version")
    lines = [
        f"SDK GENERATE [{status}]",
        f"Application: {result.get('application_rid') or 'unknown'}",
        "Application version: "
        + (str(application_version) if application_version is not None else "unknown"),
        f"Request: {request.get('verb') or 'POST'} {request.get('path') or ''}",
        f"Body: {json.dumps(request.get('body') or {}, sort_keys=True)}",
    ]
    if status == "dry-run":
        lines.append(
            "Dry-run: nothing was sent. Re-run with --apply to mint the SDK version."
        )
        return "\n".join(lines) + "\n"

    lines.append(f"SDK version: {result.get('sdk_version') or 'unknown'}")
    lines.append(f"npm package: {result.get('npm_package_name') or 'unknown'}")
    lines.append(f"npm status: {result.get('npm_status') or 'unknown'}")
    poll = result.get("poll")
    if isinstance(poll, Mapping):
        lines.append(
            f"Polled {poll.get('attempts')} time(s) over {poll.get('elapsed_seconds')}s"
        )
    if status == "timeout":
        lines.append(f"TIMEOUT: {result.get('reason')}")
    if status == "failed":
        lines.append(
            "Generation failed server-side "
            f"(npm.status.type = {result.get('npm_status')})."
        )
    return "\n".join(lines) + "\n"


def _render_convert(result: Mapping[str, Any], format_type: str) -> str:
    status = result.get("status")
    if resolve_output_format(format_type) == "agent":
        errors = None
        if status == "unresolved":
            errors = [{"type": "unresolved", "message": str(result.get("reason"))}]
        elif status == "conflict":
            errors = [{"type": "conflict", "message": str(result.get("reason"))}]
        buffer_agent_payload(
            result,
            meta={"result_type": "convert-osdk-react", "status": status},
            warnings=list(result.get("warnings") or []),
            errors=errors,
        )
        return ""
    if format_type == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"

    lines = [
        f"CONVERT-OSDK-REACT [{status}]",
        f"Application: {result.get('application_rid') or 'unknown'}",
        f"Output directory: {result.get('output_dir') or 'unknown'}",
        f"Object types: {len(result.get('object_types') or [])}",
    ]
    for warning in result.get("warnings") or []:
        lines.append(f"WARNING: {warning}")
    if status in {"unresolved", "conflict"}:
        lines.append(f"RESIDUAL GAP: {result.get('reason')}")
        return "\n".join(lines) + "\n"
    for path in result.get("files") or []:
        lines.append(f"  wrote {path}")
    return "\n".join(lines) + "\n"
