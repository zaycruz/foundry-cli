"""
Tests for the `evals` command group.
"""

import json

import typer
from unittest.mock import Mock, patch
from typer.testing import CliRunner

from foundry_cli.commands.evals import app
from foundry_cli.services.errors import FoundryApiError
from foundry_cli.services.evals import EvalsShapeError

SUITE_RID = "ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000042"
FUNCTION_RID = "ri.function-registry.main.function.00000000-0000-0000-0000-000000000007"
EXECUTION_ID = "00000000-0000-0000-0000-000000000099"

RUN_BODY = {
    "executionTarget": {
        "type": "function",
        "function": {
            "ridAndVersion": {
                "functionRid": FUNCTION_RID,
                "functionVersion": "2.18.0",
            }
        },
    },
    "backendParameters": {"type": "evals", "evals": {}},
    "reportMetadata": {},
}

# The module app holds nested sub-apps; register it on a parent (as cli.py
# does) so the tests exercise the real `evals ...` command paths.
root_app = typer.Typer()
root_app.add_typer(app, name="evals")


def _write_definition(tmp_path, body=RUN_BODY):
    definition = tmp_path / "run.json"
    definition.write_text(json.dumps(body))
    return str(definition)


class TestEvalsSuiteListCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_list_success(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_evaluation_suites_for_target.return_value = [SUITE_RID]

        result = self.runner.invoke(
            root_app, ["evals", "suite", "list", "--target", FUNCTION_RID]
        )

        assert result.exit_code == 0
        mock_service.list_evaluation_suites_for_target.assert_called_once_with(
            FUNCTION_RID
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_list_json_format(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_evaluation_suites_for_target.return_value = [SUITE_RID]

        result = self.runner.invoke(
            root_app,
            ["evals", "suite", "list", "--target", FUNCTION_RID, "--format", "json"],
        )

        assert result.exit_code == 0
        assert SUITE_RID in result.stdout

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_list_error(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.list_evaluation_suites_for_target.side_effect = Exception(
            "service unavailable"
        )

        result = self.runner.invoke(
            root_app, ["evals", "suite", "list", "--target", FUNCTION_RID]
        )

        assert result.exit_code == 1
        assert "Error listing evaluation suites" in result.stdout


class TestEvalsSuiteGetCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_v2_default(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config_v2.return_value = {"config": {}}

        result = self.runner.invoke(root_app, ["evals", "suite", "get", SUITE_RID])

        assert result.exit_code == 0
        mock_service.get_evaluation_suite_config_v2.assert_called_once_with(SUITE_RID)

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_with_version(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config_v2_version.return_value = {}

        result = self.runner.invoke(
            root_app, ["evals", "suite", "get", SUITE_RID, "--version", "v1"]
        )

        assert result.exit_code == 0
        mock_service.get_evaluation_suite_config_v2_version.assert_called_once_with(
            SUITE_RID, "v1"
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_legacy(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config.return_value = {}

        result = self.runner.invoke(
            root_app, ["evals", "suite", "get", SUITE_RID, "--legacy"]
        )

        assert result.exit_code == 0
        mock_service.get_evaluation_suite_config.assert_called_once_with(SUITE_RID)

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_legacy_version(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config_version.return_value = {}

        result = self.runner.invoke(
            root_app,
            ["evals", "suite", "get", SUITE_RID, "--legacy", "--version", "v1"],
        )

        assert result.exit_code == 0
        mock_service.get_evaluation_suite_config_version.assert_called_once_with(
            SUITE_RID, "v1"
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_typed_error(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config_v2.side_effect = FoundryApiError(
            "suite not found", error_name="Evals:EvaluationSuiteNotFound"
        )

        result = self.runner.invoke(root_app, ["evals", "suite", "get", SUITE_RID])

        assert result.exit_code == 1
        assert "suite not found" in result.stdout

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_get_unverified_shape(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluation_suite_config_v2.side_effect = EvalsShapeError(
            "Unverified foundry-evals response shape"
        )

        result = self.runner.invoke(root_app, ["evals", "suite", "get", SUITE_RID])

        assert result.exit_code == 1
        assert "Unverified" in result.stdout


class TestEvalsCatalogCommands:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_evaluators(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_evaluators.return_value = {"evaluators": []}

        result = self.runner.invoke(root_app, ["evals", "suite", "evaluators"])

        assert result.exit_code == 0
        mock_service.get_evaluators.assert_called_once_with()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_auto_metrics(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_auto_generated_metrics.return_value = {"metrics": []}

        result = self.runner.invoke(root_app, ["evals", "suite", "auto-metrics"])

        assert result.exit_code == 0
        mock_service.get_auto_generated_metrics.assert_called_once_with()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_suggested_scope(self, mock_service_class, tmp_path):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_suggested_execution_scope.return_value = {
            "suggestedScopeItems": []
        }
        definition = _write_definition(tmp_path, RUN_BODY["executionTarget"])

        result = self.runner.invoke(
            root_app,
            [
                "evals",
                "suite",
                "suggested-scope",
                SUITE_RID,
                "--execution-target",
                definition,
            ],
        )

        assert result.exit_code == 0
        mock_service.get_suggested_execution_scope.assert_called_once_with(
            SUITE_RID, [RUN_BODY["executionTarget"]]
        )


class TestEvalsRunReadCommands:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_run_list(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_execution_history.return_value = {"executionsPage": []}

        result = self.runner.invoke(
            root_app, ["evals", "run", "list", SUITE_RID, "--page-size", "10"]
        )

        assert result.exit_code == 0
        mock_service.get_execution_history.assert_called_once_with(
            SUITE_RID, page_size=10
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_run_summary(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_execution_summary.return_value = {"summary": {}}

        result = self.runner.invoke(
            root_app, ["evals", "run", "summary", SUITE_RID, EXECUTION_ID]
        )

        assert result.exit_code == 0
        mock_service.get_execution_summary.assert_called_once_with(
            SUITE_RID, EXECUTION_ID
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_run_test_cases_default(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_execution_test_cases.return_value = {"testCaseResults": []}

        result = self.runner.invoke(
            root_app, ["evals", "run", "test-cases", SUITE_RID, EXECUTION_ID]
        )

        assert result.exit_code == 0
        mock_service.get_execution_test_cases.assert_called_once_with(
            SUITE_RID, EXECUTION_ID, page_size=1000
        )

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_run_test_cases_v3(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.get_execution_test_cases_v3.return_value = {"testCaseResults": []}

        result = self.runner.invoke(
            root_app, ["evals", "run", "test-cases", SUITE_RID, EXECUTION_ID, "--v3"]
        )

        assert result.exit_code == 0
        mock_service.get_execution_test_cases_v3.assert_called_once_with(
            SUITE_RID, EXECUTION_ID, page_size=1000
        )


class TestEvalsRunTriggerCommand:
    def setup_method(self):
        self.runner = CliRunner()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_trigger_plan_default_issues_no_run(self, mock_service_class, tmp_path):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_run.return_value = {
            "mode": "plan",
            "request": {"verb": "PUT", "path": "/run", "body": RUN_BODY},
        }
        mock_service.get_suggested_execution_scope.return_value = {
            "suggestedScopeItems": []
        }
        definition = _write_definition(tmp_path)

        result = self.runner.invoke(
            root_app,
            ["evals", "run", "trigger", SUITE_RID, "--definition", definition],
        )

        assert result.exit_code == 0
        mock_service.plan_run.assert_called_once_with(SUITE_RID, RUN_BODY)
        mock_service.get_suggested_execution_scope.assert_called_once_with(
            SUITE_RID, [RUN_BODY["executionTarget"]]
        )
        mock_service.trigger_run.assert_not_called()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_trigger_apply_issues_run(self, mock_service_class, tmp_path):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.trigger_run.return_value = {
            "buildRid": "ri.foundry.main.build.1",
            "jobRid": "ri.foundry.main.job.2",
            "executionId": EXECUTION_ID,
        }
        definition = _write_definition(tmp_path)

        result = self.runner.invoke(
            root_app,
            [
                "evals",
                "run",
                "trigger",
                SUITE_RID,
                "--definition",
                definition,
                "--apply",
            ],
        )

        assert result.exit_code == 0
        mock_service.trigger_run.assert_called_once_with(SUITE_RID, RUN_BODY)
        mock_service.get_suggested_execution_scope.assert_not_called()

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_trigger_stdin_definition(self, mock_service_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.plan_run.return_value = {"mode": "plan"}
        mock_service.get_suggested_execution_scope.return_value = {}

        result = self.runner.invoke(
            root_app,
            ["evals", "run", "trigger", SUITE_RID, "--definition", "-"],
            input=json.dumps(RUN_BODY),
        )

        assert result.exit_code == 0
        mock_service.plan_run.assert_called_once_with(SUITE_RID, RUN_BODY)

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_trigger_invalid_json_fails(self, mock_service_class, tmp_path):
        definition = tmp_path / "run.json"
        definition.write_text("{not json")

        result = self.runner.invoke(
            root_app,
            ["evals", "run", "trigger", SUITE_RID, "--definition", str(definition)],
        )

        assert result.exit_code == 1
        assert "Invalid JSON" in result.stdout

    @patch("foundry_cli.commands.evals.EvalsService")
    def test_trigger_apply_error(self, mock_service_class, tmp_path):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.trigger_run.side_effect = FoundryApiError(
            "invalid execution target", error_name="Evals:InvalidExecutionTarget"
        )
        definition = _write_definition(tmp_path)

        result = self.runner.invoke(
            root_app,
            [
                "evals",
                "run",
                "trigger",
                SUITE_RID,
                "--definition",
                definition,
                "--apply",
            ],
        )

        assert result.exit_code == 1
        assert "invalid execution target" in result.stdout
