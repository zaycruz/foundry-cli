"""
Tests for the Compute Modules service (internal gateway wrapper).
"""

from unittest.mock import Mock, patch

import pytest

from foundry_cli.services.compute import (
    ComputeModulesError,
    ComputeService,
    ComputeSessionNotFoundError,
    ComputeShapeError,
)

DEPLOYED_APP_RID = "ri.foundry.main.deployed-app.00000000-0000-0000-0000-000000000000"
BUILD_JOB_RID = "ri.foundry.main.job.00000000-0000-0000-0000-000000000000"
BUILD_RID = "ri.foundry.main.build.00000000-0000-0000-0000-000000000000"
BRANCH = "master"

CONTOUR_403 = (
    403,
    {
        "errorCode": "PERMISSION_DENIED",
        "errorName": "Contour:InsufficientPermission",
    },
    '{"errorName":"Contour:InsufficientPermission"}',
)


class TestComputeInfoService:
    """Test cases for read-only status/config loads."""

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_status_success(self, mock_client_class):
        """Test loading status returns the raw payload via the verified path."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"state": "RUNNING", "buildJobRid": BUILD_JOB_RID}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = ComputeService(profile="test")
        result = service.get_status(DEPLOYED_APP_RID, BRANCH)

        assert result == payload
        mock_client_class.assert_called_once_with("test")
        mock_client.conjure.assert_called_once_with(
            "GET",
            "contour-backend-multiplexer/api/deployed-apps/"
            f"{DEPLOYED_APP_RID}/{BRANCH}/status",
            json_body=None,
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_config_success(self, mock_client_class):
        """Test loading config returns the raw payload via the verified path."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"rid": DEPLOYED_APP_RID, "type": "FUNCTION"}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = ComputeService(profile="test")
        result = service.get_config(DEPLOYED_APP_RID)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "GET",
            f"contour-backend-multiplexer/api/deployed-apps/{DEPLOYED_APP_RID}/v2",
            json_body=None,
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_status_permission_denied_is_loud(self, mock_client_class):
        """Test the captured 403 contract surfaces honestly, not as not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = CONTOUR_403

        service = ComputeService(profile="test")
        with pytest.raises(
            ComputeModulesError, match="HTTP 403 \\(Contour:InsufficientPermission\\)"
        ):
            service.get_status(DEPLOYED_APP_RID, BRANCH)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_status_route_not_mounted(self, mock_client_class):
        """Test a clear error when the multiplexer route is not mounted."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            404,
            {"errorName": "Route:RouteNotMounted"},
            "{}",
        )

        service = ComputeService(profile="test")
        with pytest.raises(ComputeModulesError, match="not mounted"):
            service.get_status(DEPLOYED_APP_RID, BRANCH)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_status_unverified_shape(self, mock_client_class):
        """Test that a non-object success payload fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["not", "an", "object"], "[...]")

        service = ComputeService(profile="test")
        with pytest.raises(ComputeShapeError, match="Unverified"):
            service.get_status(DEPLOYED_APP_RID, BRANCH)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_config_empty_object_fails_loudly(self, mock_client_class):
        """Test that an empty object is not rendered as a result."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {}, "")

        service = ComputeService(profile="test")
        with pytest.raises(ComputeShapeError, match="Unverified"):
            service.get_config(DEPLOYED_APP_RID)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_status_transport_error_wrapped(self, mock_client_class):
        """Test that transport failures are wrapped."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")

        service = ComputeService(profile="test")
        with pytest.raises(ComputeModulesError, match="Failed to status load"):
            service.get_status(DEPLOYED_APP_RID, BRANCH)


class TestComputeLogsService:
    """Test cases for the two-step telemetry logs flow."""

    @staticmethod
    def _client(mock_client_class, logs_payload=None):
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = [
            (
                200,
                {
                    "runRidsToContainerAndSessionIds": {
                        BUILD_JOB_RID: {
                            "containerRid": "ri.container.main.container.abc",
                            "sessionId": "session-1",
                        }
                    }
                },
                "{...}",
            ),
            (200, logs_payload if logs_payload is not None else {"logs": []}, "{...}"),
        ]
        return mock_client

    @patch("foundry_cli.services.compute.time.time", return_value=1_700_000_000.0)
    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_logs_two_step_flow(self, mock_client_class, _mock_time):
        """Test session resolution then logs/read/v3 with microsecond range."""
        mock_client = self._client(mock_client_class)

        service = ComputeService(profile="test")
        result = service.get_logs(BUILD_JOB_RID)

        assert result["session"] == {
            "containerRid": "ri.container.main.container.abc",
            "sessionId": "session-1",
        }
        expected_to = 1_700_000_000 * 1_000_000
        assert result["request"] == {
            "fromInclusive": expected_to - 24 * 60 * 60 * 1_000_000,
            "toExclusive": expected_to,
            "pageSizeLimit": 100,
            "chronological": True,
        }
        assert result["response"] == {"logs": []}

        session_call, logs_call = mock_client.conjure.call_args_list
        assert session_call.args[0] == "POST"
        assert session_call.args[1] == (
            "foundry-telemetry-service/api/info/sessions/by-run-rids/get-batch"
        )
        assert session_call.kwargs["json_body"] == {"runRids": [BUILD_JOB_RID]}
        assert logs_call.args[1] == (
            "foundry-telemetry-service/api/containers/"
            "ri.container.main.container.abc/sessions/session-1/logs/read/v3"
        )
        assert logs_call.kwargs["json_body"]["fromInclusive"] == (
            expected_to - 24 * 60 * 60 * 1_000_000
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_logs_explicit_range_and_reverse(self, mock_client_class):
        """Test explicit microsecond bounds and reverse chronological order."""
        mock_client = self._client(mock_client_class)

        service = ComputeService(profile="test")
        result = service.get_logs(
            BUILD_JOB_RID,
            from_inclusive=10,
            to_exclusive=20,
            page_size_limit=500,
            chronological=False,
        )

        assert result["request"] == {
            "fromInclusive": 10,
            "toExclusive": 20,
            "pageSizeLimit": 500,
            "chronological": False,
        }
        assert mock_client.conjure.call_count == 2

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_logs_response_passed_through_raw(self, mock_client_class):
        """Test the bundle-derived step-2 shape is not projected."""
        raw_logs = {"events": [{"payload": {"log": {"time": 1}}}]}
        self._client(mock_client_class, logs_payload=raw_logs)

        service = ComputeService(profile="test")
        result = service.get_logs(BUILD_JOB_RID)

        assert result["response"] == raw_logs

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_logs_no_session_is_loud(self, mock_client_class):
        """Test the captured empty-map response maps to a clear not-found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            {"runRidsToContainerAndSessionIds": {}},
            "{...}",
        )

        service = ComputeService(profile="test")
        with pytest.raises(ComputeSessionNotFoundError, match="No telemetry session"):
            service.get_logs(BUILD_JOB_RID)
        # Step 2 must never fire without a resolved session.
        mock_client.conjure.assert_called_once()

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_get_logs_malformed_session_payload(self, mock_client_class):
        """Test a surprising step-1 payload fails loudly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["unexpected"], "[...]")

        service = ComputeService(profile="test")
        with pytest.raises(ComputeShapeError, match="Unverified"):
            service.get_logs(BUILD_JOB_RID)

    def test_get_logs_page_size_limit_validated_before_network(self):
        """Test an out-of-range page size fails before any request."""
        service = ComputeService(profile="test")
        with pytest.raises(ComputeModulesError, match="page_size_limit"):
            service.get_logs(BUILD_JOB_RID, page_size_limit=0)
        with pytest.raises(ComputeModulesError, match="page_size_limit"):
            service.get_logs(BUILD_JOB_RID, page_size_limit=1001)


class TestComputeManagePlans:
    """Test cases for dry-run plans (no network)."""

    def test_plan_start_matches_captured_body(self):
        """Test the start plan carries the captured submitBuild payload."""
        service = ComputeService(profile="test")
        plan = service.plan_start(DEPLOYED_APP_RID, BRANCH)

        assert plan["mode"] == "plan"
        assert plan["request"]["verb"] == "POST"
        assert plan["request"]["path"] == "/build2/api/manager/submitBuild"
        assert plan["request"]["body"] == {
            "branch": BRANCH,
            "branchFallbacks": {"branches": []},
            "buildParameters": {},
            "jobSpecSelections": [
                {
                    "type": "datasets",
                    "datasets": {
                        "datasetRids": [DEPLOYED_APP_RID],
                        "isRequired": True,
                    },
                }
            ],
            "inputFailureStrategies": [],
            "inputSpecOverrides": [],
            "forceBuild": False,
        }

    def test_plan_stop_matches_captured_request(self):
        """Test the stop plan is a bodiless DELETE with the RID in the path."""
        service = ComputeService(profile="test")
        plan = service.plan_stop(BUILD_RID)

        assert plan["request"] == {
            "verb": "DELETE",
            "path": f"/build2/api/manager/builds/{BUILD_RID}",
            "body": {},
        }

    def test_plan_dev_mode_enable_and_disable(self):
        """Test dev-mode plans: until timestamp enables, omission disables."""
        service = ComputeService(profile="test")

        enable = service.plan_dev_mode(DEPLOYED_APP_RID, BRANCH, "2026-07-25T07:00:00Z")
        assert enable["request"]["verb"] == "PUT"
        assert enable["request"]["path"] == (
            "/contour-backend-multiplexer/api/deployed-apps/"
            f"{DEPLOYED_APP_RID}/{BRANCH}/dev-mode"
        )
        assert enable["request"]["body"] == {
            "automaticUpgradesUntil": "2026-07-25T07:00:00Z"
        }

        disable = service.plan_dev_mode(DEPLOYED_APP_RID, BRANCH, None)
        assert disable["request"]["body"] == {}

    def test_plan_execute_matches_captured_body(self):
        """Test the execute plan carries the captured execute payload."""
        service = ComputeService(profile="test")
        plan = service.plan_execute(
            DEPLOYED_APP_RID, BRANCH, "my-query", {"probe": True}
        )

        assert plan["request"]["path"] == (
            "/contour-backend-multiplexer/api/module-group-multiplexer/"
            "compute-modules/jobs/execute"
        )
        assert plan["request"]["body"] == {
            "deployedAppRid": DEPLOYED_APP_RID,
            "deployedAppBranch": BRANCH,
            "queryType": "my-query",
            "query": {"probe": True},
        }

    def test_plan_execute_omits_undefined_query(self):
        """Test a query-less function omits the field rather than nulling it."""
        service = ComputeService(profile="test")
        plan = service.plan_execute(DEPLOYED_APP_RID, BRANCH, "my-query", None)

        assert "query" not in plan["request"]["body"]


class TestComputeManageWrites:
    """Test cases for start/stop/dev-mode writes (behind --apply)."""

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_start_success(self, mock_client_class):
        """Test start returns the raw submitBuild payload."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        payload = {"buildRid": BUILD_RID, "jobsCreated": 1}
        mock_client.conjure.return_value = (200, payload, "{...}")

        service = ComputeService(profile="test")
        result = service.start(DEPLOYED_APP_RID, BRANCH)

        assert result == payload
        mock_client.conjure.assert_called_once_with(
            "POST",
            "build2/api/manager/submitBuild",
            json_body=service._start_body(DEPLOYED_APP_RID, BRANCH),
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_start_captured_400_is_loud(self, mock_client_class):
        """Test the captured 400 contract surfaces honestly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            400,
            {
                "errorCode": "INVALID_ARGUMENT",
                "errorName": "Build2:JobSpecsForDatasetsNotFoundInGraph",
            },
            "{...}",
        )

        service = ComputeService(profile="test")
        with pytest.raises(
            ComputeModulesError,
            match="HTTP 400 \\(Build2:JobSpecsForDatasetsNotFoundInGraph\\)",
        ):
            service.start(DEPLOYED_APP_RID, BRANCH)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_stop_empty_2xx_is_acknowledgment(self, mock_client_class):
        """Test an empty 2xx body maps to an explicit acknowledgment."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (204, "", "")

        service = ComputeService(profile="test")
        result = service.stop(BUILD_RID)

        assert result == {
            "buildRid": BUILD_RID,
            "acknowledged": True,
            "response_empty": True,
        }
        mock_client.conjure.assert_called_once_with(
            "DELETE", f"build2/api/manager/builds/{BUILD_RID}", json_body=None
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_stop_captured_400_is_loud(self, mock_client_class):
        """Test the captured BuildNotFound contract surfaces honestly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            400,
            {"errorCode": "INVALID_ARGUMENT", "errorName": "Build2:BuildNotFound"},
            "{...}",
        )

        service = ComputeService(profile="test")
        with pytest.raises(ComputeModulesError, match="Build2:BuildNotFound"):
            service.stop(BUILD_RID)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_stop_non_object_2xx_fails_loudly(self, mock_client_class):
        """Test that a non-object success payload is a shape error."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, ["stopped"], "[...]")

        service = ComputeService(profile="test")
        with pytest.raises(ComputeShapeError, match="Unverified"):
            service.stop(BUILD_RID)

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_configure_dev_mode_sends_until(self, mock_client_class):
        """Test dev-mode enable sends the captured body."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (204, "", "")

        service = ComputeService(profile="test")
        result = service.configure_dev_mode(
            DEPLOYED_APP_RID, BRANCH, "2026-07-25T07:00:00Z"
        )

        assert result["acknowledged"] is True
        mock_client.conjure.assert_called_once_with(
            "PUT",
            "contour-backend-multiplexer/api/deployed-apps/"
            f"{DEPLOYED_APP_RID}/{BRANCH}/dev-mode",
            json_body={"automaticUpgradesUntil": "2026-07-25T07:00:00Z"},
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_configure_dev_mode_disable_sends_empty_body(self, mock_client_class):
        """Test dev-mode disable omits the field (empty body)."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (204, "", "")

        service = ComputeService(profile="test")
        service.configure_dev_mode(DEPLOYED_APP_RID, BRANCH, None)

        mock_client.conjure.assert_called_once_with(
            "PUT",
            "contour-backend-multiplexer/api/deployed-apps/"
            f"{DEPLOYED_APP_RID}/{BRANCH}/dev-mode",
            json_body={},
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_configure_dev_mode_permission_denied_is_loud(self, mock_client_class):
        """Test the captured 403 edit-permission contract surfaces honestly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = CONTOUR_403

        service = ComputeService(profile="test")
        with pytest.raises(ComputeModulesError, match="HTTP 403"):
            service.configure_dev_mode(DEPLOYED_APP_RID, BRANCH, None)


class TestComputeExecute:
    """Test cases for function execution (behind --apply)."""

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_execute_json_result(self, mock_client_class):
        """Test a JSON-parsable octet-stream body lands under result."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (200, {"answer": 42}, '{"answer":42}')

        service = ComputeService(profile="test")
        result = service.execute(DEPLOYED_APP_RID, BRANCH, "my-query", {"x": 1})

        assert result == {"result": {"answer": 42}}
        mock_client.conjure.assert_called_once_with(
            "POST",
            "contour-backend-multiplexer/api/module-group-multiplexer/"
            "compute-modules/jobs/execute",
            json_body={
                "deployedAppRid": DEPLOYED_APP_RID,
                "deployedAppBranch": BRANCH,
                "queryType": "my-query",
                "query": {"x": 1},
            },
        )

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_execute_non_json_result(self, mock_client_class):
        """Test a non-JSON octet-stream body lands under resultText."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = (
            200,
            "plain text result",
            "plain text result",
        )

        service = ComputeService(profile="test")
        result = service.execute(DEPLOYED_APP_RID, BRANCH, "my-query", None)

        assert result == {"resultText": "plain text result"}

    @patch("foundry_cli.services.compute.FoundryInternalClient")
    def test_execute_captured_403_is_loud(self, mock_client_class):
        """Test the captured submit-permission contract surfaces honestly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.return_value = CONTOUR_403

        service = ComputeService(profile="test")
        with pytest.raises(
            ComputeModulesError, match="HTTP 403 \\(Contour:InsufficientPermission\\)"
        ):
            service.execute(DEPLOYED_APP_RID, BRANCH, "my-query", None)


class TestComputeServiceProfile:
    """Test profile resolution before any network call."""

    def test_without_profile_raises_before_network(self):
        """Test that a missing profile fails before any network call."""
        from foundry_cli.auth.base import ProfileNotFoundError

        service = ComputeService()
        with patch(
            "foundry_cli.config.profiles.ProfileManager.get_active_profile",
            return_value=None,
        ):
            with pytest.raises(ProfileNotFoundError, match="No profile specified"):
                service.get_status(DEPLOYED_APP_RID, BRANCH)
