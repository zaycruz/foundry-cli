"""CLI-native extension tools for the AI FDE agent loop.

These are NOT part of the captured 72-tool AI FDE catalog. They are
pfoundry-native synthetic tools (``cliExtension`` in the loop registry)
added because two live runs proved the captured catalog cannot answer
"show me the most recent runs of the <name> pipeline": the catalog has
no name-search tool (Palantir's design relies on UI @-mentions) and no
build-history/dataset-transaction tool at all.

Every executor wraps an already-verified pfoundry surface — public
Foundry SDK contracts or existing service wrappers; no reverse-engineered
contracts here:

- ``pfoundry_search_resources`` wraps ``SearchService.search`` (the
  pinned GraphQL ``SearchTitles`` query behind ``pfoundry search``).
- ``pfoundry_search_builds`` wraps ``OrchestrationService.search_builds``
  (SDK ``Build.search``) and ``OrchestrationService.get_build_jobs``
  (SDK ``Build.jobs``). Two SDK constraints shape the design: ``where``
  is REQUIRED (a no-filter search is expressed as
  ``gte STARTED_TIME epoch``), and the filter vocabulary has no dataset
  member (eq: CREATED_BY/BRANCH_NAME/STATUS/RID; gte/lt:
  STARTED_TIME/FINISHED_TIME), so ``datasetRid`` filtering scans recent
  builds newest-first and keeps those whose ``Build.jobs`` outputs
  include the dataset RID (``DatasetJobOutput.dataset_rid``), bounded by
  ``_DATASET_SCAN_*`` below and reported honestly in the result.
- ``pfoundry_get_dataset_transactions`` wraps
  ``DatasetService.get_transactions`` /
  ``DatasetService.get_branch_transactions`` (SDK ``Dataset.transactions``
  / ``Dataset.Branch.transactions``); ``limit`` is applied client-side to
  the SDK-returned order.
- ``pfoundry_get_resource`` wraps ``ResourceService.get_resource`` (SDK
  ``filesystem.Resource.get``).

All extension tools are read-risk and always exposed (not mode-gated).
Specs are hand-written by us (the captured catalog is verbatim-only).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from .dataset import DatasetService
from .orchestration import OrchestrationService
from .resource import ResourceService
from .search import SearchService

EXTENSION_TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "pfoundry_search_resources": {
        "function": {
            "name": "pfoundry_search_resources",
            "description": (
                "CLI extension (not a captured AI FDE tool): search Foundry "
                "resources by title to resolve a NAME to its RID. Use this "
                "whenever the user names a dataset, pipeline, repository, "
                "code repo, ontology object type, evaluation suite, or other "
                "resource without giving its RID."
            ),
            "parameters": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Title text to search for.",
                    },
                    "limit": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": (
                            "Max results (default 25). The search has no page "
                            "token; results are capped at this limit and the "
                            "server does not report whether more matches "
                            "exist."
                        ),
                    },
                },
                "required": ["query", "limit"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        "type": "function",
    },
    "pfoundry_search_builds": {
        "function": {
            "name": "pfoundry_search_builds",
            "description": (
                "CLI extension (not a captured AI FDE tool): search recent "
                "builds (pipeline runs), newest first. Filter by branch "
                "and/or start time, or by the dataset a build produced "
                "(datasetRid). Use this to answer 'show me the most recent "
                "runs of pipeline/dataset X' after resolving X's dataset RID."
            ),
            "parameters": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "datasetRid": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": (
                            "Only keep builds whose jobs output this dataset "
                            "RID (e.g. ri.foundry.main.dataset.<uuid>). "
                            "Resolved client-side by scanning recent builds "
                            "and their jobs; the result reports how many "
                            "builds were scanned."
                        ),
                    },
                    "branch": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": ("Branch name to filter on (e.g. 'master')."),
                    },
                    "createdAfter": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": (
                            "ISO-8601 timestamp; only builds started at or "
                            "after this time are searched."
                        ),
                    },
                    "limit": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Max builds to return (default 10).",
                    },
                },
                "required": ["datasetRid", "branch", "createdAfter", "limit"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        "type": "function",
    },
    "pfoundry_get_dataset_transactions": {
        "function": {
            "name": "pfoundry_get_dataset_transactions",
            "description": (
                "CLI extension (not a captured AI FDE tool): list a dataset's "
                "transaction history (status, type, branch, created/committed "
                "times) — the record of what changed the dataset and when."
            ),
            "parameters": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "datasetRid": {
                        "type": "string",
                        "description": "Dataset RID (ri.foundry.main.dataset.<uuid>).",
                    },
                    "branch": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": (
                            "Branch name; when given, transactions are listed "
                            "for that branch only."
                        ),
                    },
                    "limit": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": (
                            "Max transactions to return (default 20), applied "
                            "to the SDK-returned order."
                        ),
                    },
                },
                "required": ["datasetRid", "branch", "limit"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        "type": "function",
    },
    "pfoundry_get_resource": {
        "function": {
            "name": "pfoundry_get_resource",
            "description": (
                "CLI extension (not a captured AI FDE tool): get Compass "
                "resource metadata (name, path, type, timestamps) for one RID."
            ),
            "parameters": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "rid": {
                        "type": "string",
                        "description": "The resource RID to load.",
                    },
                },
                "required": ["rid"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        "type": "function",
    },
}

EXTENSION_TOOL_NAMES: tuple[str, ...] = tuple(EXTENSION_TOOL_SPECS)

# Bounds for the datasetRid scan (SDK Build.search has no dataset filter).
_DATASET_SCAN_PAGES = 5
_DATASET_SCAN_PAGE_SIZE = 50
_DEFAULT_BUILD_LIMIT = 10
_DEFAULT_TRANSACTION_LIMIT = 20
_DEFAULT_SEARCH_LIMIT = 25
_EPOCH_ISO = "1970-01-01T00:00:00Z"


class ExtensionToolExecutor:
    """Execute the CLI-native extension tools against pfoundry services."""

    def __init__(
        self,
        profile: Optional[str] = None,
        *,
        search_service: Optional[Any] = None,
        orchestration_service: Optional[Any] = None,
        dataset_service: Optional[Any] = None,
        resource_service: Optional[Any] = None,
    ) -> None:
        self.profile = profile
        self._search_service = search_service
        self._orchestration_service = orchestration_service
        self._dataset_service = dataset_service
        self._resource_service = resource_service

    def _search(self) -> Any:
        if self._search_service is None:
            self._search_service = SearchService(profile=self.profile)
        return self._search_service

    def _orchestration(self) -> Any:
        if self._orchestration_service is None:
            self._orchestration_service = OrchestrationService(profile=self.profile)
        return self._orchestration_service

    def _dataset(self) -> Any:
        if self._dataset_service is None:
            self._dataset_service = DatasetService(profile=self.profile)
        return self._dataset_service

    def _resource(self) -> Any:
        if self._resource_service is None:
            self._resource_service = ResourceService(profile=self.profile)
        return self._resource_service

    def execute(self, name: str, args: Mapping[str, Any]) -> str:
        """Run one extension tool; return the tool output payload."""
        executor = getattr(self, f"_exec_{name.removeprefix('pfoundry_')}", None)
        if executor is None:
            raise ValueError(f"unknown extension tool: {name}")
        return executor(args)

    @staticmethod
    def _int_arg(args: Mapping[str, Any], key: str, default: int) -> int:
        value = args.get(key)
        if value is None:
            return default
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"'{key}' must be a positive integer, got {value!r}")
        return value

    def _exec_search_resources(self, args: Mapping[str, Any]) -> str:
        query = args.get("query")
        if not isinstance(query, str) or not query:
            raise ValueError("pfoundry_search_resources requires a string 'query'")
        limit = self._int_arg(args, "limit", _DEFAULT_SEARCH_LIMIT)
        payload = self._search().search(query, limit=limit)
        return json.dumps(payload, indent=1, default=str)

    def _exec_search_builds(self, args: Mapping[str, Any]) -> str:
        limit = self._int_arg(args, "limit", _DEFAULT_BUILD_LIMIT)
        branch = args.get("branch")
        created_after = args.get("createdAfter")
        dataset_rid = args.get("datasetRid")
        filters: List[Dict[str, Any]] = [
            {
                "type": "gte",
                "field": "STARTED_TIME",
                "value": created_after
                if isinstance(created_after, str)
                else _EPOCH_ISO,
            }
        ]
        if isinstance(branch, str) and branch:
            filters.append({"type": "eq", "field": "BRANCH_NAME", "value": branch})
        where: Dict[str, Any] = (
            filters[0] if len(filters) == 1 else {"type": "and", "items": filters}
        )
        order_by = {"fields": [{"field": "STARTED_TIME", "direction": "DESC"}]}
        service = self._orchestration()
        if not (isinstance(dataset_rid, str) and dataset_rid):
            payload = service.search_builds(
                page_size=limit, where=where, order_by=order_by
            )
            return json.dumps(
                {
                    "builds": payload.get("builds", []),
                    "next_page_token": payload.get("next_page_token"),
                    "where": where,
                },
                indent=1,
                default=str,
            )
        # datasetRid: no server-side filter exists, so scan recent builds
        # newest-first and keep those whose job outputs include the dataset.
        matches: List[Dict[str, Any]] = []
        scanned = 0
        page_token: Optional[str] = None
        for _ in range(_DATASET_SCAN_PAGES):
            if len(matches) >= limit:
                break
            page = service.search_builds(
                page_size=_DATASET_SCAN_PAGE_SIZE,
                page_token=page_token,
                where=where,
                order_by=order_by,
            )
            builds = page.get("builds", [])
            if not builds:
                break
            for build in builds:
                if len(matches) >= limit:
                    break
                scanned += 1
                build_rid = build.get("rid")
                if not isinstance(build_rid, str):
                    continue
                jobs = service.get_build_jobs(build_rid)
                matching_outputs = _dataset_outputs(jobs, dataset_rid)
                if matching_outputs:
                    matches.append(
                        {**build, "matching_dataset_outputs": matching_outputs}
                    )
            page_token = page.get("next_page_token")
            if not page_token:
                break
        return json.dumps(
            {
                "builds": matches,
                "dataset_rid": dataset_rid,
                "builds_scanned": scanned,
                "scan_note": (
                    "datasetRid filtering is client-side over recent builds "
                    f"(up to {_DATASET_SCAN_PAGES}x{_DATASET_SCAN_PAGE_SIZE}); "
                    "older matching builds may exist beyond the scan"
                ),
                "where": where,
            },
            indent=1,
            default=str,
        )

    def _exec_get_dataset_transactions(self, args: Mapping[str, Any]) -> str:
        dataset_rid = args.get("datasetRid")
        if not isinstance(dataset_rid, str) or not dataset_rid:
            raise ValueError(
                "pfoundry_get_dataset_transactions requires a string 'datasetRid'"
            )
        limit = self._int_arg(args, "limit", _DEFAULT_TRANSACTION_LIMIT)
        branch = args.get("branch")
        service = self._dataset()
        if isinstance(branch, str) and branch:
            transactions = service.get_branch_transactions(dataset_rid, branch)
        else:
            transactions = service.get_transactions(dataset_rid)
        return json.dumps(
            {
                "dataset_rid": dataset_rid,
                "branch": branch,
                "total_count": len(transactions),
                "returned_count": min(limit, len(transactions)),
                "ordering_note": "transaction order is the SDK's return order",
                "transactions": transactions[:limit],
            },
            indent=1,
            default=str,
        )

    def _exec_get_resource(self, args: Mapping[str, Any]) -> str:
        rid = args.get("rid")
        if not isinstance(rid, str) or not rid:
            raise ValueError("pfoundry_get_resource requires a string 'rid'")
        payload = self._resource().get_resource(rid)
        return json.dumps(payload, indent=1, default=str)


def _dataset_outputs(jobs_payload: Mapping[str, Any], dataset_rid: str) -> List[Any]:
    """Extract job outputs that reference ``dataset_rid``."""
    matches: List[Any] = []
    jobs = jobs_payload.get("jobs")
    for job in jobs if isinstance(jobs, list) else []:
        if not isinstance(job, Mapping):
            continue
        outputs = job.get("outputs")
        for output in outputs if isinstance(outputs, list) else []:
            if isinstance(output, Mapping) and output.get("dataset_rid") == dataset_rid:
                matches.append(
                    {
                        "job_rid": job.get("rid"),
                        "job_status": job.get("job_status") or job.get("status"),
                        "output": output,
                    }
                )
    return matches


__all__ = [
    "EXTENSION_TOOL_NAMES",
    "EXTENSION_TOOL_SPECS",
    "ExtensionToolExecutor",
]
