"""Ingest NARA's bulk-download JSON metadata into our manifest.

NARA publishes per-collection ZIPs at:
    https://www.archives.gov/research/catalog/catalog-bulk-downloads/uap-bulk-download

Each ZIP is paired with a JSON metadata file describing every record. By
ingesting that JSON, we avoid hitting the catalog API at all (it has a
10,000-queries-per-month-per-key limit) and our manifest stays aligned
with whatever NARA last published.

The parser tolerates several JSON shapes (top-level list, NDJSON, or
{"records":[...]} envelope) and several field-name conventions
(camelCase, snake_case). When in doubt, run `uap-archive bulk --inspect`
to dump the structure so we can adjust.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from uap_archive.manifest import (
    DigitalObject,
    merge_record,
    nara_object_id,
    now_iso,
    read_manifest,
    write_manifest,
)

log = logging.getLogger(__name__)


def _first(d: dict, *keys: str) -> Any:
    """Return the first present, non-None, non-empty value among keys."""
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None


def _coerce_records(payload: Any) -> list[dict]:
    """Normalize whatever JSON shape NARA hands us into a list of records."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        # Try common envelope keys.
        for key in ("records", "items", "results", "hits", "data"):
            v = payload.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
            if isinstance(v, dict) and isinstance(v.get("hits"), list):
                return [r for r in v["hits"] if isinstance(r, dict)]
        # Single-record document.
        return [payload]
    return []


def _load_payload(path: Path) -> list[dict]:
    """JSON or NDJSON. NDJSON detection: first non-blank line parses as a dict."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        try:
            return _coerce_records(json.loads(text))
        except json.JSONDecodeError:
            pass
    # Fall through to NDJSON.
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError as e:
            log.warning("skipping bad NDJSON line: %s", e)
    return out


def _digital_objects(record: dict) -> Iterable[dict]:
    src = record.get("_source", record) if isinstance(record, dict) else {}
    candidates = (
        _first(src, "digitalObjects", "digital_objects", "DigitalObjects") or []
    )
    for d in candidates:
        if not isinstance(d, dict):
            continue
        url = _first(d, "objectUrl", "object_url", "url", "ObjectUrl")
        if not url:
            continue
        yield {
            "url": url,
            "filename": _first(d, "objectFilename", "filename", "ObjectFilename")
                       or url.rsplit("/", 1)[-1],
            "media_type": _first(d, "mediaType", "media_type", "contentType"),
            "size_bytes": _first(d, "size", "sizeBytes", "fileSize"),
        }


def parse(path: Path, *, agency: str, root_naid: int | None = None) -> list[DigitalObject]:
    """Return a list of DigitalObject built from a NARA bulk-download JSON file."""
    payload = _load_payload(path)
    captured = now_iso()
    out: list[DigitalObject] = []

    for rec in payload:
        src = rec.get("_source", rec) if isinstance(rec, dict) else {}
        naid = _first(src, "naId", "naid", "NAID")
        title = _first(src, "title", "Title", "name")
        parent = _first(src, "parentNaId", "parent_na_id", "parentSeriesNaId") or root_naid

        try:
            naid_int = int(naid) if naid is not None else None
        except (TypeError, ValueError):
            naid_int = None
        try:
            parent_int = int(parent) if parent is not None else None
        except (TypeError, ValueError):
            parent_int = None

        for d in _digital_objects(rec):
            out.append(DigitalObject(
                object_id=nara_object_id(naid_int or root_naid or 0, d["url"]),
                naid=naid_int,
                parent_series_naid=parent_int,
                agency=agency.upper(),
                title=str(title) if title else None,
                object_url=d["url"],
                object_filename=d["filename"],
                media_type=d.get("media_type"),
                size_bytes=int(d["size_bytes"]) if d.get("size_bytes") else None,
                etag=None,
                last_modified=None,
                captured_at=captured,
                source="nara-catalog",
            ))
    return out


def ingest(
    path: Path,
    *,
    agency: str,
    out: Path,
    root_naid: int | None = None,
) -> int:
    """Parse a NARA JSON metadata file and merge into a per-agency manifest."""
    existing = read_manifest(out)
    new = parse(path, agency=agency, root_naid=root_naid)
    for obj in new:
        existing, _ = merge_record(existing, obj)
    write_manifest(out, existing)
    return len(existing)


def inspect(path: Path) -> dict:
    """Probe the file shape without producing a manifest. For diagnosis."""
    payload = _load_payload(path)
    sample = payload[0] if payload else {}

    sample_src = sample.get("_source", sample) if isinstance(sample, dict) else {}
    fields = sorted(sample_src.keys()) if isinstance(sample_src, dict) else []
    do_count = sum(1 for _ in _digital_objects(sample))
    return {
        "record_count": len(payload),
        "first_record_top_keys": sorted(sample.keys()) if isinstance(sample, dict) else [],
        "first_record_source_fields": fields,
        "first_record_digital_objects": do_count,
        "naid_present": "naId" in fields or "naid" in fields,
    }
