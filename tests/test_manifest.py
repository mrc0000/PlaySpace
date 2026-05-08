"""Manifest schema, idempotency, and JSONL stable-write."""

from __future__ import annotations

from pathlib import Path

from uap_archive.manifest import (
    DigitalObject,
    merge_record,
    nara_object_id,
    now_iso,
    read_manifest,
    wargov_object_id,
    write_manifest,
)


def _obj(**overrides) -> DigitalObject:
    base = dict(
        object_id="nara:1:do:abcdef12",
        naid=1,
        parent_series_naid=1,
        agency="FAA",
        title="t",
        object_url="https://example.com/a.pdf",
        object_filename="a.pdf",
        media_type="application/pdf",
        size_bytes=10,
        sha256=None,
        etag='"v1"',
        last_modified="2026-05-08T12:00:00Z",
        captured_at=now_iso(),
        source="nara-catalog",
    )
    base.update(overrides)
    return DigitalObject(**base)


def test_object_id_deterministic():
    a = nara_object_id(123, "https://example.com/x.pdf")
    b = nara_object_id(123, "https://example.com/x.pdf")
    assert a == b
    assert a != nara_object_id(123, "https://example.com/y.pdf")


def test_wargov_object_id_distinguishes_pages():
    a = wargov_object_id("https://www.war.gov/UFO/", "https://www.war.gov/UFO/x.pdf")
    b = wargov_object_id("https://www.war.gov/UFO/agencies/", "https://www.war.gov/UFO/x.pdf")
    assert a != b


def test_roundtrip_jsonl(tmp_path: Path):
    p = tmp_path / "x.jsonl"
    o1 = _obj()
    o2 = _obj(object_id="nara:2:do:00000000", naid=2, object_url="https://example.com/b.pdf")
    write_manifest(p, {o1.object_id: o1, o2.object_id: o2})
    loaded = read_manifest(p)
    assert set(loaded) == {o1.object_id, o2.object_id}
    assert loaded[o1.object_id].object_url == "https://example.com/a.pdf"


def test_write_is_sorted_and_stable(tmp_path: Path):
    p = tmp_path / "x.jsonl"
    objs = {
        "z": _obj(object_id="z"),
        "a": _obj(object_id="a"),
        "m": _obj(object_id="m"),
    }
    write_manifest(p, objs)
    lines = p.read_text().splitlines()
    ids = [line.split('"object_id":"')[1].split('"')[0] for line in lines]
    assert ids == ["a", "m", "z"]


def test_merge_unchanged_etag_keeps_sha(tmp_path: Path):
    existing = {}
    o1 = _obj(sha256="cafe" * 16, etag='"abc"')
    existing, changed = merge_record(existing, o1)
    assert changed
    o2 = _obj(sha256=None, etag='"abc"', captured_at="2026-06-01T00:00:00Z")
    existing, changed = merge_record(existing, o2)
    assert not changed
    assert existing[o1.object_id].sha256 == "cafe" * 16
    assert existing[o1.object_id].captured_at == "2026-06-01T00:00:00Z"


def test_merge_changed_etag_updates_record():
    existing = {}
    o1 = _obj(etag='"v1"')
    existing, _ = merge_record(existing, o1)
    o2 = _obj(etag='"v2"', size_bytes=999)
    existing, changed = merge_record(existing, o2)
    assert changed
    assert existing[o1.object_id].size_bytes == 999
