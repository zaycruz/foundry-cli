"""
AI FDE client-side agent loop (LLM orchestration + tool execution).

The AI FDE agent loop runs client-side in the Foundry UI (see
``services/ai_fde.py``); this module reimplements that loop for the CLI:
build the OpenAI-Responses-shaped request, call the LLM, execute the
returned tool calls, write the results back into the thread document, and
repeat until the model stops calling tools.

Evidence: every contract below was captured from the live AI FDE UI via
Chrome DevTools Protocol (artifact
``/tmp/evals-capture/capture.jsonl``, 1896 requests; richest request artifact
``/tmp/ai-fde-richest-request.json`` with 170 input items and 72 tool specs)
and the LLM call plus thread delta writes were live-verified
against a second deployment (probe artifact
``/tmp/stream-toolcall-probe.json``). This is "UI capture, live-exercised"
evidence per ``tickets/README.md``.

LLM call (live-verified):

- ``PUT {host}/language-model-service/api/llm/v3/completion/{MODEL}/
  streamCompletionChunk`` (default model ``GPT_5_6_SOL``), bearer auth,
  ``Accept: application/octet-stream``, body
  ``{attribution: {type: "userAttributionV2", userAttributionV2: {user:
  <THE BEARER TOKEN ITSELF — verified live>, application: "AI_FDE"}},
  requestPriority: "CRITICAL", sessionId: <thread UUID>, request: {type:
  "openAiResponses", openAiResponses: {instructions: {text, type: "text"},
  input: [...], tools: [...], toolChoice: {auto: {}, type: "auto"},
  reasoning: {effort: "MEDIUM", summary: "AUTO"}, include:
  ["REASONING_ENCRYPTED_CONTENT"]}}}``.
- Every union node carries a ``type`` discriminator; input items are
  ``{"type": "item", "item": {"type": "inputMessage", ...}}``.
- The response is a single JSON ARRAY of events ``{"type": "success",
  "success": {"type": "openAiResponses", "openAiResponses": {<event>}}}``
  (event types: ``created``, ``outputTextDelta``,
  ``functionCallArgumentsDelta``, ``functionCallArgumentsDone``,
  ``outputItemDone``, ``completed``). ``completed.output`` is the
  authoritative output list (``outputMessage`` content
  ``[{"type": "text", "text": {"text": ...}}]``; ``functionToolCall``
  ``{arguments (JSON string), callId, id, name, status}``; ``reasoning``
  with encrypted content).
- **callId rewriting (captured behavior)**: the UI rewrites LLM
  ``call_xxx`` ids to its own UUIDs (== the ``tool-usage`` contextItemId)
  when constructing follow-up requests, and the server accepts this. This
  loop replicates it: each ``functionToolCall`` gets a minted UUID as its
  callId, and the tool result answers with the same UUID.
- Thread items are serialized into message text as XML-ish markup:
  ``<context-item contextItemId=... contextItemType=... tokenCount=...
  cumulativeTokenCount=...>\\n<payload/>\\n</context-item>`` (copied from the
  richest request; token counts here are char/4 estimates, not the UI's
  tokenizer counts). Hidden items serialize as
  ``<context-item contextItemType="hidden" ...><hiddenContextItem>
  <hiddenChild originalType="tool-usage">Content hidden from context
  </hiddenChild></hiddenContextItem></context-item>``.

Tool executors — endpoint mappings mined from the capture (all HTTP 200):

- ``ontology_sql_query`` (read, LIVE): one ``POST /object-set-service/api/
  sql-endpoint/v1/queries/query`` per query; body ``{querySpec: {query,
  tableProviders: {alias: {objectSet: {objectSet: {base: {objectTypeId},
  type: "base"}, columnMappings: {}}, type: "objectSet"}}, dialect: "SPARK",
  options: {options: [{option: "objectSetContext", value: "{}"}]}},
  executionParams: {resultFormat: "ARROW", defaultBranchIds: [],
  resultMode: "SYNC", rowLimit: 100}}`` (constant across all 15 captured
  calls). Source objectTypeRids are resolved to objectTypeIds via ``POST
  /ontology-metadata/api/ontology/ontology/bulkLoadEntities`` (captured
  body shape). The Arrow IPC result is decoded with pyarrow and serialized
  in the captured ``<ontologySql>``/``<ontology-sql-table>`` pattern.
  Non-null ``ontologyBranchRid`` and non-sync result modes fail closed
  (never captured).
- ``list_evaluation_runs`` / ``load_evaluation_runs`` /
  ``get_test_case_results`` / ``get_evaluation_suite_definition`` (read,
  LIVE): delegate to ``EvalsService`` (history, summary, v3 test cases, v2
  config). Run-history/test-case ``pageToken`` pagination was never
  captured (history bodies carry only ``{executionTarget, pageSize}``), so
  a non-null pageToken fails closed. Only the ``{"mainBranch": true}``
  branch arm was captured for suite-definition target resolution.
- ``run_evaluation_suite`` (write, LIVE, approval-gated): ``EvalsService``
  v2 config read (test-case parameter name->UUID from
  ``providedParametersSchema``, projected-field name->UUID from
  ``generatedParametersSchema``, single function target from
  ``executionTargets``) + pinned ``LatestFunctionVersionQuery`` for the
  main-branch version, then the captured ``PUT
  /foundry-evals/api/evals/execute/v3/{suiteRid}/run`` contract. Only the
  captured sub-contract is executable: function target, ``mainBranch``,
  ``projectScoped`` mode, no static inputs, no experiments — anything else
  fails closed.
- ``execute_action`` (write, LIVE, approval-gated, plan-first): pinned
  ``ActionTypeParametersQuery`` maps parameter API names to parameter RIDs
  and object/primary-key metadata; then ``POST
  /actions/api/actions/validate?owningRid=<actionTypeRid>`` (body
  ``{actionTypeRid, parameters, parametersPrefill: {all: {}, type:
  "all"}}``) and only when every rule result is ``validResult`` ``POST
  /actions/api/actionsV2`` (body ``{actionTypeRid, actionContext:
  {branchRid, loadActionEdits: true, parametersPrefill}, parameters}``).
  Only the captured parameter encoding is supported: object and
  object-list parameters with a single string primary key, encoded as
  ``objectLocator``/``objectLocatorList`` values. Scalar static values and
  composite/non-string primary keys fail closed.
- ``load_skill`` (read, LIVE): ``GET /aip-agents/api/skills/{rid}/latest``
  (captured) after resolving the skill NAME to an enabled skill RID from
  the thread agentState ``sessionState.aipSkillConfigurations``. Threads
  whose agentState advertises no skills fail closed.
- ``request_clarification_from_user`` (read, LIVE): interactive runs
  surface the questions to the operator (injected handler);
  non-interactive runs return a fixed "make reasonable assumptions"
  output instead of blocking.
- ``change_mode`` / ``enable_capabilities`` / ``disable_capabilities`` /
  ``manage_context`` (state tools, LIVE): client-side only in the capture
  (no endpoint). Mode/capability changes adjust the active tool set for
  subsequent LLM requests within the registered MVP tools (capability ->
  tool mapping per the captured instructions block); ``manage_context``
  hides/restores tool outputs from subsequent request construction
  (captured ``<manageContextResult>`` and hidden-item serializations).
  The full Foundry mode->tool-category semantics are NOT captured, so
  modes do not gate which registered tools are offered.
- ``load_documentation`` / ``load_documentation_bundles`` (read, FAIL
  CLOSED): no documentation page-load endpoint appears anywhere in the
  1896-request capture — the only ``/documentation/api/`` call is
  ``/documentation/api/v2/release-notes/pagination``, a different surface
  (workspace release notes). The specs are registered verbatim but the
  executors raise ``UnverifiedContract`` rather than guess a contract.

Write-back shapes (captured, ``/tmp/ai-fde-item-shapes.json``): tool
results are written as ``tool-usage`` items ``{contextItemId,
typeAndVersion: {contextItemType: "tool-usage", contextItemVersion: 0},
content: [{id, type: "tool-usage", toolName, toolRequest, toolResponse:
{state, contextItemIds}}], fallbackMessages: [],
childContextItemsOrder: [], fallbackMessage: {role: "USER", contents:
[]}}`` with state ``completed`` (captured) or ``rejected`` (DERIVED — a
declined approval was never captured; the write is still recorded so the
thread reflects what the loop did). Assistant text is written as
``assistant-message`` items with ``response: {status: "completed",
content: [{type: "text", text}]`` and an ASSISTANT fallback message.

Resume (DERIVED — resuming a UI-created thread was never captured): the
thread document does NOT persist tool result payloads (a completed
``tool-usage`` carries only ``{state, contextItemIds}``), so full-fidelity
resume is impossible. Resume rebuilds user messages and assistant texts,
and re-presents prior tool calls with an explicit "result not persisted"
note payload instead of fabricating results.

Token/context discipline: request tokens are estimated as chars/4; when
the estimate exceeds ``CONTEXT_TOKEN_THRESHOLD`` the oldest tool outputs
are replaced with the captured hidden-item placeholder until the estimate
fits (the UI's ``manage_context`` does the same at the model's request;
captured sessions hit ~130k cumulative tokens).
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid4

import requests

from ..auth.base import MissingCredentialsError
from ..auth.storage import CredentialStorage
from .ai_fde import AiFdeService
from .ai_fde_tool_specs import CAPTURED_INSTRUCTIONS_PREFIX, TOOL_SPECS
from .errors import FoundryApiError, foundry_error_from_conjure
from .evals import EvalsService
from .foundry_internal_client import FoundryInternalClient

DEFAULT_MODEL = "GPT_5_6_SOL"
DEFAULT_MAX_TURNS = 25
CONTEXT_TOKEN_THRESHOLD = 60_000
LLM_REQUEST_TIMEOUT = 240.0

_LLM_PATH = "language-model-service/api/llm/v3/completion/{model}/streamCompletionChunk"
_SQL_QUERY_PATH = "object-set-service/api/sql-endpoint/v1/queries/query"
_BULK_LOAD_ENTITIES_PATH = "ontology-metadata/api/ontology/ontology/bulkLoadEntities"
_ACTIONS_VALIDATE_PATH = "actions/api/actions/validate"
_ACTIONS_APPLY_PATH = "actions/api/actionsV2"
_SKILL_LATEST_PATH = "aip-agents/api/skills/{rid}/latest"

# Additive CLI-specific guidance appended after the captured instructions;
# NOT part of the captured block (it describes this loop's own constraints).
_CLI_NOTES = """
<cliNotes>
You are running inside the pfoundry CLI agent loop, not the Foundry UI.
- Write tools (execute_action, run_evaluation_suite) execute only after
  operator approval. If a write is declined, continue without it.
