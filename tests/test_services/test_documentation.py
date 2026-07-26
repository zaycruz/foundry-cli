"""Tests for the public-docs proxy service (network fully mocked)."""

from __future__ import annotations

import json

from pltr.services.documentation import (
    DocumentationService,
    _normalize_page_path,
    extract_code_blocks,
    DocumentationError,
)

import pytest


def _page_html(
    markdown: str, title: str = "Doc title", description: str = "desc"
) -> str:
    payload = {
        "props": {
            "pageProps": {
                "markdown": markdown,
                "metadata": {
                    "type": "raw",
                    "data": {"pageTitle": title, "seoDescription": description},
                },
                "tableOfContentsItems": [{"title": "Section A"}],
            }
        }
    }
    return (
        '<html><script id="__NEXT_DATA__" type="application/json" crossorigin="">'
        + json.dumps(payload)
        + "</script></html>"
    )


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://palantir.com/docs/foundry/transforms-python/overview/</loc></url>
<url><loc>https://palantir.com/docs/foundry/transforms-python/incremental-overview/</loc></url>
<url><loc>https://palantir.com/docs/foundry/compute-modules/overview/</loc></url>
<url><loc>https://palantir.com/docs/jp/foundry/transforms-python/overview/</loc></url>
<url><loc>https://palantir.com/docs/apollo/search/</loc></url>
</urlset>
"""


def _fake_fetcher(pages: dict[str, str], sitemaps: dict[str, str]):
    def fetch(url: str) -> str:
        if url in pages:
            return pages[url]
        if url in sitemaps:
            return sitemaps[url]
        raise DocumentationError(f"{url} returned HTTP 404; expected 200")

    return fetch


def _service(
    pages: dict[str, str] | None = None, sitemaps: dict[str, str] | None = None
) -> DocumentationService:
    return DocumentationService(fetcher=_fake_fetcher(pages or {}, sitemaps or {}))


class TestFetchPage:
    def test_returns_verbatim_markdown(self):
        url = "https://www.palantir.com/docs/foundry/transforms-python/overview/"
        service = _service(pages={url: _page_html("# Python transforms\n\nReal body.")})
        result = service.fetch_page("/foundry/transforms-python/overview/")
        assert result["status"] == "ok"
        assert result["markdown"] == "# Python transforms\n\nReal body."
        assert result["title"] == "Doc title"
        assert result["source_url"] == url
        assert result["toc"] == ["Section A"]

    def test_accepts_full_url(self):
        url = "https://www.palantir.com/docs/foundry/compute-modules/overview/"
        service = _service(pages={url: _page_html("body")})
        result = service.fetch_page(url)
        assert result["status"] == "ok"

    def test_missing_next_data_is_unavailable_not_fabricated(self):
        url = "https://www.palantir.com/docs/foundry/x/"
        service = _service(pages={url: "<html>no payload</html>"})
        result = service.fetch_page("/foundry/x/")
        assert result["status"] == "unavailable"
        assert "__NEXT_DATA__" in result["reason"]

    def test_http_failure_is_unavailable(self):
        service = _service()
        result = service.fetch_page("/foundry/missing/")
        assert result["status"] == "unavailable"
        assert "404" in result["reason"]

    def test_rejects_non_palantir_url(self):
        result = _service().fetch_page("https://evil.example.com/docs/foundry/x/")
        assert result["status"] == "invalid"

    def test_rejects_localized_page(self):
        result = _service().fetch_page("/docs/jp/foundry/transforms-python/overview/")
        assert result["status"] == "invalid"


class TestNormalize:
    def test_variants(self):
        assert _normalize_page_path("foundry/a/b") == "/foundry/a/b/"
        assert _normalize_page_path("/docs/foundry/a/") == "/foundry/a/"
        assert (
            _normalize_page_path("https://www.palantir.com/docs/foundry/a")
            == "/foundry/a/"
        )
        with pytest.raises(DocumentationError):
            _normalize_page_path("")


class TestListPageUrls:
    def test_unions_sitemaps_and_filters_locales(self):
        sitemaps = {
            "https://www.palantir.com/docs/sitemap.xml": SITEMAP_XML,
            "https://www.palantir.com/docs/sitemap-1.xml": SITEMAP_XML,
        }
        service = _service(sitemaps=sitemaps)
        result = service.list_page_urls()
        assert result["status"] == "partial"  # sitemap-2 missing
        assert result["page_count"] == 3
        assert all("/jp/" not in path for path in result["pages"])
        assert all(path.startswith("/foundry/") for path in result["pages"])
        assert result["sitemap_failures"]

    def test_total_failure_is_unavailable(self):
        result = _service().list_page_urls()
        assert result["status"] == "unavailable"
        assert result["page_count"] == 0


class TestSummaries:
    def _corpus_service(self) -> DocumentationService:
        sitemaps = {
            "https://www.palantir.com/docs/sitemap.xml": SITEMAP_XML,
            "https://www.palantir.com/docs/sitemap-1.xml": SITEMAP_XML,
            "https://www.palantir.com/docs/sitemap-2.xml": SITEMAP_XML,
        }
        return _service(sitemaps=sitemaps)

    def test_groups_by_section(self):
        result = self._corpus_service().summaries()
        assert result["status"] == "ok"
        sections = {entry["section"]: entry for entry in result["sections"]}
        assert sections["transforms-python"]["page_count"] == 2
        assert sections["compute-modules"]["page_count"] == 1

    def test_unknown_section_is_not_found(self):
        result = self._corpus_service().summaries(section="nope")
        assert result["status"] == "not-found"

    def test_with_overviews_fetches_real_lead(self):
        sitemaps = {
            path: SITEMAP_XML
            for path in (
                "https://www.palantir.com/docs/sitemap.xml",
                "https://www.palantir.com/docs/sitemap-1.xml",
                "https://www.palantir.com/docs/sitemap-2.xml",
            )
        }
        pages = {
            "https://www.palantir.com/docs/foundry/transforms-python/overview/": _page_html(
                "# T\n\nLead paragraph here.\n\nMore."
            ),
        }
        result = _service(pages=pages, sitemaps=sitemaps).summaries(
            section="transforms-python", with_overviews=True
        )
        overview = result["sections"][0]["overview"]
        assert overview["lead"] == "Lead paragraph here."


class TestSearch:
    def test_ranks_by_real_term_frequency(self):
        sitemaps = {
            path: SITEMAP_XML
            for path in (
                "https://www.palantir.com/docs/sitemap.xml",
                "https://www.palantir.com/docs/sitemap-1.xml",
                "https://www.palantir.com/docs/sitemap-2.xml",
            )
        }
        pages = {
            "https://www.palantir.com/docs/foundry/transforms-python/overview/": _page_html(
                "transforms transforms transforms python"
            ),
            "https://www.palantir.com/docs/foundry/transforms-python/incremental-overview/": _page_html(
                "transforms once"
            ),
        }
        result = _service(pages=pages, sitemaps=sitemaps).search(
            "transforms", fetch_pages=2
        )
        assert result["status"] == "ok"
        assert result["coverage"] == "partial"
        assert len(result["results"]) == 2
        assert result["results"][0]["term_hits"] >= result["results"][1]["term_hits"]
        assert "transforms" in result["results"][0]["excerpt"]

    def test_empty_query_is_invalid(self):
        assert _service().search("  ")["status"] == "invalid"

    def test_unavailable_corpus_propagates(self):
        result = _service().search("anything")
        assert result["status"] == "unavailable"
        assert result["results"] is None


class TestTopic:
    def test_fetches_curated_pages_and_marks_failures(self):
        sitemaps = {
            path: SITEMAP_XML
            for path in (
                "https://www.palantir.com/docs/sitemap.xml",
                "https://www.palantir.com/docs/sitemap-1.xml",
                "https://www.palantir.com/docs/sitemap-2.xml",
            )
        }
        pages = {
            "https://www.palantir.com/docs/foundry/transforms-python/overview/": _page_html(
                "real overview"
            ),
        }
        result = _service(pages=pages, sitemaps=sitemaps).topic("python-transforms")
        assert result["status"] == "partial"
        assert len(result["pages"]) == 1
        assert result["pages"][0]["markdown"] == "real overview"
        assert len(result["failures"]) == 2
        # related pages come from the real sitemap family prefix
        assert result["related_pages"] == [
            "/foundry/transforms-python/incremental-overview/"
        ]

    def test_unknown_topic(self):
        assert _service().topic("nope")["status"] == "invalid"


def test_extract_code_blocks():
    blocks = extract_code_blocks("intro\n```python\nx = 1\n```\nmiddle\n```\ny\n```\n")
    assert blocks == [
        {"language": "python", "code": "x = 1"},
        {"language": "", "code": "y"},
    ]
