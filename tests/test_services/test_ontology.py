"""
Tests for ontology services.
"""

import uuid

import pytest
import requests
from unittest.mock import Mock, patch

from foundry_cli.services.errors import FoundryApiError
from foundry_cli.services.ontology import (
    OntologyService,
    ObjectTypeService,
    OntologyObjectService,
    ActionService,
    QueryService,
)


def _http_error(status_code: int, message: str) -> requests.HTTPError:
    """Create an HTTPError with an attached response status code."""
    error = requests.HTTPError(message)
    error.response = Mock(status_code=status_code)
    return error


@pytest.fixture
def mock_ontology_service():
    """Create a mocked OntologyService."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_ontology_class = Mock()
        mock_ontologies.Ontology = mock_ontology_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service
        service = OntologyService()
        return service, mock_ontology_class


@pytest.fixture
def mock_object_type_service():
    """Create a mocked ObjectTypeService."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_ontology_class = Mock()
        mock_object_type_class = Mock()
        # ObjectType is nested under Ontology in the SDK
        mock_ontology_class.ObjectType = mock_object_type_class
        mock_ontologies.Ontology = mock_ontology_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service
        service = ObjectTypeService()
        return service, mock_object_type_class


@pytest.fixture
def mock_ontology_object_service():
    """Create a mocked OntologyObjectService."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_ontology_object_class = Mock()
        mock_ontologies.OntologyObject = mock_ontology_object_class
        mock_ontologies.LinkedObject = Mock()
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service
        service = OntologyObjectService()
        return service, mock_ontology_object_class


@pytest.fixture
def mock_action_service():
    """Create a mocked ActionService."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_action_class = Mock()
        mock_ontologies.Action = mock_action_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service
        service = ActionService()
        return service, mock_action_class


@pytest.fixture
def mock_query_service():
    """Create a mocked QueryService."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_query_class = Mock()
        mock_ontologies.Query = mock_query_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service
        service = QueryService()
        return service, mock_query_class


@pytest.fixture
def sample_ontology():
    """Create sample ontology object."""
    ontology = Mock()
    ontology.rid = "ri.ontology.main.ontology.test"
    ontology.api_name = "test_ontology"
    ontology.display_name = "Test Ontology"
    ontology.description = "A test ontology"
    return ontology


@pytest.fixture
def sample_object_type():
    """Create sample object type."""
    obj_type = Mock()
    obj_type.api_name = "Employee"
    obj_type.display_name = "Employee"
    obj_type.description = "Employee object type"
    obj_type.primary_key = "employee_id"
    obj_type.properties = {
        "employee_id": {"type": "string"},
        "name": {"type": "string"},
        "department": {"type": "string"},
    }
    return obj_type


@pytest.fixture
def sample_object():
    """Create sample ontology object."""
    return {
        "employee_id": "EMP001",
        "name": "John Doe",
        "department": "Engineering",
        "__primaryKey": "EMP001",
    }


@pytest.fixture
def sample_action_result():
    """Create sample action result."""
    result = Mock()
    result.operation_id = "ri.action.operation.123"
    result.validation = Mock(result="VALID")
    result.edits = Mock(
        type="objectEdits",
        added_object_count=0,
        modified_objects_count=1,
        deleted_objects_count=0,
        added_links_count=0,
        deleted_links_count=0,
        edits=["EMP001"],
    )
    return result


@pytest.fixture
def sample_validation_result():
    """Create sample validation result."""
    result = Mock()
    result.validation = Mock(
        result="VALID",
        submission_criteria=[],
        parameters={},
    )
    return result


@pytest.fixture
def sample_query_result():
    """Create sample query result."""
    result = Mock()
    result.rows = [
        {"employee_id": "EMP001", "name": "John Doe"},
        {"employee_id": "EMP002", "name": "Jane Smith"},
    ]
    result.columns = ["employee_id", "name"]
    return result


# OntologyService Tests
def test_ontology_service_initialization():
    """Test OntologyService initialization."""
    with patch("foundry_cli.services.base.AuthManager"):
        service = OntologyService()
        assert service is not None
        assert service.auth_manager is not None


def test_list_ontologies(mock_ontology_service, sample_ontology):
    """Test listing ontologies."""
    service, mock_ontology_class = mock_ontology_service
    # Mock the response with a 'data' field
    mock_response = Mock()
    mock_response.data = [sample_ontology]
    mock_ontology_class.list.return_value = mock_response

    result = service.list_ontologies()

    assert len(result) == 1
    assert result[0]["rid"] == "ri.ontology.main.ontology.test"
    assert result[0]["api_name"] == "test_ontology"
    mock_ontology_class.list.assert_called_once()


def test_get_ontology(mock_ontology_service, sample_ontology):
    """Test getting a specific ontology."""
    service, mock_ontology_class = mock_ontology_service
    mock_ontology_class.get.return_value = sample_ontology

    result = service.get_ontology("ri.ontology.main.ontology.test")

    assert result["rid"] == "ri.ontology.main.ontology.test"
    assert result["api_name"] == "test_ontology"
    mock_ontology_class.get.assert_called_once_with("ri.ontology.main.ontology.test")


# ObjectTypeService Tests
def test_list_object_types(mock_object_type_service, sample_object_type):
    """Test listing object types."""
    service, mock_object_type_class = mock_object_type_service
    # Mock the response with a 'data' field
    mock_response = Mock()
    mock_response.data = [sample_object_type]
    mock_object_type_class.list.return_value = mock_response

    result = service.list_object_types("ri.ontology.main.ontology.test")

    assert len(result) == 1
    assert result[0]["api_name"] == "Employee"
    assert result[0]["primary_key"] == "employee_id"
    mock_object_type_class.list.assert_called_once_with(
        "ri.ontology.main.ontology.test"
    )


def test_get_object_type(mock_object_type_service, sample_object_type):
    """Test getting a specific object type."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = sample_object_type

    result = service.get_object_type("ri.ontology.main.ontology.test", "Employee")

    assert result["api_name"] == "Employee"
    assert result["primary_key"] == "employee_id"
    mock_object_type_class.get.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee"
    )


def test_create_object_type(mock_object_type_service):
    """Test creating an object type via direct API endpoint."""
    service, _ = mock_object_type_service

    mock_response = Mock()
    mock_response.text = "ok"
    mock_response.json.return_value = {
        "apiName": "ExampleObject",
        "ontologyRid": "ri.ontology.main.ontology.test",
    }

    with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
        result = service.create_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert result["apiName"] == "ExampleObject"
    assert result["ontologyRid"] == "ri.ontology.main.ontology.test"
    mock_req.assert_called_once_with(
        "POST",
        "/v2/ontologies/ri.ontology.main.ontology.test/objectTypes",
        json_data={
            "apiName": "ExampleObject",
            "displayName": "Example Object",
            "primaryKey": "id",
            "backingDatasetRid": "ri.foundry.main.dataset.example",
        },
    )


def test_create_object_type_with_description(mock_object_type_service):
    """Test creating an object type includes description when provided."""
    service, _ = mock_object_type_service

    mock_response = Mock()
    mock_response.text = "ok"
    mock_response.json.return_value = {"apiName": "ExampleObject"}

    with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
        service.create_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            description="Example entity",
        )

    assert mock_req.call_args.kwargs["json_data"]["description"] == "Example entity"


def test_upsert_object_type_dry_run_is_the_default(mock_object_type_service):
    """Without apply, upsert discovers, validates, and stops before modify."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"

    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert result["mode"] == "dry-run"
    assert result["validation"] == {"status": "success", "errors": []}
    assert result["objectTypeId"] == "ns0abcde.example-object"
    assert "rid" not in result
    # Probe + dry-run only; the real modify endpoint is never called.
    assert mock_client.conjure.call_count == 2
    for call in mock_client.conjure.call_args_list:
        assert "/modify/dry-run" in call.args[1]


def test_upsert_object_type_maps_primary_key_to_explicit_backing_column(
    mock_object_type_service,
):
    """A normalized primary-key API name may map to a physical source column."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="facility_id",
            backing_dataset="ri.foundry.main.dataset.example",
            primary_key_backing_column="FACILITY_ID",
        )

    assert result["primaryKeyBackingColumn"] == "FACILITY_ID"
    request = mock_client.conjure.call_args_list[1].kwargs["json_body"]
    datasource = request["modificationRequest"]["objectTypeDatasources"]
    mapping = datasource["ns0abcde.example-object"][0]["create"]
    mapping = mapping["objectTypeDatasourceDefinition"]["dataset"]["propertyMapping"]
    assert mapping == {"facility_id": "FACILITY_ID"}


