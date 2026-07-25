"""Tests for DeveloperConsoleService OSDK reads and SDK install planning."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pltr.services.dev_console import (
    COORDINATES_UNRESOLVED_REASON,
    DeveloperConsoleService,
    SdkDefinitionDriftError,
)

APP_RID = "ri.third-party-applications.main.third-party-application.my-app"
REPO_RID = "ri.artifacts.main.repository.sdk-repo"


def _service() -> DeveloperConsoleService:
    client = Mock()
    client.profile = "qa"
    return DeveloperConsoleService(client=client)


def _definition(**overrides):
    definition = {
        "version": "1.2.3",
        "packages": [
            {"type": "npm", "name": "@my-app/sdk", "version": "1.2.3"},
            {"type": "python", "name": "my-app-sdk", "version": "1.2.3"},
        ],
        "ontologyRid": "ri.ontology.main.ontology.example",
    }
    definition.update(overrides)
    return definition


@pytest.fixture()
def storage():
    with patch("pltr.services.dev_console.CredentialStorage") as storage_cls:
        storage_cls.return_value.get_profile.return_value = {
            "host": "foundry.example.com",
            "token": "abc",
        }
        yield storage_cls


def test_get_sdk_latest_hits_verified_endpoint():
    service = _service()
    service.client.conjure.return_value = (200, _definition(), "{}")

    result = service.get_sdk(APP_RID)

    service.client.conjure.assert_called_once_with(
        "GET",
        "/third-party-application-service/api/application-sdks/"
        f"{APP_RID}/latest",
    )
    assert result["application_rid"] == APP_RID
    assert result["version"] == "1.2.3"
    assert result["definition"]["ontologyRid"].startswith("ri.ontology")


def test_get_sdk_specific_version_uses_version_endpoint():
    service = _service()
    service.client.conjure.return_value = (200, _definition(), "{}")

    result = service.get_sdk(APP_RID, "0.9.0")

    service.client.conjure.assert_called_once_with(
        "GET",
        f"/third-party-application-service/api/application-sdks/{APP_RID}/0.9.0",
    )
    assert result["version"] == "1.2.3"  # payload version wins


def test_get_sdk_falls_back_to_requested_version_when_payload_lacks_one():
    service = _service()
    payload = _definition()
    del payload["version"]
    service.client.conjure.return_value = (200, payload, "{}")

    assert service.get_sdk(APP_RID, "0.9.0")["version"] == "0.9.0"


def test_get_sdk_fails_loud_on_non_object_payload():
    service = _service()
    service.client.conjure.return_value = (200, ["not", "an", "object"], "[]")

    with pytest.raises(SdkDefinitionDriftError, match="non-object or empty"):
        service.get_sdk(APP_RID)


def test_get_sdk_fails_loud_on_empty_payload():
    service = _service()
    service.client.conjure.return_value = (200, {}, "{}")

    with pytest.raises(SdkDefinitionDriftError):
        service.get_sdk(APP_RID)


def test_http_error_raises_with_status_and_error_name():
    service = _service()
    service.client.conjure.return_value = (
        403,
        {"errorName": "ThirdPartyApplications:InsufficientPermissions"},
        '{"errorName": "ThirdPartyApplications:InsufficientPermissions"}',
    )

    with pytest.raises(RuntimeError, match="HTTP 403"):
        service.get_sdk(APP_RID)


def test_route_not_mounted_raises_clear_message():
    service = _service()
    service.client.conjure.return_value = (
        400,
        {"errorName": "Route:RouteNotMounted"},
        "{}",
    )

    with pytest.raises(RuntimeError, match="not mounted"):
        service.get_sdk(APP_RID)


def test_get_sdk_repository_rid_extracts_repository_rid():
    service = _service()
    service.client.conjure.return_value = (200, {"repositoryRid": REPO_RID}, "{}")

    assert service.get_sdk_repository_rid(APP_RID) == REPO_RID
    service.client.conjure.assert_called_once_with(
        "GET",
        f"/third-party-application-service/api/application-sdks/{APP_RID}"
        "/repository",
    )


def test_get_sdk_repository_rid_accepts_rid_key():
    service = _service()
    service.client.conjure.return_value = (200, {"rid": REPO_RID}, "{}")

    assert service.get_sdk_repository_rid(APP_RID) == REPO_RID


def test_get_sdk_repository_rid_fails_loud_on_drift():
    service = _service()
    service.client.conjure.return_value = (200, {"unexpected": True}, "{}")

    with pytest.raises(SdkDefinitionDriftError, match="no repositoryRid/rid"):
        service.get_sdk_repository_rid(APP_RID)


def _planning_service() -> DeveloperConsoleService:
    service = _service()
    service.client.conjure.side_effect = [
        (200, {"repositoryRid": REPO_RID}, "{}"),
        (200, _definition(), "{}"),
    ]
    return service


def test_build_install_plan_resolves_coordinates_and_registry_urls(storage):
    plan = _planning_service().build_install_plan(APP_RID)

    assert plan["status"] == "planned"
    assert plan["repository_rid"] == REPO_RID
    assert plan["sdk_version"] == "1.2.3"
    assert plan["warnings"]  # registry pattern not verified end-to-end
    steps = {step["ecosystem"]: step for step in plan["steps"]}
    assert (
        steps["pypi"]["registry_url"]
        == f"https://foundry.example.com/the captured contract{REPO_RID}"
        "/contents/release/pypi/simple"
    )
    assert (
        steps["npm"]["registry_url"]
        == f"https://foundry.example.com/the captured contract{REPO_RID}"
        "/contents/release/npm"
    )
    assert steps["pypi"]["package"] == "my-app-sdk==1.2.3"
    assert steps["npm"]["package"] == "@my-app/sdk@1.2.3"


def test_install_defaults_to_dry_run_and_executes_nothing(storage):
    with patch("pltr.services.dev_console.subprocess.run") as run:
        result = _planning_service().install_sdk_package(APP_RID)

    assert result["status"] == "dry-run"
    run.assert_not_called()


def test_explicit_dry_run_wins_over_yes(storage):
    with patch("pltr.services.dev_console.subprocess.run") as run:
        result = _planning_service().install_sdk_package(
            APP_RID, yes=True, dry_run=True
        )

    assert result["status"] == "dry-run"
    run.assert_not_called()


def test_unrecognized_definition_shape_reports_residual_gap(storage):
    service = _service()
    service.client.conjure.side_effect = [
        (200, {"repositoryRid": REPO_RID}, "{}"),
        (200, {"version": "9.9.9", "someUnknownShape": {}}, "{}"),
    ]

    result = service.install_sdk_package(APP_RID, yes=True, target=Path("/tmp/x"))

    assert result["status"] == "unresolved"
    assert result["reason"] == COORDINATES_UNRESOLVED_REASON
    assert result["steps"] == []


def test_pip_install_with_target_uses_current_interpreter_without_sudo(storage):
    completed = Mock(returncode=0, stdout="ok", stderr="")
    with patch(
        "pltr.services.dev_console.subprocess.run", return_value=completed
    ) as run:
        result = _planning_service().install_sdk_package(
            APP_RID, target=Path("/tmp/sdk-target")
        )

    assert result["status"] == "installed"
    pypi_calls = [
        call for call in run.call_args_list if "-m" in call.args[0]
    ]
    assert pypi_calls, "expected a pip invocation"
    command = pypi_calls[0].args[0]
    assert command[0] == sys.executable
    assert "sudo" not in command
    assert command[command.index("--target") + 1] == "/tmp/sdk-target"
    # npm steps are refused without a --target prefix, but target was given,
    # so npm must have run with --prefix.
    npm_calls = [call for call in run.call_args_list if call.args[0][0] == "npm"]
    assert npm_calls
    npm_command = npm_calls[0].args[0]
    assert npm_command[npm_command.index("--prefix") + 1] == "/tmp/sdk-target"


def test_npm_without_target_is_refused_and_marks_failure(storage):
    service = _service()
    service.client.conjure.side_effect = [
        (200, {"repositoryRid": REPO_RID}, "{}"),
        (200, _definition(packages=[{"type": "npm", "name": "@my-app/sdk"}]), "{}"),
    ]
    completed = Mock(returncode=0, stdout="ok", stderr="")
    with patch(
        "pltr.services.dev_console.subprocess.run", return_value=completed
    ) as run:
        result = service.install_sdk_package(APP_RID, yes=True)

    assert result["status"] == "failed"
    run.assert_not_called()
    assert "npm installs require --target" in result["executed"][0]["refused"]


def test_pip_without_target_refused_outside_virtualenv(storage):
    service = _service()
    service.client.conjure.side_effect = [
        (200, {"repositoryRid": REPO_RID}, "{}"),
        (200, _definition(packages=[{"type": "pypi", "name": "my-app-sdk"}]), "{}"),
    ]
    with (
        patch("pltr.services.dev_console.subprocess.run") as run,
        patch.object(sys, "prefix", "/usr"),
        patch.object(sys, "base_prefix", "/usr"),
    ):
        result = service.install_sdk_package(APP_RID, yes=True)

    assert result["status"] == "failed"
    run.assert_not_called()
    assert "system Python" in result["executed"][0]["refused"]


def test_subprocess_failure_marks_install_failed(storage):
    service = _service()
    service.client.conjure.side_effect = [
        (200, {"repositoryRid": REPO_RID}, "{}"),
        (200, _definition(packages=[{"type": "pypi", "name": "my-app-sdk"}]), "{}"),
    ]
    completed = Mock(returncode=1, stdout="", stderr="boom")
    with patch("pltr.services.dev_console.subprocess.run", return_value=completed):
        result = service.install_sdk_package(APP_RID, target=Path("/tmp/t"))

    assert result["status"] == "failed"
    assert result["executed"][0]["returncode"] == 1
    assert result["executed"][0]["stderr"] == "boom"


# ---------------------------------------------------------------------------
# connect (read-only connection context)
# ---------------------------------------------------------------------------

ONT_RID = "ri.ontology.main.ontology.example"
OT_RID = "ri.ontology.main.object-type.aaaa"


def _application_payload(**app_overrides):
    app = {
        "rid": APP_RID,
        "name": "My App",
        "organizationRid": "ri.multipass..organization.org-1",
        "clientSpecification": {
            "type": "public",
            "public": {
                "authorizationCodeGrant": {
                    "enabled": True,
                    "redirectUrls": ["https://app.example.com/auth/callback"],
                },
                "refreshTokenGrant": {"enabled": True},
            },
        },
        "scopes": {
            "dataScope": {
                "ontologyRid": ONT_RID,
                "objectTypes": [OT_RID],
                "linkTypes": ["ri.ontology.main.relation.l1"],
                "actionTypes": [],
            }
        },
    }
    app.update(app_overrides)
    return {"application": app}


def test_connect_returns_validated_connection_context():
    service = _service()
    service.client.conjure.return_value = (200, _application_payload(), "{}")

    result = service.get_connection_context(APP_RID)

    service.client.conjure.assert_called_once_with(
        "GET",
        f"/third-party-application-service/api/applications/{APP_RID}",
    )
    assert result["status"] == "connected"
    assert result["mode"] == "read-only"
    assert result["application_rid"] == APP_RID
    assert result["client_type"] == "public"
    assert result["grants"] == {
        "authorization_code": True,
        "refresh_token": True,
    }
    assert result["redirect_urls"] == ["https://app.example.com/auth/callback"]
    assert result["data_scope"] == {
        "ontology_rid": ONT_RID,
        "objectTypes": 1,
        "linkTypes": 1,
        "actionTypes": 0,
    }
    assert result["warnings"]  # read-only divergence is surfaced, not hidden


def test_connect_fails_loud_on_non_object_payload():
    service = _service()
    service.client.conjure.return_value = (200, ["nope"], "[]")

    with pytest.raises(SdkDefinitionDriftError, match="non-object"):
        service.get_connection_context(APP_RID)


def test_connect_fails_loud_on_missing_application_object():
    service = _service()
    service.client.conjure.return_value = (200, {"unexpected": {}}, "{}")

    with pytest.raises(SdkDefinitionDriftError, match="no 'application' object"):
        service.get_connection_context(APP_RID)


def test_connect_fails_loud_on_missing_identity_fields():
    service = _service()
    service.client.conjure.return_value = (
        200,
        {"application": {"description": "no rid or name"}},
        "{}",
    )

    with pytest.raises(SdkDefinitionDriftError, match="rid/name"):
        service.get_connection_context(APP_RID)


# ---------------------------------------------------------------------------
# sdk generate (blocked posture, never mutates)
# ---------------------------------------------------------------------------


def _sdks_payload():
    return {
        "sdks": [
            {
                "repositoryRid": REPO_RID,
                "version": "0.7.0",
                "npm": {"npmPackageName": "@my-app/sdk"},
            },
            {"repositoryRid": REPO_RID, "version": "0.6.0"},
        ]
    }


def test_sdk_generate_reports_blocked_with_evidence_and_current_sdks():
    service = _service()
    service.client.conjure.return_value = (200, _sdks_payload(), "{}")

    result = service.plan_sdk_generation(APP_RID)

    service.client.conjure.assert_called_once_with(
        "GET",
        f"/third-party-application-service/api/application-sdks/{APP_RID}",
    )
    assert result["status"] == "blocked"
    assert "createSdkV2-contract-unverified" in result["reason"]
    assert any("400" in item for item in result["evidence"])
    assert any("422" in item for item in result["evidence"])
    assert result["current_sdks"][0]["npmPackageName"] == "@my-app/sdk"
    assert result["current_sdks"][1] == {
        "repositoryRid": REPO_RID,
        "version": "0.6.0",
    }


def test_sdk_generate_never_posts():
    service = _service()
    service.client.conjure.return_value = (200, _sdks_payload(), "{}")

    service.plan_sdk_generation(APP_RID)

    methods = [call.args[0] for call in service.client.conjure.call_args_list]
    assert methods == ["GET"]


def test_sdk_generate_fails_loud_on_drift():
    service = _service()
    service.client.conjure.return_value = (200, {"unexpected": []}, "{}")

    with pytest.raises(SdkDefinitionDriftError, match="'sdks' list"):
        service.plan_sdk_generation(APP_RID)


# ---------------------------------------------------------------------------
# convert-osdk-react (local scaffold codegen)
# ---------------------------------------------------------------------------


def _object_type_page():
    return {
        "nextPageToken": None,
        "data": [
            {
                "rid": OT_RID,
                "apiName": "Program",
                "displayName": "Program",
                "titleProperty": "name",
                "primaryKey": "programId",
                "properties": {
                    "programId": {
                        "displayName": "Program ID",
                        "dataType": {"type": "string"},
                    },
                    "name": {
                        "displayName": "Name",
                        "dataType": {"type": "string"},
                    },
                    "active": {"dataType": {"type": "boolean"}},
                    "capacity": {"dataType": {"type": "integer"}},
                    "enrolledOn": {"dataType": {"type": "timestamp"}},
                    "odd": {"dataType": {"type": "mediaReference"}},
                },
            },
            {
                "rid": "ri.ontology.main.object-type.out-of-scope",
                "apiName": "OutOfScope",
                "properties": {},
            },
        ],
    }


def _scaffold_service() -> DeveloperConsoleService:
    service = _service()
    service.client.conjure.side_effect = [
        (200, _application_payload(), "{}"),
        (200, _object_type_page(), "{}"),
    ]
    return service


def test_scaffold_writes_typed_components_for_in_scope_types_only(tmp_path):
    result = _scaffold_service().generate_react_scaffold(APP_RID, tmp_path)

    assert result["status"] == "generated"
    assert result["object_types"] == ["Program"]
    card = (tmp_path / "ProgramCard.tsx").read_text(encoding="utf-8")
    assert "export interface ProgramObject {" in card
    assert "programId: string;" in card
    assert "active: boolean;" in card
    assert "capacity: number;" in card
    assert "enrolledOn: string;" in card
    assert "odd: unknown;" in card  # unrecognized dataType degrades honestly
    assert "export function ProgramCard(" in card
    assert "<h2>{String(object.name)}</h2>" in card
    assert any("unrecognized dataType" in w for w in result["warnings"])
    barrel = (tmp_path / "index.ts").read_text(encoding="utf-8")
    assert 'export { ProgramCard } from "./ProgramCard";' in barrel
    assert not (tmp_path / "OutOfScopeCard.tsx").exists()


def test_scaffold_refuses_overwrite_without_force(tmp_path):
    (tmp_path / "ProgramCard.tsx").write_text("hand-written", encoding="utf-8")

    result = _scaffold_service().generate_react_scaffold(APP_RID, tmp_path)

    assert result["status"] == "conflict"
    assert result["files"] == []
    assert str(tmp_path / "ProgramCard.tsx") in result["conflicts"]
    assert (tmp_path / "ProgramCard.tsx").read_text() == "hand-written"
    assert not (tmp_path / "index.ts").exists()


def test_scaffold_force_overwrites(tmp_path):
    (tmp_path / "ProgramCard.tsx").write_text("old", encoding="utf-8")

    result = _scaffold_service().generate_react_scaffold(
        APP_RID, tmp_path, force=True
    )

    assert result["status"] == "generated"
    assert "ProgramObject" in (tmp_path / "ProgramCard.tsx").read_text()


def test_scaffold_unresolved_when_data_scope_missing(tmp_path):
    service = _service()
    service.client.conjure.return_value = (
        200,
        _application_payload(scopes={}),
        "{}",
    )

    result = service.generate_react_scaffold(APP_RID, tmp_path)

    assert result["status"] == "unresolved"
    assert "data-scope-unresolved" in result["reason"]
    assert list(tmp_path.iterdir()) == []


def test_scaffold_fails_loud_on_object_type_drift(tmp_path):
    service = _service()
    service.client.conjure.side_effect = [
        (200, _application_payload(), "{}"),
        (200, {"nextPageToken": None, "data": [{"rid": OT_RID}]}, "{}"),
    ]

    with pytest.raises(SdkDefinitionDriftError, match="apiName"):
        service.generate_react_scaffold(APP_RID, tmp_path)


def test_scaffold_paginates_object_types(tmp_path):
    service = _service()
    page_one = _object_type_page()
    page_one["nextPageToken"] = "tok-1"
    page_two = {"nextPageToken": None, "data": []}
    service.client.conjure.side_effect = [
        (200, _application_payload(), "{}"),
        (200, page_one, "{}"),
        (200, page_two, "{}"),
    ]

    result = service.generate_react_scaffold(APP_RID, tmp_path)

    assert result["status"] == "generated"
    second_call = service.client.conjure.call_args_list[2]
    assert "pageToken=tok-1" in second_call.args[1]
