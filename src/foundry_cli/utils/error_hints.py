"""Recovery hints attached to agent-envelope error entries.

Trace analysis of agent sessions showed a ~32% tool-call failure rate whose
canonical recovery was fail -> tool_search -> retry, because error envelopes
reported what failed without teaching the fix. Each rule below maps one
positively recognized (command context, error condition) pair to a concrete
hint. A rule fires only when its condition is recognized -- never on a
generic match -- so unrelated errors carry no hint at all.

Every command and flag named in a hint is verified against the registered
app in tests/test_error_hints.py; do not name a command or flag here that
``pfoundry ... --help`` does not show.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Optional

import click
from typer.core import TyperCommand

# Class 1: agents pass a branch *name* ("master") where dependency commands
# require an ontology/global branch RID; omitting --branch also succeeds.
BRANCH_RID_HINT = (
    "--branch expects a branch RID (e.g. ri.branch..branch.<uuid>), not a "
    "branch name like 'master'; omit --branch for server-default branch "
    "semantics."
)

# Class 2: agents probe existence by calling object-type-get/action-type-get
# with name variants; resolve checks existence and identity in one call.
ONTOLOGY_GET_NOT_FOUND_HINT = (
    "Do not probe name variants with repeated gets: `foundry ontology resolve` "
    "(--kind object-type|action-type with exactly one of --api-name/--rid) "
    "maps API name <-> RID <-> internal IDs and checks existence in one "
    "call, or `foundry ontology object-type-list` enumerates object types."
)

# Class 3: upsert invocations fail on missing flags or malformed definitions.
OBJECT_TYPE_UPSERT_HINT = (
    "object-type-upsert requires --api-name --display-name --primary-key "
    "--backing-dataset and is a dry-run unless --apply is passed; for a "
    "guided path that preflights and verifies the modification use "
    "`foundry ontology object-type-guarded-upsert`."
)

ACTION_TYPE_UPSERT_HINT = (
    "action-type-upsert requires --definition pointing at an ActionTypeCreate "
    "JSON file ('-' reads stdin) and is a dry-run unless --apply is passed; "
    "for object types, `foundry ontology object-type-guarded-upsert` preflights "
    "and verifies the modification."
)

# Typed SDK error names a chained exception may carry for an ontology get
# that missed. Matching runs on both the exception class name and the SDK's
# ``name`` attribute, mirroring guarded_upsert._is_object_type_not_found.
_ONTOLOGY_GET_NOT_FOUND_NAMES = frozenset(
    {
        "ObjectTypeNotFound",
        "OntologyObjectTypeNotFound",
        "ActionTypeNotFound",
        "OntologyActionTypeNotFound",
    }
)


def _walk_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield an exception and its cause/context chain, cycle-safe."""
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _chain_error_names(exc: Optional[BaseException]) -> Iterator[str]:
    """Yield class names and SDK ``name`` attributes along the chain."""
    if exc is None:
        return
    for candidate in _walk_chain(exc):
        yield type(candidate).__name__
        sdk_name = getattr(candidate, "name", None)
        if isinstance(sdk_name, str):
            yield sdk_name


def _is_branch_misuse(exc: Optional[BaseException], entry: Mapping[str, Any]) -> bool:
    if entry.get("error_class") == "branch-not-found":
        return True
    return "BranchNotFound" in _chain_error_names(exc)


def _is_ontology_get_not_found(
    exc: Optional[BaseException], entry: Mapping[str, Any]
) -> bool:
    if entry.get("errorName") in _ONTOLOGY_GET_NOT_FOUND_NAMES:
        return True
    return bool(_ONTOLOGY_GET_NOT_FOUND_NAMES.intersection(_chain_error_names(exc)))


def _is_upsert_invocation_error(
    exc: Optional[BaseException], entry: Mapping[str, Any]
) -> bool:
    # "usage" entries come from HintedUsageCommand (missing/extra flags);
    # "validation" entries from _exit_on_validation_error (rejected dry-run).
    if entry.get("type") in ("usage", "validation"):
        return True
    if isinstance(exc, (click.UsageError, json.JSONDecodeError, OSError)):
        return True
    from ..services.errors import FoundryApiError

    if isinstance(exc, FoundryApiError):
        return exc.status_code in (400, 422) or exc.validation_details is not None
    return False


@dataclass(frozen=True)
class HintRule:
    """One recognized (command context, error condition) -> hint mapping.

    ``contexts`` restricts the rule to named commands (an empty set would
    fire everywhere and is not used: speculative hints are worse than none).
    """

    contexts: frozenset
    matches: Callable[[Optional[BaseException], Mapping[str, Any]], bool]
    hint: str


_HINT_RULES = (
    HintRule(frozenset({"dependency"}), _is_branch_misuse, BRANCH_RID_HINT),
    HintRule(
        frozenset({"object-type-get", "action-type-get"}),
        _is_ontology_get_not_found,
        ONTOLOGY_GET_NOT_FOUND_HINT,
    ),
    HintRule(
        frozenset({"object-type-upsert"}),
        _is_upsert_invocation_error,
        OBJECT_TYPE_UPSERT_HINT,
    ),
    HintRule(
        frozenset({"action-type-upsert"}),
        _is_upsert_invocation_error,
        ACTION_TYPE_UPSERT_HINT,
    ),
)


def resolve_error_hint(
    context: str = "",
    *,
    exc: Optional[BaseException] = None,
    entry: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Return the recovery hint for a recognized failure, else None.

    ``context`` is the command name (e.g. "object-type-get", "dependency");
    ``exc``/``entry`` carry the failure itself. Returns None for anything
    not positively recognized, so callers attach hints additively.
    """
    error_entry = entry or {}
    for rule in _HINT_RULES:
        if rule.contexts and context not in rule.contexts:
            continue
        if rule.matches(exc, error_entry):
            return rule.hint
    return None


class HintedUsageCommand(TyperCommand):
    """Turn Click usage errors into hinted envelope entries under --agent.

    A missing/extra flag raises UsageError during argument parsing, before
    the command body runs -- so without this hook an agent gets empty stdout
    and exit 2 with nothing actionable to read. Under --agent the error is
    buffered as a typed entry (with a recovery hint when one is registered
    for this command name); the already-registered close callback then
    flushes exactly one envelope. Human output is untouched: non-agent mode
    re-raises immediately and Click prints its usual usage message.
    """

    def make_context(self, info_name, args, parent=None, **extra):
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except click.UsageError as exc:
            from .agent_output import agent_mode_enabled, buffer_agent_payload

            if agent_mode_enabled():
                entry = {"type": "usage", "message": str(exc)}
                hint = resolve_error_hint(self.name or "", exc=exc, entry=entry)
                if hint:
                    entry["hint"] = hint
                buffer_agent_payload(None, errors=[entry])
            raise
