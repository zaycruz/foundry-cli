"""Tests for typed Foundry API error preservation."""

from foundry_cli.services.errors import (
    FoundryApiError,
    foundry_error_from_conjure,
    foundry_error_from_sdk,
)


class _FakeSdkError(Exception):
    """Mimics foundry_sdk PalantirRPCException attributes."""

    def __init__(self) -> None:
        super().__init__('{"errorName": "Datasets:SchemaNotFound"}')
        self.name = "Datasets:SchemaNotFound"
        self.error_code = "NOT_FOUND"
        self.error_instance_id = "aaaa-bbbb"
        self.parameters = {"datasetRid": "ri.foundry.main.dataset.abc"}
        self.error_description = "Schema not found on branch"


def test_error_entry_keeps_all_foundry_fields() -> None:
    err = FoundryApiError(
        "boom",
        error_name="OntologyMetadata:InvalidObjectTypeId",
        error_code="INVALID_ARGUMENT",
        error_instance_id="iid-1",
        safe_parameters={"objectTypeId": "ns0abcde.cohort"},
        validation_details=[{"errorName": "X"}],
        status_code=400,
    )
    entry = err.error_entry()
    assert entry == {
        "type": "foundry_api",
        "message": "boom",
        "errorName": "OntologyMetadata:InvalidObjectTypeId",
        "errorCode": "INVALID_ARGUMENT",
        "errorInstanceId": "iid-1",
        "safeParameters": {"objectTypeId": "ns0abcde.cohort"},
        "validationDetails": [{"errorName": "X"}],
        "statusCode": 400,
    }


def test_from_sdk_preserves_rpc_fields() -> None:
    err = foundry_error_from_sdk(_FakeSdkError(), context="put schema")
    assert err.error_name == "Datasets:SchemaNotFound"
    assert err.error_code == "NOT_FOUND"
    assert err.error_instance_id == "aaaa-bbbb"
    assert err.safe_parameters == {"datasetRid": "ri.foundry.main.dataset.abc"}
    assert "put schema" in str(err)


def test_from_sdk_degrades_for_plain_exceptions() -> None:
    err = foundry_error_from_sdk(ValueError("nope"))
    assert err.error_name is None
    assert "nope" in str(err)


def test_from_conjure_reads_error_payload() -> None:
    parsed = {
        "errorName": "OntologyMetadata:ObjectTypesNotFound",
        "errorCode": "INVALID_ARGUMENT",
        "errorInstanceId": "iid-9",
        "parameters": {"objectTypeId": "ns0abcde.missing"},
    }
    err = foundry_error_from_conjure(400, parsed, "raw", context="modify")
    assert err.error_name == "OntologyMetadata:ObjectTypesNotFound"
    assert err.status_code == 400
    assert err.safe_parameters["objectTypeId"] == "ns0abcde.missing"


def test_from_conjure_extracts_validation_union() -> None:
    parsed = {
        "type": "error",
        "error": {"errors": [{"errorName": "OntologyMetadata:InvalidPropertyType"}]},
    }
    err = foundry_error_from_conjure(200, parsed, "raw")
    assert err.validation_details == [
        {"errorName": "OntologyMetadata:InvalidPropertyType"}
    ]


def test_from_conjure_handles_unparsed_body() -> None:
    err = foundry_error_from_conjure(502, "bad gateway", "bad gateway")
    assert err.error_name is None
    assert err.status_code == 502
    assert "bad gateway" in str(err)
