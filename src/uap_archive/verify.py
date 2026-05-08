"""Re-hash everything in staging/ for a given agency, write a verify-report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from uap_archive import config
from uap_archive.manifest import DigitalObject, iter_manifest, now_iso, write_manifest

CHUNK = 64 * 1024


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def verify_agency(agency: str) -> dict:
    manifest_path = config.BY_AGENCY_DIR / f"{agency.lower()}.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"no manifest: {manifest_path}")

    ok, mismatch, missing = [], [], []
    updated: dict[str, DigitalObject] = {}
    files_seen: set[Path] = set()

    for obj in iter_manifest(manifest_path):
        target = config.STAGING_DIR / obj.agency.lower() / str(obj.naid or 0) / obj.object_filename
        if not target.exists():
            missing.append(obj.object_id)
            updated[obj.object_id] = obj
            continue
        files_seen.add(target)
        sha = _sha256(target)
        if obj.sha256 and obj.sha256 != sha:
            mismatch.append({"object_id": obj.object_id,
                             "expected": obj.sha256, "actual": sha})
            updated[obj.object_id] = obj
            continue
        ok.append(obj.object_id)
        updated[obj.object_id] = obj.model_copy(update={
            "sha256": sha,
            "size_bytes": target.stat().st_size,
        })

    # Detect extras
    extra: list[str] = []
    agency_root = config.STAGING_DIR / agency.lower()
    if agency_root.exists():
        for p in agency_root.rglob("*"):
            if p.is_file() and p not in files_seen and p.suffix != ".part":
                extra.append(str(p.relative_to(config.STAGING_DIR)))

    write_manifest(manifest_path, updated)
    report = {
        "agency": agency.upper(),
        "generated_at": now_iso(),
        "ok": ok,
        "mismatch": mismatch,
        "missing": missing,
        "extra": extra,
    }
    out = config.MANIFESTS_DIR / f"verify-report-{agency.lower()}-{now_iso().replace(':', '')}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