def test_upsert_object_type_apply_verifies_read_back(mock_object_type_service):
    """Applied upserts modify and then read the object type back via SDK."""
    service, mock_object_type_class = mock_object_type_service
    service.profile = "test-profile"

    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (
            200,
            {
                "createdObjectTypes": {
                    "ns0abcde.example-object": (
                        "ri.ontology.main.object-type.example-object"
                    )
                }
            },
            '{"createdObjectTypes":{}}',
        ),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            description="Example entity",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["apiName"] == "ExampleObject"
    assert result["objectTypeId"] == "ns0abcde.example-object"
    assert result["rid"] == "ri.ontology.main.object-type.example-object"
    assert result["ontologyRid"] == "ri.ontology.main.ontology.test"
    assert result["verification"]["status"] == "verified"
    assert mock_client.conjure.call_count == 3
    # SDK read-back verification hit the mocked ObjectType.get.
    mock_object_type_class.get.assert_called_once_with(
        "ri.ontology.main.ontology.test", "ExampleObject"
    )

    probe_call, dry_run_call, modify_call = mock_client.conjure.call_args_list
    expected_dry_run_path = (
        "/ontology-metadata/api/ontology/v2/modify/dry-run"
        "?ontologyRid=ri.ontology.main.ontology.test"
    )
    expected_modify_path = (
        "/ontology-metadata/api/ontology/v2/modify"
        "?ontologyRid=ri.ontology.main.ontology.test"
    )
    assert probe_call.args[:2] == ("POST", expected_dry_run_path)
    assert dry_run_call.args[:2] == ("POST", expected_dry_run_path)
    assert modify_call.args[:2] == ("POST", expected_modify_path)

    probe_request = probe_call.kwargs["json_body"]["modificationRequest"]
    assert "probe.bad-id" in probe_request["objectTypes"]

    modification_request = dry_run_call.kwargs["json_body"]["modificationRequest"]
    object_type_id = "ns0abcde.example-object"
    object_type = modification_request["objectTypes"][object_type_id]["create"][
        "objectType"
    ]
    assert object_type["apiName"] == "ExampleObject"
    assert object_type["displayMetadata"]["description"] == "Example entity"
    assert (
        object_type["propertyTypes"]["id"]["type"]["string"]["supportsExactMatching"]
        is False
    )
    assert modification_request["objectTypeEntityMetadata"][object_type_id] == {
        "targetStorageBackend": {
            "type": "objectStorageV2",
            "objectStorageV2": {},
        }
    }
    assert modification_request["objectTypeDatasources"][object_type_id][0]["create"][
        "objectTypeDatasourceDefinition"
    ] == {
        "type": "dataset",
        "dataset": {
            "datasetRid": "ri.foundry.main.dataset.example",
            "propertyMapping": {"id": "id"},
        },
    }
    assert modify_call.kwargs["json_body"] == modification_request


def test_upsert_object_type_apply_reports_unverified_read_back(
    mock_object_type_service,
):
    """A failed read-back is reported honestly, not hidden."""
    service, mock_object_type_class = mock_object_type_service
    service.profile = "test-profile"
    mock_object_type_class.get.side_effect = RuntimeError("not found")

    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (
            200,
            {"createdObjectTypes": {"ns0abcde.example-object": "ri.x"}},
            "{}",
        ),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["verification"]["status"] == "not-verified"
    assert "read-back" in result["verification"]["detail"]


def _namespace_probe_response() -> tuple[int, dict, str]:
    return (
        200,
        {
            "type": "error",
            "error": {
                "errors": [
                    {
                        "errorData": {
                            "errorName": "OntologyMetadata:InvalidObjectTypeId",
                            "safeArgs": [
                                {
                                    "name": "regex",
                                    "value": r"^ns0abcde\.([a-z][a-z0-9\-]*)",
                                }
                            ],
                        }
                    }
                ]
            },
        },
        '{"type":"error"}',
    )


def _validation_error_response(error_name: str) -> tuple[int, dict, str]:
    return (
        200,
        {
            "type": "error",
            "error": {
                "errors": [
                    {
                        "errorData": {
                            "errorName": f"OntologyMetadata:{error_name}",
                            "errorMessage": error_name,
                            "safeArgs": [],
                        }
                    }
                ]
            },
        },
        '{"type":"error"}',
    )


def _bulk_load_response(
    display_name: str = "Example Object",
    description: str | None = None,
    primary_key: str = "id",
    dataset_rid: str = "ri.foundry.main.dataset.example",
) -> tuple[int, dict, str]:
    """Loaded-state response mirroring bulkLoadEntities against a live deployment."""
    property_rid = "ri.ontology.main.property.id"
    display_metadata: dict = {
        "displayName": display_name,
        "pluralDisplayName": display_name,
        "icon": {
            "type": "blueprint",
            "blueprint": {"color": "#4C90F0", "locator": "cube"},
        },
        "visibility": "NORMAL",
    }
    if description is not None:
        display_metadata["description"] = description
    entry = {
        "objectType": {
            "id": "ns0abcde.example-object",
            "apiName": "ExampleObject",
            "rid": "ri.ontology.main.object-type.example-object",
            "displayMetadata": display_metadata,
            "implementsInterfaces": [],
            "implementsInterfaces2": [],
            "primaryKeys": [property_rid],
            "propertyTypes": {
                property_rid: {
                    "rid": property_rid,
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
                    "status": {"type": "active", "active": {}},
                }
            },
            "titlePropertyTypeRid": property_rid,
            "traits": {"workflowObjectTypeTraits": {}},
            "typeGroups": [],
            "status": {"type": "active", "active": {}},
        },
        "datasources": [
            {
                "rid": "ri.ontology.main.datasource.tm",
                "datasource": {
                    "type": "dataset",
                    "dataset": {
                        "branchId": "master",
                        "datasetRid": dataset_rid,
                        "propertyMapping": {property_rid: primary_key},
                    },
                },
            }
        ],
        "entityMetadata": None,
    }
    return (200, {"objectTypes": [entry]}, "[]")


def test_upsert_object_type_dry_run_plans_update_for_existing_type(
    mock_object_type_service,
):
    """An existing type produces a validated update plan, not a refusal."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object v2",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            description="updated description",
        )

    assert result["mode"] == "dry-run"
    assert result["upsertMode"] == "update"
    assert result["changedFields"] == ["displayName", "description"]
    merged = result["update"]["objectType"]
    assert merged["id"] == "ns0abcde.example-object"
    assert merged["displayMetadata"]["displayName"] == "Example Object v2"
    assert merged["displayMetadata"]["pluralDisplayName"] == "Example Object v2"
    assert merged["displayMetadata"]["description"] == "updated description"
    # Loaded state carried over: rids became PropertyTypeIds, type kept.
    assert merged["primaryKeys"] == ["id"]
    assert merged["titlePropertyTypeId"] == "id"
    assert merged["propertyTypes"]["id"]["type"]["string"] == {
        "isLongText": False,
        "supportsExactMatching": False,
    }
    assert merged["traits"] == {"workflowObjectTypeTraits": {}}
    assert result["validation"] == {"status": "success", "errors": []}
    # Probe + create dry-run + load + update dry-run; never real modify.
    assert mock_client.conjure.call_count == 4
    paths = [call.args[1] for call in mock_client.conjure.call_args_list]
    assert "/ontology/ontology/bulkLoadEntities" in paths[2]
    assert all("/modify?" not in path for path in paths)
    update_dry_run = mock_client.conjure.call_args_list[3]
    update_body = update_dry_run.kwargs["json_body"]["modificationRequest"]
    update_variant = update_body["objectTypes"]["ns0abcde.example-object"]
    assert update_variant["type"] == "update"
    assert update_variant["update"]["objectType"] == merged


def test_upsert_object_type_apply_updates_existing_type(
    mock_object_type_service,
):
    """With apply, the merged update modification is issued and verified."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object v2",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            description="updated description",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["upsertMode"] == "update"
    assert result["changed"] is True
    assert result["changedFields"] == ["displayName", "description"]
    assert result["rid"] == "ri.ontology.main.object-type.example-object"
    assert result["verification"]["status"] == "verified"
    modify_call = mock_client.conjure.call_args_list[4]
    assert "/modify?" in modify_call.args[1]
    body = modify_call.kwargs["json_body"]
    variant = body["objectTypes"]["ns0abcde.example-object"]
    assert variant["type"] == "update"
    assert (
        variant["update"]["objectType"]["displayMetadata"]["displayName"]
        == "Example Object v2"
    )


def test_upsert_object_type_update_fails_when_state_cannot_load(
    mock_object_type_service,
):
    """A missing load entry fails loudly; nothing is guessed or recreated."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        (200, {"objectTypes": [None]}, '{"objectTypes":[null]}'),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="Could not load the current state"),
    ):
        service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object v2",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert mock_client.conjure.call_count == 3


def test_upsert_object_type_update_noop_skips_modify(mock_object_type_service):
    """Identical fields validate but skip the real modification."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["upsertMode"] == "update"
    assert result["changed"] is False
    assert result["changedFields"] == []
    assert result["verification"]["status"] == "skipped"
    # No fifth call: the real modify endpoint was never hit.
    assert mock_client.conjure.call_count == 4
    for call in mock_client.conjure.call_args_list:
        assert "/modify?" not in call.args[1]


