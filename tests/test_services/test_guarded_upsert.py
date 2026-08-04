"""
Tests for the guarded mutation composite services (upsert and delete).
"""

import pytest
from unittest.mock import Mock, patch

from foundry_cli.services.guarded_upsert import (
    GuardedUpsertService,
    _is_object_type_not_found,
)
from foundry_cli.services.ontology import ObjectTypeNotFoundError


ONTOLOGY_RID = "ri.ontology.main.ontology.test"
API_NAME = "ExampleObject"
HOST = "https://example.palantirfoundry.com"
DATASET_RID = "ri.foundry.main.dataset.example"


class ObjectTypeNotFound(Exception):
    """Stand-in matching the SDK error class name for net-new detection."""


def _not_found_error() -> RuntimeError:
    error = RuntimeError(f"Failed to get object type {API_NAME}: not found")
    error.__cause__ = ObjectTypeNotFound("missing")
    return error


def _dry_run_plan() -> dict:
    return {
        "operation": "object-type-upsert",
        "mode": "dry-run",
        "apiName": API_NAME,
        "objectTypeId": "ns0abcde.example-object",
        "ontologyRid": ONTOLOGY_RID,
        "validation": {"status": "success", "errors": []},
    }


def _clean_analysis() -> dict:
    return {
        "target": {"kind": "object-type", "display_name": API_NAME},
        "coverage": [],
        "gaps": [],
        "agent": {
            "status": "clean",
            "summary": "0 deduped impacts",
            "change": {"text": "rename", "change_type": "rename"},
            "blast_radius": {"score": 0},
            "verification": {"must_verify_before_merge": []},
            "coverage_completeness": {"complete": True},
        },
    }


@pytest.fixture
def mock_guarded_service():
    """Create a GuardedUpsertService with profile/host resolution mocked."""
    with patch("foundry_cli.services.base.AuthManager") as mock_auth:
        mock_auth.return_value.get_current_profile.return_value = "test-profile"
        mock_auth.return_value.storage.get_profile.return_value = {"host": HOST}
        yield GuardedUpsertService(profile="test-profile")


def _prepare_kwargs(**overrides):
    kwargs = {
        "ontology_rid": ONTOLOGY_RID,
        "api_name": API_NAME,
        "display_name": "Example Object",
        "primary_key": "id",
        "backing_dataset": DATASET_RID,
        "change": "rename the display name",
        "change_type": "rename",
    }
    kwargs.update(overrides)
    return kwargs


def test_is_object_type_not_found_matches_typed_sdk_error():
    """The typed SDK error is detected through the RuntimeError chain."""
    from foundry_sdk.v2.ontologies.errors import (
        ObjectTypeNotFound as SDKObjectTypeNotFound,
    )

    sdk_error = SDKObjectTypeNotFound(
        name="ObjectTypeNotFound",
        parameters={"objectType": "ExampleObject", "ontology": "ri.ontology.x"},
        error_instance_id="iid",
    )
    wrapped = RuntimeError("Failed to get object type ExampleObject: x")
    wrapped.__cause__ = sdk_error
    assert _is_object_type_not_found(wrapped)


def test_is_object_type_not_found_rejects_other_failures():
    assert not _is_object_type_not_found(RuntimeError("permission denied"))


def test_prepare_existing_type_runs_impact_gate(mock_guarded_service):
    """Existing type: dependency gate runs and the dry-run plan is composed."""
    object_types = Mock()
    object_types.get_object_type.return_value = {"api_name": API_NAME}
    object_types.upsert_object_type.return_value = _dry_run_plan()
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    artifact = {"analysis_id": "dep-1", "path": "/tmp/dep-1.json", "sha256": "abc"}
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ) as dependency_cls,
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value=artifact,
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        result = mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())

    assert result["operation"] == "object-type-guarded-upsert"
    assert result["preflight"]["state"] == "existing"
    assert result["preflight"]["current"] == {"api_name": API_NAME}
    assert result["impact"]["status"] == "clean"
    assert result["impact"]["skipped"] is False
    assert result["impact"]["artifact"] == artifact
    assert result["plan"]["mode"] == "dry-run"
    assert result["gate"]["impact_gate"] == "run"
    assert result["gate"]["verification_required"] is False
    assert result["applied"] is False
    assert result["readback"] is None
    assert result["caveats"] == []
    dependency_cls.assert_called_once()
    dependency.resolve_object_type.assert_called_once()
    dependency.analyze.assert_called_once()
    object_types.upsert_object_type.assert_called_once_with(
        ontology_rid=ONTOLOGY_RID,
        api_name=API_NAME,
        display_name="Example Object",
        primary_key="id",
        backing_dataset=DATASET_RID,
        description=None,
        apply=False,
    )


