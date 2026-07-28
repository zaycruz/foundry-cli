"""
Ontology service wrappers for Foundry SDK.
"""

import re
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union
from urllib.parse import quote

import requests
from foundry_sdk.v2.ontologies.models import ApplyActionRequestOptions

from ..config.settings import Settings
from ..utils.pagination import PaginationConfig, PaginationResult
from .base import BaseService
from .errors import (
    FoundryApiError,
    foundry_error_from_conjure,
    foundry_error_from_sdk,
)

# Verified request contract for OntologyModificationService.modifyOntology:
# the captured contract (contract-verified against a live deployment).
_MODIFY_ENDPOINT = "/ontology-metadata/api/ontology/v2/modify"
# Verified against a live deployment: OntologyMetadataService.bulkLoadOntologyEntities
# loads the current state of entities keyed by ObjectTypeId/LinkTypeId. The
# response carries the full _api ObjectType used to build update modifications.
_BULK_LOAD_ENTITIES_ENDPOINT = (
    "/ontology-metadata/api/ontology/ontology/bulkLoadEntities"
)
_NAMESPACE_PROBE_OBJECT_TYPE_ID = "probe.bad-id"

# Terminal error names that prove an entity is gone when a delete is
# re-issued as a dry-run (read-back verification for deletions).
_GONE_ERROR_NAMES = {
    "ObjectTypesNotFound",
    "LinkTypesNotFound",
    "ActionTypesNotFound",
}

_ALREADY_EXISTS_ERROR_NAMES = {
    "ObjectTypesAlreadyExistError",
    "ObjectTypesAlreadyExist",
    "objectTypesAlreadyExist",
    "LinkTypesAlreadyExistError",
    "LinkTypesAlreadyExist",
    "linkTypesAlreadyExist",
    "ActionTypesAlreadyExistError",
    "ActionTypesAlreadyExist",
    "actionTypesAlreadyExist",
}

_OBJECT_TYPE_ALREADY_EXISTS_NAMES = {
    "ObjectTypesAlreadyExistError",
    "ObjectTypesAlreadyExist",
    "objectTypesAlreadyExist",
}

_COMMON_ERROR_MESSAGES = {
    "InvalidObjectTypeId": (
        "Foundry rejected the generated object type ID for this ontology namespace"
    ),
    "CannotCreateV1ObjectType": (
        "Foundry requires objectStorageV2 metadata for new object types"
    ),
    "ObjectTypeWithZeroDatasourcesNotAllowed": (
        "Foundry requires at least one datasource for a new object type"
    ),
    "SchemaForObjectTypeDatasourceNotFound": (
        "the backing dataset has no schema; apply a schema to the "
        "dataset before creating the object type"
    ),
    "TooManyObjectTypesInOntology": ("the ontology has reached its object type limit"),
}


def _modify_urls(ontology_rid: str) -> Tuple[str, str]:
    """Return the (dry-run, real) modifyOntology URLs for an ontology."""
    encoded = quote(ontology_rid, safe="")
    return (
        f"{_MODIFY_ENDPOINT}/dry-run?ontologyRid={encoded}",
        f"{_MODIFY_ENDPOINT}?ontologyRid={encoded}",
    )


def _internal_client(service: BaseService) -> Any:
    """Build a FoundryInternalClient for the service's effective profile."""
    from .foundry_internal_client import FoundryInternalClient

    effective_profile = service.profile or service.auth_manager.get_current_profile()
    if not effective_profile:
        from ..auth.base import ProfileNotFoundError

        raise ProfileNotFoundError(
            "No profile specified and no default profile configured. "
            "Run 'pltr configure configure' to set up authentication."
        )
    return FoundryInternalClient(profile=effective_profile)


def _require_successful_internal_response(
    status: int,
    payload: Any,
    raw: str,
    *,
    operation: str,
) -> None:
    """Separate transport/deserialization failures from validation errors."""
    if status == 200:
        return
    if status == 400:
        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        detail = f" ({error_name})" if error_name else ""
        raise foundry_error_from_conjure(
            status,
            payload,
            raw,
            context=(
                f"{operation} request failed during contract deserialization"
                f"{detail}; the request shape was rejected before validation"
            ),
        )
    raise foundry_error_from_conjure(status, payload, raw, context=operation)


