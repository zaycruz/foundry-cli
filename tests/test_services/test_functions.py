"""Tests for Functions service."""

import pytest
from unittest.mock import Mock, patch
from foundry_cli.services.functions import FunctionsService


class TestFunctionsService:
    """Test Functions service functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Foundry client."""
        client = Mock()
        client.functions = Mock()
        client.functions.Query = Mock()
        client.functions.ValueType = Mock()
        return client

    @pytest.fixture
    def service(self, mock_client):
        """Create FunctionsService with mocked client."""
        with patch("foundry_cli.services.base.AuthManager") as mock_auth:
            mock_auth.return_value.get_client.return_value = mock_client
            service = FunctionsService()
            return service

    # ===== Query Get Tests =====

    def test_get_query(self, service, mock_client):
        """Test getting a query by API name."""
        # Setup
        query_api_name = "myQuery"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": "ri.functions.main.query.abc123",
            "apiName": query_api_name,
            "version": "1.0.0",
            "parameters": {"limit": "integer"},
        }
        mock_client.functions.Query.get.return_value = mock_response

        # Execute
        result = service.get_query(query_api_name)

        # Assert
        mock_client.functions.Query.get.assert_called_once_with(
            query_api_name, preview=False, version=None
        )
        assert result["apiName"] == query_api_name
        assert result["version"] == "1.0.0"

    def test_get_query_with_version(self, service, mock_client):
        """Test getting a specific query version."""
        # Setup
        query_api_name = "myQuery"
        version = "2.0.0"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": "ri.functions.main.query.abc123",
            "apiName": query_api_name,
            "version": version,
        }
        mock_client.functions.Query.get.return_value = mock_response

        # Execute
        result = service.get_query(query_api_name, version=version)

        # Assert
        mock_client.functions.Query.get.assert_called_once_with(
            query_api_name, preview=False, version=version
        )
        assert result["version"] == version

    def test_get_query_with_preview(self, service, mock_client):
        """Test getting a query with preview mode."""
        # Setup
        query_api_name = "myQuery"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": "ri.functions.main.query.abc123",
            "apiName": query_api_name,
        }
        mock_client.functions.Query.get.return_value = mock_response

        # Execute
        service.get_query(query_api_name, preview=True)

        # Assert
        mock_client.functions.Query.get.assert_called_once_with(
            query_api_name, preview=True, version=None
        )

    def test_get_query_error(self, service, mock_client):
        """Test error handling in get_query."""
        # Setup
        query_api_name = "invalidQuery"
        mock_client.functions.Query.get.side_effect = Exception("Query not found")

        # Execute & Assert
        with pytest.raises(RuntimeError, match="Failed to get query 'invalidQuery'"):
            service.get_query(query_api_name)

    # ===== Query Get-By-RID Tests =====

    def test_get_query_by_rid(self, service, mock_client):
        """Test getting a query by RID."""
        # Setup
        query_rid = "ri.functions.main.query.abc123"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": query_rid,
            "apiName": "myQuery",
            "version": "1.0.0",
        }
        mock_client.functions.Query.get_by_rid.return_value = mock_response

        # Execute
        result = service.get_query_by_rid(query_rid)

        # Assert
        mock_client.functions.Query.get_by_rid.assert_called_once_with(
            query_rid, preview=False, version=None
        )
        assert result["rid"] == query_rid

    def test_get_query_by_rid_error(self, service, mock_client):
        """Test error handling in get_query_by_rid."""
        # Setup
        query_rid = "ri.functions.main.query.invalid"
        mock_client.functions.Query.get_by_rid.side_effect = Exception(
            "Query not found"
        )

        # Execute & Assert
        with pytest.raises(RuntimeError, match=f"Failed to get query {query_rid}"):
            service.get_query_by_rid(query_rid)

    # ===== Query Execute Tests =====

    def test_execute_query(self, service, mock_client):
        """Test executing a query by API name."""
        # Setup
        query_api_name = "myQuery"
        parameters = {"limit": 10, "filter": "active"}
        mock_response = Mock()
        mock_response.dict.return_value = {"result": [{"id": 1, "name": "Test"}]}
        mock_client.functions.Query.execute.return_value = mock_response

        # Execute
        result = service.execute_query(query_api_name, parameters=parameters)

        # Assert
        mock_client.functions.Query.execute.assert_called_once_with(
            query_api_name,
            parameters=parameters,
            preview=False,
            version=None,
        )
        assert "result" in result

    def test_execute_query_no_parameters(self, service, mock_client):
        """Test executing a query without parameters."""
        # Setup
        query_api_name = "myQuery"
        mock_response = Mock()
        mock_response.dict.return_value = {"result": []}
        mock_client.functions.Query.execute.return_value = mock_response

        # Execute
        service.execute_query(query_api_name)

        # Assert
        mock_client.functions.Query.execute.assert_called_once_with(
            query_api_name,
            parameters={},
            preview=False,
            version=None,
        )

    def test_execute_query_with_version(self, service, mock_client):
        """Test executing a specific query version."""
        # Setup
        query_api_name = "myQuery"
        version = "1.5.0"
        parameters = {"limit": 100}
        mock_response = Mock()
        mock_response.dict.return_value = {"result": []}
        mock_client.functions.Query.execute.return_value = mock_response

        # Execute
        service.execute_query(query_api_name, parameters=parameters, version=version)

        # Assert
        mock_client.functions.Query.execute.assert_called_once_with(
            query_api_name,
            parameters=parameters,
            preview=False,
            version=version,
        )

    def test_execute_query_with_preview(self, service, mock_client):
        """Test executing a query with preview mode."""
        # Setup
        query_api_name = "myQuery"
        mock_response = Mock()
        mock_response.dict.return_value = {"result": []}
        mock_client.functions.Query.execute.return_value = mock_response

        # Execute
        service.execute_query(query_api_name, preview=True)

        # Assert
        mock_client.functions.Query.execute.assert_called_once_with(
            query_api_name,
            parameters={},
            preview=True,
            version=None,
        )

    def test_execute_query_error(self, service, mock_client):
        """Test error handling in execute_query."""
        # Setup
        query_api_name = "myQuery"
        mock_client.functions.Query.execute.side_effect = Exception("Permission denied")

        # Execute & Assert
        with pytest.raises(
            RuntimeError, match=f"Failed to execute query '{query_api_name}'"
        ):
            service.execute_query(query_api_name)

    # ===== Query Execute-By-RID Tests =====

    def test_execute_query_by_rid(self, service, mock_client):
        """Test executing a query by RID."""
        # Setup
        query_rid = "ri.functions.main.query.abc123"
        parameters = {"limit": 10}
        mock_query = Mock(api_name="employeeSearch")
        mock_response = Mock()
        mock_response.dict.return_value = {"result": [{"id": 1}]}
        mock_client.functions.Query.get_by_rid.return_value = mock_query
        mock_client.functions.Query.execute.return_value = mock_response

        # Execute
        service.execute_query_by_rid(query_rid, parameters=parameters)

        # Assert
        mock_client.functions.Query.get_by_rid.assert_called_once_with(
            rid=query_rid,
            preview=False,
            version=None,
        )
        mock_client.functions.Query.execute.assert_called_once_with(
            "employeeSearch",
            parameters=parameters,
            preview=False,
            version=None,
        )

    def test_execute_query_by_rid_error(self, service, mock_client):
        """Test error handling in execute_query_by_rid."""
        # Setup
        query_rid = "ri.functions.main.query.invalid"
        mock_client.functions.Query.get_by_rid.side_effect = Exception(
            "Query not found"
        )

        # Execute & Assert
        with pytest.raises(RuntimeError, match=f"Failed to execute query {query_rid}"):
            service.execute_query_by_rid(query_rid)

    # ===== Value Type Tests =====

    def test_get_value_type(self, service, mock_client):
        """Test getting a value type."""
        # Setup
        value_type_rid = "ri.functions.main.value-type.xyz"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": value_type_rid,
            "apiName": "MyValueType",
            "definition": {"type": "struct"},
        }
        mock_client.functions.ValueType.get.return_value = mock_response

        # Execute
        result = service.get_value_type(value_type_rid)

        # Assert
        mock_client.functions.ValueType.get.assert_called_once_with(
            value_type_rid, preview=False
        )
        assert result["rid"] == value_type_rid
        assert result["apiName"] == "MyValueType"

    def test_get_value_type_with_preview(self, service, mock_client):
        """Test getting a value type with preview mode."""
        # Setup
        value_type_rid = "ri.functions.main.value-type.xyz"
        mock_response = Mock()
        mock_response.dict.return_value = {
            "rid": value_type_rid,
            "apiName": "MyValueType",
        }
        mock_client.functions.ValueType.get.return_value = mock_response

        # Execute
        service.get_value_type(value_type_rid, preview=True)

        # Assert
        mock_client.functions.ValueType.get.assert_called_once_with(
            value_type_rid, preview=True
        )

    def test_get_value_type_error(self, service, mock_client):
        """Test error handling in get_value_type."""
        # Setup
        value_type_rid = "ri.functions.main.value-type.invalid"
        mock_client.functions.ValueType.get.side_effect = Exception(
            "ValueType not found"
        )

        # Execute & Assert
        with pytest.raises(
            RuntimeError, match=f"Failed to get value type {value_type_rid}"
        ):
            service.get_value_type(value_type_rid)

    # ===== Response Serialization Tests =====

    def test_response_serialization(self, service, mock_client):
        """Test that responses are properly serialized."""
        # Setup
        query_api_name = "myQuery"
        mock_response = Mock()
        # Simulate a Pydantic model with dict() method
        mock_response.dict.return_value = {
            "rid": "ri.functions.main.query.abc123",
            "apiName": query_api_name,
        }
        mock_client.functions.Query.get.return_value = mock_response

        # Execute
        result = service.get_query(query_api_name)

        # Assert
        assert isinstance(result, dict)
        assert result["apiName"] == query_api_name
        # Verify dict() was called for serialization
        mock_response.dict.assert_called_once()


