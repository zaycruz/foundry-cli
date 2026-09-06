"""
AI FDE thread and settings service wrapper.

Backed by the internal ``ai-fde`` Conjure service (base ``/ai-fde/api``) and
the GraphQL bulk gateway. All contracts below were captured from the live AI
FDE UI on a live Foundry deployment via Chrome DevTools Protocol on
2026-09-04; every listed call returned HTTP 200. Capture artifact:
/tmp/evals-capture/capture.jsonl (digest:
/tmp/evals-capture/contracts-digest.md). This is "UI capture, live-exercised"
evidence per ``tickets/README.md``.

Key architectural finding: **the AI FDE agent loop runs client-side**. The
browser calls the LLM directly
(``language-model-service/api/llm/v3/completion/GPT_5_6_SOL/
streamCompletionChunk``, OpenAI-Responses-shaped body with
instructions/input/tools, sessionId == threadId), executes returned tool
calls itself (e.g. ``POST /actions/api/actionsV2``), and writes results into
the thread. This service implements the THREAD PRIMITIVES (list/read/create
threads, append context items, agent-state metadata, settings), NOT the
agent loop — there is no server-side "run the agent" endpoint to wrap.
Remaining gaps (agent loop, stop/cancel, reject-change, thread
delete/rename) are tracked in ``tickets/TICKET-009-ai-fde.md``.

Thread IDs are plain UUIDs, not RIDs.

Conjure contracts (all captured with HTTP 200):

- ``GET /ai-fde/api/settings`` (no body) returns
  ``{attributionSettings, skillEnablementSettings, bulkToolApprovalSettings,
  modelSelectionSettings}``.
- ``POST /ai-fde/api/settings`` takes a settings MODIFICATION document; the
  captured body wraps each section in a union, e.g.
  ``{"attributionSettings": {"type": "unchanged", "unchanged": {}},
  "skillEnablementSettings": {"type": "modification", "modification":
  {"skillConfigs": {<skillRid>: {"type": "standard", "standard": {"enabled":
  true}}, ...}}}}`` and returns ``{}``. The CLI sends a caller-supplied body
  verbatim; only the ``skillEnablementSettings`` modification arm was
  observed, so other sections are not synthesized.
- ``PUT /ai-fde/api/threads/{threadId}/metadata`` body ``{currentVersion,
  agentStateModification}`` sets the agent state (system prompt, tool
  configurations, mode config, model configuration). The captured
  ``agentStateModification`` is a full agent-state document
  (``agentSystemPrompt``, ``toolConfigurations``, ``modeConfig``,
  ``modelConfiguration``, ``todoItems``, ``sessionState``); the CLI sends a
  caller-supplied modification verbatim. Response: ``{"metadata": {...}}``
  with the new ``threadVersion``.
- ``PUT /ai-fde/api/threads/{threadId}/update`` is the thread document sync:
  body ``{currentVersion, itemIdsInOrder, itemsToWrite}``. Items are typed
  context items (``user-message``, ``assistant-message``, ``tool-usage``,
  ``executedAction``, ``evaluationRun``, ``evaluationSuite``, ...) shaped
  ``{contextItemId, typeAndVersion: {contextItemType, contextItemVersion:
  0}, content: [<typed content object>], fallbackMessages,
  childContextItemsOrder, fallbackMessage}``. Response: ``{"metadata":
  {...}}`` with the new ``threadVersion``.

GraphQL operations (documents pinned verbatim below, all captured with
HTTP 200):

- ``AvailableThreadsQuery`` — list threads (``aiFdeThreadsV2``).
- ``ThreadMetadataQuery`` — one thread's metadata
  (``aiFdeThreadV2.metadataV3``, full or redacted).
- ``ThreadContextItemsPageQuery`` — paged thread items
  (``aiFdeThreadV2.contextItemsV2.contextItems``).
- ``CreateThreadMutation`` — thread creation. This is a GraphQL MUTATION and
  runs through the scoped exception in
  ``foundry_internal_client.VERIFIED_GRAPHQL_MUTATION_NAMES``: the client's
  general mutation ban stays in force, and only this captured, named
  operation can pass, and only when the caller opts in via
  ``allow_mutation_names``. Variables captured: ``{"threadName": "New
  session"}`` with ``contextItems: []`` hardcoded in the document; whether
  non-empty ``contextItems`` are accepted at creation time is unknown and
  not guessed.

``send_user_message`` derives the ``user-message`` item from the captured
``itemsToWrite`` sample verbatim (``content`` entry ``{"id", "type":
"user-message", "prompt", "createdAt"}`` with ``createdAt`` in millisecond
ISO-8601; ``fallbackMessages`` ``[{"role": "USER", "contents": [{"type":
"text", "text": <prompt>}]}]``; ``fallbackMessage`` ``{"role": "USER",
"contents": []}``). The delta update was partially-derived at capture time
(only a full-thread write was observed) and has since been contract-verified:
on
2026-09-05 against a second live deployment (zap.usw-18) a minimal delta
(``itemIdsInOrder`` = existing order + new id, ``itemsToWrite`` = just the
new item) was accepted with HTTP 200, the server-assigned ``contextItemId``
was returned, and a GraphQL read-back showed the ``user-message`` item
exactly as sent.

Responses are passed through as parsed JSON with strict shape-checking:
anything that is not the expected JSON shape fails loudly instead of
rendering as a result. Non-2xx Conjure statuses raise typed errors via
``foundry_error_from_conjure``; GraphQL errors raise ``AiFdeGraphQLError``.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

from .base import BaseService
from .errors import foundry_error_from_conjure
from .foundry_internal_client import (
    VERIFIED_GRAPHQL_MUTATION_NAMES,
    FoundryInternalClient,
)

_AI_FDE_API = "ai-fde/api"

AVAILABLE_THREADS_QUERY = """query AvailableThreadsQuery($pageSize: Int!) {
  aiFdeThreadsV2(pageSize: $pageSize) {
    ...ThreadOptionFragment
    __typename
  }
  __typename
}

