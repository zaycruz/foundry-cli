"""
Ontology service wrappers for Foundry SDK.
"""

import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Union
from urllib.parse import quote

import requests
from foundry_sdk.v2.ontologies.models import ApplyActionRequestOptions

from ..config.settings import Settings
from ..utils.pagination import PaginationConfig, PaginationResult
from .base import BaseService


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

    _MODIFY_ENDPOINT = "/ontology-metadata/api/ontology/v2/modify"
    _NAMESPACE_PROBE_OBJECT_TYPE_ID = "probe.bad-id"
    _ALREADY_EXISTS_ERROR_NAMES = {
        "ObjectTypesAlreadyExistError",
        "ObjectTypesAlreadyExist",
        "objectTypesAlreadyExist",
    }
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
            raise RuntimeError(f"Failed to get object type {object_type}: {e}")

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
    ) -> Dict[str, Any]:
        """Create an object type through the verified modifyOntology contract.

        The internal API requires an ontology-specific namespace in new object
        type IDs. It does not expose that namespace directly, so a dry-run with
        a deliberately invalid ID discovers the namespace regex. The completed
        request is then dry-run validated before the real modification.

        Existing object types are intentionally not updated yet. Foundry's
        create validation is used to detect that case rather than attempting a
        destructive delete-and-recreate.
        """
        from .foundry_internal_client import FoundryInternalClient

        effective_profile = self.profile or self.auth_manager.get_current_profile()
        if not effective_profile:
            from ..auth.base import ProfileNotFoundError

            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'pltr configure configure' to set up authentication."
            )

        client = FoundryInternalClient(profile=effective_profile)
        dry_run_endpoint = (
            f"{self._MODIFY_ENDPOINT}/dry-run"
            f"?ontologyRid={quote(ontology_rid, safe='')}"
        )
        modify_endpoint = (
            f"{self._MODIFY_ENDPOINT}?ontologyRid={quote(ontology_rid, safe='')}"
        )

        probe_request = self._build_object_type_modification_request(
            object_type_id=self._NAMESPACE_PROBE_OBJECT_TYPE_ID,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
        )
        status, parsed, raw = client.conjure(
            "POST",
            dry_run_endpoint,
            json_body={"modificationRequest": probe_request},
            expected=200,
        )
        self._require_successful_internal_response(
            status, parsed, raw, operation="object type namespace discovery"
        )
        namespace = self._extract_object_type_namespace(parsed)

        object_type_id = f"{namespace}.{self._object_type_id_suffix(api_name)}"
        modification_request = self._build_object_type_modification_request(
            object_type_id=object_type_id,
            api_name=api_name,
            display_name=display_name,
            primary_key=primary_key,
            backing_dataset=backing_dataset,
            description=description,
        )
        status, parsed, raw = client.conjure(
            "POST",
            dry_run_endpoint,
            json_body={"modificationRequest": modification_request},
            expected=200,
        )
        self._require_successful_internal_response(
            status, parsed, raw, operation="object type dry-run"
        )
        self._require_successful_dry_run(parsed)

        status, parsed, raw = client.conjure(
            "POST",
            modify_endpoint,
            json_body=modification_request,
            expected=200,
        )
        self._require_successful_internal_response(
            status, parsed, raw, operation="object type modify"
        )
        if not isinstance(parsed, Mapping):
            raise RuntimeError(
                "Object type modify returned an invalid response shape: "
                "expected a JSON object"
            )
        created = parsed.get("createdObjectTypes")
        if not isinstance(created, Mapping) or not isinstance(
            created.get(object_type_id), str
        ):
            raise RuntimeError(
                "Object type modify succeeded but did not return the created "
                f"object type RID for {object_type_id}"
            )

        return {
            "apiName": api_name,
            "objectTypeId": object_type_id,
            "rid": created[object_type_id],
            "ontologyRid": ontology_rid,
        }

    @staticmethod
    def _object_type_id_suffix(api_name: str) -> str:
        """Convert an API name into the lower-kebab ID required by OMS."""
        with_word_boundaries = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", api_name)
        with_word_boundaries = re.sub(
            r"([a-z0-9])([A-Z])", r"\1-\2", with_word_boundaries
        )
        suffix = re.sub(
            r"[^a-z0-9]+", "-", with_word_boundaries.casefold()
        ).strip("-")
        if not suffix or not suffix[0].isalpha():
            raise RuntimeError(
                f"Cannot derive a valid object type ID from API name {api_name!r}; "
                "the derived ID must start with a letter"
            )
        return suffix

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
        for error in cls._dry_run_errors(payload):
            error_data = error.get("errorData")
            if not isinstance(error_data, Mapping):
                continue
            error_name = str(error_data.get("errorName") or "")
            if cls._error_terminal_name(error_name) != "InvalidObjectTypeId":
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

    @classmethod
    def _require_successful_dry_run(cls, payload: Any) -> None:
        """Accept only the explicit dry-run success variant."""
        if isinstance(payload, Mapping) and payload.get("type") == "success":
            return
        errors = cls._dry_run_errors(payload)
        if errors:
            messages = [cls._format_validation_error(error) for error in errors]
            raise RuntimeError(
                "Object type dry-run validation failed: " + "; ".join(messages)
            )
        raise RuntimeError(
            "Object type dry-run returned an invalid response shape: expected "
            "{'type': 'success'} or {'type': 'error', 'error': {'errors': [...]}}"
        )

    @staticmethod
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

    @classmethod
    def _format_validation_error(cls, error: Mapping[str, Any]) -> str:
        error_data = error.get("errorData")
        if not isinstance(error_data, Mapping):
            return "unknown ontology validation error"
        error_name = str(error_data.get("errorName") or "unknown")
        terminal_name = cls._error_terminal_name(error_name)
        if terminal_name in cls._ALREADY_EXISTS_ERROR_NAMES:
            return (
                "object type already exists; update path not yet implemented "
                f"({error_name})"
            )
        messages = {
            "InvalidObjectTypeId": (
                "Foundry rejected the generated object type ID for this "
                "ontology namespace"
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
            "TooManyObjectTypesInOntology": (
                "the ontology has reached its object type limit"
            ),
        }
        mapped = messages.get(terminal_name)
        if mapped:
            return f"{mapped} ({error_name})"
        error_message = error_data.get("errorMessage")
        if isinstance(error_message, str) and error_message:
            return f"{error_name}: {error_message}"
        return error_name

    @staticmethod
    def _error_terminal_name(error_name: str) -> str:
        return error_name.rsplit(":", 1)[-1]

    @staticmethod
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
        error_name = (
            payload.get("errorName") if isinstance(payload, Mapping) else None
        )
        if status == 400:
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"{operation} request failed during contract deserialization "
                f"with HTTP 400{detail}; the modifyOntology request shape was "
                f"rejected before validation: {str(raw)[:300]}"
            )
        detail = f" ({error_name})" if error_name else ""
        raise RuntimeError(
            f"{operation} failed with HTTP {status}{detail}: {str(raw)[:300]}"
        )

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
        contract-verified on a live Foundry deployment. The endpoint is gated behind
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
