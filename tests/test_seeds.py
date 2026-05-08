"""Seed parser: TSV ingestion, agency normalization, dedup."""

from __future__ import annotations

from pathlib import Path

from uap_archive.seeds import parse_pdf_manifest_tsv, seed_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_tsv_dedupes_on_url():
    objs = parse_pdf_manifest_tsv(FIXTURES / "wargov_seed_sample.tsv")
    # 4 valid rows but two share the same URL → 3 distinct + 1 broken filtered out.
    urls = {o.object_url for o in objs}
    assert len(urls) == 3
    titles = {o.title for o in objs}
    assert "65_HS1-834228961_62-HQ-83894_Section_10" in titles


def test_agency_normalization():
    objs = parse_pdf_manifest_tsv(FIXTURES / "wargov_seed_sample.tsv")
    by_agency = {o.agency for o in objs}
    assert "FBI" in by_agency
    assert "DOW" in by_agency  # "Department of War" → DOW
    assert "NASA" in by_agency
    # "Department of State" was not in this sample
    assert "DOS" not in by_agency


def test_seed_manifest_writes_jsonl(tmp_path: Path):
    out = tmp_path / "wargov.jsonl"
    n = seed_manifest(tsv=FIXTURES / "wargov_seed_sample.tsv", csv_path=None, out=out)
    assert n == 3
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    # All entries have proper schema
    for line in lines:
        assert '"source":"war.gov"' in line
        assert '"object_id":"wargov:' in line


def test_seed_manifest_idempotent(tmp_path: Path):
    out = tmp_path / "wargov.jsonl"
    n1 = seed_manifest(tsv=FIXTURES / "wargov_seed_sample.tsv", csv_path=None, out=out)
    first_bytes = out.read_bytes()
    n2 = seed_manifest(tsv=FIXTURES / "wargov_seed_sample.tsv", csv_path=None, out=out)
    second_bytes = out.read_bytes()
    assert n1 == n2 == 3
    # Stable sort means re-running yields byte-identical output (etags would
    # differ if we re-fetched; from a static seed they don't).
    assert first_bytes == second_bytes