def test_upsert_object_type_update_refuses_backing_dataset_change(
    mock_object_type_service,
):
    """A different backing dataset is refused, not silently dropped."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        _bulk_load_response(dataset_rid="ri.foundry.main.dataset.other"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="cannot change the backing dataset"),
    ):
        service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object v2",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )


def test_upsert_object_type_update_refuses_primary_key_change(
    mock_object_type_service,
):
    """A different primary key is refused, not silently dropped."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesAlreadyExistError"),
        _bulk_load_response(),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="cannot change the primary key"),
    ):
        service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object v2",
            primary_key="tail_number",
            backing_dataset="ri.foundry.main.dataset.example",
        )


def test_upsert_object_type_surfaces_missing_dataset_schema(
    mock_object_type_service,
):
    """Dataset schema validation tells the operator how to unblock creation."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("SchemaForObjectTypeDatasourceNotFound"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(
            RuntimeError,
            match="backing dataset has no schema; apply a schema",
        ),
    ):
        service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
            apply=True,
        )

    assert mock_client.conjure.call_count == 2


# Object type delete tests
def test_delete_object_type_rejects_api_name(mock_object_type_service):
    """Deletes require the internal ObjectTypeId, not an API name."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"

    with pytest.raises(RuntimeError, match="internal ObjectTypeId"):
        service.delete_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type_id="ExampleObject",
        )


def test_delete_object_type_dry_run_is_the_default(mock_object_type_service):
    """Without apply, a delete validates and returns the plan only."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.delete_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type_id="ns0abcde.example-object",
        )

    assert result["mode"] == "dry-run"
    assert result["validation"] == {"status": "success", "errors": []}
    assert mock_client.conjure.call_count == 1
    body = mock_client.conjure.call_args.kwargs["json_body"]
    assert body == {
        "modificationRequest": {
            "objectTypes": {"ns0abcde.example-object": {"type": "delete", "delete": {}}}
        }
    }
    assert "/modify/dry-run" in mock_client.conjure.call_args.args[1]


def test_delete_object_type_apply_verifies_gone(mock_object_type_service):
    """An applied delete is verified by a post-delete dry-run NotFound."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
        _validation_error_response("ObjectTypesNotFound"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.delete_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type_id="ns0abcde.example-object",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["verification"]["status"] == "verified"
    calls = mock_client.conjure.call_args_list
    assert "/modify/dry-run" in calls[0].args[1]
    assert (
        calls[1].args[1].endswith("/modify?ontologyRid=ri.ontology.main.ontology.test")
    )
    assert calls[1].kwargs["json_body"] == {
        "objectTypes": {"ns0abcde.example-object": {"type": "delete", "delete": {}}}
    }
    assert "/modify/dry-run" in calls[2].args[1]


def test_delete_object_type_apply_reports_still_present(mock_object_type_service):
    """A delete whose dry-run still validates is reported as not verified."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.delete_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type_id="ns0abcde.example-object",
            apply=True,
        )

    assert result["verification"]["status"] == "not-verified"
    assert "may not be deleted" in result["verification"]["detail"]


# Link type upsert/delete tests
def test_upsert_link_type_builds_verified_one_to_many_shape(
    mock_object_type_service,
):
    """Link upsert dry-run sends the contract oneToMany create variant."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="exampleObjectOwner",
            one_side_object_type_id="ns0abcde.example-owner",
            many_side_object_type_id="ns0abcde.example-object",
            display_name="Example owner",
            one_side_primary_key="owner_id",
            many_side_property="owner_ref",
        )

    assert result["mode"] == "dry-run"
    assert result["linkTypeId"] == "ns0abcde.example-object-owner"
    modification_request = mock_client.conjure.call_args_list[1].kwargs["json_body"][
        "modificationRequest"
    ]
    create = modification_request["linkTypes"]["ns0abcde.example-object-owner"][
        "create"
    ]
    link_type = create["linkType"]
    assert link_type["linkTypeId"] == "ns0abcde.example-object-owner"
    one_to_many = link_type["definition"]["oneToMany"]
    assert one_to_many["cardinalityHint"] == "ONE_TO_MANY"
    assert one_to_many["objectTypeIdOneSide"] == "ns0abcde.example-owner"
    assert one_to_many["objectTypeIdManySide"] == "ns0abcde.example-object"
    assert one_to_many["oneSidePrimaryKeyToManySidePropertyMapping"] == {
        "owner_id": "owner_ref"
    }
    assert one_to_many["oneToManyLinkMetadata"]["apiName"] == "exampleObjectOwner"
    assert (
        one_to_many["manyToOneLinkMetadata"]["apiName"] == "exampleObjectOwnerReverse"
    )
    assert create["markings"] == []


def test_upsert_link_type_apply_verifies_via_dry_run(mock_object_type_service):
    """An applied link create is verified by an already-exists re-dry-run."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (
            200,
            {"createdLinkTypes": {"ns0abcde.tm-link": "ri.ontology.main.link-type.x"}},
            "{}",
        ),
        _validation_error_response("LinkTypesAlreadyExistError"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="tmLink",
            one_side_object_type_id="ns0abcde.example-owner",
            many_side_object_type_id="ns0abcde.example-object",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["rid"] == "ri.ontology.main.link-type.x"
    assert result["verification"]["status"] == "verified"
    assert mock_client.conjure.call_count == 4


def test_delete_link_type_apply_verifies_gone(mock_object_type_service):
    """Link delete uses the linkTypes delete variant and NotFound read-back."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
        _validation_error_response("LinkTypesNotFound"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.delete_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            link_type_id="ns0abcde.tm-link",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["verification"]["status"] == "verified"
    modify_call = mock_client.conjure.call_args_list[1]
    assert modify_call.kwargs["json_body"] == {
        "linkTypes": {"ns0abcde.tm-link": {"type": "delete", "delete": {}}}
    }


def test_delete_link_type_rejects_api_name(mock_object_type_service):
    """Link deletes require the internal LinkTypeId, not an API name."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"

    with pytest.raises(RuntimeError, match="internal LinkTypeId"):
        service.delete_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            link_type_id="tmLink",
        )


# Action type upsert/delete tests
def _action_type_definition() -> dict:
    return {
        "apiName": "foundry-test-action",
        "displayMetadata": {"displayName": "FOUNDRY Test"},
        "logic": {
            "rules": [
                {
                    "type": "deleteObjectRule",
                    "deleteObjectRule": {"objectToDelete": "Contact"},
                }
            ]
        },
        "parameters": {},
        "validations": {
            "always": {
                "condition": {"type": "true", "true": {}},
                "displayMetadata": {"failureMessage": "x", "typeClasses": []},
            }
        },
        "validationsOrdering": ["always"],
    }


def test_action_type_create_normalization_rewrites_validation_keys():
    """Non-UUID validations keys are rewritten and ordering kept in sync."""
    create = ActionService._normalize_action_type_create(_action_type_definition())

    assert create["apiName"] == "foundry-test-action"
    (new_key,) = create["validations"].keys()
    assert new_key != "always"
    uuid.UUID(new_key)  # raises if not a UUID
    assert create["validationsOrdering"] == [new_key]


def test_action_type_create_normalization_keeps_uuid_keys():
    """Already-UUID validations keys pass through unchanged."""
    definition = _action_type_definition()
    uuid_key = "00000000-0000-0000-0000-0000000000d1"
    definition["validations"] = {uuid_key: definition["validations"]["always"]}
    definition["validationsOrdering"] = [uuid_key]

    create = ActionService._normalize_action_type_create(definition)

    assert list(create["validations"]) == [uuid_key]
    assert create["validationsOrdering"] == [uuid_key]


@pytest.mark.parametrize("missing_key", ["apiName", "logic", "validations"])
def test_action_type_create_normalization_requires_fields(missing_key):
    """Required ActionTypeCreate fields are validated client-side."""
    definition = _action_type_definition()
    del definition[missing_key]

    with pytest.raises(RuntimeError, match=missing_key):
        ActionService._normalize_action_type_create(definition)


def test_upsert_action_type_dry_run_is_the_default(mock_action_service):
    """Dry-run sends the council-approved create envelope and stops before modify."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    validation_id = uuid.UUID("00000000-0000-0000-0000-0000000000d2")
    request_id = uuid.UUID("00000000-0000-0000-0000-0000000000d3")
    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch(
            "foundry_cli.services.ontology.uuid.uuid4",
            side_effect=[validation_id, request_id],
        ),
    ):
        result = service.upsert_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            definition=_action_type_definition(),
        )

    assert result["mode"] == "dry-run"
    assert result["apiName"] == "foundry-test-action"
    modification_request = mock_client.conjure.call_args.kwargs["json_body"]["modificationRequest"]
    expected = _action_type_definition()
    expected.pop("apiName")
    expected["validations"] = {str(validation_id): expected["validations"].pop("always")}
    expected["validationsOrdering"] = [str(validation_id)]
    assert modification_request == {
        "actionTypesToCreate": {
            "foundry-test-action": {
                "id": str(request_id),
                "definition": expected,
            }
        }
    }
    assert "apiName" not in modification_request["actionTypesToCreate"][
        "foundry-test-action"
    ]["definition"]
    assert mock_client.conjure.call_count == 1