def test_prepare_net_new_skips_gate_with_caveat(mock_guarded_service):
    """Net-new type: gate skipped, coverage caveat recorded, plan still built."""
    object_types = Mock()
    object_types.get_object_type.side_effect = _not_found_error()
    object_types.upsert_object_type.return_value = _dry_run_plan()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch("foundry_cli.services.guarded_upsert.DependencyGraphService") as dependency_cls,
    ):
        result = mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())

    assert result["preflight"]["state"] == "net-new"
    assert result["preflight"]["current"] is None
    assert result["impact"]["skipped"] is True
    assert result["gate"]["impact_gate"] == "skipped-net-new"
    assert any("net-new" in caveat for caveat in result["caveats"])
    assert result["plan"]["mode"] == "dry-run"
    dependency_cls.assert_not_called()


def test_prepare_skip_impact_gate_is_recorded(mock_guarded_service):
    """--skip-impact-gate opts out explicitly and is recorded in the result."""
    object_types = Mock()
    object_types.get_object_type.return_value = {"api_name": API_NAME}
    object_types.upsert_object_type.return_value = _dry_run_plan()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch("foundry_cli.services.guarded_upsert.DependencyGraphService") as dependency_cls,
    ):
        result = mock_guarded_service.prepare_object_type_upsert(
            **_prepare_kwargs(skip_impact_gate=True)
        )

    assert result["impact"]["skipped"] is True
    assert result["impact"]["status"] == "skipped"
    assert result["gate"]["impact_gate"] == "skipped-requested"
    assert any("--skip-impact-gate" in caveat for caveat in result["caveats"])
    dependency_cls.assert_not_called()


def test_prepare_carries_coverage_gaps_into_caveats(mock_guarded_service):
    """Uncertain gate coverage surfaces as caveats, never as 'no impact'."""
    object_types = Mock()
    object_types.get_object_type.return_value = {"api_name": API_NAME}
    object_types.upsert_object_type.return_value = _dry_run_plan()
    dependency = Mock()
    analysis = _clean_analysis()
    analysis["gaps"] = [
        {
            "surface": "action-contracts",
            "target": API_NAME,
            "coverage": "partial",
            "message": "ACP providers unavailable",
        }
    ]
    analysis["agent"]["status"] = "needs-verification"
    analysis["agent"]["verification"] = {
        "must_verify_before_merge": [{"item": "verify action contracts"}]
    }
    analysis["agent"]["coverage_completeness"] = {"complete": False}
    dependency.analyze.return_value = analysis
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-2", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        result = mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())

    assert result["impact"]["status"] == "needs-verification"
    assert result["gate"]["verification_required"] is True
    assert any(
        "partial" in caveat and "uncertain" in caveat for caveat in result["caveats"]
    )


def test_prepare_propagates_non_not_found_preflight_errors(mock_guarded_service):
    """A preflight read failure that is not not-found aborts loudly."""
    object_types = Mock()
    object_types.get_object_type.side_effect = RuntimeError("permission denied")
    with patch(
        "foundry_cli.services.guarded_upsert.ObjectTypeService",
        return_value=object_types,
    ):
        with pytest.raises(RuntimeError, match="permission denied"):
            mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())


def test_apply_performs_upsert_and_authoritative_readback(mock_guarded_service):
    """Apply replays the request with apply=True and reads the type back."""
    object_types = Mock()
    object_types.get_object_type.return_value = {"api_name": API_NAME}
    object_types.upsert_object_type.side_effect = [
        _dry_run_plan(),
        {
            **_dry_run_plan(),
            "mode": "applied",
            "rid": "ri.ontology.main.object-type.example-object",
            "verification": {"status": "verified", "detail": "read back"},
        },
    ]
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-3", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        prepared = mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())
        result = mock_guarded_service.apply_object_type_upsert(
            prepared, verification_accepted=True
        )

    assert result["applied"] is True
    assert result["upsert"]["mode"] == "applied"
    assert result["readback"]["status"] == "verified"
    assert result["readback"]["object_type"] == {"api_name": API_NAME}
    assert result["gate"]["verification_accepted"] is True
    assert any("accepted" in caveat for caveat in result["caveats"])
    assert object_types.upsert_object_type.call_args.kwargs["apply"] is True


