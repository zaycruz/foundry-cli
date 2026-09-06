"""Manifest parsing and argument compilation tests."""

from __future__ import annotations

import pytest

from foundry_cli_hermes_plugin.manifest import (
    ManifestError,
    FoundryManifest,
)


def test_manifest_compiles_typed_positional_and_option_arguments(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)

    command = manifest.command(("search",))
    argv = manifest.compile(
        command,
        {"text": "customer;touch /tmp/nope", "limit": 25, "path_prefix": ["a", "b"]},
    )

    assert argv == [
        "search",
        "customer;touch /tmp/nope",
        "--limit",
        "25",
        "--path-prefix",
        "a",
        "--path-prefix",
        "b",
        "--format",
        "json",
    ]


def test_manifest_compiles_profile_as_a_command_option(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    command = manifest.command(("search",))

    argv = manifest.compile(
        command,
        {"text": "customer", "foundry_profile": "prod"},
    )

    assert argv[-4:] == ["--profile", "prod", "--format", "json"]


def test_manifest_rejects_positional_flag_injection(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)

    with pytest.raises(ManifestError, match="must not start"):
        manifest.compile(manifest.command(("search",)), {"text": "--help"})


def test_manifest_rejects_unknown_parameters(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)

    with pytest.raises(ManifestError, match="Unknown parameter"):
        manifest.compile(manifest.command(("search",)), {"text": "x", "shell": "id"})


def test_manifest_rejects_missing_required_parameters(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)

    with pytest.raises(ManifestError, match="Missing required parameter"):
        manifest.compile(manifest.command(("search",)), {})


def test_manifest_rejects_wrong_types_and_enum_values(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)
    command = manifest.command(("search",))

    with pytest.raises(ManifestError, match="must be an integer"):
        manifest.compile(command, {"text": "x", "limit": "many"})

    dependency = manifest.command(("dependency", "resource"))
    with pytest.raises(ManifestError, match="must be one of"):
        manifest.compile(
            dependency,
            {"resource_rid": "ri.resource.x", "output_mode": "unsafe"},
        )


def test_manifest_rejects_incompatible_envelopes(manifest_payload):
    broken = dict(manifest_payload)
    broken["schema_version"] = "other-contract"

    with pytest.raises(ManifestError, match="schema_version"):
        FoundryManifest.from_envelope(broken)


def test_manifest_summary_is_bounded(manifest_payload):
    manifest = FoundryManifest.from_envelope(manifest_payload)

    summary = manifest.summary(group="search", include_parameters=False)

    assert summary["command_count"] == 4
    assert summary["commands"] == [
        {
            "path": ["search"],
            "stable_id": "search",
            "group": "search",
            "risk": "read",
            "description": "Search resources.",
        }
    ]
    assert "parameters" not in summary["commands"][0]