fragment ThreadOptionFragment on AiFdeThreadMetadataV2 {
  ... on AiFdeFullThreadMetadata {
    ...FullThreadOptionFragment
    _id
    __typename
  }
  ... on AiFdeRedactedThreadMetadata {
    ...RedactedThreadOptionFragment
    _id
    __typename
  }
  __typename
}

fragment FullThreadOptionFragment on AiFdeFullThreadMetadata {
  id
  name
  createdAt
  lastUpdatedAt
  _id
  __typename
}

fragment RedactedThreadOptionFragment on AiFdeRedactedThreadMetadata {
  id
  createdAt
  lastUpdatedAt
  _id
  __typename
}"""

THREAD_METADATA_QUERY = """query ThreadMetadataQuery($threadId: String!) {
  aiFdeThreadV2(id: $threadId) {
    metadataV3 {
      ... on AiFdeFullThreadMetadata {
        ...ThreadMetadataFragment
        _id
        __typename
      }
      ... on AiFdeRedactedThreadMetadata {
        ...RedactedThreadMetadataFragment
        _id
        __typename
      }
      __typename
    }
    __typename
  }
  __typename
}

fragment ThreadMetadataFragment on AiFdeFullThreadMetadata {
  id
  name
  createdAt
  lastUpdatedAt
  version
  agentState
  contextItemsOrder
  _id
  __typename
}

fragment RedactedThreadMetadataFragment on AiFdeRedactedThreadMetadata {
  id
  createdAt
  lastUpdatedAt
  _id
  __typename
}"""

THREAD_CONTEXT_ITEMS_PAGE_QUERY = """query ThreadContextItemsPageQuery($threadId: String!, $pageToken: PageToken, $pageSize: Int!) {
  aiFdeThreadV2(id: $threadId) {
    contextItemsV2(pageSize: $pageSize, pageToken: $pageToken) {
      contextItems {
        ...ContextItemFragment
        _id
        __typename
      }
      nextPageToken
      __typename
    }
    __typename
  }
  __typename
}

