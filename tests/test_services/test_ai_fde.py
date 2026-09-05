"""
Tests for the AI FDE (ai-fde) service.
"""

import pytest
from unittest.mock import Mock, patch

from foundry_cli.services.ai_fde import (
    CREATE_THREAD_MUTATION,
    CREATE_THREAD_MUTATION_NAME,
    AiFdeGraphQLError,
    AiFdeService,
    AiFdeShapeError,
)
from foundry_cli.services.errors import FoundryApiError
from foundry_cli.services.foundry_internal_client import (
    FoundryInternalClient,
    GraphQLResult,
)

THREAD_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "8041e2bb-45d0-4ec2-bf71-530f77fa8ffa"
NEW_VERSION = "75e108de-3cd8-484b-a970-821953b8d221"
EXISTING_ITEM_ID = "621553cb-3ad0-4139-a064-306354687bdc"

FULL_METADATA = {
    "id": THREAD_ID,
    "name": "New session",
    "createdAt": "2026-09-04T17:54:11.255329462Z",
    "lastUpdatedAt": "2026-09-04T17:54:11.255329462Z",
    "version": VERSION,
    "agentState": {"agentSystemPrompt": ""},
    "contextItemsOrder": [EXISTING_ITEM_ID],
    "__typename": "AiFdeFullThreadMetadata",
}


def _service_with_mock(mock_client_class, payload, status=200, raw="{...}"):
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    mock_client.conjure.return_value = (status, payload, raw)
    return AiFdeService(profile="test"), mock_client


def _service_with_graphql(mock_client_class, result):
    mock_client = Mock()
    mock_client_class.return_value = mock_client
    mock_client.graphql.return_value = result
    return AiFdeService(profile="test"), mock_client


class TestAiFdeThreadReads:
    """Pinned GraphQL read contracts."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_list_threads(self, mock_client_class):
        threads = [{"id": THREAD_ID, "name": "New session"}]
        service, mock_client = _service_with_graphql(
            mock_client_class, GraphQLResult(data={"aiFdeThreadsV2": threads})
        )

        result = service.list_threads(page_size=50)

        assert result == threads
        mock_client_class.assert_called_once_with("test")
        name, query, variables = mock_client.graphql.call_args.args[:3]
        assert name == "AvailableThreadsQuery"
        assert "query AvailableThreadsQuery" in query
        assert variables == {"pageSize": 50}
        assert mock_client.graphql.call_args.kwargs["allow_mutation_names"] is None

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_list_threads_bad_shape(self, mock_client_class):
        service, _ = _service_with_graphql(
            mock_client_class, GraphQLResult(data={"unexpected": []})
        )

        with pytest.raises(AiFdeShapeError, match="aiFdeThreadsV2"):
            service.list_threads()

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_thread_metadata(self, mock_client_class):
        service, mock_client = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"metadataV3": FULL_METADATA}}),
        )

        result = service.get_thread_metadata(THREAD_ID)

        assert result == FULL_METADATA
        name, query, variables = mock_client.graphql.call_args.args[:3]
        assert name == "ThreadMetadataQuery"
        assert variables == {"threadId": THREAD_ID}

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_thread_items(self, mock_client_class):
        item = {"id": EXISTING_ITEM_ID, "contextItemType": "evaluationRun"}
        page = {"contextItems": [item], "nextPageToken": "tok-1"}
        service, mock_client = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"contextItemsV2": page}}),
        )

        result = service.get_thread_items(THREAD_ID, page_size=50, page_token="tok-0")

        assert result == page
        name, query, variables = mock_client.graphql.call_args.args[:3]
        assert name == "ThreadContextItemsPageQuery"
        assert variables == {
            "threadId": THREAD_ID,
            "pageSize": 50,
            "pageToken": "tok-0",
        }

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_thread_items_omits_page_token_when_unset(self, mock_client_class):
        page = {"contextItems": [], "nextPageToken": None}
        service, mock_client = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"contextItemsV2": page}}),
        )

        service.get_thread_items(THREAD_ID)

        variables = mock_client.graphql.call_args.args[2]
        assert "pageToken" not in variables

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_graphql_errors_raise(self, mock_client_class):
        service, _ = _service_with_graphql(
            mock_client_class,
            GraphQLResult(errors=[{"message": "boom"}], status="ok"),
        )

        with pytest.raises(AiFdeGraphQLError, match="errors"):
            service.get_thread_metadata(THREAD_ID)

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_graphql_inconclusive_raises(self, mock_client_class):
        service, _ = _service_with_graphql(
            mock_client_class,
            GraphQLResult(status="inconclusive", reason="missing-response-frame"),
        )

        with pytest.raises(AiFdeGraphQLError, match="inconclusive"):
            service.list_threads()


class TestAiFdeCreateThread:
    """The captured CreateThreadMutation runs via the scoped exception."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_create_thread(self, mock_client_class):
        created = {"id": THREAD_ID, "version": VERSION}
        service, mock_client = _service_with_graphql(
            mock_client_class, GraphQLResult(data={"createAiFdeThread": created})
        )

        result = service.create_thread("New session")

        assert result == created
        name, query, variables = mock_client.graphql.call_args.args[:3]
        assert name == CREATE_THREAD_MUTATION_NAME
        assert query == CREATE_THREAD_MUTATION
        assert query.lstrip().startswith("mutation CreateThreadMutation")
        assert variables == {"threadName": "New session"}
        assert mock_client.graphql.call_args.kwargs["allow_mutation_names"] == {
            CREATE_THREAD_MUTATION_NAME
        }

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_create_thread_bad_shape(self, mock_client_class):
        service, _ = _service_with_graphql(
            mock_client_class, GraphQLResult(data={"createAiFdeThread": {}})
        )

        with pytest.raises(AiFdeShapeError, match="createAiFdeThread"):
            service.create_thread("New session")


