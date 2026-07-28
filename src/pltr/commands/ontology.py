"""
Ontology commands for interacting with Foundry ontologies.
"""

import click
import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console

from ..services.functions import FunctionsService
from ..services.dependency import CHANGE_TYPES
from ..services.guarded_upsert import GuardedMutationService, GuardedUpsertService
from ..services.ontology import (
    OntologyService,
    ObjectTypeService,
    OntologyObjectService,
    ActionService,
    QueryService,
)
from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_exception,
    buffer_agent_payload,
    require_confirmation,
)
from ..utils.error_hints import HintedUsageCommand, resolve_error_hint
from ..utils.formatting import OutputFormatter
from ..utils.pagination import PaginationConfig
from ..utils.progress import SpinnerProgressTracker
from ..auth.base import ProfileNotFoundError, MissingCredentialsError

app = typer.Typer(help="Ontology operations")
console = Console()
formatter = OutputFormatter(console)


# Ontology management commands
@app.command("list")
def list_ontologies(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List all available ontologies."""
    try:
        service = OntologyService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Fetching ontologies..."):
            ontologies = service.list_ontologies()

        formatter.format_table(
            ontologies,
            columns=["rid", "api_name", "display_name", "description"],
            format=format,
            output=output,
        )

        if output:
            formatter.print_success(f"Ontologies saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to list ontologies: {e}")
        raise typer.Exit(1)


@app.command("get")
def get_ontology(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get details of a specific ontology."""
    try:
        service = OntologyService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching ontology {ontology_rid}..."
        ):
            ontology = service.get_ontology(ontology_rid)

        formatter.format_dict(ontology, format=format, output=output)

        if output:
            formatter.print_success(f"Ontology information saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to get ontology: {e}")
        raise typer.Exit(1)


