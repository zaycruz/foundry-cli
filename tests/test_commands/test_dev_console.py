"""CLI tests for dev-console OSDK definition reads and SDK installs."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from foundry_cli.cli import app
from foundry_cli.services.dev_console import SdkDefinitionDriftError
from foundry_cli.services.foundry_internal_client import TokenExpiredError

APP_RID = "ri.third-party-applications.main.third-party-application.my-app"
REPO_RID = "ri.artifacts.main.repository.sdk-repo"

runner = CliRunner()

SERVICE = "foundry_cli.commands.dev_console.DeveloperConsoleService"


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
        "coordinates": [
            {"ecosystem": "pypi", "name": "my-app-sdk", "version": "1.2.3"}
        ],
        "steps": [
            {
                "ecosystem": "pypi",
                "package": "my-app-sdk==1.2.3",
                "registry_url": (
                    f"https://foundry.example.com/artifacts/api/repositories/"
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
    assert envelope["schema_version"] == "foundry-agent-v1"
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
    assert envelope["schema_version"] == "foundry-agent-v1"
    assert envelope["meta"]["result_type"] == "sdk-install"
    assert envelope["meta"]["status"] == "dry-run"
    assert "registry-unverified" in envelope["warnings"]


def test_capabilities_flip_to_implemented_for_dev_console_commands():
    result = runner.invoke(app, ["capabilities", "--format", "json"])

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)
    by_id = {entry["capability_id"]: entry for entry in manifest["capabilities"]}
    assert by_id["view_osdk_definition"]["status"] == "implemented"
    assert by_id["view_osdk_definition"]["command"] == "dev-console osdk definition"
    assert by_id["install_sdk_package"]["status"] == "implemented"
    assert by_id["install_sdk_package"]["command"] == "dev-console sdk install"
    assert by_id["connect_to_dev_console_app"]["status"] == "implemented"
    assert by_id["connect_to_dev_console_app"]["command"] == "dev-console connect"
    assert by_id["generate_new_ontology_sdk_version"]["status"] == "implemented"
    assert (
        by_id["generate_new_ontology_sdk_version"]["command"]
        == "dev-console sdk generate"
    )
    assert by_id["convert_to_osdk_react"]["status"] == "implemented"
    assert by_id["convert_to_osdk_react"]["command"] == "dev-console convert-osdk-react"


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


def _connect_result():
    return {
        "application_rid": APP_RID,
        "name": "My App",
        "organization_rid": "ri.multipass..organization.org-1",
        "client_type": "public",
        "grants": {"authorization_code": True, "refresh_token": True},
        "redirect_urls": ["https://app.example.com/auth/callback"],
        "data_scope": {
            "ontology_rid": "ri.ontology.main.ontology.x",
            "objectTypes": 2,
            "linkTypes": 1,
            "actionTypes": 0,
        },
        "status": "connected",
        "mode": "read-only",
        "warnings": ["headless read-only form"],
    }


def test_connect_renders_json_and_calls_service():
    with patch(SERVICE) as service:
        service.return_value.get_connection_context.return_value = _connect_result()
        result = runner.invoke(
            app, ["dev-console", "connect", APP_RID, "--profile", "qa"]
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "connected"
    assert payload["mode"] == "read-only"
    service.assert_called_once_with(profile="qa")
    service.return_value.get_connection_context.assert_called_once_with(APP_RID)


def test_connect_agent_mode_emits_single_envelope():
    with patch(SERVICE) as service:
        service.return_value.get_connection_context.return_value = _connect_result()
        result = runner.invoke(app, ["--agent", "dev-console", "connect", APP_RID])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "foundry-agent-v1"
    assert envelope["meta"]["result_type"] == "dev-console-connect"
    assert envelope["data"]["application_rid"] == APP_RID
    assert "headless read-only form" in envelope["warnings"]


def test_connect_drift_exits_nonzero_and_fails_loud():
    with patch(SERVICE) as service:
        service.return_value.get_connection_context.side_effect = (
            SdkDefinitionDriftError("no 'application' object")
        )
        result = runner.invoke(app, ["dev-console", "connect", APP_RID])

    assert result.exit_code == 1
    assert "DRIFT [application-shape]" in result.output


def test_connect_token_expired_exits_nonzero():
    with patch(SERVICE) as service:
        service.return_value.get_connection_context.side_effect = TokenExpiredError()
        result = runner.invoke(app, ["dev-console", "connect", APP_RID])

    assert result.exit_code == 1
    assert "token-expired" in result.output


# ---------------------------------------------------------------------------
# sdk generate (plan-first; --apply mutates)
# ---------------------------------------------------------------------------


def _generate_plan_result():
    return {
        "application_rid": APP_RID,
        "status": "dry-run",
        "application_version": 6,
        "request": {
            "verb": "POST",
            "path": "/third-party-application-service/api/application-sdks/v2/"
            f"{APP_RID}",
            "body": {"applicationVersion": 6, "npm": {}},
        },
        "contract": "contract-verified against a live deployment",
        "warnings": [],
    }


def _generate_success_result():
    return {
        **_generate_plan_result(),
        "status": "success",
        "sdk_version": "0.9.0",
        "repository_rid": REPO_RID,
        "npm_package_name": "@my-app/sdk",
        "npm_status": "success",
        "poll": {"attempts": 5, "elapsed_seconds": 24.1},
    }


def test_sdk_generate_defaults_to_dry_run_plan():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = _generate_plan_result()
        result = runner.invoke(app, ["dev-console", "sdk", "generate", APP_RID])

    assert result.exit_code == 0, result.output
    assert "SDK GENERATE [dry-run]" in result.output
    assert "Application version: 6" in result.output
    assert '"applicationVersion": 6' in result.output
    assert "nothing was sent" in result.output
    service.return_value.generate_sdk.assert_called_once_with(
        APP_RID, apply=False, wait=True, timeout_seconds=180.0
    )


def test_sdk_generate_passes_apply_no_wait_and_timeout_through():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = {
            **_generate_plan_result(),
            "status": "requested",
            "sdk_version": "0.9.0",
            "npm_status": "requested",
        }
        result = runner.invoke(
            app,
            [
                "dev-console",
                "sdk",
                "generate",
                APP_RID,
                "--apply",
                "--no-wait",
                "--timeout",
                "60",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "SDK GENERATE [requested]" in result.output
    kwargs = service.return_value.generate_sdk.call_args.kwargs
    assert kwargs["apply"] is True
    assert kwargs["wait"] is False
    assert kwargs["timeout_seconds"] == 60.0


def test_sdk_generate_success_renders_version_and_poll():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = _generate_success_result()
        result = runner.invoke(
            app, ["dev-console", "sdk", "generate", APP_RID, "--apply"]
        )

    assert result.exit_code == 0, result.output
    assert "SDK GENERATE [success]" in result.output
    assert "SDK version: 0.9.0" in result.output
    assert "npm status: success" in result.output
    assert "Polled 5 time(s) over 24.1s" in result.output


def test_sdk_generate_failed_exits_nonzero():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = {
            **_generate_success_result(),
            "status": "failed",
            "npm_status": "failure",
        }
        result = runner.invoke(
            app, ["dev-console", "sdk", "generate", APP_RID, "--apply"]
        )

    assert result.exit_code == 1
    assert "SDK GENERATE [failed]" in result.output


def test_sdk_generate_timeout_exits_2():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = {
            **_generate_success_result(),
            "status": "timeout",
            "npm_status": "requested",
            "reason": "sdk-generation-timeout: ...",
        }
        result = runner.invoke(
            app, ["dev-console", "sdk", "generate", APP_RID, "--apply"]
        )

    assert result.exit_code == 2
    assert "TIMEOUT" in result.output


def test_sdk_generate_agent_mode_carries_status_and_errors():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = {
            **_generate_success_result(),
            "status": "timeout",
            "npm_status": "requested",
            "reason": "sdk-generation-timeout: ...",
        }
        result = runner.invoke(
            app, ["--agent", "dev-console", "sdk", "generate", APP_RID, "--apply"]
        )

    assert result.exit_code == 2, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "foundry-agent-v1"
    assert envelope["meta"]["result_type"] == "sdk-generate"
    assert envelope["meta"]["status"] == "timeout"
    assert envelope["errors"][0]["type"] == "timeout"


def test_sdk_generate_agent_mode_success_has_no_errors():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.return_value = _generate_success_result()
        result = runner.invoke(
            app, ["--agent", "dev-console", "sdk", "generate", APP_RID, "--apply"]
        )

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["meta"]["status"] == "success"
    assert envelope["data"]["sdk_version"] == "0.9.0"
    assert not envelope["errors"]


def test_sdk_generate_drift_exits_nonzero_and_fails_loud():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.side_effect = SdkDefinitionDriftError(
            "no integer metadata.applicationVersion"
        )
        result = runner.invoke(app, ["dev-console", "sdk", "generate", APP_RID])

    assert result.exit_code == 1
    assert "DRIFT [sdk-generate-shape]" in result.output


def test_sdk_generate_token_expired_exits_nonzero():
    with patch(SERVICE) as service:
        service.return_value.generate_sdk.side_effect = TokenExpiredError()
        result = runner.invoke(app, ["dev-console", "sdk", "generate", APP_RID])

    assert result.exit_code == 1
    assert "token-expired" in result.output


# ---------------------------------------------------------------------------
# convert-osdk-react
# ---------------------------------------------------------------------------


def _convert_result(status: str = "generated"):
    result = {
        "application_rid": APP_RID,
        "ontology_rid": "ri.ontology.main.ontology.x",
        "output_dir": "/tmp/scaffold",
        "status": status,
        "reason": None,
        "object_types": ["Program"],
        "files": ["/tmp/scaffold/ProgramCard.tsx", "/tmp/scaffold/index.ts"],
        "warnings": [],
    }
    if status == "unresolved":
        result.update(object_types=[], files=[], reason="data-scope-unresolved: ...")
    if status == "conflict":
        result.update(
            files=[],
            conflicts=["/tmp/scaffold/ProgramCard.tsx"],
            reason="output-files-exist: ...",
        )
    return result


def test_convert_renders_generated_files(tmp_path):
    with patch(SERVICE) as service:
        service.return_value.generate_react_scaffold.return_value = _convert_result()
        result = runner.invoke(
            app,
            [
                "dev-console",
                "convert-osdk-react",
                APP_RID,
                "--output-dir",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "CONVERT-OSDK-REACT [generated]" in result.output
    assert "ProgramCard.tsx" in result.output
    kwargs = service.return_value.generate_react_scaffold.call_args
    assert kwargs.args[0] == APP_RID
    assert kwargs.args[1] == tmp_path
    assert kwargs.kwargs["force"] is False


def test_convert_passes_force_through(tmp_path):
    with patch(SERVICE) as service:
        service.return_value.generate_react_scaffold.return_value = _convert_result()
        result = runner.invoke(
            app,
            [
                "dev-console",
                "convert-osdk-react",
                APP_RID,
                "--output-dir",
                str(tmp_path),
                "--force",
            ],
        )

    assert result.exit_code == 0, result.output
    assert (
        service.return_value.generate_react_scaffold.call_args.kwargs["force"] is True
    )


def test_convert_unresolved_exits_2(tmp_path):
    with patch(SERVICE) as service:
        service.return_value.generate_react_scaffold.return_value = _convert_result(
            "unresolved"
        )
        result = runner.invoke(
            app,
            [
                "dev-console",
                "convert-osdk-react",
                APP_RID,
                "--output-dir",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 2
    assert "RESIDUAL GAP" in result.output


def test_convert_conflict_exits_1(tmp_path):
    with patch(SERVICE) as service:
        service.return_value.generate_react_scaffold.return_value = _convert_result(
            "conflict"
        )
        result = runner.invoke(
            app,
            [
                "dev-console",
                "convert-osdk-react",
                APP_RID,
                "--output-dir",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 1
    assert "conflict" in result.output


def test_convert_agent_mode_emits_single_envelope(tmp_path):
    with patch(SERVICE) as service:
        service.return_value.generate_react_scaffold.return_value = _convert_result()
        result = runner.invoke(
            app,
            [
                "--agent",
                "dev-console",
                "convert-osdk-react",
                APP_RID,
                "--output-dir",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "foundry-agent-v1"
    assert envelope["meta"]["result_type"] == "convert-osdk-react"
    assert envelope["meta"]["status"] == "generated"
