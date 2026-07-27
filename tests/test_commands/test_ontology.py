"""
Tests for ontology commands.
"""

import json
import pytest
from unittest.mock import Mock, patch
from typer.testing import CliRunner

from pltr.commands.ontology import app

runner = CliRunner()


@pytest.fixture
def mock_services():
    """Mock all ontology services."""
    with (
        patch("pltr.commands.ontology.OntologyService") as mock_ont_svc,
        patch("pltr.commands.ontology.ObjectTypeService") as mock_obj_type_svc,
        patch("pltr.commands.ontology.OntologyObjectService") as mock_obj_svc,
        patch("pltr.commands.ontology.ActionService") as mock_action_svc,
        patch("pltr.commands.ontology.QueryService") as mock_query_svc,
    ):
        yield {
            "ontology": mock_ont_svc,
            "object_type": mock_obj_type_svc,
            "object": mock_obj_svc,
            "action": mock_action_svc,
            "query": mock_query_svc,
        }


# Ontology management command tests
def test_list_ontologies_command(mock_services):
    """Test list ontologies command."""
    mock_instance = Mock()
    mock_instance.list_ontologies.return_value = [
        {
            "rid": "ri.ontology.main.ontology.test",
            "api_name": "test_ontology",
            "display_name": "Test Ontology",
            "description": "A test ontology",
        }
    ]
    mock_services["ontology"].return_value = mock_instance

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    mock_instance.list_ontologies.assert_called_once()


def test_get_ontology_command(mock_services):
    """Test get ontology command."""
    mock_instance = Mock()
    mock_instance.get_ontology.return_value = {
        "rid": "ri.ontology.main.ontology.test",
        "api_name": "test_ontology",
        "display_name": "Test Ontology",
        "description": "A test ontology",
    }
    mock_services["ontology"].return_value = mock_instance

    result = runner.invoke(app, ["get", "ri.ontology.main.ontology.test"])

    assert result.exit_code == 0
    mock_instance.get_ontology.assert_called_once_with("ri.ontology.main.ontology.test")


# Object Type command tests
def test_list_object_types_command(mock_services):
    """Test list object types command."""
    mock_instance = Mock()
    mock_instance.list_object_types.return_value = [
        {
            "api_name": "Employee",
            "display_name": "Employee",
            "description": "Employee object type",
            "primary_key": "employee_id",
        }
    ]
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, ["object-type-list", "ri.ontology.main.ontology.test"])

    assert result.exit_code == 0
    mock_instance.list_object_types.assert_called_once()


def test_get_object_type_command(mock_services):
    """Test get object type command."""
    mock_instance = Mock()
    mock_instance.get_object_type.return_value = {
        "api_name": "Employee",
        "display_name": "Employee",
        "description": "Employee object type",
        "primary_key": "employee_id",
        "properties": {},
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app, ["object-type-get", "ri.ontology.main.ontology.test", "Employee"]
    )

    assert result.exit_code == 0
    mock_instance.get_object_type.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee"
    )


def test_create_object_type_command(mock_services):
    """Test create object type command."""
    mock_instance = Mock()
    mock_instance.create_object_type.return_value = {
        "apiName": "ExampleObject",
        "ontologyRid": "ri.ontology.main.ontology.test",
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "ExampleObject",
            "--display-name",
            "Example Object",
            "--primary-key",
            "id",
            "--backing-dataset",
            "ri.foundry.main.dataset.example",
        ],
    )

    assert result.exit_code == 0
    assert "ExampleObject" in result.output
    mock_instance.create_object_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        api_name="ExampleObject",
        display_name="Example Object",
        primary_key="id",
        backing_dataset="ri.foundry.main.dataset.example",
        description=None,
    )


def test_create_object_type_command_auth_error(mock_services):
    """Test object type create command auth error handling."""
    from pltr.auth.base import ProfileNotFoundError

    mock_instance = Mock()
    mock_instance.create_object_type.side_effect = ProfileNotFoundError(
        "Profile not found"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "ExampleObject",
            "--display-name",
            "Example Object",
            "--primary-key",
            "id",
            "--backing-dataset",
            "ri.foundry.main.dataset.example",
        ],
    )

    assert result.exit_code == 1
    assert "Authentication error" in result.output


def test_create_object_type_command_runtime_error(mock_services):
    """Test object type create command runtime error handling."""
    mock_instance = Mock()
    mock_instance.create_object_type.side_effect = RuntimeError("boom")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "ExampleObject",
            "--display-name",
            "Example Object",
            "--primary-key",
            "id",
            "--backing-dataset",
            "ri.foundry.main.dataset.example",
        ],
    )

    assert result.exit_code == 1
    assert "Failed to create object type" in result.output


def _object_type_upsert_args(*extra: str) -> list[str]:
    return [
        "object-type-upsert",
        "ri.ontology.main.ontology.test",
        "--api-name",
        "ExampleObject",
        "--display-name",
        "Example Object",
        "--primary-key",
        "id",
        "--backing-dataset",
        "ri.foundry.main.dataset.example",
        *extra,
    ]


