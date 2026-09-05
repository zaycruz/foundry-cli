"""
Evaluation suite service wrapper (AIP Evals).

Reads plus a plan-first run trigger backed by the internal ``foundry-evals``
Conjure service (base ``/foundry-evals/api``). All thirteen endpoints below
were captured from the live AIP Evals UI on a live Foundry deployment
via Chrome DevTools Protocol on 2026-09-04; every listed call returned HTTP
200. Capture artifact: /tmp/evals-capture/capture.jsonl (digest:
/tmp/evals-capture/contracts-digest.md). This is "UI capture, live-exercised"
evidence per ``tickets/README.md``.

Suite RIDs look like ``ri.evals..evaluation-suite.<uuid>`` — note the DOUBLE
DOT (empty service segment), server-evidenced.

Config reads (all PUT, all observed with HTTP 200):

- ``PUT /foundry-evals/api/evals/config/v2/target/get-evaluation-suites``
  body ``{"linkedTarget": {"function": "<functionRid>", "type": "function"}}``
  returns ``{"evaluationSuiteRids": [...]}``. Only the ``function`` arm of
  the ``linkedTarget`` union was observed; other target kinds are not
  guessed.
- ``PUT /foundry-evals/api/evals/config/v2/get`` body
  ``{"requests": [{"rid": "<suiteRid>"}]}`` returns
  ``{"evaluationSuites": {rid: {...}}}`` — full v2 suite config (metrics,
  test case definitions, execution backend).
- ``PUT /foundry-evals/api/evals/config/v2/version/get`` body
  ``{"evaluationSuiteRid", "evaluationSuiteVersion"}`` — v2 version read.
- ``PUT /foundry-evals/api/evals/config/get`` body
  ``{"rids": ["<suiteRid>"]}`` — legacy (pre-metrics) config read.
- ``PUT /foundry-evals/api/evals/config/version/get`` body
  ``{"evaluationSuiteRid", "evaluationSuiteVersion"}`` — legacy version
  read.
- ``PUT /foundry-evals/api/evals/config/evaluators/get`` empty body ``{}``
  returns ``{"evaluators": [...]}`` — the evaluator catalog. The capture
  shows no suite scoping in the request; whether a suite filter exists is
  unknown and not guessed.
- ``PUT /foundry-evals/api/evals/config/auto-generated-metric/get`` empty
  body ``{}`` returns ``{"metrics": [...]}``.

Execution reads and the run trigger:

- ``PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/history`` body
  ``{"executionTarget": null, "pageSize": N}`` (the UI also issues
  ``{"pageSize": N}`` without the key) returns ``{"executionsPage": [...]}``.
- ``PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/suggestedExecutionScope``
  body ``{"executionTargets": [ExecutionTarget], "extraResources": []}``
  returns ``{"suggestedScopeItems": [...]}``.
- ``PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/run`` — RUN TRIGGER
  (mutation). Body ``{executionTarget, backendParameters, reportMetadata}``;
  the captured ``backendParameters`` are ``{"type": "evals", "evals":
  {"executionMode": {"type": "projectScoped", ...}, "repeatTestCases":
  {"numTimesToRun": 1}, "testCaseParallelism": 10, "enableAsyncExecution":
  false}}``. The response is ``{buildRid, jobRid, executionId}``. The CLI
  sends a caller-supplied body verbatim (``--definition`` JSON), plan-first:
  dry-run by default, the real PUT behind ``--apply``.
- ``PUT /foundry-evals/api/evals/execute/execution/{suiteRid}/summary``
  body ``{"executionId"}`` returns ``{"summary": {...}}``.
- ``PUT /foundry-evals/api/evals/execute/execution/{suiteRid}/testCases``
  and ``PUT /foundry-evals/api/evals/execute/v3/execution/{suiteRid}/testCases``
  body ``{"executionId", "pageSize"}`` both return
  ``{"testCaseResults": [...]}``; the per-result shapes differ between the
  two variants (both captured).

Known gap (deliberately not implemented): the suite config-WRITE endpoint
was never observed in the capture — the UI appears to embed run-scoped
config in the ``/run`` body. Suite-level config write remains a gap to
capture; see ``tickets/TICKET-007-evaluation-suites.md``.

Responses are passed through as parsed JSON objects with strict
shape-checking: anything that is not a JSON object fails loudly instead of
rendering as a result. Non-2xx statuses raise typed errors via
``foundry_error_from_conjure``.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .base import BaseService
from .errors import foundry_error_from_conjure
from .foundry_internal_client import FoundryInternalClient

_EVALS_API = "foundry-evals/api/evals"


class EvalsShapeError(RuntimeError):
    """Raised when a foundry-evals response is not a loadable JSON object."""


class EvalsService(BaseService):
    """Service wrapper for AIP Evals (evaluation suites and runs)."""

    RUN_CONTRACT = (
        "PUT /foundry-evals/api/evals/execute/v3/{suiteRid}/run with "
        "{executionTarget, backendParameters, reportMetadata}; response "
        "{buildRid, jobRid, executionId}. UI capture via CDP 2026-09-04 "
        "(a live Foundry deployment), HTTP 200."
    )

    def _get_service(self) -> Any:
        """Get the Foundry client (evals calls use the internal API)."""
        return self.client

    def _internal_client(self) -> FoundryInternalClient:
        """Build an internal API client for the active profile."""
        from ..auth.base import ProfileNotFoundError
        from ..config.profiles import ProfileManager

        profile_name = self.profile or ProfileManager().get_active_profile()
        if not profile_name:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'foundry configure configure' to set up authentication."
            )
        return FoundryInternalClient(profile_name)

    def _put(
        self, path: str, body: Mapping[str, Any], context: str
    ) -> Dict[str, Any]:
        """Issue one foundry-evals PUT and return the parsed JSON object.

        Non-2xx statuses raise a typed FoundryApiError; a success payload
        that is not a JSON object fails loudly rather than guessing.
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure("PUT", path, json_body=body)
        except Exception as e:
            raise RuntimeError(
                f"Failed to {context}: {self._describe_error(e)}"
            ) from e

        if not 200 <= status < 300:
            raise foundry_error_from_conjure(status, payload, raw, context=context)
        if not isinstance(payload, Mapping):
            raise EvalsShapeError(
                f"Unverified foundry-evals {context} response shape: expected a "
                f"JSON object, got {str(raw)[:200]!r}. Refusing to guess at "
                "the contract."
            )
        return dict(payload)

    # --- Config reads -------------------------------------------------

    def list_evaluation_suites_for_target(self, function_rid: str) -> List[str]:
        """List evaluation suite RIDs linked to a target function.

        Backed by PUT config/v2/target/get-evaluation-suites. Only the
        ``function`` arm of ``linkedTarget`` was captured, so the target is
        always encoded as ``{"function": rid, "type": "function"}``.
        """
        payload = self._put(
            f"{_EVALS_API}/config/v2/target/get-evaluation-suites",
            {"linkedTarget": {"function": function_rid, "type": "function"}},
            "list evaluation suites",
        )
        rids = payload.get("evaluationSuiteRids")
        if not isinstance(rids, list):
            raise EvalsShapeError(
                "Unverified foundry-evals suite list response shape: expected "
                f"'evaluationSuiteRids' to be a list, got {payload!r}."
            )
        return [str(rid) for rid in rids]

    def get_evaluation_suite_config_v2(self, suite_rid: str) -> Dict[str, Any]:
        """Load the full v2 suite config (metrics, test cases, backend)."""
        return self._put(
            f"{_EVALS_API}/config/v2/get",
            {"requests": [{"rid": suite_rid}]},
            "load evaluation suite config (v2)",
        )

    def get_evaluation_suite_config_v2_version(
        self, suite_rid: str, version: str
    ) -> Dict[str, Any]:
        """Load the v2 suite config pinned to one suite version."""
        return self._put(
            f"{_EVALS_API}/config/v2/version/get",
            {"evaluationSuiteRid": suite_rid, "evaluationSuiteVersion": version},
            "load evaluation suite config version (v2)",
        )

    def get_evaluation_suite_config(self, suite_rid: str) -> Dict[str, Any]:
        """Load the legacy (pre-metrics) suite config."""
        return self._put(
            f"{_EVALS_API}/config/get",
            {"rids": [suite_rid]},
            "load evaluation suite config (legacy)",
        )

    def get_evaluation_suite_config_version(
        self, suite_rid: str, version: str
    ) -> Dict[str, Any]:
        """Load the legacy suite config pinned to one suite version."""
        return self._put(
            f"{_EVALS_API}/config/version/get",
            {"evaluationSuiteRid": suite_rid, "evaluationSuiteVersion": version},
            "load evaluation suite config version (legacy)",
        )

    def get_evaluators(self) -> Dict[str, Any]:
        """Load the evaluator catalog (empty-body read; not suite-scoped)."""
        return self._put(
            f"{_EVALS_API}/config/evaluators/get", {}, "load evaluators"
        )

    def get_auto_generated_metrics(self) -> Dict[str, Any]:
        """Load the auto-generated metric catalog (empty-body read)."""
        return self._put(
            f"{_EVALS_API}/config/auto-generated-metric/get",
            {},
            "load auto-generated metrics",
        )

    # --- Execution reads ----------------------------------------------

    def get_execution_history(
        self, suite_rid: str, page_size: int = 20
    ) -> Dict[str, Any]:
        """Load paged run history for one suite (v3)."""
        return self._put(
            f"{_EVALS_API}/execute/v3/{suite_rid}/history",
            {"executionTarget": None, "pageSize": page_size},
            "load execution history",
        )

    def get_suggested_execution_scope(
        self,
        suite_rid: str,
        execution_targets: Sequence[Mapping[str, Any]],
        extra_resources: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """Load the suggested execution scope for candidate run targets."""
        return self._put(
            f"{_EVALS_API}/execute/v3/{suite_rid}/suggestedExecutionScope",
            {
                "executionTargets": [dict(t) for t in execution_targets],
                "extraResources": list(extra_resources or []),
            },
            "load suggested execution scope",
        )

    def get_execution_summary(
        self, suite_rid: str, execution_id: str
    ) -> Dict[str, Any]:
        """Load one run's summary (aggregated metrics, test case counts)."""
        return self._put(
            f"{_EVALS_API}/execute/execution/{suite_rid}/summary",
            {"executionId": execution_id},
            "load execution summary",
        )

    def get_execution_test_cases(
        self, suite_rid: str, execution_id: str, page_size: int = 1000
    ) -> Dict[str, Any]:
        """Load per-test-case results for one run (v1 result shape)."""
        return self._put(
            f"{_EVALS_API}/execute/execution/{suite_rid}/testCases",
            {"executionId": execution_id, "pageSize": page_size},
            "load execution test cases",
        )

    def get_execution_test_cases_v3(
        self, suite_rid: str, execution_id: str, page_size: int = 50
    ) -> Dict[str, Any]:
        """Load per-test-case results for one run (v3 result shape)."""
        return self._put(
            f"{_EVALS_API}/execute/v3/execution/{suite_rid}/testCases",
            {"executionId": execution_id, "pageSize": page_size},
            "load execution test cases (v3)",
        )

    # --- Run trigger (mutation; plan-first at the command layer) ------

    @staticmethod
    def plan_run(suite_rid: str, run_body: Mapping[str, Any]) -> Dict[str, Any]:
        """Describe a run trigger without issuing it (dry-run payload)."""
        return {
            "mode": "plan",
            "request": {
                "verb": "PUT",
                "path": f"/{_EVALS_API}/execute/v3/{suite_rid}/run",
                "body": dict(run_body),
            },
            "contract": EvalsService.RUN_CONTRACT,
        }

    def trigger_run(
        self, suite_rid: str, run_body: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Trigger one evaluation run.

        The body is sent verbatim (``{executionTarget, backendParameters,
        reportMetadata}`` per the captured contract); the success response
        is ``{buildRid, jobRid, executionId}``.
        """
        return self._put(
            f"{_EVALS_API}/execute/v3/{suite_rid}/run",
            run_body,
            "trigger evaluation run",
        )
