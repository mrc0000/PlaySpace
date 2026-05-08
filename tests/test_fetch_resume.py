"""Resumable fetch: kill mid-stream, restart with Range, sha256 stays correct."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from uap_archive import config
from uap_archive.fetch import _download_one
from uap_archive.manifest import DigitalObject, now_iso
from uap_archive.nara_client import RateLimitedClient


def _obj(url: str, filename: str = "a.pdf", size: int | None = None) -> DigitalObject:
    return DigitalObject(
        object_id="nara:1:do:11111111",
        naid=42,
        parent_series_naid=1,
        agency="FAA",
        title=None,
        object_url=url,
        object_filename=filename,
        media_type="application/pdf",
        size_bytes=size,
        captured_at=now_iso(),
        source="nara-catalog",
    )


@pytest.mark.asyncio
async def test_full_download_and_skip(httpx_mock, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "STAGING_DIR", tmp_path)
    payload = b"hello-uap-archive" * 200
    sha = hashlib.sha256(payload).hexdigest()

    httpx_mock.add_response(
        url="https://catalog.archives.gov/robots.txt",
        status_code=200, text="User-agent: *\nAllow: /\n",
    )
    httpx_mock.add_response(
        url="https://catalog.archives.gov/file.pdf",
        status_code=200, content=payload,
        headers={"content-length": str(len(payload))},
    )

    obj = _obj("https://catalog.archives.gov/file.pdf", size=len(payload))
    async with RateLimitedClient(rps=1000) as c:
        status, written, observed = await _download_one(c, obj)
    assert status == "ok"
    assert written == len(payload)
    assert observed == sha


@pytest.mark.asyncio
async def test_resume_uses_range_request(httpx_mock, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "STAGING_DIR", tmp_path)
    payload = b"abcdef" * 100  # 600 bytes
    sha = hashlib.sha256(payload).hexdigest()
    half = len(payload) // 2

    # Pre-seed a half-written .part file so we exercise the resume path.
    part_dir = tmp_path / "faa" / "42"
    part_dir.mkdir(parents=True)
    part_file = part_dir / "a.pdf.part"
    part_file.write_bytes(payload[:half])

    httpx_mock.add_response(
        url="https://catalog.archives.gov/robots.txt",
        status_code=200, text="User-agent: *\nAllow: /\n",
    )
    # Server returns a 206 with the remaining bytes
    httpx_mock.add_response(
        url="https://catalog.archives.gov/file.pdf",
        status_code=206,
        content=payload[half:],
        headers={
            "content-length": str(len(payload) - half),
            "content-range": f"bytes {half}-{len(payload)-1}/{len(payload)}",
        },
    )

    obj = _obj("https://catalog.archives.gov/file.pdf", size=len(payload))
    async with RateLimitedClient(rps=1000) as c:
        status, written, observed = await _download_one(c, obj)
    assert status == "ok"
    assert written == len(payload) - half
    assert observed == sha
    final = tmp_path / "faa" / "42" / "a.pdf"
    assert final.read_bytes() == payload
    assert not part_file.exists()


@pytest.mark.asyncio
async def test_size_match_skips(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "STAGING_DIR", tmp_path)
    payload = b"already-here"
    target = tmp_path / "faa" / "42" / "a.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    obj = _obj("https://catalog.archives.gov/file.pdf", size=len(payload))
    async with RateLimitedClient(rps=1000) as c:
        status, written, _sha = await _download_one(c, obj)
    assert status == "skip"
    assert written == 0
