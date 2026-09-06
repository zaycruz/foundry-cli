"""Credential-free contract test against the real local foundry executable."""

from __future__ import annotations

from pathlib import Path

from foundry_cli_hermes_plugin.manifest import MANIFEST_SCHEMA_VERSION, FoundryManifest
from foundry_cli_hermes_plugin.runner import CliRunner, RunnerSettings


REPOSITORY_ROOT = Path(__file__).parents[2]


def test_live_cli_manifest_contract():
    runner = CliRunner(RunnerSettings(working_directory=REPOSITORY_ROOT))

    manifest = FoundryManifest.from_envelope(runner.run(["agent-manifest"]))

    assert manifest.commands
    assert manifest.envelope["data"]["schemaVersion"] == MANIFEST_SCHEMA_VERSION
    assert len(manifest.commands) > 100
