"""Tests for the stable agent output and execution policy helpers."""

import json
from io import StringIO

import pytest

from foundry_cli.utils.agent_output import (
    AgentPolicyError,
    configure_agent_settings,
    flush_agent_output,
    redact_value,
    render_agent_json,
    require_confirmation,
)
from foundry_cli.utils.formatting import OutputFormatter


def test_agent_json_has_stable_envelope_and_redacts_credentials() -> None:
    rendered = render_agent_json(
        {"name": "example", "token": "secret-value"},
        meta={"operation": "test"},
        pagination={"has_more": False},
    )

    payload = json.loads(rendered)
    assert payload["schema_version"] == "foundry-agent-v1"
    assert payload["data"] == {"name": "example", "token": "[REDACTED]"}
    assert payload["meta"] == {"operation": "test"}
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert payload["pagination"] == {"has_more": False}
    assert payload["artifacts"] == []


def test_agent_json_preserves_pagination_cursors_but_redacts_credentials() -> None:
    payload = json.loads(
        render_agent_json(
            {"token": "secret", "page_token": "cursor"},
            pagination={"next_page_token": "cursor-2"},
        )
    )

    assert payload["data"] == {
        "token": "[REDACTED]",
        "page_token": "cursor",
    }
    assert payload["pagination"]["next_page_token"] == "cursor-2"


def test_formatter_uses_agent_envelope_when_enabled(capsys) -> None:
    # The formatter now records the result instead of writing it: a command
    # that renders more than once must still produce one envelope. The flush
    # at the end of the invocation is what reaches stdout.
    configure_agent_settings(enabled=True)
    try:
        OutputFormatter().format_output({"value": 3}, "table")
        rendered = flush_agent_output(StringIO())
    finally:
        configure_agent_settings()

    assert rendered is not None
    assert capsys.readouterr().out == ""
    payload = json.loads(rendered)
    assert payload["schema_version"] == "foundry-agent-v1"
    assert payload["data"] == {"value": 3}
    assert payload["meta"]["result_type"] == "dict"


def test_non_interactive_confirmation_requires_explicit_flag() -> None:
    configure_agent_settings(non_interactive=True)
    try:
        with pytest.raises(AgentPolicyError, match="explicit --force"):
            require_confirmation("Delete resource?")
        assert require_confirmation("Delete resource?", confirmed=True)
    finally:
        configure_agent_settings()


def test_redact_value_handles_nested_sensitive_keys() -> None:
    assert redact_value({"nested": {"client_secret": "secret"}}) == {
        "nested": {"client_secret": "[REDACTED]"}
    }


def test_redact_value_scrubs_credentials_embedded_in_strings() -> None:
    assert redact_value({"remote": "https://user:hunter2@github.com/org/repo.git"}) == {
        "remote": "https://user:[REDACTED]@github.com/org/repo.git"
    }
    assert redact_value({"line": "Authorization: Bearer abcdef123456"}) == {
        "line": "Authorization: Bearer [REDACTED]"
    }
    assert redact_value({"npmrc": "//registry/:_authToken=npm_xyz"}) == {
        "npmrc": "//registry/:_authToken=[REDACTED]"
    }
    assert redact_value({"argv": "git clone --token ghp_secretvalue ."}) == {
        "argv": "git clone --token [REDACTED] ."
    }
    assert redact_value({"env": "FOO_TOKEN=abc123\nOTHER=ok"}) == {
        "env": "FOO_TOKEN=[REDACTED]\nOTHER=ok"
    }
    # Ordinary strings pass through untouched.
    assert redact_value({"note": "branch develop"}) == {"note": "branch develop"}


def test_buffer_agent_exception_emits_typed_foundry_error() -> None:
    from foundry_cli.services.errors import FoundryApiError
    from foundry_cli.utils.agent_output import buffer_agent_exception

    configure_agent_settings(enabled=True)
    try:
        buffer_agent_exception(
            FoundryApiError(
                "schema conflict",
                error_name="Datasets:SchemaVersionConflict",
                error_code="CONFLICT",
                error_instance_id="00000000-1111-2222-3333-444444444444",
                safe_parameters={"datasetRid": "ri.foundry.main.dataset.abc"},
                status_code=409,
            )
        )
        rendered = flush_agent_output(StringIO())
    finally:
        configure_agent_settings()

    assert rendered is not None
    payload = json.loads(rendered)
    assert len(payload["errors"]) == 1
    entry = payload["errors"][0]
    assert entry["type"] == "foundry_api"
    assert entry["errorName"] == "Datasets:SchemaVersionConflict"
    assert entry["errorCode"] == "CONFLICT"
    assert entry["errorInstanceId"] == "00000000-1111-2222-3333-444444444444"
    assert entry["safeParameters"] == {"datasetRid": "ri.foundry.main.dataset.abc"}


def test_format_agent_with_output_file_still_buffers_envelope(tmp_path) -> None:
    configure_agent_settings(enabled=True)
    out = tmp_path / "result.json"
    try:
        OutputFormatter().format_output({"value": 7}, "json", str(out))
        rendered = flush_agent_output(StringIO())
    finally:
        configure_agent_settings()

    assert rendered is not None
    payload = json.loads(rendered)
    # stdout envelope carries the result even though --output was used
    assert payload["data"] == {"value": 7}
    assert payload["meta"]["output_file"] == str(out)
    on_disk = json.loads(out.read_text())
    assert on_disk["data"] == {"value": 7}