class TestFunctionsServiceSearch:
    """Test Functions service search functionality."""

    @pytest.fixture
    def service(self):
        """Create FunctionsService with a mocked SDK client."""
        with patch("foundry_cli.services.base.AuthManager") as mock_auth:
            mock_auth.return_value.get_client.return_value = Mock()
            return FunctionsService()

    @pytest.fixture
    def mock_search_service(self):
        """Mock the SearchService used for the GraphQL title search."""
        with patch("foundry_cli.services.functions.SearchService") as MockSearch:
            yield MockSearch

    def test_search_functions_filters_to_functions(self, service, mock_search_service):
        """Test that search results are filtered locally to function resources."""
        mock_search_service.return_value.search.return_value = {
            "status": "ok",
            "reason": None,
            "query": "revenue",
            "limit": 25,
            "truncation_note": "note",
            "results": [
                {
                    "rid": "ri.function-registry.main.function.abc123",
                    "name": "computeRevenue",
                    "path": "/Functions/computeRevenue",
                    "type": "Function",
                    "typename": "ResourceMetadata",
                },
                {
                    "rid": "ri.foundry.main.dataset.def456",
                    "name": "revenue_dataset",
                    "path": "/Data/revenue",
                    "type": "Dataset",
                    "typename": "ResourceMetadata",
                },
            ],
        }

        result = service.search_functions("revenue")

        assert result["status"] == "ok"
        assert result["mode"] == "functions-search"
        assert result["local_filters"]["rid_prefix"] == (
            "ri.function-registry.main.function."
        )
        assert len(result["results"]) == 1
        assert result["results"][0]["rid"] == (
            "ri.function-registry.main.function.abc123"
        )
        mock_search_service.return_value.search.assert_called_once_with(
            "revenue", limit=25
        )

    def test_search_functions_matches_type_name(self, service, mock_search_service):
        """Test function matching by type name when the RID shape differs."""
        mock_search_service.return_value.search.return_value = {
            "status": "ok",
            "reason": None,
            "query": "forecast",
            "limit": 10,
            "results": [
                {
                    "rid": "ri.some-other.main.function.abc",
                    "name": "forecast",
                    "path": "/forecast",
                    "type": "Foundry Function",
                    "typename": "ResourceMetadata",
                }
            ],
        }

        result = service.search_functions("forecast", limit=10)

        assert len(result["results"]) == 1
        mock_search_service.return_value.search.assert_called_once_with(
            "forecast", limit=10
        )

    def test_search_functions_inconclusive_passthrough(
        self, service, mock_search_service
    ):
        """Test that an inconclusive title search is passed through, not emptied."""
        mock_search_service.return_value.search.return_value = {
            "status": "inconclusive",
            "reason": "graphql-error",
            "query": "revenue",
            "limit": 25,
            "results": None,
        }

        result = service.search_functions("revenue")

        assert result["status"] == "inconclusive"
        assert result["reason"] == "graphql-error"
        assert result["results"] is None
        assert result["mode"] == "functions-search"

    def test_search_functions_transport_error(self, service, mock_search_service):
        """Test that a transport failure surfaces as a RuntimeError."""
        mock_search_service.return_value.search.side_effect = Exception("timeout")

        with pytest.raises(RuntimeError, match="Failed to search functions"):
            service.search_functions("revenue")


