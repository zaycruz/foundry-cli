"""Contract tests for self-correcting agent error hints.

Trace analysis showed agents burning a third of tool calls on
fail -> tool_search -> retry because error envelopes did not teach the fix.
These tests pin the three observed failure classes: each failing invocation
must carry an actionable ``hint`` field in its error entry, and unrecognized
failures must carry none.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import patch

import click
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from pltr.cli import app
from pltr.services.dependency import DependencyFatalError
from pltr.utils.error_hints import (
    ACTION_TYPE_UPSERT_HINT,
    BRANCH_RID_HINT,
    OBJECT_TYPE_UPSERT_HINT,
    ONTOLOGY_GET_NOT_FOUND_HINT,
    resolve_error_hint,
)

runner = CliRunner()

ONTOLOGY_RID = "ri.ontology.main.ontology.placeholder"


class ObjectTypeNotFound(Exception):
    """Stands in for the SDK's typed not-found error."""


class ActionTypeNotFound(Exception):
    """Stands in for the SDK's typed not-found error."""


def _envelope(result) -> Dict[str, Any]:
    return json.loads(result.stdout)


def _hints(result) -> list:
    return [entry["hint"] for entry in _envelope(result)["errors"] if "hint" in entry]


class TestResolveErrorHint:
    """The mapping fires only on positively recognized conditions."""

    def test_branch_not_found_entry_in_dependency_context(self):
        hint = resolve_error_hint(
            "dependency", entry={"error_class": "branch-not-found"}
        )
        assert hint == BRANCH_RID_HINT

    def test_branch_error_outside_dependency_context_gets_no_hint(self):
        assert (
            resolve_error_hint("dataset", entry={"error_class": "branch-not-found"})
            is None
        )

    def test_typed_not_found_in_ontology_get_context(self):
        error = RuntimeError("Failed to get object type Foo: ...")
        error.__cause__ = ObjectTypeNotFound("not found")
        assert (
            resolve_error_hint("object-type-get", exc=error)
            == ONTOLOGY_GET_NOT_FOUND_HINT
        )
        assert (
            resolve_error_hint("action-type-get", exc=error)
            == ONTOLOGY_GET_NOT_FOUND_HINT
        )

    def test_not_found_outside_get_context_gets_no_hint(self):
        error = RuntimeError("Failed: ...")
        error.__cause__ = ObjectTypeNotFound("not found")
        assert resolve_error_hint("object-type-delete", exc=error) is None

    def test_generic_error_in_get_context_gets_no_hint(self):
        assert (
            resolve_error_hint("object-type-get", exc=RuntimeError("boom")) is None
        )

    def test_upsert_validation_and_usage_entries(self):
        assert (
            resolve_error_hint("object-type-upsert", entry={"type": "validation"})
            == OBJECT_TYPE_UPSERT_HINT
        )
        assert (
            resolve_error_hint("object-type-upsert", entry={"type": "usage"})
            == OBJECT_TYPE_UPSERT_HINT
        )
        assert (
            resolve_error_hint("action-type-upsert", entry={"type": "usage"})
            == ACTION_TYPE_UPSERT_HINT
        )

    def test_upsert_malformed_definition(self):
        error = json.JSONDecodeError("expecting value", "doc", 0)
        assert (
            resolve_error_hint("action-type-upsert", exc=error)
            == ACTION_TYPE_UPSERT_HINT
        )

    def test_unrelated_error_in_upsert_context_gets_no_hint(self):
        assert (
            resolve_error_hint("object-type-upsert", exc=RuntimeError("boom"))
            is None
        )

    def test_no_context_no_hint(self):
        assert resolve_error_hint("", exc=RuntimeError("boom")) is None


class TestDependencyBranchHint:
    """Class 1: --branch master fails; the hint must teach the RID fix."""

    def _invoke(self, argv):
        with (
            patch("pltr.commands.dependency.AuthManager") as auth_constructor,
            patch(
                "pltr.commands.dependency.DependencyGraphService"
            ) as service_constructor,
            patch("pltr.commands.dependency.FoundryInternalClient"),
        ):
            auth_manager = auth_constructor.return_value
            auth_manager.get_current_profile.return_value = "active"
            auth_manager.storage.get_profile.side_effect = lambda profile: {
                "host": f"https://{profile}.example.com"
            }
            service = service_constructor.return_value
            service.resolve_object_type.side_effect = DependencyFatalError(
                "branch-not-found",
                "Employee",
                "object-type.get-full-metadata",
                "BranchNotFound: The branch master was not found",
                False,
                "ctx-1",
            )
            return runner.invoke(app, ["--agent", *argv])

    def test_branch_name_failure_carries_rid_hint(self):
        result = self._invoke(
            ["dependency", "object-type", ONTOLOGY_RID, "Employee", "--branch", "master"]
        )
        assert result.exit_code == 1
        envelope = _envelope(result)
        assert envelope["errors"][0]["error_class"] == "branch-not-found"
        assert envelope["errors"][0]["hint"] == BRANCH_RID_HINT

    def test_other_dependency_fatals_carry_no_hint(self):
        with (
            patch("pltr.commands.dependency.AuthManager") as auth_constructor,
            patch(
                "pltr.commands.dependency.DependencyGraphService"
            ) as service_constructor,
            patch("pltr.commands.dependency.FoundryInternalClient"),
        ):
            auth_manager = auth_constructor.return_value
            auth_manager.get_current_profile.return_value = "active"
            auth_manager.storage.get_profile.side_effect = lambda profile: {
                "host": f"https://{profile}.example.com"
            }
            service = service_constructor.return_value
            service.resolve_object_type.side_effect = DependencyFatalError(
                "permission-denied",
                "Employee",
                "object-type.get-full-metadata",
                "Access denied",
                False,
                "ctx-1",
            )
            result = runner.invoke(
                app,
                ["--agent", "dependency", "object-type", ONTOLOGY_RID, "Employee"],
            )
        assert result.exit_code == 1
        assert _hints(result) == []