@app.command("rid")
def resolve_ontology_rid(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Resolve and print the ontology RID for this stack.

    Succeeds only when exactly one ontology is visible; zero or multiple
    visible ontologies make the RID ambiguous and fail instead of guessing.
    """
    try:
        service = OntologyService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Resolving ontology RID..."):
            ontology = service.get_ontology_rid()

        formatter.format_dict(ontology, format=format, output=output)

        if output:
            formatter.print_success(f"Ontology RID saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to resolve ontology RID: {e}")
        raise typer.Exit(1)


# Object Type commands
@app.command("object-type-list")
def list_object_types(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """List object types in an ontology."""
    try:
        service = ObjectTypeService(profile=profile)

        with SpinnerProgressTracker().track_spinner("Fetching object types..."):
            object_types = service.list_object_types(ontology_rid)

        formatter.format_table(
            object_types,
            columns=["api_name", "display_name", "description", "primary_key"],
            format=format,
            output=output,
        )

        if output:
            formatter.print_success(f"Object types saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to list object types: {e}")
        raise typer.Exit(1)


@app.command("object-type-get")
def get_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get details of a specific object type."""
    try:
        service = ObjectTypeService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching object type {object_type}..."
        ):
            obj_type = service.get_object_type(ontology_rid, object_type)

        formatter.format_dict(obj_type, format=format, output=output)

        if output:
            formatter.print_success(f"Object type information saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        if agent_mode_enabled():
            buffer_agent_exception(e, context="object-type-get")
        formatter.print_error(f"Failed to get object type: {e}")
        raise typer.Exit(1)


@app.command("link-type-get")
def get_link_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Source object type API name"),
    link_type: str = typer.Argument(..., help="Link type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Get details of a specific outgoing link type of an object type."""
    try:
        service = ObjectTypeService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching link type {link_type}..."
        ):
            link = service.get_link_type(ontology_rid, object_type, link_type)

        formatter.format_dict(link, format=format, output=output)

        if output:
            formatter.print_success(f"Link type information saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to get link type: {e}")
        raise typer.Exit(1)


@app.command("object-type-create")
def create_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    api_name: str = typer.Option(..., "--api-name", help="Object type API name"),
    display_name: str = typer.Option(
        ..., "--display-name", help="Object type display name"
    ),
    primary_key: str = typer.Option(
        ..., "--primary-key", help="Primary key property API name"
    ),
    backing_dataset: str = typer.Option(
        ..., "--backing-dataset", help="Backing dataset RID"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Object type description"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a new object type in an ontology."""
    try:
        service = ObjectTypeService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Creating object type {api_name}..."
        ):
            result = service.create_object_type(
                ontology_rid=ontology_rid,
                api_name=api_name,
                display_name=display_name,
                primary_key=primary_key,
                backing_dataset=backing_dataset,
                description=description,
            )

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Object type creation result saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to create object type: {e}")
        raise typer.Exit(1)


@app.command("object-type-upsert", cls=HintedUsageCommand)
def upsert_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    api_name: str = typer.Option(..., "--api-name", help="Object type API name"),
    display_name: str = typer.Option(
        ..., "--display-name", help="Object type display name"
    ),
    primary_key: str = typer.Option(
        ..., "--primary-key", help="Primary key property API name"
    ),
    backing_dataset: str = typer.Option(
        ..., "--backing-dataset", help="Backing dataset RID"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Object type description"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run only)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create an object type via modifyOntology (dry-run unless --apply).

    This command is step 3 of the required ontology contract publication
    order: 1) modify backing dataset schemas, 2) implement transaction
    functions, 3) object-type-upsert, 4) link-type-upsert,
    5) action-type-upsert, 6) validate actions and re-read test objects,
    7) regenerate OSDK, 8) enable the corresponding application controls.
    Complete steps 1-2 first; the backing dataset must carry a schema.

    When the object type already exists, the command switches to the
    update path: it loads the type's current state, merges the provided
    display name / description onto it, and issues an update modification.
    The result reports the changed fields. Primary key and backing dataset
    must match the existing type.
    """
    try:
        result = ObjectTypeService(profile=profile).upsert_object_type(
            ontology_rid=ontology_rid,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
            apply=apply,
        )
        formatter.format_dict(result, format=format, output=output)
        _exit_on_validation_error(result, context="object-type-upsert")
        _warn_on_unverified(result)
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        if agent_mode_enabled():
            buffer_agent_exception(e, context="object-type-upsert")
        formatter.print_error(f"Failed to upsert object type: {e}")
        raise typer.Exit(1) from e


def _exit_on_validation_error(result: dict, *, context: str = "") -> None:
    """Exit non-zero when a dry-run plan failed Foundry validation."""
    validation = result.get("validation") if isinstance(result, dict) else None
    if isinstance(validation, dict) and validation.get("status") == "error":
        errors = validation.get("errors")
        if isinstance(errors, list):
            for error in errors:
                formatter.print_error(f"Dry-run validation failed: {error}")
        else:
            formatter.print_error("Dry-run validation failed")
        if context and agent_mode_enabled():
            detail = (
                "; ".join(str(error) for error in errors)
                if isinstance(errors, list)
                else "see the printed plan"
            )
            entry: dict = {
                "type": "validation",
                "message": f"{context}: dry-run validation failed: {detail}",
            }
            hint = resolve_error_hint(context, entry=entry)
            if hint:
                entry["hint"] = hint
            buffer_agent_payload(None, errors=[entry])
        raise typer.Exit(1)


def _warn_on_unverified(result: dict) -> None:
    """Warn honestly when a real mutation could not be read back."""
    verification = result.get("verification") if isinstance(result, dict) else None
    # "skipped" is a deliberate no-op (nothing to apply), not a verification
    # failure; only "not-verified" warrants a warning.
    if isinstance(verification, dict) and verification.get("status") not in (
        "verified",
        "skipped",
    ):
        formatter.print_warning(
            f"Mutation applied but not verified: {verification.get('detail')}"
        )


@app.command("object-type-guarded-upsert")
def guarded_upsert_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    api_name: str = typer.Option(..., "--api-name", help="Object type API name"),
    display_name: str = typer.Option(
        ..., "--display-name", help="Object type display name"
    ),
    primary_key: str = typer.Option(
        ..., "--primary-key", help="Primary key property API name"
    ),
    backing_dataset: str = typer.Option(
        ..., "--backing-dataset", help="Backing dataset RID"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Object type description"
    ),
    change: Optional[str] = typer.Option(
        None, "--change", help="Free-text description of the intended change"
    ),
    change_type: Optional[str] = typer.Option(
        None,
        "--change-type",
        help="Classify the intended change for the impact gate",
        click_type=click.Choice(list(CHANGE_TYPES)),
    ),
    skip_impact_gate: bool = typer.Option(
        False,
        "--skip-impact-gate",
        help="Explicitly opt out of the dependency preflight (recorded in the result)",
    ),
    graph_output: Optional[str] = typer.Option(
        None,
        "--graph-output",
        help="Dependency graph artifact path (default: pltr state directory)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Accept unresolved must_verify_before_merge items (with --apply)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Guarded object type upsert: preflight, impact gate, plan, apply, read-back.

    One composite invocation for the sequence agents otherwise hand-assemble:
    1) load the current object type state (not-found means net-new), 2) run
    the read-only dependency impact gate for --change/--change-type, 3) build
    the modifyOntology dry-run plan, and — with --apply — 4) issue the real
    modification and read the type back authoritatively.

    Without --apply nothing mutates; the composite plan (preflight state,
    impact agent block, validated upsert plan, caveats) is printed. When the
    gate reports needs-verification with unresolved must_verify_before_merge
    items, --apply additionally requires --yes as explicit operator
    acceptance. --skip-impact-gate opts out of step 2 and is recorded.
    """
    try:
        service = GuardedUpsertService(profile=profile)
        result = service.prepare_object_type_upsert(
            ontology_rid=ontology_rid,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
            change=change,
            change_type=change_type,
            skip_impact_gate=skip_impact_gate,
            graph_output=graph_output,
        )
        plan = result.get("plan") or {}
        if not apply:
            formatter.format_dict(result, format=format, output=output)
            _exit_on_validation_error(plan)
            formatter.print_info(
                f"Dry-run only; pass --apply to upsert object type {api_name}."
            )
            return
        # Never apply a plan Foundry validation already rejected.
        _exit_on_validation_error(plan)
        impact = result.get("impact") or {}
        verification = impact.get("verification") or {}
        must_verify = verification.get("must_verify_before_merge") or []
        accepted = False
        if impact.get("status") == "needs-verification" and must_verify:
            if not require_confirmation(
                f"Impact gate for {api_name} reports {len(must_verify)} "
                "unresolved must_verify_before_merge item(s). Apply the "
                "upsert anyway?",
                confirmed=yes,
                option_name="--yes",
            ):
                formatter.print_info("Guarded upsert cancelled")
                raise typer.Exit(0)
            accepted = True
        result = service.apply_object_type_upsert(
            result, verification_accepted=accepted
        )
        formatter.format_dict(result, format=format, output=output)
        _warn_on_unverified(result.get("upsert") or {})
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        buffer_agent_exception(e, context="object-type-guarded-upsert")
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        buffer_agent_exception(e, context="object-type-guarded-upsert")
        formatter.print_error(f"Failed guarded upsert of object type: {e}")
        raise typer.Exit(1) from e