- request_clarification_from_user may be unavailable in non-interactive
  runs; then make reasonable assumptions, state them, and proceed.
- load_documentation and load_documentation_bundles are registered but not
  wired to a verified endpoint in this environment; they will fail closed.
  Do not rely on them.
</cliNotes>
"""

ACTION_TYPE_PARAMETERS_QUERY = """query ActionTypeParametersQuery($actionTypeRid: RID!, $ontologyBranchRid: RID) {
  actionTypeBranch(
    actionTypeRid: $actionTypeRid
    ontologyBranchRid: $ontologyBranchRid
  ) {
    latest {
      parameters {
        id
        rid
        type {
          ... on ActionParameterType_Object {
            objectType {
              ...ObjectPrimaryKeyMetadataFragment
              _id
              __typename
            }
            __typename
          }
          ... on ActionParameterType_ObjectList {
            objectType {
              ...ObjectPrimaryKeyMetadataFragment
              _id
              __typename
            }
            __typename
          }
          __typename
        }
        _id
        __typename
      }
      _id
      __typename
    }
    _id
    __typename
  }
  __typename
}

fragment ObjectPrimaryKeyMetadataFragment on ObjectType {
  id
  latest {
    primaryKeyPropertiesV2 {
      id
      objectTypeProperty {
        rid
        _id
        __typename
      }
      type {
        ...PrimaryKeyPropertyTypeFragment
        __typename
      }
      _id
      __typename
    }
    _id
    __typename
  }
  _id
  __typename
}

fragment PrimaryKeyPropertyTypeFragment on ObjectTypePropertyType {
  __typename
}"""

LATEST_FUNCTION_VERSION_QUERY = """query LatestFunctionVersionQuery($functionRid: RID!) {
  function(rid: $functionRid) {
    latestVersion {
      version
      _id
      __typename
    }
    _id
    __typename
  }
  __typename
}"""


class UnverifiedContract(RuntimeError):
    """A tool's endpoint mapping was never captured; fail closed, never guess."""

    def __init__(self, tool: str, reason: str) -> None:
        self.tool = tool
        self.reason = reason
        super().__init__(f"{tool}: {reason}")


class LlmResponseShapeError(RuntimeError):
    """The streamCompletionChunk response is not the captured JSON-array shape."""


