"""Guard: CAPABILITIES.md is generated and never stale.

There is no runtime `pltr capabilities` command any more -- the MCP parity
scorecard is a generated report. This regenerates it from the same derived
manifest and fails if the committed file has drifted, so the parity claim
cannot rot the way the hand-maintained version did.

To fix a failure: `python -m pltr.capabilities`.
"""

from __future__ import annotations

import pathlib

from pltr.capabilities import render_markdown

CAPABILITIES_MD = pathlib.Path(__file__).resolve().parents[1] / "CAPABILITIES.md"


def test_capabilities_doc_is_current():
    expected = render_markdown()
    actual = CAPABILITIES_MD.read_text(encoding="utf-8")
    assert actual == expected, (
        "CAPABILITIES.md is stale. Regenerate it: python -m pltr.capabilities"
    )
