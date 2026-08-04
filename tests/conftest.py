"""
Pytest configuration and fixtures for foundry tests.
"""

import os

# Neutralise forced colour before anything imports typer or foundry_cli. Two separate
# mechanisms make a fixture too late, so this has to run in the module body:
#
#   1. ``typer.rich_utils`` computes FORCE_TERMINAL from these variables at
#      *module import*. Clearing them afterwards does nothing.
#   2. ``src/foundry_cli/commands/*`` construct module-level ``Console()`` objects at
#      *collection* time, and ``Console.__init__`` caches the colour system.
#
# Under forced colour Rich's option highlighter splits flags into ANSI-separated
# fragments -- ``--parent-rid`` becomes ``\x1b[1;36m-\x1b[0m\x1b[1;36m-parent...``
# -- so any assertion on a literal flag string fails. GITHUB_ACTIONS is always
# set on hosted runners, which is why CI diverged from local runs.
for _colour_var in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(_colour_var, None)

import typer.rich_utils as _typer_rich_utils  # noqa: E402

# Belt and braces: the clear above only works while typer imports rich_utils
# lazily. Pin the attribute too, so a typer patch release that hoists that
# import cannot silently re-arm the failure.
_typer_rich_utils.FORCE_TERMINAL = None

import pytest  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import Mock, patch  # noqa: E402
from typing import Generator  # noqa: E402

from foundry_cli.auth.storage import CredentialStorage  # noqa: E402
from foundry_cli.config.settings import Settings  # noqa: E402
from foundry_cli.config.profiles import ProfileManager  # noqa: E402
from foundry_cli.utils.agent_output import configure_agent_settings  # noqa: E402


def test_colour_is_neutralised_for_the_session() -> None:
    """The conftest colour clear must actually reach typer's console.

    Asserting on pass counts would be a tautology -- it cannot fail once the
    two environments are equalised. Assert the mechanism instead.
    """
    assert _typer_rich_utils.FORCE_TERMINAL is None
    assert _typer_rich_utils._get_rich_console().is_terminal is False


@pytest.fixture(autouse=True)
def _reset_agent_settings() -> Generator[None, None, None]:
    """Keep --agent state from leaking between tests.

    The root CLI callback sets agent mode on a process-wide ContextVar and only
    resets it on the *next* root invocation. A test that invokes a sub-app
    directly bypasses that reset, so a prior `--agent` run would leak in and
    flip its output path. Reset around every test so order never matters.
    """
    configure_agent_settings()
    try:
        yield
    finally:
        configure_agent_settings()


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    """Create a temporary configuration directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_keyring():
    """Mock keyring for credential storage tests."""
    with (
        patch("keyring.set_password") as mock_set,
        patch("keyring.get_password") as mock_get,
        patch("keyring.delete_password") as mock_delete,
    ):
        # Set up mock storage
        storage = {}

        def set_password(service, username, password):
            storage[f"{service}:{username}"] = password

        def get_password(service, username):
            return storage.get(f"{service}:{username}")

        def delete_password(service, username):
            key = f"{service}:{username}"
            if key in storage:
                del storage[key]

        mock_set.side_effect = set_password
        mock_get.side_effect = get_password
        mock_delete.side_effect = delete_password

        yield {
            "set": mock_set,
            "get": mock_get,
            "delete": mock_delete,
            "storage": storage,
        }


@pytest.fixture
def mock_settings(temp_config_dir):
    """Mock settings with temporary directory."""
    with patch.object(Settings, "_get_config_dir", return_value=temp_config_dir):
        settings = Settings()
        yield settings


@pytest.fixture
def mock_credential_storage(mock_keyring):
    """Mock credential storage with keyring mocked."""
    storage = CredentialStorage()
    yield storage


@pytest.fixture
def mock_profile_manager(temp_config_dir):
    """Mock profile manager with temporary directory."""
    with patch.object(Settings, "_get_config_dir", return_value=temp_config_dir):
        manager = ProfileManager()
        yield manager


@pytest.fixture
def sample_token_credentials():
    """Sample token-based credentials."""
    return {
        "auth_type": "token",
        "host": "https://test.palantirfoundry.com",
        "token": "test_token_12345",
    }


@pytest.fixture
def sample_oauth_credentials():
    """Sample OAuth credentials."""
    return {
        "auth_type": "oauth",
        "host": "https://test.palantirfoundry.com",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "scopes": ["api:read"],
    }


@pytest.fixture
def mock_requests():
    """Mock requests for HTTP calls."""
    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        # Default successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "username": "test.user@example.com",
            "id": "12345-abcde",
            "organization": {"rid": "ri.organization.main"},
        }

        mock_get.return_value = mock_response
        mock_post.return_value = mock_response

        yield {"get": mock_get, "post": mock_post, "response": mock_response}