def test_upsert_action_type_apply_verifies_read_back(mock_action_service):
    """Apply is rejected before the real modify endpoint can be reached."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(FoundryApiError, match="unverified contract"),
    ):
        service.upsert_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            definition=_action_type_definition(),
            apply=True,
        )

    mock_client.conjure.assert_not_called()


def test_delete_action_type_resolves_rid_and_verifies_gone(mock_action_service):
    """Action delete resolves the RID, modifies, and verifies via NotFound."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    rid = "ri.actions.main.action-type.abc"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
        _validation_error_response("ActionTypesNotFound"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(ActionService, "get_action_type", return_value={"rid": rid}),
    ):
        result = service.delete_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="foundry-test-action",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["rid"] == rid
    assert result["verification"]["status"] == "verified"
    modify_call = mock_client.conjure.call_args_list[1]
    assert modify_call.kwargs["json_body"] == {"actionTypesToDelete": [rid]}


def test_delete_action_type_missing_type_raises(mock_action_service):
    """A missing action type fails before any modification is attempted."""
    service, _ = mock_action_service
    service.profile = "test-profile"

    with (
        patch.object(
            ActionService,
            "get_action_type",
            side_effect=RuntimeError("Failed to get action type"),
        ),
        pytest.raises(RuntimeError, match="Failed to get action type"),
    ):
        service.delete_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="does-not-exist",
        )


def test_create_link_type(mock_object_type_service):
    """Test creating a link type via direct API endpoint."""
    service, _ = mock_object_type_service

    mock_response = Mock()
    mock_response.text = "ok"
    mock_response.json.return_value = {
        "apiName": "exampleLink",
        "ontologyRid": "ri.ontology.main.ontology.test",
    }

    with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
        result = service.create_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="exampleLink",
            from_object_type="ExampleObject",
            to_object_type="ExampleAgreement",
            reverse_api_name="linkExample",
        )

    assert result["apiName"] == "exampleLink"
    assert result["ontologyRid"] == "ri.ontology.main.ontology.test"
    mock_req.assert_called_once_with(
        "POST",
        "/v2/ontologies/ri.ontology.main.ontology.test/linkTypes",
        json_data={
            "apiName": "exampleLink",
            "fromObjectTypeApiName": "ExampleObject",
            "toObjectTypeApiName": "ExampleAgreement",
            "reverseApiName": "linkExample",
        },
    )


def test_create_object_type_fallback_endpoint(mock_object_type_service):
    """Test object type creation fallback across endpoint variants."""
    service, _ = mock_object_type_service

    mock_response = Mock()
    mock_response.text = ""

    with patch.object(
        service,
        "_make_request",
        side_effect=[_http_error(404, "not found"), mock_response],
    ) as mock_req:
        result = service.create_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert result["apiName"] == "ExampleObject"
    assert result["ontologyRid"] == "ri.ontology.main.ontology.test"
    assert mock_req.call_count == 2


def test_create_object_type_non_404_does_not_fallback(mock_object_type_service):
    """Test non-404 errors fail immediately instead of trying all endpoints."""
    service, _ = mock_object_type_service

    with patch.object(
        service, "_make_request", side_effect=_http_error(403, "forbidden")
    ) as mock_req:
        with pytest.raises(
            RuntimeError, match="Failed to create object type ExampleObject"
        ):
            service.create_object_type(
                ontology_rid="ri.ontology.main.ontology.test",
                api_name="ExampleObject",
                display_name="Example Object",
                primary_key="id",
                backing_dataset="ri.foundry.main.dataset.example",
            )

    assert mock_req.call_count == 1


def test_create_object_type_all_endpoints_fail(mock_object_type_service):
    """Test object type creation failure after exhausting fallback endpoints."""
    service, _ = mock_object_type_service

    with patch.object(
        service,
        "_make_request",
        side_effect=[
            _http_error(404, "not found"),
            _http_error(404, "not found"),
            _http_error(404, "not found"),
        ],
    ):
        with pytest.raises(
            RuntimeError, match="Failed to create object type ExampleObject"
        ):
            service.create_object_type(
                ontology_rid="ri.ontology.main.ontology.test",
                api_name="ExampleObject",
                display_name="Example Object",
                primary_key="id",
                backing_dataset="ri.foundry.main.dataset.example",
            )


def test_create_link_type_fallback_uses_legacy_payload(mock_object_type_service):
    """Test link type fallback uses legacy payload fields for legacy endpoints."""
    service, _ = mock_object_type_service

    mock_response = Mock()
    mock_response.text = "ok"
    mock_response.json.return_value = {"apiName": "exampleLink"}

    with patch.object(
        service,
        "_make_request",
        side_effect=[_http_error(404, "not found"), mock_response],
    ) as mock_req:
        service.create_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="exampleLink",
            from_object_type="ExampleObject",
            to_object_type="ExampleAgreement",
            reverse_api_name="linkExample",
        )

    fallback_payload = mock_req.call_args_list[-1].kwargs["json_data"]
    assert "linkTypeApiNameAtoB" in fallback_payload
    assert "aSideObjectTypeApiName" in fallback_payload
    assert "fromObjectTypeApiName" not in fallback_payload


# OntologyObjectService Tests
def test_list_objects(mock_ontology_object_service, sample_object):
    """Test listing objects."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_ontology_object_class.list.return_value = [sample_object]

    result = service.list_objects("ri.ontology.main.ontology.test", "Employee")

    assert len(result) == 1
    assert result[0]["employee_id"] == "EMP001"
    assert result[0]["name"] == "John Doe"
    assert result[0]["department"] == "Engineering"
    assert result[0]["__primaryKey"] == "EMP001"
    mock_ontology_object_class.list.assert_called_once()


def test_get_object():
    """Test getting a specific object."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        # Set up client mock
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_ontology_object_class = Mock()

        mock_obj = {
            "employee_id": "EMP001",
            "name": "John Doe",
            "department": "Engineering",
            "__primaryKey": "EMP001",
        }

        mock_ontology_object_class.get.return_value = mock_obj
        mock_ontologies.OntologyObject = mock_ontology_object_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        # Create service and test
        service = OntologyObjectService()
        result = service.get_object(
            "ri.ontology.main.ontology.test", "Employee", "EMP001"
        )

        assert result["employee_id"] == "EMP001"
        assert result["name"] == "John Doe"
        assert result["department"] == "Engineering"
        assert result["__primaryKey"] == "EMP001"
        mock_ontology_object_class.get.assert_called_once()


def test_aggregate_objects(mock_ontology_object_service):
    """Test aggregating objects."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_result = {"count": 10, "avg_salary": 75000}
    mock_ontology_object_class.aggregate.return_value = mock_result

    aggregations = [{"type": "count"}, {"type": "avg", "field": "salary"}]
    result = service.aggregate_objects(
        "ri.ontology.main.ontology.test", "Employee", aggregations
    )

    assert result["count"] == 10
    assert result["avg_salary"] == 75000
    mock_ontology_object_class.aggregate.assert_called_once()


def test_list_linked_objects(mock_ontology_object_service, sample_object):
    """Test listing linked objects."""
    service, _ = mock_ontology_object_service
    mock_linked_object_class = service.service.LinkedObject
    mock_linked_object_class.list_linked_objects.return_value = [sample_object]

    result = service.list_linked_objects(
        "ri.ontology.main.ontology.test",
        "Employee",
        "EMP001",
        "manages",
    )

    assert len(result) == 1
    assert result[0]["employee_id"] == "EMP001"
    mock_linked_object_class.list_linked_objects.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "Employee",
        "EMP001",
        "manages",
        page_size=None,
        select=None,
    )


def test_count_objects(mock_ontology_object_service):
    """Test counting objects."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_ontology_object_class.count.return_value = Mock(count=42)

    result = service.count_objects("ri.ontology.main.ontology.test", "Employee")

    assert result["count"] == 42
    assert result["ontology_rid"] == "ri.ontology.main.ontology.test"
    assert result["object_type"] == "Employee"
    assert result["branch"] is None
    mock_ontology_object_class.count.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", branch=None, preview=True
    )


