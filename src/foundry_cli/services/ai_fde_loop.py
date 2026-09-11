"""
AI FDE client-side agent loop (LLM orchestration + tool execution).

The AI FDE agent loop runs client-side in the Foundry UI (see
``services/ai_fde.py``); this module reimplements that loop for the CLI:
build the OpenAI-Responses-shaped request, call the LLM, execute the
returned tool calls, write the results back into the thread document, and
repeat until the model stops calling tools.

Evidence: every contract below was captured from the live AI FDE UI via
Chrome DevTools Protocol (artifact
``/tmp/evals-capture/capture.jsonl``, 8143 requests; richest request artifact
``/tmp/ai-fde-richest-request.json`` with 170 input items and all 72 tool
specs) and the LLM call plus thread delta writes were live-verified
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
  (no endpoint). ``change_mode`` swaps the exposed tool set for subsequent
  LLM requests per the mined mode->tool-set mapping below;
  ``enable_capabilities``/``disable_capabilities`` toggle capability ->
  tool groups per the captured instructions block and the captured
  ``executeAction`` enablement; ``manage_context`` hides/restores tool
  outputs from subsequent request construction (captured
  ``<manageContextResult>`` and hidden-item serializations).
- ``load_object_types`` / ``load_action_types`` (read, LIVE): one ``POST
  /ontology-metadata/api/ontology/ontology/bulkLoadEntities`` per entity.
  Object types use the captured identifier-form body
  (``{objectTypes: [{identifier: {objectTypeRid, type: "objectTypeRid"}}],
  entityMetadata: {}, datasourceTypes: [...5 captured types...],
  includeObjectTypesWithoutSearchableDatasources: true, ...}``); action
  types use the captured rid-form body (``{actionTypes: [{rid}],
  loadRedacted: true, datasourceTypes: [], ...}``). Those are the only two
  bulkLoad forms in the capture; non-null ``ontologyBranchRid`` arguments
  fail closed (never captured).
- ``load_link_types`` (read, LIVE): the pinned ``LinkTypeMainQuery``
  GraphQL read per link type RID (captured batched 31 RIDs in one bulk
  call). The bulkLoad ``linkTypes`` request form was never captured, so
  the GraphQL read is used instead; non-null branches fail closed.
- ``get_link_types_for_object_type`` / ``get_action_types_for_object_type``
  (read, LIVE): the pinned ``AssociatedLinkTypesForObjectTypeMainQuery``
  / ``AssociatedActionTypeRidsMainQuery`` GraphQL reads (variables carry
  only ``objectTypeRid``), followed by the detail loads above
  (``LinkTypeMainQuery`` per link type; rid-form bulkLoad per action
  type). Pagination was never captured: only the first page of action
  types is returned, with a ``_truncated`` marker when the page carries a
  ``nextPageToken``. Non-null ``ontologyBranchRid`` fails closed.
- ``load_object_sets`` (read, LIVE): ``GET /object-set-service/api/
  objectSets/{objectSetRid}`` per RID (captured). The captured GETs carry
  no branch parameter, so a non-null ``ontologyBranchRid`` fails closed.
- ``get_evaluation_suites_for_target`` (read, LIVE): only the captured
  arms — ``target == {"type": "function", "rid": ...}`` and
  ``branch == {"mainBranch": true}``. Delegates to ``EvalsService``
  (``config/v2/target/get-evaluation-suites`` then ``config/v2/get`` per
  suite, both captured in this tool's execution window).
- ``load_functions`` (read, LIVE): ``GET /function-registry/api/
  functions/{functionRid}/specs/{version}`` per function (captured,
  visible response). A null ``version`` resolves through the pinned
  ``LatestFunctionVersionQuery`` (main branch); a non-null
  ``ontologyBranchRid`` fails closed (never captured).
- ``load_code_repo`` (read, LIVE): only the captured ``{"mainBranch":
  true}`` arm. ``GET /stemma/api/repos/{rid}/resolve/refs%2Fheads%2F
  master`` then ``GET .../paths/contents/%2F?commitish=refs%2Fheads%2F
  master`` (root listing) and ``GET .../paths/contents/AGENTS.md?
  commitish=...`` (the captured triple; a missing AGENTS.md is reported
  as null, matching the UI's best-effort load).
- ``load_pull_request`` (read, LIVE): delegates to
  ``RepositoryService.get_pull_request`` (contract-verified ``GET
  /stemma-pull-request/api/pulls/{pullRequestRid}``).
- ``container_git_status`` (read, LIVE — boots a container deployment as
  a side effect, exactly as the captured UI does): pinned
  ``GetContainersForRepository`` GraphQL read (first non-trashed ``CODE``
  container) -> ``POST /foundry-container-service/api/containers/{rid}/
  deployments`` (captured empty body) -> poll ``GET .../deployments/
  {rid}/status`` until ``running`` (captured states: starting,
  initializing, launching, running) -> ``GET .../deployments/{rid}/
  git/status`` (visible ``{gitStatus: {head, fileChanges}}`` response).
- ``container_execute_terminal_command`` (write, LIVE, approval-gated):
  the same container chain, then ``POST .../deployments/{rid}/terminal/
  execute-command`` with the captured ``{command, directory?}`` body and
  visible ``{exitCode, stdout, stderr}`` response, serialized in the
  captured "Terminal command executed: ... with exit code N" pattern.
  The UI's read-only command auto-approval classifier is NOT captured, so
  every terminal command goes through the operator approval gate instead.
- ``load_documentation`` / ``load_documentation_bundles`` (read, FAIL
  CLOSED): no documentation page-load endpoint appears anywhere in the
  8143-request capture — the only ``/documentation/api/`` call is
  ``/documentation/api/v2/release-notes/pagination``, a different surface
  (workspace release notes). The specs are registered verbatim but the
  executors raise ``UnverifiedContract`` rather than guess a contract.
- ``ci_checks`` (FAIL CLOSED): the tool was never exercised in the
  capture. The only CI endpoints present are heavy UI background polling
  for already-known job/build RIDs (``GET /build2/api/info/jobs3/
  {jobRid}``, ``GET /job-tracker/api/builds/{buildRid}``); the
  repositoryRid+branch -> job/check mapping the tool contract needs was
  never captured.
- Schedules family (``get_dataset_schedules``, ``run_schedule``,
  ``pause_schedule``, ``unpause_schedule``, ``create_schedule``,
  ``replace_schedule``, ``delete_schedule`` — FAIL CLOSED): no
  schedule/orchestration endpoint appears anywhere in the 8143-request
  capture, even though the 72-tool set exposes the specs.
- ``container_get_file_contents`` (FAIL CLOSED): the endpoint was
  captured (``GET .../deployments/{rid}/files/contents/{path}``, HTTP
  200) but every response body was elided by the capture, so the result
  contract is unknown. ``container_put_file`` / ``container_edit_file`` /
  ``container_sync`` / ``container_copy_blobster_file_to_repo`` fail
  closed for the same reason (terminal proxy traffic was captured but
  the mutation contracts were not).
- ``get_evaluation_suite_project_scope_readiness`` (FAIL CLOSED): the
  core ``suggestedExecutionScope`` call is captured (and exposed via
  ``evals suite suggested-scope``), but the full tool flow also posts a
  project-imports context body whose resource-RID list construction was
  not fully captured.
- Logic family (12 tools), ``await_automation_execution``,
  ``search_language_model_functions`` / ``get_language_model_function``,
  ``get_ontology_sdk_documentation``, ``refresh_ontology_sdk``,
  ``get_functions_repository_imports`` /
  ``edit_functions_repository_imports``, ``run_functions_diagnostics``,
  ``function_preview``, ``publish_functions``, ``create_branch``,
  ``create_code_repo``, ``create_or_update_pull_request``,
  ``add_missing_project_imports``,
  ``edit_code_workspace_source_imports``, ``upgrade_code_repository``,
  ``create_evaluation_suite`` / ``edit_evaluation_suite`` /
  ``put_evaluation_suite`` (FAIL CLOSED): no endpoint for these tools
  appears in the capture (their tool sets were exposed, but the tools
  were never exercised while the network was recorded).

Mode -> tool-set mapping (mined from the capture; the request tool list
matches the ``agentStateModification.toolConfigurations`` enabled map
written to thread metadata at each transition):

- No mode selected (the default; captured ``<selectedMode>none``): the
  8 base tools — ``change_mode``, ``enable_capabilities``,
  ``disable_capabilities``, ``manage_context``,
  ``request_clarification_from_user``, ``load_skill``,
  ``load_documentation``, ``load_documentation_bundles``.
- ``functionsEditing`` (the only mode ever selected in the capture;
  config with ``functionsType.selected == "typescriptV2"``, ``evals``,
  ``useLanguageModels``): the base 8 plus 43 more (51 total) — see
  ``MODE_TOOL_SETS``.
- ``executeAction`` capability enabled on top of ``functionsEditing``:
  adds ``execute_action`` AND ``await_automation_execution`` (53 total;
  the captured ``enable_capabilities {"capabilities": ["executeAction"]}``
  call added both to the next request's tool list).
- The 72-tool superset (51 + the 7 schedule tools + the 12 logic tools +
  the 2 executeAction tools): the schedule and logic families were added
  client-side mid-session with no capability name recorded anywhere in
  the capture (modeConfig and sessionState are byte-identical across the
  transition; only ``toolConfigurations`` changed). Exposed from turn 1
  via ``ai-fde run --all-tools``.
- Other modes advertised in the captured instructions
  (``dataIntegration``, ``dataConnection``, ``ontologyEditing``,
  ``exploration``, ``governance``, ``applicationBuilding``,
  ``platformQna``, ``machineLearning``) were never selected, so their
  tool sets are unknown: ``change_mode`` to one keeps the current set
  and says so in the tool output.

CLI-native extension tools (NOT part of the captured catalog): the
``pfoundry_*`` tools in ``EXTENSION_TOOL_REGISTRY`` are synthetic tools
this CLI adds beyond the captured 72, because live runs proved the
catalog alone cannot answer "show me the most recent runs of the <name>
pipeline" (no name-search tool exists even in the full catalog, and no
build-history/dataset-transaction tool exists at all). They wrap
pfoundry's already-verified surfaces — public SDK / existing service
contracts, no captured-contract claims — and are always exposed (not
mode-gated), all read-risk, executed through the same
approval/write-back machinery. See ``ai_fde_extension_tools.py`` for the
per-tool wrapper mapping.

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
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid4

import requests

from ..auth.base import MissingCredentialsError
from ..auth.storage import CredentialStorage
from .ai_fde import AiFdeService
from .ai_fde_extension_tools import EXTENSION_TOOL_SPECS, ExtensionToolExecutor
from .ai_fde_tool_specs import CAPTURED_INSTRUCTIONS_PREFIX, TOOL_SPECS
from .errors import FoundryApiError, foundry_error_from_conjure
from .evals import EvalsService
from .foundry_internal_client import FoundryInternalClient

DEFAULT_MODEL = "GPT_5_6_SOL"
DEFAULT_MAX_TURNS = 25
# Context budget for one request, in estimated tokens (chars/4). The
# captured instructions block states a 1,050,000-token context window
# with a 300,000-token recommended limit; the threshold stays just under
# the recommended limit so the full 72-tool catalog (~140k estimated
# tokens of specs) plus a long conversation still fits.
CONTEXT_TOKEN_THRESHOLD = 280_000
LLM_REQUEST_TIMEOUT = 240.0

_LLM_PATH = "language-model-service/api/llm/v3/completion/{model}/streamCompletionChunk"
_SQL_QUERY_PATH = "object-set-service/api/sql-endpoint/v1/queries/query"
_BULK_LOAD_ENTITIES_PATH = "ontology-metadata/api/ontology/ontology/bulkLoadEntities"
_ACTIONS_VALIDATE_PATH = "actions/api/actions/validate"
_ACTIONS_APPLY_PATH = "actions/api/actionsV2"
_SKILL_LATEST_PATH = "aip-agents/api/skills/{rid}/latest"
_OBJECT_SET_PATH = "object-set-service/api/objectSets/{rid}"
_FUNCTION_SPECS_PATH = "function-registry/api/functions/{rid}/specs/{version}"
_STEMMA_RESOLVE_PATH = "stemma/api/repos/{rid}/resolve/refs%2Fheads%2Fmaster"
_STEMMA_CONTENTS_PATH = "stemma/api/repos/{rid}/paths/contents/{path}"
_STEMMA_COMMITISH = "commitish=refs%2Fheads%2Fmaster"
_CONTAINER_DEPLOYMENTS_PATH = (
    "foundry-container-service/api/containers/{container_rid}/deployments"
)
_DEPLOYMENT_STATUS_PATH = (
    "foundry-container-service/api/deployments/{deployment_rid}/status"
)
_DEPLOYMENT_GIT_STATUS_PATH = (
    "foundry-container-service/api/deployments/{deployment_rid}/git/status"
)
_DEPLOYMENT_EXECUTE_COMMAND_PATH = (
    "foundry-container-service/api/deployments/{deployment_rid}/terminal/"
    "execute-command"
)

# Additive CLI-specific guidance appended after the captured instructions;
# NOT part of the captured block (it describes this loop's own constraints).
_CLI_NOTES = """
<cliNotes>
You are running inside the pfoundry CLI agent loop, not the Foundry UI.
- Write tools (execute_action, run_evaluation_suite,
  container_execute_terminal_command) execute only after operator
  approval. If a write is declined, continue without it.
