"""Read-only access to Palantir's public Foundry documentation.

Every command returns verbatim Palantir-authored content retrieved from the
public documentation site (https://www.palantir.com/docs); nothing is
generated locally. No Foundry profile is required.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional

import typer

from ..services.documentation import TOPICS, DocumentationService
from ..utils.agent_output import buffer_agent_payload, resolve_output_format
from ..utils.completion import complete_output_format

app = typer.Typer(
    help="Read Palantir's public Foundry documentation (verbatim, read-only)"
)

_FORMATS = {"markdown", "json"}


def _service() -> DocumentationService:
    return DocumentationService()


def _emit(
    result: Mapping[str, Any],
    format_type: str,
    *,
    result_type: str,
    human: str,
) -> None:
    if resolve_output_format(format_type) == "agent":
        buffer_agent_payload(dict(result), meta={"result_type": result_type})
        return
    if format_type == "json":
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    typer.echo(human, nl=False)


def _check_format(format_type: str) -> None:
    if format_type not in _FORMATS:
        raise typer.BadParameter(
            "must be markdown or json", param_hint="--format"
        )


def _fail_unless_ok(result: Mapping[str, Any]) -> None:
    if result.get("status") in {"unavailable", "invalid", "not-found"}:
        raise typer.Exit(1)


def _render_page(page: Mapping[str, Any]) -> str:
    if page.get("status") != "ok":
        return (
            f"UNAVAILABLE: {page.get('reason', 'unknown')}\n"
            f"Source: {page.get('source_url') or page.get('page')}\n"
        )
    return (
        f"Source: {page['source_url']}\n"
        f"Title: {page.get('title') or 'unknown'}\n"
        "---\n"
        f"{page['markdown']}\n"
    )


def _render_topic(result: Mapping[str, Any]) -> str:
    lines = [
        f"Topic: {result.get('title')} ({result.get('topic')})",
        f"Status: {result.get('status')}",
        "",
    ]
    for page in result.get("pages") or []:
        lines.append(_render_page(page))
    for failure in result.get("failures") or []:
        lines.append(
            f"FAILED PAGE: {failure.get('page')} — {failure.get('reason')}\n"
        )
    related = result.get("related_pages") or []
    if related:
        lines.append("Related pages (from the docs sitemap):")
        lines.extend(f"  {path}" for path in related)
        lines.append("")
    return "\n".join(lines)


def _topic_command(topic_key: str) -> Callable[..., None]:
    def command(
        format: str = typer.Option(
            "markdown",
            "--format",
            "-f",
            help="Output format (markdown, json)",
            autocompletion=complete_output_format,
        ),
    ) -> None:
        """Fetch this topic's curated real documentation pages."""
        _check_format(format)
        try:
            result = _service().topic(topic_key)
        except Exception as exc:
            typer.echo(f"Error: {exc}")
            raise typer.Exit(1)
        _emit(
            result,
            format,
            result_type=f"docs-{topic_key}",
            human=_render_topic(result),
        )
        _fail_unless_ok(result)

    return command


for _topic_key, _spec in TOPICS.items():
    app.command(_topic_key, help=f"{_spec['title']} documentation")(
        _topic_command(_topic_key)
    )


@app.command("page")
def docs_page(
    page: str = typer.Argument(
        ...,
        help="Docs path (e.g. /foundry/transforms-python/overview/) or full palantir.com URL",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Load one Foundry documentation page as verbatim markdown."""
    _check_format(format)
    try:
        result = _service().fetch_page(page)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(result, format, result_type="docs-page", human=_render_page(result))
    _fail_unless_ok(result)


@app.command("summaries")
def docs_summaries(
    section: Optional[str] = typer.Option(
        None, "--section", help="Restrict to one docs section (e.g. transforms-python)"
    ),
    with_overviews: bool = typer.Option(
        False,
        "--with-overviews",
        help="Fetch each section overview page's real lead paragraph (slower)",
    ),
    section_limit: int = typer.Option(
        50, "--section-limit", help="Maximum sections to return"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Summarize the documentation corpus by section from the real sitemap."""
    _check_format(format)
    try:
        result = _service().summaries(
            section=section,
            with_overviews=with_overviews,
            section_limit=section_limit,
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(
        result,
        format,
        result_type="docs-summaries",
        human=_render_summaries(result),
    )
    _fail_unless_ok(result)


def _render_summaries(result: Mapping[str, Any]) -> str:
    sections = result.get("sections")
    if not sections:
        return f"UNAVAILABLE: {result.get('reason', 'unknown')}\n"
    lines = [
        f"Documentation corpus: {result.get('page_count')} pages in "
        f"{result.get('section_count')} sections "
        f"(status {result.get('status')})",
        "",
    ]
    for entry in sections:
        lines.append(f"{entry['section']} ({entry['page_count']} pages)")
        overview = entry.get("overview")
        if isinstance(overview, Mapping) and overview.get("lead"):
            lines.append(f"  {overview['lead']}")
        for page in (entry.get("pages") or [])[:5]:
            lines.append(f"  {page}")
        if entry.get("pages_truncated"):
            lines.append("  ...")
    return "\n".join(lines) + "\n"


@app.command("search")
def docs_search(
    query: str = typer.Argument(..., help="Search terms"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum results"),
    fetch_pages: int = typer.Option(
        5,
        "--fetch-pages",
        help="Candidate pages fetched and ranked (bounded network)",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format (markdown, json)",
        autocompletion=complete_output_format,
    ),
) -> None:
    """Search the real documentation corpus (bounded, honestly partial)."""
    _check_format(format)
    try:
        result = _service().search(query, limit=limit, fetch_pages=fetch_pages)
    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)
    _emit(
        result,
        format,
        result_type="docs-search",
        human=_render_search(result),
    )
    _fail_unless_ok(result)


def _render_search(result: Mapping[str, Any]) -> str:
    results = result.get("results")
    if results is None:
        return f"UNAVAILABLE: {result.get('reason', 'unknown')}\n"
    lines = [
        f"Query: {result.get('query')}",
        f"Strategy: {result.get('search_strategy')}",
        f"Coverage: {result.get('coverage')} — {result.get('coverage_note')}",
        "",
    ]
    if not results:
        lines.append("No matching pages in the fetched candidates.")
    for entry in results:
        lines.append(f"{entry.get('title') or entry['page']}")
        lines.append(f"  {entry['source_url']}")
        if entry.get("excerpt"):
            lines.append(f"  {entry['excerpt']}")
        lines.append("")
    return "\n".join(lines) + "\n"