def test_upsert_object_type_command_success(mock_services):
    """Command returns formatted upsert dry-run plan on success."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "mode": "dry-run",
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "validation": {"status": "success", "errors": []},
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args())

    assert result.exit_code == 0
    mock_instance.upsert_object_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        api_name="ExampleObject",
        display_name="Example Object",
        primary_key="id",
        backing_dataset="ri.foundry.main.dataset.example",
        description=None,
        apply=False,
    )


def test_upsert_object_type_command_apply_flag(mock_services):
    """--apply is forwarded to the service."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "mode": "applied",
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "rid": "ri.ontology.main.object-type.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "validation": {"status": "success", "errors": []},
        "verification": {"status": "verified", "detail": "read back"},
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args("--apply"))

    assert result.exit_code == 0
    assert mock_instance.upsert_object_type.call_args.kwargs["apply"] is True


def test_upsert_object_type_command_surfaces_update_plan(mock_services):
    """An existing type yields an update plan with changed fields, exit 0."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "mode": "dry-run",
        "upsertMode": "update",
        "changedFields": ["displayName"],
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "update": {"objectType": {"id": "ns0abcde.example-object"}},
        "validation": {"status": "success", "errors": []},
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args())

    assert result.exit_code == 0
    normalized_output = " ".join(result.output.split())
    assert "update" in normalized_output
    assert "displayName" in normalized_output


def test_upsert_object_type_command_noop_update_does_not_warn(mock_services):
    """A no-op applied update reports skipped verification without warning."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "mode": "applied",
        "upsertMode": "update",
        "changed": False,
        "changedFields": [],
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "rid": "ri.ontology.main.object-type.example-object",
        "validation": {"status": "success", "errors": []},
        "verification": {"status": "skipped", "detail": "no field changes"},
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args("--apply"))

    assert result.exit_code == 0
    assert "not verified" not in result.output


def test_upsert_object_type_command_surfaces_missing_dataset_schema(mock_services):
    """Command tells the user to schema the backing dataset first."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "mode": "dry-run",
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "validation": {
            "status": "error",
            "errors": [
                "the backing dataset has no schema; apply a schema to the "
                "dataset before creating the object type "
                "(OntologyMetadata:SchemaForObjectTypeDatasourceNotFound)"
            ],
        },
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args())

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "backing dataset has no schema; apply a schema" in normalized_output


def test_upsert_object_type_command_apply_error(mock_services):
    """Service-side apply failures surface as command errors."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.side_effect = RuntimeError("boom")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args("--apply"))

    assert result.exit_code == 1
    assert "Failed to upsert object type" in result.output


def test_object_type_upsert_capability_uses_internal_ontology_metadata_api():
    """The live catalog maps upsert to the implemented modifyOntology command."""
    from pltr.capabilities import all_capabilities

    all_capabilities.cache_clear()
    capability = next(
        item
        for item in all_capabilities()
        if item.capability_id == "create_or_update_foundry_object_type"
    )

    assert capability.command == "ontology object-type-upsert"
    assert capability.status == "implemented"
    assert capability.api_evidence is not None
    assert "/ontology-metadata/api/ontology/v2/modify" in capability.api_evidence


def test_create_link_type_command(mock_services):
    """Test create link type command."""
    mock_instance = Mock()
    mock_instance.create_link_type.return_value = {
        "apiName": "exampleLink",
        "ontologyRid": "ri.ontology.main.ontology.test",
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "link-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "exampleLink",
            "--from",
            "ExampleObject",
            "--to",
            "ExampleAgreement",
            "--reverse-api-name",
            "linkExample",
        ],
    )

    assert result.exit_code == 0
    assert "exampleLink" in result.output
    mock_instance.create_link_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        api_name="exampleLink",
        from_object_type="ExampleObject",
        to_object_type="ExampleAgreement",
        display_name=None,
        description=None,
        reverse_api_name="linkExample",
    )


def test_create_link_type_command_auth_error(mock_services):
    """Test link type create command auth error handling."""
    from pltr.auth.base import MissingCredentialsError

    mock_instance = Mock()
    mock_instance.create_link_type.side_effect = MissingCredentialsError(
        "Missing credentials"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "link-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "exampleLink",
            "--from",
            "ExampleObject",
            "--to",
            "ExampleAgreement",
        ],
    )

    assert result.exit_code == 1
    assert "Authentication error" in result.output


def test_create_link_type_command_runtime_error(mock_services):
    """Test link type create command runtime error handling."""
    mock_instance = Mock()
    mock_instance.create_link_type.side_effect = RuntimeError("boom")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "link-type-create",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "exampleLink",
            "--from",
            "ExampleObject",
            "--to",
            "ExampleAgreement",
        ],
    )

    assert result.exit_code == 1
    assert "Failed to create link type" in result.output


