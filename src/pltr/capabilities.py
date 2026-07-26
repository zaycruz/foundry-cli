"""Versioned capability manifest for the native, agent-first Foundry CLI."""

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Iterable, Mapping, Optional, Sequence


CAPABILITY_SCHEMA_VERSION = "foundry-agent-capabilities-v1"
CATALOG_VERSION = "palantir-mcp-available-tools-2026-07-20"
CATALOG_SOURCE_URL = (
    "https://www.palantir.com/docs/foundry/palantir-mcp/available-tools/"
)
CATALOG_RETRIEVED_ON = "2026-07-20"
VALID_KINDS = frozenset({"tool", "workflow"})
VALID_STATUSES = frozenset({"planned", "implemented", "blocked", "unsupported"})
VALID_MUTATION_RISKS = frozenset({"read", "write", "destructive"})


class ManifestValidationError(ValueError):
    """Raised when the capability manifest violates its contract."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class CapabilitySpec:
    """One native CLI capability and its parity evidence."""

    capability_id: str
    kind: str
    group: str
    command: str
    service: str
    api_evidence: str
    status: str
    mutation_risk: str
    output_contract: str
    test_reference: str
    blocked_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Return the stable serialized representation."""
        return asdict(self)


# These IDs are the exact tool rows from the 2026-07-20 parity baseline.
_TOOL_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "compass",
        "list_resources_in_foundry_folder",
        "resource list",
        "ResourceService",
        "official-catalog",
    ),
    (
        "compass",
        "get_project_imports",
        "project imports",
        "ProjectService",
        "official-catalog",
    ),
    (
        "compass",
        "list_foundry_namespaces",
        "namespace list",
        "CompassService",
        "official-catalog",
    ),
    (
        "compass",
        "list_foundry_project_templates",
        "project templates list",
        "CompassService",
        "official-catalog",
    ),
    (
        "compass",
        "create_foundry_project",
        "project create",
        "ProjectService",
        "official-catalog",
    ),
    (
        "compass",
        "search_foundry_projects",
        "project search",
        "ProjectService",
        "official-catalog",
    ),
    (
        "dataset",
        "get_foundry_dataset_schema",
        "dataset schema get",
        "DatasetService",
        "official-catalog",
    ),
    (
        "dataset",
        "run_sql_query_on_foundry_dataset",
        "sql execute",
        "SqlService",
        "official-catalog",
    ),
    (
        "dataset",
        "create_and_write_to_foundry_dataset",
        "dataset create",
        "DatasetService",
        "official-catalog",
    ),
    (
        "dataset",
        "list_dataset_files",
        "dataset files list",
        "DatasetService",
        "official-catalog",
    ),
    (
        "dataset",
        "build_datasets",
        "orchestration builds create",
        "OrchestrationService",
        "official-catalog",
    ),
    (
        "dataset",
        "get_build_status",
        "orchestration builds get",
        "OrchestrationService",
        "official-catalog",
    ),
    (
        "dataset",
        "search_dataset_builds",
        "orchestration builds search",
        "OrchestrationService",
        "official-catalog",
    ),
    (
        "dataset",
        "get_job_status",
        "orchestration jobs get",
        "OrchestrationService",
        "official-catalog",
    ),
    (
        "dataset",
        "get_dataset_stats",
        "dataset stats",
        "DatasetService",
        "official-catalog",
    ),
    (
        "data-lineage",
        "get_resource_graph",
        "lineage graph",
        "LineageService",
        "official-catalog",
    ),
    (
        "ontology",
        "get_foundry_ontology_rid",
        "ontology rid",
        "OntologyService",
        "official-catalog",
    ),
    (
        "ontology",
        "search_foundry_ontology",
        "ontology object-search",
        "OntologyService",
        "official-catalog",
    ),
    (
        "ontology",
        "search_foundry_functions",
        "functions search",
        "FunctionsService",
        "official-catalog",
    ),
    (
        "ontology",
        "view_foundry_object_type",
        "ontology object-type-get",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "create_or_update_foundry_object_type",
        "ontology object-type-upsert",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "delete_foundry_object_type",
        "ontology object-type-delete",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "view_foundry_link_type",
        "ontology link-type-get",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "create_or_update_foundry_link_type",
        "ontology link-type-upsert",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "delete_foundry_link_type",
        "ontology link-type-delete",
        "ObjectTypeService",
        "official-catalog",
    ),
    (
        "ontology",
        "view_foundry_action_type",
        "ontology action-type-get",
        "ActionService",
        "official-catalog",
    ),
    (
        "ontology",
        "create_or_update_foundry_action_type",
        "ontology action-type-upsert",
        "ActionService",
        "official-catalog",
    ),
    (
        "ontology",
        "delete_foundry_action_type",
        "ontology action-type-delete",
        "ActionService",
        "official-catalog",
    ),
    (
        "object-set",
        "query_ontology_objects",
        "ontology query-execute",
        "OntologyObjectService",
        "official-catalog",
    ),
    (
        "object-set",
        "aggregate_ontology_objects",
        "ontology object-aggregate",
        "OntologyObjectService",
        "official-catalog",
    ),
    (
        "osdk",
        "get_ontology_sdk_context",
        "osdk context",
        "OsdkService",
        "official-catalog",
    ),
    (
        "osdk",
        "get_ontology_sdk_examples",
        "osdk examples",
        "OsdkService",
        "official-catalog",
    ),
    (
        "platform-sdk",
        "list_platform_sdk_apis",
        "platform-sdk api list",
        "PlatformSdkService",
        "official-catalog",
    ),
    (
        "platform-sdk",
        "get_platform_sdk_api_reference",
        "platform-sdk api reference",
        "PlatformSdkService",
        "official-catalog",
    ),
    (
        "code-repository",
        "get_repository_context",
        "repository context",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "create_python_transforms_code_repository",
        "repository create-python-transforms",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "clone_code_repository_locally",
        "repository clone",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "create_code_repository_pull_request",
        "repository pull-request create",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "list_code_repository_pull_requests",
        "repository pull-request list",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "get_code_repository_pull_request",
        "repository pull-request get",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "code-repository",
        "create_code_repository_pull_request_comment",
        "repository pull-request comment",
        "RepositoryService",
        "official-catalog",
    ),
    (
        "global-branching",
        "create_global_branch",
        "global-branch create",
        "GlobalBranchService",
        "official-catalog",
    ),
    (
        "global-branching",
        "view_global_branch",
        "global-branch get",
        "GlobalBranchService",
        "official-catalog",
    ),
    (
        "global-branching",
        "close_global_branch",
        "global-branch close",
        "GlobalBranchService",
        "official-catalog",
    ),
    (
        "global-branching",
        "create_global_proposal",
        "global-proposal create",
        "GlobalProposalService",
        "official-catalog",
    ),
    (
        "global-branching",
        "view_global_proposal",
        "global-proposal get",
        "GlobalProposalService",
        "official-catalog",
    ),
    (
        "global-branching",
        "close_global_proposal",
        "global-proposal close",
        "GlobalProposalService",
        "official-catalog",
    ),
    (
        "developer-console",
        "connect_to_dev_console_app",
        "dev-console connect",
        "DeveloperConsoleService",
        "official-catalog",
    ),
    (
        "developer-console",
        "convert_to_osdk_react",
        "dev-console convert-osdk-react",
        "DeveloperConsoleService",
        "official-catalog",
    ),
    (
        "developer-console",
        "generate_new_ontology_sdk_version",
        "dev-console sdk generate",
        "DeveloperConsoleService",
        "official-catalog",
    ),
    (
        "developer-console",
        "install_sdk_package",
        "dev-console sdk install",
        "DeveloperConsoleService",
        "official-catalog",
    ),
    (
        "developer-console",
        "view_osdk_definition",
        "dev-console osdk definition",
        "DeveloperConsoleService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_compute_modules_documentation",
        "docs compute",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "compute",
        "get_compute_modules_info",
        "compute info",
        "ComputeService",
        "official-catalog",
    ),
    (
        "compute",
        "get_compute_modules_logs",
        "compute logs",
        "ComputeService",
        "official-catalog",
    ),
    (
        "compute",
        "manage_compute_modules",
        "compute manage",
        "ComputeService",
        "official-catalog",
    ),
    (
        "compute",
        "execute_compute_modules_function",
        "compute execute",
        "ComputeService",
        "official-catalog",
    ),
    (
        "data-connection",
        "create_foundry_rest_api_data_source",
        "connectivity rest-source create",
        "DataConnectionService",
        "official-catalog",
    ),
    (
        "data-connection",
        "create_foundry_rest_api_data_source_webhook",
        "connectivity webhook create",
        "DataConnectionService",
        "official-catalog",
    ),
    (
        "data-connection",
        "update_foundry_rest_api_data_source_webhook",
        "connectivity webhook update",
        "DataConnectionService",
        "official-catalog",
    ),
    (
        "data-connection",
        "view_foundry_rest_api_data_source_webhook",
        "connectivity webhook get",
        "DataConnectionService",
        "official-catalog",
    ),
    (
        "data-connection",
        "get_or_create_network_egress_policy",
        "connectivity egress ensure",
        "DataConnectionService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_python_transforms_documentation",
        "docs python-transforms",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_typescript_v1_functions_documentation",
        "docs typescript-v1-functions",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_typescript_v2_functions_documentation",
        "docs typescript-v2-functions",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_custom_widget_documentation",
        "docs custom-widgets",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_ml_documentation",
        "docs ml",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_spark_profile_documentation",
        "docs spark-profile",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_osdk_react_components_documentation",
        "docs osdk-react-components",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "load_foundry_documentation_page",
        "docs page",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "get_documentation_summaries",
        "docs summaries",
        "DocumentationService",
        "official-catalog",
    ),
    (
        "documentation",
        "search_foundry_documentation",
        "docs search",
        "DocumentationService",
        "official-catalog",
    ),
)

