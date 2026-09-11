"""CLI tests for the docs command group (service mocked; no network)."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from foundry_cli.cli import app


runner = CliRunner()

PAGE = {
    "status": "ok",
    "page": "/foundry/transforms-python/overview/",
    "source_url": "https://www.palantir.com/docs/foundry/transforms-python/overview/",
    "title": "Documentation | Python > Overview",
    "description": "desc",
    "markdown": "# Python transforms\n\nReal body.",
    "toc": [],
}

TOPIC_RESULT = {
    "status": "ok",
    "topic": "python-transforms",
    "title": "Python transforms",
    "pages": [PAGE],
    "failures": [],
    "related_pages": ["/foundry/transforms-python/incremental-overview/"],
    "reason": None,
}


def test_topic_command_renders_verbatim_markdown():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.topic.return_value = TOPIC_RESULT
        result = runner.invoke(app, ["docs", "python-transforms"])
    assert result.exit_code == 0, result.output
    assert "Real body." in result.output
    assert TOPIC_RESULT["related_pages"][0] in result.output
    service.return_value.topic.assert_called_once_with("python-transforms")


def test_topic_command_json_format():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.topic.return_value = TOPIC_RESULT
        result = runner.invoke(app, ["docs", "compute", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["pages"][0]["markdown"] == "# Python transforms\n\nReal body."
    service.return_value.topic.assert_called_once_with("compute")


def test_topic_unavailable_exits_nonzero():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.topic.return_value = {
            "status": "unavailable",
            "topic": "ml",
            "title": "Machine learning",
            "pages": [],
            "failures": [],
            "related_pages": [],
            "reason": "no curated page for this topic could be retrieved",
        }
        result = runner.invoke(app, ["docs", "ml"])
    assert result.exit_code == 1


def test_page_command():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.fetch_page.return_value = PAGE
        result = runner.invoke(
            app, ["docs", "page", "/foundry/transforms-python/overview/"]
        )
    assert result.exit_code == 0, result.output
    assert (
        "Source: https://www.palantir.com/docs/foundry/transforms-python/overview/"
        in result.output
    )
    assert "Real body." in result.output


def test_page_not_found_exits_nonzero():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.fetch_page.return_value = {
            "status": "unavailable",
            "reason": "HTTP 404",
            "page": "/foundry/nope/",
            "source_url": "https://www.palantir.com/docs/foundry/nope/",
        }
        result = runner.invoke(app, ["docs", "page", "/foundry/nope/"])
    assert result.exit_code == 1
    assert "UNAVAILABLE" in result.output


def test_summaries_command():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.summaries.return_value = {
            "status": "ok",
            "page_count": 3,
            "section_count": 2,
            "sections": [
                {
                    "section": "transforms-python",
                    "page_count": 2,
                    "pages": ["/foundry/transforms-python/overview/"],
                    "pages_truncated": False,
                }
            ],
            "sitemaps_fetched": [],
            "sitemap_failures": [],
        }
        result = runner.invoke(app, ["docs", "summaries"])
    assert result.exit_code == 0, result.output
    assert "transforms-python (2 pages)" in result.output
    service.return_value.summaries.assert_called_once_with(
        section=None, with_overviews=False, section_limit=50
    )


def test_search_command_shows_partial_coverage():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.search.return_value = {
            "status": "ok",
            "query": "incremental",
            "results": [
                {
                    "page": "/foundry/transforms-python/incremental-overview/",
                    "source_url": "https://www.palantir.com/docs/foundry/transforms-python/incremental-overview/",
                    "title": "Incremental",
                    "term_hits": 3,
                    "excerpt": "real incremental excerpt",
                }
            ],
            "slug_candidates": 1,
            "pages_fetched": 1,
            "search_strategy": "slug-token candidates",
            "coverage": "partial",
            "coverage_note": "bounded subset",
            "sitemaps_fetched": [],
        }
        result = runner.invoke(app, ["docs", "search", "incremental"])
    assert result.exit_code == 0, result.output
    assert "Coverage: partial" in result.output
    assert "real incremental excerpt" in result.output
    service.return_value.search.assert_called_once_with(
        "incremental", limit=10, fetch_pages=5
    )


def test_agent_mode_emits_single_envelope():
    with patch("foundry_cli.commands.docs.DocumentationService") as service:
        service.return_value.fetch_page.return_value = PAGE
        result = runner.invoke(app, ["--agent", "docs", "page", "/foundry/x/"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "foundry-agent-v1"
    assert payload["data"]["markdown"] == "# Python transforms\n\nReal body."
    assert payload["meta"]["result_type"] == "docs-page"


def test_all_eleven_subcommands_registered():
    from foundry_cli.capabilities import registered_command_paths

    paths = registered_command_paths()
    expected = {
        "docs python-transforms",
        "docs typescript-v1-functions",
        "docs typescript-v2-functions",
        "docs custom-widgets",
        "docs ml",
        "docs spark-profile",
        "docs osdk-react-components",
        "docs compute",
        "docs page",
        "docs summaries",
        "docs search",
    }
    assert expected <= paths


def test_invalid_format_rejected():
    result = runner.invoke(app, ["docs", "page", "/foundry/x/", "--format", "csv"])
    assert result.exit_code != 0