# Object operation command tests
def test_list_objects_command(mock_services):
    """Test list objects command."""
    from src.pltr.utils.pagination import PaginationResult, PaginationMetadata

    mock_instance = Mock()
    object_data = [
        {
            "employee_id": "EMP001",
            "name": "John Doe",
            "department": "Engineering",
        }
    ]
    pagination_result = PaginationResult(
        data=object_data, metadata=PaginationMetadata(items_fetched=1, current_page=1)
    )
    mock_instance.list_objects_paginated.return_value = pagination_result
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app, ["object-list", "ri.ontology.main.ontology.test", "Employee"]
    )

    assert result.exit_code == 0
    mock_instance.list_objects_paginated.assert_called_once()


def test_list_objects_with_properties(mock_services):
    """Test list objects with specific properties."""
    from src.pltr.utils.pagination import PaginationResult, PaginationMetadata

    mock_instance = Mock()
    object_data = [{"employee_id": "EMP001", "name": "John Doe"}]
    pagination_result = PaginationResult(
        data=object_data, metadata=PaginationMetadata(items_fetched=1, current_page=1)
    )
    mock_instance.list_objects_paginated.return_value = pagination_result
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-list",
            "ri.ontology.main.ontology.test",
            "Employee",
            "--properties",
            "employee_id,name",
        ],
    )

    assert result.exit_code == 0
    mock_instance.list_objects_paginated.assert_called_once()


def test_get_object_command(mock_services):
    """Test get object command."""
    mock_instance = Mock()
    mock_instance.get_object.return_value = {
        "employee_id": "EMP001",
        "name": "John Doe",
        "department": "Engineering",
    }
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app, ["object-get", "ri.ontology.main.ontology.test", "Employee", "EMP001"]
    )

    assert result.exit_code == 0
    mock_instance.get_object.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", "EMP001", properties=None
    )


def test_aggregate_objects_command(mock_services):
    """Test aggregate objects command."""
    mock_instance = Mock()
    mock_instance.aggregate_objects.return_value = {"count": 10, "avg_salary": 75000}
    mock_services["object"].return_value = mock_instance

    aggregations = json.dumps([{"type": "count"}])
    result = runner.invoke(
        app,
        [
            "object-aggregate",
            "ri.ontology.main.ontology.test",
            "Employee",
            aggregations,
        ],
    )

    assert result.exit_code == 0
    mock_instance.aggregate_objects.assert_called_once()


def test_list_linked_objects_command(mock_services):
    """Test list linked objects command."""
    mock_instance = Mock()
    mock_instance.list_linked_objects.return_value = [
        {"employee_id": "EMP002", "name": "Jane Smith"}
    ]
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-linked",
            "ri.ontology.main.ontology.test",
            "Employee",
            "EMP001",
            "manages",
        ],
    )

    assert result.exit_code == 0
    mock_instance.list_linked_objects.assert_called_once()


def test_count_objects_command(mock_services):
    """Test count objects command."""
    mock_instance = Mock()
    mock_instance.count_objects.return_value = {
        "ontology_rid": "ri.ontology.main.ontology.test",
        "object_type": "Employee",
        "count": 42,
        "branch": None,
    }
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app, ["object-count", "ri.ontology.main.ontology.test", "Employee"]
    )

    assert result.exit_code == 0
    mock_instance.count_objects.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", branch=None
    )


def test_count_objects_with_branch(mock_services):
    """Test count objects with branch specified."""
    mock_instance = Mock()
    mock_instance.count_objects.return_value = {
        "ontology_rid": "ri.ontology.main.ontology.test",
        "object_type": "Employee",
        "count": 24,
        "branch": "master",
    }
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-count",
            "ri.ontology.main.ontology.test",
            "Employee",
            "--branch",
            "master",
        ],
    )

    assert result.exit_code == 0
    mock_instance.count_objects.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", branch="master"
    )


def test_search_objects_command(mock_services):
    """Test search objects command."""
    mock_instance = Mock()
    mock_instance.search_objects.return_value = [
        {"employee_id": "EMP001", "name": "John Doe"}
    ]
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-search",
            "ri.ontology.main.ontology.test",
            "Employee",
            "--query",
            "John",
        ],
    )

    assert result.exit_code == 0
    mock_instance.search_objects.assert_called_once()


def test_search_objects_with_options(mock_services):
    """Test search objects with all options."""
    mock_instance = Mock()
    mock_instance.search_objects.return_value = [
        {"employee_id": "EMP001", "name": "John Doe"}
    ]
    mock_services["object"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-search",
            "ri.ontology.main.ontology.test",
            "Employee",
            "--query",
            "Jane",
            "--page-size",
            "10",
            "--properties",
            "name,department",
            "--branch",
            "master",
        ],
    )

    assert result.exit_code == 0
    call_args = mock_instance.search_objects.call_args
    assert call_args[0] == ("ri.ontology.main.ontology.test", "Employee", "Jane")
    assert call_args[1]["page_size"] == 10
    assert call_args[1]["properties"] == ["name", "department"]
    assert call_args[1]["branch"] == "master"


