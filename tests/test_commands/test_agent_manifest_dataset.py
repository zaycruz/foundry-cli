"""Manifest coverage for the dataset schema mutation commands."""

import json

from typer.testing import CliRunner

from foundry_cli.cli import app


runner = CliRunner()


def _command(payload: dict, stable_id: str) -> dict:
    for command in payload["commands"]:
        if command["stableId"] == stable_id:
            return command
    raise AssertionError(f"{stable_id} missing from the agent manifest")


def _parameters(command: dict) -> dict:
    return {parameter["name"]: parameter for parameter in command["parameters"]}


def test_dataset_schema_update_manifest_entry() -> None:
    result = runner.invoke(app, ["agent-manifest"])
    assert result.exit_code == 0, result.output
    update = _command(json.loads(result.stdout), "dataset_schema_update")

    assert update["path"] == ["dataset", "schema", "update"]
    assert update["risk"] == "unknown"
    assert update["context"]["profile"]["argv"] == "--profile"

    parameters = _parameters(update)
    assert parameters["dataset_rid"]["mapping"] == {"kind": "positional", "index": 0}
    assert parameters["apply"]["type"] == "boolean"
    assert parameters["apply"]["default"] is False
    assert parameters["apply"]["mapping"] == {
        "kind": "flag",
        "argv": "--apply",
        "aliases": [],
        "activeWhen": True,
    }
    assert parameters["branch"]["type"] == "string"
    assert parameters["branch"]["mapping"]["argv"] == "--branch"
    assert parameters["expected_schema_version"]["type"] == "string"
    assert (
        parameters["expected_schema_version"]["mapping"]["argv"]
        == "--expected-schema-version"
    )
    assert parameters["add_field"]["repeatable"] is True
    assert parameters["fields_json"]["mapping"]["argv"] == "--fields-json"


def test_dataset_schema_set_manifest_entry() -> None:
    result = runner.invoke(app, ["agent-manifest"])
    assert result.exit_code == 0, result.output
    set_command = _command(json.loads(result.stdout), "dataset_schema_set")

    assert set_command["path"] == ["dataset", "schema", "set"]
    assert set_command["risk"] == "unknown"
    assert set_command["context"]["profile"]["argv"] == "--profile"

    parameters = _parameters(set_command)
    assert parameters["dataset_rid"]["mapping"] == {"kind": "positional", "index": 0}
    assert parameters["expected_schema_version"]["type"] == "string"
    assert (
        parameters["expected_schema_version"]["mapping"]["argv"]
        == "--expected-schema-version"
    )
    assert parameters["branch"]["mapping"]["argv"] == "--branch"
    assert parameters["transaction_rid"]["mapping"]["argv"] == "--transaction-rid"