# Richer evidence for a few implemented capabilities. This no longer drives
# status — status is derived from whether the mapped command actually exists in
# the CLI (see _spec_status) — it only replaces the generic "official-catalog"
# evidence string with the concrete SDK path when one is known.
_DOCS_SITE_EVIDENCE = (
    "public Palantir docs site (contract-verified): verbatim markdown from "
    "__NEXT_DATA__ + XML sitemap corpus; stack-side /documentation API is "
    "NOT VERIFIED and deliberately not guessed"
)
_IMPLEMENTED_EVIDENCE: dict[str, str] = {
    "get_project_imports": "foundry-platform-sdk==1.95.0: filesystem.Project.Reference.list",
    "list_foundry_namespaces": (
        "internal compass (contract-verified): GET "
        "/compass/api/hierarchy/v2/all-namespace-rids + PUT "
        "/compass/api/hierarchy/v2/batch/namespaces (read-PUT batch get)"
    ),
    "list_foundry_project_templates": (
        "internal compass (contract-verified): GET "
        "/compass/api/templates/namespace/{namespaceRid}"
    ),
    "search_foundry_projects": "foundry-platform-sdk==1.95.0: filesystem.Space.list + Folder.children",
    "get_dataset_stats": "foundry-platform-sdk==1.95.0: datasets.Dataset.File.list + Dataset.transactions",
    "get_resource_graph": "foundry-platform-sdk==1.95.0: filesystem.Resource.get + Folder.children + Project.Reference.list",
    "view_foundry_rest_api_data_source_webhook": "internal webhooks API (VERIFIED): GET /webhooks/api/registry/v0/{webhookRid}/latest + /version/{version}",
    "get_foundry_ontology_rid": "foundry-platform-sdk==1.95.0: ontologies.Ontology.list (single-ontology resolution)",
    "search_foundry_functions": "internal GraphQL gateway: search(title:, limit:) root field (VERIFIED) with local function matching",
    "view_foundry_link_type": "foundry-platform-sdk==1.95.0: ontologies.Ontology.ObjectType.get_outgoing_link_type",
    "view_foundry_action_type": "foundry-platform-sdk==1.95.0: ontologies.ActionTypeFullMetadata.get (contract-verified; preview flag required)",
    "create_or_update_foundry_object_type": (
        "internal ontology-metadata (contract-verified, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify objectTypes create "
        "variant; dry-run-first with --apply gate and SDK read-back "
        "verification; existing types take the update path: current state "
        "loaded via POST /ontology-metadata/api/ontology/ontology/"
        "bulkLoadEntities, caller delta (display name, description) merged, "
        "update modification dry-run-validated then issued"
    ),
    "delete_foundry_object_type": (
        "internal ontology-metadata (contract-verified, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify objectTypes delete "
        "variant keyed by internal ObjectTypeId; dry-run preview + --apply "
        "--yes gate; verified by post-delete dry-run NotFound read-back"
    ),
    "create_or_update_foundry_link_type": (
        "internal ontology-metadata (contract-verified, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify linkTypes oneToMany "
        "create variant; dry-run-first with --apply gate and post-create "
        "dry-run already-exists read-back; create-only"
    ),
    "delete_foundry_link_type": (
        "internal ontology-metadata (contract-verified, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify linkTypes delete "
        "variant keyed by internal LinkTypeId; dry-run preview + --apply "
        "--yes gate; verified by post-delete dry-run NotFound read-back"
    ),
    "create_or_update_foundry_action_type": (
        "internal ontology-metadata (contract-verified dry-run, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify actionTypesToCreate "
        "with UUID map keys; dry-run-first with --apply gate and SDK "
        "full-metadata read-back; create-only"
    ),
    "delete_foundry_action_type": (
        "internal ontology-metadata (contract-verified dry-run, "
        "the captured contract): POST "
        "/ontology-metadata/api/ontology/v2/modify actionTypesToDelete by "
        "action type RID resolved via SDK full-metadata; dry-run preview + "
        "--apply --yes gate; verified by post-delete dry-run NotFound "
        "read-back"
    ),
    "list_code_repository_pull_requests": (
        "internal stemma-pull-request (contract-verified): GET "
        "/stemma-pull-request/api/pulls returns {'values': [...]}; repository "
        "query parameter is silently ignored server-side, so repository "
        "filtering is client-side"
    ),
    "get_code_repository_pull_request": (
        "internal stemma-pull-request (contract-verified): GET "
        "/stemma-pull-request/api/pulls/{pullRequestRid}"
    ),
    "create_code_repository_pull_request": (
        "internal stemma-pull-request (contract-verified against a live deployment, "
        "the captured contract): POST /pulls with {title, "
        "baseRepositoryRid, headRepositoryRid, baseBranchName, "
        "headCommitish} (+ optional description); strict deserialization"
        " (400 on unknown/missing fields, 403 semantic against a "
        "non-existent repository RID, no speculative 200); dry-run plan "
        "by default, real POST behind --apply; end-to-end verified with "
        "disposable test PR ri.pull-request.main.pull-request.00000000-0000-"
        "0000-0000-000000000030 (closed unmerged after verification via "
        "PUT /pulls/{rid}/update {title, status: CLOSED})"
    ),
    "create_code_repository_pull_request_comment": (
        "internal stemma-pull-request (contract-verified against a live deployment, "
        "the captured contract): POST "
        "/pulls/{pullRequestRid}/comments/global with {content}; strict "
        "strict deserialization (400 on text/body/markdown variants, 403 "
        "semantic against a non-existent pull-request RID); dry-run plan "
        "by default, real POST behind --apply; verified on the "
        "disposable test PR and read back via GET "
        "/pulls/{rid}/comments/global"
    ),
    "view_global_branch": (
        "internal branch-service (contract-verified): PUT "
        "/branch-service/api/branch/load/{branchRid} (empty-body load; "
        "success shape UNVERIFIED — branch-service is unused on the "
        "a live Foundry deployment, responses passed through raw)"
    ),
    "create_global_branch": (
        "internal branch-service: POST /branch-service/api/branch/create; "
        "plan-first command (dry-run default). Contract-recovery "
        "validation identified "
        "{displayName, description, ontologyRid} but the request never "
        "progressed past 400 Default:InvalidArgument, so --apply refuses "
        "with an unverified-write-contract error instead of guessing"
    ),
    "close_global_branch": (
        "internal branch-service (contract-verified): PUT "
        "/branch-service/api/branch/close/{branchRid} (empty-body write; "
        "error contract verified — 403 Branch:PermissionDeniedError "
        "naming branch:edit-branch; success shape UNVERIFIED). Plan-first: "
        "real close requires --apply --yes"
    ),
    "create_global_proposal": (
        "internal branch-service: POST "
        "/branch-service/api/branch/proposal/create; plan-first command "
        "(dry-run default). Validation identified {branchRid, "
        "description, displayName} but the request never progressed past "
        "400 Default:InvalidArgument, so --apply refuses with an "
        "unverified-write-contract error instead of guessing"
    ),
    "close_global_proposal": (
        "internal branch-service (contract-verified): PUT "
        "/branch-service/api/branch/proposal/close/{proposalRid} (empty-body "
        "write; error contract verified — 403 "
        "Branch:PermissionDeniedError naming branch:edit-proposal; success "
        "shape UNVERIFIED). Plan-first: real close requires --apply --yes"
    ),
    "create_foundry_rest_api_data_source_webhook": (
        "internal webhooks API (request contract verified "
        "up to the permission boundary): POST /webhooks/api/registry/v0 "
        "(createWebhook) with {name, apiName, description, spec, "
        "executionPolicy} — the full body passed server-side validation on "
        "a live Foundry deployment, failing only with 403 Compass:InsufficientPermissions; "
        "success shape UNVERIFIED, passed through raw. Plan-first: dry-run "
        "default, --apply sends the verified body"
    ),
    "update_foundry_rest_api_data_source_webhook": (
        "internal webhooks API: POST /webhooks/api/registry/v0/{webhookRid} "
        "(publishWebhookVersion); plan-first command (dry-run default). "
        " validation confirmed only the 'spec' request key; "
        "the full body is UNVERIFIED (webhook creation is "
        "permission-blocked against a live deployment), so --apply refuses with an "
        "unverified-write-contract error instead of guessing"
    ),
    "create_foundry_rest_api_data_source": (
        "internal magritte-coordinator: POST "
        "/magritte-coordinator/api/source-store/source/v2 (addSourceV2/V3); "
        "plan-only command. Validation could NOT recover the write "
        "contract — the service drops unknown keys leniently (defeating the "
        "field validation) and every candidate envelope failed 400; the printed "
        "candidate body models the live target config shape with dummy "
        "values and is never sent. --apply refuses. The CLI never calls "
        "getSourceConfigWithPlaintextSecretValues"
    ),
    "view_global_proposal": (
        "internal branch-service (contract-verified): PUT "
        "/branch-service/api/branch/proposal/load/{proposalRid} (empty-body "
        "load; success shape UNVERIFIED — branch-service is unused on the "
        "a live Foundry deployment, responses passed through raw)"
    ),
    "get_or_create_network_egress_policy": (
        "internal resource-policy-manager (read-contract-verified): POST "
        "/network-egress-policies/get-all-policies + get-batch (read-POSTs); "
        "read-only ensure — the CLI never creates a policy and fails loudly "
        "with a 'would create' message when no policy matches"
    ),
    "get_compute_modules_info": (
        "internal contour-backend-multiplexer (routes contract-verified "
        "against a live deployment): GET "
        "/contour-backend-multiplexer/api/deployed-apps/{rid}/{branch}/status "
        "+ GET /contour-backend-multiplexer/api/deployed-apps/{rid}/v2; "
        "mounts proved by 403 Contour:InsufficientPermission (not "
        "RouteNotMounted) with an inert RID; success shapes UNVERIFIED, "
        "passed through raw"
    ),
    "get_compute_modules_logs": (
        "internal foundry-telemetry-service (the captured contract"
        "): POST /foundry-telemetry-service/api/info/sessions/"
        "by-run-rids/get-batch (contract-verified 200 against a live deployment) then POST "
        "/foundry-telemetry-service/api/containers/{containerRid}/sessions/"
        "{sessionId}/logs/read/v3 with microsecond timestamps; step 2 shape "
        "is bundle-derived and NOT contract-verified (shape_verified: false), "
        "response passed through raw"
    ),
    "manage_compute_modules": (
        "internal build2 + contour-backend-multiplexer (routes contract-verified"
        " against a live deployment): start "
        "= POST /build2/api/manager/submitBuild with the deployed-app RID as "
        "a datasets jobSpecSelection (isRequired: true) — 400 "
        "Build2:JobSpecsForDatasetsNotFoundInGraph proves the contract; stop "
        "= DELETE /build2/api/manager/builds/{buildRid} — 400 "
        "Build2:BuildNotFound proves the route; dev-mode = PUT "
        "/contour-backend-multiplexer/api/deployed-apps/{rid}/{branch}/"
        "dev-mode — 403 Contour:InsufficientPermission proves the mount. "
        "Plan-first: dry-run default, mutations behind --apply (stop also "
        "--yes); success shapes UNVERIFIED, passed through raw"
    ),
    "execute_compute_modules_function": (
        "internal contour-backend-multiplexer (route contract-verified "
        "against a live deployment): POST "
        "/contour-backend-multiplexer/api/module-group-multiplexer/"
        "compute-modules/jobs/execute — 403 Contour:InsufficientPermission "
        "(deployed-apps:submit) proves the mount; response is a raw "
        "octet-stream, success shape UNVERIFIED and passed through raw. "
        "Plan-first: dry-run default, execution behind --apply"
    ),
    # Documentation: verbatim Palantir-authored content proxied from the
    # public docs site (stack-side /documentation API is NOT VERIFIED, so it
    # is not guessed). Pages embed raw markdown in __NEXT_DATA__; the corpus
    # comes from the XML sitemaps. Verified.
    "get_python_transforms_documentation": _DOCS_SITE_EVIDENCE,
    "get_typescript_v1_functions_documentation": _DOCS_SITE_EVIDENCE,
    "get_typescript_v2_functions_documentation": _DOCS_SITE_EVIDENCE,
    "get_custom_widget_documentation": _DOCS_SITE_EVIDENCE,
    "get_ml_documentation": _DOCS_SITE_EVIDENCE,
    "get_spark_profile_documentation": _DOCS_SITE_EVIDENCE,
    "get_osdk_react_components_documentation": _DOCS_SITE_EVIDENCE,
    "get_compute_modules_documentation": _DOCS_SITE_EVIDENCE,
    "load_foundry_documentation_page": _DOCS_SITE_EVIDENCE,
    "get_documentation_summaries": _DOCS_SITE_EVIDENCE,
    "search_foundry_documentation": _DOCS_SITE_EVIDENCE,
    "get_ontology_sdk_context": (
        "foundry-platform-sdk==1.95.0: ontologies.Ontology.list + "
        "Ontology.get_full_metadata + vendored @osdk/foundry.ontologies@2.69.0 "
        "type declarations"
    ),
    "generate_new_ontology_sdk_version": (
        "internal third-party-application-service ("
        "contract-verified against a live deployment, "
        "the captured contract): GET "
        "/third-party-application-service/api/applications/{applicationRid} "
        "for metadata.applicationVersion, then POST "
        "/third-party-application-service/api/application-sdks/v2/"
        '{applicationRid} with exactly {"applicationVersion": N, "npm": {}} '
        "(unknown top-level keys -> 422 Conjure:UnprocessableEntity); "
        "npm.status.type polled requested -> inProgress -> success (~24s "
        "observed) via listSdks GET /application-sdks/{rid} — the "
        "/latest?sdkStatus=REQUESTED confirmation read 204s once the record "
        "leaves requested. Dry-run plan by default, real generation behind "
        "--apply; verified on a disposable test application "
        "tutorial app (0.8.0 minted by the MCP capture, 0.9.0 by this CLI) "
        "from applicationVersion 6"
    ),
    "get_ontology_sdk_examples": (
        "verbatim code blocks from palantir.com/docs OSDK pages + bindings "
        "generated from live ontology metadata (marked generated: true)"
    ),
    "list_platform_sdk_apis": (
        "local AST introspection of installed foundry-platform-sdk==1.95.0 "
        "(foundry_sdk/v2/*/_client.py + resource modules); no network"
    ),
    "get_platform_sdk_api_reference": (
        "local AST introspection of installed foundry-platform-sdk==1.95.0; "
        "docstrings quoted verbatim from the package"
    ),
    "get_repository_context": (
        "internal stemma + compass (contract-verified): GET "
        "/stemma/api/repos/{rid} + /head + /v2/branches + /tags + "
        "/paths/tree/{path}, plus GET /compass/api/resources/{rid}"
        "?decoration=path; stemma silently falls back to the default-branch "
        "tree for unresolvable ?ref= values"
    ),
    "clone_code_repository_locally": (
        "git smart-HTTP (contract-verified via git ls-remote): "
        "https://<host>/stemma/git/<repositoryRid> with the profile bearer "
        "token as http.extraHeader injected via GIT_CONFIG_* env; token "
        "never printed, never persisted in the clone"
    ),
    "create_python_transforms_code_repository": (
        "internal stemma + repository-bootstrapper (contract derived from "
        "the @palantir/mcp 0.408.0 client contract, "
        "the captured contract; pltr contract-verified "
        "the same day, the captured contract): folder -> project "
        "-> Compass path via compass hierarchy batch reads, POST "
        "/stemma/api/repos {path}, then POST /repository-bootstrapper/api/"
        "repos/{rid}/bootstrap (transforms + transforms-python). Plan-first: "
        "dry-run default, creation behind --apply"
    ),
}

