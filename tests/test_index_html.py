"""Static index renderer: substitution, structure, no marker leakage."""

from __future__ import annotations

import json
import re
from pathlib import Path

from uap_archive.index_html import build_site
from uap_archive.manifest import DigitalObject, now_iso, write_manifest


def _obj(i: int, agency: str = "FAA", size: int | None = 1024) -> DigitalObject:
    return DigitalObject(
        object_id=f"nara:1:do:{i:08x}",
        naid=i,
        parent_series_naid=1,
        agency=agency,
        title=f"Test record {i} <html-safe?>",
        object_url=f"https://example.com/{i}.pdf",
        object_filename=f"{i}.pdf",
        media_type="application/pdf",
        size_bytes=size,
        captured_at=now_iso(),
        source="nara-catalog",
    )


def test_build_site_renders_self_contained_html(tmp_path: Path):
    manifests = tmp_path / "manifests"
    write_manifest(
        manifests / "by-agency" / "faa.jsonl",
        {o.object_id: o for o in (_obj(i) for i in range(5))},
    )
    write_manifest(
        manifests / "by-agency" / "nrc.jsonl",
        {o.object_id: o for o in (_obj(i + 100, "NRC", size=2048) for i in range(3))},
    )

    out = tmp_path / "site" / "index.html"
    info = build_site(manifests, out)
    assert info["record_count"] == 8
    assert out.exists()

    text = out.read_text(encoding="utf-8")

    # Single self-contained file: no external script/style/img references.
    assert "<script src=" not in text
    assert '<link rel="stylesheet"' not in text

    # Markers all substituted.
    for marker in ("__DATA_JSON__", "__META_JSON__", "__N_RECORDS__", "__SOURCES_LABEL__"):
        assert marker not in text, f"{marker} not substituted"

    # The embedded JSON parses and has the right shape.
    m = re.search(r'<script id="data"[^>]*>(.*?)</script>', text, re.DOTALL)
    assert m
    rows = json.loads(m.group(1))
    assert len(rows) == 8
    assert {r["agency"] for r in rows} == {"FAA", "NRC"}

    # HTML escaping is applied to titles via JS at render-time, but the JSON
    # itself preserves the raw value — confirm round-trip.
    assert any("<html-safe?>" in r["title"] for r in rows)


def test_build_site_handles_empty_manifest(tmp_path: Path):
    manifests = tmp_path / "manifests"
    (manifests / "by-agency").mkdir(parents=True)
    out = tmp_path / "site" / "index.html"
    info = build_site(manifests, out)
    assert info["record_count"] == 0
    assert out.exists()
    assert "[]" in out.read_text()  # empty data array
