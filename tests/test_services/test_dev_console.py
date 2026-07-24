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
