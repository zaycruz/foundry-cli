"""Local introspection of the installed ``foundry-platform-sdk`` package.

The platform SDK API surface is enumerated from the installed package's own
source (``foundry_sdk/v2/<namespace>/_client.py`` for the republished contract, and
``foundry_sdk/v2/<namespace>/<resource>.py`` for method signatures and real
docstrings) using ``ast`` — no client is constructed and no network call is
made. Everything reported here is verifiable against the pinned package.
"""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path
from typing import Any, Optional


class PlatformSdkError(RuntimeError):
    """Raised when the installed SDK surface cannot be introspected."""


def _default_sdk_root() -> Path:
    try:
        import foundry_sdk  # noqa: PLC0415
    except ImportError as exc:
        raise PlatformSdkError(
            "foundry-platform-sdk is not installed in this environment"
        ) from exc
    root = Path(foundry_sdk.__file__).resolve().parent / "v2"
    if not root.is_dir():
        raise PlatformSdkError(f"foundry_sdk v2 package not found at {root}")
    return root


def _sdk_version() -> str:
    try:
        return importlib.metadata.version("foundry-platform-sdk")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class PlatformSdkService:
    """Enumerate and describe the installed platform SDK's API surface."""

    def __init__(
        self,
        *,
        sdk_root: Optional[Path] = None,
        version: Optional[str] = None,
    ) -> None:
        self.sdk_root = Path(sdk_root) if sdk_root else _default_sdk_root()
        self.version = version or _sdk_version()

    # -- listing ---------------------------------------------------------------

    def list_apis(self) -> dict[str, Any]:
        """Return namespaces -> resources -> methods for the installed SDK."""
        namespaces: dict[str, Any] = {}
        for namespace_dir in sorted(self.sdk_root.iterdir()):
            client_file = namespace_dir / "_client.py"
            if not namespace_dir.is_dir() or not client_file.is_file():
                continue
            resources = self._namespace_resources(namespace_dir, client_file)
            if resources:
                namespaces[namespace_dir.name] = {
                    "resources": resources,
                    "resource_count": len(resources),
                    "method_count": sum(
                        len(resource["methods"]) for resource in resources.values()
                    ),
                }
        return {
            "status": "ok",
            "sdk": "foundry-platform-sdk",
            "version": self.version,
            "sdk_root": str(self.sdk_root),
            "namespaces": namespaces,
            "namespace_count": len(namespaces),
            "sources": [str(self.sdk_root)],
        }

    # -- reference ---------------------------------------------------------------

    def api_reference(self, dotted: str) -> dict[str, Any]:
        """Describe one namespace, resource, or method (``a[.b[.c]]``).

        Method docstrings are quoted verbatim from the installed package.
        """
        parts = [part for part in dotted.strip().split(".") if part]
        if not parts:
            return {"status": "invalid", "reason": "reference must not be empty"}
        if len(parts) > 3:
            return {
                "status": "invalid",
                "reason": "reference must be namespace[.resource[.method]]",
            }
        listing = self.list_apis()
        namespaces = listing["namespaces"]
        namespace = parts[0]
        if namespace not in namespaces:
            return {
                "status": "not-found",
                "reason": f"no namespace '{namespace}' in the installed SDK",
                "available": sorted(namespaces),
            }
        if len(parts) == 1:
            return {
                "status": "ok",
                "kind": "namespace",
                "namespace": namespace,
                **namespaces[namespace],
                "sdk": listing["sdk"],
                "version": listing["version"],
            }
        resource_name = parts[1]
        resources = namespaces[namespace]["resources"]
        if resource_name not in resources:
            return {
                "status": "not-found",
                "reason": f"no resource '{resource_name}' in namespace '{namespace}'",
                "available": sorted(resources),
            }
        resource = resources[resource_name]
        if len(parts) == 2:
            return {
                "status": "ok",
                "kind": "resource",
                "namespace": namespace,
                "resource": resource_name,
                **resource,
                "sdk": listing["sdk"],
                "version": listing["version"],
            }
        method_name = parts[2]
        method = next(
            (m for m in resource["methods"] if m["name"] == method_name), None
        )
        if method is None:
            return {
                "status": "not-found",
                "reason": f"no method '{method_name}' on {namespace}.{resource_name}",
                "available": [m["name"] for m in resource["methods"]],
            }
        return {
            "status": "ok",
            "kind": "method",
            "namespace": namespace,
            "resource": resource_name,
            **method,
            "sdk": listing["sdk"],
            "version": listing["version"],
        }

    # -- introspection helpers -----------------------------------------------------

    def _namespace_resources(
        self, namespace_dir: Path, client_file: Path
    ) -> dict[str, Any]:
        resources: dict[str, Any] = {}
        for resource_name, module_name in _client_resource_map(client_file).items():
            module_file = namespace_dir / f"{module_name}.py"
            if not module_file.is_file():
                continue
            resources[resource_name] = {
                "module": f"foundry_sdk.v2.{namespace_dir.name}.{module_name}",
                "methods": _resource_methods(module_file),
            }
        return resources


def _client_resource_map(client_file: Path) -> dict[str, str]:
    """Map resource property -> module name from a namespace ``_client.py``.

    Reads the ``@cached_property`` getters whose body imports ``XClient`` from
    ``foundry_sdk.v2.<namespace>.<module>`` — the SDK's own resource wiring.
    """
    tree = ast.parse(client_file.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_cached_property = any(
            (isinstance(d, ast.Name) and d.id == "cached_property")
            or (isinstance(d, ast.Attribute) and d.attr == "cached_property")
            for d in node.decorator_list
        )
        if not is_cached_property:
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.ImportFrom)
                and inner.module
                and inner.module.startswith("foundry_sdk.v2.")
            ):
                for alias in inner.names:
                    if alias.name.endswith("Client") and not alias.name.startswith(
                        "Async"
                    ):
                        mapping[node.name] = inner.module.rsplit(".", 1)[-1]
    return mapping


def _sync_client_class(tree: ast.Module) -> Optional[ast.ClassDef]:
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name.endswith("Client")
            and not node.name.startswith(("Async", "_"))
        ):
            return node
    return None


def _resource_methods(module_file: Path) -> list[dict[str, Any]]:
    tree = ast.parse(module_file.read_text(encoding="utf-8"))
    client = _sync_client_class(tree)
    if client is None:
        return []
    methods: list[dict[str, Any]] = []
    for node in client.body:
        if not isinstance(node, ast.FunctionDef):
            continue  # sync client only; async variants live in Async*Client
        if node.name.startswith("_") or node.name == "__init__":
            continue
        docstring = ast.get_docstring(node) or ""
        first_line = docstring.strip().splitlines()[0] if docstring.strip() else ""
        methods.append(
            {
                "name": node.name,
                "signature": f"({_format_args(node.args)})",
                "summary": first_line,
                "docstring": docstring,
            }
        )
    return methods


def _format_args(args: ast.arguments) -> str:
    names = [arg.arg for arg in args.posonlyargs + args.args]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return ", ".join(names)
