"""
Code repository service wrapper.

Pull-request reads plus contract-verified writes backed by the internal
``stemma-pull-request`` API, which the 2026-07-22 gap analysis catalogues
(29 endpoints) and which was contract-verified on a live Foundry deployment:

- ``GET /stemma-pull-request/api/pulls`` returns ``{"values": [...]}``. The
  gap analysis noted a live PR read was UNVERIFIED without a repository
  argument; validation showed a ``repositoryRid`` query parameter is silently
  ignored (PRs from other repositories are still returned), so repository
  filtering is done client-side and documented as such.
- ``GET /stemma-pull-request/api/pulls/{pullRequestRid}`` returns one pull
  request object.
- ``POST /stemma-pull-request/api/pulls`` creates a pull request from
  ``{title, baseRepositoryRid, headRepositoryRid, baseBranchName,
  headCommitish}`` (+ optional ``description``); dry-run plan by default,
  real write behind ``--apply``.
- ``POST /stemma-pull-request/api/pulls/{pullRequestRid}/comments/global``
  creates a global comment from ``{content}``; same dry-run/``--apply``
  posture. Both write contracts were established with strict
  deserialization probes that stop short of any 200 and then verified
  end-to-end on a disposable test pull request (closed unmerged
  afterward); see ``the captured contract``.

Repository context (contract-verified on a live Foundry deployment, probes retained
under ``the captured contract``):

- ``GET /stemma/api/repos/{repositoryRid}`` returns ``{"rid", "sourceRid"}``.
- ``GET /stemma/api/repos/{repositoryRid}/head`` returns
  ``{"commitish": "refs/heads/master", "peeledCommitHash": ...}``.
- ``GET /stemma/api/repos/{repositoryRid}/v2/branches`` returns
  ``{"values": [{"name", "commitHash", "globalBranch"}, ...]}``.
- ``GET /stemma/api/repos/{repositoryRid}/tags`` returns a bare array of
  ``{"name", "commitHash", "message", "tagger"}`` objects.
- ``GET /stemma/api/repos/{repositoryRid}/paths/tree/{path}`` returns
  ``{"metadata": {path: {type, size, name, path, ...}}}`` — a recursive tree.
  Verified: an unresolvable ``?ref=`` query parameter does NOT
  error; the server silently falls back to the default-branch tree, so the
  tree is always reported with the ref that was actually served.
- ``GET /compass/api/resources/{repositoryRid}`` (+ ``?decoration=path``)
  supplies the display name and Compass path for repository metadata.

Local clone (contract-verified): the git smart-HTTP endpoint is
``https://<host>/stemma/git/<repositoryRid>`` (a ``.git`` suffix is rejected,
rc 128). Bearer-token auth via ``http.extraHeader`` passed through
``GIT_CONFIG_*`` environment variables — never on the command line, never
written into the clone's config, never printed.

Python transforms repository creation (contract derived from Palantir MCP
the client contract 2026-07-25 on a live Foundry deployment, see
``the captured contract`` and the pltr live
verification in ``repo-create-live-verification.md``): the folder RID is
resolved to its enclosing project and the project's Compass path via the
read-PUT batch endpoints ``PUT /compass/api/hierarchy/v2/batch/resources/
projects`` and ``PUT /compass/api/hierarchy/v2/batch/projects-v3``
(decorations ``["path"]``); the repository is then created with
``POST /stemma/api/repos`` ``{"path": "<projectPath>/<name>"}`` and the
Python transforms template is applied by a second call,
``POST /repository-bootstrapper/api/repos/{rid}/bootstrap`` with
``{"parentTemplateId": "transforms", "childTemplateIdsByPath":
{"transforms-python": "python"}, "templateTokens": {}}`` (204). Dry-run
plan by default; the real write sits behind ``--apply``.

Responses are passed through raw (never fabricated); unexpected shapes fail
loudly instead of rendering as a result.
"""

import os
import shutil
import subprocess
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base import BaseService
from .foundry_internal_client import FoundryInternalClient


class PullRequestNotFoundError(RuntimeError):
    """Raised when the pull-request service has no PR for a RID."""


class PullRequestShapeError(RuntimeError):
    """Raised when a pull-request response does not match the verified shape."""


class RepositoryNotFoundError(RuntimeError):
    """Raised when stemma has no repository for a RID."""


class RepositoryShapeError(RuntimeError):
    """Raised when a stemma response does not match the verified shape."""


class RepositoryCloneError(RuntimeError):
    """Raised when a local clone cannot be completed honestly."""