def test_count_objects_with_branch(mock_ontology_object_service):
    """Test counting objects with branch specified."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_ontology_object_class.count.return_value = Mock(count=24)

    result = service.count_objects(
        "ri.ontology.main.ontology.test", "Employee", branch="master"
    )

    assert result["count"] == 24
    assert result["branch"] == "master"
    mock_ontology_object_class.count.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", branch="master", preview=True
    )


def test_search_objects(mock_ontology_object_service, sample_object):
    """Test searching objects."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_ontology_object_class.search.return_value = [sample_object]

    result = service.search_objects(
        "ri.ontology.main.ontology.test", "Employee", "John"
    )

    assert len(result) == 1
    assert result[0]["employee_id"] == "EMP001"
    assert result[0]["name"] == "John Doe"
    mock_ontology_object_class.search.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "Employee",
        query="John",
        page_size=None,
        select=None,
        branch=None,
    )


def test_search_objects_with_options(mock_ontology_object_service, sample_object):
    """Test searching objects with all options."""
    service, mock_ontology_object_class = mock_ontology_object_service
    mock_ontology_object_class.search.return_value = [sample_object]

    result = service.search_objects(
        "ri.ontology.main.ontology.test",
        "Employee",
        "Jane",
        page_size=10,
        properties=["name", "department"],
        branch="master",
    )

    assert len(result) == 1
    mock_ontology_object_class.search.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "Employee",
        query="Jane",
        page_size=10,
        select=["name", "department"],
        branch="master",
    )


# ActionService Tests
def test_apply_action(mock_action_service, sample_action_result):
    """Test applying an action."""
    service, mock_action_class = mock_action_service
    mock_action_class.apply.return_value = sample_action_result

    params = {"employee_id": "EMP001", "new_department": "Sales"}
    result = service.apply_action(
        "ri.ontology.main.ontology.test", "transfer_employee", params
    )

    assert result["operation_id"] == "ri.action.operation.123"
    assert result["validation_result"] == "VALID"
    assert result["modified_objects_count"] == 1
    mock_action_class.apply.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "transfer_employee",
        parameters=params,
    )


def test_validate_action(mock_action_service, sample_validation_result):
    """Test validating an action."""
    service, mock_action_class = mock_action_service
    mock_action_class.apply.return_value = sample_validation_result

    params = {"employee_id": "EMP001", "new_department": "Sales"}
    result = service.validate_action(
        "ri.ontology.main.ontology.test", "transfer_employee", params
    )

    assert result["result"] == "VALID"
    assert result["submission_criteria"] == []
    assert result["parameters"] == {}
    mock_action_class.apply.assert_called_once()
    call = mock_action_class.apply.call_args
    assert call.args == (
        "ri.ontology.main.ontology.test",
        "transfer_employee",
    )
    assert call.kwargs["parameters"] == params
    assert call.kwargs["options"].mode == "VALIDATE_ONLY"


def test_apply_batch_actions(mock_action_service, sample_action_result):
    """Test applying batch actions."""
    service, mock_action_class = mock_action_service
    batch_result = Mock(edits=sample_action_result.edits)
    mock_action_class.apply_batch.return_value = batch_result

    requests = [
        {"employee_id": "EMP001", "new_department": "Sales"},
        {"employee_id": "EMP002", "new_department": "Marketing"},
    ]
    result = service.apply_batch_actions(
        "ri.ontology.main.ontology.test", "transfer_employee", requests
    )

    assert result["modified_objects_count"] == 1
    assert result["edits"] == ["EMP001"]
    mock_action_class.apply_batch.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "transfer_employee",
        requests=[
            {"parameters": requests[0]},
            {"parameters": requests[1]},
        ],
    )


def test_apply_batch_actions_exceeds_limit(mock_action_service):
    """Test that batch actions fail when exceeding limit."""
    service, _ = mock_action_service

    # Create 21 requests (exceeds limit of 20)
    requests = [{"employee_id": f"EMP{i}"} for i in range(21)]

    with pytest.raises(RuntimeError) as excinfo:
        service.apply_batch_actions(
            "ri.ontology.main.ontology.test", "transfer_employee", requests
        )

    assert "Maximum 20 actions" in str(excinfo.value)


# QueryService Tests
def test_execute_query(mock_query_service, sample_query_result):
    """Test executing a query."""
    service, mock_query_class = mock_query_service
    mock_query_class.execute.return_value = sample_query_result

    params = {"department": "Engineering"}
    result = service.execute_query(
        "ri.ontology.main.ontology.test", "get_employees_by_dept", params
    )

    assert len(result["rows"]) == 2
    assert result["columns"] == ["employee_id", "name"]
    mock_query_class.execute.assert_called_once()


def test_execute_query_with_objects_result(mock_query_service):
    """Test executing a query that returns objects."""
    service, mock_query_class = mock_query_service
    # Create a mock with spec to control attributes
    mock_result = Mock(spec=["objects"])
    mock_result.objects = [{"id": "1", "name": "Test"}]
    mock_query_class.execute.return_value = mock_result

    result = service.execute_query("ri.ontology.main.ontology.test", "get_all_objects")

    assert "objects" in result
    assert len(result["objects"]) == 1
    mock_query_class.execute.assert_called_once()


# Ontology RID resolution tests
def test_get_ontology_rid_single(mock_ontology_service, sample_ontology):
    """Test resolving the ontology RID when exactly one ontology is visible."""
    service, mock_ontology_class = mock_ontology_service
    mock_response = Mock()
    mock_response.data = [sample_ontology]
    mock_ontology_class.list.return_value = mock_response

    result = service.get_ontology_rid()

    assert result["rid"] == "ri.ontology.main.ontology.test"
    assert result["api_name"] == "test_ontology"
    mock_ontology_class.list.assert_called_once()


def test_get_ontology_rid_none_visible(mock_ontology_service):
    """Test that resolving with zero visible ontologies raises."""
    service, mock_ontology_class = mock_ontology_service
    mock_response = Mock()
    mock_response.data = []
    mock_ontology_class.list.return_value = mock_response

    with pytest.raises(RuntimeError, match="No ontologies are visible"):
        service.get_ontology_rid()


def test_get_ontology_rid_multiple_visible(mock_ontology_service, sample_ontology):
    """Test that resolving with multiple visible ontologies raises."""
    service, mock_ontology_class = mock_ontology_service
    other = Mock()
    other.rid = "ri.ontology.main.ontology.other"
    other.api_name = "other_ontology"
    other.display_name = "Other Ontology"
    other.description = None
    mock_response = Mock()
    mock_response.data = [sample_ontology, other]
    mock_ontology_class.list.return_value = mock_response

    with pytest.raises(RuntimeError, match="Multiple ontologies are visible"):
        service.get_ontology_rid()


def test_get_ontology_rid_list_failure(mock_ontology_service):
    """Test that an SDK list failure surfaces as a RuntimeError."""
    service, mock_ontology_class = mock_ontology_service
    mock_ontology_class.list.side_effect = Exception("connection refused")

    with pytest.raises(RuntimeError, match="Failed to list ontologies"):
        service.get_ontology_rid()


# Link type get tests
def test_get_link_type(mock_object_type_service):
    """Test getting a specific outgoing link type."""
    service, mock_object_type_class = mock_object_type_service
    link_type = Mock()
    link_type.link_type_rid = "ri.ontology.main.link-type.abc123"
    link_type.api_name = "worksAt"
    link_type.display_name = "Works At"
    link_type.status = "ACTIVE"
    link_type.object_type_api_name = "Employee"
    link_type.cardinality = "MANY_TO_ONE"
    link_type.foreign_key_property_api_name = "company_id"
    mock_object_type_class.get_outgoing_link_type.return_value = link_type

    result = service.get_link_type(
        "ri.ontology.main.ontology.test", "Employee", "worksAt"
    )

    assert result["rid"] == "ri.ontology.main.link-type.abc123"
    assert result["api_name"] == "worksAt"
    assert result["object_type"] == "Employee"
    assert result["cardinality"] == "MANY_TO_ONE"
    assert result["foreign_key_property"] == "company_id"
    mock_object_type_class.get_outgoing_link_type.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", "worksAt"
    )


def test_get_link_type_error(mock_object_type_service):
    """Test error handling in get_link_type."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get_outgoing_link_type.side_effect = Exception(
        "Link type not found"
    )

    with pytest.raises(RuntimeError, match="Failed to get link type worksAt"):
        service.get_link_type("ri.ontology.main.ontology.test", "Employee", "worksAt")


# Action type get tests (view_foundry_action_type)
@pytest.fixture
def mock_action_type_full_metadata_service():
    """Create a mocked ActionService with an ActionTypeFullMetadata client."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        mock_client = Mock()
        mock_ontologies = Mock()
        mock_metadata_class = Mock()
        mock_ontologies.ActionTypeFullMetadata = mock_metadata_class
        mock_client.ontologies = mock_ontologies
        mock_auth.return_value.get_client.return_value = mock_client

        service = ActionService()
        return service, mock_metadata_class