def _dry_run_errors(payload: Any) -> List[Mapping[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("type") != "error":
        return []
    error_status = payload.get("error")
    if not isinstance(error_status, Mapping):
        return []
    errors = error_status.get("errors")
    if not isinstance(errors, list):
        return []
    return [error for error in errors if isinstance(error, Mapping)]


def _error_terminal_name(error_name: str) -> str:
    return error_name.rsplit(":", 1)[-1]


def _format_validation_error(error: Mapping[str, Any], *, entity: str) -> str:
    error_data = error.get("errorData")
    if not isinstance(error_data, Mapping):
        return "unknown ontology validation error"
    error_name = str(error_data.get("errorName") or "unknown")
    terminal_name = _error_terminal_name(error_name)
    if terminal_name in _ALREADY_EXISTS_ERROR_NAMES:
        if entity == "object type":
            # Object types have an update path; this message only surfaces
            # when already-exists arrives mixed with other create errors.
            return f"{entity} already exists ({error_name})"
        return (
            f"{entity} already exists; update path not yet implemented ({error_name})"
        )
    mapped = _COMMON_ERROR_MESSAGES.get(terminal_name)
    if mapped:
        return f"{mapped} ({error_name})"
    error_message = error_data.get("errorMessage")
    if isinstance(error_message, str) and error_message:
        return f"{error_name}: {error_message}"
    return error_name


def _run_dry_run_full(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
    *,
    operation: str,
    entity: str,
) -> Tuple[List[str], List[str], List[Mapping[str, Any]]]:
    """POST a dry-run validation.

    Returns ``(formatted_errors, terminal_error_names, raw_errors)``. Callers
    that need the server's structured validation entries (for example to
    attach them to a typed ``FoundryApiError``) use this over
    :func:`_run_dry_run_collect`.
    """
    dry_run_url, _ = _modify_urls(ontology_rid)
    status, parsed, raw = client.conjure(
        "POST",
        dry_run_url,
        json_body={"modificationRequest": modification_request},
        expected=200,
    )
    _require_successful_internal_response(status, parsed, raw, operation=operation)
    if isinstance(parsed, Mapping) and parsed.get("type") == "success":
        return [], [], []
    errors = _dry_run_errors(parsed)
    if errors:
        names = []
        for error in errors:
            error_data = error.get("errorData")
            if isinstance(error_data, Mapping):
                names.append(
                    _error_terminal_name(str(error_data.get("errorName") or ""))
                )
        return (
            [_format_validation_error(error, entity=entity) for error in errors],
            names,
            errors,
        )
    raise RuntimeError(
        f"{operation} returned an invalid response shape: expected "
        "{'type': 'success'} or {'type': 'error', 'error': {'errors': [...]}}"
    )


def _run_dry_run_collect(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
    *,
    operation: str,
    entity: str,
) -> Tuple[List[str], List[str]]:
    """POST a dry-run validation.

    Returns ``(formatted_errors, terminal_error_names)``. Callers that only
    need messages use :func:`_run_dry_run`; callers that branch on the kind of
    validation failure (for example already-exists -> update path) need the
    terminal names too.
    """
    errors, names, _ = _run_dry_run_full(
        client,
        ontology_rid,
        modification_request,
        operation=operation,
        entity=entity,
    )
    return errors, names


def _run_dry_run(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
    *,
    operation: str,
    entity: str,
) -> List[str]:
    """POST a dry-run validation; return formatted errors ([] on success)."""
    errors, _ = _run_dry_run_collect(
        client,
        ontology_rid,
        modification_request,
        operation=operation,
        entity=entity,
    )
    return errors


def _strip_nulls(value: Any) -> Any:
    """Recursively drop None values from mappings; keep lists and scalars.

    Loaded entity state contains explicit JSON nulls for absent optional
    fields. Conjure deserialization on this stack treats a present-but-null
    optional field differently from an absent one, so update modifications
    must omit them.
    """
    if isinstance(value, Mapping):
        return {
            key: _strip_nulls(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [_strip_nulls(item) for item in value]
    return value


def _run_modify(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
    *,
    operation: str,
) -> Mapping[str, Any]:
    """POST the real modifyOntology request (no dry-run wrapper)."""
    _, modify_url = _modify_urls(ontology_rid)
    status, parsed, raw = client.conjure(
        "POST",
        modify_url,
        json_body=modification_request,
        expected=200,
    )
    _require_successful_internal_response(status, parsed, raw, operation=operation)
    if not isinstance(parsed, Mapping):
        raise RuntimeError(
            f"{operation} returned an invalid response shape: expected a JSON object"
        )
    return parsed


def _collect_terminal_error_names(status: int, payload: Any) -> List[str]:
    """Collect terminal error names from an error body or dry-run union."""
    names: List[str] = []
    if isinstance(payload, Mapping):
        error_name = payload.get("errorName")
        if isinstance(error_name, str):
            names.append(_error_terminal_name(error_name))
    for error in _dry_run_errors(payload):
        error_data = error.get("errorData")
        if isinstance(error_data, Mapping):
            names.append(_error_terminal_name(str(error_data.get("errorName") or "")))
    return names


def _verify_entity_gone(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
    *,
    gone_error_names: Optional[Any] = None,
) -> Dict[str, Any]:
    """Verify a deletion landed by re-issuing it as a dry-run.

    Deserialization on this stack is lenient, so a 200 on the real modify
    call is not proof of effect. A deleted entity makes the same request
    fail validation with a NotFound error, which is a positive read-back
    signal from the verified dry-run endpoint.
    """
    names = set(gone_error_names or _GONE_ERROR_NAMES)
    dry_run_url, _ = _modify_urls(ontology_rid)
    status, parsed, raw = client.conjure(
        "POST",
        dry_run_url,
        json_body={"modificationRequest": modification_request},
        expected=200,
    )
    terminal_names = _collect_terminal_error_names(status, parsed)
    if status in (200, 400) and any(name in names for name in terminal_names):
        return {
            "status": "verified",
            "detail": ("post-delete dry-run now reports the entity as not found"),
        }
    if (
        status == 200
        and isinstance(parsed, Mapping)
        and parsed.get("type") == "success"
    ):
        return {
            "status": "not-verified",
            "detail": (
                "post-delete dry-run still validates, so the entity may not be deleted"
            ),
        }
    return {
        "status": "not-verified",
        "detail": (
            f"post-delete verification inconclusive (HTTP {status}): {str(raw)[:200]}"
        ),
    }


def _verify_entity_present(
    client: Any,
    ontology_rid: str,
    modification_request: Mapping[str, Any],
) -> Dict[str, Any]:
    """Verify a creation landed by re-issuing it as a dry-run.

    A created entity makes the same create request fail validation with an
    already-exists error, which is a positive read-back signal from the
    verified dry-run endpoint.
    """
    dry_run_url, _ = _modify_urls(ontology_rid)
    status, parsed, raw = client.conjure(
        "POST",
        dry_run_url,
        json_body={"modificationRequest": modification_request},
        expected=200,
    )
    terminal_names = _collect_terminal_error_names(status, parsed)
    if status == 200 and any("AlreadyExist" in name for name in terminal_names):
        return {
            "status": "verified",
            "detail": (
                "post-create dry-run now reports the entity as already existing"
            ),
        }
    if (
        status == 200
        and isinstance(parsed, Mapping)
        and parsed.get("type") == "success"
    ):
        return {
            "status": "not-verified",
            "detail": (
                "post-create dry-run still validates as a create, so the "
                "entity may not have been created"
            ),
        }
    return {
        "status": "not-verified",
        "detail": (
            f"post-create verification inconclusive (HTTP {status}): {str(raw)[:200]}"
        ),
    }


def _entity_id_suffix(api_name: str) -> str:
    """Convert an API name into the lower-kebab ID required by OMS."""
    with_word_boundaries = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", api_name)
    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", with_word_boundaries)
    suffix = re.sub(r"[^a-z0-9]+", "-", with_word_boundaries.casefold()).strip("-")
    if not suffix or not suffix[0].isalpha():
        raise RuntimeError(
            f"Cannot derive a valid entity ID from API name {api_name!r}; "
            "the derived ID must start with a letter"
        )
    return suffix


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# Property type scalars supported by object-type-add-property, mapped to their
# TypeForModification wire shapes (vendor: PropertyTypeModification.type; all
# scalars except string are empty structs).
_PROPERTY_TYPE_WIRE_TYPES: Dict[str, Dict[str, Any]] = {
    "STRING": {
        "type": "string",
        "string": {"isLongText": False, "supportsExactMatching": True},
    },
    "INTEGER": {"type": "integer", "integer": {}},
    "LONG": {"type": "long", "long": {}},
    "DOUBLE": {"type": "double", "double": {}},
    "BOOLEAN": {"type": "boolean", "boolean": {}},
    "TIMESTAMP": {"type": "timestamp", "timestamp": {}},
    "DATE": {"type": "date", "date": {}},
}

# DEPRECATED is deliberately absent: DeprecatedPropertyTypeStatusModification
# requires deadline/message fields the command does not collect.
_PROPERTY_STATUS_WIRE_TYPES: Dict[str, Dict[str, Any]] = {
    "ACTIVE": {"type": "active", "active": {}},
    "EXPERIMENTAL": {"type": "experimental", "experimental": {}},
    "EXAMPLE": {"type": "example", "example": {}},
}

_BRANCH_UNSUPPORTED_TERMINAL_NAME = "BranchUnsupported"


def _raise_on_branch_unsupported(
    terminal_names: List[str],
    raw_errors: List[Mapping[str, Any]],
    *,
    branch_rid: Optional[str],
) -> None:
    """Surface branch-targeting failures as a typed FoundryApiError.

    ``ontologyBranchRid`` support is source-only on this stack, so a dry-run
    that rejects branch targeting must not degrade to a generic validation
    message: the typed error keeps the server's validation details.
    """
    if not branch_rid:
        return
    if not any(_BRANCH_UNSUPPORTED_TERMINAL_NAME in name for name in terminal_names):
        return
    raise FoundryApiError(
        f"ontology branch {branch_rid} is not supported as a modification "
        "target on this stack",
        error_name="OntologyMetadata:BranchUnsupported",
        validation_details=list(raw_errors),
    )


def _property_type_id(api_name: str) -> str:
    """Derive the snake_case PropertyTypeId matching loaded-state convention."""
    with_word_boundaries = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", api_name)
    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", with_word_boundaries)
    suffix = re.sub(r"[^a-z0-9]+", "_", with_word_boundaries.casefold()).strip("_")
    if not suffix or not suffix[0].isalpha():
        raise RuntimeError(
            f"Cannot derive a valid property type ID from API name "
            f"{api_name!r}; the derived ID must start with a letter"
        )
    return suffix


def _status_type_name(status: Any) -> Optional[str]:
    """Return the union discriminator of a loaded status, if present."""
    if isinstance(status, Mapping):
        status_type = status.get("type")
        if isinstance(status_type, str):
            return status_type
    return None


# Required ontology contract publication order. Referenced by
# the upsert/delete commands' help text and by validation hints.
PUBLICATION_ORDER_STEPS = (
    "modify backing dataset schemas",
    "implement transaction functions",
    "object-type-upsert",
    "link-type-upsert",
    "action-type-upsert",
    "validate actions and re-read test objects",
    "regenerate OSDK",
    "enable the corresponding application controls",
)

PUBLICATION_ORDER_TEXT = "; ".join(
    f"{index}) {step}" for index, step in enumerate(PUBLICATION_ORDER_STEPS, 1)
)

OBJECT_TYPE_UPSERT_STEP = 3
LINK_TYPE_UPSERT_STEP = 4
ACTION_TYPE_UPSERT_STEP = 5


def _order_hint(
    errors: List[str],
    *,
    step: int,
    triggers: Mapping[str, str],
) -> List[str]:
    """Append a required-order hint when validation reports a missing dependency.

    ``triggers`` maps terminal Foundry error names (matched as substrings of
    the formatted errors) to guidance for the dependency they signal. The
    hint is appended as an extra entry so it surfaces in JSON plans and
    printed output alike; it is operator guidance, not a Foundry error.
    """
    matched = sorted(
        {trigger for trigger in triggers if any(trigger in e for e in errors)}
    )
    if not matched:
        return errors
    guidance = "; ".join(triggers[trigger] for trigger in matched)
    return [
        *errors,
        f"hint (step {step} of the required publication order): {guidance}. "
        f"Full order: {PUBLICATION_ORDER_TEXT}",
    ]


class OntologyService(BaseService):
    """Service wrapper for Foundry ontology operations."""

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    def list_ontologies(self) -> List[Dict[str, Any]]:
        """
        List all ontologies visible to the current user.

        Returns:
            List of ontology information dictionaries
        """
        try:
            result = self.service.Ontology.list()
            ontologies = []
            # The response has a 'data' field containing the list of ontologies
            for ontology in result.data:
                ontologies.append(self._format_ontology_info(ontology))
            return ontologies
        except Exception as e:
            raise RuntimeError(f"Failed to list ontologies: {e}")

    def get_ontology(self, ontology_rid: str) -> Dict[str, Any]:
        """
        Get a specific ontology by RID.

        Args:
            ontology_rid: Ontology Resource Identifier

        Returns:
            Ontology information dictionary
        """
        try:
            ontology = self.service.Ontology.get(ontology_rid)
            return self._format_ontology_info(ontology)
        except Exception as e:
            raise RuntimeError(f"Failed to get ontology {ontology_rid}: {e}")

    def get_ontology_rid(self) -> Dict[str, Any]:
        """
        Resolve the ontology RID for this stack.

        The SDK exposes no "current ontology" lookup, so resolution lists the
        visible ontologies and succeeds only when exactly one is visible.
        Zero or multiple visible ontologies make the RID ambiguous and raise
        instead of guessing.

        Returns:
            Ontology information dictionary containing the resolved rid

        Raises:
            RuntimeError: If zero or multiple ontologies are visible
        """
        ontologies = self.list_ontologies()
        if not ontologies:
            raise RuntimeError("No ontologies are visible to the current user")
        if len(ontologies) > 1:
            choices = ", ".join(
                f"{ontology.get('api_name') or 'unknown'} ({ontology.get('rid')})"
                for ontology in ontologies
            )
            raise RuntimeError(
                "Multiple ontologies are visible; the ontology RID cannot be "
                "resolved unambiguously. Pick one with 'pltr ontology list': "
                f"{choices}"
            )
        return ontologies[0]

    def _format_ontology_info(self, ontology: Any) -> Dict[str, Any]:
        """Format ontology information for consistent output."""
        return {
            "rid": ontology.rid,
            "api_name": getattr(ontology, "api_name", None),
            "display_name": getattr(ontology, "display_name", None),
            "description": getattr(ontology, "description", None),
        }


class ObjectTypeService(BaseService):
    """Service wrapper for object type operations."""

    _OBJECT_TYPE_CREATE_ENDPOINTS = [
        "/v2/ontologies/{ontology}/objectTypes",
        "/v1/ontologies/{ontology}/objectTypes",
        "/ontology-manager/api/ontologies/{ontology}/objectTypes",
    ]
    _LINK_TYPE_CREATE_ENDPOINTS = [
        "/v2/ontologies/{ontology}/linkTypes",
        "/v1/ontologies/{ontology}/linkTypes",
        "/ontology-manager/api/ontologies/{ontology}/linkTypes",
    ]

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    def list_object_types(self, ontology_rid: str) -> List[Dict[str, Any]]:
        """
        List object types in an ontology.

        Args:
            ontology_rid: Ontology Resource Identifier

        Returns:
            List of object type information dictionaries
        """
        try:
            # ObjectType is nested under Ontology in the SDK
            result = self.service.Ontology.ObjectType.list(ontology_rid)
            object_types = []
            # The response has a 'data' field containing the list of object types
            for obj_type in result.data:
                object_types.append(self._format_object_type_info(obj_type))
            return object_types
        except Exception as e:
            raise RuntimeError(f"Failed to list object types: {e}")

    def get_object_type(self, ontology_rid: str, object_type: str) -> Dict[str, Any]:
        """
        Get a specific object type.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name

        Returns:
            Object type information dictionary
        """
        try:
            # ObjectType is nested under Ontology in the SDK
            obj_type = self.service.Ontology.ObjectType.get(ontology_rid, object_type)
            return self._format_object_type_info(obj_type)
        except Exception as e:
            # Chain explicitly so callers (e.g. guarded upsert preflight) can
            # distinguish a typed not-found from other failures.
            raise RuntimeError(f"Failed to get object type {object_type}: {e}") from e

    def create_object_type(
        self,
        ontology_rid: str,
        api_name: str,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an ontology object type via direct API calls.

        Args:
            ontology_rid: Ontology Resource Identifier
            api_name: Object type API name
            display_name: Object type display name
            primary_key: Primary key property API name
            backing_dataset: Backing dataset RID
            description: Optional object type description

        Returns:
            API response dictionary
        """
        payload = {
            "apiName": api_name,
            "displayName": display_name,
            "primaryKey": primary_key,
            "backingDatasetRid": backing_dataset,
        }
        if description is not None:
            payload["description"] = description

        return self._create_schema_entity(
            ontology_rid=ontology_rid,
            endpoints=self._OBJECT_TYPE_CREATE_ENDPOINTS,
            payload=payload,
            entity_type="object type",
            entity_id=api_name,
        )

    def upsert_object_type(
        self,
        ontology_rid: str,
        api_name: str,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Create an object type through the verified modifyOntology contract.

        Defaults to a dry-run: the request is validated against
        ``POST /ontology/v2/modify/dry-run`` and the validated plan is
        returned. With ``apply=True`` the real modification is issued and the
        result is verified by reading the object type back through the SDK,
        because deserialization on this stack is lenient and a 200 is not
        proof of effect.

        The internal API requires an ontology-specific namespace in new
        object type IDs. It does not expose that namespace directly, so a
        dry-run with a deliberately invalid ID discovers the namespace regex.

        When create validation reports the type already exists, the upsert
        switches to the update path: the type's current state is loaded
        through OntologyMetadataService.bulkLoadOntologyEntities, the
        caller-provided fields (display name, description) are merged onto
        that state, and an ``update`` modification is validated and issued.
        The merge never replaces the loaded state wholesale; fields the
        caller did not provide are carried over unchanged. Primary key and
        backing dataset changes are refused with a clear error rather than
        guessed at.
        """
        client = _internal_client(self)
        namespace = self._discover_object_type_namespace(client, ontology_rid)

        object_type_id = f"{namespace}.{_entity_id_suffix(api_name)}"
        modification_request = self._build_object_type_modification_request(
            object_type_id=object_type_id,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
        )
        plan: Dict[str, Any] = {
            "operation": "object-type-upsert",
            "apiName": api_name,
            "objectTypeId": object_type_id,
            "ontologyRid": ontology_rid,
        }

        validation_errors, terminal_names = _run_dry_run_collect(
            client,
            ontology_rid,
            modification_request,
            operation="object type dry-run",
            entity="object type",
        )
        if terminal_names and all(
            name in _OBJECT_TYPE_ALREADY_EXISTS_NAMES for name in terminal_names
        ):
            return self._update_existing_object_type(
                client,
                ontology_rid=ontology_rid,
                object_type_id=object_type_id,
                api_name=api_name,
                display_name=display_name,
                primary_key=primary_key,
                backing_dataset=backing_dataset,
                description=description,
                apply=apply,
                plan=plan,
            )
        validation_errors = _order_hint(
            validation_errors,
            step=OBJECT_TYPE_UPSERT_STEP,
            triggers={
                "SchemaForObjectTypeDatasourceNotFound": (
                    "the backing dataset schema must be updated before "
                    "object types are created or changed (step 1)"
                )
            },
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Object type dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        parsed = _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="object type modify",
        )
        created = parsed.get("createdObjectTypes")
        rid = created.get(object_type_id) if isinstance(created, Mapping) else None
        if not isinstance(rid, str):
            raise RuntimeError(
                "Object type modify succeeded but did not return the created "
                f"object type RID for {object_type_id}"
            )

        return {
            **plan,
            "mode": "applied",
            "rid": rid,
            "validation": {"status": "success", "errors": []},
            "verification": self._verify_object_type_present(ontology_rid, api_name),
        }

    def _update_existing_object_type(
        self,
        client: Any,
        *,
        ontology_rid: str,
        object_type_id: str,
        api_name: str,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str],
        apply: bool,
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing object type by merging the caller's delta.

        The current state is loaded from OntologyMetadataService; the
        caller-provided fields are applied onto that loaded state and the
        merged object is sent as an ``update`` modification. Fields the
        caller did not provide are preserved. If the current state cannot
        be loaded or cannot be faithfully reconstructed (interfaces,
        shared property types), the update fails loudly rather than
        guessing.
        """
        loaded = self._load_object_type_state(client, object_type_id)
        modification, changed_fields = self._merge_object_type_update(
            loaded,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
        )
        modification_request: Dict[str, Any] = {
            "objectTypes": {
                object_type_id: {
                    "type": "update",
                    "update": {"objectType": modification},
                }
            }
        }
        update_plan: Dict[str, Any] = {
            **plan,
            "upsertMode": "update",
            "changedFields": changed_fields,
            "update": {"objectType": modification},
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="object type update dry-run",
            entity="object type",
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Object type update dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **update_plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **update_plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        result: Dict[str, Any] = {
            **update_plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
        }
        loaded_rid = loaded.get("objectType", {}).get("rid")
        if isinstance(loaded_rid, str):
            result["rid"] = loaded_rid
        if not changed_fields:
            result["changed"] = False
            result["verification"] = {
                "status": "skipped",
                "detail": (
                    "no field changes; the update modification was not "
                    "issued to avoid a no-op ontology version bump"
                ),
            }
            return result

        result["changed"] = True
        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="object type update modify",
        )
        result["verification"] = self._verify_object_type_present(
            ontology_rid, api_name
        )
        return result

    def add_property_to_object_type(
        self,
        ontology_rid: str,
        object_type: str,
        api_name: str,
        property_type: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        backing_column: Optional[str] = None,
        backing_dataset: Optional[str] = None,
        branch_rid: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Add a property to an existing object type via modifyOntology.

        ``object_type`` is the object type API name or RID; the internal
        ObjectTypeId is resolved through the verified bulkLoadEntities read.
        The request is an ``objectTypes`` update carrying the merged state
        plus the new propertyType, and — when ``backing_column`` is given —
        an ``objectTypeDatasources`` update adding the columnMapping entry
        (see artifacts/ontology-modify-contract.md sections 2-3). Object
        types using interfaces or shared property types are refused: the
        loaded state cannot be faithfully reconstructed for them.

        Defaults to a dry-run; ``apply=True`` issues the real modification
        and verifies it by reloading the state and reading the created
        property RID and column mapping back. ``branch_rid`` targets a
        non-default ontology branch (request-level ``ontologyBranchRid``,
        source-only on this stack); a dry-run rejection of branch targeting
        surfaces as ``OntologyMetadata:BranchUnsupported``.
        """
        wire_type = _PROPERTY_TYPE_WIRE_TYPES.get(property_type.upper())
        if wire_type is None:
            raise RuntimeError(
                f"unsupported property type {property_type!r}; supported: "
                + ", ".join(sorted(_PROPERTY_TYPE_WIRE_TYPES))
            )
        status_wire = None
        if status is not None:
            status_wire = _PROPERTY_STATUS_WIRE_TYPES.get(status.upper())
            if status_wire is None:
                raise RuntimeError(
                    f"unsupported property status {status!r}; supported: "
                    + ", ".join(sorted(_PROPERTY_STATUS_WIRE_TYPES))
                )

        client = _internal_client(self)
        loaded = self._load_object_type_state(
            client,
            None,
            identifier=self._object_type_load_identifier(ontology_rid, object_type),
        )
        loaded_object_type = loaded["objectType"]
        object_type_id = loaded_object_type.get("id")
        if not isinstance(object_type_id, str):
            raise RuntimeError(
                "loaded object type state has no ObjectTypeId; the "
                "add-property path cannot proceed without it"
            )
        object_type_rid = loaded_object_type.get("rid")
        property_id = _property_type_id(api_name)

        # Reuse the loaded-state translation. It refuses interfaces and
        # shared property types, and with the loaded display name / primary
        # key / backing dataset passed back it changes nothing by itself.
        loaded_properties = loaded_object_type.get("propertyTypes") or {}
        loaded_primary_keys = [
            loaded_properties[rid]["id"]
            for rid in loaded_object_type.get("primaryKeys") or []
            if isinstance(loaded_properties.get(rid), Mapping)
            and loaded_properties[rid].get("id")
        ]
        if not loaded_primary_keys:
            raise RuntimeError(
                "loaded object type state has no resolvable primary key; "
                "the add-property path cannot proceed without it"
            )
        modification, _ = self._merge_object_type_update(
            loaded,
            display_name=(
                (loaded_object_type.get("displayMetadata") or {}).get("displayName")
                or object_type_id
            ),
            primary_key=loaded_primary_keys[0],
            backing_dataset=self._first_loaded_dataset_rid(loaded) or "",
            description=None,
        )

        property_mods = modification["propertyTypes"]
        if property_id in property_mods or any(
            prop.get("apiName") == api_name for prop in property_mods.values()
        ):
            raise RuntimeError(
                f"object type {object_type_id} already has a property with "
                f"API name {api_name!r}; nothing was added"
            )
        new_property: Dict[str, Any] = {
            "id": property_id,
            "apiName": api_name,
            "displayMetadata": {
                "displayName": display_name or api_name,
                "visibility": visibility or "NORMAL",
            },
            "indexedForSearch": False,
            "type": dict(wire_type),
            "typeClasses": [],
        }
        if description is not None:
            new_property["displayMetadata"]["description"] = description
        if status_wire is not None:
            new_property["status"] = status_wire
        property_mods[property_id] = new_property

        datasource_update: Optional[Dict[str, Any]] = None
        chosen_dataset_rid: Optional[str] = None
        if backing_column is not None:
            # The loaded payload is untyped, so narrow both halves here rather
            # than handing Any through: the callee keys a wire mapping by these
            # values and a non-string id would produce an unusable request.
            rid_to_id: Dict[str, str] = {
                rid: property_id_value
                for rid, prop in loaded_properties.items()
                if isinstance(prop, Mapping)
                and isinstance(rid, str)
                and isinstance(property_id_value := prop.get("id"), str)
                and property_id_value
            }
            datasource_update, chosen_dataset_rid = (
                self._build_datasource_column_update(
                    loaded,
                    rid_to_id=rid_to_id,
                    property_id=property_id,
                    backing_column=backing_column,
                    backing_dataset=backing_dataset,
                )
            )

        modification_request: Dict[str, Any] = {
            "objectTypes": {
                object_type_id: {
                    "type": "update",
                    "update": {"objectType": modification},
                }
            }
        }
        if datasource_update is not None:
            modification_request["objectTypeDatasources"] = {
                object_type_id: [datasource_update]
            }
        if branch_rid is not None:
            modification_request["ontologyBranchRid"] = branch_rid

        plan: Dict[str, Any] = {
            "operation": "object-type-add-property",
            "apiName": api_name,
            "propertyTypeId": property_id,
            "objectTypeId": object_type_id,
            "ontologyRid": ontology_rid,
        }
        if isinstance(object_type_rid, str):
            plan["objectTypeRid"] = object_type_rid
        if backing_column is not None:
            plan["backingColumn"] = backing_column
            plan["backingDataset"] = chosen_dataset_rid
        if branch_rid is not None:
            plan["ontologyBranchRid"] = branch_rid

        validation_errors, terminal_names, raw_errors = _run_dry_run_full(
            client,
            ontology_rid,
            modification_request,
            operation="object type add property dry-run",
            entity="object type",
        )
        _raise_on_branch_unsupported(terminal_names, raw_errors, branch_rid=branch_rid)
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Object type add property dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="object type add property modify",
        )
        verification, property_rid = self._verify_property_present(
            client,
            object_type_id=object_type_id,
            api_name=api_name,
            backing_column=backing_column,
        )
        result: Dict[str, Any] = {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": verification,
        }
        if property_rid is not None:
            result["propertyRid"] = property_rid
        return result

    def _object_type_load_identifier(
        self, ontology_rid: str, object_type: str
    ) -> Dict[str, Any]:
        """Build a bulkLoadEntities identifier, resolving API names to RIDs.

        The bulk-load ``ObjectTypeIdentifier`` union supports only
        ``objectTypeId``/``objectTypeRid`` (vendor api-components.ts); an
        ``objectTypeApiName`` variant is leniently dropped server-side and
        yields a null entry. API names are resolved to RIDs through the SDK
        first.
        """
        if object_type.startswith("ri."):
            return {"type": "objectTypeRid", "objectTypeRid": object_type}
        try:
            resolved = self.service.Ontology.ObjectType.get(ontology_rid, object_type)
        except Exception as e:
            raise foundry_error_from_sdk(
                e, context=f"resolve object type '{object_type}'"
            )
        rid = getattr(resolved, "rid", None)
        if not isinstance(rid, str) or not rid:
            raise FoundryApiError(
                f"Could not resolve object type API name '{object_type}' to a RID",
                error_name="OntologyMetadata:ObjectTypeNotFound",
                safe_parameters={"objectTypeApiName": object_type},
            )
        return {"type": "objectTypeRid", "objectTypeRid": rid}

    @staticmethod
    def _first_loaded_dataset_rid(loaded: Mapping[str, Any]) -> Optional[str]:
        """Return the first dataset RID among loaded datasources, if any."""
        for entry in loaded.get("datasources") or []:
            if not isinstance(entry, Mapping):
                continue
            definition = entry.get("datasource")
            if not isinstance(definition, Mapping):
                continue
            body = next(
                (
                    definition.get(variant)
                    for variant in ("dataset", "datasetV2", "datasetV3")
                    if isinstance(definition.get(variant), Mapping)
                ),
                None,
            )
            if body is not None and isinstance(body.get("datasetRid"), str):
                return body["datasetRid"]
        return None

    @staticmethod
    def _build_datasource_column_update(
        loaded: Mapping[str, Any],
        *,
        rid_to_id: Mapping[str, str],
        property_id: str,
        backing_column: str,
        backing_dataset: Optional[str],
    ) -> Tuple[Dict[str, Any], str]:
        """Build the objectTypeDatasources update adding a columnMapping.

        The loaded datasource definition is translated back into its
        modification shape (PropertyTypeRid keys become PropertyTypeIds)
        and the new property's column mapping is appended. Only ``dataset``
        and ``datasetV2`` datasources are supported: ``datasetV3`` carries
        property security groups that an update could silently drop, so it
        is refused. Returns ``(update_entry, dataset_rid)``.
        """
        candidates: List[Tuple[Mapping[str, Any], str, Mapping[str, Any]]] = []
        unsupported_variants: List[str] = []
        for entry in loaded.get("datasources") or []:
            if not isinstance(entry, Mapping):
                continue
            definition = entry.get("datasource")
            if not isinstance(definition, Mapping):
                continue
            variant = definition.get("type")
            body = definition.get(variant) if isinstance(variant, str) else None
            if not isinstance(body, Mapping) or "datasetRid" not in body:
                continue
            if variant not in ("dataset", "datasetV2"):
                unsupported_variants.append(str(variant))
                continue
            if backing_dataset is not None and (
                body.get("datasetRid") != backing_dataset
            ):
                continue
            candidates.append((entry, str(variant), body))

        if not candidates:
            if unsupported_variants:
                raise RuntimeError(
                    "cannot map the backing column: the object type's "
                    f"datasources are {unsupported_variants}, which the "
                    "add-property path cannot faithfully update (property "
                    "security groups would be dropped); only 'dataset' and "
                    "'datasetV2' datasources are supported"
                )
            raise RuntimeError(
                "cannot map the backing column: the object type has no "
                "dataset-backed datasource"
                + (
                    f" matching {backing_dataset}"
                    if backing_dataset is not None
                    else ""
                )
            )
        if len(candidates) > 1:
            raise RuntimeError(
                "the object type has multiple dataset-backed datasources; "
                "pass --backing-dataset to select one"
            )

        entry, variant, body = candidates[0]
        datasource_rid = entry.get("rid")
        if not isinstance(datasource_rid, str):
            raise RuntimeError(
                "loaded datasource has no datasource RID; the datasource "
                "update path requires it"
            )
        dataset_rid = body["datasetRid"]

        mapping: Dict[str, Any] = {}
        for prop_rid, info in (body.get("propertyMapping") or {}).items():
            mapped_id = rid_to_id.get(prop_rid)
            if mapped_id is None:
                raise RuntimeError(
                    f"loaded datasource maps unknown property {prop_rid}; "
                    "the add-property path refuses to drop the mapping"
                )
            mapping[mapped_id] = info

        if variant == "dataset":
            mapping[property_id] = backing_column
            dataset_mod: Dict[str, Any] = {
                "datasetRid": dataset_rid,
                "propertyMapping": mapping,
            }
            if body.get("writebackDatasetRid"):
                dataset_mod["writebackDatasetRid"] = body["writebackDatasetRid"]
            definition = {"type": "dataset", "dataset": dataset_mod}
        else:
            mapping[property_id] = {
                "type": "column",
                "column": backing_column,
            }
            definition = {
                "type": "datasetV2",
                "datasetV2": {
                    "datasetRid": dataset_rid,
                    "propertyMapping": mapping,
                },
            }
        return (
            {
                "type": "update",
                "update": {
                    "rid": datasource_rid,
                    "objectTypeDatasourceDefinition": definition,
                },
            },
            dataset_rid,
        )

    def _verify_property_present(
        self,
        client: Any,
        *,
        object_type_id: str,
        api_name: str,
        backing_column: Optional[str],
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Read a created property back via the verified bulkLoadEntities.

        Returns ``(verification, property_rid)``. The authoritative read-back
        reloads the object type state and locates the property by API name;
        when a backing column was requested, the datasource mappings are
        checked for the new column too.
        """
        try:
            entry = self._load_object_type_state(client, object_type_id)
        except Exception as e:
            return (
                {
                    "status": "not-verified",
                    "detail": (f"read-back via bulkLoadEntities failed: {e}"),
                },
                None,
            )
        properties = entry["objectType"].get("propertyTypes") or {}
        match = next(
            (
                (rid, prop)
                for rid, prop in properties.items()
                if isinstance(prop, Mapping) and prop.get("apiName") == api_name
            ),
            None,
        )
        if match is None:
            return (
                {
                    "status": "not-verified",
                    "detail": (
                        "read-back via bulkLoadEntities did not find the "
                        f"property {api_name!r}"
                    ),
                },
                None,
            )
        property_rid, _ = match
        if backing_column is not None:
            mapped = False
            for ds_entry in entry.get("datasources") or []:
                if not isinstance(ds_entry, Mapping):
                    continue
                definition = ds_entry.get("datasource")
                if not isinstance(definition, Mapping):
                    continue
                body = definition.get(definition.get("type"))
                if not isinstance(body, Mapping):
                    continue
                values = (body.get("propertyMapping") or {}).values()
                if any(
                    value == backing_column
                    or (
                        isinstance(value, Mapping)
                        and value.get("column") == backing_column
                    )
                    for value in values
                ):
                    mapped = True
                    break
            if not mapped:
                return (
                    {
                        "status": "not-verified",
                        "detail": (
                            "property read back via bulkLoadEntities but "
                            f"no datasource maps column {backing_column!r}"
                        ),
                    },
                    property_rid,
                )
            return (
                {
                    "status": "verified",
                    "detail": (
                        "property and column mapping read back via bulkLoadEntities"
                    ),
                },
                property_rid,
            )
        return (
            {
                "status": "verified",
                "detail": "property read back via bulkLoadEntities",
            },
            property_rid,
        )

    def resolve_object_type(
        self,
        ontology_rid: str,
        *,
        api_name: Optional[str] = None,
        rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve an object type API name or RID to its full identifiers.

        Read-only: goes through the verified bulkLoadEntities endpoint and
        returns both the RID and the internal ObjectTypeId, plus display
        name and status where available.
        """
        if (api_name is None) == (rid is None):
            raise RuntimeError("resolve requires exactly one of api_name or rid")
        client = _internal_client(self)
        identifier = (
            {"type": "objectTypeRid", "objectTypeRid": rid}
            if rid is not None
            else self._object_type_load_identifier(ontology_rid, api_name or "")
        )
        entry = self._load_object_type_state(client, None, identifier=identifier)
        object_type = entry["objectType"]
        display_metadata = object_type.get("displayMetadata") or {}
        return {
            "kind": "object-type",
            "ontologyRid": ontology_rid,
            "rid": object_type.get("rid"),
            "id": object_type.get("id"),
            "apiName": object_type.get("apiName"),
            "displayName": display_metadata.get("displayName"),
            "status": _status_type_name(object_type.get("status")),
        }

    def resolve_property(
        self,
        ontology_rid: str,
        *,
        object_type: str,
        api_name: str,
    ) -> Dict[str, Any]:
        """Resolve a property API name within an object type scope.

        Read-only: loads the object type (API name or RID) through the
        verified bulkLoadEntities endpoint and returns the property's RID
        and internal PropertyTypeId.
        """
        client = _internal_client(self)
        entry = self._load_object_type_state(
            client,
            None,
            identifier=self._object_type_load_identifier(ontology_rid, object_type),
        )
        loaded_object_type = entry["objectType"]
        for property_rid, prop in (
            loaded_object_type.get("propertyTypes") or {}
        ).items():
            if not isinstance(prop, Mapping):
                continue
            if prop.get("apiName") != api_name:
                continue
            display_metadata = prop.get("displayMetadata") or {}
            return {
                "kind": "property",
                "ontologyRid": ontology_rid,
                "rid": prop.get("rid") or property_rid,
                "id": prop.get("id"),
                "apiName": api_name,
                "displayName": display_metadata.get("displayName"),
                "status": _status_type_name(prop.get("status")),
                "objectType": {
                    "rid": loaded_object_type.get("rid"),
                    "id": loaded_object_type.get("id"),
                    "apiName": loaded_object_type.get("apiName"),
                },
            }
        raise RuntimeError(
            f"object type {loaded_object_type.get('apiName') or object_type} "
            f"has no property with API name {api_name!r}"
        )

    @staticmethod
    def _load_object_type_state(
        client: Any,
        object_type_id: Optional[str],
        *,
        identifier: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        """Load an object type's current state via bulkLoadEntities.

        Endpoint contract-verified against a live deployment. ``identifier``
        overrides the default ``objectTypeId`` identifier so callers can load by
        ``objectTypeRid`` (API names are resolved to RIDs by callers;
        the bulk-load union has no API-name variant). Requested entities that
        do not exist (or are not visible) come back as null/absent entries,
        which fails the update path loudly: no state, no update.
        """
        if identifier is None:
            identifier = {
                "type": "objectTypeId",
                "objectTypeId": object_type_id,
            }
        status, parsed, raw = client.conjure(
            "POST",
            _BULK_LOAD_ENTITIES_ENDPOINT,
            json_body={
                "objectTypes": [
                    {
                        "identifier": dict(identifier),
                    }
                ],
                "linkTypes": [],
                "actionTypes": [],
                "interfaceTypes": [],
                "sharedPropertyTypes": [],
                "typeGroups": [],
                # datasourceTypes filters which datasource definitions the
                # server includes; an empty list returns none, which would
                # silently disable the backing-dataset guard.
                "datasourceTypes": [
                    "DATASET",
                    "DATASET_V2",
                    "DATASET_V3",
                    "EDITS_ONLY",
                    "RESTRICTED_VIEW",
                    "RESTRICTED_VIEW_V2",
                    "STREAM",
                    "STREAM_V2",
                    "STREAM_V3",
                    "TIME_SERIES",
                ],
            },
            expected=200,
        )
        _require_successful_internal_response(
            status, parsed, raw, operation="object type load"
        )
        if not isinstance(parsed, Mapping):
            raise RuntimeError(
                "object type load returned an invalid response shape: "
                "expected a JSON object"
            )
        entries = parsed.get("objectTypes")
        entry = entries[0] if isinstance(entries, list) and entries else None
        if not isinstance(entry, Mapping) or not isinstance(
            entry.get("objectType"), Mapping
        ):
            raise RuntimeError(
                "Could not load the current state of object type "
                f"{object_type_id or identifier}: bulkLoadEntities returned "
                "no usable entry. The update path requires the existing "
                "type's state and refuses to guess or recreate."
            )
        return entry

    @staticmethod
    def _merge_object_type_update(
        loaded: Mapping[str, Any],
        *,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Build an ObjectTypeModification from loaded state plus the delta.

        The loaded ``_api`` ObjectType is translated field-by-field into
        the modification shape (property RIDs become PropertyTypeIds,
        interface RIDs become ``rid`` union members). Only display name
        and description are caller-mutable; primary key and backing
        dataset must match the loaded state. Returns
        ``(modification, changed_fields)``.
        """
        object_type = loaded["objectType"]
        if object_type.get("implementsInterfaces2"):
            raise RuntimeError(
                f"object type {object_type.get('id')} implements "
                "interfaces; the update path cannot faithfully reconstruct "
                "interface implementations and refuses to drop them"
            )

        loaded_properties = object_type.get("propertyTypes")
        if not isinstance(loaded_properties, Mapping):
            raise RuntimeError(
                "loaded object type state is missing propertyTypes; the "
                "update path cannot proceed without the current schema"
            )

        rid_to_id: Dict[str, str] = {}
        property_mods: Dict[str, Any] = {}
        copy_keys = (
            "apiName",
            "baseFormatter",
            "dataConstraints",
            "displayMetadata",
            "id",
            "indexedForSearch",
            "inlineAction",
            "ruleSetBinding",
            "status",
            "type",
            "typeClasses",
            "valueType",
        )
        for property_rid, loaded_property in loaded_properties.items():
            if not isinstance(loaded_property, Mapping):
                continue
            if loaded_property.get("sharedPropertyTypeRid") or (
                loaded_property.get("sharedPropertyTypeApiName")
            ):
                raise RuntimeError(
                    "object type uses shared property types; the update "
                    "path cannot faithfully reconstruct them and refuses "
                    "to drop them"
                )
            property_id = loaded_property.get("id")
            if not isinstance(property_id, str):
                raise RuntimeError(
                    f"loaded property {property_rid} has no PropertyTypeId; "
                    "the update path cannot proceed without it"
                )
            rid_to_id[property_rid] = property_id
            property_mods[property_id] = {
                key: value
                for key, value in ((key, loaded_property.get(key)) for key in copy_keys)
                if value is not None
            }

        loaded_primary_keys = [
            rid_to_id[rid]
            for rid in object_type.get("primaryKeys") or []
            if rid in rid_to_id
        ]
        if primary_key not in loaded_primary_keys:
            raise RuntimeError(
                "the update path cannot change the primary key: the loaded "
                f"primary keys are {loaded_primary_keys} but the caller "
                f"requested {primary_key!r}; change the primary key in the "
                "Foundry ontology manager instead"
            )

        for datasource_entry in loaded.get("datasources") or []:
            if not isinstance(datasource_entry, Mapping):
                continue
            definition = datasource_entry.get("datasource")
            if not isinstance(definition, Mapping):
                continue
            dataset = next(
                (
                    definition.get(variant)
                    for variant in ("dataset", "datasetV2", "datasetV3")
                    if isinstance(definition.get(variant), Mapping)
                ),
                None,
            )
            if dataset is None:
                continue
            loaded_dataset_rid = dataset.get("datasetRid")
            if isinstance(loaded_dataset_rid, str) and (
                loaded_dataset_rid != backing_dataset
            ):
                raise RuntimeError(
                    "the update path cannot change the backing dataset: "
                    f"the loaded datasource is {loaded_dataset_rid} but "
                    f"the caller requested {backing_dataset}"
                )

        display_metadata = dict(object_type.get("displayMetadata") or {})
        changed_fields: List[str] = []
        if display_name != display_metadata.get("displayName"):
            if display_metadata.get("pluralDisplayName") == (
                display_metadata.get("displayName")
            ):
                display_metadata["pluralDisplayName"] = display_name
            display_metadata["displayName"] = display_name
            changed_fields.append("displayName")
        if description is not None and description != (
            display_metadata.get("description")
        ):
            display_metadata["description"] = description
            changed_fields.append("description")

        loaded_traits = object_type.get("traits") or {}
        traits: Dict[str, Any] = {
            "workflowObjectTypeTraits": (
                loaded_traits.get("workflowObjectTypeTraits") or {}
            )
        }
        for trait_key in (
            "eventMetadata",
            "actionLogMetadata",
            "timeSeriesMetadata",
            "peeringMetadata",
            "sensorTrait",
        ):
            if loaded_traits.get(trait_key) is not None:
                traits[trait_key] = loaded_traits[trait_key]

        title_property_type_id = rid_to_id.get(
            str(object_type.get("titlePropertyTypeRid") or "")
        )
        if title_property_type_id is None:
            raise RuntimeError(
                "loaded object type state has an unmapped "
                "titlePropertyTypeRid; the update path cannot proceed "
                "without the title property"
            )

        modification: Dict[str, Any] = {
            "id": object_type["id"],
            "displayMetadata": display_metadata,
            "implementsInterfaces": [
                {"type": "rid", "rid": rid}
                for rid in object_type.get("implementsInterfaces") or []
            ],
            "implementsInterfaces2": [],
            "primaryKeys": loaded_primary_keys,
            "propertyTypes": property_mods,
            "sharedPropertyTypes": {},
            "titlePropertyTypeId": title_property_type_id,
            "traits": traits,
            "typeGroups": list(object_type.get("typeGroups") or []),
        }
        if object_type.get("apiName"):
            modification["apiName"] = object_type["apiName"]
        if object_type.get("status"):
            modification["status"] = object_type["status"]

        return _strip_nulls(modification), changed_fields

    def delete_object_type(
        self,
        ontology_rid: str,
        object_type_id: str,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Delete an object type through the verified modifyOntology contract.

        ``object_type_id`` is the internal ObjectTypeId (for example
        ``ns1exmpl.my-type``), not the API name: the delete variant is keyed
        by ObjectTypeId. Defaults to a dry-run; ``apply=True`` issues the
        real deletion and verifies it by re-issuing the delete as a dry-run,
        which must then report the object type as not found.
        """
        if "." not in object_type_id:
            raise RuntimeError(
                "object-type-delete requires the internal ObjectTypeId "
                "(for example 'ns1exmpl.my-type'), not an API name. The ID is "
                "returned by 'pltr ontology object-type-upsert' and visible "
                "in the Foundry ontology manager."
            )
        client = _internal_client(self)
        modification_request: Dict[str, Any] = {
            "objectTypes": {object_type_id: {"type": "delete", "delete": {}}}
        }
        plan: Dict[str, Any] = {
            "operation": "object-type-delete",
            "objectTypeId": object_type_id,
            "ontologyRid": ontology_rid,
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="object type delete dry-run",
            entity="object type",
        )
        validation_errors = _order_hint(
            validation_errors,
            step=OBJECT_TYPE_UPSERT_STEP,
            triggers={
                "LinkType": (
                    "dependent link types still reference this object "
                    "type; delete dependents in reverse publication order "
                    "— action-type-delete (step 5), then link-type-delete "
                    "(step 4), then object-type-delete (step 3)"
                )
            },
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Object type delete dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="object type delete",
        )
        return {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": _verify_entity_gone(
                client,
                ontology_rid,
                modification_request,
                gone_error_names={"ObjectTypesNotFound"},
            ),
        }

    def _discover_object_type_namespace(self, client: Any, ontology_rid: str) -> str:
        """Discover the ontology ID namespace via a deliberate ID error."""
        dry_run_url, _ = _modify_urls(ontology_rid)
        probe_request = self._build_object_type_modification_request(
            object_type_id=_NAMESPACE_PROBE_OBJECT_TYPE_ID,
            api_name="PltrNamespaceProbe",
            display_name="pltr namespace check",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.pltr-namespace-probe",
            description=None,
        )
        status, parsed, raw = client.conjure(
            "POST",
            dry_run_url,
            json_body={"modificationRequest": probe_request},
            expected=200,
        )
        _require_successful_internal_response(
            status, parsed, raw, operation="object type namespace discovery"
        )
        return self._extract_object_type_namespace(parsed)

    def _verify_object_type_present(
        self, ontology_rid: str, api_name: str
    ) -> Dict[str, Any]:
        """Read a created object type back through the verified SDK get."""
        try:
            self.get_object_type(ontology_rid, api_name)
        except Exception as e:
            return {
                "status": "not-verified",
                "detail": (f"read-back via SDK ontologies ObjectType.get failed: {e}"),
            }
        return {
            "status": "verified",
            "detail": "read back via SDK ontologies ObjectType.get",
        }

    def upsert_link_type(
        self,
        ontology_rid: str,
        api_name: str,
        one_side_object_type_id: str,
        many_side_object_type_id: str,
        display_name: Optional[str] = None,
        reverse_api_name: Optional[str] = None,
        one_side_primary_key: str = "id",
        many_side_property: Optional[str] = None,
        description: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Create a one-to-many link type through modifyOntology.

        The link definition references object types by their internal
        ObjectTypeIds (for example ``ns1exmpl.my-type``), which is the only
        identifier the verified contract accepts. Defaults to a dry-run;
        ``apply=True`` issues the real modification and verifies the create
        by re-issuing it as a dry-run, which must then report the link type
        as already existing.

        Existing link types are intentionally not updated yet.
        """
        client = _internal_client(self)
        namespace = self._discover_object_type_namespace(client, ontology_rid)

        link_type_id = f"{namespace}.{_entity_id_suffix(api_name)}"
        reverse_name = reverse_api_name or f"{api_name}Reverse"
        many_side = many_side_property or one_side_primary_key
        link_display = display_name or api_name

        def _link_metadata(name: str, display: str) -> Dict[str, Any]:
            return {
                "apiName": name,
                "displayMetadata": {
                    "displayName": display,
                    "pluralDisplayName": display,
                    "visibility": "NORMAL",
                },
                "typeClasses": [],
            }

        modification_request: Dict[str, Any] = {
            "linkTypes": {
                link_type_id: {
                    "type": "create",
                    "create": {
                        "linkType": {
                            "linkTypeId": link_type_id,
                            "definition": {
                                "type": "oneToMany",
                                "oneToMany": {
                                    "cardinalityHint": "ONE_TO_MANY",
                                    "objectTypeIdOneSide": one_side_object_type_id,
                                    "objectTypeIdManySide": many_side_object_type_id,
                                    "oneSidePrimaryKeyToManySidePropertyMapping": {
                                        one_side_primary_key: many_side,
                                    },
                                    "oneToManyLinkMetadata": _link_metadata(
                                        api_name, link_display
                                    ),
                                    "manyToOneLinkMetadata": _link_metadata(
                                        reverse_name, reverse_name
                                    ),
                                },
                            },
                            "description": description,
                            "status": None,
                        },
                        "markings": [],
                        "packageRid": None,
                        "projectRid": None,
                    },
                }
            }
        }
        plan: Dict[str, Any] = {
            "operation": "link-type-upsert",
            "apiName": api_name,
            "linkTypeId": link_type_id,
            "ontologyRid": ontology_rid,
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="link type dry-run",
            entity="link type",
        )
        validation_errors = _order_hint(
            validation_errors,
            step=LINK_TYPE_UPSERT_STEP,
            triggers={
                "ObjectTypesNotFound": (
                    "one of the referenced object types does not exist "
                    "yet; run object-type-upsert (step 3) before "
                    "link-type-upsert"
                )
            },
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Link type dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        parsed = _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="link type modify",
        )
        created = parsed.get("createdLinkTypes")
        rid = created.get(link_type_id) if isinstance(created, Mapping) else None
        result: Dict[str, Any] = {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": _verify_entity_present(
                client, ontology_rid, modification_request
            ),
        }
        if isinstance(rid, str):
            result["rid"] = rid
        return result

    def delete_link_type(
        self,
        ontology_rid: str,
        link_type_id: str,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Delete a link type through the verified modifyOntology contract.

        ``link_type_id`` is the internal LinkTypeId (for example
        ``ns1exmpl.my-link``), not the API name. Defaults to a dry-run;
        ``apply=True`` issues the real deletion and verifies it by
        re-issuing the delete as a dry-run, which must then report the link
        type as not found.
        """
        if "." not in link_type_id:
            raise RuntimeError(
                "link-type-delete requires the internal LinkTypeId "
                "(for example 'ns1exmpl.my-link'), not an API name. The ID is "
                "returned by 'pltr ontology link-type-upsert' and visible "
                "in the Foundry ontology manager."
            )
        client = _internal_client(self)
        modification_request: Dict[str, Any] = {
            "linkTypes": {link_type_id: {"type": "delete", "delete": {}}}
        }
        plan: Dict[str, Any] = {
            "operation": "link-type-delete",
            "linkTypeId": link_type_id,
            "ontologyRid": ontology_rid,
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="link type delete dry-run",
            entity="link type",
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Link type delete dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="link type delete",
        )
        return {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": _verify_entity_gone(
                client,
                ontology_rid,
                modification_request,
                gone_error_names={"LinkTypesNotFound"},
            ),
        }

    @staticmethod
    def _build_object_type_modification_request(
        *,
        object_type_id: str,
        api_name: str,
        display_name: str,
        primary_key: str,
        backing_dataset: str,
        description: Optional[str],
    ) -> Dict[str, Any]:
        """Build the minimal contract-verified ObjectType create modification."""
        object_display_metadata: Dict[str, Any] = {
            "displayName": display_name,
            "pluralDisplayName": display_name,
            "icon": {
                "type": "blueprint",
                "blueprint": {"color": "#4C90F0", "locator": "cube"},
            },
            "visibility": "NORMAL",
        }
        if description is not None:
            object_display_metadata["description"] = description

        return {
            "objectTypes": {
                object_type_id: {
                    "type": "create",
                    "create": {
                        "markings": [],
                        "objectType": {
                            "id": object_type_id,
                            "apiName": api_name,
                            "displayMetadata": object_display_metadata,
                            "implementsInterfaces": [],
                            "implementsInterfaces2": [],
                            "primaryKeys": [primary_key],
                            "propertyTypes": {
                                primary_key: {
                                    "id": primary_key,
                                    "apiName": primary_key,
                                    "displayMetadata": {
                                        "displayName": primary_key,
                                        "visibility": "NORMAL",
                                    },
                                    "indexedForSearch": True,
                                    "typeClasses": [],
                                    "type": {
                                        "type": "string",
                                        "string": {
                                            "isLongText": False,
                                            "supportsExactMatching": False,
                                        },
                                    },
                                }
                            },
                            "sharedPropertyTypes": {},
                            "titlePropertyTypeId": primary_key,
                            "traits": {"workflowObjectTypeTraits": {}},
                            "typeGroups": [],
                        },
                    },
                }
            },
            "objectTypeEntityMetadata": {
                object_type_id: {
                    "targetStorageBackend": {
                        "type": "objectStorageV2",
                        "objectStorageV2": {},
                    }
                }
            },
            "objectTypeDatasources": {
                object_type_id: [
                    {
                        "type": "create",
                        "create": {
                            "objectTypeDatasourceDefinition": {
                                "type": "dataset",
                                "dataset": {
                                    "datasetRid": backing_dataset,
                                    "propertyMapping": {
                                        primary_key: primary_key,
                                    },
                                },
                            }
                        },
                    }
                ]
            },
        }

    @classmethod
    def _extract_object_type_namespace(cls, payload: Any) -> str:
        """Extract the ontology namespace from the intentional ID error."""
        for error in _dry_run_errors(payload):
            error_data = error.get("errorData")
            if not isinstance(error_data, Mapping):
                continue
            error_name = str(error_data.get("errorName") or "")
            if _error_terminal_name(error_name) != "InvalidObjectTypeId":
                continue
            safe_args = error_data.get("safeArgs")
            if not isinstance(safe_args, list):
                continue
            for safe_arg in safe_args:
                if not isinstance(safe_arg, Mapping):
                    continue
                if safe_arg.get("name") != "regex":
                    continue
                regex_value = cls._unwrap_flexible_value(safe_arg.get("value"))
                namespace_match = re.match(
                    r"^\^?([a-z][a-z0-9-]*)\\\.",
                    str(regex_value or ""),
                )
                if namespace_match:
                    return namespace_match.group(1)
        raise RuntimeError(
            "Could not discover the ontology object type namespace: the dry-run "
            "probe did not return OntologyMetadata:InvalidObjectTypeId with a "
            "parseable regex safe argument"
        )

    @staticmethod
    def _unwrap_flexible_value(value: Any) -> Any:
        """Unwrap a Foundry flexible-value union to its scalar payload.

        Safe args arrive as `{"type": "string", "string": "..."}` and may
        nest inside `{"type": "optional", "optional": {"value": {...}}}`.
        """
        while isinstance(value, Mapping):
            if "string" in value:
                return value["string"]
            nested = value.get("optional")
            if isinstance(nested, Mapping) and "value" in nested:
                value = nested["value"]
                continue
            return None
        return value

    def create_link_type(
        self,
        ontology_rid: str,
        api_name: str,
        from_object_type: str,
        to_object_type: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        reverse_api_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an ontology link type via direct API calls.

        Args:
            ontology_rid: Ontology Resource Identifier
            api_name: Link type API name
            from_object_type: Source object type API name
            to_object_type: Target object type API name
            display_name: Optional link type display name
            description: Optional link type description
            reverse_api_name: Optional reverse direction API name

        Returns:
            API response dictionary
        """
        modern_payload = {
            "apiName": api_name,
            "fromObjectTypeApiName": from_object_type,
            "toObjectTypeApiName": to_object_type,
        }
        legacy_payload = {
            "apiName": api_name,
            "linkTypeApiNameAtoB": api_name,
            "aSideObjectTypeApiName": from_object_type,
            "bSideObjectTypeApiName": to_object_type,
        }

        if display_name is not None:
            modern_payload["displayName"] = display_name
            legacy_payload["displayName"] = display_name
        if description is not None:
            modern_payload["description"] = description
            legacy_payload["description"] = description
        if reverse_api_name is not None:
            modern_payload["reverseApiName"] = reverse_api_name
            legacy_payload["linkTypeApiNameBtoA"] = reverse_api_name

        def payload_for_endpoint(endpoint_template: str) -> Dict[str, Any]:
            if endpoint_template.startswith("/v2/"):
                return modern_payload
            return legacy_payload

        return self._create_schema_entity(
            ontology_rid=ontology_rid,
            endpoints=self._LINK_TYPE_CREATE_ENDPOINTS,
            payload=payload_for_endpoint,
            entity_type="link type",
            entity_id=api_name,
        )

    def get_link_type(
        self, ontology_rid: str, object_type: str, link_type: str
    ) -> Dict[str, Any]:
        """
        Get a specific outgoing link type of an object type.

        Uses the public SDK endpoint
        GET /v2/ontologies/{ontology}/objectTypes/{objectType}/outgoingLinkTypes/{linkType}.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Source object type API name
            link_type: Link type API name

        Returns:
            Link type information dictionary
        """
        try:
            # ObjectType is nested under Ontology in the SDK
            link = self.service.Ontology.ObjectType.get_outgoing_link_type(
                ontology_rid, object_type, link_type
            )
            return self._format_link_type_side_info(link)
        except Exception as e:
            raise RuntimeError(f"Failed to get link type {link_type}: {e}")

    def list_outgoing_link_types(
        self, ontology_rid: str, object_type: str
    ) -> List[Dict[str, Any]]:
        """
        List outgoing link types for an object type.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name

        Returns:
            List of link type information dictionaries
        """
        try:
            # ObjectType is nested under Ontology in the SDK
            result = self.service.Ontology.ObjectType.list_outgoing_link_types(
                ontology_rid, object_type
            )
            link_types = []
            # The response has a 'data' field containing the list of link types
            for link_type in result.data:
                link_types.append(self._format_link_type_info(link_type))
            return link_types
        except Exception as e:
            raise RuntimeError(f"Failed to list link types: {e}")

    def _format_object_type_info(self, obj_type: Any) -> Dict[str, Any]:
        """Format object type information for consistent output."""
        return {
            "api_name": obj_type.api_name,
            "display_name": getattr(obj_type, "display_name", None),
            "description": getattr(obj_type, "description", None),
            "primary_key": getattr(obj_type, "primary_key", None),
            "properties": getattr(obj_type, "properties", {}),
        }

    def _format_link_type_info(self, link_type: Any) -> Dict[str, Any]:
        """Format link type information for consistent output."""
        return {
            "api_name": link_type.api_name,
            "display_name": getattr(link_type, "display_name", None),
            "object_type": getattr(link_type, "object_type", None),
            "linked_object_type": getattr(link_type, "linked_object_type", None),
        }

    def _format_link_type_side_info(self, link_type: Any) -> Dict[str, Any]:
        """Format a LinkTypeSideV2 response for consistent output."""
        return {
            "rid": getattr(link_type, "link_type_rid", None),
            "api_name": link_type.api_name,
            "display_name": getattr(link_type, "display_name", None),
            "status": getattr(link_type, "status", None),
            "object_type": getattr(link_type, "object_type_api_name", None),
            "cardinality": getattr(link_type, "cardinality", None),
            "foreign_key_property": getattr(
                link_type, "foreign_key_property_api_name", None
            ),
        }

    def _create_schema_entity(
        self,
        ontology_rid: str,
        endpoints: List[str],
        payload: Union[Dict[str, Any], Callable[[str], Dict[str, Any]]],
        entity_type: str,
        entity_id: str,
    ) -> Dict[str, Any]:
        """Post create requests across known schema management endpoints."""
        encoded_ontology = quote(ontology_rid, safe="")
        last_error: Optional[Exception] = None

        for endpoint_template in endpoints:
            endpoint = endpoint_template.format(ontology=encoded_ontology)
            request_payload = (
                payload(endpoint_template) if callable(payload) else payload
            )
            try:
                response = self._make_request(
                    "POST", endpoint, json_data=request_payload
                )
                result = response.json() if response.text else {}
                if isinstance(result, dict):
                    result.setdefault("apiName", entity_id)
                    result.setdefault("ontologyRid", ontology_rid)
                    return result
                return {
                    "apiName": entity_id,
                    "ontologyRid": ontology_rid,
                    "response": result,
                }
            except requests.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                if status_code not in (404, 405):
                    raise RuntimeError(
                        f"Failed to create {entity_type} {entity_id}: {e}"
                    ) from e
                last_error = e
            except RuntimeError as e:
                if "404" in str(e) or "405" in str(e):
                    last_error = e
                    continue
                raise RuntimeError(f"Failed to create {entity_type} {entity_id}: {e}")
            except requests.RequestException as e:
                raise RuntimeError(f"Failed to create {entity_type} {entity_id}: {e}")
            except ValueError as e:
                raise RuntimeError(
                    f"Failed to parse create {entity_type} response for {entity_id}: {e}"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create {entity_type} {entity_id}: {e}"
                ) from e

        raise RuntimeError(f"Failed to create {entity_type} {entity_id}: {last_error}")


class OntologyObjectService(BaseService):
    """Service wrapper for ontology object operations."""

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    def list_objects(
        self,
        ontology_rid: str,
        object_type: str,
        page_size: Optional[int] = None,
        properties: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List objects of a specific type.

        DEPRECATED: Use list_objects_paginated() instead for better pagination support.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            page_size: Number of results per page
            properties: List of properties to include

        Returns:
            List of object dictionaries
        """
        try:
            result = self.service.OntologyObject.list(
                ontology_rid,
                object_type,
                page_size=page_size,
                select=properties,
            )
            objects = []
            for obj in result:
                objects.append(self._format_object(obj))
            return objects
        except Exception as e:
            raise RuntimeError(f"Failed to list objects: {e}")

    def list_objects_paginated(
        self,
        ontology_rid: str,
        object_type: str,
        config: PaginationConfig,
        properties: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> PaginationResult:
        """
        List objects with full pagination control.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            config: Pagination configuration
            properties: List of properties to include
            progress_callback: Optional progress callback

        Returns:
            PaginationResult with objects and metadata
        """
        try:
            settings = Settings()

            # Get iterator from SDK - ResourceIterator with next_page_token support
            iterator = self.service.OntologyObject.list(
                ontology_rid,
                object_type,
                page_size=config.page_size or settings.get("page_size", 20),
                select=properties,
            )

            # Use iterator pagination handler
            result = self._paginate_iterator(iterator, config, progress_callback)

            # Format objects
            result.data = [self._format_object(obj) for obj in result.data]

            return result
        except Exception as e:
            raise RuntimeError(f"Failed to list objects: {e}")

    def get_object(
        self,
        ontology_rid: str,
        object_type: str,
        primary_key: str,
        properties: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get a specific object by primary key.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            primary_key: Object primary key
            properties: List of properties to include

        Returns:
            Object dictionary
        """
        try:
            obj = self.service.OntologyObject.get(
                ontology_rid, object_type, primary_key, select=properties
            )
            return self._format_object(obj)
        except Exception as e:
            raise RuntimeError(f"Failed to get object {primary_key}: {e}")

    def aggregate_objects(
        self,
        ontology_rid: str,
        object_type: str,
        aggregations: List[Dict[str, Any]],
        group_by: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate objects with specified functions.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            aggregations: List of aggregation specifications
            group_by: Fields to group by
            filter: Filter criteria

        Returns:
            Aggregation results
        """
        try:
            result = self.service.OntologyObject.aggregate(
                ontology_rid,
                object_type,
                aggregations=aggregations,
                group_by=group_by,
                filter=filter,
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to aggregate objects: {e}")

    def list_linked_objects(
        self,
        ontology_rid: str,
        object_type: str,
        primary_key: str,
        link_type: str,
        page_size: Optional[int] = None,
        properties: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List objects linked to a specific object.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            primary_key: Object primary key
            link_type: Link type API name
            page_size: Number of results per page
            properties: List of properties to include

        Returns:
            List of linked object dictionaries
        """
        try:
            result = self.service.LinkedObject.list_linked_objects(
                ontology_rid,
                object_type,
                primary_key,
                link_type,
                page_size=page_size,
                select=properties,
            )
            objects = []
            for obj in result:
                objects.append(self._format_object(obj))
            return objects
        except Exception as e:
            raise RuntimeError(f"Failed to list linked objects: {e}")

    def count_objects(
        self,
        ontology_rid: str,
        object_type: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Count objects of a specific type.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            branch: Branch name (optional)

        Returns:
            Dictionary containing count information
        """
        try:
            response = self.service.OntologyObject.count(
                ontology_rid,
                object_type,
                branch=branch,
                preview=True,
            )
            return {
                "ontology_rid": ontology_rid,
                "object_type": object_type,
                "count": response.count,
                "branch": branch,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to count objects: {e}")

    def search_objects(
        self,
        ontology_rid: str,
        object_type: str,
        query: str,
        page_size: Optional[int] = None,
        properties: Optional[List[str]] = None,
        branch: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search objects by query.

        Args:
            ontology_rid: Ontology Resource Identifier
            object_type: Object type API name
            query: Search query string
            page_size: Number of results per page
            properties: List of properties to include
            branch: Branch name (optional)

        Returns:
            List of matching object dictionaries
        """
        try:
            result = self.service.OntologyObject.search(
                ontology_rid,
                object_type,
                query=query,
                page_size=page_size,
                select=properties,
                branch=branch,
            )
            objects = []
            for obj in result:
                objects.append(self._format_object(obj))
            return objects
        except Exception as e:
            raise RuntimeError(f"Failed to search objects: {e}")

    def _format_object(self, obj: Any) -> Dict[str, Any]:
        """Format object for consistent output."""
        if isinstance(obj, dict):
            return dict(obj)

        # Objects may have various properties - extract them dynamically
        result = {}
        if hasattr(obj, "__dict__"):
            for key, value in obj.__dict__.items():
                if not key.startswith("_"):
                    result[key] = value
        return result


class ActionService(BaseService):
    """Service wrapper for action operations."""

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    def apply_action(
        self,
        ontology_rid: str,
        action_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply an action with given parameters.

        Args:
            ontology_rid: Ontology Resource Identifier
            action_type: Action type API name
            parameters: Action parameters

        Returns:
            Action result
        """
        try:
            result = self.service.Action.apply(
                ontology_rid, action_type, parameters=parameters
            )
            return self._format_action_result(result)
        except Exception as e:
            raise RuntimeError(f"Failed to apply action {action_type}: {e}")

    def validate_action(
        self,
        ontology_rid: str,
        action_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate action parameters without executing.

        Args:
            ontology_rid: Ontology Resource Identifier
            action_type: Action type API name
            parameters: Action parameters to validate

        Returns:
            Validation result
        """
        try:
            result = self.service.Action.apply(
                ontology_rid,
                action_type,
                parameters=parameters,
                options=ApplyActionRequestOptions(mode="VALIDATE_ONLY"),
            )
            return self._format_validation_result(result)
        except Exception as e:
            raise RuntimeError(f"Failed to validate action {action_type}: {e}")

    def apply_batch_actions(
        self,
        ontology_rid: str,
        action_type: str,
        requests: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Apply multiple actions of the same type.

        Args:
            ontology_rid: Ontology Resource Identifier
            action_type: Action type API name
            requests: List of action requests (max 20)

        Returns:
            Combined batch action result
        """
        try:
            if len(requests) > 20:
                raise ValueError("Maximum 20 actions can be applied in a batch")

            result = self.service.Action.apply_batch(
                ontology_rid,
                action_type,
                requests=[{"parameters": request} for request in requests],
            )
            return self._format_batch_action_result(result)
        except Exception as e:
            raise RuntimeError(f"Failed to apply batch actions: {e}")

    def get_action_type(
        self,
        ontology_rid: str,
        action_type: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the full metadata of a specific action type.

        Uses the public SDK endpoint
        GET /v2/ontologies/{ontology}/actionTypes/{actionType}/fullMetadata,
        contract-verified against a live deployment. The endpoint is gated behind
        the preview flag, so ``preview=True`` is always passed.

        Args:
            ontology_rid: Ontology Resource Identifier
            action_type: Action type API name
            branch: Optional Foundry branch to load the definition from

        Returns:
            Action type information dictionary
        """
        try:
            metadata = self.service.ActionTypeFullMetadata.get(
                ontology_rid, action_type, branch=branch, preview=True
            )
            return self._format_action_type_info(metadata)
        except Exception as e:
            raise RuntimeError(f"Failed to get action type {action_type}: {e}")

    def upsert_action_type(
        self,
        ontology_rid: str,
        definition: Mapping[str, Any],
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Create an action type through the verified modifyOntology contract.

        ``definition`` is an ``ActionTypeCreate`` JSON document ( §4). It must contain
        ``apiName``, ``logic``, and at least one action-type-level entry in
        ``validations`` — all required by Foundry. ``actionTypesToCreate``
        and ``validations`` map keys must be UUID strings on the wire, so
        the request key is always generated and any non-UUID ``validations``
        keys are rewritten (``validationsOrdering`` is kept in sync).

        Defaults to a dry-run; ``apply=True`` issues the real modification
        and verifies the create by reading the action type back through the
        SDK full-metadata endpoint. Updates to existing action types go
        through :meth:`update_action_type`.
        """
        create = self._normalize_action_type_create(definition)
        api_name = create["apiName"]
        client = _internal_client(self)

        id_in_request = str(uuid.uuid4())
        modification_request: Dict[str, Any] = {
            "actionTypesToCreate": {id_in_request: create}
        }
        plan: Dict[str, Any] = {
            "operation": "action-type-upsert",
            "apiName": api_name,
            "ontologyRid": ontology_rid,
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="action type dry-run",
            entity="action type",
        )
        validation_errors = _order_hint(
            validation_errors,
            step=ACTION_TYPE_UPSERT_STEP,
            triggers={
                "ObjectTypesNotFound": (
                    "a parameter or rule references an object type that "
                    "does not exist yet; run object-type-upsert (step 3) "
                    "and link-type-upsert (step 4) before "
                    "action-type-upsert"
                )
            },
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Action type dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        parsed = _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="action type modify",
        )
        created = parsed.get("createdActionTypeRids")
        rid = created.get(id_in_request) if isinstance(created, Mapping) else None
        result: Dict[str, Any] = {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": self._verify_action_type_present(ontology_rid, api_name),
        }
        if isinstance(rid, str):
            result["rid"] = rid
        return result

    # Patch keys supported by update_action_type. Anything else is rejected
    # client-side with the supported set, because unknown body keys are
    # silently dropped by the server (contract doc, gotcha 6).
    _ACTION_TYPE_UPDATE_PATCH_KEYS = (
        "displayMetadata",
        "logic",
        "parameters",
        "status",
        "validations",
        "writeAuthorization",
    )

    def update_action_type(
        self,
        ontology_rid: str,
        action_type: str,
        patch: Mapping[str, Any],
        branch: Optional[str] = None,
        branch_rid: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Update an existing action type via modifyOntology.

        ``action_type`` is the action type API name or RID. ``patch`` is a
        partial document with keys from
        ``ActionService._ACTION_TYPE_UPDATE_PATCH_KEYS``; unknown keys are
        rejected client-side. The current definition is loaded through the
        verified bulkLoadEntities endpoint (resolved branch-aware through
        the SDK full-metadata read when an API name is given), the patch is
        merged onto it, and the result is sent as
        ``actionTypesToUpdate: {<actionTypeRid>: <ActionTypeUpdate>}`` (see
        artifacts/ontology-modify-contract.md section 4).

        Defaults to a dry-run; ``apply=True`` issues the real modification
        and verifies it by reading the action type back through the SDK
        full-metadata endpoint (``branch`` selects the read-back branch).
        ``branch_rid`` targets the modification itself at a non-default
        ontology branch (``ontologyBranchRid``, source-only on this stack).
        """
        if not isinstance(patch, Mapping) or not patch:
            raise FoundryApiError(
                "action-type-update requires a non-empty patch document "
                "(supported keys: "
                + ", ".join(self._ACTION_TYPE_UPDATE_PATCH_KEYS)
                + ")"
            )
        unknown = sorted(set(patch) - set(self._ACTION_TYPE_UPDATE_PATCH_KEYS))
        if unknown:
            raise FoundryApiError(
                "unsupported action type patch keys: "
                + ", ".join(unknown)
                + "; supported keys: "
                + ", ".join(self._ACTION_TYPE_UPDATE_PATCH_KEYS)
            )

        if action_type.startswith("ri."):
            rid = action_type
        else:
            metadata = self.get_action_type(ontology_rid, action_type, branch=branch)
            resolved = metadata.get("rid")
            if not isinstance(resolved, str) or not resolved:
                raise RuntimeError(
                    f"Could not resolve a RID for action type {action_type}; "
                    "the update path requires the action type RID"
                )
            rid = resolved

        client = _internal_client(self)
        loaded = self._load_action_type_state(client, rid=rid)
        update, changed_fields = self._merge_action_type_update(loaded, patch)
        api_name = (loaded["actionType"].get("metadata") or {}).get(
            "apiName"
        ) or action_type

        modification_request: Dict[str, Any] = {"actionTypesToUpdate": {rid: update}}
        if branch_rid is not None:
            modification_request["ontologyBranchRid"] = branch_rid

        plan: Dict[str, Any] = {
            "operation": "action-type-update",
            "apiName": api_name,
            "rid": rid,
            "ontologyRid": ontology_rid,
            "changedFields": changed_fields,
            "update": update,
        }
        if branch is not None:
            plan["branch"] = branch
        if branch_rid is not None:
            plan["ontologyBranchRid"] = branch_rid

        validation_errors, terminal_names, raw_errors = _run_dry_run_full(
            client,
            ontology_rid,
            modification_request,
            operation="action type update dry-run",
            entity="action type",
        )
        _raise_on_branch_unsupported(terminal_names, raw_errors, branch_rid=branch_rid)
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Action type update dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="action type update modify",
        )
        result: Dict[str, Any] = {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
        }
        try:
            result["metadata"] = self.get_action_type(
                ontology_rid, api_name, branch=branch
            )
            result["verification"] = {
                "status": "verified",
                "detail": ("read back via SDK ontologies ActionTypeFullMetadata.get"),
            }
        except Exception as e:
            result["verification"] = {
                "status": "not-verified",
                "detail": (
                    "read-back via SDK ontologies "
                    f"ActionTypeFullMetadata.get failed: {e}"
                ),
            }
        return result

    @staticmethod
    def _load_action_type_state(
        client: Any,
        *,
        rid: str,
    ) -> Mapping[str, Any]:
        """Load an action type's internal definition via bulkLoadEntities.

        Same verified endpoint as the object type state load. Returns the
        full entry (``actionType.actionTypeLogic`` +
        ``actionType.metadata``), which the update path translates into an
        ``ActionTypeUpdate``. Missing entries fail loudly. The bulk-load
        request takes ``ActionTypeLoadRequestV2`` entries (``{"rid": ...}``
        directly — there is no identifier wrapper and no API-name variant),
        so callers must resolve API names to RIDs before calling this.
        """
        status, parsed, raw = client.conjure(
            "POST",
            _BULK_LOAD_ENTITIES_ENDPOINT,
            json_body={
                "objectTypes": [],
                "linkTypes": [],
                "actionTypes": [{"rid": rid}],
                "interfaceTypes": [],
                "sharedPropertyTypes": [],
                "typeGroups": [],
                "datasourceTypes": [],
            },
            expected=200,
        )
        _require_successful_internal_response(
            status, parsed, raw, operation="action type load"
        )
        if not isinstance(parsed, Mapping):
            raise RuntimeError(
                "action type load returned an invalid response shape: "
                "expected a JSON object"
            )
        entries = parsed.get("actionTypes")
        entry = entries[0] if isinstance(entries, list) and entries else None
        if not isinstance(entry, Mapping) or not isinstance(
            entry.get("actionType"), Mapping
        ):
            raise RuntimeError(
                "Could not load the current state of action type "
                f"{rid}: bulkLoadEntities returned no usable "
                "entry. The update path requires the existing definition "
                "and refuses to guess or recreate."
            )
        return entry

    @classmethod
    def _merge_action_type_update(
        cls,
        loaded: Mapping[str, Any],
        patch: Mapping[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Build an ActionTypeUpdate from loaded state plus the patch.

        Loaded state (see artifacts/real-action-type-delete-contact.json)
        is translated field-by-field: logic and action-type-level
        validations are wholesale-replaced from the loaded values unless
        the patch overrides them; parameter/validation deltas go into the
        ``*ToCreate``/``*ToDelete``/``*ToUpdate`` maps (create keys are
        UUID-normalized, delete/update keys are rids). Returns
        ``(update, changed_fields)``.
        """
        action = loaded["actionType"]
        logic_block = action.get("actionTypeLogic") or {}
        metadata = action.get("metadata") or {}
        api_name = metadata.get("apiName")
        if not isinstance(api_name, str) or not api_name:
            raise RuntimeError(
                "loaded action type state has no apiName; the update path "
                "cannot proceed without it"
            )

        changed_fields: List[str] = []

        display_metadata = _strip_nulls(dict(metadata.get("displayMetadata") or {}))
        if "displayMetadata" in patch:
            dm_patch = patch["displayMetadata"]
            if not isinstance(dm_patch, Mapping):
                raise RuntimeError(
                    "'displayMetadata' patch must be a JSON object; it is "
                    "merged shallowly onto the loaded display metadata"
                )
            display_metadata.update(_strip_nulls(dict(dm_patch)))
            changed_fields.append("displayMetadata")

        logic = _strip_nulls(dict(logic_block.get("logic") or {"rules": []}))
        logic = cls._normalize_loaded_logic_rules(logic)
        if "logic" in patch:
            logic = cls._normalize_action_type_logic_patch(patch["logic"])
            changed_fields.append("logic")

        loaded_parameters = metadata.get("parameters") or {}
        parameter_ordering = list(metadata.get("parameterOrdering") or [])
        form_content_ordering = [
            dict(item)
            for item in (metadata.get("formContentOrdering") or [])
            if isinstance(item, Mapping)
        ]
        parameters_to_create: Dict[str, Any] = {}
        parameters_to_delete: List[str] = []
        if "parameters" in patch:
            (
                parameters_to_create,
                parameters_to_delete,
                parameter_ordering,
                form_content_ordering,
            ) = cls._apply_parameters_patch(
                patch["parameters"],
                loaded_parameters=loaded_parameters,
                parameter_ordering=parameter_ordering,
                form_content_ordering=form_content_ordering,
            )
            changed_fields.append("parameters")

        at_level = (logic_block.get("validation") or {}).get(
            "actionTypeLevelValidation"
        ) or {}
        loaded_rules = at_level.get("rules") or {}
        validations_ordering: List[Any] = list(at_level.get("ordering") or [])
        validations_to_create: Dict[str, Any] = {}
        validations_to_delete: List[str] = []
        validations_to_update: Dict[str, Any] = {}
        if "validations" in patch:
            (
                validations_to_create,
                validations_to_delete,
                validations_to_update,
                validations_ordering,
            ) = cls._apply_validations_patch(
                patch["validations"],
                loaded_rules=loaded_rules,
                ordering=validations_ordering,
            )
            changed_fields.append("validations")

        status_mod: Optional[Dict[str, Any]] = None
        if "status" in patch:
            status_mod = _PROPERTY_STATUS_WIRE_TYPES.get(str(patch["status"]).upper())
            if status_mod is None:
                raise RuntimeError(
                    "'status' patch must be ACTIVE, EXPERIMENTAL, or "
                    "EXAMPLE (DEPRECATED requires deadline/message fields "
                    "and is not supported)"
                )
            changed_fields.append("status")

        write_authorization: Optional[Any] = None
        if "writeAuthorization" in patch:
            write_auth_patch = patch["writeAuthorization"]
            if not isinstance(write_auth_patch, Mapping):
                raise RuntimeError(
                    "'writeAuthorization' patch must be a JSON object "
                    "(AuthorizationModification)"
                )
            write_authorization = _strip_nulls(dict(write_auth_patch))
            changed_fields.append("writeAuthorization")
        elif at_level.get("writeAuthorization") is not None:
            # Carry the loaded write authorization over so the update does
            # not clear it.
            write_authorization = _strip_nulls(dict(at_level["writeAuthorization"]))

        update: Dict[str, Any] = {
            "apiName": api_name,
            "displayMetadata": display_metadata,
            "logic": logic,
            "notifications": list(logic_block.get("notifications") or []),
            "parameterOrdering": parameter_ordering,
            "formContentOrdering": form_content_ordering,
            "parametersToCreate": parameters_to_create,
            "parametersToDelete": parameters_to_delete,
            "parametersToUpdate": {},
            "sectionsToCreate": {},
            "sectionsToDelete": [],
            "sectionsToUpdate": {},
            "typeGroups": list(
                (metadata.get("entities") or {}).get("typeGroups") or []
            ),
            "validationsOrdering": [
                cls._validation_rule_identifier(entry) for entry in validations_ordering
            ],
            "validationsToCreate": validations_to_create,
            "validationsToDelete": validations_to_delete,
            "validationsToUpdate": validations_to_update,
        }
        if status_mod is not None:
            update["status"] = status_mod
        if write_authorization is not None:
            update["writeAuthorization"] = write_authorization
        return _strip_nulls(update), changed_fields

    @staticmethod
    def _validation_rule_identifier(entry: Any) -> Any:
        """Encode one validationsOrdering entry as a ValidationRuleIdentifier.

        The wire union is ``{"type": "rid", "rid": ...}`` for persisted
        rules and ``{"type": "validationRuleIdInRequest", ...}`` for rules
        created in the same request; plain strings fail Conjure
        deserialization with a 422.
        """
        if isinstance(entry, Mapping):
            return dict(entry)
        if isinstance(entry, str) and entry.startswith("ri."):
            return {"type": "rid", "rid": entry}
        return {"type": "validationRuleIdInRequest", "validationRuleIdInRequest": entry}

    @staticmethod
    def _normalize_loaded_logic_rules(logic: Dict[str, Any]) -> Dict[str, Any]:
        """Translate loaded rule fields into the modification shape.

        Loaded rules carry ``logicRuleRid``; the modification types
        reference rules by ``logicRuleIdentifier`` (union rid |
        logicRuleIdInRequest), and the server leniently DROPS unknown
        fields — an unmapped rid would silently lose the rule's identity
        on update.
        """
        rules = logic.get("rules")
        if not isinstance(rules, list):
            return logic
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            variant = rule.get(rule.get("type", ""))
            if isinstance(variant, dict) and isinstance(
                variant.get("logicRuleRid"), str
            ):
                variant["logicRuleIdentifier"] = {
                    "type": "rid",
                    "rid": variant.pop("logicRuleRid"),
                }
        return logic

    @staticmethod
    def _normalize_action_type_logic_patch(logic_patch: Any) -> Dict[str, Any]:
        """Validate a replacement ActionLogicModification document.

        Rules pass through as given; function rules must carry their
        function RID and version as given by the function registry, and
        rule inputs may bind the protected current-user value as
        ``{"type": "currentUser", "currentUser": {}}`` (vendor:
        LogicRuleValueModification_currentUser).
        """
        if not isinstance(logic_patch, Mapping) or not isinstance(
            logic_patch.get("rules"), list
        ):
            raise RuntimeError(
                "'logic' patch requires a 'rules' list; it replaces the "
                "loaded logic wholesale"
            )
        for rule in logic_patch["rules"]:
            if not isinstance(rule, Mapping) or not isinstance(rule.get("type"), str):
                raise RuntimeError(
                    "each logic rule must be a Conjure union with a 'type' "
                    "discriminator"
                )
            rule_type = rule["type"]
            payload = rule.get(rule_type)
            if not isinstance(payload, Mapping):
                raise RuntimeError(
                    f"logic rule {rule_type!r} is missing its "
                    f"'{rule_type}' payload object"
                )
            if rule_type in ("functionRule", "batchedFunctionRule"):
                if not payload.get("functionRid") or not payload.get("functionVersion"):
                    raise RuntimeError(
                        f"{rule_type} requires 'functionRid' and "
                        "'functionVersion', passed as given by the "
                        "function registry"
                    )
                for input_name, value in (
                    payload.get("functionInputValues") or {}
                ).items():
                    if (
                        isinstance(value, Mapping)
                        and value.get("type") == "currentUser"
                        and not isinstance(value.get("currentUser"), Mapping)
                    ):
                        raise RuntimeError(
                            f"function input {input_name!r}: the protected "
                            "current-user value must be "
                            '{"type": "currentUser", "currentUser": {}}'
                        )
        return _strip_nulls(dict(logic_patch))

    @staticmethod
    def _apply_parameters_patch(
        params_patch: Any,
        *,
        loaded_parameters: Mapping[str, Any],
        parameter_ordering: List[str],
        form_content_ordering: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
        """Split a parameters patch into create/delete maps plus ordering.

        ``add`` entries become ``parametersToCreate`` keyed by ParameterId
        (PutParameterRequestModification shape); ``remove`` entries resolve
        to ParameterRids in ``parametersToDelete``; ``ordering`` replaces
        ``parameterOrdering`` and must name exactly the resulting
        parameters.
        """
        if not isinstance(params_patch, Mapping):
            raise RuntimeError(
                "'parameters' patch must be a JSON object with 'add', "
                "'remove', and/or 'ordering'"
            )
        unknown = sorted(set(params_patch) - {"add", "remove", "ordering"})
        if unknown:
            raise RuntimeError(
                "unsupported 'parameters' patch keys: "
                + ", ".join(unknown)
                + "; supported: add, remove, ordering"
            )
        add = params_patch.get("add") or {}
        remove = params_patch.get("remove") or []
        ordering_patch = params_patch.get("ordering")
        if not isinstance(add, Mapping) or not isinstance(remove, list):
            raise RuntimeError(
                "'parameters.add' must be an object and 'parameters.remove' "
                "a list of ParameterIds"
            )

        to_create: Dict[str, Any] = {}
        to_delete: List[str] = []
        ordering = list(parameter_ordering)
        form_ordering = list(form_content_ordering)

        for parameter_id in remove:
            parameter = loaded_parameters.get(parameter_id)
            if not isinstance(parameter, Mapping) or not parameter.get("rid"):
                raise RuntimeError(
                    f"cannot delete parameter {parameter_id!r}: not present "
                    "on the action type (known: "
                    + ", ".join(sorted(str(k) for k in loaded_parameters))
                    + ")"
                )
            to_delete.append(str(parameter["rid"]))
            ordering = [p for p in ordering if p != parameter_id]
            form_ordering = [
                fc for fc in form_ordering if fc.get("parameterId") != parameter_id
            ]

        for parameter_id, spec in add.items():
            if parameter_id in loaded_parameters and (parameter_id not in remove):
                raise RuntimeError(
                    f"parameter {parameter_id!r} already exists; remove it "
                    "in the same patch to replace it"
                )
            if not isinstance(spec, Mapping) or not all(
                key in spec for key in ("displayMetadata", "type", "validation")
            ):
                raise RuntimeError(
                    f"'parameters.add[{parameter_id!r}]' must be a "
                    "PutParameterRequestModification object with "
                    "'displayMetadata', 'type', and 'validation' (see the "
                    "action type create contract for the full shape)"
                )
            to_create[str(parameter_id)] = _strip_nulls(dict(spec))
            if parameter_id not in ordering:
                ordering.append(str(parameter_id))
                form_ordering.append(
                    {"type": "parameterId", "parameterId": str(parameter_id)}
                )

        if ordering_patch is not None:
            if not isinstance(ordering_patch, list) or set(
                map(str, ordering_patch)
            ) != set(ordering):
                raise RuntimeError(
                    "'parameters.ordering' must contain exactly the "
                    "resulting parameter ids: " + ", ".join(ordering)
                )
            ordering = [str(p) for p in ordering_patch]
        return to_create, to_delete, ordering, form_ordering

    @staticmethod
    def _apply_validations_patch(
        validations_patch: Any,
        *,
        loaded_rules: Mapping[str, Any],
        ordering: List[Any],
    ) -> Tuple[Dict[str, Any], List[str], Dict[str, Any], List[Any]]:
        """Split a validations patch into create/delete/update + ordering.

        ``add`` keys are UUID-normalized like action-type-upsert does for
        ``validations``; ``remove``/``update`` are keyed by
        ValidationRuleRid. The patch may not remove every action-type-level
        validation: Foundry requires at least one.
        """
        if not isinstance(validations_patch, Mapping):
            raise RuntimeError(
                "'validations' patch must be a JSON object with 'add', "
                "'remove', 'update', and/or 'ordering'"
            )
        unknown = sorted(
            set(validations_patch) - {"add", "remove", "update", "ordering"}
        )
        if unknown:
            raise RuntimeError(
                "unsupported 'validations' patch keys: "
                + ", ".join(unknown)
                + "; supported: add, remove, update, ordering"
            )
        add = validations_patch.get("add") or {}
        remove = validations_patch.get("remove") or []
        update = validations_patch.get("update") or {}
        ordering_patch = validations_patch.get("ordering")

        to_create: Dict[str, Any] = {}
        key_map: Dict[str, str] = {}
        for key, value in add.items():
            if not isinstance(value, Mapping) or (
                "condition" not in value or "displayMetadata" not in value
            ):
                raise RuntimeError(
                    f"'validations.add[{key!r}]' requires 'condition' and "
                    "'displayMetadata' (ValidationRuleModification)"
                )
            new_key = str(key) if _is_uuid(key) else str(uuid.uuid4())
            to_create[new_key] = _strip_nulls(dict(value))
            key_map[str(key)] = new_key

        to_delete: List[str] = []
        for rule_rid in remove:
            if rule_rid not in loaded_rules:
                raise RuntimeError(
                    f"cannot delete validation {rule_rid!r}: not present "
                    "on the action type"
                )
            to_delete.append(str(rule_rid))

        to_update: Dict[str, Any] = {}
        for rule_rid, value in update.items():
            if rule_rid not in loaded_rules:
                raise RuntimeError(
                    f"cannot update validation {rule_rid!r}: not present "
                    "on the action type"
                )
            if not isinstance(value, Mapping):
                raise RuntimeError(
                    f"'validations.update[{rule_rid!r}]' must be a "
                    "ValidationRuleModification object"
                )
            to_update[str(rule_rid)] = _strip_nulls(dict(value))

        remaining = [rid for rid in ordering if rid not in to_delete]
        remaining.extend(key for key in to_create if key not in remaining)
        if ordering_patch is not None:
            if not isinstance(ordering_patch, list):
                raise RuntimeError("'validations.ordering' must be a list")
            remaining = [key_map.get(str(item), item) for item in ordering_patch]
        if not remaining:
            raise RuntimeError(
                "the patch removes every action-type-level validation; "
                "Foundry requires at least one (see the create contract)"
            )
        return to_create, to_delete, to_update, remaining

    def resolve_action_type(
        self,
        ontology_rid: str,
        *,
        api_name: Optional[str] = None,
        rid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve an action type API name or RID to its identifiers.

        Read-only: goes through the verified bulkLoadEntities endpoint and
        returns the RID, API name, display name, and status.
        """
        if (api_name is None) == (rid is None):
            raise RuntimeError("resolve requires exactly one of api_name or rid")
        client = _internal_client(self)
        if rid is None:
            # The bulk-load ActionTypeIdentifier union supports only rid /
            # actionTypeIdInRequest; resolve the API name to a RID first.
            metadata_for_rid = self.get_action_type(ontology_rid, api_name or "")
            resolved_rid = metadata_for_rid.get("rid")
            if not isinstance(resolved_rid, str) or not resolved_rid:
                raise FoundryApiError(
                    f"Could not resolve action type API name '{api_name}' to a RID",
                    error_name="OntologyMetadata:ActionTypeNotFound",
                    safe_parameters={"actionTypeApiName": api_name},
                )
            rid = resolved_rid
        entry = self._load_action_type_state(client, rid=rid)
        metadata = entry["actionType"].get("metadata") or {}
        display_metadata = metadata.get("displayMetadata") or {}
        return {
            "kind": "action-type",
            "ontologyRid": ontology_rid,
            "rid": metadata.get("rid"),
            "apiName": metadata.get("apiName"),
            "displayName": display_metadata.get("displayName"),
            "status": _status_type_name(metadata.get("status")),
        }

    def delete_action_type(
        self,
        ontology_rid: str,
        action_type: str,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Delete an action type through the verified modifyOntology contract.

        ``action_type`` is the action type API name; its RID is resolved
        through the verified SDK full-metadata read. Defaults to a dry-run;
        ``apply=True`` issues the real deletion and verifies it by
        re-issuing the delete as a dry-run, which must then report the
        action type as not found.
        """
        metadata = self.get_action_type(ontology_rid, action_type)
        rid = metadata.get("rid")
        if not isinstance(rid, str) or not rid:
            raise RuntimeError(
                f"Could not resolve a RID for action type {action_type}; "
                "deletion requires the action type RID"
            )
        client = _internal_client(self)
        modification_request: Dict[str, Any] = {"actionTypesToDelete": [rid]}
        plan: Dict[str, Any] = {
            "operation": "action-type-delete",
            "apiName": action_type,
            "rid": rid,
            "ontologyRid": ontology_rid,
        }

        validation_errors = _run_dry_run(
            client,
            ontology_rid,
            modification_request,
            operation="action type delete dry-run",
            entity="action type",
        )
        if validation_errors:
            if apply:
                raise RuntimeError(
                    "Action type delete dry-run validation failed: "
                    + "; ".join(validation_errors)
                )
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "error", "errors": validation_errors},
            }
        if not apply:
            return {
                **plan,
                "mode": "dry-run",
                "validation": {"status": "success", "errors": []},
            }

        _run_modify(
            client,
            ontology_rid,
            modification_request,
            operation="action type delete",
        )
        return {
            **plan,
            "mode": "applied",
            "validation": {"status": "success", "errors": []},
            "verification": _verify_entity_gone(
                client,
                ontology_rid,
                modification_request,
                gone_error_names={"ActionTypesNotFound"},
            ),
        }

    @staticmethod
    def _normalize_action_type_create(
        definition: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Validate and UUID-normalize an ActionTypeCreate definition."""
        if not isinstance(definition, Mapping):
            raise RuntimeError(
                "Action type definition must be a JSON object containing an "
                "ActionTypeCreate document"
            )
        api_name = definition.get("apiName")
        if not isinstance(api_name, str) or not api_name:
            raise RuntimeError("Action type definition requires a non-empty 'apiName'")
        logic = definition.get("logic")
        if not isinstance(logic, Mapping) or not isinstance(logic.get("rules"), list):
            raise RuntimeError(
                "Action type definition requires 'logic' with a 'rules' list"
            )
        validations = definition.get("validations")
        if not isinstance(validations, Mapping) or not validations:
            raise RuntimeError(
                "Action type definition requires at least one action-type-"
                "level entry in 'validations' (Foundry rejects action types "
                "without one)"
            )

        create = dict(definition)
        normalized_validations: Dict[str, Any] = {}
        key_map: Dict[str, str] = {}
        for key, value in validations.items():
            new_key = str(key) if _is_uuid(key) else str(uuid.uuid4())
            normalized_validations[new_key] = value
            key_map[str(key)] = new_key
        create["validations"] = normalized_validations

        ordering = definition.get("validationsOrdering")
        if isinstance(ordering, list):
            create["validationsOrdering"] = [
                key_map.get(str(item), item) for item in ordering
            ]
        else:
            create["validationsOrdering"] = list(normalized_validations)
        return create

    def _verify_action_type_present(
        self, ontology_rid: str, api_name: str
    ) -> Dict[str, Any]:
        """Read a created action type back through the verified SDK get."""
        try:
            self.get_action_type(ontology_rid, api_name)
        except Exception as e:
            return {
                "status": "not-verified",
                "detail": (
                    "read-back via SDK ontologies "
                    f"ActionTypeFullMetadata.get failed: {e}"
                ),
            }
        return {
            "status": "verified",
            "detail": ("read back via SDK ontologies ActionTypeFullMetadata.get"),
        }

    def _format_action_type_info(self, metadata: Any) -> Dict[str, Any]:
        """Format an ActionTypeFullMetadata response for consistent output."""
        action_type = getattr(metadata, "action_type", None)
        if action_type is None:
            raise RuntimeError(
                "Action type full metadata response did not contain an "
                "'action_type' field"
            )
        parameters = getattr(action_type, "parameters", None) or {}
        operations = getattr(action_type, "operations", None) or []
        logic_rules = getattr(metadata, "full_logic_rules", None) or []
        return {
            "rid": getattr(action_type, "rid", None),
            "api_name": getattr(action_type, "api_name", None),
            "display_name": getattr(action_type, "display_name", None),
            "description": getattr(action_type, "description", None),
            "status": getattr(action_type, "status", None),
            "tool_description": getattr(action_type, "tool_description", None),
            "parameters": sorted(str(key) for key in parameters),
            "operations_count": len(operations),
            "logic_rules_count": len(logic_rules),
        }

    def _format_action_result(self, result: Any) -> Dict[str, Any]:
        """Format action result for consistent output."""
        validation = getattr(result, "validation", None)
        edits = getattr(result, "edits", None)
        return {
            "operation_id": getattr(result, "operation_id", None),
            "validation_result": (
                getattr(validation, "result", None) if validation is not None else None
            ),
            "edits_type": getattr(edits, "type", None) if edits is not None else None,
            "added_object_count": (
                getattr(edits, "added_object_count", None)
                if edits is not None
                else None
            ),
            "modified_objects_count": (
                getattr(edits, "modified_objects_count", None)
                if edits is not None
                else None
            ),
            "deleted_objects_count": (
                getattr(edits, "deleted_objects_count", None)
                if edits is not None
                else None
            ),
            "added_links_count": (
                getattr(edits, "added_links_count", None) if edits is not None else None
            ),
            "deleted_links_count": (
                getattr(edits, "deleted_links_count", None)
                if edits is not None
                else None
            ),
            "edits": getattr(edits, "edits", None) if edits is not None else None,
        }

    def _format_validation_result(self, result: Any) -> Dict[str, Any]:
        """Format validation result for consistent output."""
        validation = getattr(result, "validation", None)
        return {
            "result": (
                getattr(validation, "result", None) if validation is not None else None
            ),
            "submission_criteria": (
                getattr(validation, "submission_criteria", [])
                if validation is not None
                else []
            ),
            "parameters": (
                getattr(validation, "parameters", {}) if validation is not None else {}
            ),
        }

    def _format_batch_action_result(self, result: Any) -> Dict[str, Any]:
        """Format the combined edits returned by a batch action."""
        edits = getattr(result, "edits", None)
        return {
            "edits_type": getattr(edits, "type", None) if edits is not None else None,
            "added_object_count": (
                getattr(edits, "added_object_count", None)
                if edits is not None
                else None
            ),
            "modified_objects_count": (
                getattr(edits, "modified_objects_count", None)
                if edits is not None
                else None
            ),
            "deleted_objects_count": (
                getattr(edits, "deleted_objects_count", None)
                if edits is not None
                else None
            ),
            "added_links_count": (
                getattr(edits, "added_links_count", None) if edits is not None else None
            ),
            "deleted_links_count": (
                getattr(edits, "deleted_links_count", None)
                if edits is not None
                else None
            ),
            "edits": getattr(edits, "edits", None) if edits is not None else None,
        }


class QueryService(BaseService):
    """Service wrapper for query operations."""

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    def execute_query(
        self,
        ontology_rid: str,
        query_api_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a predefined query.

        Args:
            ontology_rid: Ontology Resource Identifier
            query_api_name: Query API name
            parameters: Query parameters

        Returns:
            Query results
        """
        try:
            result = self.service.Query.execute(
                ontology_rid, query_api_name, parameters=parameters or {}
            )
            return self._format_query_result(result)
        except Exception as e:
            raise RuntimeError(f"Failed to execute query {query_api_name}: {e}")

    def _format_query_result(self, result: Any) -> Dict[str, Any]:
        """Format query result for consistent output."""
        # Query results can vary widely - extract what we can
        if hasattr(result, "rows"):
            return {"rows": result.rows, "columns": getattr(result, "columns", [])}
        elif hasattr(result, "objects"):
            return {"objects": result.objects}
        else:
            # Return as dict if possible
            return result if isinstance(result, dict) else {"result": str(result)}