# Out of scope for a Foundry operations CLI. These MCP tools generate or
# inspect SDK code, or drive a local IDE / dev console -- none of which are
# Foundry control-plane operations. They are reported so the parity picture
# is complete, marked unsupported (with a reason) rather than dangled as
# "planned" work this CLI intends to build.
# (Empty as of the parity milestone: the workspace trio — repository
# context, local clone, python-transforms creation — was re-scoped in and
# implemented against the internal stemma API.)
_UNSUPPORTED: dict[str, str] = {}

_U3_TEST_REFERENCES: dict[str, str] = {
    "get_project_imports": "tests/test_services/test_project.py;tests/test_commands/test_project.py",
    "list_foundry_namespaces": "tests/test_services/test_compass.py;tests/test_commands/test_namespace.py",
    "list_foundry_project_templates": "tests/test_services/test_compass.py;tests/test_commands/test_project.py",
    "search_foundry_projects": "tests/test_services/test_project.py;tests/test_commands/test_project.py",
    "get_dataset_stats": "tests/test_services/test_dataset.py;tests/test_commands/test_dataset.py",
    "get_resource_graph": "tests/test_services/test_lineage.py;tests/test_commands/test_lineage.py",
    "create_or_update_foundry_object_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "delete_foundry_object_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "create_or_update_foundry_link_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "delete_foundry_link_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "create_or_update_foundry_action_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "delete_foundry_action_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "view_foundry_rest_api_data_source_webhook": "tests/test_services/test_connectivity.py;tests/test_commands/test_connectivity.py",
    "get_foundry_ontology_rid": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "search_foundry_functions": "tests/test_services/test_functions.py;tests/test_commands/test_functions.py",
    "view_foundry_link_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "view_foundry_action_type": "tests/test_services/test_ontology.py;tests/test_commands/test_ontology.py",
    "list_code_repository_pull_requests": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "get_code_repository_pull_request": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "create_code_repository_pull_request": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "create_code_repository_pull_request_comment": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "get_repository_context": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "clone_code_repository_locally": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "create_python_transforms_code_repository": "tests/test_services/test_repository.py;tests/test_commands/test_repository.py",
    "view_global_branch": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_branch.py",
    "create_global_branch": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_branch.py",
    "close_global_branch": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_branch.py",
    "view_global_proposal": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_proposal.py",
    "create_global_proposal": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_proposal.py",
    "close_global_proposal": "tests/test_services/test_global_branching.py;tests/test_commands/test_global_proposal.py",
    "create_foundry_rest_api_data_source_webhook": "tests/test_services/test_connectivity.py;tests/test_commands/test_connectivity.py",
    "update_foundry_rest_api_data_source_webhook": "tests/test_services/test_connectivity.py;tests/test_commands/test_connectivity.py",
    "create_foundry_rest_api_data_source": "tests/test_services/test_connectivity.py;tests/test_commands/test_connectivity.py",
    "get_or_create_network_egress_policy": "tests/test_services/test_connectivity.py;tests/test_commands/test_connectivity.py",
    "get_python_transforms_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_typescript_v1_functions_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_typescript_v2_functions_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_custom_widget_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_ml_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_spark_profile_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_osdk_react_components_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_compute_modules_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "load_foundry_documentation_page": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_documentation_summaries": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "search_foundry_documentation": "tests/test_services/test_documentation.py;tests/test_commands/test_docs.py",
    "get_ontology_sdk_context": "tests/test_services/test_osdk.py;tests/test_commands/test_osdk.py",
    "get_ontology_sdk_examples": "tests/test_services/test_osdk.py;tests/test_commands/test_osdk.py",
    "list_platform_sdk_apis": "tests/test_services/test_platform_sdk.py;tests/test_commands/test_platform_sdk.py",
    "get_platform_sdk_api_reference": "tests/test_services/test_platform_sdk.py;tests/test_commands/test_platform_sdk.py",
    "get_compute_modules_info": "tests/test_services/test_compute.py;tests/test_commands/test_compute.py",
    "get_compute_modules_logs": "tests/test_services/test_compute.py;tests/test_commands/test_compute.py",
    "manage_compute_modules": "tests/test_services/test_compute.py;tests/test_commands/test_compute.py",
    "execute_compute_modules_function": "tests/test_services/test_compute.py;tests/test_commands/test_compute.py",
}

