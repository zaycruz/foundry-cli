"""CLI tests for dev-console OSDK definition reads and SDK installs."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from pltr.cli import app
from pltr.services.dev_console import SdkDefinitionDriftError
from pltr.services.foundry_internal_client import TokenExpiredError

APP_RID = "ri.third-party-applications.main.third-party-application.my-app"
REPO_RID = "ri.artifacts.main.repository.sdk-repo"

runner = CliRunner()

SERVICE = "pltr.commands.dev_console.DeveloperConsoleService"


def _definition_result():
    return {
        "application_rid": APP_RID,
        "version": "1.2.3",
        "definition": {"version": "1.2.3", "ontologyRid": "ri.ontology.main.x"},
    }


def _install_result(status: str = "dry-run"):
    result = {
        "application_rid": APP_RID,
        "sdk_version": "1.2.3",
        "repository_rid": REPO_RID,
        "base_url": "https://foundry.example.com",
        "coordinates": [{"ecosystem": "pypi", "name": "my-app-sdk", "version": "1.2.3"}],
        "steps": [
            {
                "ecosystem": "pypi",
                "package": "my-app-sdk==1.2.3",
                "registry_url": (
                    f"https://foundry.example.com/the captured contract"
                    f"{REPO_RID}/contents/release/pypi/simple"
                ),
                "command": ["python", "-m", "pip", "install", "my-app-sdk==1.2.3"],
            }
        ],
        "warnings": ["registry-unverified"],
        "status": status,
        "reason": None,
        "executed": [],
    }
    if status == "unresolved":
        result.update(
            coordinates=[], steps=[], reason="package-coordinates-unresolved: ..."
        )
    return result


def test_definition_renders_json_and_calls_service():
    with patch(SERVICE) as service:
        service.return_value.get_sdk.return_value = _definition_result()
        result = runner.invoke(
            app, ["dev-console", "osdk", "definition", APP_RID, "--profile", "qa"]
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["version"] == "1.2.3"
    service.assert_called_once_with(profile="qa")
    service.return_value.get_sdk.assert_called_once_with(APP_RID, None)


def test_definition_passes_version_option():
    with patch(SERVICE) as service:
        service.return_value.get_sdk.return_value = _definition_result()
        result = runner.invoke(
            app,
            ["dev-console", "osdk", "definition", APP_RID, "--version", "0.9.0"],
        )

    assert result.exit_code == 0, result.output
    service.return_value.get_sdk.assert_called_once_with(APP_RID, "0.9.0")


def test_definition_agent_mode_emits_single_envelope():
    with patch(SERVICE) as service:
        service.return_value.get_sdk.return_value = _definition_result()
        result = runner.invoke(
            app, ["--agent", "dev-console", "osdk", "definition", APP_RID]
        )

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "pltr-agent-v1"
    assert envelope["data"]["application_rid"] == APP_RID
    assert envelope["meta"]["result_type"] == "osdk-definition"


def test_definition_drift_exits_nonzero_and_fails_loud():
    with patch(SERVICE) as service:
        service.return_value.get_sdk.side_effect = SdkDefinitionDriftError(
            "non-object payload"
        )
        result = runner.invoke(app, ["dev-console", "osdk", "definition", APP_RID])

    assert result.exit_code == 1
    assert "DRIFT [sdk-definition-shape]" in result.output


def test_definition_token_expired_exits_nonzero():
    with patch(SERVICE) as service:
        service.return_value.get_sdk.side_effect = TokenExpiredError()
        result = runner.invoke(app, ["dev-console", "osdk", "definition", APP_RID])

    assert result.exit_code == 1
    assert "token-expired" in result.output


def test_install_defaults_to_dry_run_and_exits_zero():
    with patch(SERVICE) as service:
        service.return_value.install_sdk_package.return_value = _install_result()
        result = runner.invoke(app, ["dev-console", "sdk", "install", APP_RID])

    assert result.exit_code == 0, result.output
    assert "SDK INSTALL [dry-run]" in result.output
    assert "nothing was executed" in result.output
    service.return_value.install_sdk_package.assert_called_once_with(
        APP_RID, version=None, yes=False, target=None, dry_run=False
    )


def test_install_passes_execution_flags_through():
    with patch(SERVICE) as service:
        service.return_value.install_sdk_package.return_value = _install_result(
            "installed"
        )
        result = runner.invoke(
            app,
            [
                "dev-console",
                "sdk",
                "install",
                APP_RID,
                "--yes",
                "--version",
                "1.2.3",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "SDK INSTALL [installed]" in result.output
    kwargs = service.return_value.install_sdk_package.call_args.kwargs
    assert kwargs["yes"] is True
    assert kwargs["version"] == "1.2.3"


def test_install_unresolved_reports_residual_gap_with_exit_2():
    with patch(SERVICE) as service:
        service.return_value.install_sdk_package.return_value = _install_result(
            "unresolved"
        )
        result = runner.invoke(app, ["dev-console", "sdk", "install", APP_RID])

    assert result.exit_code == 2
    assert "RESIDUAL GAP" in result.output


def test_install_failed_exits_nonzero():
    with patch(SERVICE) as service:
        service.return_value.install_sdk_package.return_value = _install_result(
            "failed"
        )
        result = runner.invoke(app, ["dev-console", "sdk", "install", APP_RID])

    assert result.exit_code == 1


def test_install_agent_mode_carries_status_and_warnings():
    with patch(SERVICE) as service:
        service.return_value.install_sdk_package.return_value = _install_result()
        result = runner.invoke(
            app, ["--agent", "dev-console", "sdk", "install", APP_RID]
        )

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "pltr-agent-v1"
    assert envelope["meta"]["result_type"] == "sdk-install"
    assert envelope["meta"]["status"] == "dry-run"
    assert "registry-unverified" in envelope["warnings"]


def test_capabilities_flip_to_implemented_for_dev_console_commands():
    result = runner.invoke(app, ["capabilities", "--format", "json"])

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)
    by_id = {
        entry["capability_id"]: entry for entry in manifest["capabilities"]
    }
    assert by_id["view_osdk_definition"]["status"] == "implemented"
    assert by_id["view_osdk_definition"]["command"] == "dev-console osdk definition"
    assert by_id["install_sdk_package"]["status"] == "implemented"
    assert by_id["install_sdk_package"]["command"] == "dev-console sdk install"