# Action command tests
def test_apply_action_command(mock_services):
    """Test apply action command."""
    mock_instance = Mock()
    mock_instance.apply_action.return_value = {
        "operation_id": "ri.action.operation.123",
        "validation_result": "VALID",
        "edits_type": "objectEdits",
        "added_object_count": 0,
        "modified_objects_count": 1,
        "deleted_objects_count": 0,
        "added_links_count": 0,
        "deleted_links_count": 0,
        "edits": ["EMP001"],
    }
    mock_services["action"].return_value = mock_instance

    params = json.dumps({"employee_id": "EMP001", "new_department": "Sales"})
    result = runner.invoke(
        app,
        ["action-apply", "ri.ontology.main.ontology.test", "transfer_employee", params],
    )

    assert result.exit_code == 0
    mock_instance.apply_action.assert_called_once()


def test_validate_action_command(mock_services):
    """Test validate action command."""
    mock_instance = Mock()
    mock_instance.validate_action.return_value = {
        "result": "VALID",
        "submission_criteria": [],
        "parameters": {},
    }
    mock_services["action"].return_value = mock_instance

    params = json.dumps({"employee_id": "EMP001", "new_department": "Sales"})
    result = runner.invoke(
        app,
        [
            "action-validate",
            "ri.ontology.main.ontology.test",
            "transfer_employee",
            params,
        ],
    )

    assert result.exit_code == 0
    assert "Action parameters are valid" in result.output
    mock_instance.validate_action.assert_called_once()


def test_validate_action_invalid(mock_services):
    """Test validate action with invalid parameters."""
    mock_instance = Mock()
    mock_instance.validate_action.return_value = {
        "result": "INVALID",
        "submission_criteria": ["Missing required field: employee_id"],
        "parameters": {},
    }
    mock_services["action"].return_value = mock_instance

    params = json.dumps({"new_department": "Sales"})
    result = runner.invoke(
        app,
        [
            "action-validate",
            "ri.ontology.main.ontology.test",
            "transfer_employee",
            params,
        ],
    )

    assert result.exit_code == 0
    assert "Action parameters are invalid" in result.output
    mock_instance.validate_action.assert_called_once()


# Query command tests
def test_execute_query_command(mock_services):
    """Test execute query command."""
    mock_instance = Mock()
    mock_instance.execute_query.return_value = {
        "rows": [
            {"employee_id": "EMP001", "name": "John Doe"},
            {"employee_id": "EMP002", "name": "Jane Smith"},
        ],
        "columns": ["employee_id", "name"],
    }
    mock_services["query"].return_value = mock_instance

    result = runner.invoke(
        app, ["query-execute", "ri.ontology.main.ontology.test", "get_all_employees"]
    )

    assert result.exit_code == 0
    mock_instance.execute_query.assert_called_once()


def test_execute_query_with_parameters(mock_services):
    """Test execute query with parameters."""
    mock_instance = Mock()
    mock_instance.execute_query.return_value = {
        "rows": [{"employee_id": "EMP001", "name": "John Doe"}],
        "columns": ["employee_id", "name"],
    }
    mock_services["query"].return_value = mock_instance

    params = json.dumps({"department": "Engineering"})
    result = runner.invoke(
        app,
        [
            "query-execute",
            "ri.ontology.main.ontology.test",
            "get_employees_by_dept",
            "--parameters",
            params,
        ],
    )

    assert result.exit_code == 0
    mock_instance.execute_query.assert_called_once()
    call_args = mock_instance.execute_query.call_args
    assert call_args[1]["parameters"] == {"department": "Engineering"}


# Error handling tests
def test_authentication_error(mock_services):
    """Test handling of authentication errors."""
    from pltr.auth.base import ProfileNotFoundError

    mock_instance = Mock()
    mock_instance.list_ontologies.side_effect = ProfileNotFoundError(
        "Profile not found"
    )
    mock_services["ontology"].return_value = mock_instance

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 1
    assert "Authentication error" in result.output