_U3_BLOCKED: dict[str, str] = {
    "preview_transform": (
        "foundry-platform-sdk==1.95.0 exposes no transform preview or dry-run "
        "operation in its orchestration module (its 'preview' flag only gates "
        "preview API features), and the gap analysis catalogues no "
        "VERIFIED internal transform-preview endpoint; implementing one would "
        "require guessing an unverified request contract"
    ),
}

_WORKFLOW_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "dataset",
        "preview_transform",
        "orchestration transform-preview",
        "OrchestrationService",
        "official-overview-workflow",
    ),
)


@lru_cache(maxsize=1)
def registered_command_paths() -> frozenset[str]:
    """Every command path registered on the live Typer app.

    Imported lazily so this module never triggers a circular import at load
    time. By the time this runs (a command invocation or a test) the CLI is
    fully assembled. This is the same surface `pltr agent-manifest` emits, so a
    capability marked implemented is guaranteed to name a command that exists.
    """
    import click
    from typer.main import get_command

    from pltr.cli import app

    paths: set[str] = set()

    def _walk(command: click.Command, prefix: tuple[str, ...] = ()) -> None:
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                _walk(sub, (*prefix, name))
        elif prefix:
            paths.add(" ".join(prefix))

    _walk(get_command(app))
    return frozenset(paths)


