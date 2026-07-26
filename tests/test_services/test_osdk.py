"""Tests for the OSDK context/examples service (SDK and network mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pltr.services.osdk import OsdkService, _binding_examples, _summarize_entities


def _ontology(rid="ri.ontology.main.ontology.1", api_name="main"):
    return SimpleNamespace(rid=rid, api_name=api_name, display_name="Main")


def _metadata():
    return SimpleNamespace(
        object_types={"Restaurant": object(), "Review": object()},
        action_types={"addReview": object()},
        query_types={"findSimilar": object()},
        interface_types={},
        shared_property_types={},
        value_types={},
    )


def _service(ontologies=None, metadata=None) -> OsdkService:
    service = OsdkService()
    client = MagicMock()
    ontology_api = client.ontologies.Ontology
    if ontologies is not None:
        ontology_api.list.return_value = SimpleNamespace(data=ontologies)
    ontology_api.get.return_value = ontologies[0] if ontologies else _ontology()
    ontology_api.get_full_metadata.return_value = (
        metadata if metadata is not None else _metadata()
    )
    service._client = client
    return service


class TestSdkContext:
    def test_single_visible_ontology(self):
        result = _service(ontologies=[_ontology()]).sdk_context()
        assert result["status"] == "ok"
        assert result["ontology"]["rid"] == "ri.ontology.main.ontology.1"
        assert result["entities"]["object_types"]["count"] == 2
        assert result["entities"]["object_types"]["names"] == [
            "Restaurant",
            "Review",
        ]
        assert result["osdk"]["packages"][0]["name"] == "@osdk/foundry.ontologies"
        assert "OntologyV2" in result["osdk"]["components"]
        assert result["sources"]

    def test_explicit_ontology(self):
        service = _service(ontologies=[_ontology()])
        result = service.sdk_context("ri.ontology.main.ontology.1")
        assert result["status"] == "ok"
        service.client.ontologies.Ontology.get.assert_called_once_with(
            "ri.ontology.main.ontology.1"
        )

    def test_ambiguous_ontology_not_guessed(self):
        result = _service(
            ontologies=[_ontology(), _ontology(rid="ri.ontology.main.ontology.2")]
        ).sdk_context()
        assert result["status"] == "ambiguous"
        assert len(result["choices"]) == 2

    def test_no_visible_ontology(self):
        result = _service(ontologies=[]).sdk_context()
        assert result["status"] == "unavailable"

    def test_metadata_failure_is_unavailable(self):
        service = _service(ontologies=[_ontology()])
        service.client.ontologies.Ontology.get_full_metadata.side_effect = RuntimeError(
            "boom"
        )
        result = service.sdk_context()
        assert result["status"] == "unavailable"
        assert "boom" in result["reason"]


class _FakeDocs:
    def __init__(self, page):
        self._page = page

    def fetch_page(self, path):
        return self._page


GOOD_PAGE = {
    "status": "ok",
    "source_url": "https://www.palantir.com/docs/foundry/ontology-sdk/typescript-osdk/",
    "markdown": "text\n```typescript\nconst page = await client(Restaurant).fetchPage();\n```\n",
}


class TestSdkExamples:
    def test_verbatim_doc_examples_and_generated_bindings(self):
        result = _service(ontologies=[_ontology()]).sdk_examples(
            docs=_FakeDocs(GOOD_PAGE)
        )
        assert result["status"] == "ok"
        doc_examples = result["documentation_examples"]
        assert doc_examples[0]["code"] == (
            "const page = await client(Restaurant).fetchPage();"
        )
        assert doc_examples[0]["source"] == "palantir-docs"
        bindings = result["binding_examples"]
        assert bindings
        assert all(binding["generated"] is True for binding in bindings)
        kinds = {binding["kind"] for binding in bindings}
        assert kinds == {"object-fetch", "action-apply", "query-execute"}
        assert any(
            "client(Restaurant).fetchPage()" in binding["code"] for binding in bindings
        )

    def test_python_generates_only_verified_object_bindings(self):
        result = _service(ontologies=[_ontology()]).sdk_examples(
            language="python", docs=_FakeDocs(GOOD_PAGE)
        )
        assert result["status"] == "ok"
        kinds = {binding["kind"] for binding in result["binding_examples"]}
        assert kinds == {"object-fetch"}
        assert any(
            "client.ontology.objects.Restaurant.page()" in binding["code"]
            for binding in result["binding_examples"]
        )

    def test_ontology_failure_still_returns_docs_examples(self):
        service = _service()
        service.client.ontologies.Ontology.list.side_effect = RuntimeError("auth")
        result = service.sdk_examples(docs=_FakeDocs(GOOD_PAGE))
        assert result["status"] == "ok"
        assert result["ontology"] is None
        assert result["binding_examples"] == []
        assert result["documentation_examples"]
        assert result["warnings"]

    def test_docs_failure_with_live_bindings_still_ok(self):
        bad_page = {"status": "unavailable", "reason": "404"}
        result = _service(ontologies=[_ontology()]).sdk_examples(
            docs=_FakeDocs(bad_page)
        )
        assert result["status"] == "ok"
        assert result["documentation_examples"] == []
        assert result["binding_examples"]

    def test_invalid_language(self):
        result = _service().sdk_examples(language="java")
        assert result["status"] == "invalid"


def test_summarize_entities_truncates():
    metadata = SimpleNamespace(
        object_types={f"Type{i}": object() for i in range(10)},
        action_types={},
        query_types={},
        interface_types={},
        shared_property_types={},
        value_types={},
    )
    summary = _summarize_entities(metadata, limit=3)
    assert summary["object_types"]["count"] == 10
    assert len(summary["object_types"]["names"]) == 3
    assert summary["object_types"]["truncated"] is True


def test_binding_examples_empty_entities():
    assert _binding_examples({}, "typescript") == []