def test_invalid_json_parameters(mock_services):
    """Test handling of invalid JSON parameters."""
    result = runner.invoke(
        app,
        [
            "action-apply",
            "ri.ontology.main.ontology.test",
            "transfer_employee",
            "invalid json",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_output_formats(mock_services):
    """Test different output formats."""
    mock_instance = Mock()
    mock_instance.list_ontologies.return_value = [
        {
            "rid": "ri.ontology.main.ontology.test",
            "api_name": "test_ontology",
            "display_name": "Test Ontology",
            "description": "A test ontology",
        }
    ]
    mock_services["ontology"].return_value = mock_instance

    # Test JSON format
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0

    # Test CSV format
    result = runner.invoke(app, ["list", "--format", "csv"])
    assert result.exit_code == 0

    # Test output to file
    with patch("builtins.open", create=True):
        result = runner.invoke(app, ["list", "--output", "output.json"])
        assert result.exit_code == 0
        assert "Ontologies saved to output.json" in result.output


def test_resolve_ontology_rid_command(mock_services):
    """Test resolve ontology RID command."""
    mock_instance = Mock()
    mock_instance.get_ontology_rid.return_value = {
        "rid": "ri.ontology.main.ontology.test",
        "api_name": "test_ontology",
        "display_name": "Test Ontology",
        "description": "A test ontology",
    }
    mock_services["ontology"].return_value = mock_instance

    result = runner.invoke(app, ["rid"])

    assert result.exit_code == 0
    mock_instance.get_ontology_rid.assert_called_once_with()


def test_resolve_ontology_rid_command_ambiguous(mock_services):
    """Test resolve ontology RID command with ambiguous ontologies."""
    mock_instance = Mock()
    mock_instance.get_ontology_rid.side_effect = RuntimeError(
        "Multiple ontologies are visible"
    )
    mock_services["ontology"].return_value = mock_instance

    result = runner.invoke(app, ["rid"])

    assert result.exit_code == 1
    assert "Failed to resolve ontology RID" in result.output


def test_get_link_type_command(mock_services):
    """Test get link type command."""
    mock_instance = Mock()
    mock_instance.get_link_type.return_value = {
        "rid": "ri.ontology.main.link-type.abc123",
        "api_name": "worksAt",
        "display_name": "Works At",
        "status": "ACTIVE",
        "object_type": "Employee",
        "cardinality": "MANY_TO_ONE",
        "foreign_key_property": "company_id",
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        ["link-type-get", "ri.ontology.main.ontology.test", "Employee", "worksAt"],
    )

    assert result.exit_code == 0
    mock_instance.get_link_type.assert_called_once_with(
        "ri.ontology.main.ontology.test", "Employee", "worksAt"
    )


def test_get_link_type_command_not_found(mock_services):
    """Test get link type command error handling."""
    mock_instance = Mock()
    mock_instance.get_link_type.side_effect = RuntimeError(
        "Failed to get link type worksAt: not found"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        ["link-type-get", "ri.ontology.main.ontology.test", "Employee", "worksAt"],
    )

    assert result.exit_code == 1
    assert "Failed to get link type" in result.output


# Action type get command tests
def test_get_action_type_command(mock_services):
    """Test action-type-get command."""
    mock_instance = Mock()
    mock_instance.get_action_type.return_value = {
        "rid": "ri.actions.main.action-type.00000000-0000-0000-0000-000000000001",
        "api_name": "modify-example",
        "display_name": "Modify Example",
        "description": "Modify an example",
        "status": "EXPERIMENTAL",
        "tool_description": None,
        "parameters": ["example", "notes"],
        "operations_count": 1,
        "logic_rules_count": 1,
    }
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app, ["action-type-get", "ri.ontology.main.ontology.test", "modify-example"]
    )

    assert result.exit_code == 0
    mock_instance.get_action_type.assert_called_once_with(
        "ri.ontology.main.ontology.test", "modify-example", branch=None
    )


def test_get_action_type_command_with_branch(mock_services):
    """Test action-type-get with a branch option."""
    mock_instance = Mock()
    mock_instance.get_action_type.return_value = {"api_name": "modify-example"}
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-get",
            "ri.ontology.main.ontology.test",
            "modify-example",
            "--branch",
            "feature-branch",
        ],
    )

    assert result.exit_code == 0
    mock_instance.get_action_type.assert_called_once_with(
        "ri.ontology.main.ontology.test", "modify-example", branch="feature-branch"
    )


def test_get_action_type_command_not_found(mock_services):
    """Test action-type-get when the action type does not exist."""
    mock_instance = Mock()
    mock_instance.get_action_type.side_effect = RuntimeError(
        "Failed to get action type modify-example: ActionTypeNotFound"
    )
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app, ["action-type-get", "ri.ontology.main.ontology.test", "modify-example"]
    )

    assert result.exit_code == 1
    assert "Failed to get action type" in result.stderr


# Delete/upsert authoring commands (modifyOntology-backed)
def _dry_run_plan(operation: str) -> dict:
    return {
        "operation": operation,
        "mode": "dry-run",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "validation": {"status": "success", "errors": []},
    }


def _applied_result(operation: str) -> dict:
    return {
        "operation": operation,
        "mode": "applied",
        "ontologyRid": "ri.ontology.main.ontology.test",
        "validation": {"status": "success", "errors": []},
        "verification": {"status": "verified", "detail": "verified"},
    }


def test_object_type_delete_dry_run_default(mock_services):
    """object-type-delete previews the validated plan without --apply."""
    mock_instance = Mock()
    mock_instance.delete_object_type.return_value = _dry_run_plan("object-type-delete")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-delete",
            "ri.ontology.main.ontology.test",
            "ns0abcde.example-object",
        ],
    )

    assert result.exit_code == 0
    mock_instance.delete_object_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        object_type_id="ns0abcde.example-object",
        apply=False,
    )


