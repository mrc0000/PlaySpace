"""NARA client: shape extraction, robots.txt enforcement, retry on 429."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uap_archive.nara_client import (
    RateLimitedClient,
    _extract_record_list,
    extract_digital_objects,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_record_list_modern_shape():
    payload = json.loads((FIXTURES / "sample_record.json").read_text())
    recs = _extract_record_list(payload)
    assert len(recs) == 2
    assert recs[0]["naId"] == 493468612


def test_extract_record_list_empty():
    assert _extract_record_list({"body": {"hits": {"hits": []}}}) == []
    assert _extract_record_list({}) == []


def test_extract_digital_objects():
    payload = json.loads((FIXTURES / "sample_record.json").read_text())
    rec = _extract_record_list(payload)[0]
    dos = extract_digital_objects(rec)
    assert len(dos) == 1
    assert dos[0]["url"].endswith("report.pdf")
    assert dos[0]["filename"] == "faa-uap-2024-11.pdf"
    assert dos[0]["size_bytes"] == 4823104


@pytest.mark.asyncio
async def test_robots_txt_disallow_blocks_request(httpx_mock):
    httpx_mock.add_response(
        url="https://catalog.archives.gov/robots.txt",
        status_code=200,
        text="User-agent: *\nDisallow: /api/v2/records/\n",
    )
    async with RateLimitedClient(rps=1000) as client:
        with pytest.raises(PermissionError):
            await client.get("https://catalog.archives.gov/api/v2/records/123")


@pytest.mark.asyncio
async def test_429_retried_and_eventually_succeeds(httpx_mock):
    httpx_mock.add_response(
        url="https://catalog.archives.gov/robots.txt",
        status_code=200,
        text="User-agent: *\nAllow: /\n",
    )
    # First two responses 429, third 200
    httpx_mock.add_response(
        url="https://catalog.archives.gov/api/v2/records/123",
        status_code=429,
        headers={"retry-after": "0"},
    )
    httpx_mock.add_response(
        url="https://catalog.archives.gov/api/v2/records/123",
        status_code=429,
        headers={"retry-after": "0"},
    )
    httpx_mock.add_response(
        url="https://catalog.archives.gov/api/v2/records/123",
        status_code=200,
        json={"naId": 123},
    )

    async with RateLimitedClient(rps=1000) as client:
        r = await client.get("https://catalog.archives.gov/api/v2/records/123")
        assert r.status_code == 200
        assert r.json()["naId"] == 123