fragment ContextItemFragment on AiFdeFrontendContextItem {
  id
  content
  contextItemType
  contextItemVersion
  childContextItemsOrder
  fallbackMessages {
    ... on AiFdeMessage {
      ...AiFdeMessageFragment
      __typename
    }
    __typename
  }
  _id
  __typename
}

fragment AiFdeMessageFragment on AiFdeMessage {
  role
  contents {
    ... on AiFdeMessageContent {
      ...AiFdeMessageContentFragment
      __typename
    }
    __typename
  }
  __typename
}

fragment AiFdeMessageContentFragment on AiFdeMessageContent {
  ...AiFdeDocumentMessageFragment
  ...AiFdeImageMessageFragment
  ...AiFdeTextMessageFragment
  ...AiFdeThinkingMessageFragment
  ...AiFdeToolResponseMessageFragment
  ... on AiFdeToolUsageMessage {
    toolUseId
    toolInput
    toolName
    __typename
  }
  __typename
}

fragment AiFdeDocumentMessageFragment on AiFdeDocumentMessage {
  title
  source {
    ... on AiFdeDocumentSourceBase64 {
      data
      mediaType
      fileName
      __typename
    }
    ... on AiFdeMediaItemReference {
      mediaItemRid
      mediaSetRid
      __typename
    }
    __typename
  }
  __typename
}

fragment AiFdeImageMessageFragment on AiFdeImageMessage {
  image {
    ... on AiFdeImageMessageContentBase64 {
      data
      mediaType
      __typename
    }
    ... on AiFdeMediaItemReference {
      mediaItemRid
      mediaSetRid
      __typename
    }
    __typename
  }
  __typename
}

fragment AiFdeTextMessageFragment on AiFdeTextMessage {
  text
  __typename
}

fragment AiFdeThinkingMessageFragment on AiFdeThinkingMessage {
  modelSpecifiedThinking {
    ... on AiFdeClaudeThinking {
      signature
      thinking
      __typename
    }
    ... on AiFdeGeminiThinking {
      thought
      thoughtSignature
      __typename
    }
    ... on AiFdeOpenAiThinking {
      content
      encryptedContent
      reasoningId
      summary
      __typename
    }
    __typename
  }
  __typename
}