def _spec_status(
    capability_id: str, command: str, command_paths: frozenset[str]
) -> tuple[str, Optional[str], Optional[str]]:
    """Derive (status, blocked_reason, evidence_override) for one capability.

    Precedence matters. A capability the SDK cannot do (`blocked`) or that is
    out of scope for a CLI (`unsupported`) is classified explicitly and keeps
    that status even when it names a real fallback command. Everything else is
    classified against the live command surface: `implemented` iff the mapped
    command exists today, `planned` otherwise. So the implemented/planned split
    can never drift from the commands that actually ship, while blocked and
    unsupported stay authoritative.
    """
    if capability_id in _U3_BLOCKED:
        return "blocked", _U3_BLOCKED[capability_id], None
    if capability_id in _UNSUPPORTED:
        return "unsupported", _UNSUPPORTED[capability_id], None
    if command in command_paths:
        return "implemented", None, _IMPLEMENTED_EVIDENCE.get(capability_id)
    return "planned", None, None


def _build_specs(
    command_paths: Optional[frozenset[str]] = None,
) -> tuple[CapabilitySpec, ...]:
    paths = command_paths if command_paths is not None else registered_command_paths()
    specs: list[CapabilitySpec] = []
    for group, capability_id, command, service, evidence in (
        *_TOOL_ROWS,
        *_WORKFLOW_ROWS,
    ):
        mutation_risk = "read"
        if capability_id.startswith(
            ("create_", "update_", "manage_", "execute_", "generate_")
        ):
            mutation_risk = "write"
        if capability_id.startswith(("delete_", "close_")):
            mutation_risk = "destructive"
        status, blocked_reason, evidence_override = _spec_status(
            capability_id, command, paths
        )
        specs.append(
            CapabilitySpec(
                capability_id=capability_id,
                kind="workflow" if capability_id == "preview_transform" else "tool",
                group=group,
                command=command,
                service=service,
                api_evidence=evidence_override or evidence,
                status=status,
                mutation_risk=mutation_risk,
                output_contract="agent-v1",
                test_reference=_U3_TEST_REFERENCES.get(
                    capability_id,
                    "tests/test_capabilities.py;tests/test_commands/test_capabilities.py",
                ),
                blocked_reason=blocked_reason,
            )
        )
    return tuple(specs)


