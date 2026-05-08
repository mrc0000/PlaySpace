"""war.gov scraper — link extraction + integration via pytest-httpx."""

from __future__ import annotations

from pathlib import Path

import pytest

from uap_archive.nara_client import RateLimitedClient
from uap_archive.wargov_client import _extract_links, _is_downloadable, discover_wargov

FIXTURES = Path(__file__).parent / "fixtures"


def test_is_downloadable():
    assert _is_downloadable("https://www.war.gov/UFO/files/x.pdf")
    assert _is_downloadable("https://www.war.gov/UFO/x.MP4")
    assert not _is_downloadable("https://www.war.gov/UFO/")
    assert not _is_downloadable("https://www.war.gov/UFO/index.html")


def test_extract_links_filters_external_and_mailto():
    html = (FIXTURES / "wargov_snapshot.html").read_text()
    sub_pages, files = _extract_links(html, "https://www.war.gov/UFO/")
    # All file URLs are absolute and within war.gov
    for f in files:
        assert f.startswith("https://www.war.gov/")
    # Catches relative + absolute + <source>
    assert "https://www.war.gov/UFO/files/odni-2026-summary.pdf" in files
    assert "https://www.war.gov/UFO/files/dod-incident-log.pdf" in files
    assert "https://www.war.gov/UFO/media/clip-2024-fl.mp4" in files
    assert "https://www.war.gov/UFO/media/secondary-clip.mp4" in files
    # Sub-page link
    assert "https://www.war.gov/UFO/agencies/" in sub_pages
    # External + mailto excluded
    assert not any("example.com" in u for u in files | sub_pages)
    assert not any(u.startswith("mailto:") for u in files | sub_pages)


@pytest.mark.asyncio
async def test_discover_wargov_with_mocked_http(httpx_mock):
    landing = (FIXTURES / "wargov_snapshot.html").read_text()
    subpage = (FIXTURES / "wargov_subpage.html").read_text()

    # robots.txt for www.war.gov: permissive
    httpx_mock.add_response(
        url="https://www.war.gov/robots.txt",
        status_code=200,
        text="User-agent: *\nAllow: /\n",
    )
    httpx_mock.add_response(
        url="https://www.war.gov/UFO/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=landing,
    )
    httpx_mock.add_response(
        url="https://www.war.gov/UFO/agencies/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=subpage,
    )
    # HEADs for every file URL — return some metadata
    file_urls = [
        "https://www.war.gov/UFO/files/odni-2026-summary.pdf",
        "https://www.war.gov/UFO/files/dod-incident-log.pdf",
        "https://www.war.gov/UFO/media/clip-2024-fl.mp4",
        "https://www.war.gov/UFO/media/secondary-clip.mp4",
        "https://www.war.gov/UFO/files/faa-tower-recordings.pdf",
        "https://www.war.gov/UFO/files/nrc-incident-2018.pdf",
    ]
    for u in file_urls:
        httpx_mock.add_response(
            method="HEAD",
            url=u,
            status_code=200,
            headers={
                "content-length": "12345",
                "etag": '"abc"',
                "content-type": "application/pdf" if u.endswith(".pdf") else "video/mp4",
                "last-modified": "Wed, 07 May 2026 14:00:00 GMT",
            },
        )

    async with RateLimitedClient(rps=1000) as client:  # turbo for tests
        objs = await discover_wargov(client, landing_url="https://www.war.gov/UFO/")

    urls = {o.object_url for o in objs}
    assert urls == set(file_urls)
    pdf = next(o for o in objs if o.object_url.endswith("odni-2026-summary.pdf"))
    assert pdf.size_bytes == 12345
    assert pdf.etag == '"abc"'
    assert pdf.media_type == "application/pdf"
    assert pdf.source == "war.gov"
    assert pdf.agency == "WARGOV"
    assert pdf.captured_at  # set
