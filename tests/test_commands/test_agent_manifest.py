"""Tests for the machine-readable CLI grammar manifest."""

import json

import click
from typer.testing import CliRunner

from foundry_cli.cli import app
from foundry_cli.commands.agent_manifest import build_manifest


runner = CliRunner()


def _manifest(result) -> dict:
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_manifest_contains_registered_commands_and_flags() -> None:
    payload = _manifest(runner.invoke(app, ["agent-manifest"]))

    assert set(payload) == {"schemaVersion", "commands"}
    assert payload["schemaVersion"] == "foundry-cli-tool-manifest-v1"
    commands = {tuple(command["path"]): command for command in payload["commands"]}

    object_type_list = commands[("ontology", "object-type-list")]
    assert object_type_list["stableId"] == "ontology_object_type_list"
    assert object_type_list["risk"] == "read"
    assert object_type_list["context"]["profile"]["argv"] == "--profile"
    assert object_type_list["invocation"]["output"]["argv"] == ["--format", "json"]
    parameters = {
        parameter["name"]: parameter for parameter in object_type_list["parameters"]
    }
    assert parameters["ontology_rid"]["mapping"] == {"kind": "positional", "index": 0}
    assert "format" not in parameters

    dataset_files_list = commands[("dataset", "files", "list")]
    assert "dataset_rid" in {
        parameter["name"] for parameter in dataset_files_list["parameters"]
    }
    assert ("capabilities",) in commands


def test_hidden_commands_are_excluded_recursively() -> None:
    def json_option() -> click.Option:
        return click.Option(["--format"], type=click.Choice(["json"]))

    root = click.Group(
        commands={
            "visible": click.Command(
                "visible", help="Visible command", params=[json_option()]
            ),
            "hidden": click.Command("hidden", hidden=True, params=[json_option()]),
            "nested": click.Group(
                commands={
                    "visible": click.Command(
                        "visible", help="Nested command", params=[json_option()]
                    ),
                    "hidden": click.Command(
                        "hidden", hidden=True, params=[json_option()]
                    ),
                }
            ),
        }
    )

    payload = build_manifest(root, generated_at="fixed")

    assert [command["path"] for command in payload["commands"]] == [
        ["nested", "visible"],
        ["visible"],
    ]


def test_manifest_includes_invocable_group_callbacks() -> None:
    def json_option() -> click.Option:
        return click.Option(["--format"], type=click.Choice(["json"]))

    root = click.Group(
        commands={
            "status": click.Group(
                invoke_without_command=True,
                help="Show status",
                params=[json_option()],
                commands={
                    "detail": click.Command(
                        "detail", help="Show details", params=[json_option()]
                    ),
                },
            )
        }
    )

    payload = build_manifest(root, generated_at="fixed")

    assert [command["path"] for command in payload["commands"]] == [
        ["status"],
        ["status", "detail"],
    ]


def test_manifest_emits_optional_apply_flags() -> None:
    root = click.Group(
        commands={
            "publish": click.Command(
                "publish",
                params=[
                    click.Option(["--apply/--no-apply"], default=False),
                    click.Option(["--format"], type=click.Choice(["json"])),
                ],
            )
        }
    )

    payload = build_manifest(root, generated_at="fixed")

    apply = payload["commands"][0]["parameters"][0]
    assert apply == {
        "name": "apply",
        "description": "apply",
        "help": None,
        "type": "boolean",
        "required": False,
        "default": False,
        "enum": None,
        "repeatable": False,
        "nargs": 1,
        "mapping": {
            "kind": "flag",
            "argv": "--apply",
            "aliases": [],
            "activeWhen": True,
        },
    }


def test_manifest_is_stable() -> None:
    first = _manifest(runner.invoke(app, ["agent-manifest"]))
    second = _manifest(runner.invoke(app, ["agent-manifest"]))

    assert first == second


def test_manifest_honors_the_shared_agent_output_contract() -> None:
    result = runner.invoke(app, ["--agent", "agent-manifest"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "foundry-agent-v1"
    assert payload["data"]["schemaVersion"] == "foundry-cli-tool-manifest-v1"


def test_manifest_emission_failure_exits_nonzero(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("serialization failed")

    monkeypatch.setattr("foundry_cli.commands.agent_manifest.render_manifest", fail)

    result = runner.invoke(app, ["agent-manifest"])

    assert result.exit_code == 1
    assert "Error emitting agent manifest: serialization failed" in result.output


def test_manifest_exposes_new_ontology_commands() -> None:
    payload = _manifest(runner.invoke(app, ["agent-manifest"]))
    commands = {command["stableId"]: command for command in payload["commands"]}

    for stable_id in (
        "ontology_object_type_add_property",
        "ontology_action_type_update",
        "ontology_resolve",
    ):
        assert stable_id in commands, f"{stable_id} missing from manifest"

    resolve = commands["ontology_resolve"]
    assert resolve["risk"] == "read"
    assert resolve["path"] == ["ontology", "resolve"]
    resolve_params = {p["name"]: p for p in resolve["parameters"]}
    assert resolve_params["kind"]["enum"] == [
        "object-type",
        "property",
        "action-type",
        "function",
    ]
    assert resolve_params["kind"]["mapping"] == {
        "kind": "option",
        "argv": "--kind",
        "aliases": [],
    }
    assert resolve_params["rid"]["mapping"]["argv"] == "--rid"
    assert resolve_params["object_type"]["mapping"]["argv"] == "--object-type"

    add_property = commands["ontology_object_type_add_property"]
    assert add_property["risk"] == "unknown"
    add_params = {p["name"]: p for p in add_property["parameters"]}
    assert add_params["apply"]["type"] == "boolean"
    assert add_params["apply"]["mapping"] == {
        "kind": "flag",
        "argv": "--apply",
        "aliases": [],
        "activeWhen": True,
    }
    assert add_params["backing_column"]["mapping"]["argv"] == "--backing-column"
    assert add_params["backing_dataset"]["mapping"]["argv"] == "--backing-dataset"
    assert add_params["branch_rid"]["mapping"]["argv"] == "--branch-rid"
    assert add_params["property_type"]["mapping"]["argv"] == "--type"
    assert add_params["property_type"]["enum"] == [
        "STRING",
        "INTEGER",
        "LONG",
        "DOUBLE",
        "BOOLEAN",
        "TIMESTAMP",
        "DATE",
        "ARRAY_STRING",
    ]

    action_update = commands["ontology_action_type_update"]
    assert action_update["risk"] == "unknown"
    update_params = {p["name"]: p for p in action_update["parameters"]}
    assert update_params["apply"]["type"] == "boolean"
    assert update_params["apply"]["mapping"]["argv"] == "--apply"
    assert update_params["action_type"]["mapping"]["argv"] == "--action-type"
    assert update_params["definition"]["mapping"]["argv"] == "--definition"
    assert update_params["branch"]["mapping"]["argv"] == "--branch"
    assert update_params["branch"]["mapping"]["aliases"] == ["-b"]
    assert update_params["branch_rid"]["mapping"]["argv"] == "--branch-rid"