def test_object_type_delete_apply_requires_confirmation(mock_services):
    """--apply --yes previews, confirms, and then deletes."""
    mock_instance = Mock()
    mock_instance.delete_object_type.side_effect = [
        _dry_run_plan("object-type-delete"),
        _applied_result("object-type-delete"),
    ]
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-delete",
            "ri.ontology.main.ontology.test",
            "ns0abcde.example-object",
            "--apply",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert mock_instance.delete_object_type.call_count == 2
    assert mock_instance.delete_object_type.call_args_list[0].kwargs["apply"] is False
    assert mock_instance.delete_object_type.call_args_list[1].kwargs["apply"] is True


def test_object_type_delete_apply_cancelled_without_confirmation(mock_services):
    """Declining the confirmation stops before the real deletion."""
    mock_instance = Mock()
    mock_instance.delete_object_type.return_value = _dry_run_plan("object-type-delete")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-delete",
            "ri.ontology.main.ontology.test",
            "ns0abcde.example-object",
            "--apply",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    # Only the dry-run preview call happened.
    mock_instance.delete_object_type.assert_called_once()


def test_object_type_delete_validation_error_exits_nonzero(mock_services):
    """A failed delete validation is reported and exits 1."""
    mock_instance = Mock()
    plan = _dry_run_plan("object-type-delete")
    plan["validation"] = {
        "status": "error",
        "errors": ["OntologyMetadata:ObjectTypesNotFound"],
    }
    mock_instance.delete_object_type.return_value = plan
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-delete",
            "ri.ontology.main.ontology.test",
            "ns0abcde.missing",
            "--apply",
            "--yes",
        ],
    )

    assert result.exit_code == 1
    # The real deletion was never attempted.
    mock_instance.delete_object_type.assert_called_once()


def test_link_type_upsert_command(mock_services):
    """link-type-upsert forwards the contract options to the service."""
    mock_instance = Mock()
    mock_instance.upsert_link_type.return_value = _dry_run_plan("link-type-upsert")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "link-type-upsert",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "exampleObjectOwner",
            "--from-object-type-id",
            "ns0abcde.example-owner",
            "--to-object-type-id",
            "ns0abcde.example-object",
            "--display-name",
            "Example owner",
            "--one-side-primary-key",
            "owner_id",
            "--many-side-property",
            "owner_ref",
        ],
    )

    assert result.exit_code == 0
    mock_instance.upsert_link_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        api_name="exampleObjectOwner",
        one_side_object_type_id="ns0abcde.example-owner",
        many_side_object_type_id="ns0abcde.example-object",
        display_name="Example owner",
        reverse_api_name=None,
        one_side_primary_key="owner_id",
        many_side_property="owner_ref",
        description=None,
        apply=False,
    )


def test_link_type_delete_dry_run_default(mock_services):
    """link-type-delete previews the validated plan without --apply."""
    mock_instance = Mock()
    mock_instance.delete_link_type.return_value = _dry_run_plan("link-type-delete")
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        ["link-type-delete", "ri.ontology.main.ontology.test", "ns0abcde.tm-link"],
    )

    assert result.exit_code == 0
    mock_instance.delete_link_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        link_type_id="ns0abcde.tm-link",
        apply=False,
    )


def test_action_type_upsert_command(mock_services, tmp_path):
    """action-type-upsert reads the JSON definition and dry-runs by default."""
    definition_file = tmp_path / "action.json"
    definition_file.write_text(
        json.dumps(
            {
                "apiName": "pltr-test-action",
                "logic": {"rules": []},
                "validations": {"always": {}},
            }
        )
    )
    mock_instance = Mock()
    mock_instance.upsert_action_type.return_value = _dry_run_plan("action-type-upsert")
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-upsert",
            "ri.ontology.main.ontology.test",
            "--definition",
            str(definition_file),
        ],
    )

    assert result.exit_code == 0
    call_kwargs = mock_instance.upsert_action_type.call_args.kwargs
    assert call_kwargs["ontology_rid"] == "ri.ontology.main.ontology.test"
    assert call_kwargs["definition"]["apiName"] == "pltr-test-action"
    assert call_kwargs["apply"] is False


def test_action_type_upsert_invalid_json(mock_services, tmp_path):
    """A malformed definition file fails before any service call."""
    definition_file = tmp_path / "action.json"
    definition_file.write_text("{not json")
    mock_services["action"].return_value = Mock()

    result = runner.invoke(
        app,
        [
            "action-type-upsert",
            "ri.ontology.main.ontology.test",
            "--definition",
            str(definition_file),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_action_type_delete_dry_run_default(mock_services):
    """action-type-delete previews the validated plan without --apply."""
    mock_instance = Mock()
    mock_instance.delete_action_type.return_value = _dry_run_plan("action-type-delete")
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        ["action-type-delete", "ri.ontology.main.ontology.test", "pltr-test"],
    )

    assert result.exit_code == 0
    mock_instance.delete_action_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        action_type="pltr-test",
        apply=False,
    )


