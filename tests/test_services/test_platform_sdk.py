"""Tests for local platform-SDK introspection (no network, no Foundry client)."""

from __future__ import annotations

from pathlib import Path

from pltr.services.platform_sdk import PlatformSdkService


CLIENT_PY = """
from functools import cached_property


class DemoClient:
    @cached_property
    def Widget(self):
        from foundry_sdk.v2.demo.widget import WidgetClient

        return WidgetClient(auth=self._auth)

    @cached_property
    def Gadget(self):
        from foundry_sdk.v2.demo.gadget import (
            GadgetClient,
        )  # NOQA

        return GadgetClient(auth=self._auth)
"""

WIDGET_PY = '''
class WidgetClient:
    """Client for widgets."""

    def get(self, widget_rid, request_timeout):
        """Get a widget by RID.

        Longer details here.
        """
        raise NotImplementedError

    def list(self, page_size=None):
        raise NotImplementedError

    def _hidden(self):
        raise NotImplementedError


class _WidgetClientRaw:
    pass


class AsyncWidgetClient:
    def get(self, widget_rid):
        """Async variant — must be ignored."""
'''

GADGET_PY = '''
class GadgetClient:
    def spin(self, *, speed):
        """Spin the gadget."""
'''


def _fake_sdk(tmp_path: Path) -> Path:
    demo = tmp_path / "v2" / "demo"
    demo.mkdir(parents=True)
    (demo / "_client.py").write_text(CLIENT_PY)
    (demo / "widget.py").write_text(WIDGET_PY)
    (demo / "gadget.py").write_text(GADGET_PY)
    (tmp_path / "v2" / "core").mkdir()  # no _client.py: skipped
    return tmp_path / "v2"


def _service(tmp_path: Path) -> PlatformSdkService:
    return PlatformSdkService(sdk_root=_fake_sdk(tmp_path), version="0.0.0-test")


class TestListApis:
    def test_enumerates_namespaces_resources_methods(self, tmp_path):
        result = _service(tmp_path).list_apis()
        assert result["status"] == "ok"
        assert result["version"] == "0.0.0-test"
        demo = result["namespaces"]["demo"]
        assert demo["resource_count"] == 2
        widget = demo["resources"]["Widget"]
        assert widget["module"] == "foundry_sdk.v2.demo.widget"
        names = [method["name"] for method in widget["methods"]]
        assert names == ["get", "list"]  # sync class only, no privates
        get = widget["methods"][0]
        assert get["summary"] == "Get a widget by RID."
        assert "widget_rid" in get["signature"]

    def test_skips_dirs_without_client(self, tmp_path):
        result = _service(tmp_path).list_apis()
        assert "core" not in result["namespaces"]


class TestApiReference:
    def test_method_reference_quotes_verbatim_docstring(self, tmp_path):
        result = _service(tmp_path).api_reference("demo.Widget.get")
        assert result["status"] == "ok"
        assert result["kind"] == "method"
        assert "Longer details here." in result["docstring"]

    def test_resource_reference(self, tmp_path):
        result = _service(tmp_path).api_reference("demo.Gadget")
        assert result["status"] == "ok"
        assert result["kind"] == "resource"
        assert result["methods"][0]["name"] == "spin"

    def test_namespace_reference(self, tmp_path):
        result = _service(tmp_path).api_reference("demo")
        assert result["status"] == "ok"
        assert result["kind"] == "namespace"
        assert result["resource_count"] == 2

    def test_unknown_namespace_lists_available(self, tmp_path):
        result = _service(tmp_path).api_reference("nope")
        assert result["status"] == "not-found"
        assert result["available"] == ["demo"]

    def test_unknown_method_lists_available(self, tmp_path):
        result = _service(tmp_path).api_reference("demo.Widget.nope")
        assert result["status"] == "not-found"
        assert result["available"] == ["get", "list"]

    def test_too_many_parts(self, tmp_path):
        result = _service(tmp_path).api_reference("a.b.c.d")
        assert result["status"] == "invalid"

    def test_empty_reference(self, tmp_path):
        result = _service(tmp_path).api_reference("  ")
        assert result["status"] == "invalid"


class TestInstalledPackage:
    """Smoke checks against the real pinned foundry-platform-sdk (local only)."""

    def test_real_package_lists_ontologies_namespace(self):
        result = PlatformSdkService().list_apis()
        assert result["status"] == "ok"
        assert "ontologies" in result["namespaces"]
        assert "Ontology" in result["namespaces"]["ontologies"]["resources"]

    def test_real_method_reference(self):
        result = PlatformSdkService().api_reference(
            "ontologies.Ontology.get_full_metadata"
        )
        assert result["status"] == "ok"
        assert "full Ontology metadata" in result["docstring"]
