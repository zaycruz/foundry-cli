"""Tests for verified Compass discovery operations."""

from unittest.mock import Mock, call

import pytest

from pltr.auth.base import ProfileNotFoundError
from pltr.services.compass import CompassService


def _service() -> tuple[CompassService, Mock]:
    internal = Mock()
    return CompassService(internal_client=internal), internal


def _namespace_entry(name: str) -> dict:
    return {
        "resource": {
            "name": name,
            "description": f"{name} description",
            "path": f"/{name}",
            "alias": name,
            "created": {"time": "2025-01-01T00:00:00Z", "userId": "user-1"},
            "modified": {"time": "2025-01-02T00:00:00Z", "userId": "user-1"},
        }
    }


def _template(rid: str, namespace_rid: str, name: str = "Basic project") -> dict:
    return {
        "rid": rid,
        "name": name,
        "description": None,
        "definition": {"variables": {"Name": {}, "Region": {}}},
        "namespaceRid": namespace_rid,
        "principalsAllowedToUseTemplate": None,
    }


def test_list_namespaces_uses_internal_hierarchy_api() -> None:
    service, internal = _service()
    internal.conjure.side_effect = [
        (200, ["ri.compass.main.folder.1", "ri.compass.main.folder.2"], "raw"),
        (
            200,
            {
                "ri.compass.main.folder.1": _namespace_entry("One"),
                "ri.compass.main.folder.2": _namespace_entry("Two"),
            },
            "raw",
        ),
    ]

    result = service.list_namespaces()

    assert internal.conjure.call_args_list == [
        call("GET", "/compass/api/hierarchy/v2/all-namespace-rids"),
        call(
            "PUT",
            "/compass/api/hierarchy/v2/batch/namespaces",
            json_body=["ri.compass.main.folder.1", "ri.compass.main.folder.2"],
        ),
    ]
    assert [record["display_name"] for record in result.data] == ["One", "Two"]
    first = result.data[0]
    assert first["rid"] == "ri.compass.main.folder.1"
    assert first["type"] == "namespace"
    assert first["source_type"] == "compass-namespace"
    assert first["hydrated"] is True
    assert first["created_time"] == "2025-01-01T00:00:00Z"
    assert result.metadata.has_more is False


def test_list_namespaces_paginates_client_side() -> None:
    service, internal = _service()
    rids = [f"ri.compass.main.folder.{index}" for index in range(3)]
    internal.conjure.side_effect = [
        (200, rids, "raw"),
        (200, {rid: _namespace_entry(rid) for rid in rids}, "raw"),
    ]

    first_page = service.list_namespaces(page_size=2)

    assert len(first_page.data) == 2
    assert first_page.metadata.next_page_token == "2"
    assert first_page.metadata.has_more is True

    internal.conjure.side_effect = [
        (200, rids, "raw"),
        (200, {rid: _namespace_entry(rid) for rid in rids}, "raw"),
    ]

    second_page = service.list_namespaces(page_size=2, page_token="2")

    assert len(second_page.data) == 1
    assert second_page.metadata.has_more is False
    assert second_page.metadata.next_page_token is None


def test_list_namespaces_unhydrated_rid_is_flagged_not_dropped() -> None:
    service, internal = _service()
    internal.conjure.side_effect = [
        (200, ["ri.compass.main.folder.1", "ri.compass.main.folder.2"], "raw"),
        (200, {"ri.compass.main.folder.1": _namespace_entry("One")}, "raw"),
    ]

    result = service.list_namespaces()

    assert len(result.data) == 2
    missing = result.data[1]
    assert missing["rid"] == "ri.compass.main.folder.2"
    assert missing["hydrated"] is False
    assert missing["display_name"] is None


def test_list_namespaces_empty_stack_is_not_an_error() -> None:
    service, internal = _service()
    internal.conjure.return_value = (200, [], "raw")

    result = service.list_namespaces()

    assert result.data == []
    assert result.metadata.has_more is False
    internal.conjure.assert_called_once_with(
        "GET", "/compass/api/hierarchy/v2/all-namespace-rids"
    )