@lru_cache(maxsize=1)
def all_capabilities() -> tuple[CapabilitySpec, ...]:
    """The full capability set with status derived from the live command surface."""
    return _build_specs()


def __getattr__(name: str) -> Any:
    # PEP 562: keep `from pltr.capabilities import CAPABILITIES` working without
    # walking the Typer app at module-import time (which would be circular).
    if name == "CAPABILITIES":
        return all_capabilities()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _validation_errors(specs: Iterable[CapabilitySpec]) -> list[str]:
    entries = tuple(specs)
    errors: list[str] = []
    ids = [entry.capability_id for entry in entries]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate capability ids: {', '.join(duplicates)}")

    for index, entry in enumerate(entries):
        prefix = f"capabilities[{index}]"
        if not entry.capability_id.strip():
            errors.append(f"{prefix}.capability_id is required")
        if entry.kind not in VALID_KINDS:
            errors.append(f"{entry.capability_id}.kind is invalid: {entry.kind}")
        if not entry.group.strip():
            errors.append(f"{entry.capability_id}.group is required")
        if not entry.command.strip():
            errors.append(f"{entry.capability_id}.command is required")
        if not entry.service.strip():
            errors.append(f"{entry.capability_id}.service is required")
        if not entry.api_evidence.strip():
            errors.append(f"{entry.capability_id}.api_evidence is required")
        if entry.status not in VALID_STATUSES:
            errors.append(f"{entry.capability_id}.status is invalid: {entry.status}")
        if entry.mutation_risk not in VALID_MUTATION_RISKS:
            errors.append(
                f"{entry.capability_id}.mutation_risk is invalid: {entry.mutation_risk}"
            )
        if not entry.output_contract.strip():
            errors.append(f"{entry.capability_id}.output_contract is required")
        if not entry.test_reference.strip():
            errors.append(f"{entry.capability_id}.test_reference is required")
        if entry.status in {"blocked", "unsupported"} and not entry.blocked_reason:
            errors.append(
                f"{entry.capability_id}.blocked_reason is required for {entry.status}"
            )
        if entry.status in {"planned", "implemented"} and entry.blocked_reason:
            errors.append(
                f"{entry.capability_id}.blocked_reason is only valid for blocked/unsupported"
            )

    expected_tools = {row[1] for row in _TOOL_ROWS}
    actual_tools = {entry.capability_id for entry in entries if entry.kind == "tool"}
    missing_tools = sorted(expected_tools - actual_tools)
    unexpected_tools = sorted(actual_tools - expected_tools)
    if missing_tools:
        errors.append(f"missing baseline tool ids: {', '.join(missing_tools)}")
    if unexpected_tools:
        errors.append(f"unexpected baseline tool ids: {', '.join(unexpected_tools)}")

    expected_workflows = {row[1] for row in _WORKFLOW_ROWS}
    actual_workflows = {
        entry.capability_id for entry in entries if entry.kind == "workflow"
    }
    missing_workflows = sorted(expected_workflows - actual_workflows)
    if missing_workflows:
        errors.append(f"missing workflow ids: {', '.join(missing_workflows)}")
    if actual_workflows - expected_workflows:
        errors.append(
            f"unexpected workflow ids: {', '.join(sorted(actual_workflows - expected_workflows))}"
        )
    return errors