class TestResolveFunction:
    """Function apiName -> RID resolution (fail-safe like search)."""

    @pytest.fixture
    def service(self):
        with patch("foundry_cli.services.base.AuthManager"):
            return FunctionsService()

    def test_resolve_function_exact_match(self, service):
        search_result = {
            "status": "ok",
            "reason": None,
            "limit": 25,
            "results": [
                {
                    "name": "myFunc",
                    "rid": "ri.function-registry.main.function.abc",
                    "type": "Function",
                },
                {"name": "myFuncV2", "rid": None, "type": "Function"},
            ],
        }
        with patch("foundry_cli.services.functions.SearchService") as mock_search:
            mock_search.return_value.search.return_value = search_result
            result = service.resolve_function(api_name="myFunc")

        assert result["status"] == "ok"
        assert result["rid"] == "ri.function-registry.main.function.abc"
        assert result["apiName"] == "myFunc"

    def test_resolve_function_no_match_is_inconclusive(self, service):
        with patch("foundry_cli.services.functions.SearchService") as mock_search:
            mock_search.return_value.search.return_value = {
                "status": "ok",
                "reason": None,
                "limit": 25,
                "results": [],
            }
            result = service.resolve_function(api_name="missing")

        assert result["status"] == "inconclusive"
        assert "no function titled" in result["reason"]
        assert "rid" not in result

    def test_resolve_function_search_failure_passthrough(self, service):
        with patch("foundry_cli.services.functions.SearchService") as mock_search:
            mock_search.return_value.search.return_value = {
                "status": "inconclusive",
                "reason": "graphql-error",
                "results": None,
            }
            result = service.resolve_function(api_name="myFunc")

        assert result["status"] == "inconclusive"
        assert result["reason"] == "graphql-error"

    def test_resolve_function_rid_passthrough(self, service):
        result = service.resolve_function(
            rid="ri.function-registry.main.function.abc", version="1.0.0"
        )

        assert result["status"] == "ok"
        assert result["rid"] == "ri.function-registry.main.function.abc"
        assert result["version"] == "1.0.0"
        assert result["source"] == "argument"

    def test_resolve_function_requires_exactly_one_identifier(self, service):
        with pytest.raises(RuntimeError, match="exactly one"):
            service.resolve_function()
        with pytest.raises(RuntimeError, match="exactly one"):
            service.resolve_function(
                api_name="myFunc", rid="ri.function-registry.main.function.abc"
            )