def test_apply_records_unverified_readback(mock_guarded_service):
    """A failed read-back is reported, not raised over the applied mutation."""
    object_types = Mock()
    object_types.get_object_type.side_effect = [
        {"api_name": API_NAME},
        RuntimeError("read-back down"),
    ]
    object_types.upsert_object_type.side_effect = [
        _dry_run_plan(),
        {**_dry_run_plan(), "mode": "applied"},
    ]
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-4", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        prepared = mock_guarded_service.prepare_object_type_upsert(**_prepare_kwargs())
        result = mock_guarded_service.apply_object_type_upsert(prepared)

    assert result["applied"] is True
    assert result["readback"]["status"] == "not-verified"
    assert "read-back down" in result["readback"]["detail"]
    assert result["gate"]["verification_accepted"] is False


# Guarded delete composite (prepare_object_type_delete / apply_object_type_delete)
OBJECT_TYPE_ID = "ns0abcde.example-object"


def _loaded_entry() -> dict:
    return {
        "objectType": {
            "id": OBJECT_TYPE_ID,
            "apiName": API_NAME,
            "displayMetadata": {"displayName": "Example Object"},
            "status": "ACTIVE",
        }
    }


def _delete_dry_run_plan() -> dict:
    return {
        "operation": "object-type-delete",
        "mode": "dry-run",
        "objectTypeId": OBJECT_TYPE_ID,
        "ontologyRid": ONTOLOGY_RID,
        "validation": {"status": "success", "errors": []},
    }


def _prepare_delete_kwargs(**overrides):
    kwargs = {"ontology_rid": ONTOLOGY_RID, "object_type_id": OBJECT_TYPE_ID}
    kwargs.update(overrides)
    return kwargs


def test_prepare_delete_existing_type_runs_impact_gate(mock_guarded_service):
    """Existing type: gate runs against the resolved API name, plan composed."""
    object_types = Mock()
    object_types.load_object_type_state.return_value = _loaded_entry()
    object_types.delete_object_type.return_value = _delete_dry_run_plan()
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    artifact = {"analysis_id": "dep-1", "path": "/tmp/dep-1.json", "sha256": "abc"}
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ) as dependency_cls,
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value=artifact,
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        result = mock_guarded_service.prepare_object_type_delete(
            **_prepare_delete_kwargs()
        )

    assert result["operation"] == "object-type-guarded-delete"
    assert result["preflight"]["state"] == "existing"
    assert result["preflight"]["current"]["apiName"] == API_NAME
    assert result["impact"]["status"] == "clean"
    assert result["impact"]["skipped"] is False
    assert result["impact"]["artifact"] == artifact
    assert result["plan"]["mode"] == "dry-run"
    assert result["gate"]["impact_gate"] == "run"
    assert result["applied"] is False
    assert result["readback"] is None
    assert result["caveats"] == []
    # Defaults: intent is a removal assessment.
    assert result["request"]["change"] == "delete object type"
    assert result["request"]["changeType"] == "remove-delete"
    dependency_cls.assert_called_once()
    # The gate resolves the API name recovered from the loaded state.
    assert dependency.resolve_object_type.call_args.args[2] == API_NAME
    dependency.analyze.assert_called_once()
    object_types.delete_object_type.assert_called_once_with(
        ontology_rid=ONTOLOGY_RID,
        object_type_id=OBJECT_TYPE_ID,
        apply=False,
    )


def test_prepare_delete_not_found_fails_typed(mock_guarded_service):
    """A missing type aborts with the typed not-found before any planning."""
    object_types = Mock()
    object_types.load_object_type_state.side_effect = ObjectTypeNotFoundError(
        f"Could not load the current state of object type {OBJECT_TYPE_ID}"
    )
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch("foundry_cli.services.guarded_upsert.DependencyGraphService") as dependency_cls,
    ):
        with pytest.raises(ObjectTypeNotFoundError):
            mock_guarded_service.prepare_object_type_delete(**_prepare_delete_kwargs())

    dependency_cls.assert_not_called()
    object_types.delete_object_type.assert_not_called()


def test_prepare_delete_propagates_other_load_errors(mock_guarded_service):
    """Load failures that are not not-found propagate unchanged."""
    object_types = Mock()
    object_types.load_object_type_state.side_effect = RuntimeError("permission denied")
    with patch(
        "foundry_cli.services.guarded_upsert.ObjectTypeService",
        return_value=object_types,
    ):
        with pytest.raises(RuntimeError, match="permission denied") as exc_info:
            mock_guarded_service.prepare_object_type_delete(**_prepare_delete_kwargs())

    assert not isinstance(exc_info.value, ObjectTypeNotFoundError)
    object_types.delete_object_type.assert_not_called()