def validate_capabilities(
    specs: Optional[Iterable[CapabilitySpec]] = None,
) -> None:
    """Validate a capability collection, raising one deterministic error."""
    if specs is None:
        specs = all_capabilities()
    errors = _validation_errors(specs)
    if errors:
        raise ManifestValidationError(errors)


def manifest_payload(
    specs: Optional[Iterable[CapabilitySpec]] = None,
) -> dict[str, Any]:
    """Return the complete versioned manifest payload."""
    if specs is None:
        specs = all_capabilities()
    entries = tuple(specs)
    validate_capabilities(entries)
    capabilities = [entry.as_dict() for entry in entries]
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "catalog": {
            "version": CATALOG_VERSION,
            "source_url": CATALOG_SOURCE_URL,
            "retrieved_on": CATALOG_RETRIEVED_ON,
            "tool_count": sum(entry.kind == "tool" for entry in entries),
            "workflow_count": sum(entry.kind == "workflow" for entry in entries),
        },
        "counts": {
            "total": len(entries),
            "implemented": sum(entry.status == "implemented" for entry in entries),
            "planned": sum(entry.status == "planned" for entry in entries),
            "blocked": sum(entry.status == "blocked" for entry in entries),
            "unsupported": sum(entry.status == "unsupported" for entry in entries),
        },
        "capabilities": capabilities,
    }


def capability_manifest(
    specs: Optional[Iterable[CapabilitySpec]] = None,
) -> Mapping[str, Any]:
    """Return the validated native CLI capability manifest."""
    return manifest_payload(specs)
