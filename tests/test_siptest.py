from __future__ import annotations

from pathlib import Path

from uap_archive import config as cfg
from uap_archive.manifest import DigitalObject, now_iso, write_manifest
from uap_archive.siptest import siptest_agency, write_projection_md


def _obj(i: int, size: int) -> DigitalObject:
    return DigitalObject(
        object_id=f"nara:1:do:{i:08x}",
        naid=i,
        parent_series_naid=1,
        agency="FAA",
        object_url=f"https://example.com/{i}.pdf",
        object_filename=f"{i}.pdf",
        size_bytes=size,
        captured_at=now_iso(),
        source="nara-catalog",
    )


def test_siptest_projects_total(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cfg, "BY_AGENCY_DIR", tmp_path / "by-agency")
    monkeypatch.setattr(cfg, "MANIFESTS_DIR", tmp_path)
    objs = {o.object_id: o for o in (_obj(i, 1000) for i in range(50))}
    write_manifest(tmp_path / "by-agency" / "faa.jsonl", objs)
    row = siptest_agency("FAA", sample=10)
    assert row["object_count"] == 50
    assert row["sampled"] == 10
    assert row["mean_size"] == 1000
    assert row["projected_total"] == 50_000
    out = tmp_path / "size-projection.md"
    write_projection_md([row], out)
    md = out.read_text()
    assert "FAA" in md
    assert "50" in md