def _sample_action_type_metadata():
    action_type = Mock()
    action_type.rid = "ri.actions.main.action-type.00000000-0000-0000-0000-000000000001"
    action_type.api_name = "modify-example"
    action_type.display_name = "Modify Example"
    action_type.description = "Modify an example"
    action_type.status = "EXPERIMENTAL"
    action_type.tool_description = None
    action_type.parameters = {"example": Mock(), "notes": Mock()}
    action_type.operations = [Mock()]
    metadata = Mock()
    metadata.action_type = action_type
    metadata.full_logic_rules = [Mock()]
    return metadata


def test_get_action_type(mock_action_type_full_metadata_service):
    """Test getting full metadata for an action type."""
    service, mock_metadata_class = mock_action_type_full_metadata_service
    mock_metadata_class.get.return_value = _sample_action_type_metadata()

    result = service.get_action_type("ri.ontology.main.ontology.test", "modify-example")

    assert result["rid"].startswith("ri.actions.main.action-type.")
    assert result["api_name"] == "modify-example"
    assert result["display_name"] == "Modify Example"
    assert result["status"] == "EXPERIMENTAL"
    assert result["parameters"] == ["example", "notes"]
    assert result["operations_count"] == 1
    assert result["logic_rules_count"] == 1
    mock_metadata_class.get.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "modify-example",
        branch=None,
        preview=True,
    )


def test_get_action_type_with_branch(mock_action_type_full_metadata_service):
    """Test getting an action type from a specific branch."""
    service, mock_metadata_class = mock_action_type_full_metadata_service
    mock_metadata_class.get.return_value = _sample_action_type_metadata()

    service.get_action_type(
        "ri.ontology.main.ontology.test", "modify-example", branch="feature-branch"
    )

    mock_metadata_class.get.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        "modify-example",
        branch="feature-branch",
        preview=True,
    )


def test_get_action_type_missing_action_type_field(
    mock_action_type_full_metadata_service,
):
    """Test that a response without action_type fails loudly."""
    service, mock_metadata_class = mock_action_type_full_metadata_service
    mock_metadata_class.get.return_value = Mock(action_type=None)

    with pytest.raises(RuntimeError, match="did not contain an 'action_type'"):
        service.get_action_type("ri.ontology.main.ontology.test", "modify-example")


def test_get_action_type_error(mock_action_type_full_metadata_service):
    """Test action type get error handling."""
    service, mock_metadata_class = mock_action_type_full_metadata_service
    mock_metadata_class.get.side_effect = Exception("ActionTypeNotFound")

    with pytest.raises(RuntimeError, match="Failed to get action type"):
        service.get_action_type("ri.ontology.main.ontology.test", "modify-example")


# Required publication order hints
def test_upsert_object_type_schema_error_includes_order_hint(
    mock_object_type_service,
):
    """A missing backing dataset schema hints at step 1 of the order."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("SchemaForObjectTypeDatasourceNotFound"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert result["validation"]["status"] == "error"
    hint = result["validation"]["errors"][-1]
    assert hint.startswith("hint (step 3 of the required publication order)")
    assert "backing dataset schema" in hint
    assert "object-type-upsert" in hint  # full order text is included


def test_upsert_object_type_unrelated_error_has_no_hint(mock_object_type_service):
    """Errors that are not missing-dependency signals carry no hint."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("TooManyObjectTypesInOntology"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="ExampleObject",
            display_name="Example Object",
            primary_key="id",
            backing_dataset="ri.foundry.main.dataset.example",
        )

    assert result["validation"]["status"] == "error"
    assert not any(
        error.startswith("hint (") for error in result["validation"]["errors"]
    )


def test_upsert_link_type_missing_object_type_includes_order_hint(
    mock_object_type_service,
):
    """A missing side object type hints that step 3 must run first."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _namespace_probe_response(),
        _validation_error_response("ObjectTypesNotFound"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_link_type(
            ontology_rid="ri.ontology.main.ontology.test",
            api_name="tmLink",
            one_side_object_type_id="ns0abcde.missing-one",
            many_side_object_type_id="ns0abcde.missing-many",
        )

    assert result["validation"]["status"] == "error"
    hint = result["validation"]["errors"][-1]
    assert hint.startswith("hint (step 4 of the required publication order)")
    assert "object-type-upsert (step 3)" in hint


def test_upsert_action_type_missing_object_type_includes_order_hint(
    mock_action_service,
):
    """A missing referenced object type hints at steps 3 and 4."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _validation_error_response("ObjectTypesNotFound"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.upsert_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            definition=_action_type_definition(),
        )

    assert result["validation"]["status"] == "error"
    hint = result["validation"]["errors"][-1]
    assert hint.startswith("hint (step 5 of the required publication order)")
    assert "object-type-upsert (step 3)" in hint
    assert "link-type-upsert (step 4)" in hint


def test_delete_object_type_dependent_link_types_include_reverse_order_hint(
    mock_object_type_service,
):
    """Dependent link types on delete hint at the reverse publication order."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _validation_error_response("ObjectTypeHasDependentLinkTypes"),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.delete_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type_id="ns0abcde.example-object",
        )

    assert result["validation"]["status"] == "error"
    hint = result["validation"]["errors"][-1]
    assert hint.startswith("hint (step 3 of the required publication order)")
    assert "reverse publication order" in hint
    assert "link-type-delete (step 4)" in hint


# object-type-add-property tests


def _bulk_load_response_with_tail_number() -> tuple[int, dict, str]:
    """Loaded state after the tailNumber property was added."""
    status, payload, raw = _bulk_load_response()
    entry = payload["objectTypes"][0]
    property_rid = "ri.ontology.main.property.tail-number"
    entry["objectType"]["propertyTypes"][property_rid] = {
        "rid": property_rid,
        "id": "tail_number",
        "apiName": "tailNumber",
        "displayMetadata": {"displayName": "tailNumber", "visibility": "NORMAL"},
        "indexedForSearch": False,
        "typeClasses": [],
        "type": {
            "type": "string",
            "string": {"isLongText": False, "supportsExactMatching": True},
        },
        "status": {"type": "active", "active": {}},
    }
    entry["datasources"][0]["datasource"]["dataset"]["propertyMapping"][
        property_rid
    ] = "tail_number"
    return (status, payload, raw)


def test_add_property_dry_run_request_shape(mock_object_type_service):
    """The dry-run body matches the contract: propertyTypes add + columnMapping."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="STRING",
            backing_column="tail_number",
        )

    assert result["mode"] == "dry-run"
    assert result["validation"] == {"status": "success", "errors": []}
    assert result["propertyTypeId"] == "tail_number"
    assert result["objectTypeId"] == "ns0abcde.example-object"
    assert result["objectTypeRid"] == "ri.ontology.main.object-type.example-object"
    assert result["backingDataset"] == "ri.foundry.main.dataset.example"

    load_call, dry_run_call = mock_client.conjure.call_args_list
    assert "/ontology/ontology/bulkLoadEntities" in load_call.args[1]
    identifier = load_call.kwargs["json_body"]["objectTypes"][0]["identifier"]
    assert identifier == {
        "type": "objectTypeRid",
        "objectTypeRid": "ri.ontology.main.object-type.example-object",
    }

    body = dry_run_call.kwargs["json_body"]["modificationRequest"]
    variant = body["objectTypes"]["ns0abcde.example-object"]
    assert variant["type"] == "update"
    new_property = variant["update"]["objectType"]["propertyTypes"]["tail_number"]
    assert new_property["apiName"] == "tailNumber"
    assert new_property["type"] == {
        "type": "string",
        "string": {"isLongText": False, "supportsExactMatching": True},
    }
    # Loaded property carried over with its rid translated to the id.
    assert "id" in variant["update"]["objectType"]["propertyTypes"]

    (datasource_update,) = body["objectTypeDatasources"]["ns0abcde.example-object"]
    assert datasource_update["type"] == "update"
    assert datasource_update["update"]["rid"] == "ri.ontology.main.datasource.tm"
    assert datasource_update["update"]["objectTypeDatasourceDefinition"] == {
        "type": "dataset",
        "dataset": {
            "datasetRid": "ri.foundry.main.dataset.example",
            "propertyMapping": {"id": "id", "tail_number": "tail_number"},
        },
    }
    # Load + dry-run only; the real modify endpoint is never called.
    assert mock_client.conjure.call_count == 2
    assert "/modify?" not in dry_run_call.args[1]