def test_action_type_delete_apply_with_yes(mock_services):
    """action-type-delete --apply --yes previews then deletes."""
    mock_instance = Mock()
    mock_instance.delete_action_type.side_effect = [
        _dry_run_plan("action-type-delete"),
        _applied_result("action-type-delete"),
    ]
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-delete",
            "ri.ontology.main.ontology.test",
            "pltr-test",
            "--apply",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert mock_instance.delete_action_type.call_count == 2


# Required publication order
def test_link_type_upsert_command_surfaces_order_hint(mock_services):
    """A missing-dependency plan prints the required-order hint."""
    mock_instance = Mock()
    plan = _dry_run_plan("link-type-upsert")
    plan["validation"] = {
        "status": "error",
        "errors": [
            "OntologyMetadata:ObjectTypesNotFound: not found",
            "hint (step 4 of the required publication order): one of the "
            "referenced object types does not exist yet; run "
            "object-type-upsert (step 3) before link-type-upsert. "
            "Full order: 1) modify backing dataset schemas",
        ],
    }
    mock_instance.upsert_link_type.return_value = plan
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "link-type-upsert",
            "ri.ontology.main.ontology.test",
            "--api-name",
            "tmLink",
            "--from-object-type-id",
            "ns0abcde.missing-one",
            "--to-object-type-id",
            "ns0abcde.missing-many",
        ],
    )

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "step 4 of the required publication order" in normalized_output


def test_upsert_help_texts_reference_publication_order():
    """Each upsert command's help names its step in the required order."""
    for command, step in [
        ("object-type-upsert", "step 3"),
        ("link-type-upsert", "step 4"),
        ("action-type-upsert", "step 5"),
    ]:
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "publication" in result.output
        assert step in result.output


# object-type-add-property command tests
def test_object_type_add_property_dry_run_default(mock_services):
    """object-type-add-property dry-runs by default and passes options through."""
    mock_instance = Mock()
    mock_instance.add_property_to_object_type.return_value = _dry_run_plan(
        "object-type-add-property"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-add-property",
            "ri.ontology.main.ontology.test",
            "--object-type",
            "ExampleObject",
            "--api-name",
            "tailNumber",
            "--type",
            "STRING",
            "--backing-column",
            "tail_number",
            "--branch-rid",
            "ri.ontology.main.branch.feature",
        ],
    )

    assert result.exit_code == 0
    mock_instance.add_property_to_object_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        object_type="ExampleObject",
        api_name="tailNumber",
        property_type="STRING",
        display_name=None,
        description=None,
        status=None,
        visibility=None,
        backing_column="tail_number",
        backing_dataset=None,
        branch_rid="ri.ontology.main.branch.feature",
        apply=False,
    )


