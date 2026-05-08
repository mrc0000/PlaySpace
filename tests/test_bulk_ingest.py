"""Bulk ingest: tolerant of NARA's various JSON shapes."""

from __future__ import annotations

from pathlib import Path

from uap_archive.bulk_ingest import ingest, inspect, parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_top_level_list():
    objs = parse(FIXTURES / "nara_bulk_sample.json", agency="FAA", root_naid=493468575)
    # 1 PDF + 1 PDF + 1 JPEG; record 3 has no digital objects.
    assert len(objs) == 3
    assert all(o.agency == "FAA" for o in objs)
    assert all(o.parent_series_naid == 493468575 for o in objs)
    assert {o.media_type for o in objs} == {"application/pdf", "image/jpeg"}


def test_parse_envelope_with_underscore_keys():
    objs = parse(FIXTURES / "nara_bulk_envelope.json", agency="NRC", root_naid=488808322)
    assert len(objs) == 1
    assert objs[0].object_filename == "nrc-uap-series-index.pdf"
    assert objs[0].agency == "NRC"


def test_parse_ndjson():
    objs = parse(FIXTURES / "nara_bulk_ndjson.json", agency="NSA", root_naid=580103959)
    assert len(objs) == 2
    assert {o.naid for o in objs} == {580103959, 580103960}
    assert {o.size_bytes for o in objs} == {100, 200}


def test_ingest_writes_manifest(tmp_path: Path):
    out = tmp_path / "faa.jsonl"
    n = ingest(FIXTURES / "nara_bulk_sample.json", agency="FAA",
               out=out, root_naid=493468575)
    assert n == 3
    assert out.exists()


def test_ingest_idempotent(tmp_path: Path):
    out = tmp_path / "faa.jsonl"
    ingest(FIXTURES / "nara_bulk_sample.json", agency="FAA", out=out, root_naid=493468575)
    bytes_before = out.read_bytes()
    ingest(FIXTURES / "nara_bulk_sample.json", agency="FAA", out=out, root_naid=493468575)
    assert out.read_bytes() == bytes_before


def test_inspect_reports_shape():
    info = inspect(FIXTURES / "nara_bulk_sample.json")
    assert info["record_count"] == 3
    assert info["first_record_digital_objects"] == 1
    assert info["naid_present"]
