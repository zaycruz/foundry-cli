"""Tests for native project discovery commands."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from io import StringIO

from foundry_cli.commands.project import app
from foundry_cli.utils.agent_output import flush_agent_output
from foundry_cli.utils.pagination import PaginationMetadata, PaginationResult

runner = CliRunner()


def _page() -> PaginationResult:
    return PaginationResult(
        data=[{"rid": "ri.compass.main.project.1", "display_name": "One"}],
        metadata=PaginationMetadata(next_page_token="next", has_more=True),
    )


def test_project_imports_forwards_pagination() -> None:
    with patch("foundry_cli.commands.project.ProjectService") as service_class:
        service = Mock()
        service.get_project_imports.return_value = _page()
        service_class.return_value = service

        result = runner.invoke(
            app,
            [
                "imports",
                "ri.compass.main.project.1",
                "--page-size",
                "10",
                "--page-token",
                "previous",
            ],
        )

    assert result.exit_code == 0
    service.get_project_imports.assert_called_once_with(
        "ri.compass.main.project.1",
        reference_type=None,
        page_size=10,
        page_token="previous",
    )


def test_project_search_agent_output_is_enveloped() -> None:
    with (
        patch("foundry_cli.commands.project.ProjectService") as service_class,
        patch("foundry_cli.commands.project.agent_mode_enabled", return_value=True),
    ):
        service = Mock()
        service.search_projects.return_value = _page()
        service_class.return_value = service

        result = runner.invoke(app, ["search", "project"])

    assert result.exit_code == 0
    rendered = flush_agent_output(StringIO())
    assert rendered is not None
    assert '"schema_version": "foundry-agent-v1"' in rendered
    assert '"next_page_token": "next"' in rendered


def test_project_templates_list_forwards_options() -> None:
    with patch("foundry_cli.commands.project.CompassService") as service_class:
        service = Mock()
        service.list_project_templates.return_value = _page()
        service_class.return_value = service

        result = runner.invoke(
            app,
            [
                "templates",
                "list",
                "--namespace-rid",
                "ri.compass.main.folder.1",
                "--page-size",
                "10",
                "--page-token",
                "0",
            ],
        )

    assert result.exit_code == 0
    service.list_project_templates.assert_called_once_with(
        namespace_rid="ri.compass.main.folder.1",
        page_size=10,
        page_token="0",
    )


def test_project_templates_list_agent_output_is_enveloped() -> None:
    with (
        patch("foundry_cli.commands.project.CompassService") as service_class,
        patch("foundry_cli.commands.project.agent_mode_enabled", return_value=True),
    ):
        service = Mock()
        service.list_project_templates.return_value = _page()
        service_class.return_value = service

        result = runner.invoke(app, ["templates", "list"])

    assert result.exit_code == 0
    rendered = flush_agent_output(StringIO())
    assert rendered is not None
    assert '"operation": "list_foundry_project_templates"' in rendered
    assert '"next_page_token": "next"' in rendered


def test_project_templates_list_error_returns_nonzero() -> None:
    with patch("foundry_cli.commands.project.CompassService") as service_class:
        service_class.return_value.list_project_templates.side_effect = RuntimeError(
            "HTTP 500"
        )

        result = runner.invoke(app, ["templates", "list"])

    assert result.exit_code == 1
    assert "HTTP 500" in result.stderr
