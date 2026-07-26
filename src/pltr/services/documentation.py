"""Read-only access to Palantir's public Foundry documentation.

The stack-side documentation API behind the Foundry ``/documentation`` app is
NOT VERIFIED on the reference stack (the app itself requires interactive
OAuth, and every verified ``/documentation/api/*`` path returns
``Default:NotFound`` with no documented request contract), so this service
does not guess it. Instead it proxies Palantir's public documentation site,
whose Next.js pages embed the page's raw markdown in the ``__NEXT_DATA__``
script tag and whose XML sitemaps enumerate the full page corpus. Every
returned page body is verbatim Palantir-authored markdown; nothing is
generated locally. Read-only GETs only, no authentication required.

Verified:
- ``https://www.palantir.com/docs/foundry/<section>/<page>/`` returns HTML
  with ``<script id="__NEXT_DATA__" ...>`` whose ``props.pageProps`` carries
  ``markdown``, ``metadata.data.pageTitle``, ``metadata.data.seoDescription``,
  ``tableOfContentsItems`` and ``sidebarNavProps``.
- ``https://palantir.com/docs/robots.txt`` lists ``sitemap.xml`` and
  ``sitemap-1.xml``; ``sitemap-2.xml`` continues the same urlset. Unioned and
  filtered to ``/docs/foundry/`` they yield ~4.4k English page URLs.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import urlparse

import requests

DOCS_ORIGIN = "https://www.palantir.com"
DOCS_BASE_PATH = "/docs"
SITEMAP_PATHS = (
    "/docs/sitemap.xml",
    "/docs/sitemap-1.xml",
    "/docs/sitemap-2.xml",
)
_FOUNDRY_PREFIX = "/docs/foundry/"
_LOCALE_PREFIXES = ("/docs/jp/", "/docs/zh/", "/docs/kr/")
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
    re.S,
)
_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
_REQUEST_TIMEOUT = 20

# Curated, sitemap-verified page families for the topic commands. Every path
# below was confirmed present in the public docs sitemap on .
TOPICS: dict[str, dict[str, Any]] = {
    "python-transforms": {
        "title": "Python transforms",
        "pages": [
            "/foundry/transforms-python/overview/",
            "/foundry/transforms-python/getting-started/",
            "/foundry/transforms-python/transforms/",
        ],
        "family_prefix": "/foundry/transforms-python/",
    },
    "typescript-v1-functions": {
        "title": "TypeScript v1 functions",
        "pages": [
            "/foundry/functions/typescript-v1-getting-started/",
            "/foundry/functions/typescript-error-types/",
        ],
        "family_prefix": "/foundry/functions/",
    },
    "typescript-v2-functions": {
        "title": "TypeScript v2 functions",
        "pages": [
            "/foundry/functions/typescript-v2-getting-started/",
            "/foundry/functions/typescript-v2-ontology-edits/",
            "/foundry/functions/typescript-v2-migration/",
        ],
        "family_prefix": "/foundry/functions/",
    },
    "custom-widgets": {
        "title": "Custom widgets",
        "pages": [
            "/foundry/custom-widgets/overview/",
            "/foundry/custom-widgets/core-concepts/",
            "/foundry/custom-widgets/create/",
        ],
        "family_prefix": "/foundry/custom-widgets/",
    },
    "ml": {
        "title": "Machine learning (model integration)",
        "pages": [
            "/foundry/model-integration/overview/",
            "/foundry/model-integration/getting-started/",
            "/foundry/model-integration/models/",
        ],
        "family_prefix": "/foundry/model-integration/",
    },
    "spark-profile": {
        "title": "Spark profiles",
        "pages": [
            "/foundry/code-repositories/spark-profiles/",
            "/foundry/optimizing-pipelines/apply-spark-profiles/",
            "/foundry/optimizing-pipelines/spark-profiles-reference/",
        ],
        "family_prefix": "/foundry/optimizing-pipelines/",
    },
    "osdk-react-components": {
        "title": "OSDK React applications",
        "pages": [
            "/foundry/ontology-sdk-react-applications/overview/",
            "/foundry/ontology-sdk-react-applications/development/",
        ],
        "family_prefix": "/foundry/ontology-sdk-react-applications/",
    },
    "compute": {
        "title": "Compute modules",
        "pages": [
            "/foundry/compute-modules/overview/",
            "/foundry/compute-modules/get-started/",
            "/foundry/compute-modules/functions/",
        ],
        "family_prefix": "/foundry/compute-modules/",
    },
}


class DocumentationError(RuntimeError):
    """Raised when the public documentation site cannot be retrieved."""


Fetcher = Callable[[str], str]


def _requests_fetcher(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"Accept": "text/html,application/xml,*/*"},
        )
    except requests.RequestException as exc:
        raise DocumentationError(f"failed to retrieve {url}: {exc}") from exc
    if response.status_code != 200:
        raise DocumentationError(
            f"{url} returned HTTP {response.status_code}; expected 200"
        )
    return response.text


def _normalize_page_path(path_or_url: str) -> str:
    """Normalize a docs URL or path to a ``/foundry/...`` path with trailing slash."""
    candidate = path_or_url.strip()
    if not candidate:
        raise DocumentationError("page path must not be empty")
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.netloc and "palantir.com" not in parsed.netloc:
            raise DocumentationError(
                f"only palantir.com documentation URLs are supported: {candidate}"
            )
        candidate = parsed.path
    if candidate.startswith(DOCS_BASE_PATH):
        candidate = candidate[len(DOCS_BASE_PATH) :]
    for locale in ("/jp", "/zh", "/kr"):
        if candidate.startswith(locale + "/"):
            raise DocumentationError(
                f"localized documentation pages are out of scope: {path_or_url}"
            )
    if not candidate.startswith("/"):
        candidate = "/" + candidate
    if not candidate.endswith("/"):
        candidate += "/"
    return candidate


class DocumentationService:
    """Fetch real Palantir documentation content from the public docs site."""

    def __init__(
        self,
        *,
        fetcher: Optional[Fetcher] = None,
        origin: str = DOCS_ORIGIN,
    ) -> None:
        self._fetch = fetcher or _requests_fetcher
        self.origin = origin.rstrip("/")

    # -- low-level retrieval ------------------------------------------------

    def fetch_page(self, path_or_url: str) -> dict[str, Any]:
        """Return one documentation page's verbatim markdown and metadata.

        The markdown is extracted from the page's ``__NEXT_DATA__`` payload;
        if the site stops embedding it, the result is ``unavailable`` with a
        reason rather than a fabricated body.
        """
        try:
            path = _normalize_page_path(path_or_url)
        except DocumentationError as exc:
            return {"status": "invalid", "reason": str(exc), "page": path_or_url}
        source_url = f"{self.origin}{DOCS_BASE_PATH}{path}"
        try:
            html = self._fetch(source_url)
        except DocumentationError as exc:
            return {
                "status": "unavailable",
                "reason": str(exc),
                "page": path,
                "source_url": source_url,
            }
        match = _NEXT_DATA_RE.search(html)
        if not match:
            return {
                "status": "unavailable",
                "reason": "page has no embedded __NEXT_DATA__ payload; "
                "content cannot be extracted without fabricating it",
                "page": path,
                "source_url": source_url,
            }
        try:
            props = json.loads(match.group(1))["props"]["pageProps"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return {
                "status": "unavailable",
                "reason": f"embedded page payload is not parseable: {exc}",
                "page": path,
                "source_url": source_url,
            }
        markdown = props.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            return {
                "status": "unavailable",
                "reason": "embedded payload carries no markdown for this page",
                "page": path,
                "source_url": source_url,
            }
        metadata = props.get("metadata")
        data = metadata.get("data") if isinstance(metadata, Mapping) else None
        data = data if isinstance(data, Mapping) else {}
        toc = props.get("tableOfContentsItems")
        return {
            "status": "ok",
            "page": path,
            "source_url": source_url,
            "title": data.get("pageTitle"),
            "description": data.get("seoDescription"),
            "markdown": markdown,
            "toc": [
                str(item.get("title") or item.get("id") or "")
                for item in toc
                if isinstance(item, Mapping)
            ]
            if isinstance(toc, list)
            else [],
        }

    def list_page_urls(self) -> dict[str, Any]:
        """Return the sitemap-derived corpus of Foundry documentation paths."""
        urls: set[str] = set()
        fetched: list[str] = []
        failures: list[str] = []
        for sitemap_path in SITEMAP_PATHS:
            sitemap_url = f"{self.origin}{sitemap_path}"
            try:
                body = self._fetch(sitemap_url)
            except DocumentationError as exc:
                failures.append(str(exc))
                continue
            fetched.append(sitemap_url)
            urls.update(self._parse_sitemap(body))
        paths = sorted(
            urlparse(url).path[len(DOCS_BASE_PATH) :]
            for url in urls
            if _FOUNDRY_PREFIX in url
            and not any(locale in url for locale in _LOCALE_PREFIXES)
        )
        status = (
            "ok" if paths and not failures else ("partial" if paths else "unavailable")
        )
        return {
            "status": status,
            "page_count": len(paths),
            "pages": paths,
            "sitemaps_fetched": fetched,
            "sitemap_failures": failures,
            "reason": None
            if status != "unavailable"
            else "no sitemap could be retrieved; the corpus is unavailable",
        }

    # -- higher-level workflows ----------------------------------------------

    def summaries(
        self,
        *,
        section: Optional[str] = None,
        with_overviews: bool = False,
        section_limit: int = 50,
        pages_per_section: int = 25,
    ) -> dict[str, Any]:
        """Group the real sitemap corpus into per-section summaries.

        Section names and page lists come verbatim from the sitemap URLs;
        optional overview leads are the real first markdown block of each
        section's ``overview/`` page.
        """
        corpus = self.list_page_urls()
        if corpus["status"] == "unavailable":
            return {**corpus, "sections": None}
        sections: dict[str, list[str]] = {}
        for path in corpus["pages"]:
            parts = [part for part in path.split("/") if part]
            # corpus paths are /foundry/<section>/<page> — the section is the
            # segment after "foundry"
            if len(parts) < 2 or parts[0] != "foundry":
                continue
            sections.setdefault(parts[1], []).append(path)
        if section:
            sections = {section: sections.get(section, [])}
            if not sections[section]:
                return {
                    "status": "not-found",
                    "reason": f"no documentation section named '{section}' in the sitemap corpus",
                    "sections": [],
                    "page_count": corpus["page_count"],
                    "sitemaps_fetched": corpus["sitemaps_fetched"],
                }
        summaries: list[dict[str, Any]] = []
        for name in sorted(sections)[:section_limit]:
            pages = sections[name]
            entry: dict[str, Any] = {
                "section": name,
                "page_count": len(pages),
                "pages": pages[:pages_per_section],
                "pages_truncated": len(pages) > pages_per_section,
            }
            if with_overviews:
                overview = self.fetch_page(f"/foundry/{name}/overview/")
                entry["overview"] = (
                    {
                        "source_url": overview["source_url"],
                        "title": overview.get("title"),
                        "lead": _first_markdown_block(overview["markdown"]),
                    }
                    if overview.get("status") == "ok"
                    else {
                        "status": overview.get("status"),
                        "reason": overview.get("reason"),
                    }
                )
            summaries.append(entry)
        return {
            "status": corpus["status"],
            "page_count": corpus["page_count"],
            "section_count": len(sections),
            "sections": summaries,
            "sitemaps_fetched": corpus["sitemaps_fetched"],
            "sitemap_failures": corpus["sitemap_failures"],
        }

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        fetch_pages: int = 5,
        excerpt_chars: int = 400,
    ) -> dict[str, Any]:
        """Bounded honest search over the real documentation corpus.

        Candidates are sitemap URLs whose slug tokens match the query; the top
        ``fetch_pages`` candidates are fetched and ranked by term frequency in
        their real markdown. Excerpts are verbatim windows around the first
        match. Coverage is explicitly partial: the site's ranked pagefind
        index is WASM-bound and not reproduced here.
        """
        if not query.strip():
            return {
                "status": "invalid",
                "reason": "query must not be empty",
                "results": None,
            }
        corpus = self.list_page_urls()
        if corpus["status"] == "unavailable":
            return {**corpus, "results": None}
        terms = [term.casefold() for term in re.findall(r"[a-z0-9]+", query)]
        candidates = sorted(
            ((self._slug_score(path, terms), path) for path in corpus["pages"]),
            key=lambda item: (-item[0], item[1]),
        )
        scored = [path for score, path in candidates if score > 0]
        results: list[dict[str, Any]] = []
        for path in scored[: max(fetch_pages, 0)]:
            page = self.fetch_page(path)
            if page.get("status") != "ok":
                continue
            body = page["markdown"].casefold()
            hits = sum(body.count(term) for term in terms)
            results.append(
                {
                    "page": path,
                    "source_url": page["source_url"],
                    "title": page.get("title"),
                    "term_hits": hits,
                    "excerpt": _excerpt(page["markdown"], terms, excerpt_chars),
                }
            )
        results.sort(key=lambda item: (-item["term_hits"], item["page"]))
        results = results[:limit]
        return {
            "status": "ok",
            "query": query,
            "results": results,
            "slug_candidates": len(scored),
            "pages_fetched": min(fetch_pages, len(scored)),
            "search_strategy": "slug-token candidates from the docs sitemap, "
            "ranked by term frequency in fetched real page markdown",
            "coverage": "partial",
            "coverage_note": "Palantir's ranked pagefind index is WASM-bound; "
            "this search fetches and ranks a bounded subset of the real corpus",
            "sitemaps_fetched": corpus["sitemaps_fetched"],
        }

    def topic(self, topic_key: str, *, related_limit: int = 25) -> dict[str, Any]:
        """Fetch the curated real pages for one documentation topic."""
        spec = TOPICS.get(topic_key)
        if spec is None:
            return {
                "status": "invalid",
                "reason": f"unknown topic '{topic_key}'",
                "pages": None,
            }
        pages: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for path in spec["pages"]:
            page = self.fetch_page(path)
            if page.get("status") == "ok":
                pages.append(page)
            else:
                failures.append(
                    {
                        "page": path,
                        "status": page.get("status"),
                        "reason": page.get("reason"),
                    }
                )
        corpus = self.list_page_urls()
        prefix = spec["family_prefix"]
        related = (
            [
                path
                for path in corpus.get("pages", [])
                if path.startswith(prefix) and path not in spec["pages"]
            ][:related_limit]
            if corpus.get("status") != "unavailable"
            else []
        )
        status = (
            "ok" if pages and not failures else ("partial" if pages else "unavailable")
        )
        return {
            "status": status,
            "topic": topic_key,
            "title": spec["title"],
            "pages": pages,
            "failures": failures,
            "related_pages": related,
            "reason": None
            if pages
            else "no curated page for this topic could be retrieved",
        }

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _parse_sitemap(body: str) -> Iterable[str]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return []
        return [
            element.text
            for element in root.iter()
            if element.tag.endswith("}loc") and element.text
        ]

    @staticmethod
    def _slug_score(path: str, terms: list[str]) -> int:
        slug_tokens = re.findall(r"[a-z0-9]+", path.casefold())
        return sum(slug_tokens.count(term) for term in terms)


def _first_markdown_block(markdown: str) -> str:
    for block in markdown.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#"):
            return text
    return ""


def _excerpt(markdown: str, terms: list[str], chars: int) -> str:
    lowered = markdown.casefold()
    first = min(
        (lowered.find(term) for term in terms if lowered.find(term) >= 0),
        default=0,
    )
    start = max(first - chars // 3, 0)
    return markdown[start : start + chars].strip()


def extract_code_blocks(markdown: str) -> list[dict[str, str]]:
    """Return the verbatim fenced code blocks of a real documentation page."""
    return [
        {"language": match.group(1).strip(), "code": match.group(2).rstrip("\n")}
        for match in _FENCE_RE.finditer(markdown)
    ]
