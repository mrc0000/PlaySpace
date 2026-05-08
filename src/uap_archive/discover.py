"""Discover stage: enumerate every digital object behind the source NAIDs / war.gov.

Outputs per-agency JSONL manifests. No blob downloads — only metadata + HEAD.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from uap_archive.config import (
    BY_AGENCY_DIR,
    MANIFESTS_DIR,
    ROOT_NAIDS,
    WARGOV_URL,
)
from uap_archive.manifest import (
    SCHEMA_VERSION,
    DigitalObject,
    merge_record,
    nara_object_id,
    now_iso,
    read_manifest,
    write_manifest,
    write_root_index,
)
from uap_archive.nara_client import (
    RateLimitedClient,
    extract_digital_objects,
)
from uap_archive.wargov_client import _head_metadata, discover_wargov

log = logging.getLogger(__name__)


async def discover_nara_agency(
    client: RateLimitedClient,
    agency: str,
    root_naid: int,
    *,
    max_records: int | None = None,
) -> list[DigitalObject]:
    """Walk children of root_naid recursively. Collect every digitalObject. HEAD each."""
    objects: list[DigitalObject] = []
    seen_naids: set[int] = set()
    stack: list[int] = [root_naid]
    count = 0

    while stack:
        if max_records is not None and count >= max_records:
            break
        naid = stack.pop()
        if naid in seen_naids:
            continue
        seen_naids.add(naid)

        async for child in client.nara_children(naid):
            count += 1
            if max_records is not None and count >= max_records:
                break

            src = child.get("_source", child) if isinstance(child, dict) else {}
            child_naid = src.get("naId") or src.get("naid")
            title = src.get("title")
            level = (src.get("levelOfDescription") or "").lower()

            for d in extract_digital_objects(child):
                meta = await _head_metadata(client, d["url"])
                objects.append(DigitalObject(
                    object_id=nara_object_id(int(child_naid or root_naid), d["url"]),
                    naid=int(child_naid) if child_naid else None,
                    parent_series_naid=root_naid,
                    agency=agency,
                    title=title,
                    object_url=d["url"],
                    object_filename=d["filename"],
                    media_type=meta.get("media_type") or d.get("media_type"),
                    size_bytes=meta.get("size_bytes") or d.get("size_bytes"),
                    etag=meta.get("etag"),
                    last_modified=meta.get("last_modified"),
                    captured_at=now_iso(),
                    source="nara-catalog",
                ))

            # Descend into non-leaf nodes (series → file unit → item).
            if child_naid and level not in ("item",):
                with contextlib.suppress(TypeError, ValueError):
                    stack.append(int(child_naid))

    return objects


def _merge_into_manifest(
    manifest_path: Path,
    new_objects: list[DigitalObject],
) -> tuple[int, int]:
    """Returns (added_or_updated, unchanged)."""
    existing = read_manifest(manifest_path)
    changed = 0
    for obj in new_objects:
        existing, was_changed = merge_record(existing, obj)
        if was_changed:
            changed += 1
    write_manifest(manifest_path, existing)
    return changed, len(new_objects) - changed


async def discover_source(
    source: str,
    *,
    rps: float,
    out_path: Path | None = None,
    max_records: int | None = None,
    root_override: int | None = None,
    snapshot_html_to: str | None = None,
) -> Path:
    """Run discovery for one source. `source` is "wargov" or an agency code (FAA, ...)."""
    BY_AGENCY_DIR.mkdir(parents=True, exist_ok=True)

    async with RateLimitedClient(rps=rps) as client:
        if source.lower() == "wargov":
            target = out_path or BY_AGENCY_DIR / "wargov.jsonl"
            objs = await discover_wargov(client, snapshot_html_to=snapshot_html_to)
        else:
            agency = source.upper()
            if root_override is not None:
                root = root_override
            elif agency in ROOT_NAIDS:
                root = ROOT_NAIDS[agency]
            else:
                raise SystemExit(f"unknown agency code: {agency}")
            target = out_path or BY_AGENCY_DIR / f"{agency.lower()}.jsonl"
            objs = await discover_nara_agency(
                client, agency, root, max_records=max_records,
            )

    changed, unchanged = _merge_into_manifest(target, objs)
    log.info("discover %s: %d new/changed, %d unchanged → %s",
             source, changed, unchanged, target)
    _refresh_root_index()
    return target


def _refresh_root_index() -> None:
    """Regenerate manifests/root.json from whatever JSONL files exist."""
    sources = []
    for p in sorted(BY_AGENCY_DIR.glob("*.jsonl")):
        n = sum(1 for _ in p.open("r", encoding="utf-8"))
        sources.append({
            "agency": p.stem.upper(),
            "manifest": str(p.relative_to(MANIFESTS_DIR.parent)),
            "object_count": n,
        })
    write_root_index(MANIFESTS_DIR / "root.json", sources)


__all__ = [
    "SCHEMA_VERSION",
    "WARGOV_URL",
    "discover_nara_agency",
    "discover_source",
]