@dataclass(frozen=True)
class CompletedResponse:
    """The authoritative result of one streamCompletionChunk call."""

    output: List[Mapping[str, Any]]
    usage: Mapping[str, Any]
    response_id: Optional[str]
    model: Optional[str]
    events: List[Mapping[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ToolRegistration:
    """One registered tool: captured spec, risk class, executor, liveness."""

    name: str
    risk: str  # "read" | "write"
    executor: str  # AgentLoop method name
    live: bool
    note: str = ""


TOOL_REGISTRY: Dict[str, ToolRegistration] = {
    "load_documentation": ToolRegistration(
        "load_documentation",
        "read",
        "_exec_unverified_documentation",
        live=False,
        note="no page-load endpoint in capture; only release-notes pagination",
    ),
    "load_documentation_bundles": ToolRegistration(
        "load_documentation_bundles",
        "read",
        "_exec_unverified_documentation",
        live=False,
        note="no bundle-load endpoint in capture",
    ),
    "ontology_sql_query": ToolRegistration(
        "ontology_sql_query", "read", "_exec_ontology_sql_query", live=True
    ),
    "list_evaluation_runs": ToolRegistration(
        "list_evaluation_runs", "read", "_exec_list_evaluation_runs", live=True
    ),
    "load_evaluation_runs": ToolRegistration(
        "load_evaluation_runs", "read", "_exec_load_evaluation_runs", live=True
    ),
    "get_test_case_results": ToolRegistration(
        "get_test_case_results", "read", "_exec_get_test_case_results", live=True
    ),
    "get_evaluation_suite_definition": ToolRegistration(
        "get_evaluation_suite_definition",
        "read",
        "_exec_get_evaluation_suite_definition",
        live=True,
    ),
    "run_evaluation_suite": ToolRegistration(
        "run_evaluation_suite", "write", "_exec_run_evaluation_suite", live=True
    ),
    "execute_action": ToolRegistration(
        "execute_action", "write", "_exec_execute_action", live=True
    ),
    "request_clarification_from_user": ToolRegistration(
        "request_clarification_from_user",
        "read",
        "_exec_request_clarification_from_user",
        live=True,
    ),
    "change_mode": ToolRegistration(
        "change_mode", "read", "_exec_change_mode", live=True
    ),
    "enable_capabilities": ToolRegistration(
        "enable_capabilities", "read", "_exec_enable_capabilities", live=True
    ),
    "disable_capabilities": ToolRegistration(
        "disable_capabilities", "read", "_exec_disable_capabilities", live=True
    ),
    "manage_context": ToolRegistration(
        "manage_context", "read", "_exec_manage_context", live=True
    ),
    "load_skill": ToolRegistration("load_skill", "read", "_exec_load_skill", live=True),
}

# Capability -> registered tools, per the captured instructions block. Only
# capabilities whose tools exist in TOOL_REGISTRY can be toggled.
CAPABILITY_TOOL_MAP: Dict[str, Tuple[str, ...]] = {
    "changeMode": ("change_mode",),
    "requestClarification": ("request_clarification_from_user",),
    "loadDocumentation": ("load_documentation", "load_documentation_bundles"),
    "manageContext": ("manage_context",),
    "manageCapabilities": ("enable_capabilities", "disable_capabilities"),
    "executeAction": ("execute_action",),
    "loadSkills": ("load_skill",),
}

DEFAULT_TOOL_NAMES: Tuple[str, ...] = tuple(TOOL_REGISTRY.keys())


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4) for context budgeting."""
    return max(1, len(text) // 4)


def wrap_context_item(
    context_item_id: str,
    item_type: str,
    payload: str,
    cumulative_token_count: int,
) -> str:
    """Serialize one payload in the captured ``<context-item>`` pattern."""
    return (
        f'<context-item contextItemId="{context_item_id}" '
        f'contextItemType="{item_type}" '
        f'tokenCount="{estimate_tokens(payload)}" '
        f'cumulativeTokenCount="{cumulative_token_count}">\n'
        f"{payload}\n"
        f"</context-item>\n"
    )


def hidden_item_output(
    context_item_id: str, original_type: str, cumulative: int
) -> str:
    """Serialize a hidden item in the captured placeholder pattern."""
    payload = (
        "<hiddenContextItem>\n"
        f'  <hiddenChild originalType="{original_type}">'
        "Content hidden from context</hiddenChild>\n"
        "</hiddenContextItem>"
    )
    return (
        f'<context-item contextItemId="{context_item_id}" '
        f'contextItemType="hidden" '
        f'tokenCount="{estimate_tokens(payload)}" '
        f'cumulativeTokenCount="{cumulative}">\n'
        f"{payload}\n"
        f"</context-item>\n"
    )


def input_message_item(text: str) -> Dict[str, Any]:
    """Build a captured-shape ``inputMessage`` input item."""
    return {
        "type": "item",
        "item": {
            "type": "inputMessage",
            "inputMessage": {
                "role": "USER",
                "content": [{"text": text, "type": "text"}],
            },
        },
    }


def function_tool_call_item(call_id: str, name: str, arguments: str) -> Dict[str, Any]:
    """Build the follow-up ``functionToolCall`` item (rewritten callId).

    The captured follow-up items carry exactly ``{callId, name,
    arguments}`` — the LLM's own ``id``/``status`` are not echoed back.
    """
    return {
        "type": "item",
        "item": {
            "type": "functionToolCall",
            "functionToolCall": {
                "callId": call_id,
                "name": name,
                "arguments": arguments,
            },
        },
    }


def function_tool_call_output_item(call_id: str, output: str) -> Dict[str, Any]:
    """Build a captured-shape ``functionToolCallOutput`` input item."""
    return {
        "type": "item",
        "item": {
            "type": "functionToolCallOutput",
            "functionToolCallOutput": {"callId": call_id, "output": output},
        },
    }


def build_tool_usage_item(
    context_item_id: str,
    tool_name: str,
    tool_request: Any,
    state: str = "completed",
) -> Dict[str, Any]:
    """Build a captured-shape ``tool-usage`` thread item."""
    return {
        "contextItemId": context_item_id,
        "typeAndVersion": {
            "contextItemType": "tool-usage",
            "contextItemVersion": 0,
        },
        "content": [
            {
                "id": context_item_id,
                "type": "tool-usage",
                "toolName": tool_name,
                "toolRequest": tool_request,
                "toolResponse": {"state": state, "contextItemIds": None},
            }
        ],
        "fallbackMessages": [],
        "childContextItemsOrder": [],
        "fallbackMessage": {"role": "USER", "contents": []},
    }


def build_assistant_message_item(context_item_id: str, text: str) -> Dict[str, Any]:
    """Build a captured-shape ``assistant-message`` thread item (text only)."""
    return {
        "contextItemId": context_item_id,
        "typeAndVersion": {
            "contextItemType": "assistant-message",
            "contextItemVersion": 0,
        },
        "content": [
            {
                "id": context_item_id,
                "type": "assistant-message",
                "response": {
                    "status": "completed",
                    "content": [{"type": "text", "text": text}],
                },
            }
        ],
        "fallbackMessages": [
            {
                "role": "ASSISTANT",
                "contents": [{"type": "text", "text": text}],
            }
        ],
        "childContextItemsOrder": [],
        "fallbackMessage": {"role": "USER", "contents": []},
    }


def _output_message_text(output_message: Mapping[str, Any]) -> str:
    """Extract concatenated text from a completed ``outputMessage`` entry."""
    parts: List[str] = []
    for content in output_message.get("content") or []:
        if isinstance(content, Mapping) and content.get("type") == "text":
            text = content.get("text")
            if isinstance(text, Mapping):
                parts.append(str(text.get("text") or ""))
            elif text is not None:
                parts.append(str(text))
    return "\n".join(p for p in parts if p)


class LlmSession:
    """Thin wrapper around the streamCompletionChunk call via ``requests``.

    Unlike the Conjure transport, this call needs the raw requests path
    (model in the URL, octet-stream accept, 240s timeout) and the
    attribution-user-is-the-bearer-token quirk documented above.
    """

    def __init__(
        self,
        profile: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        request_timeout: float = LLM_REQUEST_TIMEOUT,
    ) -> None:
        self.profile = profile
        self.model = model
        self.request_timeout = request_timeout

    def _credentials(self) -> Mapping[str, Any]:
        if self.profile:
            return CredentialStorage().get_profile(self.profile)
        from ..auth.base import ProfileNotFoundError
        from ..config.profiles import ProfileManager

        profile_name = ProfileManager().get_active_profile()
        if not profile_name:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'foundry configure configure' to set up authentication."
            )
        return CredentialStorage().get_profile(profile_name)

    def build_request_body(
        self,
        *,
        thread_id: str,
        token: str,
        instructions: str,
        input_items: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Build the captured streamCompletionChunk request body."""
        return {
            "attribution": {
                "type": "userAttributionV2",
                "userAttributionV2": {"user": token, "application": "AI_FDE"},
            },
            "requestPriority": "CRITICAL",
            "sessionId": thread_id,
            "request": {
                "type": "openAiResponses",
                "openAiResponses": {
                    "instructions": {"text": instructions, "type": "text"},
                    "input": list(input_items),
                    "tools": list(tools),
                    "toolChoice": {"auto": {}, "type": "auto"},
                    "reasoning": {"effort": "MEDIUM", "summary": "AUTO"},
                    "include": ["REASONING_ENCRYPTED_CONTENT"],
                },
            },
        }

    def complete(
        self,
        *,
        thread_id: str,
        instructions: str,
        input_items: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> CompletedResponse:
        """Issue one completion call and return the authoritative output."""
        credentials = self._credentials()
        base_url = FoundryInternalClient._base_url(credentials.get("host", ""))
        token = credentials.get("token")
        if not isinstance(token, str) or not token:
            raise MissingCredentialsError(
                "The active profile has no bearer token; the AI FDE LLM call "
                "needs token auth (the attribution user is the bearer token "
                "itself)."
            )
        body = self.build_request_body(
            thread_id=thread_id,
            token=token,
            instructions=instructions,
            input_items=input_items,
            tools=tools,
        )
        response = requests.request(
            method="PUT",
            url=f"{base_url}/{_LLM_PATH.format(model=self.model)}",
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/octet-stream",
            },
            timeout=self.request_timeout,
        )
        raw = response.text
        try:
            payload: Any = response.json()
        except (requests.JSONDecodeError, ValueError):
            payload = raw
        if not 200 <= response.status_code < 300:
            raise foundry_error_from_conjure(
                response.status_code, payload, raw, context="LLM completion"
            )
        return self.parse_events(payload)

    @staticmethod
    def parse_events(payload: Any) -> CompletedResponse:
        """Parse the captured JSON-array event format into one response."""
        if not isinstance(payload, list):
            raise LlmResponseShapeError(
                "Unverified streamCompletionChunk response shape: expected a "
                f"JSON array of events, got {str(payload)[:200]!r}. Refusing "
                "to guess at the contract."
            )
        events: List[Mapping[str, Any]] = []
        for frame in payload:
            if not isinstance(frame, Mapping):
                continue
            success = frame.get("success")
            if frame.get("type") != "success" or not isinstance(success, Mapping):
                continue
            if success.get("type") != "openAiResponses":
                continue
            event = success.get("openAiResponses")
            if isinstance(event, Mapping):
                events.append(event)
        completed: Optional[Mapping[str, Any]] = None
        for event in events:
            if event.get("type") == "completed" and isinstance(
                event.get("completed"), Mapping
            ):
                completed = event["completed"]
        if completed is None:
            raise LlmResponseShapeError(
                "streamCompletionChunk response carried no 'completed' event: "
                f"{[e.get('type') for e in events]!r}."
            )
        output = completed.get("output")
        if not isinstance(output, list):
            raise LlmResponseShapeError(
                "Unverified streamCompletionChunk completed shape: expected "
                f"'output' to be a list, got {str(completed)[:200]!r}."
            )
        usage = completed.get("usage")
        return CompletedResponse(
            output=[o for o in output if isinstance(o, Mapping)],
            usage=usage if isinstance(usage, Mapping) else {},
            response_id=completed.get("id"),
            model=completed.get("model"),
            events=events,
        )


class AgentLoop:
    """Drive one AI FDE thread: instruction -> LLM <-> tools -> report.

    ``approve`` is ``interactive`` (prompt per write tool; needs a
    ``confirm`` callable), ``always`` (auto-approve writes), or ``never``
    (writes are declined; read tools still run).
    """

    def __init__(
        self,
        profile: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        approve: str = "interactive",
        tool_names: Optional[Sequence[str]] = None,
        service: Optional[AiFdeService] = None,
        evals_service: Optional[EvalsService] = None,
        llm_session: Optional[LlmSession] = None,
        internal_client: Optional[FoundryInternalClient] = None,
        progress: Optional[Callable[[str], None]] = None,
        confirm: Optional[Callable[[str], bool]] = None,
        clarification_handler: Optional[Callable[[Sequence[Any]], str]] = None,
        instructions: Optional[str] = None,
    ) -> None:
        if approve not in {"interactive", "always", "never"}:
            raise ValueError(
                f"approve must be interactive|always|never, got {approve!r}"
            )
        self.profile = profile
        self.model = model
        self.approve = approve
        names = list(tool_names) if tool_names else list(DEFAULT_TOOL_NAMES)
        unknown = [n for n in names if n not in TOOL_REGISTRY]
        if unknown:
            raise ValueError(
                f"unknown tools: {', '.join(unknown)}; registered: "
                f"{', '.join(TOOL_REGISTRY)}"
            )
        self._active_tools: set[str] = set(names)
        self._service = service
        self._evals_service = evals_service
        self._llm_session = llm_session
        self._internal_client = internal_client
        self._progress = progress or (lambda _msg: None)
        self._confirm = confirm
        self._clarification_handler = clarification_handler
        self._instructions_override = instructions
        self._mode: Optional[str] = None
        self._thread_id: Optional[str] = None
        self._cumulative_tokens = 0
        self._hidden: set[str] = set()
        self._tool_output_items: Dict[str, Dict[str, Any]] = {}
        self._tool_output_payloads: Dict[str, str] = {}
        self._object_type_id_cache: Dict[str, str] = {}
        self._skill_rids_cache: Optional[List[str]] = None

    # --- wiring --------------------------------------------------------

    def _ai_fde_service(self) -> AiFdeService:
        if self._service is None:
            self._service = AiFdeService(profile=self.profile)
        return self._service

    def _evals(self) -> EvalsService:
        if self._evals_service is None:
            self._evals_service = EvalsService(profile=self.profile)
        return self._evals_service

    def _llm(self) -> LlmSession:
        if self._llm_session is None:
            self._llm_session = LlmSession(profile=self.profile, model=self.model)
        return self._llm_session

    def _client(self) -> FoundryInternalClient:
        if self._internal_client is None:
            from ..auth.base import ProfileNotFoundError
            from ..config.profiles import ProfileManager

            profile_name = self.profile or ProfileManager().get_active_profile()
            if not profile_name:
                raise ProfileNotFoundError(
                    "No profile specified and no default profile configured. "
                    "Run 'foundry configure configure' to set up authentication."
                )
            self._internal_client = FoundryInternalClient(profile_name)
        return self._internal_client

    def _conjure(
        self, verb: str, path: str, body: Optional[Mapping[str, Any]], context: str
    ) -> Dict[str, Any]:
        status, payload, raw = self._client().conjure(verb, path, json_body=body)
        if not 200 <= status < 300:
            raise foundry_error_from_conjure(status, payload, raw, context=context)
        if not isinstance(payload, Mapping):
            raise UnverifiedContract(
                context,
                f"response was not a JSON object ({str(raw)[:200]!r}); the "
                "captured contract returned an object",
            )
        return dict(payload)

    def _instructions(self) -> str:
        if self._instructions_override is not None:
            return self._instructions_override
        return (
            CAPTURED_INSTRUCTIONS_PREFIX
            + f"- Today's date is {date.today().isoformat()}\n"
            + _CLI_NOTES
        )

    def _active_tool_specs(self) -> List[Mapping[str, Any]]:
        return [
            TOOL_SPECS[name] for name in TOOL_REGISTRY if name in self._active_tools
        ]

    # --- approval gate ---------------------------------------------------

    def _gate(self, name: str, args: Mapping[str, Any]) -> bool:
        """Resolve whether one WRITE tool call may execute."""
        if self.approve == "always":
            self._progress(f"write tool '{name}' auto-approved (--yes)")
            return True
        if self.approve == "never":
            self._progress(f"write tool '{name}' declined (non-interactive)")
            return False
        if self._confirm is None:
            self._progress(f"write tool '{name}' declined (no approval channel)")
            return False
        summary = json.dumps(args, default=str)
        if len(summary) > 600:
            summary = summary[:600] + "..."
        approved = bool(self._confirm(f"Approve write tool '{name}' with {summary}?"))
        self._progress(
            f"write tool '{name}' {'approved' if approved else 'declined'} by operator"
        )
        return approved

    # --- tool execution --------------------------------------------------

    def _execute_tool(self, name: str, raw_arguments: str) -> Tuple[str, str, Any]:
        """Run one tool call; return (payload, state, parsed_request)."""
        registration = TOOL_REGISTRY.get(name)
        if registration is None:
            return (
                f"Unknown tool '{name}'. It is not registered in this CLI loop; "
                f"registered tools: {', '.join(TOOL_REGISTRY)}.",
                "completed",
                {"_rawArguments": raw_arguments},
            )
        try:
            args: Any = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError as e:
            return (
                f"Tool arguments were not valid JSON: {e}",
                "completed",
                {"_rawArguments": raw_arguments},
            )
        if registration.risk == "write" and not self._gate(name, args):
            return (
                f"Write tool '{name}' was declined by the operator and was "
                "not executed. Continue without it.",
                "rejected",
                args,
            )
        try:
            payload = getattr(self, registration.executor)(name, args)
        except UnverifiedContract as e:
            payload = (
                f"Tool '{name}' is not executable in this CLI loop: {e.reason} "
                "Do not retry it with the same contract."
            )
        except FoundryApiError as e:
            payload = (
                f"Tool '{name}' failed: {json.dumps(e.error_entry(), default=str)}"
            )
        except Exception as e:  # tool errors become tool output; the loop continues
            payload = f"Tool '{name}' failed: {type(e).__name__}: {e}"
        return payload, "completed", args

    # --- tool executors ----------------------------------------------------

    def _exec_unverified_documentation(self, name: str, args: Mapping[str, Any]) -> str:
        raise UnverifiedContract(
            name,
            "no documentation page-load endpoint was captured (the only "
            "/documentation/api/ call in the 1896-request capture is "
            "/v2/release-notes/pagination, a different surface). The "
            "documentation tools are registered spec-only and fail closed.",
        )

    def _object_type_id_for_rid(self, rid: str) -> str:
        if rid in self._object_type_id_cache:
            return self._object_type_id_cache[rid]
        payload = self._conjure(
            "POST",
            _BULK_LOAD_ENTITIES_PATH,
            {
                "objectTypes": [
                    {"identifier": {"objectTypeRid": rid, "type": "objectTypeRid"}}
                ],
                "entityMetadata": {},
                "datasourceTypes": [
                    "DATASET",
                    "DATASET_V2",
                    "DATASET_V3",
                    "RESTRICTED_VIEW",
                    "RESTRICTED_VIEW_V2",
                ],
                "linkTypes": [],
                "sharedPropertyTypes": [],
                "interfaceTypes": [],
                "typeGroups": [],
                "actionTypes": [],
                "includeObjectTypesWithoutSearchableDatasources": True,
            },
            "resolve object type",
        )
        object_types = payload.get("objectTypes")
        object_type_id: Optional[str] = None
        if isinstance(object_types, list) and object_types:
            first = object_types[0]
            if isinstance(first, Mapping):
                ot = first.get("objectType")
                if isinstance(ot, Mapping) and isinstance(ot.get("id"), str):
                    object_type_id = ot["id"]
        if not object_type_id:
            raise UnverifiedContract(
                "ontology_sql_query",
                f"bulkLoadEntities returned no objectType.id for {rid!r}: "
                f"{str(payload)[:200]!r}",
            )
        self._object_type_id_cache[rid] = object_type_id
        return object_type_id

    def _exec_ontology_sql_query(self, name: str, args: Mapping[str, Any]) -> str:
        queries = args.get("queries")
        sources = args.get("sources")
        if not isinstance(queries, list) or not queries:
            raise ValueError("ontology_sql_query requires a non-empty 'queries' list")
        if not isinstance(sources, list) or not sources:
            raise ValueError("ontology_sql_query requires a non-empty 'sources' list")
        for query in queries:
            if not isinstance(query, Mapping) or not isinstance(
                query.get("query"), str
            ):
                raise ValueError(f"malformed query entry: {query!r}")
            if query.get("ontologyBranchRid"):
                raise UnverifiedContract(
                    name,
                    "ontology-branch SQL was never captured (defaultBranchIds "
                    "was always [] with a null branch)",
                )
        table_providers: Dict[str, Any] = {}
        for source in sources:
            if not isinstance(source, Mapping):
                raise ValueError(f"malformed source entry: {source!r}")
            alias = source.get("alias")
            body = source.get("source")
            if not isinstance(alias, str) or not isinstance(body, Mapping):
                raise ValueError(f"malformed source entry: {source!r}")
            if body.get("type") != "objectType":
                raise UnverifiedContract(
                    name,
                    f"source type {body.get('type')!r} was never captured; only "
                    "objectType sources were observed",
                )
            rid = body.get("objectTypeRid")
            if not isinstance(rid, str):
                raise ValueError(f"source {alias!r} has no objectTypeRid")
            table_providers[alias] = {
                "objectSet": {
                    "objectSet": {
                        "base": {"objectTypeId": self._object_type_id_for_rid(rid)},
                        "type": "base",
                    },
                    "columnMappings": {},
                },
                "type": "objectSet",
            }
        parts: List[str] = []
        for query in queries:
            response = self._conjure(
                "POST",
                _SQL_QUERY_PATH,
                {
                    "querySpec": {
                        "query": query["query"],
                        "tableProviders": table_providers,
                        "dialect": "SPARK",
                        "options": {
                            "options": [{"option": "objectSetContext", "value": "{}"}]
                        },
                    },
                    "executionParams": {
                        "resultFormat": "ARROW",
                        "defaultBranchIds": [],
                        "resultMode": "SYNC",
                        "rowLimit": 100,
                    },
                },
                "run ontology SQL query",
            )
            if response.get("type") != "sync":
                raise UnverifiedContract(
                    name,
                    f"result mode {response.get('type')!r} was never captured; "
                    "only SYNC results were observed",
                )
            sync = response.get("sync")
            result_b64 = sync.get("result") if isinstance(sync, Mapping) else None
            if not isinstance(result_b64, str):
                raise UnverifiedContract(
                    name,
                    f"sync result carried no base64 payload: {str(response)[:200]!r}",
                )
            columns, rows = _decode_arrow_result(result_b64)
            parts.append(_serialize_ontology_sql(query["query"], columns, rows))
        return "\n".join(parts)

    def _exec_list_evaluation_runs(self, name: str, args: Mapping[str, Any]) -> str:
        if args.get("pageToken"):
            raise UnverifiedContract(
                name,
                "run-history pagination was never captured (history bodies "
                "carry only {executionTarget, pageSize}); ask for the first "
                "page only",
            )
        suite_rid = _require_str(args, "evaluationSuiteRid", name)
        payload = self._evals().get_execution_history(suite_rid, page_size=20)
        return json.dumps(payload, indent=1, default=str)

    def _exec_load_evaluation_runs(self, name: str, args: Mapping[str, Any]) -> str:
        suite_rid = _require_str(args, "evaluationSuiteRid", name)
        execution_ids = args.get("executionIds")
        if not isinstance(execution_ids, list) or not execution_ids:
            raise ValueError(
                "load_evaluation_runs requires a non-empty 'executionIds' list"
            )
        summaries = [
            self._evals().get_execution_summary(suite_rid, str(execution_id))
            for execution_id in execution_ids
        ]
        return json.dumps(summaries, indent=1, default=str)

    def _exec_get_test_case_results(self, name: str, args: Mapping[str, Any]) -> str:
        if args.get("pageToken"):
            raise UnverifiedContract(
                name,
                "test-case pagination was never captured (v3 testCases bodies "
                "carry only {executionId, pageSize})",
            )
        suite_rid = _require_str(args, "evaluationSuiteRid", name)
        execution_id = _require_str(args, "executionId", name)
        page_size = args.get("pageSize") or 50
        payload = self._evals().get_execution_test_cases_v3(
            suite_rid, execution_id, page_size=int(page_size)
        )
        return json.dumps(payload, indent=1, default=str)

    def _exec_get_evaluation_suite_definition(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        _require_main_branch(args.get("branch"), name)
        suite_rid = _require_str(args, "evaluationSuiteRid", name)
        payload = self._evals().get_evaluation_suite_config_v2(suite_rid)
        return json.dumps(payload, indent=1, default=str)

    def _exec_run_evaluation_suite(self, name: str, args: Mapping[str, Any]) -> str:
        _require_main_branch(args.get("branch"), name)
        if args.get("staticInputs"):
            raise UnverifiedContract(
                name, "static inputs never appeared in a captured run body"
            )
        if args.get("experiment"):
            raise UnverifiedContract(
                name, "experiments never appeared in a captured run body"
            )
        execution_mode = args.get("executionMode") or "projectScoped"
        if execution_mode != "projectScoped":
            raise UnverifiedContract(
                name,
                f"execution mode {execution_mode!r} was never captured; only "
                "projectScoped runs were observed",
            )
        suite_rid = _require_str(args, "evaluationSuiteRid", name)
        parameter_mappings = args.get("parameterMappings")
        if not isinstance(parameter_mappings, list):
            raise ValueError("run_evaluation_suite requires a 'parameterMappings' list")

        config = self._evals().get_evaluation_suite_config_v2(suite_rid)
        suite = _extract_suite_definition(config, suite_rid)
        targets = suite.get("executionTargets")
        if not isinstance(targets, list) or len(targets) != 1:
            raise UnverifiedContract(
                name,
                "the captured run contract requires exactly one execution "
                f"target; this suite has {len(targets) if isinstance(targets, list) else 'none'}",
            )
        locator = targets[0].get("locator") if isinstance(targets[0], Mapping) else None
        if not isinstance(locator, Mapping) or locator.get("type") != "function":
            raise UnverifiedContract(
                name, "only function execution targets were captured"
            )
        function_rid = locator.get("function")
        provided = _parameter_schema_map(
            suite,
            ("executionBackend", "evals", "testCases", "providedParametersSchema"),
        )
        generated = _parameter_schema_map(targets[0], ("generatedParametersSchema",))

        input_mapping: Dict[str, Any] = {}
        for mapping in parameter_mappings:
            if not isinstance(mapping, Mapping):
                raise ValueError(f"malformed parameterMapping: {mapping!r}")
            parameter_name = mapping.get("testCaseParameterName")
            target_input = mapping.get("targetInputName")
            if parameter_name not in provided:
                raise ValueError(
                    f"unknown test case parameter {parameter_name!r}; the suite "
                    f"provides: {', '.join(sorted(provided)) or '(none)'}"
                )
            input_mapping[str(target_input)] = {
                "parameter": provided[parameter_name],
                "type": "parameter",
            }
        version = self._latest_function_version(str(function_rid))
        body = {
            "executionTarget": {
                "function": {
                    "ridAndVersion": {
                        "functionRid": function_rid,
                        "functionVersion": version,
                    },
                    "inputParameterMapping": input_mapping,
                    "outputParameterMapping": {
                        "multiple": {
                            "projectedFields": generated,
                            "type": "multiple",
                        }
                    },
                },
                "type": "function",
            },
            "backendParameters": {
                "evals": {
                    "executionMode": {
                        "projectScoped": {
                            "extraResources": [],
                            "forceTargetsToExecuteInProjectScopedMode": bool(
                                args.get("forceTargetsToExecuteInProjectScopedMode")
                            ),
                        },
                        "type": "projectScoped",
                    },
                    "repeatTestCases": {
                        "numTimesToRun": int(args.get("timesToRunEachTest") or 1)
                    },
                    "testCaseParallelism": int(args.get("testCaseParallelism") or 10),
                    "enableAsyncExecution": False,
                },
                "type": "evals",
            },
            "reportMetadata": {
                "Source": {"string": "AI FDE", "type": "string"},
                "EVALS_DEFAULT_RUN_METADATA_RUN_VERSION": {
                    "string": version,
                    "type": "string",
                },
                "EVALS_DEFAULT_RUN_METADATA_RUN_BRANCH": {
                    "string": "master",
                    "type": "string",
                },
            },
        }
        result = self._evals().trigger_run(suite_rid, body)
        return json.dumps(result, indent=1, default=str)

    def _latest_function_version(self, function_rid: str) -> str:
        result = self._client().graphql(
            "LatestFunctionVersionQuery",
            LATEST_FUNCTION_VERSION_QUERY,
            {"functionRid": function_rid},
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                "run_evaluation_suite",
                f"LatestFunctionVersionQuery failed: "
                f"{result.errors or result.reason or result.status}",
            )
        function = result.data.get("function")
        latest = (
            function.get("latestVersion") if isinstance(function, Mapping) else None
        )
        version = latest.get("version") if isinstance(latest, Mapping) else None
        if not isinstance(version, str) or not version:
            raise UnverifiedContract(
                "run_evaluation_suite",
                f"LatestFunctionVersionQuery returned no version: {result.data!r}",
            )
        return version

    def _action_type_parameters(
        self, action_type_rid: str, ontology_branch_rid: Optional[str]
    ) -> List[Mapping[str, Any]]:
        result = self._client().graphql(
            "ActionTypeParametersQuery",
            ACTION_TYPE_PARAMETERS_QUERY,
            {
                "actionTypeRid": action_type_rid,
                "ontologyBranchRid": ontology_branch_rid,
            },
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                "execute_action",
                f"ActionTypeParametersQuery failed: "
                f"{result.errors or result.reason or result.status}",
            )
        branch = result.data.get("actionTypeBranch")
        latest = branch.get("latest") if isinstance(branch, Mapping) else None
        parameters = latest.get("parameters") if isinstance(latest, Mapping) else None
        if not isinstance(parameters, list):
            raise UnverifiedContract(
                "execute_action",
                f"ActionTypeParametersQuery returned no parameters: {result.data!r}",
            )
        return [p for p in parameters if isinstance(p, Mapping)]

    def _exec_execute_action(self, name: str, args: Mapping[str, Any]) -> str:
        action_type_rid = _require_str(args, "actionTypeRid", name)
        ontology_branch_rid = args.get("ontologyBranchRid")
        raw_parameters = args.get("parameters")
        if not isinstance(raw_parameters, list):
            raise ValueError("execute_action requires a 'parameters' list")
        metadata = self._action_type_parameters(action_type_rid, ontology_branch_rid)
        by_id = {str(p.get("id")): p for p in metadata}
        parameters: Dict[str, Any] = {}
        for entry in raw_parameters:
            if not isinstance(entry, Mapping):
                raise ValueError(f"malformed parameter entry: {entry!r}")
            parameter_id = entry.get("parameterId")
            meta = by_id.get(str(parameter_id))
            if meta is None:
                raise ValueError(
                    f"unknown parameterId {parameter_id!r}; the action type "
                    f"declares: {', '.join(sorted(by_id)) or '(none)'}"
                )
            value = entry.get("value")
            static_value = (
                value.get("staticValue") if isinstance(value, Mapping) else None
            )
            if not isinstance(static_value, Mapping):
                raise ValueError(
                    f"parameter {parameter_id!r}: only staticValue parameters "
                    "are supported"
                )
            parameters[str(meta.get("rid"))] = self._encode_action_parameter(
                name, str(parameter_id), meta, static_value
            )

        validation = self._conjure(
            "POST",
            f"{_ACTIONS_VALIDATE_PATH}?owningRid={action_type_rid}",
            {
                "actionTypeRid": action_type_rid,
                "parameters": parameters,
                "parametersPrefill": {"all": {}, "type": "all"},
            },
            "validate action",
        )
        if validation.get("type") != "validResponse":
            raise FoundryApiError(
                "action validation did not return a validResponse",
                validation_details=validation,
            )
        valid_response = validation.get("validResponse")
        invalid: Dict[str, Any] = {}
        if isinstance(valid_response, Mapping):
            for section in ("results", "parameterResults"):
                entries = valid_response.get(section)
                if isinstance(entries, Mapping):
                    for key, entry in entries.items():
                        if (
                            not isinstance(entry, Mapping)
                            or entry.get("type") != "validResult"
                        ):
                            invalid[str(key)] = entry
        if invalid:
            raise FoundryApiError(
                "action validation failed; refusing to apply",
                validation_details=invalid,
            )

        outcome = self._conjure(
            "POST",
            _ACTIONS_APPLY_PATH,
            {
                "actionTypeRid": action_type_rid,
                "actionContext": {
                    "branchRid": ontology_branch_rid,
                    "loadActionEdits": True,
                    "parametersPrefill": {"all": {}, "type": "all"},
                },
                "parameters": parameters,
            },
            "apply action",
        )
        return json.dumps(outcome, indent=1, default=str)

    def _encode_action_parameter(
        self,
        tool: str,
        parameter_id: str,
        meta: Mapping[str, Any],
        static_value: Mapping[str, Any],
    ) -> Dict[str, Any]:
        base_type = static_value.get("baseType")
        value = static_value.get("value")
        meta_type = meta.get("type")
        parameter_type = meta_type if isinstance(meta_type, Mapping) else {}
        typename = parameter_type.get("__typename")
        object_type = parameter_type.get("objectType")
        if base_type != "object" or not isinstance(object_type, Mapping):
            raise UnverifiedContract(
                tool,
                f"parameter {parameter_id!r}: only object and object-list "
                "parameters were captured (objectLocator/objectLocatorList "
                f"encodings); got baseType {base_type!r} with parameter type "
                f"{typename!r}",
            )
        if typename == "ActionParameterType_Object":
            return {
                "objectLocator": self._object_locator(tool, object_type, value),
                "type": "objectLocator",
            }
        if typename == "ActionParameterType_ObjectList" and isinstance(value, list):
            return {
                "objectLocatorList": {
                    "objectList": [
                        self._object_locator(tool, object_type, item) for item in value
                    ]
                },
                "type": "objectLocatorList",
            }
        raise UnverifiedContract(
            tool,
            f"parameter {parameter_id!r}: parameter type {typename!r} with "
            f"value shape {type(value).__name__} was never captured",
        )

    def _object_locator(
        self, tool: str, object_type: Mapping[str, Any], primary_key_value: Any
    ) -> Dict[str, Any]:
        latest_raw = object_type.get("latest")
        latest = latest_raw if isinstance(latest_raw, Mapping) else {}
        pk_properties = latest.get("primaryKeyPropertiesV2")
        if not isinstance(pk_properties, list) or len(pk_properties) != 1:
            raise UnverifiedContract(
                tool,
                "composite or missing primary keys were never captured; only "
                "single-property primary keys were observed",
            )
        pk = pk_properties[0]
        pk_type = pk.get("type") if isinstance(pk, Mapping) else None
        typename = pk_type.get("__typename") if isinstance(pk_type, Mapping) else None
        if typename != "ObjectTypePropertyType_String":
            raise UnverifiedContract(
                tool,
                f"primary key type {typename!r} was never captured; only "
                "string primary keys were observed",
            )
        return {
            "objectTypeId": object_type.get("id"),
            "primaryKey": {
                str(pk.get("id")): {"string": primary_key_value, "type": "string"}
            },
        }

    def _exec_request_clarification_from_user(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        questions = args.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError("request_clarification_from_user requires 'questions'")
        if self._clarification_handler is None:
            return (
                "The operator cannot answer clarification questions in this "
                "run (non-interactive). Make reasonable assumptions, document "
                "them in your response, and proceed without asking again."
            )
        return self._clarification_handler(questions)

    def _exec_change_mode(self, name: str, args: Mapping[str, Any]) -> str:
        mode_config = args.get("modeConfig")
        if not isinstance(mode_config, Mapping):
            raise ValueError("change_mode requires a 'modeConfig' object")
        self._mode = str(mode_config.get("type"))
        return (
            f"<modeChange>{json.dumps(mode_config, separators=(',', ':'))}</modeChange>"
        )

    def _exec_enable_capabilities(self, name: str, args: Mapping[str, Any]) -> str:
        return self._set_capabilities(name, args, enable=True)

    def _exec_disable_capabilities(self, name: str, args: Mapping[str, Any]) -> str:
        return self._set_capabilities(name, args, enable=False)

    def _set_capabilities(
        self, name: str, args: Mapping[str, Any], *, enable: bool
    ) -> str:
        capabilities = args.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise ValueError(f"{name} requires a non-empty 'capabilities' list")
        unavailable: List[str] = []
        for capability in capabilities:
            tools = CAPABILITY_TOOL_MAP.get(str(capability))
            if tools is None:
                unavailable.append(str(capability))
                continue
            for tool in tools:
                if enable:
                    self._active_tools.add(tool)
                else:
                    self._active_tools.discard(tool)
        tag = "enableCapabilities" if enable else "disableCapabilities"
        payload = f"<{tag}>{json.dumps(capabilities)}</{tag}>"
        if unavailable:
            payload += (
                "\nThese capabilities have no registered tools in this CLI "
                f"loop and were ignored: {', '.join(unavailable)}."
            )
        return payload

    def _exec_manage_context(self, name: str, args: Mapping[str, Any]) -> str:
        ids = args.get("contextItemIds")
        action = args.get("action")
        if not isinstance(ids, list) or not ids:
            raise ValueError(
                "manage_context requires a non-empty 'contextItemIds' list"
            )
        if not isinstance(action, Mapping):
            raise ValueError("manage_context requires an 'action' object")
        kind = action.get("type")
        if kind == "hide":
            hidden = 0
            freed = 0
            for cid in ids:
                cid = str(cid)
                item = self._tool_output_items.get(cid)
                if item is None or cid in self._hidden:
                    continue
                freed += estimate_tokens(self._tool_output_payloads.get(cid, ""))
                self._hidden.add(cid)
                item["item"]["functionToolCallOutput"]["output"] = hidden_item_output(
                    cid, "tool-usage", self._cumulative_tokens
                )
                hidden += 1
            return (
                '<manageContextResult action="hide">\n'
                f"  <summary>{hidden} context items hidden. "
                f"Freed ~{freed} tokens.</summary>\n"
                "</manageContextResult>"
            )
        if kind == "unhide":
            restored = 0
            for cid in ids:
                cid = str(cid)
                item = self._tool_output_items.get(cid)
                payload = self._tool_output_payloads.get(cid)
                if item is None or payload is None or cid not in self._hidden:
                    continue
                self._hidden.discard(cid)
                item["item"]["functionToolCallOutput"]["output"] = wrap_context_item(
                    cid, "tool-usage", payload, self._cumulative_tokens
                )
                restored += 1
            return (
                '<manageContextResult action="unhide">\n'
                f"  <summary>{restored} context items restored.</summary>\n"
                "</manageContextResult>"
            )
        raise ValueError(f"manage_context action type {kind!r} is not hide|unhide")

    def _enabled_skill_rids(self) -> List[str]:
        if self._skill_rids_cache is not None:
            return self._skill_rids_cache
        if not self._thread_id:
            raise UnverifiedContract("load_skill", "no thread is bound to this run yet")
        agent_state = self._ai_fde_service().get_thread_agent_state(self._thread_id)
        session_state = agent_state.get("sessionState")
        configurations = (
            session_state.get("aipSkillConfigurations")
            if isinstance(session_state, Mapping)
            else None
        )
        rids = [
            str(rid)
            for rid, config in (configurations or {}).items()
            if isinstance(config, Mapping) and config.get("enabled")
        ]
        self._skill_rids_cache = rids
        return rids

    def _exec_load_skill(self, name: str, args: Mapping[str, Any]) -> str:
        skill_name = _require_str(args, "skillName", name)
        rids = self._enabled_skill_rids()
        if not rids:
            raise UnverifiedContract(
                name,
                "this thread's agentState advertises no enabled AIP skills "
                "(sessionState.aipSkillConfigurations is empty); skills cannot "
                "be resolved by name without it",
            )
        available: List[str] = []
        for rid in rids:
            payload = self._conjure(
                "GET", _SKILL_LATEST_PATH.format(rid=rid), None, "load AIP skill"
            )
            skill = payload.get("skill")
            content = skill.get("content") if isinstance(skill, Mapping) else None
            if not isinstance(content, Mapping):
                continue
            content_name = content.get("name")
            if isinstance(content_name, str):
                available.append(content_name)
            if content_name == skill_name:
                skill_text = str(content.get("skillText") or "")
                return (
                    f'<aip-skill skillRid="{rid}" name="{skill_name}">\n'
                    "  <note>This skill is loaded and active.</note>\n"
                    f"  <instructions>{skill_text}</instructions>\n"
                    "</aip-skill>"
                )
        raise ValueError(
            f"no enabled skill named {skill_name!r}; available: "
            f"{', '.join(available) or '(none)'}"
        )

    # --- context budgeting -------------------------------------------------

    def _truncate_if_needed(self, input_items: List[Dict[str, Any]]) -> None:
        """Replace oldest tool outputs with hidden placeholders over budget."""
        total = estimate_tokens(self._instructions())
        total += sum(
            estimate_tokens(json.dumps(spec)) for spec in self._active_tool_specs()
        )
        total += sum(estimate_tokens(json.dumps(item)) for item in input_items)
        if total <= CONTEXT_TOKEN_THRESHOLD:
            return
        truncated = 0
        for item in input_items:
            if total <= CONTEXT_TOKEN_THRESHOLD:
                break
            node = item.get("item") if isinstance(item, Mapping) else None
            if (
                not isinstance(node, dict)
                or node.get("type") != "functionToolCallOutput"
            ):
                continue
            output = node["functionToolCallOutput"]
            cid = str(output.get("callId"))
            if cid in self._hidden:
                continue
            before = estimate_tokens(str(output.get("output") or ""))
            self._hidden.add(cid)
            output["output"] = hidden_item_output(
                cid, "tool-usage", self._cumulative_tokens
            )
            total -= before - estimate_tokens(output["output"])
            truncated += 1
        if truncated:
            self._progress(
                f"context budget exceeded; truncated {truncated} oldest tool outputs"
            )

    # --- resume (derived; see module docstring) -----------------------------

    def _resume_items(self, thread_id: str) -> List[Dict[str, Any]]:
        service = self._ai_fde_service()
        items: List[Mapping[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            page = service.get_thread_items(
                thread_id, page_size=50, page_token=page_token
            )
            items.extend(page["contextItems"])
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        rebuilt: List[Dict[str, Any]] = []
        for item in items:
            cid = str(item.get("id") or "")
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for entry in content:
                if not isinstance(entry, Mapping):
                    continue
                entry_type = entry.get("type")
                if entry_type == "user-message":
                    prompt = str(entry.get("prompt") or "")
                    rebuilt.append(
                        input_message_item(
                            wrap_context_item(cid, "user-message", prompt, 0)
                        )
                    )
                elif entry_type == "assistant-message":
                    response = entry.get("response")
                    text = _output_message_text(
                        response if isinstance(response, Mapping) else {}
                    )
                    if text:
                        rebuilt.append(
                            {
                                "type": "item",
                                "item": {
                                    "type": "outputMessage",
                                    "outputMessage": {
                                        "id": f"msg_{cid}",
                                        "status": "COMPLETED",
                                        "content": [
                                            {"type": "text", "text": {"text": text}}
                                        ],
                                    },
                                },
                            }
                        )
                elif entry_type == "tool-usage":
                    tool_name = str(entry.get("toolName") or "")
                    request = entry.get("toolRequest")
                    arguments = json.dumps(request if request is not None else {})
                    rebuilt.append(function_tool_call_item(cid, tool_name, arguments))
                    note = (
                        "This tool call ran in a previous session. Its detailed "
                        "result is not persisted in the thread document and "
                        "cannot be reconstructed."
                    )
                    rebuilt.append(
                        function_tool_call_output_item(
                            cid, wrap_context_item(cid, "tool-usage", note, 0)
                        )
                    )
        return rebuilt

    # --- main loop ----------------------------------------------------------

    def run(
        self,
        instruction: str,
        *,
        thread_id: Optional[str] = None,
        thread_name: Optional[str] = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> Dict[str, Any]:
        """Create-or-resume a thread and drive the loop to completion.

        Returns a run report ``{threadId, status, turns, toolsCalled,
        toolCalls, finalText, usage, model}``.
        """
        service = self._ai_fde_service()
        if thread_id:
            metadata = service.get_thread_metadata(thread_id)
            version = metadata.get("version")
            order = [str(i) for i in metadata.get("contextItemsOrder") or []]
            if not isinstance(version, str) or not version:
                raise ValueError(
                    f"cannot resume thread {thread_id}: metadata has no version "
                    "(the thread may be redacted)"
                )
            input_items = self._resume_items(thread_id)
            self._progress(f"resumed thread {thread_id} ({len(order)} items)")
        else:
            created = service.create_thread(
                thread_name or f"pfoundry ai-fde run {date.today().isoformat()}"
            )
            thread_id = str(created["id"])
            version = str(created["version"])
            order = []
            input_items = []
            self._progress(f"created thread {thread_id}")
        self._thread_id = thread_id

        user_item = AiFdeService.build_user_message_item(instruction)
        user_item_id = user_item["contextItemId"]
        response = service.update_thread_items(
            thread_id, version, [*order, user_item_id], [user_item]
        )
        version = _thread_version(response)
        order.append(user_item_id)
        self._cumulative_tokens += estimate_tokens(instruction)
        input_items.append(
            input_message_item(
                wrap_context_item(
                    user_item_id, "user-message", instruction, self._cumulative_tokens
                )
            )
        )

        turns = 0
        tool_calls: List[Dict[str, Any]] = []
        final_text = ""
        usage_acc = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
        status = "completed"
        while turns < max_turns:
            turns += 1
            self._truncate_if_needed(input_items)
            self._progress(
                f"turn {turns}: calling {self.model} ({len(input_items)} input items)"
            )
            completed = self._llm().complete(
                thread_id=thread_id,
                instructions=self._instructions(),
                input_items=input_items,
                tools=self._active_tool_specs(),
            )
            for key in usage_acc:
                value = completed.usage.get(key)
                if isinstance(value, (int, float)):
                    usage_acc[key] += int(value)

            new_items: List[Dict[str, Any]] = []
            thread_items: List[Mapping[str, Any]] = []
            calls: List[Mapping[str, Any]] = []
            for output in completed.output:
                output_type = output.get("type")
                if output_type == "reasoning":
                    new_items.append({"type": "item", "item": dict(output)})
                elif output_type == "outputMessage":
                    new_items.append({"type": "item", "item": dict(output)})
                    text = _output_message_text(output.get("outputMessage") or output)
                    if text:
                        final_text = text
                        message_item = build_assistant_message_item(str(uuid4()), text)
                        thread_items.append(message_item)
                        order.append(message_item["contextItemId"])
                elif output_type == "functionToolCall":
                    calls.append(output)

            for call in calls:
                ftc = call.get("functionToolCall")
                if not isinstance(ftc, Mapping):
                    continue
                call_uuid = str(uuid4())
                tool_name = str(ftc.get("name") or "")
                raw_arguments = str(ftc.get("arguments") or "")
                new_items.append(
                    function_tool_call_item(call_uuid, tool_name, raw_arguments)
                )
                self._progress(f"turn {turns}: tool call {tool_name}")
                payload, state, tool_request = self._execute_tool(
                    tool_name, raw_arguments
                )
                self._cumulative_tokens += estimate_tokens(payload)
                output_item = function_tool_call_output_item(
                    call_uuid,
                    wrap_context_item(
                        call_uuid, "tool-usage", payload, self._cumulative_tokens
                    ),
                )
                self._tool_output_items[call_uuid] = output_item
                self._tool_output_payloads[call_uuid] = payload
                new_items.append(output_item)
                thread_items.append(
                    build_tool_usage_item(call_uuid, tool_name, tool_request, state)
                )
                order.append(call_uuid)
                tool_calls.append(
                    {
                        "name": tool_name,
                        "approved": state == "completed",
                        "state": state,
                    }
                )

            if thread_items:
                response = service.update_thread_items(
                    thread_id, version, order, thread_items
                )
                version = _thread_version(response)
            input_items.extend(new_items)
            if not calls:
                break
        else:
            status = "max-turns-reached"

        return {
            "threadId": thread_id,
            "status": status,
            "turns": turns,
            "toolsCalled": len(tool_calls),
            "toolCalls": tool_calls,
            "finalText": final_text,
            "usage": usage_acc,
            "model": self.model,
        }


def _thread_version(update_response: Mapping[str, Any]) -> str:
    metadata = update_response.get("metadata")
    version = metadata.get("threadVersion") if isinstance(metadata, Mapping) else None
    if not isinstance(version, str) or not version:
        raise ValueError(
            f"thread update response carried no metadata.threadVersion: "
            f"{str(update_response)[:200]!r}"
        )
    return version


def _require_str(args: Mapping[str, Any], key: str, tool: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{tool} requires a string '{key}'")
    return value


def _require_main_branch(branch: Any, tool: str) -> None:
    if branch != {"mainBranch": True}:
        raise UnverifiedContract(
            tool,
            "only the mainBranch arm was captured for target resolution; "
            f"got {branch!r}",
        )


def _extract_suite_definition(
    config: Mapping[str, Any], suite_rid: str
) -> Mapping[str, Any]:
    suites = config.get("evaluationSuites")
    entry = suites.get(suite_rid) if isinstance(suites, Mapping) else None
    suite = entry.get("evaluationSuite") if isinstance(entry, Mapping) else None
    if not isinstance(suite, Mapping):
        raise UnverifiedContract(
            "run_evaluation_suite",
            f"the v2 config read returned no definition for {suite_rid}: "
            f"{str(config)[:200]!r}",
        )
    return suite


def _parameter_schema_map(
    node: Mapping[str, Any], path: Sequence[str]
) -> Dict[str, str]:
    """Map schema entry name -> id along a nested path (empty map if absent)."""
    current: Any = node
    for segment in path:
        current = current.get(segment) if isinstance(current, Mapping) else None
    result: Dict[str, str] = {}
    if isinstance(current, list):
        for entry in current:
            if isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
                result[entry["name"]] = str(entry.get("id"))
    return result


def _decode_arrow_type(field: Any) -> Tuple[str, Optional[str]]:
    """Map one Arrow field to the captured column type vocabulary."""
    import pyarrow as pa

    array_subtype: Optional[str] = None
    t = field.type
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        name = "STRING"
    elif pa.types.is_int32(t) or pa.types.is_int16(t) or pa.types.is_int8(t):
        name = "INTEGER"
    elif pa.types.is_int64(t) or pa.types.is_uint64(t):
        name = "LONG"
    elif pa.types.is_floating(t):
        name = "DOUBLE"
    elif pa.types.is_boolean(t):
        name = "BOOLEAN"
    elif pa.types.is_timestamp(t):
        name = "TIMESTAMP"
    elif pa.types.is_date(t):
        name = "DATE"
    elif pa.types.is_list(t) or pa.types.is_large_list(t):
        name = "ARRAY"
        element = t.value_type
        if pa.types.is_string(element) or pa.types.is_large_string(element):
            subtype = "STRING"
        elif pa.types.is_integer(element):
            subtype = "LONG"
        elif pa.types.is_floating(element):
            subtype = "DOUBLE"
        elif pa.types.is_boolean(element):
            subtype = "BOOLEAN"
        else:
            subtype = str(element).upper()
        array_subtype = f'{{"type":"{subtype}","customMetadata":{{}}}}'
    else:
        name = str(t).upper()
    return name, array_subtype


def _decode_arrow_result(
    result_b64: str,
) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    """Decode the captured base64 Arrow IPC result into columns and rows."""
    import pyarrow.ipc as ipc
    import pyarrow.lib  # noqa: F401  (ArrowInvalid lives here)

    data = base64.b64decode(result_b64)
    try:
        reader = ipc.open_stream(io.BytesIO(data))
        table = reader.read_all()
    except Exception:
        reader = ipc.open_file(io.BytesIO(data))
        table = reader.read_all()
    columns: List[Dict[str, Any]] = []
    for arrow_field in table.schema:
        type_name, array_subtype = _decode_arrow_type(arrow_field)
        columns.append(
            {
                "name": arrow_field.name,
                "type": type_name,
                "nullable": arrow_field.nullable,
                "arraySubtype": array_subtype,
            }
        )
    rows: List[List[str]] = []
    pydict = table.to_pydict()
    names = table.column_names
    for row_index in range(table.num_rows):
        rows.append([_format_sql_value(pydict[name][row_index]) for name in names])
    return columns, rows


def _format_sql_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_format_sql_value(v) for v in value) + "]"
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _serialize_ontology_sql(
    query: str, columns: List[Dict[str, Any]], rows: List[List[str]]
) -> str:
    """Serialize one result in the captured ``<ontologySql>`` pattern."""
    column_lines = []
    for column in columns:
        attrs = (
            f'type="{column["type"]}" name="{column["name"]}"'
            + (" nullable" if column["nullable"] else "")
            + ' customMetadata="{}"'
        )
        if column["arraySubtype"]:
            attrs += f' arraySubtype="{column["arraySubtype"]}"'
        column_lines.append(f"      <column {attrs}/>")
    header = "|".join(column["name"] for column in columns)
    row_lines = ["|".join(row) for row in rows]
    result_body = "\n".join([header, *row_lines])
    return (
        "<ontologySql>\n"
        f"  <query>{query}</query>\n"
        f'  <ontology-sql-table rowCount="{len(rows)}">\n'
        "    <columns>\n"
        + ("\n".join(column_lines) + "\n" if column_lines else "")
        + "    </columns>\n"
        "    <result>\n"
        f"{result_body}\n"
        "</result>\n"
        "  </ontology-sql-table>\n"
        "</ontologySql>"
    )


__all__ = [
    "ACTION_TYPE_PARAMETERS_QUERY",
    "AgentLoop",
    "CAPABILITY_TOOL_MAP",
    "CONTEXT_TOKEN_THRESHOLD",
    "CompletedResponse",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_MODEL",
    "DEFAULT_TOOL_NAMES",
    "LATEST_FUNCTION_VERSION_QUERY",
    "LlmResponseShapeError",
    "LlmSession",
    "TOOL_REGISTRY",
    "ToolRegistration",
    "UnverifiedContract",
    "build_assistant_message_item",
    "build_tool_usage_item",
    "estimate_tokens",
    "function_tool_call_item",
    "function_tool_call_output_item",
    "hidden_item_output",
    "input_message_item",
    "wrap_context_item",
]
