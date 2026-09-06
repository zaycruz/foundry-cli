"""Hermes registration seam tests."""

from __future__ import annotations


def test_plugin_registers_the_read_only_toolset(plugin_package):
    registered = []

    class Context:
        profile_name = "foundry-architect"

        def register_tool(self, **kwargs):
            registered.append(kwargs)

    plugin_package.register(Context())

    assert {item["name"] for item in registered} == {
        "foundry_cli_manifest",
        "foundry_cli_capabilities",
        "foundry_cli_read",
        "foundry_cli_dependency_assess",
    }
    assert {item["toolset"] for item in registered} == {"foundry-cli"}
