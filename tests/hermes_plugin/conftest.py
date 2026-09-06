"""Test loader for the directory-shaped Hermes plugin."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parents[2] / "integrations" / "hermes-plugin"
PACKAGE_NAME = "foundry_cli_hermes_plugin"


def _load_plugin_package():
    if PACKAGE_NAME in sys.modules:
        return sys.modules[PACKAGE_NAME]
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not create plugin import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


_PLUGIN_PACKAGE = _load_plugin_package()


@pytest.fixture(scope="session")
def plugin_package():
    """Return the plugin package loaded with Hermes-compatible semantics."""
    return _PLUGIN_PACKAGE


@pytest.fixture
def manifest_payload():
    return {
        "schema_version": "foundry-agent-v1",
        "data": {
            "schemaVersion": "foundry-cli-tool-manifest-v1",
            "commands": [
                {
                    "path": ["search"],
                    "stableId": "search",
                    "group": "search",
                    "risk": "read",
                    "description": "Search resources.",
                    "context": {"profile": {"argv": "--profile", "kind": "option"}},
                    "invocation": {
                        "prefixArgv": ["--non-interactive"],
                        "output": {"argv": ["--format", "json"]},
                        "booleanMode": "per-parameter",
                        "optionValueMode": "separate",
                        "positionalOrder": "index",
                    },
                    "parameters": [
                        {
                            "name": "text",
                            "type": "string",
                            "required": True,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "positional", "index": 0},
                            "enum": None,
                            "default": None,
                        },
                        {
                            "name": "limit",
                            "type": "integer",
                            "required": False,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "option", "argv": "--limit"},
                            "enum": None,
                            "default": None,
                        },
                        {
                            "name": "path_prefix",
                            "type": "string",
                            "required": False,
                            "repeatable": True,
                            "nargs": 1,
                            "mapping": {"kind": "option", "argv": "--path-prefix"},
                            "enum": None,
                            "default": None,
                        },
                    ],
                },
                {
                    "path": ["dependency", "resource"],
                    "stableId": "dependency_resource",
                    "group": "dependency",
                    "risk": "unknown",
                    "description": "Assess a resource.",
                    "context": {"profile": {"argv": "--profile", "kind": "option"}},
                    "invocation": {
                        "prefixArgv": ["--non-interactive"],
                        "output": {"argv": ["--format", "json"]},
                        "booleanMode": "per-parameter",
                        "optionValueMode": "separate",
                        "positionalOrder": "index",
                    },
                    "parameters": [
                        {
                            "name": "resource_rid",
                            "type": "string",
                            "required": True,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "positional", "index": 0},
                            "enum": None,
                            "default": None,
                        },
                        {
                            "name": "graph_output",
                            "type": "string",
                            "required": False,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "option", "argv": "--graph-output"},
                            "enum": None,
                            "default": None,
                        },
                        {
                            "name": "change",
                            "type": "string",
                            "required": False,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "option", "argv": "--change"},
                            "enum": None,
                            "default": None,
                        },
                        {
                            "name": "output_mode",
                            "type": "string",
                            "required": False,
                            "repeatable": False,
                            "nargs": 1,
                            "mapping": {"kind": "option", "argv": "--output-mode"},
                            "enum": ["agent", "ci", "graph"],
                            "default": None,
                        },
                    ],
                },
                {
                    "path": ["admin", "group", "get"],
                    "stableId": "admin_group_get",
                    "group": "admin",
                    "risk": "read",
                    "description": "Get a group.",
                    "context": {"profile": None},
                    "invocation": {
                        "prefixArgv": ["--non-interactive"],
                        "output": {"argv": ["--format", "json"]},
                        "booleanMode": "per-parameter",
                        "optionValueMode": "separate",
                        "positionalOrder": "index",
                    },
                    "parameters": [],
                },
                {
                    "path": ["ontology", "object-type-guarded-upsert"],
                    "stableId": "ontology_object_type_guarded_upsert",
                    "group": "ontology",
                    "risk": "read",
                    "description": "Misclassified mutation.",
                    "context": {"profile": None},
                    "invocation": {
                        "prefixArgv": ["--non-interactive"],
                        "output": {"argv": ["--format", "json"]},
                        "booleanMode": "per-parameter",
                        "optionValueMode": "separate",
                        "positionalOrder": "index",
                    },
                    "parameters": [],
                },
            ],
        },
    }