def test_object_type_add_property_apply_flag(mock_services):
    """--apply propagates to the service call."""
    mock_instance = Mock()
    mock_instance.add_property_to_object_type.return_value = _applied_result(
        "object-type-add-property"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "object-type-add-property",
            "ri.ontology.main.ontology.test",
            "--object-type",
            "ExampleObject",
            "--api-name",
            "tailNumber",
            "--type",
            "INTEGER",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert mock_instance.add_property_to_object_type.call_args.kwargs["apply"] is True


def test_object_type_add_property_rejects_bad_type(mock_services):
    """The --type choice is enforced before any service call."""
    mock_services["object_type"].return_value = Mock()

    result = runner.invoke(
        app,
        [
            "object-type-add-property",
            "ri.ontology.main.ontology.test",
            "--object-type",
            "ExampleObject",
            "--api-name",
            "tailNumber",
            "--type",
            "FLOAT",
        ],
    )

    assert result.exit_code != 0


# action-type-update command tests
def test_action_type_update_command(mock_services, tmp_path):
    """action-type-update reads the JSON patch and dry-runs by default."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps({"status": "ACTIVE"}))
    mock_instance = Mock()
    mock_instance.update_action_type.return_value = _dry_run_plan("action-type-update")
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-update",
            "ri.ontology.main.ontology.test",
            "--action-type",
            "delete-contact",
            "--definition",
            str(patch_file),
            "--branch",
            "feature-branch",
            "--branch-rid",
            "ri.ontology.main.branch.feature",
        ],
    )

    assert result.exit_code == 0
    mock_instance.update_action_type.assert_called_once_with(
        ontology_rid="ri.ontology.main.ontology.test",
        action_type="delete-contact",
        patch={"status": "ACTIVE"},
        branch="feature-branch",
        branch_rid="ri.ontology.main.branch.feature",
        apply=False,
    )


def test_action_type_update_definition_from_stdin(mock_services):
    """'-' reads the patch document from stdin."""
    mock_instance = Mock()
    mock_instance.update_action_type.return_value = _dry_run_plan("action-type-update")
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-update",
            "ri.ontology.main.ontology.test",
            "--action-type",
            "delete-contact",
            "--definition",
            "-",
            "--apply",
        ],
        input=json.dumps({"displayMetadata": {"description": "new"}}),
    )

    assert result.exit_code == 0
    call_kwargs = mock_instance.update_action_type.call_args.kwargs
    assert call_kwargs["patch"] == {"displayMetadata": {"description": "new"}}
    assert call_kwargs["apply"] is True
    assert call_kwargs["branch"] is None
    assert call_kwargs["branch_rid"] is None


def test_action_type_update_invalid_json(mock_services, tmp_path):
    """A malformed patch file fails before any service call."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text("{not json")
    mock_services["action"].return_value = Mock()

    result = runner.invoke(
        app,
        [
            "action-type-update",
            "ri.ontology.main.ontology.test",
            "--action-type",
            "delete-contact",
            "--definition",
            str(patch_file),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_action_type_update_surfaces_typed_errors(mock_services, tmp_path):
    """Service failures print an error and exit non-zero."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps({"unknown": {}}))
    mock_instance = Mock()
    mock_instance.update_action_type.side_effect = RuntimeError(
        "unsupported action type patch keys: unknown"
    )
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "action-type-update",
            "ri.ontology.main.ontology.test",
            "--action-type",
            "delete-contact",
            "--definition",
            str(patch_file),
        ],
    )

    assert result.exit_code == 1
    assert "unsupported action type patch keys" in result.output


# resolve command tests
def test_resolve_requires_exactly_one_identifier(mock_services):
    """resolve fails when neither or both of --api-name/--rid are given."""
    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "object-type",
        ],
    )
    assert result.exit_code == 1
    assert "exactly one" in result.output

    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "object-type",
            "--api-name",
            "ExampleObject",
            "--rid",
            "ri.ontology.main.object-type.example-object",
        ],
    )
    assert result.exit_code == 1
    assert "exactly one" in result.output


def test_resolve_object_type_command(mock_services):
    """object-type resolution delegates to ObjectTypeService."""
    mock_instance = Mock()
    mock_instance.resolve_object_type.return_value = {
        "kind": "object-type",
        "rid": "ri.ontology.main.object-type.example-object",
        "id": "ns0abcde.example-object",
        "apiName": "ExampleObject",
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "object-type",
            "--api-name",
            "ExampleObject",
        ],
    )

    assert result.exit_code == 0
    mock_instance.resolve_object_type.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        api_name="ExampleObject",
        rid=None,
    )


def test_resolve_property_requires_object_type(mock_services):
    """--kind property without --object-type fails before the service call."""
    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "property",
            "--api-name",
            "msn",
        ],
    )

    assert result.exit_code == 1
    assert "--object-type" in result.output


def test_resolve_property_command(mock_services):
    """property resolution passes the object-type scope through."""
    mock_instance = Mock()
    mock_instance.resolve_property.return_value = {
        "kind": "property",
        "rid": "ri.ontology.main.property.msn",
        "id": "msn",
    }
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "property",
            "--object-type",
            "ExampleObject",
            "--api-name",
            "msn",
        ],
    )

    assert result.exit_code == 0
    mock_instance.resolve_property.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        object_type="ExampleObject",
        api_name="msn",
    )


def test_resolve_action_type_command(mock_services):
    """action-type resolution delegates to ActionService."""
    mock_instance = Mock()
    mock_instance.resolve_action_type.return_value = {
        "kind": "action-type",
        "rid": "ri.actions.main.action-type.1234",
        "apiName": "delete-contact",
    }
    mock_services["action"].return_value = mock_instance

    result = runner.invoke(
        app,
        [
            "resolve",
            "ri.ontology.main.ontology.test",
            "--kind",
            "action-type",
            "--rid",
            "ri.actions.main.action-type.1234",
        ],
    )

    assert result.exit_code == 0
    mock_instance.resolve_action_type.assert_called_once_with(
        "ri.ontology.main.ontology.test",
        api_name=None,
        rid="ri.actions.main.action-type.1234",
    )


def test_resolve_function_command(mock_services):
    """function resolution delegates to FunctionsService."""
    with patch("pltr.commands.ontology.FunctionsService") as mock_functions:
        mock_instance = Mock()
        mock_instance.resolve_function.return_value = {
            "status": "ok",
            "kind": "function",
            "rid": "ri.function-registry.main.function.abc",
            "apiName": "myFunc",
            "version": "1.0.0",
        }
        mock_functions.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "resolve",
                "ri.ontology.main.ontology.test",
                "--kind",
                "function",
                "--api-name",
                "myFunc",
                "--version",
                "1.0.0",
            ],
        )

    assert result.exit_code == 0
    mock_instance.resolve_function.assert_called_once_with(
        api_name="myFunc", rid=None, version="1.0.0"
    )
