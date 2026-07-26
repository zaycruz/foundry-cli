"""CLI tests for the osdk command group (service mocked; no network)."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from pltr.cli import app


runner = CliRunner()

CONTEXT = {
    "status": "ok",
    "ontology": {"rid": "ri.ontology.main.ontology.1", "api_name": "main"},
    "entities": {
        "object_types": {
            "count": 2,
            "names": ["Restaurant", "Review"],
            "truncated": False,
        },
        "action_types": {"count": 1, "names": ["addReview"], "truncated": False},
        "query_types": {"count": 0, "names": [], "truncated": False},
        "interface_types": {"count": 0, "names": [], "truncated": False},
        "shared_property_types": {"count": 0, "names": [], "truncated": False},
        "value_types": {"count": 0, "names": [], "truncated": False},
    },
    "osdk": {
        "packages": [
            {
                "name": "@osdk/foundry.ontologies",
                "version": "2.69.0",
                "provenance": "contract-verified",
            }
        ],
        "components": {"OntologyV2": ["list", "get"]},
        "docs": {},
    },
    "sources": ["live ontology via sdk", "vendored package"],
}

EXAMPLES = {
    "status": "ok",
    "language": "typescript",
    "ontology": {"rid": "ri.ontology.main.ontology.1", "api_name": "main"},
    "documentation_examples": [
        {
            "language": "typescript",
            "code": "const page = await client(Restaurant).fetchPage();",
            "source": "palantir-docs",
            "source_url": "https://www.palantir.com/docs/foundry/ontology-sdk/typescript-osdk/",
        }
    ],
    "binding_examples": [
        {
            "kind": "object-fetch",
            "entity": "Restaurant",
            "code": "const page = await client(Restaurant).fetchPage();",
            "generated": True,
            "source": "generated-from-live-ontology",
            "pattern_reference": "https://www.palantir.com/docs/foundry/ontology-sdk/typescript-osdk/",
        }
    ],
    "warnings": [],
    "reason": None,
}


def test_context_command():
    with patch("pltr.commands.osdk.OsdkService") as service:
        service.return_value.sdk_context.return_value = CONTEXT
        result = runner.invoke(app, ["osdk", "context", "--profile", "qa"])
    assert result.exit_code == 0, result.output
    assert "ri.ontology.main.ontology.1" in result.output
    assert "@osdk/foundry.ontologies@2.69.0" in result.output
    service.assert_called_once_with(profile="qa")
    service.return_value.sdk_context.assert_called_once_with(None)


def test_context_ambiguous_exits_nonzero_and_lists_choices():
    with patch("pltr.commands.osdk.OsdkService") as service:
        service.return_value.sdk_context.return_value = {
            "status": "ambiguous",
            "reason": "multiple ontologies are visible",
            "choices": [
                {"rid": "ri.ontology.main.ontology.1", "api_name": "one"},
                {"rid": "ri.ontology.main.ontology.2", "api_name": "two"},
            ],
        }
        result = runner.invoke(app, ["osdk", "context"])
    assert result.exit_code == 1
    assert "UNAVAILABLE" in result.output
    assert "ri.ontology.main.ontology.2" in result.output


def test_examples_command_marks_generated_bindings():
    with patch("pltr.commands.osdk.OsdkService") as service:
        service.return_value.sdk_examples.return_value = EXAMPLES
        result = runner.invoke(app, ["osdk", "examples"])
    assert result.exit_code == 0, result.output
    assert "verbatim from Palantir docs" in result.output
    assert "generated: true" in result.output
    service.return_value.sdk_examples.assert_called_once_with(
        None, language="typescript"
    )


def test_examples_agent_envelope():
    with patch("pltr.commands.osdk.OsdkService") as service:
        service.return_value.sdk_examples.return_value = EXAMPLES
        result = runner.invoke(app, ["--agent", "osdk", "examples"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "pltr-agent-v1"
    assert payload["data"]["binding_examples"][0]["generated"] is True
    assert payload["meta"]["result_type"] == "osdk-examples"


def test_examples_invalid_language_rejected():
    result = runner.invoke(app, ["osdk", "examples", "--language", "java"])
    assert result.exit_code != 0


def test_osdk_commands_registered():
    from pltr.capabilities import registered_command_paths

    paths = registered_command_paths()
    assert {"osdk context", "osdk examples"} <= paths
