"""End-user resumable downloader. Pulls blobs from the original government source.

Goes through the same RateLimitedClient as discover so etiquette is uniform.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from uap_archive import config
from uap_archive.manifest import DigitalObject, iter_manifest
from uap_archive.nara_client import RateLimitedClient

log = logging.getLogger(__name__)
CHUNK = 64 * 1024


def _target_path(obj: DigitalObject) -> Path:
    naid = obj.naid or 0
    return config.STAGING_DIR / obj.agency.lower() / str(naid) / obj.object_filename


async def _download_one(
    client: RateLimitedClient,
    obj: DigitalObject,
) -> tuple[str, int, str]:
    """Returns (status, bytes_written, sha256). Resumes if .part already exists."""
    target = _target_path(obj)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if obj.size_bytes and target.stat().st_size == obj.size_bytes:
            sha = _sha256_file(target)
            if obj.sha256 in (None, sha):
                return "skip", 0, sha
        # Size mismatch: clean restart.
        target.unlink()

    part = target.with_suffix(target.suffix + ".part")
    existing = part.stat().st_size if part.exists() else 0

    headers = {}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    h = hashlib.sha256()
    if existing > 0:
        with part.open("rb") as f:
            for block in iter(lambda: f.read(CHUNK), b""):
                h.update(block)

    written = 0
    async with client.stream("GET", obj.object_url, headers=headers) as r:
        if r.status_code == 416 and obj.size_bytes and existing == obj.size_bytes:
            # Already complete byte-wise.
            sha = h.hexdigest()
            part.replace(target)
            return "completed", 0, sha
        if r.status_code not in (200, 206):
            r.raise_for_status()
        if r.status_code == 200 and existing > 0:
            # Server ignored Range — start over.
            part.unlink(missing_ok=True)
            existing = 0
            h = hashlib.sha256()

        with part.open("ab") as f:
            async for chunk in r.aiter_bytes(CHUNK):
                f.write(chunk)
                h.update(chunk)
                written += len(chunk)

    sha = h.hexdigest()
    part.replace(target)
    return "ok", written, sha


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


async def fetch_agency(
    agency: str,
    *,
    rps: float,
    max_bytes: int | None = None,
) -> dict[str, int]:
    """Fetch every object for an agency, capped by `max_bytes`."""
    path = config.BY_AGENCY_DIR / f"{agency.lower()}.jsonl"
    if not path.exists():
        raise SystemExit(f"no manifest at {path}; run discover first")

    counters = {"ok": 0, "skip": 0, "fail": 0, "bytes_written": 0, "stopped_at_cap": 0}
    async with RateLimitedClient(rps=rps) as client:
        for obj in iter_manifest(path):
            if max_bytes is not None and counters["bytes_written"] >= max_bytes:
                counters["stopped_at_cap"] = 1
                break
            try:
                status, written, _sha = await _download_one(client, obj)
            except Exception as e:
                log.warning("fetch failed for %s: %s", obj.object_url, e)
                counters["fail"] += 1
                continue
            counters["bytes_written"] += written
            counters[status] = counters.get(status, 0) + 1
    return counters