- request_clarification_from_user may be unavailable in non-interactive
  runs; then make reasonable assumptions, state them, and proceed.
- There is NO resource-search tool (even in the full AI FDE catalog):
  resources are identified by explicit RIDs or user @-mentions. If you
  need a resource and do not have its RID, ask the operator for the RID
  instead of searching by name.
- Tools whose endpoint contract was never captured fail closed with an
  explanatory message (this includes the documentation tools, the
  schedules family, ci_checks, and the logic family). Do not retry a
  fail-closed tool with the same contract; use change_mode or ask the
  operator instead.
- Tools named pfoundry_* are CLI-provided extension tools (NOT part of
  the captured AI FDE catalog): pfoundry_search_resources resolves
  resource NAMES to RIDs, pfoundry_search_object_types finds ontology
  object types by name (object types are not Compass resources),
  pfoundry_search_builds lists recent pipeline
  runs (optionally filtered to the builds that produced a dataset),
  pfoundry_get_dataset_transactions lists a dataset's transaction
  history, and pfoundry_get_resource loads resource metadata by RID.
  Prefer them for resource discovery and build observability questions.
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

ASSOCIATED_LINK_TYPES_QUERY = """query AssociatedLinkTypesForObjectTypeMainQuery($objectTypeRid: RID!) {
  objectTypeV2(identifier: {rid: $objectTypeRid}) {
    latest {
      linksIncludingLinksToObjectTypesWithoutSearchableDatasources {
        linkType {
          linkType {
            rid
            _id
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
    _id
    __typename
  }
  __typename
}"""