fragment AiFdeToolResponseMessageFragment on AiFdeToolResponseMessage {
  toolUseId
  toolResponse {
    ... on AiFdeToolResponseError {
      error {
        ...AiFdeDocumentMessageFragment
        ...AiFdeTextMessageFragment
        ...AiFdeImageMessageFragment
        __typename
      }
      __typename
    }
    ... on AiFdeToolResponseSuccess {
      content {
        ...AiFdeDocumentMessageFragment
        ...AiFdeTextMessageFragment
        ...AiFdeImageMessageFragment
        __typename
      }
      __typename
    }
    __typename
  }
  __typename
}"""

CREATE_THREAD_MUTATION = """mutation CreateThreadMutation($threadName: String!) {
  createAiFdeThread(threadName: $threadName, contextItems: []) {
    id
    version
    _id
    __typename
  }
  __typename
}"""

CREATE_THREAD_MUTATION_NAME = "CreateThreadMutation"

if CREATE_THREAD_MUTATION_NAME not in VERIFIED_GRAPHQL_MUTATION_NAMES:
    raise RuntimeError(
        "CreateThreadMutation is not registered in "
        "foundry_internal_client.VERIFIED_GRAPHQL_MUTATION_NAMES; the "
        "scoped GraphQL mutation exception requires registry membership"
    )


class AiFdeShapeError(RuntimeError):
    """Raised when an ai-fde response is not the expected JSON shape."""


class AiFdeGraphQLError(RuntimeError):
    """Raised when an ai-fde GraphQL operation errors or is inconclusive."""


def _utc_now_millis() -> str:
    """Format the current UTC time like the captured UI (millisecond ISO-8601)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class AiFdeService(BaseService):
    """Service wrapper for AI FDE threads, agent state, and settings."""

    def _get_service(self) -> Any:
        """Get the Foundry client (ai-fde calls use the internal API)."""
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

    def _conjure(
        self, verb: str, path: str, body: Optional[Mapping[str, Any]], context: str
    ) -> Dict[str, Any]:
        """Issue one ai-fde Conjure call and return the parsed JSON object.

        Non-2xx statuses raise a typed FoundryApiError; a success payload
        that is not a JSON object fails loudly rather than guessing.
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(verb, path, json_body=body)
        except Exception as e:
            raise RuntimeError(f"Failed to {context}: {self._describe_error(e)}") from e

        if not 200 <= status < 300:
            raise foundry_error_from_conjure(status, payload, raw, context=context)
        if not isinstance(payload, Mapping):
            raise AiFdeShapeError(
                f"Unverified ai-fde {context} response shape: expected a "
                f"JSON object, got {str(raw)[:200]!r}. Refusing to guess at "
                "the contract."
            )
        return dict(payload)

    def _graphql(
        self,
        name: str,
        query: str,
        variables: Mapping[str, Any],
        context: str,
        *,
        allow_mutation_names: Optional[Iterable[str]] = None,
    ) -> Mapping[str, Any]:
        """Run one pinned GraphQL operation and return its data mapping."""
        client = self._internal_client()
        result = client.graphql(
            name,
            query,
            variables,
            allow_mutation_names=allow_mutation_names,
        )
        if result.errors:
            raise AiFdeGraphQLError(
                f"ai-fde GraphQL {context} returned errors: {result.errors!r}"
            )
        if result.status != "ok":
            raise AiFdeGraphQLError(
                f"ai-fde GraphQL {context} was inconclusive: "
                f"{result.reason or result.status}"
            )
        if not isinstance(result.data, Mapping):
            raise AiFdeShapeError(
                f"Unverified ai-fde GraphQL {context} response shape: "
                f"expected a data object, got {result.data!r}."
            )
        return result.data

    # --- GraphQL thread reads ------------------------------------------

    def list_threads(self, page_size: int = 50) -> List[Dict[str, Any]]:
        """List available AI FDE threads (AvailableThreadsQuery).

        Returns the raw ``aiFdeThreadsV2`` entries (full or redacted thread
        metadata); both variants were captured.
        """
        data = self._graphql(
            "AvailableThreadsQuery",
            AVAILABLE_THREADS_QUERY,
            {"pageSize": page_size},
            "list threads",
        )
        threads = data.get("aiFdeThreadsV2")
        if not isinstance(threads, list):
            raise AiFdeShapeError(
                "Unverified ai-fde thread list response shape: expected "
                f"'aiFdeThreadsV2' to be a list, got {data!r}."
            )
        return [dict(t) for t in threads if isinstance(t, Mapping)]

    def get_thread_metadata(self, thread_id: str) -> Dict[str, Any]:
        """Load one thread's metadata (ThreadMetadataQuery).

        Returns the ``metadataV3`` mapping — ``AiFdeFullThreadMetadata``
        (id, name, version, agentState, contextItemsOrder) or
        ``AiFdeRedactedThreadMetadata``; both variants were captured.
        """
        data = self._graphql(
            "ThreadMetadataQuery",
            THREAD_METADATA_QUERY,
            {"threadId": thread_id},
            "load thread metadata",
        )
        thread = data.get("aiFdeThreadV2")
        metadata = thread.get("metadataV3") if isinstance(thread, Mapping) else None
        if not isinstance(metadata, Mapping):
            raise AiFdeShapeError(
                "Unverified ai-fde thread metadata response shape: expected "
                f"'aiFdeThreadV2.metadataV3' to be an object, got {data!r}."
            )
        return dict(metadata)

    def get_thread_items(
        self,
        thread_id: str,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load one page of thread context items (ThreadContextItemsPageQuery).

        Returns ``{"contextItems": [...], "nextPageToken": ...}``.
        """
        variables: Dict[str, Any] = {"threadId": thread_id, "pageSize": page_size}
        if page_token is not None:
            variables["pageToken"] = page_token
        data = self._graphql(
            "ThreadContextItemsPageQuery",
            THREAD_CONTEXT_ITEMS_PAGE_QUERY,
            variables,
            "load thread context items",
        )
        thread = data.get("aiFdeThreadV2")
        page = thread.get("contextItemsV2") if isinstance(thread, Mapping) else None
        items = page.get("contextItems") if isinstance(page, Mapping) else None
        if not isinstance(items, list):
            raise AiFdeShapeError(
                "Unverified ai-fde thread items response shape: expected "
                "'aiFdeThreadV2.contextItemsV2.contextItems' to be a list, "
                f"got {data!r}."
            )
        return {
            "contextItems": [dict(i) for i in items if isinstance(i, Mapping)],
            "nextPageToken": page.get("nextPageToken"),
        }

    # --- Thread creation (scoped GraphQL mutation) ----------------------

    def create_thread(self, thread_name: str) -> Dict[str, Any]:
        """Create one AI FDE thread (CreateThreadMutation).

        The captured document hardcodes ``contextItems: []`` and takes only
        ``threadName``; the response is ``{id, version}``. Runs through the
        client's scoped mutation exception (registry + per-call opt-in).
        """
        data = self._graphql(
            CREATE_THREAD_MUTATION_NAME,
            CREATE_THREAD_MUTATION,
            {"threadName": thread_name},
            "create thread",
            allow_mutation_names={CREATE_THREAD_MUTATION_NAME},
        )
        created = data.get("createAiFdeThread")
        if not isinstance(created, Mapping) or not created.get("id"):
            raise AiFdeShapeError(
                "Unverified ai-fde create thread response shape: expected "
                f"'createAiFdeThread' with an id, got {data!r}."
            )
        return dict(created)

    # --- Settings --------------------------------------------------------

    def get_settings(self) -> Dict[str, Any]:
        """Load the caller's AI FDE settings (GET /ai-fde/api/settings)."""
        return self._conjure("GET", f"{_AI_FDE_API}/settings", None, "load settings")

    def update_settings(
        self, settings_modification: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Update AI FDE settings (POST /ai-fde/api/settings).

        The body is a settings modification document sent verbatim (the
        captured shape wraps each section in an unchanged/modification
        union); the success response is ``{}``.
        """
        return self._conjure(
            "POST",
            f"{_AI_FDE_API}/settings",
            dict(settings_modification),
            "update settings",
        )

    # --- Thread agent state / metadata -----------------------------------

    def get_thread_agent_state(self, thread_id: str) -> Dict[str, Any]:
        """Load one thread's agent state (from ThreadMetadataQuery)."""
        metadata = self.get_thread_metadata(thread_id)
        agent_state = metadata.get("agentState")
        if not isinstance(agent_state, Mapping):
            raise AiFdeShapeError(
                "Unverified ai-fde thread metadata shape: expected "
                f"'agentState' to be an object, got {metadata!r}. The thread "
                "may be redacted (AiFdeRedactedThreadMetadata carries no "
                "agent state)."
            )
        return dict(agent_state)

    def update_thread_metadata(
        self,
        thread_id: str,
        current_version: str,
        agent_state_modification: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Set a thread's agent state (PUT /threads/{threadId}/metadata).

        ``current_version`` is the threadVersion this modification applies
        to (optimistic concurrency); ``agent_state_modification`` is sent
        verbatim. Response: ``{"metadata": {...}}`` with the new
        ``threadVersion``.
        """
        return self._conjure(
            "PUT",
            f"{_AI_FDE_API}/threads/{thread_id}/metadata",
            {
                "currentVersion": current_version,
                "agentStateModification": dict(agent_state_modification),
            },
            "update thread metadata",
        )

    # --- Thread document sync --------------------------------------------

    def update_thread_items(
        self,
        thread_id: str,
        current_version: str,
        item_ids_in_order: List[str],
        items_to_write: List[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Sync thread context items (PUT /threads/{threadId}/update).

        ``item_ids_in_order`` is the full item order;
        ``items_to_write`` carries the typed context items to persist.
        Response: ``{"metadata": {...}}`` with the new ``threadVersion``.
        """
        return self._conjure(
            "PUT",
            f"{_AI_FDE_API}/threads/{thread_id}/update",
            {
                "currentVersion": current_version,
                "itemIdsInOrder": list(item_ids_in_order),
                "itemsToWrite": [dict(i) for i in items_to_write],
            },
            "update thread items",
        )

    @staticmethod
    def build_user_message_item(
        text: str, context_item_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a captured-shape ``user-message`` context item.

        The shape matches the captured ``itemsToWrite`` sample verbatim:
        ``content`` entry ``{"id", "type": "user-message", "prompt",
        "createdAt"}``, ``fallbackMessages`` with a USER text message, empty
        ``childContextItemsOrder``, and an empty USER ``fallbackMessage``.
        """
        item_id = context_item_id or str(uuid4())
        return {
            "contextItemId": item_id,
            "typeAndVersion": {
                "contextItemType": "user-message",
                "contextItemVersion": 0,
            },
            "content": [
                {
                    "id": item_id,
                    "type": "user-message",
                    "prompt": text,
                    "createdAt": _utc_now_millis(),
                }
            ],
            "fallbackMessages": [
                {
                    "role": "USER",
                    "contents": [{"text": text, "type": "text"}],
                }
            ],
            "childContextItemsOrder": [],
            "fallbackMessage": {"role": "USER", "contents": []},
        }

    def send_user_message(self, thread_id: str, text: str) -> Dict[str, Any]:
        """Append a user message to a thread (queue it for the agent).

        Fetches the current thread metadata (version + item order), appends
        one captured-shape ``user-message`` item, and PUTs the update.
        Returns ``{"contextItemId", "threadVersion", "metadata"}`` where
        ``threadVersion`` is the new version from the update response.

        The minimal-delta ``itemsToWrite`` behavior is contract-verified
        (2026-09-05, second live deployment; see the module docstring).
        """
        metadata = self.get_thread_metadata(thread_id)
        current_version = metadata.get("version")
        if not isinstance(current_version, str) or not current_version:
            raise AiFdeShapeError(
                "Cannot send a user message: thread metadata has no "
                f"'version' (got {metadata!r}). The thread may be redacted."
            )
        order = metadata.get("contextItemsOrder")
        if not isinstance(order, list):
            raise AiFdeShapeError(
                "Cannot send a user message: thread metadata has no "
                f"'contextItemsOrder' list (got {metadata!r})."
            )
        item = self.build_user_message_item(text)
        response = self.update_thread_items(
            thread_id,
            current_version,
            [*(str(i) for i in order), item["contextItemId"]],
            [item],
        )
        updated_metadata = response.get("metadata")
        thread_version = (
            updated_metadata.get("threadVersion")
            if isinstance(updated_metadata, Mapping)
            else None
        )
        if not isinstance(thread_version, str) or not thread_version:
            raise AiFdeShapeError(
                "Unverified ai-fde update response shape: expected "
                f"'metadata.threadVersion', got {response!r}."
            )
        return {
            "contextItemId": item["contextItemId"],
            "threadVersion": thread_version,
            "metadata": dict(updated_metadata),
        }
