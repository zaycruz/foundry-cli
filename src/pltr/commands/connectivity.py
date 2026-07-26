"""
Connectivity management commands for Foundry connections and imports.
"""

import typer
import json
from pathlib import Path
from typing import List, Optional
from rich.console import Console

from ..services.connectivity import (
    ConnectivityService,
    EgressPolicyNotFoundError,
    EgressPolicyShapeError,
    RestSourceShapeError,
    WebhookNotFoundError,
    WebhookShapeError,
)
from ..utils.agent_output import agent_mode_enabled, buffer_agent_payload
from ..utils.formatting import OutputFormatter
from ..utils.progress import SpinnerProgressTracker
from ..auth.base import ProfileNotFoundError, MissingCredentialsError
from ..utils.completion import (
    complete_rid,
    complete_profile,
    complete_output_format,
    cache_rid,
)

app = typer.Typer()
connection_app = typer.Typer()
import_app = typer.Typer()
webhook_app = typer.Typer()
egress_app = typer.Typer()
rest_source_app = typer.Typer()
console = Console()
formatter = OutputFormatter(console)

# Add sub-apps
app.add_typer(connection_app, name="connection", help="Manage connections")
app.add_typer(import_app, name="import", help="Manage data imports")
app.add_typer(webhook_app, name="webhook", help="Manage data-source webhooks")
app.add_typer(egress_app, name="egress", help="Inspect network egress policies")
app.add_typer(rest_source_app, name="rest-source", help="Manage REST API data sources")


def _load_json_param(
    json_str: Optional[str], file_path: Optional[str], param_name: str
) -> dict:
    """
    Load JSON from either a string or a file.

    Args:
        json_str: JSON string (optional)
        file_path: Path to JSON file (optional)
        param_name: Name of parameter for error messages

    Returns:
        Parsed JSON dictionary

    Raises:
        typer.Exit: If neither or both are provided, or if parsing fails
    """
    if json_str and file_path:
        console.print(
            f"[red]Cannot specify both {param_name} and {param_name}-file[/red]"
        )
        raise typer.Exit(1)

    if not json_str and not file_path:
        console.print(
            f"[red]Must specify either {param_name} or --{param_name}-file[/red]"
        )
        raise typer.Exit(1)

    if file_path:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            raise typer.Exit(1)
        try:
            json_str = path.read_text()
        except Exception as e:
            console.print(f"[red]Error reading {file_path}: {e}[/red]")
            raise typer.Exit(1)

    try:
        return json.loads(json_str)  # type: ignore[arg-type]
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON for {param_name}: {e}[/red]")
        raise typer.Exit(1)


def _load_json_list_param(
    json_str: Optional[str], file_path: Optional[str], param_name: str
) -> List[dict]:
    """Load a JSON array from either a string or a file (see _load_json_param)."""
    value = _load_json_param(json_str, file_path, param_name)
    if not isinstance(value, list):
        console.print(f"[red]{param_name} must be a JSON array[/red]")
        raise typer.Exit(1)
    return value


