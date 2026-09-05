"""Emit a machine-readable manifest of the registered CLI commands."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterator, Mapping

import click
import typer

from ..utils.agent_output import (
    agent_mode_enabled,
    buffer_agent_payload,
    render_agent_json,
)


TOOL_MANIFEST_SCHEMA_VERSION = "foundry-cli-tool-manifest-v1"

READ_ONLY_VERBS = frozenset(
    {
        "available-roles",
        "count",
        "current",
        "get",
        "info",
        "list",
        "resolve",
        "search",
        "show",
        "status",
        "validate",
    }
)

app = typer.Typer()


def _parameter_names(parameter: click.Parameter) -> list[str]:
    """Return all declared option spellings in declaration order."""
    return [
        *getattr(parameter, "opts", []),
        *getattr(parameter, "secondary_opts", []),
    ]


def iter_executable_commands(
    command: click.Command, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, click.Command]]:
    """Yield visible executable commands from a Click command tree.

    Groups with ``invoke_without_command`` have executable callbacks in
    addition to their children, so they are part of the command surface too.
    """
    if getattr(command, "hidden", False):
        return

    if isinstance(command, click.Group):
        if prefix and command.invoke_without_command:
            yield " ".join(prefix), command
        for name, child in sorted(command.commands.items()):
            yield from iter_executable_commands(child, (*prefix, name))
        return

    if prefix:
        yield " ".join(prefix), command


def _long_option_names(parameter: click.Option) -> list[str]:
    return [name for name in _parameter_names(parameter) if name.startswith("--")]


def _supported_option_names(parameter: click.Option) -> list[str]:
    return [
        name
        for name in _parameter_names(parameter)
        if name.startswith("--")
        or (len(name) == 2 and name.startswith("-") and name[1].isalpha())
    ]


def _stable_id(path: tuple[str, ...]) -> str:
    normalized_path = "_".join(segment.replace("-", "_") for segment in path)
    if len(normalized_path) <= 56:
        return normalized_path
    group = path[0].replace("-", "_")
    return f"{group}_{hashlib.sha256(' '.join(path).encode()).hexdigest()[:12]}"


def _parameter_type(parameter: click.Parameter) -> str:
    if isinstance(parameter, click.Option) and parameter.is_flag:
        return "boolean"
    if isinstance(parameter.type, click.types.IntParamType):
        return "integer"
    if isinstance(parameter.type, click.types.FloatParamType):
        return "number"
    return "string"


def _risk(path: tuple[str, ...], command: click.Command) -> str:
    if any(
        "--confirm" in _long_option_names(parameter)
        for parameter in command.params
        if isinstance(parameter, click.Option)
    ):
        return "unknown"
    if (
        path[-1].rsplit("-", 1)[-1] in READ_ONLY_VERBS
        or "read-only" in (command.help or "").casefold()
    ):
        return "read"
    return "unknown"


def _parameter_manifest(
    parameter: click.Argument | click.Option,
    *,
    positional_index: int | None = None,
) -> dict[str, Any] | None:
    if parameter.nargs != 1:
        return None
    if isinstance(parameter, click.Option):
        option_names = (
            list(parameter.opts) if parameter.is_flag else _parameter_names(parameter)
        )
        long_names = [name for name in option_names if name.startswith("--")]
        if not long_names:
            return None
        argv = long_names[0]
        aliases = [
            name
            for name in option_names
            if (
                name.startswith("--")
                or (len(name) == 2 and name.startswith("-") and name[1].isalpha())
            )
            and name != argv
        ]
        if parameter.is_flag:
            if not isinstance(parameter.flag_value, bool) or (
                parameter.default is not None
                and not isinstance(parameter.default, bool)
            ):
                return None
            mapping: dict[str, Any] = {
                "kind": "flag",
                "argv": argv,
                "aliases": aliases,
                "activeWhen": parameter.flag_value,
            }
        else:
            mapping = {"kind": "option", "argv": argv, "aliases": aliases}
    else:
        if positional_index is None:
            raise ValueError("positional arguments require an index")
        mapping = {"kind": "positional", "index": positional_index}

    enum: list[str] | None = None
    if isinstance(parameter.type, click.Choice) and all(
        isinstance(choice, str) and choice.strip() == choice and choice
        for choice in parameter.type.choices
    ):
        enum = list(parameter.type.choices)
    help_text = parameter.help if isinstance(parameter, click.Option) else None
    parameter_name = parameter.name or ""

    return {
        "name": parameter.name,
        "description": help_text or parameter_name.replace("_", " "),
        "help": help_text,
        "type": _parameter_type(parameter),
        "required": parameter.required,
        "default": parameter.default
        if isinstance(parameter, click.Option) and parameter.is_flag
        else None,
        "enum": enum,
        "repeatable": parameter.multiple,
        "nargs": 1,
        "mapping": mapping,
    }


def _command_manifest(path: str, command: click.Command) -> dict[str, Any] | None:
    """Build one conservative typed-tool record from Click metadata.

    The CLI has no explicit semantic risk declaration. A conservative read-only
    verb classifier marks known read operations as `read`; every other command is
    `unknown` and requires an interactive confirmation. Commands without JSON
    output or supported parameter shapes are excluded rather than guessed.
    """
    parameters: list[dict[str, Any]] = []
    profile: dict[str, Any] | None = None
    confirmation_argv: list[str] | None = None
    output_supported = False

    for positional_index, parameter in enumerate(
        parameter
        for parameter in command.params
        if isinstance(parameter, click.Argument)
    ):
        record = _parameter_manifest(parameter, positional_index=positional_index)
        if record is None:
            return None
        parameters.append(record)
    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter["mapping"]["kind"] == "positional"
    ]
    if any(not parameter["required"] for parameter in positional_parameters[:-1]):
        return None

    for option in command.params:
        if not isinstance(option, click.Option):
            continue
        long_names = _long_option_names(option)
        if "--format" in long_names:
            output_supported = True
            continue
        if "--profile" in long_names:
            profile = {
                "kind": "option",
                "argv": "--profile",
                "aliases": [
                    name
                    for name in _supported_option_names(option)
                    if name != "--profile"
                ],
            }
            continue
        if "--confirm" in long_names:
            confirmation_argv = ["--confirm"]
        record = _parameter_manifest(option)
        if record is None:
            if option.required:
                return None
            continue
        parameters.append(record)

    if not output_supported:
        return None

    path_segments = tuple(path.split())
    return {
        "stableId": _stable_id(path_segments),
        "group": path_segments[0],
        "path": list(path_segments),
        "description": command.help or path,
        "implementationStatus": "implemented",
        "risk": _risk(path_segments, command),
        "capability": None,
        "service": None,
        "outputContract": None,
        "parameters": parameters,
        "context": {"profile": profile, "ontology": None},
        "invocation": {
            "prefixArgv": ["--non-interactive"],
            "positionalOrder": "index",
            "optionValueMode": "separate",
            "booleanMode": "per-parameter",
            "output": {"format": "json", "argv": ["--format", "json"]},
        },
        **({"confirmationArgv": confirmation_argv} if confirmation_argv else {}),
    }


def build_manifest(
    root_command: click.Command,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic typed-tool manifest consumed by the Pi harness."""
    _ = generated_at  # Retained for callers of the former grammar-manifest helper.
    commands = [
        manifest
        for path, command in iter_executable_commands(root_command)
        if (manifest := _command_manifest(path, command)) is not None
    ]
    commands.sort(key=lambda item: item["path"])

    return {
        "schemaVersion": TOOL_MANIFEST_SCHEMA_VERSION,
        "commands": commands,
    }


def render_manifest(manifest: Mapping[str, Any], *, agent: bool = False) -> str:
    """Serialize the typed tool manifest using direct or shared agent output."""
    if agent:
        return render_agent_json(manifest, meta={"result_type": "tool_manifest"})
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


@app.callback(invoke_without_command=True)
def agent_manifest(ctx: typer.Context) -> None:
    """Emit typed commands that are safe for dynamic agent-tool registration."""
    try:
        manifest = build_manifest(ctx.find_root().command)
        if agent_mode_enabled():
            buffer_agent_payload(manifest, meta={"result_type": "tool_manifest"})
        else:
            typer.echo(render_manifest(manifest), nl=False)
    except Exception as error:
        typer.echo(f"Error emitting agent manifest: {error}", err=True)
        raise typer.Exit(1) from error
