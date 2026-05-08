"""Manifest schema and JSONL I/O. Re-runs of discover are idempotent on object_id."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 1


class DigitalObject(BaseModel):
    """One downloadable file. One JSONL line = one DigitalObject."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    object_id: str
    naid: int | None = None
    parent_series_naid: int | None = None
    agency: str
    title: str | None = None
    object_url: str
    object_filename: str
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    captured_at: str
    source: Literal["nara-catalog", "war.gov"]
    license: str = "public-domain-usgov"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_object_id(source: str, *parts: str | int) -> str:
    """Deterministic ID. Source prefix + sha1 of joined parts (first 8 chars)."""
    payload = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:8]
    return f"{source}:do:{digest}"


def nara_object_id(naid: int, object_url: str) -> str:
    return f"nara:{naid}:do:{hashlib.sha1(object_url.encode()).hexdigest()[:8]}"


def wargov_object_id(page_url: str, object_url: str) -> str:
    a = hashlib.sha1(page_url.encode()).hexdigest()[:8]
    b = hashlib.sha1(object_url.encode()).hexdigest()[:8]
    return f"wargov:{a}:do:{b}"


def read_manifest(path: Path) -> dict[str, DigitalObject]:
    """Load JSONL into a dict keyed on object_id. Missing file → empty dict."""
    out: dict[str, DigitalObject] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = DigitalObject.model_validate_json(line)
            out[obj.object_id] = obj
    return out


def write_manifest(path: Path, records: dict[str, DigitalObject]) -> None:
    """Stable serialization: sort by object_id so diffs are minimal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for object_id in sorted(records):
            f.write(records[object_id].model_dump_json(exclude_none=False))
            f.write("\n")
    tmp.replace(path)


def iter_manifest(path: Path) -> Iterator[DigitalObject]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield DigitalObject.model_validate_json(line)


def merge_record(
    existing: dict[str, DigitalObject],
    new: DigitalObject,
) -> tuple[dict[str, DigitalObject], bool]:
    """Idempotent merge. Updates only on etag change. Returns (manifest, changed)."""
    prev = existing.get(new.object_id)
    if prev is None:
        existing[new.object_id] = new
        return existing, True
    if prev.etag and new.etag and prev.etag == new.etag:
        # Unchanged upstream — bump captured_at only.
        existing[new.object_id] = prev.model_copy(update={"captured_at": new.captured_at})
        return existing, False
    # Preserve sha256 if previously verified and URL identical.
    sha = prev.sha256 if (prev.object_url == new.object_url and prev.sha256) else new.sha256
    existing[new.object_id] = new.model_copy(update={"sha256": sha})
    return existing, True


def write_root_index(path: Path, sources: list[dict]) -> None:
    """`manifests/root.json` — top-level index of what's been discovered."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "sources": sources,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
