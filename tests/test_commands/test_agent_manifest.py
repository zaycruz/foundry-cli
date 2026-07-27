"""Tests for the machine-readable CLI grammar manifest."""

import json

import click
from typer.testing import CliRunner

from pltr.cli import app
from pltr.commands.agent_manifest import build_manifest


runner = CliRunner()


def _manifest(result) -> dict:
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_manifest_contains_registered_commands_and_flags() -> None:
    payload = _manifest(runner.invoke(app, ["agent-manifest"]))

    assert set(payload) == {"schemaVersion", "commands"}
    assert payload["schemaVersion"] == "pltr-cli-tool-manifest-v1"
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
    assert payload["schema_version"] == "pltr-agent-v1"
    assert payload["data"]["schemaVersion"] == "pltr-cli-tool-manifest-v1"


def test_manifest_emission_failure_exits_nonzero(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("serialization failed")

    monkeypatch.setattr("pltr.commands.agent_manifest.render_manifest", fail)

    result = runner.invoke(app, ["agent-manifest"])

    assert result.exit_code == 1
    assert "Error emitting agent manifest: serialization failed" in result.output