def test_add_property_apply_verifies_read_back(mock_object_type_service):
    """An applied add reads the created property and mapping back."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
        _bulk_load_response_with_tail_number(),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="STRING",
            backing_column="tail_number",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["propertyRid"] == "ri.ontology.main.property.tail-number"
    assert result["verification"]["status"] == "verified"
    modify_call = mock_client.conjure.call_args_list[2]
    assert "/modify?" in modify_call.args[1]
    assert "modificationRequest" not in modify_call.kwargs["json_body"]
    assert mock_client.conjure.call_count == 4


def test_add_property_branch_rid_passthrough(mock_object_type_service):
    """--branch-rid lands in the request-level ontologyBranchRid field."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _bulk_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="INTEGER",
            branch_rid="ri.ontology.main.branch.feature",
        )

    assert result["ontologyBranchRid"] == "ri.ontology.main.branch.feature"
    body = mock_client.conjure.call_args.kwargs["json_body"]["modificationRequest"]
    assert body["ontologyBranchRid"] == "ri.ontology.main.branch.feature"
    # Without --backing-column no datasource update is sent.
    assert "objectTypeDatasources" not in body


def test_add_property_branch_unsupported_is_typed(mock_object_type_service):
    """A branch rejection surfaces as a typed FoundryApiError with details."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _bulk_load_response(),
        _validation_error_response("BranchUnsupported"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(FoundryApiError) as exc_info,
    ):
        service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="STRING",
            branch_rid="ri.ontology.main.branch.feature",
        )

    assert exc_info.value.error_name == "OntologyMetadata:BranchUnsupported"
    assert exc_info.value.validation_details
    # The typed error stops the flow before any real modify.
    assert mock_client.conjure.call_count == 2


def test_add_property_refuses_interfaces(mock_object_type_service):
    """Interface-implementing object types are refused, not dropped."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    status, payload, raw = _bulk_load_response()
    payload["objectTypes"][0]["objectType"]["implementsInterfaces2"] = [
        {"interfaceTypeRid": "ri.ontology.main.interface-type.x"}
    ]
    mock_client = Mock()
    mock_client.conjure.side_effect = [(status, payload, raw)]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="implements"),
    ):
        service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="STRING",
        )


def test_add_property_refuses_shared_property_types(mock_object_type_service):
    """Shared property types are refused, not dropped."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    status, payload, raw = _bulk_load_response()
    prop = payload["objectTypes"][0]["objectType"]["propertyTypes"][
        "ri.ontology.main.property.id"
    ]
    prop["sharedPropertyTypeRid"] = "ri.ontology.main.shared-property.x"
    mock_client = Mock()
    mock_client.conjure.side_effect = [(status, payload, raw)]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="shared property types"),
    ):
        service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="tailNumber",
            property_type="STRING",
        )


def test_add_property_refuses_existing_property(mock_object_type_service):
    """Re-adding an existing property API name fails before any modify."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_bulk_load_response()]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="already has a property"),
    ):
        service.add_property_to_object_type(
            ontology_rid="ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="id",
            property_type="STRING",
        )

    assert mock_client.conjure.call_count == 1


# resolve tests
def test_resolve_object_type_by_api_name(mock_object_type_service):
    """object-type resolution returns both the rid and the internal id."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_bulk_load_response()]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.resolve_object_type(
            "ri.ontology.main.ontology.test", api_name="ExampleObject"
        )

    assert result == {
        "kind": "object-type",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "rid": "ri.ontology.main.object-type.example-object",
        "id": "ns0abcde.example-object",
        "apiName": "ExampleObject",
        "displayName": "Example Object",
        "status": "active",
    }
    identifier = mock_client.conjure.call_args.kwargs["json_body"]["objectTypes"][0][
        "identifier"
    ]
    assert identifier == {
        "type": "objectTypeRid",
        "objectTypeRid": "ri.ontology.main.object-type.example-object",
    }


def test_resolve_object_type_by_rid(mock_object_type_service):
    """A rid input resolves through the objectTypeRid identifier."""
    service, _ = mock_object_type_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_bulk_load_response()]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.resolve_object_type(
            "ri.ontology.main.ontology.test",
            rid="ri.ontology.main.object-type.example-object",
        )

    assert result["id"] == "ns0abcde.example-object"
    identifier = mock_client.conjure.call_args.kwargs["json_body"]["objectTypes"][0][
        "identifier"
    ]
    assert identifier == {
        "type": "objectTypeRid",
        "objectTypeRid": "ri.ontology.main.object-type.example-object",
    }


def test_resolve_property(mock_object_type_service):
    """property resolution returns the property rid and internal id."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_bulk_load_response()]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.resolve_property(
            "ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="id",
        )

    assert result["kind"] == "property"
    assert result["rid"] == "ri.ontology.main.property.id"
    assert result["id"] == "id"
    assert result["status"] == "active"
    assert result["objectType"] == {
        "rid": "ri.ontology.main.object-type.example-object",
        "id": "ns0abcde.example-object",
        "apiName": "ExampleObject",
    }


def test_resolve_property_missing(mock_object_type_service):
    """An unknown property API name fails loudly."""
    service, mock_object_type_class = mock_object_type_service
    mock_object_type_class.get.return_value = Mock(
        rid="ri.ontology.main.object-type.example-object"
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_bulk_load_response()]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        pytest.raises(RuntimeError, match="has no property"),
    ):
        service.resolve_property(
            "ri.ontology.main.ontology.test",
            object_type="ExampleObject",
            api_name="unknown",
        )


# action-type-update tests
def _action_type_load_response() -> tuple[int, dict, str]:
    """bulkLoadEntities response for one action type (delete-contact shape)."""
    entry = {
        "actionType": {
            "actionTypeLogic": {
                "logic": {
                    "rules": [
                        {
                            "type": "deleteObjectRule",
                            "deleteObjectRule": {"objectToDelete": "Contact"},
                        }
                    ],
                    "actionLogRule": None,
                },
                "validation": {
                    "actionTypeLevelValidation": {
                        "rules": {
                            "ri.actions.main.validation-rule.v1": {
                                "condition": {"type": "true", "true": {}},
                                "displayMetadata": {
                                    "failureMessage": "x",
                                    "typeClasses": [],
                                },
                            }
                        },
                        "ordering": ["ri.actions.main.validation-rule.v1"],
                        "writeAuthorization": None,
                        "readAuthorization": None,
                    },
                    "parameterValidations": {},
                    "sectionValidations": {},
                    "actionEditsValidation": None,
                },
                "revert": None,
                "webhooks": None,
                "notifications": [],
                "effects": None,
            },
            "metadata": {
                "rid": "ri.actions.main.action-type.1234",
                "apiName": "delete-contact",
                "displayMetadata": {
                    "displayName": "Delete Contact",
                    "description": "",
                    "typeClasses": [],
                },
                "parameters": {
                    "Contact": {
                        "id": "Contact",
                        "rid": "ri.actions.main.parameter.p1",
                        "type": {
                            "type": "objectReference",
                            "objectReference": {"objectTypeId": "ns0abcde.contact"},
                        },
                        "displayMetadata": {
                            "displayName": "Contact",
                            "description": "",
                            "structFields": {},
                            "structFieldsV2": [],
                            "typeClasses": [],
                        },
                    }
                },
                "sections": {},
                "parameterOrdering": ["Contact"],
                "formContentOrdering": [
                    {"type": "parameterId", "parameterId": "Contact"}
                ],
                "status": {"type": "experimental", "experimental": {}},
                "entities": {
                    "affectedObjectTypes": ["ns0abcde.contact"],
                    "affectedLinkTypes": [],
                    "affectedInterfaceTypes": [],
                    "typeGroups": [],
                },
            },
        },
        "ontologyRid": "ri.ontology.main.ontology.test",
    }
    return (200, {"actionTypes": [entry]}, "[]")


def _update_dry_run_body(mock_client) -> dict:
    return mock_client.conjure.call_args.kwargs["json_body"]["modificationRequest"]


def test_update_action_type_dry_run_merges_status_and_display(
    mock_action_service,
):
    """A status flip + displayMetadata merge builds a full ActionTypeUpdate."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={
                "status": "ACTIVE",
                "displayMetadata": {"description": "updated"},
            },
        )

    assert result["mode"] == "dry-run"
    assert result["changedFields"] == ["displayMetadata", "status"]
    assert result["rid"] == "ri.actions.main.action-type.1234"
    body = _update_dry_run_body(mock_client)
    (rid,) = body["actionTypesToUpdate"].keys()
    assert rid == "ri.actions.main.action-type.1234"
    update = body["actionTypesToUpdate"][rid]
    assert update["apiName"] == "delete-contact"
    assert update["status"] == {"type": "active", "active": {}}
    assert update["displayMetadata"]["description"] == "updated"
    assert update["displayMetadata"]["displayName"] == "Delete Contact"
    # Loaded logic and validations carried over unchanged.
    assert update["logic"] == {
        "rules": [
            {
                "type": "deleteObjectRule",
                "deleteObjectRule": {"objectToDelete": "Contact"},
            }
        ]
    }
    assert update["validationsOrdering"] == [
        {"type": "rid", "rid": "ri.actions.main.validation-rule.v1"}
    ]
    assert update["parametersToCreate"] == {}
    assert update["parametersToDelete"] == []
    assert "writeAuthorization" not in update
    # Load + dry-run only; never the real modify endpoint.
    assert mock_client.conjure.call_count == 2
    assert "/modify?" not in mock_client.conjure.call_args.args[1]


def test_update_action_type_replaces_rules_with_function_rule(
    mock_action_service,
):
    """A logic patch swaps object-edit rules for a function rule, with a
    currentUser-bound input passed through per the vendor types."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]
    function_rule = {
        "type": "functionRule",
        "functionRule": {
            "functionRid": "ri.function-registry.main.function.abc",
            "functionVersion": "1.0.0",
            "functionInputValues": {
                "submitter": {"type": "currentUser", "currentUser": {}},
                "target": {"type": "parameterId", "parameterId": "Contact"},
            },
        },
    }

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"logic": {"rules": [function_rule]}},
        )

    assert result["changedFields"] == ["logic"]
    update = _update_dry_run_body(mock_client)["actionTypesToUpdate"][
        "ri.actions.main.action-type.1234"
    ]
    assert update["logic"] == {"rules": [function_rule]}