@connection_app.command("list")
def list_connections(
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List available connections."""
    try:
        with SpinnerProgressTracker().track_spinner("Fetching connections..."):
            service = ConnectivityService(profile=profile)
            connections = service.list_connections()

        if not connections:
            console.print("[yellow]No connections found[/yellow]")
            return

        formatter.format_output(connections, format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing connections: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("get")
def get_connection(
    connection_rid: str = typer.Argument(
        ..., help="Connection Resource Identifier", autocompletion=complete_rid
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get detailed information about a specific connection."""
    try:
        cache_rid(connection_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching connection {connection_rid}..."
        ):
            service = ConnectivityService(profile=profile)
            connection = service.get_connection(connection_rid)

        formatter.format_output([connection], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting connection: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("create")
def create_connection(
    display_name: str = typer.Argument(..., help="Display name for the connection"),
    parent_folder_rid: str = typer.Argument(
        ..., help="Parent folder Resource Identifier", autocompletion=complete_rid
    ),
    configuration: Optional[str] = typer.Argument(
        None, help="Connection configuration in JSON format"
    ),
    worker: Optional[str] = typer.Argument(
        None, help="Worker configuration in JSON format"
    ),
    config_file: Optional[str] = typer.Option(
        None, "--config-file", help="Path to JSON file with connection configuration"
    ),
    worker_file: Optional[str] = typer.Option(
        None, "--worker-file", help="Path to JSON file with worker configuration"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a new connection.

    Configuration and worker can be provided as JSON strings or via file options.
    """
    try:
        cache_rid(parent_folder_rid)

        # Load configuration from string or file
        config_dict = _load_json_param(configuration, config_file, "configuration")
        worker_dict = _load_json_param(worker, worker_file, "worker")

        service = ConnectivityService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Creating connection..."):
            connection = service.create_connection(
                display_name=display_name,
                parent_folder_rid=parent_folder_rid,
                configuration=config_dict,
                worker=worker_dict,
            )

        cache_rid(connection.get("rid", ""))
        console.print(f"[green]Connection created: {connection.get('rid')}[/green]")
        formatter.format_output([connection], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating connection: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("get-config")
def get_connection_configuration(
    connection_rid: str = typer.Argument(
        ..., help="Connection Resource Identifier", autocompletion=complete_rid
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get connection configuration."""
    try:
        cache_rid(connection_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching configuration for {connection_rid}..."
        ):
            service = ConnectivityService(profile=profile)
            config = service.get_connection_configuration(connection_rid)

        formatter.format_output([config], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting connection configuration: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("update-secrets")
def update_connection_secrets(
    connection_rid: str = typer.Argument(
        ..., help="Connection Resource Identifier", autocompletion=complete_rid
    ),
    secrets_file: str = typer.Option(
        ...,
        "--secrets-file",
        "-s",
        help="Path to JSON file containing secrets (mapping secret names to values)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
):
    """Update connection secrets.

    Secrets must be provided via a file for security (to avoid exposure in shell
    history or process listings).
    """
    try:
        cache_rid(connection_rid)

        # Load secrets from file
        path = Path(secrets_file)
        if not path.exists():
            console.print(f"[red]Secrets file not found: {secrets_file}[/red]")
            raise typer.Exit(1)

        try:
            secrets_content = path.read_text()
            secrets_dict = json.loads(secrets_content)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON in secrets file: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error reading secrets file: {e}[/red]")
            raise typer.Exit(1)

        service = ConnectivityService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Updating secrets..."):
            service.update_secrets(connection_rid, secrets_dict)

        console.print(
            f"[green]Secrets updated for connection: {connection_rid}[/green]"
        )

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error updating secrets: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("update-export-settings")
def update_export_settings(
    connection_rid: str = typer.Argument(
        ..., help="Connection Resource Identifier", autocompletion=complete_rid
    ),
    settings: Optional[str] = typer.Argument(
        None, help="Export settings in JSON format"
    ),
    settings_file: Optional[str] = typer.Option(
        None, "--settings-file", help="Path to JSON file with export settings"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
):
    """Update connection export settings.

    Settings can be provided as a JSON string or via --settings-file.
    """
    try:
        cache_rid(connection_rid)

        # Load settings from string or file
        settings_dict = _load_json_param(settings, settings_file, "settings")

        service = ConnectivityService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Updating export settings..."):
            service.update_export_settings(connection_rid, settings_dict)

        console.print(
            f"[green]Export settings updated for connection: {connection_rid}[/green]"
        )

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error updating export settings: {e}[/red]")
        raise typer.Exit(1)


@connection_app.command("upload-jdbc-drivers")
def upload_jdbc_drivers(
    connection_rid: str = typer.Argument(
        ..., help="Connection Resource Identifier", autocompletion=complete_rid
    ),
    driver_files: List[str] = typer.Argument(
        ..., help="Path(s) to JAR file(s) to upload"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Upload custom JDBC drivers to a connection.

    Only JAR files are supported.
    """
    try:
        cache_rid(connection_rid)

        # Validate files exist and are JAR files before uploading
        for driver_file in driver_files:
            path = Path(driver_file)
            if not path.exists():
                console.print(f"[red]File not found: {driver_file}[/red]")
                raise typer.Exit(1)
            if path.suffix.lower() != ".jar":
                console.print(f"[red]File must be a JAR file: {driver_file}[/red]")
                raise typer.Exit(1)

        service = ConnectivityService(profile=profile)
        results = []

        for driver_file in driver_files:
            with SpinnerProgressTracker().track_spinner(f"Uploading {driver_file}..."):
                result = service.upload_custom_jdbc_drivers(connection_rid, driver_file)
                results.append(result)
            console.print(f"[green]Uploaded: {driver_file}[/green]")

        formatter.format_output(results, format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error uploading JDBC drivers: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("list-file")
def list_file_imports(
    connection_rid: str = typer.Option(
        ...,
        "--connection",
        "-c",
        help="Connection Resource Identifier",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List file imports for a connection."""
    try:
        cache_rid(connection_rid)

        with SpinnerProgressTracker().track_spinner("Fetching file imports..."):
            service = ConnectivityService(profile=profile)
            imports = service.list_file_imports(connection_rid=connection_rid)

        if not imports:
            console.print("[yellow]No file imports found[/yellow]")
            return

        formatter.format_output(imports, format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing file imports: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("list-table")
def list_table_imports(
    connection_rid: str = typer.Option(
        ...,
        "--connection",
        "-c",
        help="Connection Resource Identifier",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List table imports for a connection."""
    try:
        cache_rid(connection_rid)

        with SpinnerProgressTracker().track_spinner("Fetching table imports..."):
            service = ConnectivityService(profile=profile)
            imports = service.list_table_imports(connection_rid=connection_rid)

        if not imports:
            console.print("[yellow]No table imports found[/yellow]")
            return

        formatter.format_output(imports, format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing table imports: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("get-file")
def get_file_import(
    import_rid: str = typer.Argument(
        ..., help="File import Resource Identifier", autocompletion=complete_rid
    ),
    connection_rid: str = typer.Option(
        ...,
        "--connection",
        "-c",
        help="Connection Resource Identifier",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get detailed information about a specific file import."""
    try:
        cache_rid(connection_rid)
        cache_rid(import_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching file import {import_rid}..."
        ):
            service = ConnectivityService(profile=profile)
            file_import = service.get_file_import(connection_rid, import_rid)

        formatter.format_output([file_import], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting file import: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("get-table")
def get_table_import(
    import_rid: str = typer.Argument(
        ..., help="Table import Resource Identifier", autocompletion=complete_rid
    ),
    connection_rid: str = typer.Option(
        ...,
        "--connection",
        "-c",
        help="Connection Resource Identifier",
        autocompletion=complete_rid,
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name", autocompletion=complete_profile
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format (table, json, csv)",
        autocompletion=complete_output_format,
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get detailed information about a specific table import."""
    try:
        cache_rid(connection_rid)
        cache_rid(import_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching table import {import_rid}..."
        ):
            service = ConnectivityService(profile=profile)
            table_import = service.get_table_import(connection_rid, import_rid)

        formatter.format_output([table_import], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting table import: {e}[/red]")
        raise typer.Exit(1)


@webhook_app.command("get")
def get_webhook(
    webhook_rid: str = typer.Argument(
        ..., help="Webhook Resource Identifier", autocompletion=complete_rid
    ),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        help="Specific webhook version to fetch (default: latest)",
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
    """View a REST API data-source webhook definition (read-only).

    Reads the webhook registry via the internal webhooks API
    (GET /webhooks/api/registry/v0/{webhookRid}/latest, or /version/{version}
    when --version is given).
    """
    try:
        cache_rid(webhook_rid)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching webhook {webhook_rid}..."
        ):
            service = ConnectivityService(profile=profile)
            webhook = service.get_webhook(webhook_rid, version=version)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                webhook,
                meta={
                    "operation": "view_foundry_rest_api_data_source_webhook",
                    "webhook_rid": webhook_rid,
                    "version": version if version is not None else "latest",
                },
            )
        else:
            formatter.format_output([webhook], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except WebhookNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error getting webhook: {e}[/red]")
        raise typer.Exit(1)


@webhook_app.command("create")
def create_webhook(
    name: str = typer.Argument(..., help="Webhook display name"),
    source_rid: str = typer.Option(
        ...,
        "--source-rid",
        help="Magritte source RID the webhook targets",
        autocompletion=complete_rid,
    ),
    api_name: Optional[str] = typer.Option(
        None,
        "--api-name",
        help="Webhook API name (default: the display name; the server "
        "enforces a pattern -- a letters-only PascalCase name like "
        "'Getbars' is accepted, trailing digits were rejected in validation)",
    ),
    description: str = typer.Option("", "--description", help="Webhook description"),
    spec: Optional[str] = typer.Option(
        None, "--spec", help="Full webhook spec override as JSON"
    ),
    spec_file: Optional[str] = typer.Option(
        None, "--spec-file", help="Path to a JSON file with the full webhook spec"
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
    """Create a REST API data-source webhook (plan-first).

    Backed by the internal webhooks API ``POST /registry/v0``
    (createWebhook). The contract is VERIFIED end-to-end via the
     the published client contract (a live Foundry deployment): the exact body returned
    ``200 {"webhookRid": ..., "version": 1}``. Permission failures are
    resource-scoped -- the caller needs edit rights on the target source
    (or its parent project); a 403 means the target is not editable by
    this token, not that the endpoint is blocked.

    Without ``--apply`` the command prints the dry-run plan (the exact
    request body) and issues no network request. ``--apply`` sends the
    verified body; a permission failure surfaces as a loud error.
    """
    try:
        cache_rid(source_rid)
        service = ConnectivityService(profile=profile)
        resolved_api_name = api_name if api_name is not None else name

        spec_override: Optional[dict] = None
        if spec or spec_file:
            spec_override = _load_json_param(spec, spec_file, "spec")

        body = service.build_create_webhook_body(
            name, resolved_api_name, description, source_rid, spec_override
        )

        if not apply:
            plan = {
                "mode": "plan",
                "request": {
                    "verb": "POST",
                    "path": "/webhooks/api/registry/v0",
                    "body": body,
                },
                "contract": ConnectivityService.CREATE_WEBHOOK_CONTRACT,
            }
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "create_foundry_rest_api_data_source_webhook",
                        "mode": "plan",
                        "shape_verified": True,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        with SpinnerProgressTracker().track_spinner(f"Creating webhook {name}..."):
            result = service.create_webhook(
                name, resolved_api_name, description, source_rid, spec_override
            )

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_foundry_rest_api_data_source_webhook",
                    "mode": "applied",
                    "shape_verified": True,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except WebhookShapeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating webhook: {e}[/red]")
        raise typer.Exit(1)


@webhook_app.command("update")
def update_webhook(
    webhook_rid: str = typer.Argument(
        ..., help="Webhook Resource Identifier", autocompletion=complete_rid
    ),
    spec: Optional[str] = typer.Argument(
        None, help="Replacement webhook spec (wire shape) in JSON format"
    ),
    spec_file: Optional[str] = typer.Option(
        None, "--spec-file", help="Path to JSON file with the replacement spec"
    ),
    source_rid: Optional[str] = typer.Option(
        None,
        "--source-rid",
        help="Magritte source RID (spec assembly mode)",
        autocompletion=complete_rid,
    ),
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        help="Domain host string; resolved to a domainId via a read-only "
        "source config lookup (spec assembly mode)",
    ),
    calls: Optional[str] = typer.Option(
        None,
        "--calls",
        help="Calls as JSON (MCP tool-arg shape: httpMethod, httpPath, "
        "headers, httpQueryParams)",
    ),
    calls_file: Optional[str] = typer.Option(
        None, "--calls-file", help="Path to a JSON file with the calls"
    ),
    inputs: Optional[str] = typer.Option(
        None,
        "--inputs",
        help="Webhook inputs as JSON (MCP tool-arg shape: name, dataType, description)",
    ),
    inputs_file: Optional[str] = typer.Option(
        None, "--inputs-file", help="Path to a JSON file with the inputs"
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
    """Publish a new webhook version (plan-first).

    Backed by the internal webhooks API ``POST /registry/v0/{webhookRid}``
    (publishWebhookVersion) with body ``{"spec": <spec>}`` and nothing else.
    VERIFIED end-to-end via the  the published client contract (a live Foundry deployment).

    The spec can be supplied verbatim (``SPEC`` / ``--spec-file``) or
    assembled from MCP tool-arg shaped pieces (``--source-rid`` +
    ``--domain`` + ``--calls``/``--inputs``). Assembly mirrors the captured
    MCP transform: a fresh callId UUID per call, ``httpQueryParams`` values
    land in ``queryParamsV2`` with an extra array wrap, headers are not
    wrapped, and the ``--domain`` host is resolved to a domainId via a
    read-only source config GET.

    Without ``--apply`` the command prints the dry-run plan and issues no
    mutation (the assembly mode performs the read-only domain lookup).
    """
    try:
        cache_rid(webhook_rid)
        service = ConnectivityService(profile=profile)

        spec_given = bool(spec or spec_file)
        assembly_given = any(
            [source_rid, domain, calls, calls_file, inputs, inputs_file]
        )
        if spec_given and assembly_given:
            console.print(
                "[red]Cannot combine a verbatim spec (SPEC/--spec-file) with "
                "spec assembly options (--source-rid/--domain/--calls/--inputs)[/red]"
            )
            raise typer.Exit(1)

        if spec_given:
            spec_dict = _load_json_param(spec, spec_file, "spec")
        elif assembly_given:
            if not source_rid or not domain:
                console.print(
                    "[red]Spec assembly requires both --source-rid and --domain[/red]"
                )
                raise typer.Exit(1)
            cache_rid(source_rid)
            call_list: List[dict] = []
            if calls or calls_file:
                call_list = _load_json_list_param(calls, calls_file, "calls")
            input_list: List[dict] = []
            if inputs or inputs_file:
                input_list = _load_json_list_param(inputs, inputs_file, "inputs")
            with SpinnerProgressTracker().track_spinner(
                f"Resolving domain '{domain}' on source {source_rid}..."
            ):
                domain_id = service.resolve_source_domain_id(source_rid, domain)
            spec_dict = service.build_webhook_spec(
                source_rid, domain_id=domain_id, calls=call_list, inputs=input_list
            )
        else:
            console.print(
                "[red]Must specify either spec or --spec-file, or assemble a "
                "spec with --source-rid and --domain[/red]"
            )
            raise typer.Exit(1)

        if not apply:
            plan = service.plan_update_webhook(webhook_rid, spec_dict)
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "update_foundry_rest_api_data_source_webhook",
                        "webhook_rid": webhook_rid,
                        "mode": "plan",
                        "shape_verified": True,
                        "write_verified": True,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        with SpinnerProgressTracker().track_spinner(
            f"Publishing new version of webhook {webhook_rid}..."
        ):
            result = service.update_webhook(webhook_rid, spec_dict)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "update_foundry_rest_api_data_source_webhook",
                    "webhook_rid": webhook_rid,
                    "mode": "applied",
                    "shape_verified": True,
                    "write_verified": True,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except WebhookShapeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error updating webhook: {e}[/red]")
        raise typer.Exit(1)


@rest_source_app.command("create")
def create_rest_source(
    name: str = typer.Argument(..., help="Source display name"),
    host: str = typer.Option(
        ...,
        "--host",
        help="Hostname for the source domain (use a dummy value; never a "
        "real credential-bearing endpoint unless you intend a real source)",
    ),
    parent_rid: str = typer.Option(
        ...,
        "--parent-rid",
        help="Compass folder/project RID the source is created in (requires "
        "magritte:write-resource; your home folder works)",
        autocompletion=complete_rid,
    ),
    egress_policy_rid: List[str] = typer.Option(
        ...,
        "--egress-policy-rid",
        help="Network egress policy RID covering host:port (repeatable; at "
        "least one required)",
        autocompletion=complete_rid,
    ),
    description: str = typer.Option("", "--description", help="Source description"),
    scheme: str = typer.Option("HTTPS", "--scheme", help="URL scheme"),
    port: int = typer.Option(443, "--port", help="Port"),
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
    """Create a REST API data source (plan-first).

    Backed by magritte-coordinator ``POST /source-store/source/v3``
    (addSourceV3). The contract is VERIFIED end-to-end via the
    the published client contract (a live Foundry deployment): the envelope {config, description,
    runtimePlatformRequest, parentRid} returned 200 with a bare-string body
    (the new source RID). ``domains[].domainId`` is a client-generated
    random UUID per call.

    Credentials are NOT part of the create envelope -- they are configured
    post-create in the Data Connection UI. This CLI never calls the
    plaintext-secret config endpoint and never accepts real credentials.

    Without ``--apply`` the command prints the dry-run plan (the exact
    request body) and issues no network request. ``--apply`` sends the
    verified body; a permission failure (magritte:write-resource on
    --parent-rid) surfaces as a loud error.
    """
    try:
        cache_rid(parent_rid)
        service = ConnectivityService(profile=profile)

        if not apply:
            plan = service.plan_create_rest_source(
                name, host, scheme, port, parent_rid, egress_policy_rid, description
            )
            if agent_mode_enabled() or format == "agent":
                buffer_agent_payload(
                    plan,
                    meta={
                        "operation": "create_foundry_rest_api_data_source",
                        "mode": "plan",
                        "shape_verified": True,
                        "write_verified": True,
                    },
                )
            else:
                formatter.format_output([plan], format, output)
            return

        with SpinnerProgressTracker().track_spinner(
            f"Creating REST API data source {name}..."
        ):
            result = service.create_rest_source(
                name, host, scheme, port, parent_rid, egress_policy_rid, description
            )
        cache_rid(result.get("source_rid", ""))

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                result,
                meta={
                    "operation": "create_foundry_rest_api_data_source",
                    "mode": "applied",
                    "shape_verified": True,
                    "write_verified": True,
                },
            )
        else:
            formatter.format_output([result], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except RestSourceShapeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating REST API data source: {e}[/red]")
        raise typer.Exit(1)


@egress_app.command("ensure")
def ensure_egress_policy(
    hostname: str = typer.Argument(
        ..., help="Hostname the network egress policy must cover"
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
    """Ensure a network egress policy covers a hostname (read-only).

    Implements the read half of get-or-create semantics against the internal
    resource-policy-manager API: existing policies are read and matched
    against the hostname. If none matches, the command exits loudly with a
    "would create" message -- this CLI never creates egress policies.
    """
    try:
        with SpinnerProgressTracker().track_spinner(
            f"Checking network egress policies for {hostname}..."
        ):
            service = ConnectivityService(profile=profile)
            match = service.ensure_egress_policy(hostname)

        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                match,
                meta={
                    "operation": "get_or_create_network_egress_policy",
                    "hostname": hostname,
                },
            )
        else:
            formatter.format_output([match], format, output)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)
    except EgressPolicyNotFoundError as e:
        if agent_mode_enabled() or format == "agent":
            buffer_agent_payload(
                None,
                meta={
                    "operation": "get_or_create_network_egress_policy",
                    "hostname": hostname,
                    "result_type": "would_create",
                },
                errors=[{"type": "would_create", "message": str(e)}],
            )
        else:
            console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except (EgressPolicyShapeError,) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error ensuring network egress policy: {e}[/red]")
        raise typer.Exit(1)
