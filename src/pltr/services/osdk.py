"""Ontology SDK (OSDK) context and examples.

Context is derived from two clearly-labeled sources:

1. The live ontology, read through the installed ``foundry-platform-sdk``
   (``ontologies.Ontology.list`` / ``Ontology.get_full_metadata``) — real
   entity names and counts for the caller's stack.
2. Vendored OSDK package type declarations (see ``_VENDORED_*`` provenance
   constants) — the real published ``@osdk/foundry.ontologies`` API surface.

Examples are verbatim fenced code blocks extracted from Palantir's public
OSDK documentation pages (via :class:`DocumentationService`), plus binding
snippets generated from live ontology entity names and explicitly marked
``generated: true``. No content is fabricated.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseService
from .documentation import DocumentationService, extract_code_blocks

# Provenance: the captured contract,
# extracted from build/esm/public/*.d.ts (package
# @osdk/foundry.ontologies@2.69.0, repo palantir/foundry-platform-typescript).
# The mapping is the package's real declared public API functions.
_VENDORED_OSDK_PACKAGE = {
    "name": "@osdk/foundry.ontologies",
    "version": "2.69.0",
    "provenance": "the captured contract "
    "(build/esm/public/*.d.ts)",
}
_VENDORED_MAKER_PACKAGE = {
    "name": "@osdk/maker",
    "version": "0.51.0",
    "provenance": "the captured contract",
}
_OSDK_COMPONENTS: dict[str, list[str]] = {
    "Action": ["apply", "applyAsync", "applyBatch", "applyWithOverrides", "applyBatchWithOverrides"],
    "ActionTypeFullMetadata": ["list", "get"],
    "ActionTypeV2": ["list", "search", "get", "getByRid", "getByRidBatch"],
    "Attachment": ["upload", "uploadWithRid", "read", "get"],
    "AttachmentPropertyV2": ["getAttachment", "getAttachmentByRid", "readAttachment", "readAttachmentByRid"],
    "CipherTextProperty": ["decrypt", "encryptWithDefaultChannel", "encrypt"],
    "GeotemporalSeriesProperty": ["loadGeotemporalSeriesEntries"],
    "LinkedObjectV2": ["listLinkedObjects", "getLinkedObject"],
    "MediaReferenceProperty": ["getMediaContent", "getMediaMetadata", "upload"],
    "ObjectTypeV2": ["list", "get", "getByRidBatch", "getFullMetadata", "getEditsHistory", "listOutgoingLinkTypes", "getOutgoingLinkType", "getOutgoingLinkTypesByObjectTypeRidBatch"],
    "OntologyInterface": ["list", "get", "listObjectsForInterface", "search", "aggregate", "listOutgoingInterfaceLinkTypes", "getOutgoingInterfaceLinkType", "listInterfaceLinkedObjects"],
    "OntologyObjectSet": ["createTemporary", "get", "load", "loadMultipleObjectTypes", "loadObjectsOrInterfaces", "aggregate", "loadLinks"],
    "OntologyObjectV2": ["list", "get", "count", "search", "aggregate"],
    "OntologyScenario": ["createScenario", "listScenarioEditedObjectTypes", "listScenarioEditedLinkTypes", "listScenarioEditedEntityTypes", "listScenarioEditedObjects", "listScenarioEditedLinks", "listScenarioConflictingObjects"],
    "OntologyTransaction": ["postEdits"],
    "OntologyV2": ["list", "get", "getFullMetadata", "loadMetadata"],
    "OntologyValueType": ["get", "list"],
    "Query": ["execute"],
    "QueryType": ["list", "get", "getByRidBatch"],
    "TimeSeriesPropertyV2": ["getFirstPoint", "getLastPoint", "streamPoints"],
    "TimeSeriesValueBankProperty": ["getLatestValue", "streamValues"],
}

# Official OSDK documentation pages whose real code blocks are quoted.
_OSDK_DOC_PAGES = {
    "typescript": "/foundry/ontology-sdk/typescript-osdk/",
    "python": "/foundry/ontology-sdk/python-osdk/",
}

_ENTITY_NAME_LIMIT = 50


class OsdkService(BaseService):
    """Assemble OSDK codegen context from the live ontology and OSDK packages."""

    def _get_service(self) -> Any:
        """Get the Foundry ontologies service."""
        return self.client.ontologies

    # -- context ------------------------------------------------------------

    def sdk_context(self, ontology: Optional[str] = None) -> dict[str, Any]:
        """Return OSDK codegen context for one ontology.

        ``ontology`` is an ontology RID or API name; when omitted, the single
        visible ontology is used and ambiguity is reported rather than guessed.
        """
        resolution = self._resolve_ontology(ontology)
        if resolution["status"] != "ok":
            return resolution
        rid = resolution["ontology"]["rid"]
        try:
            metadata = self.service.Ontology.get_full_metadata(rid)
        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": f"full ontology metadata read failed: {exc}",
                "ontology": resolution["ontology"],
            }
        return {
            "status": "ok",
            "ontology": resolution["ontology"],
            "entities": _summarize_entities(metadata),
            "osdk": {
                "packages": [_VENDORED_OSDK_PACKAGE, _VENDORED_MAKER_PACKAGE],
                "components": _OSDK_COMPONENTS,
                "docs": {lang: f"https://www.palantir.com/docs{path}"
                         for lang, path in _OSDK_DOC_PAGES.items()},
            },
            "sources": [
                "live ontology via foundry-platform-sdk "
                "ontologies.Ontology.get_full_metadata",
                _VENDORED_OSDK_PACKAGE["provenance"],
            ],
        }

    # -- examples -------------------------------------------------------------

    def sdk_examples(
        self,
        ontology: Optional[str] = None,
        *,
        language: str = "typescript",
        docs: Optional[DocumentationService] = None,
        entity_limit: int = 5,
    ) -> dict[str, Any]:
        """Return real OSDK usage examples plus live-ontology bindings.

        ``documentation_examples`` are verbatim code blocks from Palantir's
        public OSDK docs. ``binding_examples`` are generated from real live
        entity names and are each marked ``generated: true``.
        """
        if language not in _OSDK_DOC_PAGES:
            return {
                "status": "invalid",
                "reason": f"language must be one of {sorted(_OSDK_DOC_PAGES)}",
            }
        resolution = self._resolve_ontology(ontology)
        entities: dict[str, Any] = {}
        ontology_info: Optional[dict[str, Any]] = None
        warnings: list[str] = []
        if resolution["status"] == "ok":
            ontology_info = resolution["ontology"]
            try:
                metadata = self.service.Ontology.get_full_metadata(
                    ontology_info["rid"]
                )
                entities = _summarize_entities(metadata, limit=entity_limit)
            except Exception as exc:
                warnings.append(
                    f"live entity read failed; bindings omitted: {exc}"
                )
        else:
            warnings.append(
                f"live ontology unavailable ({resolution.get('reason')}); "
                "returning documentation examples only"
            )

        docs_service = docs or DocumentationService()
        doc_path = _OSDK_DOC_PAGES[language]
        page = docs_service.fetch_page(doc_path)
        documentation_examples: list[dict[str, Any]] = []
        if page.get("status") == "ok":
            documentation_examples = [
                {
                    **block,
                    "source": "palantir-docs",
                    "source_url": page["source_url"],
                }
                for block in extract_code_blocks(page["markdown"])
            ]
        else:
            warnings.append(
                f"OSDK documentation page unavailable: {page.get('reason')}"
            )

        binding_examples = _binding_examples(entities, language)
        status = "ok" if (documentation_examples or binding_examples) else "unavailable"
        return {
            "status": status,
            "language": language,
            "ontology": ontology_info,
            "documentation_examples": documentation_examples,
            "binding_examples": binding_examples,
            "warnings": warnings,
            "reason": None
            if status == "ok"
            else "neither documentation examples nor live bindings could be produced",
        }

    # -- helpers ---------------------------------------------------------------

    def _resolve_ontology(self, ontology: Optional[str]) -> dict[str, Any]:
        try:
            if ontology:
                found = self.service.Ontology.get(ontology)
                return {
                    "status": "ok",
                    "ontology": {
                        "rid": found.rid,
                        "api_name": getattr(found, "api_name", None),
                        "display_name": getattr(found, "display_name", None),
                    },
                }
            result = self.service.Ontology.list()
            ontologies = list(result.data)
        except Exception as exc:
            return {"status": "unavailable", "reason": f"ontology read failed: {exc}"}
        if not ontologies:
            return {
                "status": "unavailable",
                "reason": "no ontologies are visible to the current user",
            }
        if len(ontologies) > 1:
            return {
                "status": "ambiguous",
                "reason": "multiple ontologies are visible; pass one explicitly "
                "rather than letting the CLI guess",
                "choices": [
                    {
                        "rid": item.rid,
                        "api_name": getattr(item, "api_name", None),
                    }
                    for item in ontologies
                ],
            }
        only = ontologies[0]
        return {
            "status": "ok",
            "ontology": {
                "rid": only.rid,
                "api_name": getattr(only, "api_name", None),
                "display_name": getattr(only, "display_name", None),
            },
        }


def _summarize_entities(
    metadata: Any, *, limit: int = _ENTITY_NAME_LIMIT
) -> dict[str, Any]:
    """Summarize real entity names/counts from an OntologyFullMetadata model."""

    def names(mapping: Any) -> tuple[int, list[str]]:
        if not isinstance(mapping, dict):
            return 0, []
        keys = sorted(str(key) for key in mapping)
        return len(keys), keys[:limit]

    summary: dict[str, Any] = {}
    for field in (
        "object_types",
        "action_types",
        "query_types",
        "interface_types",
        "shared_property_types",
        "value_types",
    ):
        total, sample = names(getattr(metadata, field, None))
        summary[field] = {
            "count": total,
            "names": sample,
            "truncated": total > len(sample),
        }
    return summary


def _binding_examples(
    entities: dict[str, Any], language: str
) -> list[dict[str, Any]]:
    """Generate binding snippets from REAL live entity names.

    Every snippet is marked ``generated: true`` and cites the OSDK docs page
    its API pattern follows, so nothing here masquerades as Palantir-authored
    content.
    """
    object_names = (entities.get("object_types") or {}).get("names") or []
    action_names = (entities.get("action_types") or {}).get("names") or []
    query_names = (entities.get("query_types") or {}).get("names") or []
    docs_url = f"https://www.palantir.com/docs{_OSDK_DOC_PAGES[language]}"
    examples: list[dict[str, Any]] = []
    if language == "typescript":
        # Patterns verified against the verbatim code blocks of the
        # official TypeScript OSDK docs page (see pattern_reference).
        for name in object_names:
            examples.append(
                {
                    "kind": "object-fetch",
                    "entity": name,
                    "code": f"const page = await client({name}).fetchPage();",
                }
            )
        for name in action_names:
            examples.append(
                {
                    "kind": "action-apply",
                    "entity": name,
                    "code": f"const result = await client({name}).applyAction({{ /* parameters */ }});",
                }
            )
        for name in query_names:
            examples.append(
                {
                    "kind": "query-execute",
                    "entity": name,
                    "code": f"const result = await client({name}).executeFunction({{ /* parameters */ }});",
                }
            )
    else:
        # The official Python OSDK docs page only demonstrates object access
        # (verified); action/query bindings are not generated for
        # python because their API shape is unverified locally.
        for name in object_names:
            examples.append(
                {
                    "kind": "object-fetch",
                    "entity": name,
                    "code": f"page = client.ontology.objects.{name}.page()",
                }
            )
    for example in examples:
        example["generated"] = True
        example["source"] = "generated-from-live-ontology"
        example["pattern_reference"] = docs_url
    return examples