def test_update_action_type_function_rule_requires_rid_and_version(
    mock_action_service,
):
    """Function rules without rid/version are rejected client-side."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_action_type_load_response()]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
        pytest.raises(RuntimeError, match="functionRid"),
    ):
        service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"logic": {"rules": [{"type": "functionRule", "functionRule": {}}]}},
        )


def _parameter_add_spec() -> dict:
    return {
        "displayMetadata": {
            "displayName": "Notes",
            "description": "",
            "structFields": {},
            "structFieldsV2": [],
            "typeClasses": [],
        },
        "type": {"type": "string", "string": {}},
        "validation": {
            "conditionalOverrides": [],
            "defaultValidation": {
                "display": {
                    "visibility": {"type": "editable", "editable": {}},
                    "renderHint": {"type": "textInput", "textInput": {}},
                },
                "validation": {
                    "required": {"type": "optional", "optional": {}},
                    "allowedValues": {"type": "any", "any": {}},
                },
            },
            "structFieldValidations": {},
        },
    }


def test_update_action_type_parameter_add(mock_action_service):
    """A parameters.add lands in parametersToCreate and both orderings."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"parameters": {"add": {"Notes": _parameter_add_spec()}}},
        )

    assert result["changedFields"] == ["parameters"]
    update = _update_dry_run_body(mock_client)["actionTypesToUpdate"][
        "ri.actions.main.action-type.1234"
    ]
    assert update["parametersToCreate"]["Notes"]["type"] == {
        "type": "string",
        "string": {},
    }
    assert update["parameterOrdering"] == ["Contact", "Notes"]
    assert update["formContentOrdering"] == [
        {"type": "parameterId", "parameterId": "Contact"},
        {"type": "parameterId", "parameterId": "Notes"},
    ]


def test_update_action_type_parameter_remove_and_reorder(mock_action_service):
    """parameters.remove resolves to rids; ordering replaces the order."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    status, payload, raw = _action_type_load_response()
    metadata = payload["actionTypes"][0]["actionType"]["metadata"]
    metadata["parameters"]["Notes"] = {
        "id": "Notes",
        "rid": "ri.actions.main.parameter.p2",
        "type": {"type": "string", "string": {}},
        "displayMetadata": {"displayName": "Notes"},
    }
    metadata["parameterOrdering"] = ["Contact", "Notes"]
    metadata["formContentOrdering"] = [
        {"type": "parameterId", "parameterId": "Contact"},
        {"type": "parameterId", "parameterId": "Notes"},
    ]
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        (status, payload, raw),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"parameters": {"remove": ["Notes"]}},
        )

    assert result["changedFields"] == ["parameters"]
    update = _update_dry_run_body(mock_client)["actionTypesToUpdate"][
        "ri.actions.main.action-type.1234"
    ]
    assert update["parametersToDelete"] == ["ri.actions.main.parameter.p2"]
    assert update["parameterOrdering"] == ["Contact"]
    assert update["formContentOrdering"] == [
        {"type": "parameterId", "parameterId": "Contact"}
    ]


def test_update_action_type_validations_add_remove(mock_action_service):
    """validations.add keys are UUID-normalized; removes resolve to rids."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={
                "validations": {
                    "add": {
                        "must-be-admin": {
                            "condition": {"type": "true", "true": {}},
                            "displayMetadata": {
                                "failureMessage": "admin only",
                                "typeClasses": [],
                            },
                        }
                    },
                    "remove": ["ri.actions.main.validation-rule.v1"],
                }
            },
        )

    assert result["changedFields"] == ["validations"]
    update = _update_dry_run_body(mock_client)["actionTypesToUpdate"][
        "ri.actions.main.action-type.1234"
    ]
    assert update["validationsToDelete"] == ["ri.actions.main.validation-rule.v1"]
    (new_key,) = update["validationsToCreate"].keys()
    uuid.UUID(new_key)  # create keys must be UUID strings on the wire
    assert update["validationsOrdering"] == [
        {"type": "validationRuleIdInRequest", "validationRuleIdInRequest": new_key}
    ]


def test_update_action_type_validations_cannot_remove_all(mock_action_service):
    """Removing every action-type-level validation is rejected client-side."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_action_type_load_response()]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
        pytest.raises(RuntimeError, match="at least one"),
    ):
        service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"validations": {"remove": ["ri.actions.main.validation-rule.v1"]}},
        )


def test_update_action_type_unknown_patch_keys(mock_action_service):
    """Unknown patch keys fail client-side with the supported set."""
    service, _ = mock_action_service
    service.profile = "test-profile"

    with pytest.raises(FoundryApiError, match="supported keys"):
        service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"logicc": {"rules": []}},
        )


def test_update_action_type_apply_verifies_read_back(mock_action_service):
    """An applied update reads the action type back through the SDK."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        (200, {"type": "success", "success": {}}, '{"type":"success"}'),
        (200, {}, "{}"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={
                "rid": "ri.actions.main.action-type.1234",
                "api_name": "delete-contact",
                "status": "ACTIVE",
            },
        ) as mock_get,
    ):
        result = service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"status": "ACTIVE"},
            branch="feature-branch",
            branch_rid="ri.ontology.main.branch.feature",
            apply=True,
        )

    assert result["mode"] == "applied"
    assert result["verification"]["status"] == "verified"
    assert result["metadata"]["status"] == "ACTIVE"
    assert result["ontologyBranchRid"] == "ri.ontology.main.branch.feature"
    # Resolution + read-back both went through the branch-aware SDK get.
    assert mock_get.call_count == 2
    assert mock_get.call_args.kwargs["branch"] == "feature-branch"
    modify_call = mock_client.conjure.call_args_list[2]
    assert "/modify?" in modify_call.args[1]
    body = modify_call.kwargs["json_body"]
    assert body["ontologyBranchRid"] == "ri.ontology.main.branch.feature"
    assert "modificationRequest" not in body


def test_update_action_type_dry_run_blocks_apply_on_error(mock_action_service):
    """A failed dry-run raises on apply instead of issuing the modify."""
    service, _ = mock_action_service
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [
        _action_type_load_response(),
        _validation_error_response("ActionTypesNotFound"),
    ]

    with (
        patch(
            "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
            return_value=mock_client,
        ),
        patch.object(
            ActionService,
            "get_action_type",
            return_value={"rid": "ri.actions.main.action-type.1234"},
        ),
        pytest.raises(RuntimeError, match="dry-run validation failed"),
    ):
        service.update_action_type(
            ontology_rid="ri.ontology.main.ontology.test",
            action_type="delete-contact",
            patch={"status": "ACTIVE"},
            apply=True,
        )

    assert mock_client.conjure.call_count == 2


def test_resolve_action_type_by_api_name(mock_action_service):
    """action-type resolution returns rid, apiName, displayName, status."""
    service, _ = mock_action_service
    service.service.ActionTypeFullMetadata.get.return_value = Mock(
        action_type=Mock(
            rid="ri.actions.main.action-type.1234", parameters={}, operations=[]
        ),
        full_logic_rules=[],
    )
    service.profile = "test-profile"
    mock_client = Mock()
    mock_client.conjure.side_effect = [_action_type_load_response()]

    with patch(
        "foundry_cli.services.foundry_internal_client.FoundryInternalClient",
        return_value=mock_client,
    ):
        result = service.resolve_action_type(
            "ri.ontology.main.ontology.test", api_name="delete-contact"
        )

    assert result == {
        "kind": "action-type",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "rid": "ri.actions.main.action-type.1234",
        "apiName": "delete-contact",
        "displayName": "Delete Contact",
        "status": "experimental",
    }
    load_entry = mock_client.conjure.call_args.kwargs["json_body"]["actionTypes"][0]
    assert load_entry == {"rid": "ri.actions.main.action-type.1234"}