@app.command("object-type-add-property")
def add_property_to_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Option(
        ..., "--object-type", help="Object type API name or RID"
    ),
    api_name: str = typer.Option(
        ..., "--api-name", help="New property API name (camelCase)"
    ),
    property_type: str = typer.Option(
        ...,
        "--type",
        help="Property base type",
        click_type=click.Choice(
            [
                "STRING",
                "INTEGER",
                "LONG",
                "DOUBLE",
                "BOOLEAN",
                "TIMESTAMP",
                "DATE",
            ]
        ),
    ),
    display_name: Optional[str] = typer.Option(
        None, "--display-name", help="Property display name (default: API name)"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Property description"
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Property status",
        click_type=click.Choice(["ACTIVE", "EXPERIMENTAL", "EXAMPLE"]),
    ),
    visibility: Optional[str] = typer.Option(
        None,
        "--visibility",
        help="Property visibility (default: NORMAL)",
        click_type=click.Choice(["NORMAL", "HIDDEN", "PROMINENT"]),
    ),
    backing_column: Optional[str] = typer.Option(
        None,
        "--backing-column",
        help="Backing dataset column to map the property to",
    ),
    backing_dataset: Optional[str] = typer.Option(
        None,
        "--backing-dataset",
        help="Backing dataset RID (required when the object type has "
        "multiple dataset-backed datasources)",
    ),
    branch_rid: Optional[str] = typer.Option(
        None,
        "--branch-rid",
        help="Ontology branch RID to target (omit for the default branch)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run only)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Add a property to an existing object type via modifyOntology (dry-run unless --apply).

    Resolves the object type (API name or RID) to its internal ObjectTypeId,
    adds the property type, and — with --backing-column — maps it to a
    backing dataset column in the same request. Object types using
    interfaces or shared property types are refused. With --apply, the
    created property RID and column mapping are read back for verification.
    """
    try:
        result = ObjectTypeService(profile=profile).add_property_to_object_type(
            ontology_rid=ontology_rid,
            object_type=object_type,
            api_name=api_name,
            property_type=property_type,
            display_name=display_name,
            description=description,
            status=status,
            visibility=visibility,
            backing_column=backing_column,
            backing_dataset=backing_dataset,
            branch_rid=branch_rid,
            apply=apply,
        )
        formatter.format_dict(result, format=format, output=output)
        _exit_on_validation_error(result)
        _warn_on_unverified(result)
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        buffer_agent_exception(e, context="object-type-add-property")
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        buffer_agent_exception(e, context="object-type-add-property")
        formatter.print_error(f"Failed to add property to object type: {e}")
        raise typer.Exit(1) from e


def _delete_preview(
    *,
    service_delete: Any,
    plan_kwargs: dict,
    format: str,
    output: Optional[str],
) -> None:
    """Run and display the read-only dry-run preview for a delete."""
    plan = service_delete(**plan_kwargs, apply=False)
    formatter.format_dict(plan, format=format, output=output)
    _exit_on_validation_error(plan)


def _delete_apply(
    *,
    service_delete: Any,
    plan_kwargs: dict,
    format: str,
) -> None:
    """Run and display the real deletion after confirmation."""
    result = service_delete(**plan_kwargs, apply=True)
    formatter.format_dict(result, format=format)
    _warn_on_unverified(result)


@app.command("object-type-delete")
def delete_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type_id: str = typer.Argument(
        ...,
        help="Internal ObjectTypeId (e.g. 'ns1exmpl.my-type'), not the API name",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real deletion (default: dry-run preview only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt (with --apply)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Delete an object type via modifyOntology (dry-run unless --apply --yes).

    Deletes run in reverse publication order: delete dependent action types
    (step 5) and link types (step 4) before the object type (step 3). The
    dry-run preview reports remaining dependents.
    """
    try:
        service = ObjectTypeService(profile=profile)
        plan_kwargs = {
            "ontology_rid": ontology_rid,
            "object_type_id": object_type_id,
        }
        _delete_preview(
            service_delete=service.delete_object_type,
            plan_kwargs=plan_kwargs,
            format=format,
            output=output,
        )
        if not apply:
            formatter.print_info(
                f"Dry-run only; pass --apply to delete object type {object_type_id}."
            )
            return
        if not require_confirmation(
            f"Delete object type {object_type_id} from ontology "
            f"{ontology_rid}? This action cannot be undone.",
            confirmed=yes,
            option_name="--yes",
        ):
            formatter.print_info("Deletion cancelled")
            raise typer.Exit(0)
        _delete_apply(
            service_delete=service.delete_object_type,
            plan_kwargs=plan_kwargs,
            format=format,
        )
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        formatter.print_error(f"Failed to delete object type: {e}")
        raise typer.Exit(1) from e


@app.command("object-type-guarded-delete")
def guarded_delete_object_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type_id: str = typer.Argument(
        ...,
        help="Internal ObjectTypeId (e.g. 'ns1exmpl.my-type'), not the API name",
    ),
    change: Optional[str] = typer.Option(
        None,
        "--change",
        help="Free-text description of intent (default: 'delete object type')",
    ),
    change_type: Optional[str] = typer.Option(
        None,
        "--change-type",
        help="Classify the intended change for the impact gate "
        "(default: remove-delete)",
        click_type=click.Choice(list(CHANGE_TYPES)),
    ),
    skip_impact_gate: bool = typer.Option(
        False,
        "--skip-impact-gate",
        help="Explicitly opt out of the dependency preflight (recorded in the result)",
    ),
    graph_output: Optional[str] = typer.Option(
        None,
        "--graph-output",
        help="Dependency graph artifact path (default: pltr state directory)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real deletion (default: dry-run plan only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt (with --apply)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Guarded object type delete: preflight, impact gate, plan, apply, verify.

    One composite invocation for the sequence agents otherwise hand-assemble:
    1) resolve the internal ObjectTypeId to current state (a missing type
    fails with a typed not-found — no delete is planned), 2) run the
    read-only dependency impact gate for --change/--change-type, 3) build
    the modifyOntology delete dry-run plan, and — with --apply --yes —
    4) issue the real deletion and verify removal by a read-back that must
    now report the type as not found.

    Without --apply nothing mutates; the composite plan (preflight state,
    impact agent block, validated delete plan, caveats) is printed. Deletion
    always requires the double confirmation --apply AND --yes; when the gate
    also reports needs-verification, that acceptance is recorded in the
    result. Deletes run in reverse publication order (action types, then
    link types, then object types). --skip-impact-gate opts out of step 2
    and is recorded.
    """
    try:
        service = GuardedMutationService(profile=profile)
        result = service.prepare_object_type_delete(
            ontology_rid=ontology_rid,
            object_type_id=object_type_id,
            change=change,
            change_type=change_type,
            skip_impact_gate=skip_impact_gate,
            graph_output=graph_output,
        )
        plan = result.get("plan") or {}
        if not apply:
            formatter.format_dict(result, format=format, output=output)
            _exit_on_validation_error(plan)
            formatter.print_info(
                f"Dry-run only; pass --apply to delete object type {object_type_id}."
            )
            return
        # Never apply a plan Foundry validation already rejected.
        _exit_on_validation_error(plan)
        impact = result.get("impact") or {}
        verification = impact.get("verification") or {}
        must_verify = verification.get("must_verify_before_merge") or []
        accepted = bool(impact.get("status") == "needs-verification" and must_verify)
        message = (
            f"Delete object type {object_type_id} from ontology "
            f"{ontology_rid}? This action cannot be undone."
        )
        if accepted:
            message += (
                f" The impact gate also reports {len(must_verify)} unresolved "
                "must_verify_before_merge item(s); confirming accepts them."
            )
        if not require_confirmation(message, confirmed=yes, option_name="--yes"):
            formatter.print_info("Deletion cancelled")
            raise typer.Exit(0)
        result = service.apply_object_type_delete(
            result, verification_accepted=accepted
        )
        formatter.format_dict(result, format=format, output=output)
        _warn_on_unverified(result.get("delete") or {})
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        buffer_agent_exception(e, context="object-type-guarded-delete")
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        buffer_agent_exception(e, context="object-type-guarded-delete")
        formatter.print_error(f"Failed guarded delete of object type: {e}")
        raise typer.Exit(1) from e


@app.command("link-type-upsert")
def upsert_link_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    api_name: str = typer.Option(
        ..., "--api-name", help="Link type API name (camelCase, one-to-many side)"
    ),
    from_object_type_id: str = typer.Option(
        ...,
        "--from-object-type-id",
        help="Internal ObjectTypeId of the one side (e.g. 'ns1exmpl.my-type')",
    ),
    to_object_type_id: str = typer.Option(
        ...,
        "--to-object-type-id",
        help="Internal ObjectTypeId of the many side (e.g. 'ns1exmpl.my-type')",
    ),
    display_name: Optional[str] = typer.Option(
        None, "--display-name", help="Link type display name"
    ),
    reverse_api_name: Optional[str] = typer.Option(
        None, "--reverse-api-name", help="Many-to-one direction API name"
    ),
    one_side_primary_key: str = typer.Option(
        "id", "--one-side-primary-key", help="Primary key property on the one side"
    ),
    many_side_property: Optional[str] = typer.Option(
        None,
        "--many-side-property",
        help="Foreign key property on the many side (default: same as one side)",
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Link type description"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run only)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a one-to-many link type via modifyOntology (dry-run unless --apply).

    This command is step 4 of the required ontology contract publication
    order (see object-type-upsert --help for the full sequence). Both object
    types must already exist — run object-type-upsert (step 3) first.

    Existing link types are not updated yet; the create validation reports
    that case explicitly.
    """
    try:
        result = ObjectTypeService(profile=profile).upsert_link_type(
            ontology_rid=ontology_rid,
            api_name=api_name,
            one_side_object_type_id=from_object_type_id,
            many_side_object_type_id=to_object_type_id,
            display_name=display_name,
            reverse_api_name=reverse_api_name,
            one_side_primary_key=one_side_primary_key,
            many_side_property=many_side_property,
            description=description,
            apply=apply,
        )
        formatter.format_dict(result, format=format, output=output)
        _exit_on_validation_error(result)
        _warn_on_unverified(result)
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        formatter.print_error(f"Failed to upsert link type: {e}")
        raise typer.Exit(1) from e