class TestAiFdeSettings:
    """Settings read and verbatim-body update."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_settings(self, mock_client_class):
        settings = {"attributionSettings": {}, "skillEnablementSettings": {}}
        service, mock_client = _service_with_mock(mock_client_class, settings)

        result = service.get_settings()

        assert result == settings
        mock_client.conjure.assert_called_once_with(
            "GET", "ai-fde/api/settings", json_body=None
        )

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_update_settings_sends_body_verbatim(self, mock_client_class):
        body = {
            "attributionSettings": {"type": "unchanged", "unchanged": {}},
            "skillEnablementSettings": {"type": "modification", "modification": {}},
        }
        service, mock_client = _service_with_mock(mock_client_class, {})

        result = service.update_settings(body)

        assert result == {}
        mock_client.conjure.assert_called_once_with(
            "POST", "ai-fde/api/settings", json_body=body
        )


class TestAiFdeThreadMetadata:
    """Agent state read and metadata write."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_thread_agent_state(self, mock_client_class):
        service, _ = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"metadataV3": FULL_METADATA}}),
        )

        result = service.get_thread_agent_state(THREAD_ID)

        assert result == {"agentSystemPrompt": ""}

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_get_thread_agent_state_redacted_fails_loudly(self, mock_client_class):
        redacted = {
            "id": THREAD_ID,
            "createdAt": "2026-09-04T17:54:11.255329462Z",
            "__typename": "AiFdeRedactedThreadMetadata",
        }
        service, _ = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"metadataV3": redacted}}),
        )

        with pytest.raises(AiFdeShapeError, match="agentState"):
            service.get_thread_agent_state(THREAD_ID)

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_update_thread_metadata(self, mock_client_class):
        modification = {"agentSystemPrompt": "", "toolConfigurations": {}}
        response = {"metadata": {"threadId": THREAD_ID, "threadVersion": NEW_VERSION}}
        service, mock_client = _service_with_mock(mock_client_class, response)

        result = service.update_thread_metadata(THREAD_ID, VERSION, modification)

        assert result == response
        mock_client.conjure.assert_called_once_with(
            "PUT",
            f"ai-fde/api/threads/{THREAD_ID}/metadata",
            json_body={
                "currentVersion": VERSION,
                "agentStateModification": modification,
            },
        )


