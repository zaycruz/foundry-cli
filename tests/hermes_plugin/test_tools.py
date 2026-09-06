"""Native tool handler tests."""

from __future__ import annotations

import json
from pathlib import Path

from foundry_cli_hermes_plugin.policy import PluginSettings
from foundry_cli_hermes_plugin.tools import PluginRuntime


class FakeContext:
    profile_name = "foundry-architect"


class FakeRunner:
    def __init__(self, manifest_payload):
        self.manifest_payload = manifest_payload
        self.calls = []

    def run(self, argv):
        self.calls.append(list(argv))
        if argv == ["agent-manifest"]:
            return self.manifest_payload
        return {
            "schema_version": "foundry-agent-v1",
            "data": {"result": "ok"},
            "meta": {},
            "warnings": [],
            "errors": [],
            "pagination": None,
            "artifacts": [],
        }


def test_read_handler_returns_validated_cli_result(manifest_payload):
    runner = FakeRunner(manifest_payload)
    runtime = PluginRuntime(
        FakeContext(),
        settings=PluginSettings(),
        runner=runner,
    )

    result = json.loads(
        runtime.read(
            {
                "command_path": ["search"],
                "parameters": {"text": "customer"},
            }
        )
    )

    assert result["data"] == {"result": "ok"}
    assert runner.calls[-1] == [
        "search",
        "customer",
        "--format",
        "json",
    ]


def test_read_handler_fails_closed_for_disallowed_command(manifest_payload):
    runtime = PluginRuntime(
        FakeContext(),
        settings=PluginSettings(),
        runner=FakeRunner(manifest_payload),
    )

    result = json.loads(
        runtime.read(
            {
                "command_path": ["admin", "group", "get"],
                "parameters": {},
            }
        )
    )

    assert "error" in result
    assert "not allowed" in result["error"]


def test_dependency_handler_forces_agent_mode_and_retains_graph_artifact(
    manifest_payload, tmp_path: Path
):
    runner = FakeRunner(manifest_payload)
    runtime = PluginRuntime(
        FakeContext(),
        settings=PluginSettings(workspace=tmp_path),
        runner=runner,
    )

    result = json.loads(
        runtime.dependency_assess(
            {
                "target_type": "resource",
                "target": {"resource_rid": "ri.resource.example"},
                "change": "rename the resource",
                "graph_output": "evidence/graph.json",
                "foundry_profile": "prod",
            }
        )
    )

    assert result["data"] == {"result": "ok"}
    assert runner.calls[-1] == [
        "dependency",
        "resource",
        "ri.resource.example",
        "--graph-output",
        str((tmp_path / "evidence" / "graph.json").resolve()),
        "--change",
        "rename the resource",
        "--output-mode",
        "agent",
        "--profile",
        "prod",
        "--format",
        "json",
    ]


def test_fixed_tools_fail_closed_for_default_profile(manifest_payload):
    class DefaultContext:
        profile_name = "default"

    runtime = PluginRuntime(
        DefaultContext(),
        settings=PluginSettings(),
        runner=FakeRunner(manifest_payload),
    )

    result = json.loads(runtime.manifest({}))

    assert "disabled for Hermes profile" in result["error"]


def test_handlers_always_return_json_on_invalid_input(manifest_payload):
    runtime = PluginRuntime(
        FakeContext(),
        settings=PluginSettings(),
        runner=FakeRunner(manifest_payload),
    )

    result = runtime.read({"command_path": ["search"], "parameters": {}})

    parsed = json.loads(result)
    assert "error" in parsed
