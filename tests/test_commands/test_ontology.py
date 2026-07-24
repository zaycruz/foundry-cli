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
    """Command returns formatted upsert result on success."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.return_value = {
        "apiName": "ExampleObject",
        "objectTypeId": "ns0abcde.example-object",
        "rid": "ri.ontology.main.object-type.example-object",
        "ontologyRid": "ri.ontology.main.ontology.test",
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
    )


def test_upsert_object_type_command_surfaces_existing_type(mock_services):
    """Command preserves the service's explicit no-update-yet boundary."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.side_effect = RuntimeError(
        "object type already exists; update path not yet implemented "
        "(OntologyMetadata:ObjectTypesAlreadyExistError)"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args())

    assert result.exit_code == 1
    assert "Failed to upsert object type" in result.output
    normalized_output = " ".join(result.output.split())
    assert "object type already exists; update path not yet implemented" in (
        normalized_output
    )


def test_upsert_object_type_command_surfaces_missing_dataset_schema(mock_services):
    """Command tells the user to schema the backing dataset first."""
    mock_instance = Mock()
    mock_instance.upsert_object_type.side_effect = RuntimeError(
        "the backing dataset has no schema; apply a schema to the dataset "
        "before creating the object type "
        "(OntologyMetadata:SchemaForObjectTypeDatasourceNotFound)"
    )
    mock_services["object_type"].return_value = mock_instance

    result = runner.invoke(app, _object_type_upsert_args())

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "backing dataset has no schema; apply a schema" in normalized_output


def test_object_type_upsert_capability_uses_internal_ontology_metadata_api():
    """The live catalog maps upsert to the internal ontology-metadata API."""
    from pltr.capabilities import all_capabilities

    all_capabilities.cache_clear()
    capability = next(
        item
        for item in all_capabilities()
        if item.capability_id == "create_or_update_foundry_object_type"
    )

    assert capability.command == "ontology object-type-upsert"
    assert capability.status == "blocked"
    assert capability.blocked_reason is not None
    assert "internal ontology-metadata API" in capability.blocked_reason
    assert "POST /ontology-metadata/api/ontology/v2/modify" in (
        capability.blocked_reason
    )


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
    assert "Failed to get action type" in result.stdout
