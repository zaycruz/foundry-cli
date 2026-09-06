"""Subprocess runner tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from foundry_cli_hermes_plugin.runner import (
    AgentExecutionError,
    CliRunner,
    RunnerSettings,
)


def test_runner_uses_agent_contract_without_a_shell(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema_version": "foundry-agent-v1",
                    "data": {"ok": True},
                    "meta": {},
                    "warnings": [],
                    "errors": [],
                    "pagination": None,
                    "artifacts": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = CliRunner(
        RunnerSettings(
            executable=("uv", "run", "pfoundry"),
            working_directory=tmp_path,
        )
    )

    result = runner.run(["search", "literal;not-shell"])

    assert result["data"] == {"ok": True}
    argv, kwargs = calls[0]
    assert argv == [
        "uv",
        "run",
        "pfoundry",
        "--agent",
        "--non-interactive",
        "search",
        "literal;not-shell",
    ]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["cwd"] == tmp_path


def test_runner_rejects_malformed_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="{}\n{}",
            stderr="",
        ),
    )
    runner = CliRunner(RunnerSettings(working_directory=tmp_path))

    with pytest.raises(AgentExecutionError, match="one JSON envelope"):
        runner.run(["hello"])


def test_runner_converts_timeout_to_structured_error(monkeypatch, tmp_path: Path):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=2)

    monkeypatch.setattr(subprocess, "run", timeout)
    runner = CliRunner(RunnerSettings(working_directory=tmp_path, timeout_seconds=2))

    with pytest.raises(AgentExecutionError, match="timed out"):
        runner.run(["hello"])


def test_runner_redacts_credential_like_output(monkeypatch, tmp_path: Path):
    payload = {
        "schema_version": "foundry-agent-v1",
        "data": {"token": "secret-token", "message": "Bearer abc123"},
        "meta": {},
        "warnings": [],
        "errors": [],
        "pagination": None,
        "artifacts": [],
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="client_secret=hidden",
        ),
    )
    runner = CliRunner(RunnerSettings(working_directory=tmp_path))

    result = runner.run(["hello"])

    assert result["data"]["token"] == "[REDACTED]"
    assert result["data"]["message"] == "Bearer [REDACTED]"
    assert result["meta"]["stderr"] == "client_secret=[REDACTED]"