class TestAiFdeSendUserMessage:
    """send_user_message appends a captured-shape user-message item."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_sends_minimal_delta_with_captured_item_shape(self, mock_client_class):
        update_response = {
            "metadata": {
                "threadId": THREAD_ID,
                "threadVersion": NEW_VERSION,
                "contextItemsOrder": [EXISTING_ITEM_ID],
            }
        }
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.graphql.return_value = GraphQLResult(
            data={"aiFdeThreadV2": {"metadataV3": FULL_METADATA}}
        )
        mock_client.conjure.return_value = (200, update_response, "{...}")
        service = AiFdeService(profile="test")

        result = service.send_user_message(THREAD_ID, "hello agent")

        assert result["threadVersion"] == NEW_VERSION
        assert result["contextItemId"]
        mock_client.conjure.assert_called_once()
        verb, path = mock_client.conjure.call_args.args[:2]
        assert verb == "PUT"
        assert path == f"ai-fde/api/threads/{THREAD_ID}/update"
        body = mock_client.conjure.call_args.kwargs["json_body"]
        assert body["currentVersion"] == VERSION
        new_id = result["contextItemId"]
        assert body["itemIdsInOrder"] == [EXISTING_ITEM_ID, new_id]
        assert len(body["itemsToWrite"]) == 1
        item = body["itemsToWrite"][0]
        assert item["contextItemId"] == new_id
        assert item["typeAndVersion"] == {
            "contextItemType": "user-message",
            "contextItemVersion": 0,
        }
        assert item["content"] == [
            {
                "id": new_id,
                "type": "user-message",
                "prompt": "hello agent",
                "createdAt": item["content"][0]["createdAt"],
            }
        ]
        assert item["content"][0]["createdAt"].endswith("Z")
        assert item["fallbackMessages"] == [
            {
                "role": "USER",
                "contents": [{"text": "hello agent", "type": "text"}],
            }
        ]
        assert item["childContextItemsOrder"] == []
        assert item["fallbackMessage"] == {"role": "USER", "contents": []}

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_send_fails_loudly_on_redacted_thread(self, mock_client_class):
        redacted = {"id": THREAD_ID, "__typename": "AiFdeRedactedThreadMetadata"}
        service, _ = _service_with_graphql(
            mock_client_class,
            GraphQLResult(data={"aiFdeThreadV2": {"metadataV3": redacted}}),
        )

        with pytest.raises(AiFdeShapeError, match="version"):
            service.send_user_message(THREAD_ID, "hello")

    def test_build_user_message_item_matches_captured_shape(self):
        item = AiFdeService.build_user_message_item(
            "text", context_item_id=EXISTING_ITEM_ID
        )

        assert set(item) == {
            "contextItemId",
            "typeAndVersion",
            "content",
            "fallbackMessages",
            "childContextItemsOrder",
            "fallbackMessage",
        }
        assert item["content"][0]["prompt"] == "text"


class TestAiFdeErrorHandling:
    """Non-2xx and unverified shapes fail loudly with typed errors."""

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_typed_error_on_failure_status(self, mock_client_class):
        service, _ = _service_with_mock(
            mock_client_class,
            {
                "errorName": "AiFde:ThreadNotFound",
                "errorCode": "NOT_FOUND",
                "errorInstanceId": "abc",
                "parameters": {"threadId": THREAD_ID},
            },
            status=404,
        )

        with pytest.raises(FoundryApiError) as exc_info:
            service.get_settings()

        error = exc_info.value
        assert error.error_name == "AiFde:ThreadNotFound"
        assert error.status_code == 404

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_unverified_shape_fails_loudly(self, mock_client_class):
        service, _ = _service_with_mock(
            mock_client_class, ["not", "an", "object"], raw="[...]"
        )

        with pytest.raises(AiFdeShapeError, match="Unverified"):
            service.get_settings()

    @patch("foundry_cli.services.ai_fde.FoundryInternalClient")
    def test_transport_error_wrapped(self, mock_client_class):
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.conjure.side_effect = Exception("connection refused")
        service = AiFdeService(profile="test")

        with pytest.raises(RuntimeError, match="Failed to load settings"):
            service.get_settings()


class TestGraphQLMutationPolicy:
    """The scoped mutation exception: registry AND per-call opt-in required."""

    @patch("foundry_cli.services.foundry_internal_client.requests.request")
    def test_unregistered_mutation_banned_even_when_allowed(self, request):
        with pytest.raises(ValueError, match="only permits GraphQL reads"):
            FoundryInternalClient("qa").graphql(
                "WriteSomething",
                "mutation WriteSomething { writeSomething }",
                {},
                allow_mutation_names={"WriteSomething"},
            )

        request.assert_not_called()

    @patch("foundry_cli.services.foundry_internal_client.requests.request")
    def test_registered_mutation_banned_without_opt_in(self, request):
        with pytest.raises(ValueError, match="only permits GraphQL reads"):
            FoundryInternalClient("qa").graphql(
                CREATE_THREAD_MUTATION_NAME,
                CREATE_THREAD_MUTATION,
                {"threadName": "x"},
            )

        request.assert_not_called()

    @patch("foundry_cli.services.foundry_internal_client.CredentialStorage")
    @patch("foundry_cli.services.foundry_internal_client.requests.request")
    def test_registered_mutation_with_opt_in_passes(self, request, storage_class):
        storage_class.return_value.get_profile.return_value = {
            "host": "foundry.example",
            "token": "token",
        }
        response = Mock()
        response.status_code = 200
        response.text = (
            'data:{"data":{"createAiFdeThread":{"id":"abc"}},'
            '"extensions":{"requestIndex":0}}'
        )
        request.return_value = response

        result = FoundryInternalClient("qa").graphql(
            CREATE_THREAD_MUTATION_NAME,
            CREATE_THREAD_MUTATION,
            {"threadName": "New session"},
            allow_mutation_names={CREATE_THREAD_MUTATION_NAME},
        )

        request.assert_called_once()
        assert result.status == "ok"
        assert result.data == {"createAiFdeThread": {"id": "abc"}}
