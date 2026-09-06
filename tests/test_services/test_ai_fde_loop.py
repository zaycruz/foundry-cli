"""
Tests for the CLI-side AI FDE agent loop (services/ai_fde_loop.py).
"""

import base64
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from foundry_cli.services.ai_fde_loop import (
    ACTION_TYPE_PARAMETERS_QUERY,
    LATEST_FUNCTION_VERSION_QUERY,
    AgentLoop,
    CompletedResponse,
    LlmResponseShapeError,
    LlmSession,
    UnverifiedContract,
    build_tool_usage_item,
    hidden_item_output,
    wrap_context_item,
)
from foundry_cli.services.errors import FoundryApiError

THREAD_ID = "00000000-0000-0000-0000-000000000001"
VERSION = "00000000-0000-0000-0000-000000000002"
NEW_VERSION = "00000000-0000-0000-0000-000000000003"
SUITE_RID = "ri.evals..evaluation-suite.00000000-0000-0000-0000-000000000004"
ACTION_TYPE_RID = "ri.actions.main.action-type.00000000-0000-0000-0000-000000000005"
PARAMETER_RID = "ri.actions.main.parameter.00000000-0000-0000-0000-000000000006"
FUNCTION_RID = "ri.function-registry.main.function.00000000-0000-0000-0000-000000000007"
SKILL_RID = "ri.aip-agents..skill.00000000-0000-0000-0000-000000000008"
OBJECT_TYPE_RID = "ri.ontology.main.object-type.00000000-0000-0000-0000-000000000009"

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _events(output, usage=None):
    """Build a captured-shape event array around one completed output list."""
    return [
        {
            "type": "success",
            "success": {
                "type": "openAiResponses",
                "openAiResponses": {
                    "type": "created",
                    "created": {"id": "resp_1", "sequenceNumber": 0},
                },
            },
        },
        {
            "type": "success",
            "success": {
                "type": "openAiResponses",
                "openAiResponses": {
                    "type": "completed",
                    "completed": {
                        "id": "resp_1",
                        "output": output,
                        "status": "COMPLETED",
                        "usage": usage
                        or {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                    },
                },
            },
        },
    ]


def _text_output(text):
    return [
        {
            "type": "outputMessage",
            "outputMessage": {
                "id": "msg_1",
                "status": "COMPLETED",
                "content": [{"type": "text", "text": {"text": text}}],
            },
        }
    ]


def _call_output(name, arguments, call_id="call_abc"):
    return [
        {
            "type": "functionToolCall",
            "functionToolCall": {
                "arguments": arguments,
                "callId": call_id,
                "id": "fc_1",
                "name": name,
                "status": "COMPLETED",
            },
        }
    ]


def _completed(output, usage=None):
    return CompletedResponse(
        output=output,
        usage=usage or {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        response_id="resp_1",
        model="gpt-5.6-sol",
    )


def make_loop(llm_responses, approve="always", **kwargs):
    """Build an AgentLoop with a mocked thread service and scripted LLM."""
    service = kwargs.pop("service", None) or Mock()
    service.create_thread.return_value = {"id": THREAD_ID, "version": VERSION}
    service.update_thread_items.return_value = {
        "metadata": {"threadVersion": NEW_VERSION}
    }
    llm = Mock()
    llm.complete.side_effect = [
        r if isinstance(r, CompletedResponse) else _completed(r) for r in llm_responses
    ]
    loop = AgentLoop(
        profile="test",
        approve=approve,
        service=service,
        llm_session=llm,
        **kwargs,
    )
    return loop, service, llm


class TestLlmSession:
    def test_build_request_body_discriminators(self):
        session = LlmSession(profile="test")
        body = session.build_request_body(
            thread_id=THREAD_ID,
            token="token-123",
            instructions="inst",
            input_items=[{"type": "item", "item": {"type": "inputMessage"}}],
            tools=[{"type": "function"}],
        )
        # The attribution user is the bearer token itself (live-verified).
        assert body["attribution"] == {
            "type": "userAttributionV2",
            "userAttributionV2": {"user": "token-123", "application": "AI_FDE"},
        }
        assert body["requestPriority"] == "CRITICAL"
        assert body["sessionId"] == THREAD_ID
        request = body["request"]
        assert request["type"] == "openAiResponses"
        responses = request["openAiResponses"]
        assert responses["instructions"] == {"text": "inst", "type": "text"}
        assert responses["toolChoice"] == {"auto": {}, "type": "auto"}
        assert responses["reasoning"] == {"effort": "MEDIUM", "summary": "AUTO"}
        assert responses["include"] == ["REASONING_ENCRYPTED_CONTENT"]

    @patch("foundry_cli.services.ai_fde_loop.requests.request")
    @patch("foundry_cli.services.ai_fde_loop.CredentialStorage")
    def test_complete_transport(self, mock_storage, mock_request):
        mock_storage.return_value.get_profile.return_value = {
            "host": "example.palantirfoundry.com",
            "token": "token-123",
        }
        events = _events(_text_output("hello"))
        response = Mock()
        response.status_code = 200
        response.json.return_value = events
        response.text = json.dumps(events)
        mock_request.return_value = response

        session = LlmSession(profile="test", model="GPT_5_6_SOL")
        completed = session.complete(
            thread_id=THREAD_ID, instructions="i", input_items=[], tools=[]
        )

        call = mock_request.call_args
        assert call.kwargs["method"] == "PUT"
        assert call.kwargs["url"] == (
            "https://example.palantirfoundry.com/language-model-service/api/"
            "llm/v3/completion/GPT_5_6_SOL/streamCompletionChunk"
        )
        assert call.kwargs["headers"]["Authorization"] == "Bearer token-123"
        assert call.kwargs["headers"]["Accept"] == "application/octet-stream"
        assert call.kwargs["timeout"] == 240.0
        assert completed.output[0]["type"] == "outputMessage"
        assert completed.usage["totalTokens"] == 15

    @patch("foundry_cli.services.ai_fde_loop.requests.request")
    @patch("foundry_cli.services.ai_fde_loop.CredentialStorage")
    def test_complete_error_preserves_fields(self, mock_storage, mock_request):
        mock_storage.return_value.get_profile.return_value = {
            "host": "example.palantirfoundry.com",
            "token": "token-123",
        }
        payload = {
            "errorName": "InvalidModel",
            "errorInstanceId": "instance-1",
            "message": "bad model",
        }
        response = Mock()
        response.status_code = 400
        response.json.return_value = payload
        response.text = json.dumps(payload)
        mock_request.return_value = response

        session = LlmSession(profile="test")
        with pytest.raises(FoundryApiError) as exc_info:
            session.complete(
                thread_id=THREAD_ID, instructions="i", input_items=[], tools=[]
            )
        assert exc_info.value.error_name == "InvalidModel"
        assert exc_info.value.error_instance_id == "instance-1"

    def test_parse_probe_fixture(self):
        events = json.loads((FIXTURES / "stream_completion_toolcall.json").read_text())
        completed = LlmSession.parse_events(events)
        assert len(completed.output) == 1
        call = completed.output[0]["functionToolCall"]
        assert call["name"] == "load_documentation"
        assert call["callId"] == "call_Aaaaaaaaaaaaaaaaaaaaaaaaa"
        assert json.loads(call["arguments"]) == {"pageIds": ["foundry-docs/overview"]}
        assert completed.usage["totalTokens"] == 124

    def test_parse_events_requires_completed(self):
        with pytest.raises(LlmResponseShapeError, match="completed"):
            LlmSession.parse_events(
                [
                    {
                        "type": "success",
                        "success": {
                            "type": "openAiResponses",
                            "openAiResponses": {"type": "created", "created": {}},
                        },
                    }
                ]
            )

    def test_parse_events_requires_array(self):
        with pytest.raises(LlmResponseShapeError, match="JSON array"):
            LlmSession.parse_events({"not": "a list"})


class TestAgentLoopBasics:
    def test_single_turn_text_response(self):
        loop, service, llm = make_loop([_text_output("done")])
        report = loop.run("Investigate the failing run")

        assert report["status"] == "completed"
        assert report["turns"] == 1
        assert report["finalText"] == "done"
        assert report["toolsCalled"] == 0
        assert report["threadId"] == THREAD_ID
        service.create_thread.assert_called_once()
        # First write: the user message. Second write: the assistant item.
        assert service.update_thread_items.call_count == 2
        first = service.update_thread_items.call_args_list[0]
        assert first.args[1] == VERSION
        user_item = first.args[3][0]
        assert user_item["typeAndVersion"]["contextItemType"] == "user-message"
        second = service.update_thread_items.call_args_list[1]
        assert second.args[1] == NEW_VERSION
        assistant_item = second.args[3][0]
        assert (
            assistant_item["typeAndVersion"]["contextItemType"] == "assistant-message"
        )
        assert assistant_item["content"][0]["response"]["status"] == "completed"
        assert assistant_item["content"][0]["response"]["content"] == [
            {"type": "text", "text": "done"}
        ]

    def test_request_input_and_tools_shape(self):
        loop, _, llm = make_loop([_text_output("ok")])
        loop.run("hello")

        kwargs = llm.complete.call_args.kwargs
        assert kwargs["thread_id"] == THREAD_ID
        assert "cliNotes" in kwargs["instructions"]
        assert kwargs["tools"]  # the registered captured specs
        first_input = kwargs["input_items"][0]
        assert first_input["type"] == "item"
        message = first_input["item"]
        assert message["type"] == "inputMessage"
        assert message["inputMessage"]["role"] == "USER"
        text = message["inputMessage"]["content"][0]["text"]
        assert 'contextItemType="user-message"' in text
        assert "hello" in text

    def test_tool_subset_restricts_offered_specs(self):
        loop, _, llm = make_loop(
            [_text_output("ok")], tool_names=["list_evaluation_runs"]
        )
        loop.run("hello")
        tools = llm.complete.call_args.kwargs["tools"]
        assert [t["function"]["name"] for t in tools] == ["list_evaluation_runs"]

    def test_unknown_tool_name_rejected(self):
        with pytest.raises(ValueError, match="unknown tools"):
            AgentLoop(profile="test", tool_names=["not_a_tool"])

    def test_max_turns_cutoff(self):
        loop, _, llm = make_loop(
            [
                _call_output(
                    "list_evaluation_runs",
                    '{"evaluationSuiteRid": "r", "pageToken": null}',
                ),
                _call_output(
                    "list_evaluation_runs",
                    '{"evaluationSuiteRid": "r", "pageToken": null}',
                ),
            ],
            evals_service=Mock(),
        )
        report = loop.run("loop forever", max_turns=2)
        assert report["status"] == "max-turns-reached"
        assert report["turns"] == 2
        assert llm.complete.call_count == 2


class TestToolCallFlow:
    def test_call_id_uuid_rewriting_and_write_back(self):
        evals = Mock()
        evals.get_execution_history.return_value = {"executionsPage": []}
        loop, service, llm = make_loop(
            [
                _call_output(
                    "list_evaluation_runs",
                    json.dumps({"evaluationSuiteRid": SUITE_RID, "pageToken": None}),
                    call_id="call_llm_id",
                ),
                _text_output("all runs listed"),
            ],
            evals_service=evals,
        )
        report = loop.run("list the runs")

        assert report["status"] == "completed"
        assert report["toolsCalled"] == 1
        evals.get_execution_history.assert_called_once_with(SUITE_RID, page_size=20)

        # The second LLM request must carry the rewritten UUID callId (never
        # the LLM's call_xxx id) on both the call and the output.
        second_input = llm.complete.call_args_list[1].kwargs["input_items"]
        call_items = [
            i for i in second_input if i["item"]["type"] == "functionToolCall"
        ]
        output_items = [
            i for i in second_input if i["item"]["type"] == "functionToolCallOutput"
        ]
        assert len(call_items) == 1 and len(output_items) == 1
        call_id = call_items[0]["item"]["functionToolCall"]["callId"]
        assert call_id != "call_llm_id"
        assert output_items[0]["item"]["functionToolCallOutput"]["callId"] == call_id
        output_text = output_items[0]["item"]["functionToolCallOutput"]["output"]
        assert f'contextItemId="{call_id}"' in output_text
        assert 'contextItemType="tool-usage"' in output_text

        # The thread write-back: tool-usage item with the same UUID and the
        # parsed tool request, then the assistant message.
        written_types = []
        tool_usage_item = None
        for call in service.update_thread_items.call_args_list[1:]:
            for item in call.args[3]:
                written_types.append(item["typeAndVersion"]["contextItemType"])
                if item["typeAndVersion"]["contextItemType"] == "tool-usage":
                    tool_usage_item = item
        assert "tool-usage" in written_types
        assert "assistant-message" in written_types
        assert tool_usage_item["contextItemId"] == call_id
        content = tool_usage_item["content"][0]
        assert content["toolName"] == "list_evaluation_runs"
        assert content["toolRequest"] == {
            "evaluationSuiteRid": SUITE_RID,
            "pageToken": None,
        }
        assert content["toolResponse"] == {"state": "completed", "contextItemIds": None}

    def test_fail_closed_tool_returns_explanation_to_model(self):
        loop, _, llm = make_loop(
            [
                _call_output("load_documentation", '{"pageIds": ["a"]}'),
                _text_output("cannot load docs"),
            ]
        )
        report = loop.run("load the docs")
        assert report["status"] == "completed"
        second_input = llm.complete.call_args_list[1].kwargs["input_items"]
        output_item = next(
            i for i in second_input if i["item"]["type"] == "functionToolCallOutput"
        )
        output_text = output_item["item"]["functionToolCallOutput"]["output"]
        assert "not executable" in output_text
        assert "fail closed" in output_text

    def test_documentation_executor_raises_typed_error(self):
        loop, _, _ = make_loop([_text_output("x")])
        with pytest.raises(UnverifiedContract) as exc_info:
            loop._exec_unverified_documentation("load_documentation", {})
        assert exc_info.value.tool == "load_documentation"


class TestApprovalGate:
    def _action_call(self):
        return _call_output(
            "execute_action",
            json.dumps(
                {
                    "actionTypeRid": ACTION_TYPE_RID,
                    "ontologyBranchRid": None,
                    "parameters": [],
                }
            ),
        )

    def _loop_with_action(self, approve, **kwargs):
        client = Mock()
        client.graphql.return_value = Mock(
            errors=[],
            status="ok",
            data={"actionTypeBranch": {"latest": {"parameters": []}}},
        )
        client.conjure.side_effect = [
            (
                200,
                {
                    "type": "validResponse",
                    "validResponse": {"results": {}, "parameterResults": {}},
                },
                "{}",
            ),
            (200, {"outcome": {"type": "success"}}, "{}"),
        ]
        loop, service, llm = make_loop(
            [self._action_call(), _text_output("acted")],
            approve=approve,
            internal_client=client,
            **kwargs,
        )
        return loop, service, llm, client

    def test_interactive_approve_executes(self):
        loop, _, _, client = self._loop_with_action(
            "interactive", confirm=lambda _msg: True
        )
        report = loop.run("do the action")
        assert report["toolCalls"][0]["state"] == "completed"
        assert client.conjure.call_count == 2

    def test_interactive_deny_skips_execution(self):
        loop, service, _, client = self._loop_with_action(
            "interactive", confirm=lambda _msg: False
        )
        report = loop.run("do the action")
        assert report["toolCalls"][0]["state"] == "rejected"
        client.conjure.assert_not_called()
        tool_usage = service.update_thread_items.call_args_list[1].args[3][0]
        assert tool_usage["content"][0]["toolResponse"]["state"] == "rejected"

    def test_always_auto_approves(self):
        loop, _, _, client = self._loop_with_action("always")
        report = loop.run("do the action")
        assert report["toolCalls"][0]["approved"] is True
        assert client.conjure.call_count == 2

    def test_never_declines_writes_but_runs_reads(self):
        evals = Mock()
        evals.get_execution_history.return_value = {"executionsPage": []}
        loop, _, llm, client = self._loop_with_action("never", evals_service=evals)
        # One response carrying both a write and a read call.
        llm.complete.side_effect = [
            _completed(
                _call_output(
                    "execute_action",
                    json.dumps(
                        {
                            "actionTypeRid": ACTION_TYPE_RID,
                            "ontologyBranchRid": None,
                            "parameters": [],
                        }
                    ),
                    call_id="call_write",
                )
                + _call_output(
                    "list_evaluation_runs",
                    json.dumps({"evaluationSuiteRid": SUITE_RID, "pageToken": None}),
                    call_id="call_read",
                )
            ),
            _completed(_text_output("mixed")),
        ]
        report = loop.run("do both")
        states = {c["name"]: c["state"] for c in report["toolCalls"]}
        assert states["execute_action"] == "rejected"
        assert states["list_evaluation_runs"] == "completed"
        evals.get_execution_history.assert_called_once()
        client.conjure.assert_not_called()

    def test_interactive_without_confirm_channel_denies(self):
        loop, _, _, client = self._loop_with_action("interactive", confirm=None)
        report = loop.run("do the action")
        assert report["toolCalls"][0]["state"] == "rejected"
        client.conjure.assert_not_called()


class TestOntologySqlQuery:
    def _arrow_b64(self):
        import pyarrow as pa
        import pyarrow.ipc as ipc

        table = pa.table(
            {
                "nodeId": pa.array(["n1", "n2"], type=pa.string()),
                "sortOrder": pa.array([1, 2], type=pa.int32()),
                "tags": pa.array([["a", "b"], None], type=pa.list_(pa.string())),
            }
        )
        sink = io.BytesIO()
        with ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return base64.b64encode(sink.getvalue()).decode()

    def test_sql_query_contract_and_serialization(self):
        client = Mock()
        client.conjure.side_effect = [
            (
                200,
                {"objectTypes": [{"objectType": {"id": "ns.resolution-tree-1"}}]},
                "{}",
            ),
            (200, {"type": "sync", "sync": {"result": self._arrow_b64()}}, "{}"),
        ]
        loop, _, _ = make_loop([_text_output("x")], internal_client=client)
        payload = loop._exec_ontology_sql_query(
            "ontology_sql_query",
            {
                "queries": [
                    {
                        "query": "SELECT t.`nodeId` FROM `t` AS t LIMIT 10",
                        "ontologyBranchRid": None,
                    }
                ],
                "sources": [
                    {
                        "alias": "t",
                        "source": {
                            "type": "objectType",
                            "objectTypeRid": OBJECT_TYPE_RID,
                        },
                    }
                ],
            },
        )

        sql_call = client.conjure.call_args_list[1]
        assert sql_call.args[0] == "POST"
        assert "sql-endpoint/v1/queries/query" in sql_call.args[1]
        body = sql_call.kwargs["json_body"]
        assert body["querySpec"]["dialect"] == "SPARK"
        assert body["querySpec"]["tableProviders"] == {
            "t": {
                "objectSet": {
                    "objectSet": {
                        "base": {"objectTypeId": "ns.resolution-tree-1"},
                        "type": "base",
                    },
                    "columnMappings": {},
                },
                "type": "objectSet",
            }
        }
        assert body["executionParams"] == {
            "resultFormat": "ARROW",
            "defaultBranchIds": [],
            "resultMode": "SYNC",
            "rowLimit": 100,
        }
        assert "<ontologySql>" in payload
        assert '<ontology-sql-table rowCount="2">' in payload
        assert 'type="STRING" name="nodeId"' in payload
        assert 'type="INTEGER" name="sortOrder"' in payload
        assert 'type="ARRAY" name="tags"' in payload
        assert "nodeId|sortOrder|tags" in payload
        assert "n1|1|[a,b]" in payload
        assert "n2|2|null" in payload

    def test_sql_query_branch_fails_closed(self):
        loop, _, _ = make_loop([_text_output("x")], internal_client=Mock())
        with pytest.raises(UnverifiedContract, match="branch"):
            loop._exec_ontology_sql_query(
                "ontology_sql_query",
                {
                    "queries": [
                        {
                            "query": "SELECT 1",
                            "ontologyBranchRid": "ri.ontology.main.branch.x",
                        }
                    ],
                    "sources": [
                        {
                            "alias": "t",
                            "source": {
                                "type": "objectType",
                                "objectTypeRid": OBJECT_TYPE_RID,
                            },
                        }
                    ],
                },
            )


class TestEvalsTools:
    def test_list_evaluation_runs_page_token_fails_closed(self):
        loop, _, _ = make_loop([_text_output("x")], evals_service=Mock())
        with pytest.raises(UnverifiedContract, match="pagination"):
            loop._exec_list_evaluation_runs(
                "list_evaluation_runs",
                {"evaluationSuiteRid": SUITE_RID, "pageToken": "tok"},
            )

    def test_get_test_case_results_uses_v3(self):
        evals = Mock()
        evals.get_execution_test_cases_v3.return_value = {"testCaseResults": []}
        loop, _, _ = make_loop([_text_output("x")], evals_service=evals)
        loop._exec_get_test_case_results(
            "get_test_case_results",
            {
                "evaluationSuiteRid": SUITE_RID,
                "executionId": "exec-1",
                "pageToken": None,
                "pageSize": 25,
            },
        )
        evals.get_execution_test_cases_v3.assert_called_once_with(
            SUITE_RID, "exec-1", page_size=25
        )

    def _suite_config(self):
        return {
            "evaluationSuites": {
                SUITE_RID: {
                    "evaluationSuite": {
                        "rid": SUITE_RID,
                        "executionBackend": {
                            "type": "evals",
                            "evals": {
                                "testCases": {
                                    "providedParametersSchema": [
                                        {
                                            "id": "uuid-discrepancy",
                                            "name": "discrepancy",
                                        }
                                    ]
                                }
                            },
                        },
                        "executionTargets": [
                            {
                                "locator": {
                                    "type": "function",
                                    "function": FUNCTION_RID,
                                },
                                "generatedParametersSchema": [
                                    {"id": "uuid-out", "name": "matchedErrorNodeIds"}
                                ],
                            }
                        ],
                    }
                }
            }
        }

    def _run_loop(self):
        evals = Mock()
        evals.get_evaluation_suite_config_v2.return_value = self._suite_config()
        evals.trigger_run.return_value = {
            "buildRid": "b",
            "jobRid": "j",
            "executionId": "e",
        }
        client = Mock()
        client.graphql.return_value = Mock(
            errors=[],
            status="ok",
            data={"function": {"latestVersion": {"version": "2.18.0"}}},
        )
        loop, _, _ = make_loop(
            [_text_output("x")], evals_service=evals, internal_client=client
        )
        return loop, evals, client

    def test_run_evaluation_suite_builds_captured_body(self):
        loop, evals, client = self._run_loop()
        result = loop._exec_run_evaluation_suite(
            "run_evaluation_suite",
            {
                "evaluationSuiteRid": SUITE_RID,
                "branch": {"mainBranch": True},
                "parameterMappings": [
                    {
                        "targetInputName": "discrepancy",
                        "testCaseParameterName": "discrepancy",
                    }
                ],
                "staticInputs": None,
                "experiment": None,
                "timesToRunEachTest": 10,
                "testCaseParallelism": None,
                "executionMode": None,
                "forceTargetsToExecuteInProjectScopedMode": True,
            },
        )
        assert json.loads(result)["executionId"] == "e"
        client.graphql.assert_called_once_with(
            "LatestFunctionVersionQuery",
            LATEST_FUNCTION_VERSION_QUERY,
            {"functionRid": FUNCTION_RID},
        )
        suite_rid, body = evals.trigger_run.call_args.args
        assert suite_rid == SUITE_RID
        target = body["executionTarget"]["function"]
        assert target["ridAndVersion"] == {
            "functionRid": FUNCTION_RID,
            "functionVersion": "2.18.0",
        }
        assert target["inputParameterMapping"] == {
            "discrepancy": {"parameter": "uuid-discrepancy", "type": "parameter"}
        }
        assert target["outputParameterMapping"] == {
            "multiple": {
                "projectedFields": {"matchedErrorNodeIds": "uuid-out"},
                "type": "multiple",
            }
        }
        backend = body["backendParameters"]["evals"]
        assert backend["repeatTestCases"] == {"numTimesToRun": 10}
        assert backend["testCaseParallelism"] == 10
        assert backend["executionMode"] == {
            "projectScoped": {
                "extraResources": [],
                "forceTargetsToExecuteInProjectScopedMode": True,
            },
            "type": "projectScoped",
        }
        assert body["reportMetadata"]["Source"] == {
            "string": "AI FDE",
            "type": "string",
        }

    def test_run_evaluation_suite_static_inputs_fail_closed(self):
        loop, evals, _ = self._run_loop()
        with pytest.raises(UnverifiedContract, match="static inputs"):
            loop._exec_run_evaluation_suite(
                "run_evaluation_suite",
                {
                    "evaluationSuiteRid": SUITE_RID,
                    "branch": {"mainBranch": True},
                    "parameterMappings": [],
                    "staticInputs": [{"targetInputName": "x", "value": "1"}],
                    "experiment": None,
                },
            )
        evals.trigger_run.assert_not_called()

    def test_run_evaluation_suite_non_main_branch_fails_closed(self):
        loop, evals, _ = self._run_loop()
        with pytest.raises(UnverifiedContract, match="mainBranch"):
            loop._exec_run_evaluation_suite(
                "run_evaluation_suite",
                {
                    "evaluationSuiteRid": SUITE_RID,
                    "branch": {"globalBranchRid": "ri.branch..branch.x"},
                    "parameterMappings": [],
                    "staticInputs": None,
                    "experiment": None,
                },
            )
        evals.trigger_run.assert_not_called()


class TestExecuteAction:
    def _parameters_response(self):
        return {
            "actionTypeBranch": {
                "latest": {
                    "parameters": [
                        {
                            "id": "bucketNode",
                            "rid": PARAMETER_RID,
                            "type": {
                                "objectType": {
                                    "id": "ns.resolution-tree-1",
                                    "latest": {
                                        "primaryKeyPropertiesV2": [
                                            {
                                                "id": "node-id",
                                                "type": {
                                                    "__typename": "ObjectTypePropertyType_String"
                                                },
                                            }
                                        ]
                                    },
                                },
                                "__typename": "ActionParameterType_Object",
                            },
                        }
                    ]
                }
            }
        }

    def _loop(self, conjure_side_effect):
        client = Mock()
        client.graphql.return_value = Mock(
            errors=[], status="ok", data=self._parameters_response()
        )
        client.conjure.side_effect = conjure_side_effect
        loop, _, _ = make_loop([_text_output("x")], internal_client=client)
        return loop, client

    def _args(self):
        return {
            "actionTypeRid": ACTION_TYPE_RID,
            "ontologyBranchRid": None,
            "parameters": [
                {
                    "parameterId": "bucketNode",
                    "value": {
                        "type": "staticValue",
                        "staticValue": {"baseType": "object", "value": "bucket__1"},
                    },
                }
            ],
        }

    def test_validate_then_apply_with_captured_bodies(self):
        loop, client = self._loop(
            [
                (
                    200,
                    {
                        "type": "validResponse",
                        "validResponse": {"results": {}, "parameterResults": {}},
                    },
                    "{}",
                ),
                (200, {"outcome": {"type": "success"}}, "{}"),
            ]
        )
        result = loop._exec_execute_action("execute_action", self._args())
        assert json.loads(result)["outcome"]["type"] == "success"

        client.graphql.assert_called_once_with(
            "ActionTypeParametersQuery",
            ACTION_TYPE_PARAMETERS_QUERY,
            {"actionTypeRid": ACTION_TYPE_RID, "ontologyBranchRid": None},
        )
        validate_call, apply_call = client.conjure.call_args_list
        assert "actions/api/actions/validate" in validate_call.args[1]
        assert f"owningRid={ACTION_TYPE_RID}" in validate_call.args[1]
        validate_body = validate_call.kwargs["json_body"]
        assert validate_body["parameters"] == {
            PARAMETER_RID: {
                "objectLocator": {
                    "objectTypeId": "ns.resolution-tree-1",
                    "primaryKey": {
                        "node-id": {"string": "bucket__1", "type": "string"}
                    },
                },
                "type": "objectLocator",
            }
        }
        assert validate_body["parametersPrefill"] == {"all": {}, "type": "all"}
        assert apply_call.args[1] == "actions/api/actionsV2"
        apply_body = apply_call.kwargs["json_body"]
        assert apply_body["actionContext"] == {
            "branchRid": None,
            "loadActionEdits": True,
            "parametersPrefill": {"all": {}, "type": "all"},
        }
        assert apply_body["parameters"] == validate_body["parameters"]

    def test_validation_failure_blocks_apply(self):
        loop, client = self._loop(
            [
                (
                    200,
                    {
                        "type": "validResponse",
                        "validResponse": {
                            "results": {"rule-1": {"type": "invalidResult"}}
                        },
                    },
                    "{}",
                )
            ]
        )
        with pytest.raises(FoundryApiError, match="validation failed"):
            loop._exec_execute_action("execute_action", self._args())
        assert client.conjure.call_count == 1  # validate only, never apply

    def test_scalar_parameter_fails_closed(self):
        loop, _ = self._loop([])
        args = self._args()
        args["parameters"][0]["value"]["staticValue"] = {
            "baseType": "string",
            "value": "x",
        }
        with pytest.raises(UnverifiedContract, match="object"):
            loop._exec_execute_action("execute_action", args)


class TestStateTools:
    def test_change_mode_returns_captured_serialization(self):
        loop, _, _ = make_loop([_text_output("x")])
        payload = loop._exec_change_mode(
            "change_mode", {"modeConfig": {"type": "functionsEditing", "evals": True}}
        )
        assert payload == (
            '<modeChange>{"type":"functionsEditing","evals":true}</modeChange>'
        )
        assert loop._mode == "functionsEditing"

    def test_enable_disable_capabilities_adjust_tool_set(self):
        loop, _, _ = make_loop(
            [_text_output("x")],
            tool_names=["change_mode", "enable_capabilities", "disable_capabilities"],
        )
        payload = loop._exec_enable_capabilities(
            "enable_capabilities", {"capabilities": ["executeAction"]}
        )
        assert '<enableCapabilities>["executeAction"]</enableCapabilities>' in payload
        assert "execute_action" in loop._active_tools
        loop._exec_disable_capabilities(
            "disable_capabilities", {"capabilities": ["executeAction"]}
        )
        assert "execute_action" not in loop._active_tools

    def test_unknown_capability_is_reported_not_invented(self):
        loop, _, _ = make_loop([_text_output("x")])
        payload = loop._exec_enable_capabilities(
            "enable_capabilities", {"capabilities": ["notepad"]}
        )
        assert "notepad" in payload
        assert "ignored" in payload

    def test_manage_context_hide_and_unhide(self):
        evals = Mock()
        evals.get_execution_history.return_value = {"executionsPage": []}
        loop, _, llm = make_loop(
            [
                _call_output(
                    "list_evaluation_runs",
                    json.dumps({"evaluationSuiteRid": SUITE_RID, "pageToken": None}),
                ),
                _text_output("done"),
            ],
            evals_service=evals,
        )
        loop.run("produce a tool output")
        second_input = llm.complete.call_args_list[1].kwargs["input_items"]
        output_item = next(
            i for i in second_input if i["item"]["type"] == "functionToolCallOutput"
        )
        hidden_id = output_item["item"]["functionToolCallOutput"]["callId"]

        payload = loop._exec_manage_context(
            "manage_context",
            {
                "contextItemIds": [hidden_id],
                "action": {"type": "hide", "assistantSummary": "done"},
            },
        )
        assert "1 context items hidden" in payload
        assert hidden_id in loop._hidden
        assert (
            "hiddenContextItem"
            in (output_item["item"]["functionToolCallOutput"]["output"])
        )

        # Unhide restores the original payload.
        payload = loop._exec_manage_context(
            "manage_context",
            {"contextItemIds": [hidden_id], "action": {"type": "unhide"}},
        )
        assert "1 context items restored" in payload
        assert (
            "executionsPage"
            in (output_item["item"]["functionToolCallOutput"]["output"])
        )


class TestClarificationAndSkill:
    def test_clarification_non_interactive_returns_assumption_guidance(self):
        loop, _, _ = make_loop([_text_output("x")], clarification_handler=None)
        payload = loop._exec_request_clarification_from_user(
            "request_clarification_from_user",
            {"questions": [{"type": "freeText", "question": "which run?"}]},
        )
        assert "reasonable assumptions" in payload

    def test_clarification_interactive_delegates(self):
        handler = Mock(return_value="the latest run")
        loop, _, _ = make_loop([_text_output("x")], clarification_handler=handler)
        payload = loop._exec_request_clarification_from_user(
            "request_clarification_from_user", {"questions": [{"q": 1}]}
        )
        assert payload == "the latest run"
        handler.assert_called_once_with([{"q": 1}])

    def test_load_skill_resolves_name_and_serializes(self):
        client = Mock()
        client.conjure.return_value = (
            200,
            {
                "skill": {
                    "rid": SKILL_RID,
                    "version": "v1",
                    "content": {
                        "name": "ce-work",
                        "whenToUse": "when working",
                        "skillText": "# Work\nDo the work.",
                    },
                }
            },
            "{}",
        )
        service = Mock()
        service.get_thread_agent_state.return_value = {
            "sessionState": {"aipSkillConfigurations": {SKILL_RID: {"enabled": True}}}
        }
        loop, _, _ = make_loop(
            [_text_output("x")], internal_client=client, service=service
        )
        loop._thread_id = THREAD_ID
        payload = loop._exec_load_skill("load_skill", {"skillName": "ce-work"})
        assert f'<aip-skill skillRid="{SKILL_RID}" name="ce-work">' in payload
        assert "This skill is loaded and active." in payload
        assert "# Work" in payload
        assert client.conjure.call_args.args[1] == (
            f"aip-agents/api/skills/{SKILL_RID}/latest"
        )

    def test_load_skill_without_advertised_skills_fails_closed(self):
        service = Mock()
        service.get_thread_agent_state.return_value = {"sessionState": {}}
        loop, _, _ = make_loop([_text_output("x")], service=service)
        loop._thread_id = THREAD_ID
        with pytest.raises(UnverifiedContract, match="no enabled AIP skills"):
            loop._exec_load_skill("load_skill", {"skillName": "ce-work"})


class TestContextBudget:
    def test_oldest_tool_outputs_truncated_over_budget(self, monkeypatch):
        big_history = {"executionsPage": ["x" * 5000]}
        evals = Mock()
        evals.get_execution_history.return_value = big_history
        monkeypatch.setattr(
            "foundry_cli.services.ai_fde_loop.CONTEXT_TOKEN_THRESHOLD", 2000
        )
        loop, _, llm = make_loop(
            [
                _call_output(
                    "list_evaluation_runs",
                    json.dumps({"evaluationSuiteRid": SUITE_RID, "pageToken": None}),
                ),
                _text_output("done"),
            ],
            evals_service=evals,
        )
        loop.run("trigger truncation")
        second_input = llm.complete.call_args_list[1].kwargs["input_items"]
        output_item = next(
            i for i in second_input if i["item"]["type"] == "functionToolCallOutput"
        )
        assert (
            "hiddenContextItem"
            in (output_item["item"]["functionToolCallOutput"]["output"])
        )


class TestResume:
    def test_resume_rebuilds_conversation(self):
        service = Mock()
        service.get_thread_metadata.return_value = {
            "id": THREAD_ID,
            "version": VERSION,
            "contextItemsOrder": ["item-1"],
        }
        service.get_thread_items.return_value = {
            "contextItems": [
                {
                    "id": "item-1",
                    "contextItemType": "user-message",
                    "content": [
                        {
                            "id": "item-1",
                            "type": "user-message",
                            "prompt": "earlier ask",
                        }
                    ],
                },
                {
                    "id": "item-2",
                    "contextItemType": "assistant-message",
                    "content": [
                        {
                            "id": "item-2",
                            "type": "assistant-message",
                            "response": {
                                "status": "completed",
                                "content": [{"type": "text", "text": "earlier answer"}],
                            },
                        }
                    ],
                },
                {
                    "id": "item-3",
                    "contextItemType": "tool-usage",
                    "content": [
                        {
                            "id": "item-3",
                            "type": "tool-usage",
                            "toolName": "ontology_sql_query",
                            "toolRequest": {"queries": []},
                            "toolResponse": {
                                "state": "completed",
                                "contextItemIds": None,
                            },
                        }
                    ],
                },
            ],
            "nextPageToken": None,
        }
        service.update_thread_items.return_value = {
            "metadata": {"threadVersion": NEW_VERSION}
        }
        llm = Mock()
        llm.complete.side_effect = [_completed(_text_output("new answer"))]
        loop = AgentLoop(
            profile="test", approve="never", service=service, llm_session=llm
        )
        report = loop.run("follow up", thread_id=THREAD_ID)

        assert report["status"] == "completed"
        service.create_thread.assert_not_called()
        input_items = llm.complete.call_args.kwargs["input_items"]
        types = [i["item"]["type"] for i in input_items]
        assert types.count("inputMessage") == 2  # resumed + new instruction
        assert "outputMessage" in types
        assert "functionToolCall" in types
        resumed_output = next(
            i for i in input_items if i["item"]["type"] == "functionToolCallOutput"
        )
        assert (
            "not persisted"
            in (resumed_output["item"]["functionToolCallOutput"]["output"])
        )
        first_write = service.update_thread_items.call_args_list[0]
        assert first_write.args[1] == VERSION
        assert first_write.args[2][0] == "item-1"  # existing order preserved


class TestSerializers:
    def test_wrap_context_item(self):
        text = wrap_context_item("cid", "tool-usage", "payload", 42)
        assert text.startswith(
            '<context-item contextItemId="cid" contextItemType="tool-usage"'
        )
        assert 'cumulativeTokenCount="42"' in text
        assert text.endswith("</context-item>\n")
        assert "payload" in text

    def test_hidden_item_output(self):
        text = hidden_item_output("cid", "tool-usage", 42)
        assert 'contextItemType="hidden"' in text
        assert "Content hidden from context" in text

    def test_build_tool_usage_item(self):
        item = build_tool_usage_item("cid", "tool", {"a": 1}, "rejected")
        assert item["content"][0]["toolResponse"]["state"] == "rejected"
        assert item["fallbackMessage"] == {"role": "USER", "contents": []}
