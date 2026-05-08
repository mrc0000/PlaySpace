"""Seed-based discovery: build manifests from a curated upstream list.

Useful when:
  - The data source has been mirrored elsewhere and we trust the URL list
  - We want a Phase-1 manifest without hitting the source server at all

Currently supports the war.gov/UFO Release 01 metadata pulled from:
  https://github.com/DenisSergeevitch/UFO-USA  (community archive of the
  PURSUE Release 01 corpus; the upstream metadata files describe
  public-domain U.S. government works)
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from uap_archive.config import WARGOV_URL
from uap_archive.manifest import DigitalObject, now_iso, wargov_object_id

log = logging.getLogger(__name__)

_OK_LINE = re.compile(r"^\[\d+/\d+\] ok (?P<filename>.+?) bytes=(?P<size>\d+)\s*$")


_AGENCY_NORMALIZE = {
    "FBI": "FBI",
    "DEPARTMENT OF WAR": "DOW",
    "DEPARTMENT OF STATE": "DOS",
    "NASA": "NASA",
    "": "WARGOV",
    "N/A": "WARGOV",
}


def _normalize_agency(label: str) -> str:
    return _AGENCY_NORMALIZE.get((label or "").strip().upper(), label.strip().upper() or "WARGOV")


def parse_curl_log(path: Path) -> dict[str, int]:
    """Parse the upstream curl_download.log into {filename: size_bytes}.

    Lines look like: ``[2/120] ok 65_HS1-...Section_2.pdf bytes=118380300``.
    """
    out: dict[str, int] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _OK_LINE.match(line)
            if m:
                out[m.group("filename")] = int(m.group("size"))
    return out


def parse_pdf_manifest_tsv(path: Path, *, source_page: str = WARGOV_URL) -> list[DigitalObject]:
    """Parse the pdf_manifest.tsv layout used by DenisSergeevitch/UFO-USA.

    Columns: filename, url, title, agency, release_date, incident_date, incident_location.
    No header row. URLs that point to the same blob multiple times collapse to
    one DigitalObject (object_id is deterministic on the URL).
    """
    objects: dict[str, DigitalObject] = {}
    captured = now_iso()

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            if not row or len(row) < 4:
                continue
            filename = row[0].strip()
            url = row[1].strip()
            title = row[2].strip() if len(row) > 2 else ""
            agency = _normalize_agency(row[3] if len(row) > 3 else "")
            if not url or not url.startswith("http"):
                continue
            obj_id = wargov_object_id(source_page, url)
            obj = DigitalObject(
                object_id=obj_id,
                naid=None,
                parent_series_naid=None,
                agency=agency,
                title=title or filename,
                object_url=url,
                object_filename=filename or url.rsplit("/", 1)[-1],
                media_type="application/pdf" if url.lower().endswith(".pdf") else None,
                size_bytes=None,
                etag=None,
                last_modified=None,
                captured_at=captured,
                source="war.gov",
            )
            # Idempotent: dedupe rows that point at the same URL.
            objects.setdefault(obj_id, obj)

    return list(objects.values())


def parse_uap_csv(path: Path, *, source_page: str = WARGOV_URL) -> list[DigitalObject]:
    """Parse the wider uap-csv.csv (PDFs + videos + images, 162 rows).

    Column layout (per upstream): Redaction, Release Date, Title, Type,
    Video Pairing, PDF Pairing, Description Blurb, DVIDS Video ID, Video Title,
    Agency, Incident Date, Incident Location, PDF | Image Link, Modal Image, ...
    The CSV has multi-line cells, so use csv.reader's RFC-4180 mode.
    """
    objects: dict[str, DigitalObject] = {}
    captured = now_iso()

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            agency = _normalize_agency(row.get("Agency", ""))
            title = (row.get("Title") or "").strip().strip("\n")
            type_ = (row.get("Type") or "").strip().upper()
            primary_url = (row.get("PDF | Image Link") or "").strip()
            modal_url = (row.get("Modal Image") or "").strip()
            dvids_id = (row.get("DVIDS Video ID") or "").strip()
            incident_date = (row.get("Incident Date") or "").strip()
            location = (row.get("Incident Location") or "").strip()

            for url in (primary_url, modal_url):
                if not url or not url.startswith("http"):
                    continue
                filename = url.rsplit("/", 1)[-1]
                obj_id = wargov_object_id(source_page, url)
                # Skip duplicates so primary URL wins over thumbnail.
                if obj_id in objects:
                    continue
                lower = url.lower()
                media_type = (
                    "application/pdf" if lower.endswith(".pdf")
                    else "video/mp4" if lower.endswith(".mp4")
                    else "image/jpeg" if lower.endswith((".jpg", ".jpeg"))
                    else "image/png" if lower.endswith(".png")
                    else None
                )
                pretty_title = title or filename
                if dvids_id and "video" in type_.lower():
                    pretty_title = f"{pretty_title} (DVIDS {dvids_id})"
                if location and location != "N/A":
                    pretty_title = f"{pretty_title} — {location}"
                if incident_date and incident_date != "N/A":
                    pretty_title = f"{pretty_title} ({incident_date})"

                objects[obj_id] = DigitalObject(
                    object_id=obj_id,
                    naid=None,
                    parent_series_naid=None,
                    agency=agency,
                    title=pretty_title or filename,
                    object_url=url,
                    object_filename=filename,
                    media_type=media_type,
                    size_bytes=None,
                    etag=None,
                    last_modified=None,
                    captured_at=captured,
                    source="war.gov",
                )

    return list(objects.values())


def seed_manifest(
    *,
    tsv: Path | None = None,
    csv_path: Path | None = None,
    curl_log: Path | None = None,
    out: Path,
) -> int:
    """Combine seed parsers, write the resulting manifest. Returns object count.

    If ``curl_log`` is provided, sizes from it are merged into matching
    records by ``object_filename``.
    """
    from uap_archive.manifest import merge_record, read_manifest, write_manifest

    if not tsv and not csv_path:
        raise SystemExit("seed: pass at least one of --tsv or --csv")

    existing = read_manifest(out)

    # Prefer TSV records (which carry original-case filenames) when the same
    # URL appears in both sources; CSV fills in URLs that TSV doesn't cover.
    by_id: dict[str, DigitalObject] = {}
    if tsv and tsv.exists():
        for r in parse_pdf_manifest_tsv(tsv):
            by_id.setdefault(r.object_id, r)
    if csv_path and csv_path.exists():
        for r in parse_uap_csv(csv_path):
            by_id.setdefault(r.object_id, r)

    sizes = parse_curl_log(curl_log) if curl_log else {}
    if sizes:
        sizes_lc = {k.lower(): v for k, v in sizes.items()}
        for oid, r in list(by_id.items()):
            key = r.object_filename.lower()
            if r.size_bytes is None and key in sizes_lc:
                by_id[oid] = r.model_copy(update={"size_bytes": sizes_lc[key]})

    for obj in by_id.values():
        existing, _ = merge_record(existing, obj)
    write_manifest(out, existing)
    return len(existing)
