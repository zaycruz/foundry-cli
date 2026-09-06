"""CLI tests for the platform-sdk command group (service mocked)."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from foundry_cli.cli import app


runner = CliRunner()

LISTING = {
    "status": "ok",
    "sdk": "foundry-platform-sdk",
    "version": "1.95.0",
    "sdk_root": "/venv/foundry_sdk/v2",
    "namespace_count": 1,
    "namespaces": {
        "ontologies": {
            "resource_count": 1,
            "method_count": 2,
            "resources": {
                "Ontology": {
                    "module": "foundry_sdk.v2.ontologies.ontology",
                    "methods": [
                        {
                            "name": "get",
                            "signature": "(self, ontology)",
                            "summary": "Get an ontology.",
                            "docstring": "Get an ontology.",
                        },
                        {
                            "name": "list",
                            "signature": "(self)",
                            "summary": "List ontologies.",
                            "docstring": "List ontologies.",
                        },
                    ],
                }
            },
        }
    },
    "sources": ["/venv/foundry_sdk/v2"],
}

METHOD_REF = {
    "status": "ok",
    "kind": "method",
    "namespace": "ontologies",
    "resource": "Ontology",
    "name": "get",
    "signature": "(self, ontology)",
    "summary": "Get an ontology.",
    "docstring": "Get an ontology.\n\nFull details.",
    "sdk": "foundry-platform-sdk",
    "version": "1.95.0",
}


def test_api_list_table():
    with patch("foundry_cli.commands.platform_sdk.PlatformSdkService") as service:
        service.return_value.list_apis.return_value = LISTING
        result = runner.invoke(app, ["platform-sdk", "api", "list"])
    assert result.exit_code == 0, result.output
    assert "foundry-platform-sdk==1.95.0" in result.output
    assert "Ontology: get, list" in result.output


def test_api_list_json():
    with patch("foundry_cli.commands.platform_sdk.PlatformSdkService") as service:
        service.return_value.list_apis.return_value = LISTING
        result = runner.invoke(app, ["platform-sdk", "api", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["namespaces"]["ontologies"]["method_count"] == 2


def test_api_reference_method():
    with patch("foundry_cli.commands.platform_sdk.PlatformSdkService") as service:
        service.return_value.api_reference.return_value = METHOD_REF
        result = runner.invoke(
            app, ["platform-sdk", "api", "reference", "ontologies.Ontology.get"]
        )
    assert result.exit_code == 0, result.output
    assert "ontologies.Ontology.get(self, ontology)" in result.output
    assert "Full details." in result.output
    service.return_value.api_reference.assert_called_once_with(
        "ontologies.Ontology.get"
    )


def test_api_reference_not_found_exits_nonzero():
    with patch("foundry_cli.commands.platform_sdk.PlatformSdkService") as service:
        service.return_value.api_reference.return_value = {
            "status": "not-found",
            "reason": "no namespace 'nope' in the installed SDK",
            "available": ["ontologies"],
        }
        result = runner.invoke(app, ["platform-sdk", "api", "reference", "nope"])
    assert result.exit_code == 1
    assert "NOT FOUND" in result.output
    assert "ontologies" in result.output


def test_agent_envelope():
    with patch("foundry_cli.commands.platform_sdk.PlatformSdkService") as service:
        service.return_value.list_apis.return_value = LISTING
        result = runner.invoke(app, ["--agent", "platform-sdk", "api", "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "foundry-agent-v1"
    assert payload["data"]["version"] == "1.95.0"
    assert payload["meta"]["result_type"] == "platform-sdk-apis"


def test_platform_sdk_commands_registered():
    from foundry_cli.capabilities import registered_command_paths

    paths = registered_command_paths()
    assert {"platform-sdk api list", "platform-sdk api reference"} <= paths