def test_list_namespaces_non_200_is_loud() -> None:
    service, internal = _service()
    internal.conjure.return_value = (500, "boom", "boom")

    with pytest.raises(RuntimeError, match="HTTP 500"):
        service.list_namespaces()


def test_list_namespaces_shape_drift_is_loud() -> None:
    service, internal = _service()
    internal.conjure.return_value = (200, {"not": "a list"}, "raw")

    with pytest.raises(RuntimeError, match="unexpected response shape"):
        service.list_namespaces()


def test_list_namespaces_hydration_non_200_is_loud() -> None:
    service, internal = _service()
    internal.conjure.side_effect = [
        (200, ["ri.compass.main.folder.1"], "raw"),
        (403, "denied", "denied"),
    ]

    with pytest.raises(RuntimeError, match="HTTP 403"):
        service.list_namespaces()


def test_invalid_page_token_is_loud() -> None:
    service, internal = _service()
    internal.conjure.side_effect = [
        (200, ["ri.compass.main.folder.1"], "raw"),
        (200, {}, "raw"),
    ]

    with pytest.raises(RuntimeError, match="Invalid page token"):
        service.list_namespaces(page_token="not-an-offset")


def test_list_project_templates_combines_all_namespaces() -> None:
    service, internal = _service()
    internal.conjure.side_effect = [
        (200, ["ri.compass.main.folder.1", "ri.compass.main.folder.2"], "raw"),
        (
            200,
            [_template("ri.compass.main.template.1", "ri.compass.main.folder.1")],
            "raw",
        ),
        (
            200,
            [_template("ri.compass.main.template.2", "ri.compass.main.folder.2")],
            "raw",
        ),
    ]

    result = service.list_project_templates()

    assert internal.conjure.call_args_list == [
        call("GET", "/compass/api/hierarchy/v2/all-namespace-rids"),
        call("GET", "/compass/api/templates/namespace/ri.compass.main.folder.1"),
        call("GET", "/compass/api/templates/namespace/ri.compass.main.folder.2"),
    ]
    assert [record["rid"] for record in result.data] == [
        "ri.compass.main.template.1",
        "ri.compass.main.template.2",
    ]
    first = result.data[0]
    assert first["type"] == "project-template"
    assert first["source_type"] == "compass-template"
    assert first["namespace_rid"] == "ri.compass.main.folder.1"
    assert first["variables"] == ["Name", "Region"]


def test_list_project_templates_single_namespace_skips_enumeration() -> None:
    service, internal = _service()
    internal.conjure.return_value = (
        200,
        [_template("ri.compass.main.template.1", "ri.compass.main.folder.9")],
        "raw",
    )

    result = service.list_project_templates(namespace_rid="ri.compass.main.folder.9")

    internal.conjure.assert_called_once_with(
        "GET", "/compass/api/templates/namespace/ri.compass.main.folder.9"
    )
    assert len(result.data) == 1


def test_list_project_templates_non_200_names_the_namespace() -> None:
    service, internal = _service()
    internal.conjure.return_value = (500, "boom", "boom")

    with pytest.raises(RuntimeError, match="ri.compass.main.folder.9"):
        service.list_project_templates(namespace_rid="ri.compass.main.folder.9")


def test_list_project_templates_shape_drift_is_loud() -> None:
    service, internal = _service()
    internal.conjure.return_value = (200, {"not": "a list"}, "raw")

    with pytest.raises(RuntimeError, match="unexpected response shape"):
        service.list_project_templates(namespace_rid="ri.compass.main.folder.9")


def test_missing_profile_is_an_auth_error() -> None:
    service = CompassService()
    service.auth_manager = Mock()
    service.auth_manager.get_current_profile.return_value = None

    with pytest.raises(ProfileNotFoundError):
        service.list_namespaces()
