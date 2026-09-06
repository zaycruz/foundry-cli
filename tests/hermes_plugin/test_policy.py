"""Read policy and artifact containment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from foundry_cli_hermes_plugin.manifest import FoundryManifest
from foundry_cli_hermes_plugin.policy import (
    ArtifactPathError,
    CommandPolicyError,
    PluginSettings,
    Policy,
)


def test_architect_policy_allows_safe_resource_reads(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    policy = Policy.for_profile("foundry-architect", PluginSettings())

    policy.require_read_allowed(manifest.command(("search",)))


def test_architect_policy_denies_admin_reads(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    policy = Policy.for_profile("foundry-architect", PluginSettings())

    with pytest.raises(CommandPolicyError, match="not allowed"):
        policy.require_read_allowed(manifest.command(("admin", "group", "get")))


def test_policy_denies_misclassified_mutation(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    policy = Policy.for_profile("foundry-architect", PluginSettings())

    with pytest.raises(CommandPolicyError, match="not allowed"):
        policy.require_read_allowed(
            manifest.command(("ontology", "object-type-guarded-upsert"))
        )


def test_unknown_profile_fails_closed(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    policy = Policy.for_profile("default", PluginSettings())

    with pytest.raises(CommandPolicyError, match="profile"):
        policy.require_read_allowed(manifest.command(("search",)))


def test_artifact_path_stays_inside_workspace(tmp_path: Path):
    policy = Policy.for_profile("foundry-fde", PluginSettings(workspace=tmp_path))

    resolved = policy.artifact_path("evidence/graph.json")
    assert resolved == (tmp_path / "evidence" / "graph.json").resolve()

    with pytest.raises(ArtifactPathError, match="workspace"):
        policy.artifact_path("../outside.json")

    with pytest.raises(ArtifactPathError, match="relative"):
        policy.artifact_path(str(tmp_path / "absolute.json"))