class TestOntologyGetNotFoundHint:
    """Class 2: name-probing gets must be pointed at resolve/list."""

    @pytest.mark.parametrize(
        "command,service_path,method,sdk_error",
        [
            (
                "object-type-get",
                "pltr.commands.ontology.ObjectTypeService",
                "get_object_type",
                ObjectTypeNotFound,
            ),
            (
                "action-type-get",
                "pltr.commands.ontology.ActionService",
                "get_action_type",
                ActionTypeNotFound,
            ),
        ],
    )
    def test_not_found_get_carries_resolve_hint(
        self, command, service_path, method, sdk_error
    ):
        error = RuntimeError(f"Failed to get {command} Nope: ...")
        error.__cause__ = sdk_error("not found")
        with patch(service_path) as service_constructor:
            getattr(service_constructor.return_value, method).side_effect = error
            result = runner.invoke(
                app, ["--agent", "ontology", command, ONTOLOGY_RID, "Nope"]
            )
        assert result.exit_code == 1
        assert _hints(result) == [ONTOLOGY_GET_NOT_FOUND_HINT]

    def test_generic_get_failure_carries_no_hint(self):
        with patch("pltr.commands.ontology.ObjectTypeService") as service_constructor:
            service_constructor.return_value.get_object_type.side_effect = RuntimeError(
                "connection reset"
            )
            result = runner.invoke(
                app, ["--agent", "ontology", "object-type-get", ONTOLOGY_RID, "Employee"]
            )
        assert result.exit_code == 1
        assert _hints(result) == []


class TestUpsertInvocationHint:
    """Class 3: bad upsert invocations must name the required arguments."""

    def test_missing_flags_fail_with_usage_hint(self):
        result = runner.invoke(
            app, ["--agent", "ontology", "object-type-upsert", ONTOLOGY_RID]
        )
        assert result.exit_code == 2
        (entry,) = _envelope(result)["errors"]
        assert entry["type"] == "usage"
        assert entry["hint"] == OBJECT_TYPE_UPSERT_HINT

    def test_missing_flags_without_agent_mode_stays_plain_click_error(self):
        result = runner.invoke(app, ["ontology", "object-type-upsert", ONTOLOGY_RID])
        assert result.exit_code == 2
        assert not result.stdout.strip()

    def test_malformed_action_type_definition_carries_hint(self, tmp_path):
        definition = tmp_path / "definition.json"
        definition.write_text("{not valid json")
        result = runner.invoke(
            app,
            [
                "--agent",
                "ontology",
                "action-type-upsert",
                ONTOLOGY_RID,
                "--definition",
                str(definition),
            ],
        )
        assert result.exit_code == 1
        assert _hints(result) == [ACTION_TYPE_UPSERT_HINT]

    def test_dry_run_validation_failure_carries_hint(self):
        with patch("pltr.commands.ontology.ObjectTypeService") as service_constructor:
            service_constructor.return_value.upsert_object_type.return_value = {
                "validation": {
                    "status": "error",
                    "errors": ["SchemaForObjectTypeDatasourceNotFound"],
                }
            }
            result = runner.invoke(
                app,
                [
                    "--agent",
                    "ontology",
                    "object-type-upsert",
                    ONTOLOGY_RID,
                    "--api-name",
                    "employee",
                    "--display-name",
                    "Employee",
                    "--primary-key",
                    "id",
                    "--backing-dataset",
                    "ri.foundry.main.dataset.placeholder",
                ],
            )
        assert result.exit_code == 1
        validation_entries = [
            entry
            for entry in _envelope(result)["errors"]
            if entry.get("type") == "validation"
        ]
        assert len(validation_entries) == 1
        assert validation_entries[0]["hint"] == OBJECT_TYPE_UPSERT_HINT


class TestHintsNameRealCommandsAndFlags:
    """A hint that names a nonexistent command or flag is worse than none."""

    @staticmethod
    def _command(*path: str) -> click.Command:
        command = get_command(app)
        for part in path:
            assert isinstance(command, click.Group), f"{' '.join(path)} is not a group"
            assert part in command.commands, f"missing command: {' '.join(path)}"
            command = command.commands[part]
        return command

    @staticmethod
    def _flags(command: click.Command) -> set:
        flags = set()
        for param in command.params:
            flags.update(param.opts)
            flags.update(getattr(param, "secondary_opts", []))
        return flags

    @pytest.mark.parametrize(
        "path",
        [
            ("ontology", "resolve"),
            ("ontology", "object-type-list"),
            ("ontology", "object-type-guarded-upsert"),
        ],
    )
    def test_hinted_commands_exist(self, path):
        self._command(*path)

    def test_object_type_upsert_flags_exist(self):
        flags = self._flags(self._command("ontology", "object-type-upsert"))
        assert {
            "--api-name",
            "--display-name",
            "--primary-key",
            "--backing-dataset",
            "--apply",
        } <= flags

    def test_action_type_upsert_flags_exist(self):
        flags = self._flags(self._command("ontology", "action-type-upsert"))
        assert {"--definition", "--apply"} <= flags

    def test_dependency_object_type_branch_flag_exists(self):
        flags = self._flags(self._command("dependency", "object-type"))
        assert "--branch" in flags