def test_prepare_delete_skip_impact_gate_is_recorded(mock_guarded_service):
    """--skip-impact-gate opts out explicitly and is recorded in the result."""
    object_types = Mock()
    object_types.load_object_type_state.return_value = _loaded_entry()
    object_types.delete_object_type.return_value = _delete_dry_run_plan()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch("foundry_cli.services.guarded_upsert.DependencyGraphService") as dependency_cls,
    ):
        result = mock_guarded_service.prepare_object_type_delete(
            **_prepare_delete_kwargs(skip_impact_gate=True)
        )

    assert result["impact"]["skipped"] is True
    assert result["impact"]["status"] == "skipped"
    assert result["gate"]["impact_gate"] == "skipped-requested"
    assert any("--skip-impact-gate" in caveat for caveat in result["caveats"])
    dependency_cls.assert_not_called()
    object_types.delete_object_type.assert_called_once()


def test_prepare_delete_carries_coverage_gaps_into_caveats(mock_guarded_service):
    """Uncertain gate coverage surfaces as caveats, never as 'no impact'."""
    object_types = Mock()
    object_types.load_object_type_state.return_value = _loaded_entry()
    object_types.delete_object_type.return_value = _delete_dry_run_plan()
    dependency = Mock()
    analysis = _clean_analysis()
    analysis["gaps"] = [
        {
            "surface": "action-contracts",
            "target": API_NAME,
            "coverage": "inaccessible",
            "message": "ACP providers denied",
        }
    ]
    analysis["agent"]["status"] = "needs-verification"
    analysis["agent"]["verification"] = {
        "must_verify_before_merge": [{"item": "verify action contracts"}]
    }
    analysis["agent"]["coverage_completeness"] = {"complete": False}
    dependency.analyze.return_value = analysis
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-2", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        result = mock_guarded_service.prepare_object_type_delete(
            **_prepare_delete_kwargs()
        )

    assert result["impact"]["status"] == "needs-verification"
    assert result["gate"]["verification_required"] is True
    assert any(
        "inaccessible" in caveat and "uncertain" in caveat
        for caveat in result["caveats"]
    )


def test_apply_delete_verifies_removal_by_readback(mock_guarded_service):
    """Apply deletes, then the read-back's typed not-found proves removal."""
    object_types = Mock()
    object_types.load_object_type_state.side_effect = [
        _loaded_entry(),
        ObjectTypeNotFoundError("gone"),
    ]
    object_types.delete_object_type.side_effect = [
        _delete_dry_run_plan(),
        {
            **_delete_dry_run_plan(),
            "mode": "applied",
            "verification": {"status": "verified", "detail": "not found"},
        },
    ]
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-3", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        prepared = mock_guarded_service.prepare_object_type_delete(
            **_prepare_delete_kwargs()
        )
        result = mock_guarded_service.apply_object_type_delete(
            prepared, verification_accepted=True
        )

    assert result["applied"] is True
    assert result["delete"]["mode"] == "applied"
    assert result["readback"]["status"] == "verified-removed"
    assert result["gate"]["verification_accepted"] is True
    assert any("accepted" in caveat for caveat in result["caveats"])
    assert object_types.delete_object_type.call_args.kwargs["apply"] is True


def test_apply_delete_reports_not_verified_when_type_still_loads(
    mock_guarded_service,
):
    """A type that still loads after delete is reported, not raised over."""
    object_types = Mock()
    object_types.load_object_type_state.return_value = _loaded_entry()
    object_types.delete_object_type.side_effect = [
        _delete_dry_run_plan(),
        {**_delete_dry_run_plan(), "mode": "applied"},
    ]
    dependency = Mock()
    dependency.analyze.return_value = _clean_analysis()
    with (
        patch(
            "foundry_cli.services.guarded_upsert.ObjectTypeService",
            return_value=object_types,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.DependencyGraphService",
            return_value=dependency,
        ),
        patch(
            "foundry_cli.services.guarded_upsert.write_dependency_artifact",
            return_value={"analysis_id": "dep-4", "path": "/tmp/d.json", "sha256": "x"},
        ),
        patch("foundry_cli.services.foundry_internal_client.FoundryInternalClient"),
        patch("foundry_cli.services.dependency_providers.ConjureRestProvider"),
    ):
        prepared = mock_guarded_service.prepare_object_type_delete(
            **_prepare_delete_kwargs()
        )
        result = mock_guarded_service.apply_object_type_delete(prepared)

    assert result["applied"] is True
    assert result["readback"]["status"] == "not-verified"
    assert "still loads" in result["readback"]["detail"]
    assert result["gate"]["verification_accepted"] is False
