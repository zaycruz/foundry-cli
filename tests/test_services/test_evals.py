"""
Tests for the AIP Evals (foundry-evals) service.
"""

import pytest
from unittest.mock import Mock, patch

from foundry_cli.services.errors import FoundryApiError
from foundry_cli.services.evals import EvalsService, EvalsShapeError

SUITE_RID = "ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000042"
FUNCTION_RID = "ri.function-registry.main.function.00000000-0000-0000-0000-000000000007"
VERSION = "00000000-0000-0005-aba8-7cce25c4e89f"
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
    "backendParameters": {
        "type": "evals",
        "evals": {
            "repeatTestCases": {"numTimesToRun": 1},
            "testCaseParallelism": 10,
            "enableAsyncExecution": False,
        },
    },
    "reportMetadata": {},
}


def _service_with_mock(mock_client_class, payload, status=200, raw="{...}"):
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    mock_client.conjure.return_value = (status, payload, raw)
    return EvalsService(profile="test"), mock_client


class TestEvalsConfigReads:
    """Contract-shape assertions for the config read endpoints."""

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_list_suites_for_target(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"evaluationSuiteRids": [SUITE_RID]}
        )

        result = service.list_evaluation_suites_for_target(FUNCTION_RID)

        assert result == [SUITE_RID]
        mock_client_class.assert_called_once_with("test")
        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/v2/target/get-evaluation-suites",
            json_body={"linkedTarget": {"function": FUNCTION_RID, "type": "function"}},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_list_suites_bad_shape(self, mock_client_class):
        service, _ = _service_with_mock(mock_client_class, {"unexpected": []})

        with pytest.raises(EvalsShapeError, match="evaluationSuiteRids"):
            service.list_evaluation_suites_for_target(FUNCTION_RID)

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_config_v2(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"evaluationSuites": {SUITE_RID: {}}}
        )

        result = service.get_evaluation_suite_config_v2(SUITE_RID)

        assert result == {"evaluationSuites": {SUITE_RID: {}}}
        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/v2/get",
            json_body={"requests": [{"rid": SUITE_RID}]},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_config_v2_version(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"evaluationSuite": {}}
        )

        service.get_evaluation_suite_config_v2_version(SUITE_RID, VERSION)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/v2/version/get",
            json_body={
                "evaluationSuiteRid": SUITE_RID,
                "evaluationSuiteVersion": VERSION,
            },
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_config_legacy(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"evaluationSuites": {}}
        )

        service.get_evaluation_suite_config(SUITE_RID)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/get",
            json_body={"rids": [SUITE_RID]},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_config_legacy_version(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"evaluationSuite": {}}
        )

        service.get_evaluation_suite_config_version(SUITE_RID, VERSION)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/version/get",
            json_body={
                "evaluationSuiteRid": SUITE_RID,
                "evaluationSuiteVersion": VERSION,
            },
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_evaluators_empty_body(self, mock_client_class):
        service, mock_client = _service_with_mock(mock_client_class, {"evaluators": []})

        service.get_evaluators()

        mock_client.conjure.assert_called_once_with(
            "PUT", "foundry-evals/api/evals/config/evaluators/get", json_body={}
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_get_auto_generated_metrics_empty_body(self, mock_client_class):
        service, mock_client = _service_with_mock(mock_client_class, {"metrics": []})

        service.get_auto_generated_metrics()

        mock_client.conjure.assert_called_once_with(
            "PUT",
            "foundry-evals/api/evals/config/auto-generated-metric/get",
            json_body={},
        )


class TestEvalsExecutionReads:
    """Contract-shape assertions for the execution read endpoints."""

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_history(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"executionsPage": []}
        )

        service.get_execution_history(SUITE_RID, page_size=20)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/v3/{SUITE_RID}/history",
            json_body={"executionTarget": None, "pageSize": 20},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_suggested_execution_scope(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"suggestedScopeItems": []}
        )
        target = RUN_BODY["executionTarget"]

        service.get_suggested_execution_scope(SUITE_RID, [target])

        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/v3/{SUITE_RID}/suggestedExecutionScope",
            json_body={"executionTargets": [target], "extraResources": []},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_summary(self, mock_client_class):
        service, mock_client = _service_with_mock(mock_client_class, {"summary": {}})

        service.get_execution_summary(SUITE_RID, EXECUTION_ID)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/execution/{SUITE_RID}/summary",
            json_body={"executionId": EXECUTION_ID},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_test_cases(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"testCaseResults": []}
        )

        service.get_execution_test_cases(SUITE_RID, EXECUTION_ID, page_size=100)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/execution/{SUITE_RID}/testCases",
            json_body={"executionId": EXECUTION_ID, "pageSize": 100},
        )

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_test_cases_v3(self, mock_client_class):
        service, mock_client = _service_with_mock(
            mock_client_class, {"testCaseResults": []}
        )

        service.get_execution_test_cases_v3(SUITE_RID, EXECUTION_ID, page_size=50)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/v3/execution/{SUITE_RID}/testCases",
            json_body={"executionId": EXECUTION_ID, "pageSize": 50},
        )


class TestEvalsRunTrigger:
    """Run trigger is verbatim-body, plan-first at the command layer."""

    def test_plan_run_describes_without_network(self):
        plan = EvalsService.plan_run(SUITE_RID, RUN_BODY)

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "PUT"
        assert plan["request"]["path"] == (
            f"/foundry-evals/api/evals/execute/v3/{SUITE_RID}/run"
        )
        assert plan["request"]["body"] == RUN_BODY
        assert "contract" in plan

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_trigger_run_sends_body_verbatim(self, mock_client_class):
        response = {
            "buildRid": "ri.foundry.main.build.1",
            "jobRid": "ri.foundry.main.job.2",
            "executionId": EXECUTION_ID,
        }
        service, mock_client = _service_with_mock(mock_client_class, response)

        result = service.trigger_run(SUITE_RID, RUN_BODY)

        assert result == response
        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"foundry-evals/api/evals/execute/v3/{SUITE_RID}/run",
            json_body=RUN_BODY,
        )


class TestEvalsErrorHandling:
    """Non-2xx and unverified shapes fail loudly with typed errors."""

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_typed_error_on_failure_status(self, mock_client_class):
        service, _ = _service_with_mock(
            mock_client_class,
            {
                "errorName": "Evals:EvaluationSuiteNotFound",
                "errorCode": "NOT_FOUND",
                "errorInstanceId": "abc",
                "parameters": {"evaluationSuiteRid": SUITE_RID},
            },
            status=404,
        )

        with pytest.raises(FoundryApiError) as exc_info:
            service.get_evaluation_suite_config_v2(SUITE_RID)

        error = exc_info.value
        assert error.error_name == "Evals:EvaluationSuiteNotFound"
        assert error.status_code == 404
        assert error.safe_parameters == {"evaluationSuiteRid": SUITE_RID}

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_unverified_shape_fails_loudly(self, mock_client_class):
        service, _ = _service_with_mock(
            mock_client_class, ["not", "an", "object"], raw="[...]"
        )

        with pytest.raises(EvalsShapeError, match="Unverified"):
            service.get_execution_history(SUITE_RID)

    @patch("foundry_cli.services.evals.FoundryInternalClient")
    def test_transport_error_wrapped(self, mock_client_class):
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")
        service = EvalsService(profile="test")

        with pytest.raises(RuntimeError, match="Failed to load execution history"):
            service.get_execution_history(SUITE_RID)