class RepositoryService(BaseService):
    """Service wrapper for code repository operations (reads + verified writes)."""

    # Listing every pull request on a busy stack took ~60s in verification;
    # the default 30s timeout is not enough for this endpoint.
    PULL_REQUEST_LIST_TIMEOUT = 120.0

    def _get_service(self) -> Any:
        """Get the Foundry client (pull requests use the internal API)."""
        return self.client

    def list_pull_requests(
        self, repository_rid: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List pull requests, optionally filtered to one repository.

        Read-only against GET /stemma-pull-request/api/pulls. The server does
        not honor a repository query parameter (verified: it is
        silently ignored), so when ``repository_rid`` is given the filtering
        happens client-side on the verified ``baseRepositoryRid`` /
        ``headRepositoryRid`` fields.

        Args:
            repository_rid: Optional repository RID to filter by (client-side)

        Returns:
            List of raw pull request dictionaries

        Raises:
            PullRequestShapeError: If the response shape is not the verified
                ``{"values": [...]}`` envelope
            RuntimeError: If the read fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET",
                "stemma-pull-request/api/pulls",
                request_timeout=self.PULL_REQUEST_LIST_TIMEOUT,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to list pull requests: {e}") from e

        self._raise_for_status(status, payload, raw, "pull-request list")

        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("values"), list
        ):
            raise PullRequestShapeError(
                "Unverified pull-request list response shape: expected an "
                'object with a "values" array, got '
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )

        pull_requests = payload["values"]
        for entry in pull_requests:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("rid"), str):
                raise PullRequestShapeError(
                    "Unverified pull-request entry shape: expected an object "
                    f'with a string "rid", got {str(entry)[:200]!r}. '
                    "Refusing to guess at the contract."
                )

        if repository_rid is None:
            return [dict(entry) for entry in pull_requests]
        return [
            dict(entry)
            for entry in pull_requests
            if entry.get("baseRepositoryRid") == repository_rid
            or entry.get("headRepositoryRid") == repository_rid
        ]

    def get_pull_request(self, pull_request_rid: str) -> Dict[str, Any]:
        """
        Get one pull request by RID.

        Read-only against GET /stemma-pull-request/api/pulls/{pullRequestRid}
        (shape contract-verified on a live Foundry deployment).

        Args:
            pull_request_rid: Pull request Resource Identifier

        Returns:
            Raw pull request dictionary

        Raises:
            PullRequestNotFoundError: If no pull request exists for the RID
            PullRequestShapeError: If the response shape is not the verified
                pull request object
            RuntimeError: If the read fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma-pull-request/api/pulls/{pull_request_rid}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to read pull request {pull_request_rid}: {e}"
            ) from e

        if status == 404:
            raise PullRequestNotFoundError(
                f"No pull request found for RID {pull_request_rid}"
            )
        self._raise_for_status(status, payload, raw, "pull-request get")

        if not isinstance(payload, Mapping) or not payload:
            raise PullRequestNotFoundError(
                f"No pull request found for RID {pull_request_rid}"
            )
        if not isinstance(payload.get("rid"), str):
            raise PullRequestShapeError(
                "Unverified pull-request response shape: expected an object "
                f'with a string "rid", got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        return dict(payload)

    # ------------------------------------------------------------------
    # Pull-request creation + global comments
    #
    # Request contracts verified on a live Foundry deployment via
    # strict-deserialization checks that stop short of any 200 (a 200
    # creates): the server strictly rejects unknown and missing fields
    # with 400 Default:InvalidArgument, so candidate bodies carrying a
    # non-existent repository/pull-request RID separate "body shape
    # wrong" (400) from "body shape right" (403 semantic failure, no
    # resource created). Success paths contract-verified the same day on the
    # probe repository with a disposable test repository pull
    # request (closed after verification). See
    # the captured contract
    # ------------------------------------------------------------------

    #: Evidence for the POST /pulls request contract.
    PULL_REQUEST_CREATE_CONTRACT_EVIDENCE = (
        "POST /stemma-pull-request/api/pulls contract contract-verified "
        "2026-07-24 on a live Foundry deployment (the captured contract): "
        "strict deserialization (400 Default:InvalidArgument on empty "
        "body, bogus keys, and headBranchName-style variants); "
        "{title, baseRepositoryRid, headRepositoryRid, baseBranchName, "
        "headCommitish} (+ optional description) passed deserialization "
        "and failed only semantically (403 "
        "StemmaPullRequest:CannotCreatePullRequest) against a "
        "non-existent repository RID, so the shape was established "
        "without any speculative 200. End-to-end verified with "
        "disposable test PR ri.pull-request.main.pull-request.00000000-0000-"
        "0000-0000-000000000030 on the probe repository (read back via "
        "GET /pulls/{rid}, then closed unmerged via PUT "
        "/pulls/{rid}/update with {title, status: CLOSED})"
    )

    #: Evidence for the POST /pulls/{rid}/comments/global request contract.
    PULL_REQUEST_COMMENT_CONTRACT_EVIDENCE = (
        "POST /stemma-pull-request/api/pulls/{pullRequestRid}/comments/"
        "global contract contract-verified on a live Foundry deployment "
        "(the captured contract): strict deserialization (400 "
        "Default:InvalidArgument on empty body, bogus keys, and "
        "text/body/markdown variants); {content} passed deserialization "
        "and failed only semantically (403 "
        "Comments:NotPermittedToWriteComment) against a non-existent "
        "pull-request RID, so the shape was established without any "
        "speculative 200. End-to-end verified on the disposable test PR "
        "(comment ri.pull-request.main.pull-request-comment.00000000-"
        "a5f2-0000-0000-000000000030.00000000-0000-0000-0000-000000000029 "
        "read back via GET /pulls/{rid}/comments/global)"
    )

    def create_pull_request_plan(
        self,
        *,
        title: str,
        base_repository_rid: str,
        head_commitish: str,
        head_repository_rid: Optional[str] = None,
        base_branch_name: str = "refs/heads/master",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build the dry-run plan for creating a pull request.

        The request body mirrors the contract verified in
        PULL_REQUEST_CREATE_CONTRACT_EVIDENCE; this plan is what
        ``create_pull_request`` posts verbatim under ``--apply``.
        """
        body: Dict[str, Any] = {
            "title": title,
            "baseRepositoryRid": base_repository_rid,
            "headRepositoryRid": head_repository_rid or base_repository_rid,
            "baseBranchName": base_branch_name,
            "headCommitish": head_commitish,
        }
        if description is not None:
            body["description"] = description
        return {
            "status": "dry-run",
            "operation": "create_code_repository_pull_request",
            "intended_endpoint": "POST /stemma-pull-request/api/pulls",
            "intended_body": body,
            "contract": "VERIFIED",
            "evidence": self.PULL_REQUEST_CREATE_CONTRACT_EVIDENCE,
            "apply_note": "Re-run with --apply to issue the POST.",
            "cleanup_policy": (
                "disposable test pull requests are closed after "
                "verification and never merged"
            ),
        }

    def create_pull_request(
        self,
        *,
        title: str,
        base_repository_rid: str,
        head_commitish: str,
        head_repository_rid: Optional[str] = None,
        base_branch_name: str = "refs/heads/master",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a pull request (real POST /stemma-pull-request/api/pulls).

        Posts exactly the body the dry-run plan shows. The response is
        passed through raw; an unexpected shape fails loudly instead of
        rendering as a result.

        Raises:
            PullRequestShapeError: If the response is not the verified
                pull request object
            RuntimeError: If the write fails or the API is not mounted
        """
        plan = self.create_pull_request_plan(
            title=title,
            base_repository_rid=base_repository_rid,
            head_commitish=head_commitish,
            head_repository_rid=head_repository_rid,
            base_branch_name=base_branch_name,
            description=description,
        )
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "POST",
                "stemma-pull-request/api/pulls",
                json_body=plan["intended_body"],
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create pull request: {e}") from e

        self._raise_for_status(status, payload, raw, "pull-request create")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rid"), str):
            raise PullRequestShapeError(
                "Unverified pull-request create response shape: expected an "
                f'object with a string "rid", got {str(raw)[:200]!r}. '
                "The POST may still have succeeded; reconcile via "
                "repository pull-request list before retrying."
            )
        return dict(payload)

    def create_pull_request_comment_plan(
        self, pull_request_rid: str, content: str
    ) -> Dict[str, Any]:
        """
        Build the dry-run plan for a global comment on one pull request.

        The request body mirrors the contract verified in
        PULL_REQUEST_COMMENT_CONTRACT_EVIDENCE; this plan is what
        ``create_pull_request_comment`` posts verbatim under ``--apply``.
        """
        return {
            "status": "dry-run",
            "operation": "create_code_repository_pull_request_comment",
            "pull_request_rid": pull_request_rid,
            "intended_endpoint": (
                "POST /stemma-pull-request/api/pulls/"
                f"{pull_request_rid}/comments/global"
            ),
            "intended_body": {"content": content},
            "contract": "VERIFIED",
            "evidence": self.PULL_REQUEST_COMMENT_CONTRACT_EVIDENCE,
            "apply_note": "Re-run with --apply to issue the POST.",
        }

    def create_pull_request_comment(
        self, pull_request_rid: str, content: str
    ) -> Dict[str, Any]:
        """
        Create a global comment on one pull request (real POST).

        Posts exactly the body the dry-run plan shows. The response is
        passed through raw; an unexpected shape fails loudly instead of
        rendering as a result.

        Raises:
            PullRequestShapeError: If the response is not the verified
                comment object
            RuntimeError: If the write fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "POST",
                f"stemma-pull-request/api/pulls/{pull_request_rid}/comments/global",
                json_body={"content": content},
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to comment on pull request {pull_request_rid}: {e}"
            ) from e

        self._raise_for_status(status, payload, raw, "pull-request comment create")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rid"), str):
            raise PullRequestShapeError(
                "Unverified pull-request comment response shape: expected an "
                f'object with a string "rid", got {str(raw)[:200]!r}. '
                "The POST may still have succeeded; reconcile via GET "
                "/pulls/{rid}/comments/global before retrying."
            )
        return dict(payload)

    # ------------------------------------------------------------------
    # Repository context (read-only, contract-verified on a live Foundry deployment)
    # ------------------------------------------------------------------

    def get_repository(self, repository_rid: str) -> Dict[str, Any]:
        """
        Get stemma repository metadata plus the Compass display name/path.

        Read-only against GET /stemma/api/repos/{repositoryRid} and
        GET /compass/api/resources/{repositoryRid}?decoration=path (both
        contract-verified on a live Foundry deployment).

        Raises:
            RepositoryNotFoundError: If no repository exists for the RID
            RepositoryShapeError: If a response shape drifts from verified
            RuntimeError: If the read fails or the API is not mounted
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma/api/repos/{repository_rid}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to read repository {repository_rid}: {e}"
            ) from e

        if status == 404 and not (
            isinstance(payload, Mapping)
            and payload.get("errorName") == "Route:RouteNotMounted"
        ):
            raise RepositoryNotFoundError(
                f"No repository found for RID {repository_rid}"
            )
        self._raise_for_status(status, payload, raw, "repository get")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rid"), str):
            raise RepositoryShapeError(
                "Unverified repository response shape: expected an object "
                f'with a string "rid", got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )

        repository = dict(payload)
        repository["compass"] = self._get_compass_metadata(repository_rid)
        return repository

    def _get_compass_metadata(self, repository_rid: str) -> Dict[str, Any]:
        """Read the Compass display name and path for one repository."""
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET",
                f"compass/api/resources/{repository_rid}?decoration=path",
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to read Compass metadata for {repository_rid}: {e}"
            ) from e
        self._raise_for_status(status, payload, raw, "compass repository get")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("name"), str):
            raise RepositoryShapeError(
                "Unverified Compass resource shape: expected an object with "
                f'a string "name", got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        return {"name": payload["name"], "path": payload.get("path")}

    def get_head(self, repository_rid: str) -> Dict[str, Any]:
        """
        Get the default branch (HEAD) of one repository.

        Read-only against GET /stemma/api/repos/{repositoryRid}/head, which
        returns ``{"commitish": ..., "peeledCommitHash": ...}`` (verified
        2026-07-24).
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma/api/repos/{repository_rid}/head"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to read HEAD for {repository_rid}: {e}") from e
        self._raise_for_status(status, payload, raw, "repository head")
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("commitish"), str
        ):
            raise RepositoryShapeError(
                "Unverified head response shape: expected an object with a "
                f'string "commitish", got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        return dict(payload)

    def list_branches(self, repository_rid: str) -> List[Dict[str, Any]]:
        """
        List branch refs of one repository.

        Read-only against GET /stemma/api/repos/{repositoryRid}/v2/branches,
        which returns ``{"values": [{"name", "commitHash", ...}]}`` (verified
        2026-07-24).
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma/api/repos/{repository_rid}/v2/branches"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to list branches for {repository_rid}: {e}"
            ) from e
        self._raise_for_status(status, payload, raw, "repository branches")
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("values"), list
        ):
            raise RepositoryShapeError(
                "Unverified branches response shape: expected an object with "
                f'a "values" array, got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        branches = payload["values"]
        for entry in branches:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
                raise RepositoryShapeError(
                    "Unverified branch entry shape: expected an object with "
                    f'a string "name", got {str(entry)[:200]!r}. '
                    "Refusing to guess at the contract."
                )
        return [dict(entry) for entry in branches]

    def list_tags(self, repository_rid: str) -> List[Dict[str, Any]]:
        """
        List tag refs of one repository.

        Read-only against GET /stemma/api/repos/{repositoryRid}/tags, which
        returns a bare array of ``{"name", "commitHash", ...}`` objects
        (verified).
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "GET", f"stemma/api/repos/{repository_rid}/tags"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to list tags for {repository_rid}: {e}") from e
        self._raise_for_status(status, payload, raw, "repository tags")
        if not isinstance(payload, list):
            raise RepositoryShapeError(
                "Unverified tags response shape: expected a JSON array, got "
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )
        for entry in payload:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
                raise RepositoryShapeError(
                    "Unverified tag entry shape: expected an object with a "
                    f'string "name", got {str(entry)[:200]!r}. '
                    "Refusing to guess at the contract."
                )
        return [dict(entry) for entry in payload]

    def get_path_tree(
        self,
        repository_rid: str,
        path: str = "",
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the recursive file tree at ``path``.

        Read-only against GET /stemma/api/repos/{rid}/paths/tree/{path},
        which returns ``{"metadata": {path: entry}}`` (verified).

        A ``ref`` is forwarded as the ``?ref=`` query parameter, but verified
        2026-07-24 the server silently falls back to the default-branch tree
        for unresolvable refs instead of erroring. Callers must therefore
        treat the returned tree as "the tree stemma served", not proof the
        requested ref was honored.
        """
        client = self._internal_client()
        endpoint = f"stemma/api/repos/{repository_rid}/paths/tree/{path}"
        if ref:
            endpoint = f"{endpoint}?ref={ref}"
        try:
            status, payload, raw = client.conjure("GET", endpoint)
        except Exception as e:
            raise RuntimeError(
                f"Failed to read path tree for {repository_rid}: {e}"
            ) from e
        if status == 404 and not (
            isinstance(payload, Mapping)
            and payload.get("errorName") == "Route:RouteNotMounted"
        ):
            raise RepositoryNotFoundError(
                f"No path {path!r} in repository {repository_rid}"
            )
        self._raise_for_status(status, payload, raw, "repository path tree")
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("metadata"), Mapping
        ):
            raise RepositoryShapeError(
                "Unverified path-tree response shape: expected an object "
                f'with a "metadata" object, got {str(raw)[:200]!r}. '
                "Refusing to guess at the contract."
            )
        metadata = payload["metadata"]
        for entry_path, entry in metadata.items():
            if not isinstance(entry, Mapping) or not isinstance(entry.get("type"), str):
                raise RepositoryShapeError(
                    "Unverified path-tree entry shape: expected an object "
                    f'with a string "type" at {entry_path!r}, got '
                    f"{str(entry)[:200]!r}. Refusing to guess at the contract."
                )
        return {key: dict(value) for key, value in metadata.items()}

    def get_repository_context(
        self,
        repository_rid: str,
        path: str = "",
        ref: Optional[str] = None,
        include_tree: bool = True,
    ) -> Dict[str, Any]:
        """
        Compose the headless repository context for one repository.

        Read-only aggregation of the verified stemma/compass reads: repository
        metadata, default branch, branch and tag refs, and the recursive file
        tree. When ``ref`` is None the tree is read at the default branch.

        Returns a dict with ``repository``, ``default_branch``, ``refs`` and
        (optionally) ``tree``. ``tree.requested_ref`` records what was asked
        for; stemma silently falls back to the default branch for
        unresolvable refs (verified), so the note is carried in
        ``tree.ref_note`` rather than hidden.
        """
        repository = self.get_repository(repository_rid)
        head = self.get_head(repository_rid)
        branches = self.list_branches(repository_rid)
        tags = self.list_tags(repository_rid)

        context: Dict[str, Any] = {
            "repository": repository,
            "default_branch": head,
            "refs": {"branches": branches, "tags": tags},
        }
        if include_tree:
            tree_ref = ref or head["commitish"]
            tree = self.get_path_tree(repository_rid, path=path, ref=tree_ref)
            context["tree"] = {
                "path": path,
                "requested_ref": tree_ref,
                "ref_note": (
                    "stemma silently falls back to the default-branch tree "
                    "for unresolvable ?ref= values (verified); "
                    "honoring of valid refs is not distinguishable on the "
                    "verified stack"
                ),
                "entries": [tree[key] for key in sorted(tree.keys())],
            }
        return context

    # ------------------------------------------------------------------
    # Local clone (git smart-HTTP endpoint verified on a live Foundry deployment)
    # ------------------------------------------------------------------

    def resolve_clone_plan(
        self, repository_rid: str, target_dir: str, branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve everything needed for a local clone without cloning.

        Verifies the repository exists (stemma get + head), then constructs
        the git URL ``https://<host>/stemma/git/<repositoryRid>`` — the exact
        form contract-verified with ``git ls-remote`` 2026-07-24 (a ``.git``
        suffix is rejected by the server).
        """
        repository = self.get_repository(repository_rid)
        head = self.get_head(repository_rid)
        base_url, _ = self._git_credentials()
        return {
            "repository_rid": repository_rid,
            "repository_name": repository.get("compass", {}).get("name"),
            "git_url": f"{base_url}/stemma/git/{repository_rid}",
            "target_dir": target_dir,
            "branch": branch,
            "default_branch": head["commitish"],
            "credential": (
                "profile bearer token via http.extraHeader at clone time; "
                "never printed and never written into the clone's config"
            ),
        }

    def clone_repository(
        self,
        repository_rid: str,
        target_dir: str,
        *,
        branch: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
        clone_timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Clone a Foundry code repository to a local path.

        Runs ``git clone`` with the profile bearer token passed via
        ``GIT_CONFIG_*`` environment variables (http.extraHeader), so the
        token never appears on the command line, in output, or in the
        clone's persisted config. Note this means later ``git fetch`` inside
        the clone needs fresh credentials — re-run this command or configure
        a credential helper.

        Refuses to overwrite a non-empty target directory unless ``force`` is
        given; with ``force`` the existing directory is deleted first (the
        command layer confirms this interactively when possible).

        Raises:
            RepositoryCloneError: On any clone precondition or git failure
        """
        plan = self.resolve_clone_plan(repository_rid, target_dir, branch)
        if dry_run:
            plan["status"] = "dry-run"
            plan["would_overwrite"] = self._target_nonempty(target_dir)
            return plan

        if shutil.which("git") is None:
            raise RepositoryCloneError(
                f"git is not available on PATH; cannot clone {repository_rid} locally"
            )

        if self._target_nonempty(target_dir):
            if not force:
                raise RepositoryCloneError(
                    f"Target directory {target_dir} exists and is not empty; "
                    "refusing to overwrite without --force"
                )
            shutil.rmtree(target_dir)

        _, token = self._git_credentials()
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Keep the token out of argv: GIT_CONFIG_* injects http.extraHeader
        # for this process only; nothing is persisted into the clone.
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {token}"

        cmd = ["git", "clone"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [plan["git_url"], target_dir]
        try:
            proc = subprocess.run(
                cmd, env=env, capture_output=True, text=True, timeout=clone_timeout
            )
        except subprocess.TimeoutExpired as e:
            raise RepositoryCloneError(
                f"git clone timed out after {clone_timeout}s for {repository_rid}"
            ) from e
        if proc.returncode != 0:
            raise RepositoryCloneError(
                f"git clone failed (exit {proc.returncode}) for "
                f"{repository_rid}: {self._redact(proc.stderr, token)[:400]}"
            )

        plan["status"] = "cloned"
        plan["git_stderr"] = self._redact(proc.stderr, token).strip()
        return plan

    @staticmethod
    def _target_nonempty(target_dir: str) -> bool:
        return os.path.isdir(target_dir) and bool(os.listdir(target_dir))

    @staticmethod
    def _redact(text: str, token: str) -> str:
        return text.replace(token, "[REDACTED]") if token else text

    def _git_credentials(self) -> Tuple[str, str]:
        """Resolve (base_url, token) for the active profile."""
        from ..auth.base import MissingCredentialsError, ProfileNotFoundError
        from ..auth.storage import CredentialStorage
        from ..config.profiles import ProfileManager

        profile_name = self.profile or ProfileManager().get_active_profile()
        if not profile_name:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'pltr configure configure' to set up authentication."
            )
        credentials = CredentialStorage().get_profile(profile_name)
        token = credentials.get("token")
        if not token:
            raise MissingCredentialsError(
                f"Profile '{profile_name}' has no token for git clone auth."
            )
        base_url = FoundryInternalClient._base_url(credentials.get("host", ""))
        return base_url, token

    # ------------------------------------------------------------------
    # Python transforms repository creation
    #
    # Contract derived from the Palantir MCP client contract
    # (@palantir/mcp 0.408.0) traffic on a live Foundry deployment
    # (the captured contract): the MCP resolves
    # the folder RID to its enclosing project, reads the project's Compass
    # path, creates the repository with a single {"path": ...} stemma
    # body, and applies the Python transforms template with a second
    # repository-bootstrapper call. contract-verified end-to-end by pltr the
    # same day (the captured contract
    # repo-create-live-verification.md). Both stemma and
    # repository-bootstrapper are internal APIs catalogued from observed
    # traffic, not public-v2 contracts.
    # ------------------------------------------------------------------

    #: Bootstrapper body that materializes the Python transforms template.
    PYTHON_TRANSFORMS_BOOTSTRAP_BODY: Dict[str, Any] = {
        "parentTemplateId": "transforms",
        "childTemplateIdsByPath": {"transforms-python": "python"},
        "templateTokens": {},
    }

    #: Evidence for the repository creation contract.
    CREATE_CONTRACT_EVIDENCE = (
        "Repository creation contract derived from the Palantir MCP client contract "
        "(@palantir/mcp 0.408.0) traffic 2026-07-25 on a live Foundry deployment "
        "(the captured contract): folder RID -> "
        "enclosing project via PUT /compass/api/hierarchy/v2/batch/"
        "resources/projects; project Compass path via PUT /compass/api/"
        'hierarchy/v2/batch/projects-v3 (decorations ["path"]); '
        'POST /stemma/api/repos {"path": "<projectPath>/<name>"} -> '
        '{"rid", "sourceRid"}; POST /repository-bootstrapper/api/'
        'repos/<rid>/bootstrap {"parentTemplateId": "transforms", '
        '"childTemplateIdsByPath": {"transforms-python": "python"}, '
        '"templateTokens": {}} -> 204. contract-verified end-to-end by pltr '
        "the same day on a disposable repository (master branch + 0.0.1 "
        "tag materialized, then compass trash + permanent delete); see "
        "the captured contract "
        "The repository always lands in the project ROOT regardless of "
        "how deep the passed folder RID sits."
    )

    #: Verified cleanup path for created repositories.
    CREATE_CLEANUP_POLICY = (
        "created repositories are trashed with `pltr resource delete "
        "--force` and permanently removed with `pltr resource "
        "permanently-delete --force` (both verified on a live Foundry deployment "
        "against ri.stemma.main.repository RIDs); disposable test "
        "repositories are always deleted after verification"
    )

    def resolve_enclosing_project(self, folder_rid: str) -> str:
        """
        Resolve a Compass folder RID to its enclosing project RID.

        Read-only against PUT /compass/api/hierarchy/v2/batch/resources/
        projects, a read-PUT batch get whose body is a bare JSON array of
        RIDs and whose response maps each RID to its project RID
        (contract captured; the repository create always lands
        in the project root).

        Raises:
            RepositoryShapeError: If the response shape drifts from verified
            RuntimeError: If the folder has no enclosing project in the
                response, or the read fails
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "PUT",
                "compass/api/hierarchy/v2/batch/resources/projects",
                json_body=[folder_rid],
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to resolve enclosing project for {folder_rid}: {e}"
            ) from e
        self._raise_for_status(status, payload, raw, "folder-to-project resolve")
        if not isinstance(payload, Mapping):
            raise RepositoryShapeError(
                "Unverified folder-to-project response shape: expected an "
                f"object mapping folder RIDs to project RIDs, got "
                f"{str(raw)[:200]!r}. Refusing to guess at the contract."
            )
        project_rid = payload.get(folder_rid)
        if project_rid is None:
            raise RuntimeError(
                f"No enclosing project found for folder {folder_rid}: the "
                "hierarchy batch response carried no entry for it (the "
                "folder may not exist or may not be readable)"
            )
        if not isinstance(project_rid, str):
            raise RepositoryShapeError(
                "Unverified folder-to-project entry shape: expected a "
                f"string project RID for {folder_rid}, got "
                f"{str(project_rid)[:200]!r}. Refusing to guess at the contract."
            )
        return project_rid

    def get_project_path(self, project_rid: str) -> str:
        """
        Read the full Compass path of one project.

        Read-only against PUT /compass/api/hierarchy/v2/batch/projects-v3
        with ``{"decorations": ["path"], "includeOperations": false,
        "rids": [...]}``; the response maps each project RID to an entry
        whose ``resource.path`` carries the full Compass path (contract
        captured).

        Raises:
            RepositoryShapeError: If the response shape drifts from verified
            RuntimeError: If the project is absent from the response or the
                read fails
        """
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "PUT",
                "compass/api/hierarchy/v2/batch/projects-v3",
                json_body={
                    "decorations": ["path"],
                    "includeOperations": False,
                    "rids": [project_rid],
                },
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to read Compass path for project {project_rid}: {e}"
            ) from e
        self._raise_for_status(status, payload, raw, "project path read")
        if not isinstance(payload, Mapping):
            raise RepositoryShapeError(
                "Unverified projects-v3 response shape: expected an object "
                f"mapping project RIDs to entries, got {str(raw)[:200]!r}. "
                "Refusing to guess at the contract."
            )
        entry = payload.get(project_rid)
        if entry is None:
            raise RuntimeError(
                f"No entry for project {project_rid} in the projects-v3 "
                "response (the project may not exist or may not be readable)"
            )
        resource = entry.get("resource") if isinstance(entry, Mapping) else None
        path = resource.get("path") if isinstance(resource, Mapping) else None
        if not isinstance(path, str) or not path:
            raise RepositoryShapeError(
                "Unverified projects-v3 entry shape: expected "
                f"{project_rid}.resource.path to be a non-empty string, got "
                f"{str(entry)[:200]!r}. Refusing to guess at the contract."
            )
        return path

    def resolve_repository_target_path(
        self, name: str, parent_rid: str
    ) -> Dict[str, Any]:
        """
        Resolve the full Compass path a new repository will be created at.

        Read-only preflight: folder RID -> enclosing project RID ->
        project Compass path; the repository always lands in the project
        ROOT, so the target path is ``<projectPath>/<name>``.
        """
        project_rid = self.resolve_enclosing_project(parent_rid)
        project_path = self.get_project_path(project_rid)
        return {
            "project_rid": project_rid,
            "project_path": project_path,
            "path": f"{project_path.rstrip('/')}/{name}",
        }

    def create_python_transforms_plan(
        self, name: str, parent_rid: str
    ) -> Dict[str, Any]:
        """
        Build the dry-run plan for creating a Python transforms repository.

        Runs the read-only preflight (folder -> project -> Compass path) so
        the plan shows the exact stemma body ``create_python_transforms_
        repository`` posts under ``--apply``, followed by the bootstrapper
        call that materializes the template.
        """
        target = self.resolve_repository_target_path(name, parent_rid)
        return {
            "status": "dry-run",
            "operation": "create_python_transforms_code_repository",
            "name": name,
            "parent_rid": parent_rid,
            "project_rid": target["project_rid"],
            "intended_calls": [
                {
                    "endpoint": "POST /stemma/api/repos",
                    "body": {"path": target["path"]},
                },
                {
                    "endpoint": (
                        "POST /repository-bootstrapper/api/repos/"
                        "<repositoryRid>/bootstrap"
                    ),
                    "body": dict(self.PYTHON_TRANSFORMS_BOOTSTRAP_BODY),
                },
            ],
            "contract": "VERIFIED",
            "evidence": self.CREATE_CONTRACT_EVIDENCE,
            "apply_note": "Re-run with --apply to create the repository.",
            "cleanup_policy": self.CREATE_CLEANUP_POLICY,
        }

    def create_python_transforms_repository(
        self, name: str, parent_rid: str
    ) -> Dict[str, Any]:
        """
        Create a Python transforms repository (real writes).

        Posts exactly the stemma body the dry-run plan shows, then applies
        the Python transforms template via the repository-bootstrapper
        (without it the result is a bare empty repo, not a transforms
        repository). After the 204 bootstrap response the master branch and
        initial ``0.0.1`` tag are read back via the verified stemma reads;
        a read-back failure is reported in ``verification_error`` rather
        than raised, because the repository itself already exists by then.

        Raises:
            RepositoryShapeError: If a response shape drifts from verified
            RuntimeError: If any write fails or an API is not mounted
        """
        plan = self.create_python_transforms_plan(name, parent_rid)
        stemma_body = plan["intended_calls"][0]["body"]
        client = self._internal_client()
        try:
            status, payload, raw = client.conjure(
                "POST", "stemma/api/repos", json_body=stemma_body
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create repository {name!r}: {e}") from e
        self._raise_for_status(status, payload, raw, "repository create")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rid"), str):
            raise RepositoryShapeError(
                "Unverified repository create response shape: expected an "
                f'object with a string "rid", got {str(raw)[:200]!r}. '
                "The POST may still have succeeded; reconcile via compass "
                "search for the repository name before retrying."
            )
        repository_rid = payload["rid"]
        source_rid = payload.get("sourceRid")

        bootstrap_endpoint = (
            f"repository-bootstrapper/api/repos/{repository_rid}/bootstrap"
        )
        try:
            status, payload, raw = client.conjure(
                "POST",
                bootstrap_endpoint,
                json_body=self.PYTHON_TRANSFORMS_BOOTSTRAP_BODY,
            )
        except Exception as e:
            raise RuntimeError(
                f"Repository {repository_rid} was created but the "
                f"bootstrapper call failed: {e}. The repository is a bare "
                "empty repo without the transforms template; reconcile or "
                f"delete it ({self.CREATE_CLEANUP_POLICY})."
            ) from e
        if not 200 <= status < 300:
            error_name = (
                payload.get("errorName") if isinstance(payload, Mapping) else None
            )
            detail = f" ({error_name})" if error_name else ""
            raise RuntimeError(
                f"Repository {repository_rid} was created but the "
                f"bootstrapper call failed with HTTP {status}{detail}: "
                f"{str(raw)[:200]}. The repository is a bare empty repo "
                "without the transforms template; reconcile or delete it."
            )

        verification: Dict[str, Any]
        try:
            head = self.get_head(repository_rid)
            branches = self.list_branches(repository_rid)
            tags = self.list_tags(repository_rid)
            verification = {
                "default_branch": head,
                "branches": branches,
                "tags": tags,
                "bootstrap_verified": (
                    any(b["name"] == "refs/heads/master" for b in branches)
                    and any(t["name"] == "refs/tags/0.0.1" for t in tags)
                ),
            }
        except Exception as e:
            verification = {
                "bootstrap_verified": None,
                "verification_error": (
                    f"read-back failed after a successful bootstrap: {e}. "
                    "The repository exists; verify via `pltr repository "
                    "context` before retrying anything."
                ),
            }

        return {
            "status": "created",
            "operation": "create_python_transforms_code_repository",
            "name": name,
            "parent_rid": parent_rid,
            "project_rid": plan["project_rid"],
            "repository": {
                "rid": repository_rid,
                "sourceRid": source_rid,
            },
            "compass_path": stemma_body["path"],
            "bootstrap": {
                "status": "applied",
                "endpoint": f"POST /{bootstrap_endpoint}",
                "body": dict(self.PYTHON_TRANSFORMS_BOOTSTRAP_BODY),
            },
            "verification": verification,
            "contract": "VERIFIED",
            "evidence": self.CREATE_CONTRACT_EVIDENCE,
            "cleanup_policy": self.CREATE_CLEANUP_POLICY,
        }

    @staticmethod
    def _raise_for_status(status: int, payload: Any, raw: Any, operation: str) -> None:
        """Fail loudly on non-2xx internal API responses."""
        if 200 <= status < 300:
            return
        error_name = payload.get("errorName") if isinstance(payload, Mapping) else None
        if error_name == "Route:RouteNotMounted":
            raise RuntimeError(
                f"The internal API backing {operation} is not mounted on "
                f"this stack (Route:RouteNotMounted during {operation})"
            )
        detail = f" ({error_name})" if error_name else ""
        raise RuntimeError(
            f"Repository {operation} failed with HTTP {status}{detail}: "
            f"{str(raw)[:200]}"
        )

    def _internal_client(self) -> FoundryInternalClient:
        """Build an internal API client for the active profile."""
        from ..auth.base import ProfileNotFoundError
        from ..config.profiles import ProfileManager

        profile_name = self.profile or ProfileManager().get_active_profile()
        if not profile_name:
            raise ProfileNotFoundError(
                "No profile specified and no default profile configured. "
                "Run 'pltr configure configure' to set up authentication."
            )
        return FoundryInternalClient(profile_name)