@app.command("link-type-delete")
def delete_link_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    link_type_id: str = typer.Argument(
        ...,
        help="Internal LinkTypeId (e.g. 'ns1exmpl.my-link'), not the API name",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real deletion (default: dry-run preview only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt (with --apply)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Delete a link type via modifyOntology (dry-run unless --apply --yes).

    Deletes run in reverse publication order: link types (step 4) are
    deleted after their dependent action types (step 5) and before their
    object types (step 3).
    """
    try:
        service = ObjectTypeService(profile=profile)
        plan_kwargs = {
            "ontology_rid": ontology_rid,
            "link_type_id": link_type_id,
        }
        _delete_preview(
            service_delete=service.delete_link_type,
            plan_kwargs=plan_kwargs,
            format=format,
            output=output,
        )
        if not apply:
            formatter.print_info(
                f"Dry-run only; pass --apply to delete link type {link_type_id}."
            )
            return
        if not require_confirmation(
            f"Delete link type {link_type_id} from ontology "
            f"{ontology_rid}? This action cannot be undone.",
            confirmed=yes,
            option_name="--yes",
        ):
            formatter.print_info("Deletion cancelled")
            raise typer.Exit(0)
        _delete_apply(
            service_delete=service.delete_link_type,
            plan_kwargs=plan_kwargs,
            format=format,
        )
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        formatter.print_error(f"Failed to delete link type: {e}")
        raise typer.Exit(1) from e


@app.command("action-type-upsert", cls=HintedUsageCommand)
def upsert_action_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Path to a JSON file with the ActionTypeCreate definition "
        "('-' reads stdin)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run only)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create an action type via modifyOntology (dry-run unless --apply).

    This command is step 5 of the required ontology contract publication
    order (see object-type-upsert --help for the full sequence). Referenced
    object types (step 3) and link types (step 4) must already exist. After
    applying, continue with step 6 (validate actions and re-read test
    objects), step 7 (regenerate OSDK), and step 8 (enable the
    corresponding application controls).

    The definition is an ActionTypeCreate JSON document. Existing action types
    are not updated yet; the create validation reports that case explicitly.
    """
    try:
        if definition == "-":
            raw_definition = sys.stdin.read()
        else:
            raw_definition = Path(definition).read_text()
        try:
            parsed_definition = json.loads(raw_definition)
        except json.JSONDecodeError as e:
            if agent_mode_enabled():
                buffer_agent_exception(e, context="action-type-upsert")
            formatter.print_error(f"Invalid JSON in action type definition: {e}")
            raise typer.Exit(1) from e

        result = ActionService(profile=profile).upsert_action_type(
            ontology_rid=ontology_rid,
            definition=parsed_definition,
            apply=apply,
        )
        formatter.format_dict(result, format=format, output=output)
        _exit_on_validation_error(result, context="action-type-upsert")
        _warn_on_unverified(result)
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        if agent_mode_enabled():
            buffer_agent_exception(e, context="action-type-upsert")
        formatter.print_error(f"Failed to upsert action type: {e}")
        raise typer.Exit(1) from e


@app.command("action-type-update")
def update_action_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    action_type: str = typer.Option(
        ..., "--action-type", help="Action type API name or RID"
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Path to a JSON file with the partial patch document ('-' reads stdin)",
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        "-b",
        help="Foundry branch to read the definition back from",
    ),
    branch_rid: Optional[str] = typer.Option(
        None,
        "--branch-rid",
        help="Ontology branch RID to target the modification at "
        "(omit for the default branch)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real modification (default: dry-run only)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Update an existing action type via modifyOntology (dry-run unless --apply).

    The definition is a partial patch document; supported keys are
    displayMetadata, logic, parameters, validations, writeAuthorization,
    and status. The patch is merged onto the action type's loaded
    definition and sent as actionTypesToUpdate (see
    artifacts/ontology-modify-contract.md section 4). Creates stay with
    action-type-upsert.

    Logic patches replace the loaded rules wholesale; a functionRule must
    carry functionRid and functionVersion as given by the function
    registry. Rule inputs can bind the current user with
    {"type": "currentUser", "currentUser": {}}. Parameter patches take
    add/remove/ordering; validation patches take add/remove/update/
    ordering.
    """
    try:
        if definition == "-":
            raw_definition = sys.stdin.read()
        else:
            raw_definition = Path(definition).read_text()
        try:
            parsed_definition = json.loads(raw_definition)
        except json.JSONDecodeError as e:
            formatter.print_error(f"Invalid JSON in action type patch: {e}")
            raise typer.Exit(1) from e

        result = ActionService(profile=profile).update_action_type(
            ontology_rid=ontology_rid,
            action_type=action_type,
            patch=parsed_definition,
            branch=branch,
            branch_rid=branch_rid,
            apply=apply,
        )
        formatter.format_dict(result, format=format, output=output)
        _exit_on_validation_error(result)
        _warn_on_unverified(result)
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        buffer_agent_exception(e, context="action-type-update")
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        buffer_agent_exception(e, context="action-type-update")
        formatter.print_error(f"Failed to update action type: {e}")
        raise typer.Exit(1) from e


@app.command("action-type-delete")
def delete_action_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    action_type: str = typer.Argument(..., help="Action type API name"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Issue the real deletion (default: dry-run preview only)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt (with --apply)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Delete an action type via modifyOntology (dry-run unless --apply --yes).

    Deletes run in reverse publication order: action types (step 5) are
    deleted first, before link types (step 4) and object types (step 3).
    """
    try:
        service = ActionService(profile=profile)
        plan_kwargs = {
            "ontology_rid": ontology_rid,
            "action_type": action_type,
        }
        _delete_preview(
            service_delete=service.delete_action_type,
            plan_kwargs=plan_kwargs,
            format=format,
            output=output,
        )
        if not apply:
            formatter.print_info(
                f"Dry-run only; pass --apply to delete action type {action_type}."
            )
            return
        if not require_confirmation(
            f"Delete action type {action_type} from ontology "
            f"{ontology_rid}? This action cannot be undone.",
            confirmed=yes,
            option_name="--yes",
        ):
            formatter.print_info("Deletion cancelled")
            raise typer.Exit(0)
        _delete_apply(
            service_delete=service.delete_action_type,
            plan_kwargs=plan_kwargs,
            format=format,
        )
    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        formatter.print_error(f"Failed to delete action type: {e}")
        raise typer.Exit(1) from e


@app.command("link-type-create")
def create_link_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    api_name: str = typer.Option(..., "--api-name", help="Link type API name"),
    from_object: str = typer.Option(..., "--from", help="Source object type API name"),
    to_object: str = typer.Option(..., "--to", help="Target object type API name"),
    display_name: Optional[str] = typer.Option(
        None, "--display-name", help="Link type display name"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Link type description"
    ),
    reverse_api_name: Optional[str] = typer.Option(
        None, "--reverse-api-name", help="Reverse direction link type API name"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Create a new link type in an ontology."""
    try:
        service = ObjectTypeService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Creating link type {api_name}..."
        ):
            result = service.create_link_type(
                ontology_rid=ontology_rid,
                api_name=api_name,
                from_object_type=from_object,
                to_object_type=to_object,
                display_name=display_name,
                description=description,
                reverse_api_name=reverse_api_name,
            )

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Link type creation result saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to create link type: {e}")
        raise typer.Exit(1)


# Object operations
@app.command("object-list")
def list_objects(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    page_size: Optional[int] = typer.Option(
        None, "--page-size", help="Number of objects per page (default: from settings)"
    ),
    max_pages: Optional[int] = typer.Option(
        1, "--max-pages", help="Maximum number of pages to fetch (default: 1)"
    ),
    page_token: Optional[str] = typer.Option(
        None, "--page-token", help="Page token to resume from previous response"
    ),
    all: bool = typer.Option(
        False, "--all", help="Fetch all available pages (overrides --max-pages)"
    ),
    properties: Optional[str] = typer.Option(
        None, "--properties", help="Comma-separated list of properties to include"
    ),
):
    """
    List objects of a specific type with pagination support.

    By default, fetches only the first page of results. Use --all to fetch all objects,
    or --max-pages to control how many pages to fetch.

    Examples:
        # List first page of objects (default)
        pltr ontology object-list ONTOLOGY_RID ObjectType

        # List all objects
        pltr ontology object-list ONTOLOGY_RID ObjectType --all

        # List first 3 pages
        pltr ontology object-list ONTOLOGY_RID ObjectType --max-pages 3

        # Resume from a specific page
        pltr ontology object-list ONTOLOGY_RID ObjectType --page-token abc123
    """
    try:
        service = OntologyObjectService(profile=profile)

        prop_list = properties.split(",") if properties else None

        # Create pagination config
        config = PaginationConfig(
            page_size=page_size,
            max_pages=max_pages,
            page_token=page_token,
            fetch_all=all,
        )

        with SpinnerProgressTracker().track_spinner(
            f"Fetching {object_type} objects..."
        ):
            result = service.list_objects_paginated(
                ontology_rid, object_type, config, properties=prop_list
            )

        # Format and display paginated results
        if output:
            formatter.format_paginated_output(result, format, output)
            formatter.print_success(f"Objects saved to {output}")
        else:
            formatter.format_paginated_output(result, format)

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to list objects: {e}")
        raise typer.Exit(1)


@app.command("object-get")
def get_object(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    primary_key: str = typer.Argument(..., help="Object primary key"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    properties: Optional[str] = typer.Option(
        None, "--properties", help="Comma-separated list of properties to include"
    ),
):
    """Get a specific object by primary key."""
    try:
        service = OntologyObjectService(profile=profile)

        prop_list = properties.split(",") if properties else None

        with SpinnerProgressTracker().track_spinner(
            f"Fetching object {primary_key}..."
        ):
            obj = service.get_object(
                ontology_rid, object_type, primary_key, properties=prop_list
            )

        formatter.format_dict(obj, format=format, output=output)

        if output:
            formatter.print_success(f"Object information saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to get object: {e}")
        raise typer.Exit(1)


@app.command("object-aggregate")
def aggregate_objects(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    aggregations: str = typer.Argument(..., help="JSON string of aggregation specs"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    group_by: Optional[str] = typer.Option(
        None, "--group-by", help="Comma-separated list of fields to group by"
    ),
    filter: Optional[str] = typer.Option(
        None, "--filter", help="JSON string of filter criteria"
    ),
):
    """Aggregate objects with specified functions."""
    try:
        service = OntologyObjectService(profile=profile)

        # Parse JSON inputs
        agg_list = json.loads(aggregations)
        group_list = group_by.split(",") if group_by else None
        filter_dict = json.loads(filter) if filter else None

        with SpinnerProgressTracker().track_spinner("Aggregating objects..."):
            result = service.aggregate_objects(
                ontology_rid,
                object_type,
                agg_list,
                group_by=group_list,
                filter=filter_dict,
            )

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Aggregation results saved to {output}")

    except json.JSONDecodeError as e:
        formatter.print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to aggregate objects: {e}")
        raise typer.Exit(1)


@app.command("object-linked")
def list_linked_objects(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    primary_key: str = typer.Argument(..., help="Object primary key"),
    link_type: str = typer.Argument(..., help="Link type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    page_size: Optional[int] = typer.Option(
        None, "--page-size", help="Number of results per page"
    ),
    properties: Optional[str] = typer.Option(
        None, "--properties", help="Comma-separated list of properties to include"
    ),
):
    """List objects linked to a specific object."""
    try:
        service = OntologyObjectService(profile=profile)

        prop_list = properties.split(",") if properties else None

        with SpinnerProgressTracker().track_spinner("Fetching linked objects..."):
            objects = service.list_linked_objects(
                ontology_rid,
                object_type,
                primary_key,
                link_type,
                page_size=page_size,
                properties=prop_list,
            )

        if format == "table" and objects:
            # Use first object's keys as columns
            columns = list(objects[0].keys()) if objects else []
            formatter.format_table(
                objects, columns=columns, format=format, output=output
            )
        else:
            formatter.format_list(objects, format=format, output=output)

        if output:
            formatter.print_success(f"Linked objects saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to list linked objects: {e}")
        raise typer.Exit(1)


@app.command("object-count")
def count_objects(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch name"),
):
    """Count objects of a specific type."""
    try:
        service = OntologyObjectService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Counting {object_type} objects..."
        ):
            result = service.count_objects(ontology_rid, object_type, branch=branch)

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Count result saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to count objects: {e}")
        raise typer.Exit(1)


@app.command("object-search")
def search_objects(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    object_type: str = typer.Argument(..., help="Object type API name"),
    query: str = typer.Option(..., "--query", "-q", help="Search query string"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    page_size: Optional[int] = typer.Option(
        None, "--page-size", help="Number of results per page"
    ),
    properties: Optional[str] = typer.Option(
        None, "--properties", help="Comma-separated list of properties to include"
    ),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch name"),
):
    """Search objects by query."""
    try:
        service = OntologyObjectService(profile=profile)

        prop_list = properties.split(",") if properties else None

        with SpinnerProgressTracker().track_spinner(
            f"Searching {object_type} objects..."
        ):
            objects = service.search_objects(
                ontology_rid,
                object_type,
                query,
                page_size=page_size,
                properties=prop_list,
                branch=branch,
            )

        if format == "table" and objects:
            # Use first object's keys as columns
            columns = list(objects[0].keys()) if objects else []
            formatter.format_table(
                objects, columns=columns, format=format, output=output
            )
        else:
            formatter.format_list(objects, format=format, output=output)

        if output:
            formatter.print_success(f"Search results saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to search objects: {e}")
        raise typer.Exit(1)


# Action commands
@app.command("action-type-get")
def get_action_type(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    action_type: str = typer.Argument(..., help="Action type API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", "-b", help="Foundry branch to load the definition from"
    ),
):
    """Get full metadata of a specific action type (read-only)."""
    try:
        service = ActionService(profile=profile)

        with SpinnerProgressTracker().track_spinner(
            f"Fetching action type {action_type}..."
        ):
            action = service.get_action_type(ontology_rid, action_type, branch=branch)

        formatter.format_dict(action, format=format, output=output)

        if output:
            formatter.print_success(f"Action type information saved to {output}")

    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        if agent_mode_enabled():
            buffer_agent_exception(e, context="action-type-get")
        formatter.print_error(f"Failed to get action type: {e}")
        raise typer.Exit(1)


@app.command("action-apply")
def apply_action(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    action_type: str = typer.Argument(..., help="Action type API name"),
    parameters: str = typer.Argument(..., help="JSON string of action parameters"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Apply an action with given parameters."""
    try:
        service = ActionService(profile=profile)

        # Parse JSON parameters
        params = json.loads(parameters)

        with SpinnerProgressTracker().track_spinner(
            f"Applying action {action_type}..."
        ):
            result = service.apply_action(ontology_rid, action_type, params)

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Action result saved to {output}")

    except json.JSONDecodeError as e:
        formatter.print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to apply action: {e}")
        raise typer.Exit(1)


@app.command("action-validate")
def validate_action(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    action_type: str = typer.Argument(..., help="Action type API name"),
    parameters: str = typer.Argument(..., help="JSON string of action parameters"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Validate action parameters without executing."""
    try:
        service = ActionService(profile=profile)

        # Parse JSON parameters
        params = json.loads(parameters)

        with SpinnerProgressTracker().track_spinner(
            f"Validating action {action_type}..."
        ):
            result = service.validate_action(ontology_rid, action_type, params)

        formatter.format_dict(result, format=format, output=output)

        if result.get("result") == "VALID":
            formatter.print_success("Action parameters are valid")
        else:
            formatter.print_error("Action parameters are invalid")

        if output:
            formatter.print_success(f"Validation result saved to {output}")

    except json.JSONDecodeError as e:
        formatter.print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to validate action: {e}")
        raise typer.Exit(1)


# Query commands
@app.command("query-execute")
def execute_query(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    query_name: str = typer.Argument(..., help="Query API name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    parameters: Optional[str] = typer.Option(
        None, "--parameters", help="JSON string of query parameters"
    ),
):
    """Execute a predefined query."""
    try:
        service = QueryService(profile=profile)

        # Parse JSON parameters if provided
        params = json.loads(parameters) if parameters else None

        with SpinnerProgressTracker().track_spinner(f"Executing query {query_name}..."):
            result = service.execute_query(ontology_rid, query_name, parameters=params)

        # Handle different result formats
        if "rows" in result:
            formatter.format_list(result["rows"], format=format, output=output)
        elif "objects" in result:
            formatter.format_list(result["objects"], format=format, output=output)
        else:
            formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Query results saved to {output}")

    except json.JSONDecodeError as e:
        formatter.print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        formatter.print_error(f"Failed to execute query: {e}")
        raise typer.Exit(1)


@app.command("resolve")
def resolve_entity(
    ontology_rid: str = typer.Argument(..., help="Ontology Resource Identifier"),
    kind: str = typer.Option(
        ...,
        "--kind",
        help="Entity kind to resolve",
        click_type=click.Choice(["object-type", "property", "action-type", "function"]),
    ),
    api_name: Optional[str] = typer.Option(
        None, "--api-name", help="Entity API name (exactly one of --api-name/--rid)"
    ),
    rid: Optional[str] = typer.Option(
        None, "--rid", help="Entity RID (exactly one of --api-name/--rid)"
    ),
    object_type: Optional[str] = typer.Option(
        None,
        "--object-type",
        help="Object type API name or RID (required for --kind property)",
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        help="Function version (recorded but not resolved; the search "
        "gateway exposes no per-version RIDs)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json, csv, agent)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Resolve a typed identifier to its RID and internal ID (read-only).

    object-type and action-type return the RID plus display name and
    status; object-type also returns the internal ObjectTypeId (for
    example 'ns0abcde.cohort'). property requires --object-type plus
    --api-name and returns the property RID and internal PropertyTypeId.
    function resolves an API name through the fail-safe search gateway;
    unresolved lookups report status "inconclusive" rather than empty.
    """
    try:
        if (api_name is None) == (rid is None):
            formatter.print_error("resolve requires exactly one of --api-name or --rid")
            raise typer.Exit(1)

        if kind == "object-type":
            result = ObjectTypeService(profile=profile).resolve_object_type(
                ontology_rid, api_name=api_name, rid=rid
            )
        elif kind == "property":
            if api_name is None or object_type is None:
                formatter.print_error(
                    "--kind property requires --api-name and --object-type"
                )
                raise typer.Exit(1)
            result = ObjectTypeService(profile=profile).resolve_property(
                ontology_rid, object_type=object_type, api_name=api_name
            )
        elif kind == "action-type":
            result = ActionService(profile=profile).resolve_action_type(
                ontology_rid, api_name=api_name, rid=rid
            )
        else:
            result = FunctionsService(profile=profile).resolve_function(
                api_name=api_name, rid=rid, version=version
            )

        formatter.format_dict(result, format=format, output=output)

        if output:
            formatter.print_success(f"Resolution saved to {output}")

    except (typer.Exit, typer.Abort):
        raise
    except (ProfileNotFoundError, MissingCredentialsError) as e:
        buffer_agent_exception(e, context="resolve")
        formatter.print_error(f"Authentication error: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        buffer_agent_exception(e, context="resolve")
        formatter.print_error(f"Failed to resolve {kind}: {e}")
        raise typer.Exit(1) from e
