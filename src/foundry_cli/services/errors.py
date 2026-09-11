"""Typed Foundry API errors that survive to the agent envelope.

Services historically wrapped failures as ``RuntimeError(f"Failed to ...: {self._describe_error(e)}")``,
which flattened Foundry's structured error (errorName, errorCode,
errorInstanceId, safe parameters) into one string. ``FoundryApiError`` keeps
those fields so commands can hand agents an actionable error entry instead of
forcing blind retries.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


class FoundryApiError(RuntimeError):
    """A Foundry API failure with its structured fields preserved."""

    def __init__(
        self,
        message: str,
        *,
        error_name: Optional[str] = None,
        error_code: Optional[str] = None,
        error_instance_id: Optional[str] = None,
        safe_parameters: Optional[Mapping[str, Any]] = None,
        validation_details: Optional[Any] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.error_name = error_name
        self.error_code = error_code
        self.error_instance_id = error_instance_id
        self.safe_parameters = dict(safe_parameters or {})
        self.validation_details = validation_details
        self.status_code = status_code

    def error_entry(self) -> Dict[str, Any]:
        """Serialize as one typed agent-envelope error entry."""
        entry: Dict[str, Any] = {
            "type": "foundry_api",
            "message": str(self),
        }
        if self.error_name:
            entry["errorName"] = self.error_name
        if self.error_code:
            entry["errorCode"] = self.error_code
        if self.error_instance_id:
            entry["errorInstanceId"] = self.error_instance_id
        if self.safe_parameters:
            entry["safeParameters"] = dict(self.safe_parameters)
        if self.validation_details is not None:
            entry["validationDetails"] = self.validation_details
        if self.status_code is not None:
            entry["statusCode"] = self.status_code
        return entry


def foundry_error_from_sdk(exc: BaseException, *, context: str = "") -> FoundryApiError:
    """Convert a foundry-platform-sdk exception, preserving its fields.

    ``PalantirRPCException`` carries ``name``, ``error_code``,
    ``error_instance_id`` and ``parameters``; anything else degrades to a
    message-only error. The original exception's string form is JSON-ish and
    verbose, so the message prefers the SDK's structured description.
    """
    error_name = getattr(exc, "name", None)
    error_code = getattr(exc, "error_code", None)
    error_instance_id = getattr(exc, "error_instance_id", None)
    parameters = getattr(exc, "parameters", None)
    description = getattr(exc, "error_description", None)
    if error_name or error_code or error_instance_id:
        message = description or (str(error_name) if error_name else str(exc))
        if context:
            message = f"{context}: {message}"
        return FoundryApiError(
            message,
            error_name=error_name,
            error_code=error_code,
            error_instance_id=error_instance_id,
            safe_parameters=parameters if isinstance(parameters, Mapping) else None,
        )
    message = f"{context}: {exc}" if context else str(exc)
    return FoundryApiError(message)


def foundry_error_from_conjure(
    status: int,
    parsed: Any,
    raw: str,
    *,
    context: str = "",
) -> FoundryApiError:
    """Build a typed error from an internal (Conjure-style) response.

    Internal endpoints return ``errorName``/``errorCode``/``errorInstanceId``
    and Conjure ``parameters`` in the payload; some return a union with an
    ``error.errors`` list (validation details). Unknown payloads degrade to a
    message-only error carrying the HTTP status.
    """
    payload = parsed if isinstance(parsed, Mapping) else {}
    error_name = payload.get("errorName")
    error_code = payload.get("errorCode")
    error_instance_id = payload.get("errorInstanceId")
    parameters = payload.get("parameters")
    validation_details: Optional[Any] = None
    union_error = payload.get("error")
    if isinstance(union_error, Mapping) and isinstance(union_error.get("errors"), list):
        validation_details = union_error["errors"]
    message = payload.get("message") or payload.get("errorMessage") or ""
    if not message and error_name:
        message = str(error_name)
    if not message:
        message = raw[:500] if isinstance(raw, str) and raw else f"HTTP {status}"
    if context:
        message = f"{context}: {message}"
    return FoundryApiError(
        message,
        error_name=error_name,
        error_code=error_code,
        error_instance_id=error_instance_id,
        safe_parameters=parameters if isinstance(parameters, Mapping) else None,
        validation_details=validation_details,
        status_code=status,
    )