ASSOCIATED_ACTION_TYPE_RIDS_QUERY = """query AssociatedActionTypeRidsMainQuery($objectTypeRid: RID!, $nextPageToken: String) {
  objectTypeV2(identifier: {rid: $objectTypeRid}) {
    latest {
      associatedActionTypesV2(pageSize: 20, pageToken: $nextPageToken) {
        ... on ActionTypeVersionPage {
          values {
            actionTypeRid
            _id
            __typename
          }
          nextPageToken
          __typename
        }
        ... on AssociatedActionTypesError {
          reason
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
  __typename
}"""

GET_CONTAINERS_FOR_REPOSITORY_QUERY = """query GetContainersForRepository($repositoryRid: RID!) {
  stemmaRepository(rid: $repositoryRid) {
    containers {
      ...GetEditorContainerFragment
      rid
      metadata {
        trashedStatus
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

fragment GetEditorContainerFragment on Container {
  imageType
  metadata {
    created {
      time
      __typename
    }
    _id
    __typename
  }
  _id
  __typename
}"""

# Verbatim from the capture (289 lines; the UI issues one bulk request
# with one LinkTypeMainQuery request per link type RID).
LINK_TYPE_MAIN_QUERY = """query LinkTypeMainQuery($linkTypeRid: RID!) {
  linkType(rid: $linkTypeRid) {
    latest {
      ...LinkTypeDetailsFragment
      _id
      __typename
    }
    _id
    __typename
  }
  __typename
}

fragment LinkTypeDetailsFragment on LinkTypeVersion {
  linkType {
    rid
    id
    ontology {
      rid
      namespace {
        rid
        _id
        __typename
      }
      _id
      __typename
    }
    metadata {
      description
      ...SaveLocationFragment
      _id
      __typename
    }
    _id
    __typename
  }
  status {
    __typename
  }
  dataSources {
    _id
    ... on LinkTypeDataSource_CatalogBranch {
      ...LinkTypeDatasetFragment
      __typename
    }
    __typename
  }
  definition {
    ... on LinkTypeDefinition_OneToMany {
      ...ManyToOneConfigFragment
      __typename
    }
    ... on LinkTypeDefinition_ManyToMany {
      ...ManyToManyConfigFragment
      __typename
    }
    ... on LinkTypeDefinition_Intermediary {
      ...ObjectBackedConfigFragment
      __typename
    }
    __typename
  }
  _id
  __typename
}

fragment SaveLocationFragment on ResourceMetadata {
  parent {
    rid
    resource {
      _id
      ... on Project {
        type
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

fragment LinkTypeDatasetFragment on LinkTypeDataSource_CatalogBranch {
  datasetRid
  objectTypeAPrimaryKeyMapping {
    columnName
    __typename
  }
  objectTypeBPrimaryKeyMapping {
    columnName
    __typename
  }
  _id
  __typename
}

fragment ManyToOneConfigFragment on LinkTypeDefinition_OneToMany {
  manySide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    cardinality
    _id
    __typename
  }
  oneSidePrimaryKeyPropertyV2 {
    apiName
    _id
    __typename
  }
  manySideForeignKeyPropertyV2 {
    id
    apiName
    _id
    __typename
  }
  oneSide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    _id
    __typename
  }
  __typename
}

fragment LinkSideMetadataFragment on LinkTypeMetadata {
  displayName
  pluralDisplayName
  visibility
  apiName
  __typename
}

fragment LinkTypeObjectTypeFragment on ObjectTypeVersion {
  ...ObjectTypeTitleFragment
  objectType {
    rid
    _id
    __typename
  }
  _id
  __typename
}

fragment ObjectTypeTitleFragment on ObjectTypeVersion {
  objectTypeApiName: apiName
  displayName
  objectTypeIcon: iconV2 {
    ...ObjectTypeIconFragment
    __typename
  }
  objectType {
    id
    _id
    __typename
  }
  status {
    ...ObjectTypeStatusTypeFragment
    __typename
  }
  _id
  __typename
}

fragment ObjectTypeIconFragment on BlueprintIcon {
  locator
  color
  __typename
}

fragment ObjectTypeStatusTypeFragment on ObjectTypeStatus {
  ... on ObjectTypeStatus {
    __typename
  }
  __typename
}

fragment ManyToManyConfigFragment on LinkTypeDefinition_ManyToMany {
  aSide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    _id
    __typename
  }
  bSide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    _id
    __typename
  }
  settings {
    editable
    __typename
  }
  __typename
}

fragment ObjectBackedConfigFragment on LinkTypeDefinition_Intermediary {
  intermediaryObjectTypeV2 {
    objectType {
      rid
      _id
      __typename
    }
    _id
    __typename
  }
  aSide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    _id
    __typename
  }
  aSideToIntermediarySide {
    linkType {
      linkType {
        rid
        _id
        __typename
      }
      _id
      __typename
    }
    _id
    __typename
  }
  bSide {
    metadata {
      ...LinkSideMetadataFragment
      __typename
    }
    objectTypeV2 {
      ...LinkTypeObjectTypeFragment
      _id
      __typename
    }
    _id
    __typename
  }
  bSideToIntermediarySide {
    linkType {
      linkType {
        rid
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
    cli_extension: bool = False  # CLI-native tool, not part of the captured 72


_NO_SCHEDULE_ENDPOINT = (
    "no schedule/orchestration endpoint appears anywhere in the 8143-request capture"
)
_NO_LOGIC_ENDPOINT = "no logic-authoring endpoint for this tool appears in the capture"

# Fail-closed tools whose contract would be a mutation; the class is kept
# accurate so a future live wiring is approval-gated from day one.
_FAIL_CLOSED_WRITE_RISKS: Dict[str, str] = {
    name: "write"
    for name in (
        "add_missing_project_imports",
        "container_copy_blobster_file_to_repo",
        "container_edit_file",
        "container_put_file",
        "container_sync",
        "create_branch",
        "create_code_repo",
        "create_evaluation_suite",
        "create_logic_function",
        "create_or_update_pull_request",
        "create_schedule",
        "delete_schedule",
        "edit_code_workspace_source_imports",
        "edit_evaluation_suite",
        "edit_functions_repository_imports",
        "edit_logic_function_definition",
        "modify_logic_function_metadata",
        "pause_schedule",
        "publish_functions",
        "publish_logic_function",
        "put_evaluation_suite",
        "put_logic_function_definition",
        "refresh_ontology_sdk",
        "replace_schedule",
        "run_schedule",
        "unpause_schedule",
        "upgrade_code_repository",
    )
}

_LIVE_TOOLS: Dict[str, Tuple[str, str]] = {
    # name -> (risk, AgentLoop executor method); contracts in the docstring
    "ontology_sql_query": ("read", "_exec_ontology_sql_query"),
    "list_evaluation_runs": ("read", "_exec_list_evaluation_runs"),
    "load_evaluation_runs": ("read", "_exec_load_evaluation_runs"),
    "get_test_case_results": ("read", "_exec_get_test_case_results"),
    "get_evaluation_suite_definition": (
        "read",
        "_exec_get_evaluation_suite_definition",
    ),
    "get_evaluation_suites_for_target": (
        "read",
        "_exec_get_evaluation_suites_for_target",
    ),
    "run_evaluation_suite": ("write", "_exec_run_evaluation_suite"),
    "execute_action": ("write", "_exec_execute_action"),
    "request_clarification_from_user": (
        "read",
        "_exec_request_clarification_from_user",
    ),
    "change_mode": ("read", "_exec_change_mode"),
    "enable_capabilities": ("read", "_exec_enable_capabilities"),
    "disable_capabilities": ("read", "_exec_disable_capabilities"),
    "manage_context": ("read", "_exec_manage_context"),
    "load_skill": ("read", "_exec_load_skill"),
    "load_object_types": ("read", "_exec_load_object_types"),
    "load_action_types": ("read", "_exec_load_action_types"),
    "load_link_types": ("read", "_exec_load_link_types"),
    "get_action_types_for_object_type": (
        "read",
        "_exec_get_action_types_for_object_type",
    ),
    "get_link_types_for_object_type": ("read", "_exec_get_link_types_for_object_type"),
    "load_object_sets": ("read", "_exec_load_object_sets"),
    "load_functions": ("read", "_exec_load_functions"),
    "load_code_repo": ("read", "_exec_load_code_repo"),
    "load_pull_request": ("read", "_exec_load_pull_request"),
    "container_git_status": ("read", "_exec_container_git_status"),
    "container_execute_terminal_command": (
        "write",
        "_exec_container_execute_terminal_command",
    ),
}

# Fail-closed tools: spec exposed verbatim, executor raises
# UnverifiedContract with this reason (evidence in the module docstring).
_FAIL_CLOSED_TOOLS: Dict[str, str] = {
    "load_documentation": (
        "no documentation page-load endpoint was captured (the only "
        "/documentation/api/ call in the 8143-request capture is "
        "/v2/release-notes/pagination, a different surface); the "
        "documentation tools are registered spec-only and fail closed"
    ),
    "load_documentation_bundles": (
        "no documentation bundle-load endpoint was captured"
    ),
    "ci_checks": (
        "ci_checks was never exercised in the capture; only polling "
        "endpoints for already-known job/build RIDs were recorded "
        "(GET /build2/api/info/jobs3/{jobRid}, GET "
        "/job-tracker/api/builds/{buildRid}) — the repositoryRid+branch "
        "to check mapping was never captured"
    ),
    "container_get_file_contents": (
        "the container files/contents endpoint was captured (HTTP 200) "
        "but every response body was elided by the capture, so the "
        "result contract is unknown"
    ),
    "container_put_file": "no container file-write contract was captured",
    "container_edit_file": "no container file-edit contract was captured",
    "container_sync": "no container sync/commit contract was captured",
    "container_copy_blobster_file_to_repo": ("no blobster copy contract was captured"),
    "get_evaluation_suite_project_scope_readiness": (
        "the full readiness flow was only partially captured (the "
        "project-imports context body construction was not); use "
        "'pfoundry evals suite suggested-scope' for the captured core"
    ),
    "await_automation_execution": (
        "no automation-execution endpoint appears in the capture"
    ),
    "get_dataset_schedules": _NO_SCHEDULE_ENDPOINT,
    "run_schedule": _NO_SCHEDULE_ENDPOINT,
    "pause_schedule": _NO_SCHEDULE_ENDPOINT,
    "unpause_schedule": _NO_SCHEDULE_ENDPOINT,
    "create_schedule": _NO_SCHEDULE_ENDPOINT,
    "replace_schedule": _NO_SCHEDULE_ENDPOINT,
    "delete_schedule": _NO_SCHEDULE_ENDPOINT,
    "create_logic_function": _NO_LOGIC_ENDPOINT,
    "edit_logic_function_definition": _NO_LOGIC_ENDPOINT,
    "put_logic_function_definition": _NO_LOGIC_ENDPOINT,
    "publish_logic_function": _NO_LOGIC_ENDPOINT,
    "modify_logic_function_metadata": _NO_LOGIC_ENDPOINT,
    "get_logic_function_definition": _NO_LOGIC_ENDPOINT,
    "get_logic_function_metadata": _NO_LOGIC_ENDPOINT,
    "get_logic_execution_details": _NO_LOGIC_ENDPOINT,
    "list_logic_blocks": _NO_LOGIC_ENDPOINT,
    "list_logic_executions": _NO_LOGIC_ENDPOINT,
    "lookup_logic_block_declarations": _NO_LOGIC_ENDPOINT,
    "preview_run_logic_function": _NO_LOGIC_ENDPOINT,
    "search_language_model_functions": (
        "no language-model search endpoint appears in the capture"
    ),
    "get_language_model_function": (
        "no language-model function endpoint appears in the capture"
    ),
    "get_ontology_sdk_documentation": (
        "no OSDK documentation endpoint appears in the capture"
    ),
    "refresh_ontology_sdk": "no SDK refresh endpoint appears in the capture",
    "get_functions_repository_imports": (
        "no repository-imports read endpoint appears in the capture"
    ),
    "edit_functions_repository_imports": (
        "no repository-imports edit endpoint appears in the capture"
    ),
    "run_functions_diagnostics": (
        "no functions diagnostics endpoint appears in the capture"
    ),
    "function_preview": "no function preview endpoint appears in the capture",
    "publish_functions": "no function publish endpoint appears in the capture",
    "create_branch": "no branch-creation endpoint appears in the capture",
    "create_code_repo": "no repo-creation endpoint appears in the capture",
    "create_or_update_pull_request": (
        "no pull-request create/update call was captured from this tool "
        "(the verified stemma-pull-request contracts are exposed via the "
        "'proposal code-pr' commands instead)"
    ),
    "add_missing_project_imports": (
        "no project-imports edit endpoint appears in the capture"
    ),
    "edit_code_workspace_source_imports": (
        "no code-workspace imports endpoint appears in the capture"
    ),
    "upgrade_code_repository": (
        "no repository upgrade endpoint appears in the capture"
    ),
    "create_evaluation_suite": ("no suite-creation endpoint appears in the capture"),
    "edit_evaluation_suite": "no suite-edit endpoint appears in the capture",
    "put_evaluation_suite": "no suite-put endpoint appears in the capture",
}

TOOL_REGISTRY: Dict[str, ToolRegistration] = {
    **{
        name: ToolRegistration(name, risk, executor, live=True)
        for name, (risk, executor) in _LIVE_TOOLS.items()
    },
    **{
        name: ToolRegistration(
            name,
            _FAIL_CLOSED_WRITE_RISKS.get(name, "read"),
            "_exec_fail_closed",
            live=False,
            note=note,
        )
        for name, note in _FAIL_CLOSED_TOOLS.items()
    },
}

_missing = set(TOOL_SPECS) - set(TOOL_REGISTRY)
_extra = set(TOOL_REGISTRY) - set(TOOL_SPECS)
if _missing or _extra:
    raise RuntimeError(
        f"TOOL_REGISTRY/TOOL_SPECS drift: missing={sorted(_missing)}, "
        f"extra={sorted(_extra)}"
    )

# The captured default: no mode selected exposes these 8 base tools.
BASE_TOOL_NAMES: Tuple[str, ...] = (
    "change_mode",
    "disable_capabilities",
    "enable_capabilities",
    "load_documentation",
    "load_documentation_bundles",
    "load_skill",
    "manage_context",
    "request_clarification_from_user",
)

# Mined mode -> tool-set mapping (see the module docstring). Only
# functionsEditing was ever selected in the capture; the 51-tool set is
# BASE_TOOL_NAMES plus the tools below.
_FUNCTIONS_EDITING_EXTRA: Tuple[str, ...] = (
    "add_missing_project_imports",
    "ci_checks",
    "container_copy_blobster_file_to_repo",
    "container_edit_file",
    "container_execute_terminal_command",
    "container_get_file_contents",
    "container_git_status",
    "container_put_file",
    "container_sync",
    "create_branch",
    "create_code_repo",
    "create_evaluation_suite",
    "create_or_update_pull_request",
    "edit_code_workspace_source_imports",
    "edit_evaluation_suite",
    "edit_functions_repository_imports",
    "function_preview",
    "get_action_types_for_object_type",
    "get_evaluation_suite_definition",
    "get_evaluation_suite_project_scope_readiness",
    "get_evaluation_suites_for_target",
    "get_functions_repository_imports",
    "get_language_model_function",
    "get_link_types_for_object_type",
    "get_ontology_sdk_documentation",
    "get_test_case_results",
    "list_evaluation_runs",
    "load_action_types",
    "load_code_repo",
    "load_evaluation_runs",
    "load_functions",
    "load_link_types",
    "load_object_sets",
    "load_object_types",
    "load_pull_request",
    "ontology_sql_query",
    "publish_functions",
    "put_evaluation_suite",
    "refresh_ontology_sdk",
    "run_evaluation_suite",
    "run_functions_diagnostics",
    "search_language_model_functions",
    "upgrade_code_repository",
)

MODE_TOOL_SETS: Dict[str, Tuple[str, ...]] = {
    "functionsEditing": BASE_TOOL_NAMES + _FUNCTIONS_EDITING_EXTRA,
}

# Modes advertised in the captured instructions but never selected, so
# their tool sets are unknown; change_mode keeps the current set.
UNCAPTURED_MODE_TYPES: Tuple[str, ...] = (
    "applicationBuilding",
    "dataConnection",
    "dataIntegration",
    "exploration",
    "governance",
    "machineLearning",
    "ontologyEditing",
    "platformQna",
)

# Capability -> registered tools, per the captured instructions block and
# the captured executeAction enablement (which added BOTH execute_action
# and await_automation_execution to the next request's tool list).
CAPABILITY_TOOL_MAP: Dict[str, Tuple[str, ...]] = {
    "changeMode": ("change_mode",),
    "requestClarification": ("request_clarification_from_user",),
    "loadDocumentation": ("load_documentation", "load_documentation_bundles"),
    "manageContext": ("manage_context",),
    "manageCapabilities": ("enable_capabilities", "disable_capabilities"),
    "executeAction": ("execute_action", "await_automation_execution"),
    "loadSkills": ("load_skill",),
}

DEFAULT_TOOL_NAMES: Tuple[str, ...] = BASE_TOOL_NAMES

ALL_TOOL_NAMES: Tuple[str, ...] = tuple(sorted(TOOL_REGISTRY))

# CLI-native extension tools (see ai_fde_extension_tools.py): pfoundry's
# own synthetic tools BEYOND the captured 72, wrapping already-verified
# services (compass title search, SDK Build.search/Build.jobs, dataset
# transactions, resource get) because the captured catalog has no
# name-search or build-history tool. Always exposed, never mode-gated,
# all read-risk.
EXTENSION_TOOL_REGISTRY: Dict[str, ToolRegistration] = {
    name: ToolRegistration(
        name,
        "read",
        "_exec_extension",
        live=True,
        note="CLI extension (public SDK / existing service contract)",
        cli_extension=True,
    )
    for name in EXTENSION_TOOL_SPECS
}

_extension_collisions = set(EXTENSION_TOOL_SPECS) & set(TOOL_SPECS)
if _extension_collisions:
    raise RuntimeError(
        f"extension tools collide with the captured catalog: "
        f"{sorted(_extension_collisions)}"
    )


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
        all_tools: bool = False,
        service: Optional[AiFdeService] = None,
        evals_service: Optional[EvalsService] = None,
        repository_service: Optional[Any] = None,
        extension_executor: Optional[ExtensionToolExecutor] = None,
        llm_session: Optional[LlmSession] = None,
        internal_client: Optional[FoundryInternalClient] = None,
        progress: Optional[Callable[[str], None]] = None,
        confirm: Optional[Callable[[str], bool]] = None,
        clarification_handler: Optional[Callable[[Sequence[Any]], str]] = None,
        instructions: Optional[str] = None,
        container_boot_timeout: float = 120.0,
        container_poll_interval: float = 2.0,
    ) -> None:
        if approve not in {"interactive", "always", "never"}:
            raise ValueError(
                f"approve must be interactive|always|never, got {approve!r}"
            )
        self.profile = profile
        self.model = model
        self.approve = approve
        if all_tools:
            names = list(ALL_TOOL_NAMES)
        else:
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
        self._repository_service = repository_service
        self._extension_executor = extension_executor
        self._llm_session = llm_session
        self._internal_client = internal_client
        self._progress = progress or (lambda _msg: None)
        self._confirm = confirm
        self._clarification_handler = clarification_handler
        self._instructions_override = instructions
        self._container_boot_timeout = container_boot_timeout
        self._container_poll_interval = container_poll_interval
        self._mode: Optional[str] = None
        self._thread_id: Optional[str] = None
        self._cumulative_tokens = 0
        self._hidden: set[str] = set()
        self._tool_output_items: Dict[str, Dict[str, Any]] = {}
        self._tool_output_payloads: Dict[str, str] = {}
        self._object_type_id_cache: Dict[str, str] = {}
        self._object_type_load_cache: Dict[str, Dict[str, Any]] = {}
        self._skill_rids_cache: Optional[List[str]] = None
        self._container_deployment_cache: Dict[str, str] = {}
        self._consecutive_clarifications = 0
        self._turns_remaining = DEFAULT_MAX_TURNS

    # --- wiring --------------------------------------------------------

    def _ai_fde_service(self) -> AiFdeService:
        if self._service is None:
            self._service = AiFdeService(profile=self.profile)
        return self._service

    def _evals(self) -> EvalsService:
        if self._evals_service is None:
            self._evals_service = EvalsService(profile=self.profile)
        return self._evals_service

    def _repository(self) -> Any:
        if self._repository_service is None:
            from .repository import RepositoryService

            self._repository_service = RepositoryService(profile=self.profile)
        return self._repository_service

    def _extensions(self) -> ExtensionToolExecutor:
        if self._extension_executor is None:
            self._extension_executor = ExtensionToolExecutor(profile=self.profile)
        return self._extension_executor

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
        captured = [TOOL_SPECS[name] for name in sorted(self._active_tools)]
        extensions = [EXTENSION_TOOL_SPECS[name] for name in EXTENSION_TOOL_REGISTRY]
        return captured + extensions

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
        registration = TOOL_REGISTRY.get(name) or EXTENSION_TOOL_REGISTRY.get(name)
        if registration is None:
            return (
                f"Unknown tool '{name}'. It is not registered in this CLI loop; "
                f"registered tools: {', '.join(TOOL_REGISTRY)}; CLI extension "
                f"tools: {', '.join(EXTENSION_TOOL_REGISTRY)}.",
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
        if (
            registration.risk == "write"
            and registration.live
            and not self._gate(name, args)
        ):
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

    def _exec_fail_closed(self, name: str, args: Mapping[str, Any]) -> str:
        note = TOOL_REGISTRY[name].note or "no endpoint contract was captured"
        raise UnverifiedContract(name, note)

    def _exec_extension(self, name: str, args: Mapping[str, Any]) -> str:
        return self._extensions().execute(name, args)

    def _object_type_id_for_rid(self, rid: str) -> str:
        if rid in self._object_type_id_cache:
            return self._object_type_id_cache[rid]
        payload = self._bulk_load_object_type(rid)
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

    def _bulk_load_object_type(self, rid: str) -> Dict[str, Any]:
        """The captured identifier-form bulkLoadEntities object-type load."""
        if rid in self._object_type_load_cache:
            return self._object_type_load_cache[rid]
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
            "load object type",
        )
        self._object_type_load_cache[rid] = payload
        return payload

    def _bulk_load_action_type(self, rid: str) -> Dict[str, Any]:
        """The captured rid-form bulkLoadEntities action-type load."""
        return self._conjure(
            "POST",
            _BULK_LOAD_ENTITIES_PATH,
            {
                "actionTypes": [{"rid": rid}],
                "loadRedacted": True,
                "datasourceTypes": [],
                "objectTypes": [],
                "linkTypes": [],
                "sharedPropertyTypes": [],
                "interfaceTypes": [],
                "typeGroups": [],
            },
            "load action type",
        )

    def _require_null_branch(self, args: Mapping[str, Any], tool: str) -> None:
        if args.get("ontologyBranchRid"):
            raise UnverifiedContract(
                tool,
                "a non-null ontologyBranchRid was never captured for this "
                "tool; only default-branch loads were observed",
            )

    def _exec_load_object_types(self, name: str, args: Mapping[str, Any]) -> str:
        entries = args.get("objectTypes")
        if not isinstance(entries, list) or not entries:
            raise ValueError(
                "load_object_types requires a non-empty 'objectTypes' list"
            )
        loaded: List[Any] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError(f"malformed objectTypes entry: {entry!r}")
            self._require_null_branch(entry, name)
            locator = entry.get("objectTypeLocator")
            if not isinstance(locator, Mapping) or not isinstance(
                locator.get("objectTypeRid"), str
            ):
                raise UnverifiedContract(
                    name,
                    f"only the objectTypeRid locator arm was captured; got {locator!r}",
                )
            loaded.append(self._bulk_load_object_type(locator["objectTypeRid"]))
        return json.dumps({"objectTypes": loaded}, indent=1, default=str)

    def _exec_load_action_types(self, name: str, args: Mapping[str, Any]) -> str:
        entries = args.get("actionTypes")
        if not isinstance(entries, list) or not entries:
            raise ValueError(
                "load_action_types requires a non-empty 'actionTypes' list"
            )
        loaded: List[Any] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError(f"malformed actionTypes entry: {entry!r}")
            self._require_null_branch(entry, name)
            rid = entry.get("actionTypeRid")
            if not isinstance(rid, str) or not rid:
                raise ValueError(f"actionTypes entry has no actionTypeRid: {entry!r}")
            loaded.append(self._bulk_load_action_type(rid))
        return json.dumps({"actionTypes": loaded}, indent=1, default=str)

    def _link_type_main(self, link_type_rid: str) -> Dict[str, Any]:
        """The pinned LinkTypeMainQuery read for one link type RID."""
        result = self._client().graphql(
            "LinkTypeMainQuery",
            LINK_TYPE_MAIN_QUERY,
            {"linkTypeRid": link_type_rid},
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                "load_link_types",
                f"LinkTypeMainQuery failed for {link_type_rid}: "
                f"{result.errors or result.reason or result.status}",
            )
        return dict(result.data)

    def _exec_load_link_types(self, name: str, args: Mapping[str, Any]) -> str:
        entries = args.get("linkTypes")
        if not isinstance(entries, list) or not entries:
            raise ValueError("load_link_types requires a non-empty 'linkTypes' list")
        loaded: List[Any] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError(f"malformed linkTypes entry: {entry!r}")
            self._require_null_branch(entry, name)
            rid = entry.get("linkTypeRid")
            if not isinstance(rid, str) or not rid:
                raise ValueError(f"linkTypes entry has no linkTypeRid: {entry!r}")
            loaded.append(self._link_type_main(rid))
        return json.dumps({"linkTypes": loaded}, indent=1, default=str)

    def _exec_get_link_types_for_object_type(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        self._require_null_branch(args, name)
        object_type_rid = _require_str(args, "objectTypeRid", name)
        result = self._client().graphql(
            "AssociatedLinkTypesForObjectTypeMainQuery",
            ASSOCIATED_LINK_TYPES_QUERY,
            {"objectTypeRid": object_type_rid},
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                name,
                f"AssociatedLinkTypesForObjectTypeMainQuery failed: "
                f"{result.errors or result.reason or result.status}",
            )
        object_type = result.data.get("objectTypeV2")
        latest = object_type.get("latest") if isinstance(object_type, Mapping) else None
        links = (
            latest.get("linksIncludingLinksToObjectTypesWithoutSearchableDatasources")
            if isinstance(latest, Mapping)
            else None
        )
        if not isinstance(links, list):
            raise UnverifiedContract(
                name,
                "AssociatedLinkTypesForObjectTypeMainQuery returned no link "
                f"list: {str(result.data)[:200]!r}",
            )
        rids: List[str] = []
        for link in links:
            node = link.get("linkType") if isinstance(link, Mapping) else None
            inner = node.get("linkType") if isinstance(node, Mapping) else None
            rid = inner.get("rid") if isinstance(inner, Mapping) else None
            if isinstance(rid, str):
                rids.append(rid)
        return json.dumps(
            {
                "objectTypeRid": object_type_rid,
                "linkTypeRids": rids,
                "linkTypes": [self._link_type_main(rid) for rid in rids],
            },
            indent=1,
            default=str,
        )

    def _exec_get_action_types_for_object_type(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        self._require_null_branch(args, name)
        object_type_rid = _require_str(args, "objectTypeRid", name)
        result = self._client().graphql(
            "AssociatedActionTypeRidsMainQuery",
            ASSOCIATED_ACTION_TYPE_RIDS_QUERY,
            {"objectTypeRid": object_type_rid},
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                name,
                f"AssociatedActionTypeRidsMainQuery failed: "
                f"{result.errors or result.reason or result.status}",
            )
        object_type = result.data.get("objectTypeV2")
        latest = object_type.get("latest") if isinstance(object_type, Mapping) else None
        page = (
            latest.get("associatedActionTypesV2")
            if isinstance(latest, Mapping)
            else None
        )
        if not isinstance(page, Mapping) or "reason" in page:
            raise UnverifiedContract(
                name,
                f"AssociatedActionTypeRidsMainQuery returned no action type "
                f"page: {str(result.data)[:200]!r}",
            )
        values = page.get("values")
        rids = [
            str(v.get("actionTypeRid"))
            for v in (values if isinstance(values, list) else [])
            if isinstance(v, Mapping) and v.get("actionTypeRid")
        ]
        output: Dict[str, Any] = {
            "objectTypeRid": object_type_rid,
            "actionTypeRids": rids,
            "actionTypes": [self._bulk_load_action_type(rid) for rid in rids],
        }
        if page.get("nextPageToken"):
            output["_truncated"] = (
                "the association page carried a nextPageToken, but "
                "pagination was never captured; only the first page is "
                "returned"
            )
        return json.dumps(output, indent=1, default=str)

    def _exec_load_object_sets(self, name: str, args: Mapping[str, Any]) -> str:
        self._require_null_branch(args, name)
        rids = args.get("objectSetRids")
        if not isinstance(rids, list) or not rids:
            raise ValueError(
                "load_object_sets requires a non-empty 'objectSetRids' list"
            )
        loaded = []
        for rid in rids:
            if not isinstance(rid, str) or not rid:
                raise ValueError(f"malformed object set RID: {rid!r}")
            loaded.append(
                self._conjure(
                    "GET", _OBJECT_SET_PATH.format(rid=rid), None, "load object set"
                )
            )
        return json.dumps({"objectSets": loaded}, indent=1, default=str)

    def _exec_load_functions(self, name: str, args: Mapping[str, Any]) -> str:
        entries = args.get("functions")
        if not isinstance(entries, list) or not entries:
            raise ValueError("load_functions requires a non-empty 'functions' list")
        loaded: List[Any] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError(f"malformed functions entry: {entry!r}")
            self._require_null_branch(entry, name)
            function_rid = entry.get("functionRid")
            if not isinstance(function_rid, str) or not function_rid:
                raise ValueError(f"functions entry has no functionRid: {entry!r}")
            version = entry.get("version")
            if version is None:
                version = self._latest_function_version(function_rid)
            loaded.append(
                self._conjure(
                    "GET",
                    _FUNCTION_SPECS_PATH.format(rid=function_rid, version=version),
                    None,
                    "load function spec",
                )
            )
        return json.dumps({"functions": loaded}, indent=1, default=str)

    def _exec_load_code_repo(self, name: str, args: Mapping[str, Any]) -> str:
        _require_main_branch(args.get("branch"), name)
        repository_rid = _require_str(args, "repositoryRid", name)
        resolved = self._conjure(
            "GET",
            _STEMMA_RESOLVE_PATH.format(rid=repository_rid),
            None,
            "resolve repository master ref",
        )
        root = self._conjure(
            "GET",
            f"{_STEMMA_CONTENTS_PATH.format(rid=repository_rid, path='%2F')}"
            f"?{_STEMMA_COMMITISH}",
            None,
            "load repository root listing",
        )
        agents_md: Optional[str] = None
        status, payload, _raw = self._client().conjure(
            "GET",
            f"{_STEMMA_CONTENTS_PATH.format(rid=repository_rid, path='AGENTS.md')}"
            f"?{_STEMMA_COMMITISH}",
            json_body=None,
        )
        if 200 <= status < 300 and isinstance(payload, Mapping):
            contents = payload.get("fileContents")
            if isinstance(contents, str):
                agents_md = base64.b64decode(contents).decode("utf-8", "replace")
        return json.dumps(
            {
                "repositoryRid": repository_rid,
                "resolvedRef": resolved,
                "rootContents": root,
                "agentsMd": agents_md,
            },
            indent=1,
            default=str,
        )

    def _exec_load_pull_request(self, name: str, args: Mapping[str, Any]) -> str:
        pull_request_rid = _require_str(args, "pullRequestRid", name)
        payload = self._repository().get_pull_request(pull_request_rid)
        return json.dumps(payload, indent=1, default=str)

    def _container_deployment(self, repository_rid: str, tool: str) -> str:
        """Resolve repository -> container -> running deployment (captured chain)."""
        if repository_rid in self._container_deployment_cache:
            return self._container_deployment_cache[repository_rid]
        result = self._client().graphql(
            "GetContainersForRepository",
            GET_CONTAINERS_FOR_REPOSITORY_QUERY,
            {"repositoryRid": repository_rid},
        )
        if (
            result.errors
            or result.status != "ok"
            or not isinstance(result.data, Mapping)
        ):
            raise UnverifiedContract(
                tool,
                f"GetContainersForRepository failed: "
                f"{result.errors or result.reason or result.status}",
            )
        repository = result.data.get("stemmaRepository")
        containers = (
            repository.get("containers") if isinstance(repository, Mapping) else None
        )
        container_rid: Optional[str] = None
        for container in containers if isinstance(containers, list) else []:
            if not isinstance(container, Mapping):
                continue
            metadata = container.get("metadata")
            trashed = (
                metadata.get("trashedStatus") if isinstance(metadata, Mapping) else None
            )
            if container.get("imageType") == "CODE" and trashed == "NOT_TRASHED":
                rid = container.get("rid")
                if isinstance(rid, str):
                    container_rid = rid
                    break
        if container_rid is None:
            raise UnverifiedContract(
                tool,
                "GetContainersForRepository returned no non-trashed CODE "
                f"container for {repository_rid}: {str(result.data)[:200]!r}",
            )
        created = self._conjure(
            "POST",
            _CONTAINER_DEPLOYMENTS_PATH.format(container_rid=container_rid),
            None,
            "create container deployment",
        )
        deployment_rid = created.get("deploymentRid")
        if not isinstance(deployment_rid, str) or not deployment_rid:
            raise UnverifiedContract(
                tool,
                f"container deployment creation returned no deploymentRid: "
                f"{str(created)[:200]!r}",
            )
        deadline = time.monotonic() + self._container_boot_timeout
        while True:
            status_payload = self._conjure(
                "GET",
                _DEPLOYMENT_STATUS_PATH.format(deployment_rid=deployment_rid),
                None,
                "poll container deployment status",
            )
            status = status_payload.get("status")
            state = status.get("type") if isinstance(status, Mapping) else None
            if state == "running":
                break
            if state not in {"starting", "initializing", "launching"}:
                raise UnverifiedContract(
                    tool,
                    f"container deployment reached uncaptured state "
                    f"{state!r}: {str(status_payload)[:200]!r}",
                )
            if time.monotonic() >= deadline:
                raise FoundryApiError(
                    f"container deployment {deployment_rid} did not reach "
                    f"'running' within {self._container_boot_timeout:.0f}s",
                )
            time.sleep(self._container_poll_interval)
        self._container_deployment_cache[repository_rid] = deployment_rid
        return deployment_rid

    def _exec_container_git_status(self, name: str, args: Mapping[str, Any]) -> str:
        repository_rid = _require_str(args, "repositoryRid", name)
        deployment_rid = self._container_deployment(repository_rid, name)
        payload = self._conjure(
            "GET",
            _DEPLOYMENT_GIT_STATUS_PATH.format(deployment_rid=deployment_rid),
            None,
            "load container git status",
        )
        return json.dumps(payload, indent=1, default=str)

    def _exec_container_execute_terminal_command(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        repository_rid = _require_str(args, "repositoryRid", name)
        command = _require_str(args, "command", name)
        deployment_rid = self._container_deployment(repository_rid, name)
        body: Dict[str, Any] = {"command": command}
        directory = args.get("directory")
        if isinstance(directory, str) and directory:
            body["directory"] = directory
        result = self._conjure(
            "POST",
            _DEPLOYMENT_EXECUTE_COMMAND_PATH.format(deployment_rid=deployment_rid),
            body,
            "execute terminal command",
        )
        exit_code = result.get("exitCode")
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        return (
            f"Terminal command executed: {command} with exit code {exit_code}\n\n"
            f"stdout:\n```console\n{stdout}\n```\n\n"
            f"stderr:\n```console\n{stderr}\n```"
        )

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

    def _exec_get_evaluation_suites_for_target(
        self, name: str, args: Mapping[str, Any]
    ) -> str:
        _require_main_branch(args.get("branch"), name)
        target = args.get("target")
        if (
            not isinstance(target, Mapping)
            or target.get("type") != "function"
            or not isinstance(target.get("rid"), str)
        ):
            raise UnverifiedContract(
                name,
                f"only the function target arm was captured; got {target!r}",
            )
        function_rid = target["rid"]
        rids = self._evals().list_evaluation_suites_for_target(function_rid)
        suites = {
            rid: self._evals().get_evaluation_suite_config_v2(rid) for rid in rids
        }
        return json.dumps(
            {"evaluationSuiteRids": rids, "evaluationSuites": suites},
            indent=1,
            default=str,
        )

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
            answer = (
                "The operator cannot answer clarification questions in this "
                "run (non-interactive). Make reasonable assumptions, document "
                "them in your response, and proceed without asking again."
            )
        else:
            answer = self._clarification_handler(questions)
        if self._consecutive_clarifications >= 2:
            answer += (
                "\n\n<cliDirective>\nYou have asked for clarification "
                f"{self._consecutive_clarifications} times in a row without "
                "making progress. STOP asking: make reasonable assumptions, "
                "state them explicitly, and answer best-effort with the "
                "information you already have. Further clarification "
                "requests without intermediate tool use will not be "
                f"answered. You have {self._turns_remaining} turn(s) "
                "remaining in this run.\n</cliDirective>"
            )
        return answer

    def _exec_change_mode(self, name: str, args: Mapping[str, Any]) -> str:
        mode_config = args.get("modeConfig")
        if not isinstance(mode_config, Mapping):
            raise ValueError("change_mode requires a 'modeConfig' object")
        mode_type = str(mode_config.get("type"))
        self._mode = mode_type
        payload = (
            f"<modeChange>{json.dumps(mode_config, separators=(',', ':'))}</modeChange>"
        )
        tool_set = MODE_TOOL_SETS.get(mode_type)
        if tool_set is not None:
            self._active_tools = set(tool_set)
            payload += (
                f"\nMode '{mode_type}' is now active; the next request "
                f"exposes the captured {len(tool_set)}-tool set for this mode."
            )
        else:
            payload += (
                f"\nThe tool set for mode '{mode_type}' was never captured, "
                "so the CLI loop keeps the current tool set. Known modes: "
                "functionsEditing (51 tools). To expose the full captured "
                "catalog regardless of mode, restart with --all-tools."
            )
        return payload

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
                self._turns_remaining = max_turns - turns
                if tool_name == "request_clarification_from_user":
                    self._consecutive_clarifications += 1
                    if self._consecutive_clarifications >= 2:
                        self._progress(
                            "clarification loop guard: injecting best-effort directive"
                        )
                else:
                    self._consecutive_clarifications = 0
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
    "ALL_TOOL_NAMES",
    "ASSOCIATED_ACTION_TYPE_RIDS_QUERY",
    "ASSOCIATED_LINK_TYPES_QUERY",
    "AgentLoop",
    "BASE_TOOL_NAMES",
    "CAPABILITY_TOOL_MAP",
    "CONTEXT_TOKEN_THRESHOLD",
    "CompletedResponse",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_MODEL",
    "DEFAULT_TOOL_NAMES",
    "EXTENSION_TOOL_REGISTRY",
    "GET_CONTAINERS_FOR_REPOSITORY_QUERY",
    "LATEST_FUNCTION_VERSION_QUERY",
    "LINK_TYPE_MAIN_QUERY",
    "LlmResponseShapeError",
    "LlmSession",
    "MODE_TOOL_SETS",
    "TOOL_REGISTRY",
    "ToolRegistration",
    "UNCAPTURED_MODE_TYPES",
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
