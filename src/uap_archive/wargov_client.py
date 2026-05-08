"""Scrape https://www.war.gov/UFO/ for downloadable files. One-level deep follow."""

from __future__ import annotations

import contextlib
import logging
from urllib.parse import urldefrag, urljoin, urlparse

from selectolax.parser import HTMLParser

from uap_archive.config import WARGOV_URL
from uap_archive.manifest import DigitalObject, now_iso, wargov_object_id
from uap_archive.nara_client import RateLimitedClient

log = logging.getLogger(__name__)

# File extensions we treat as downloadable.
DOWNLOADABLE_EXTS = {
    ".pdf", ".mp4", ".mov", ".m4v", ".webm",
    ".tif", ".tiff", ".jpg", ".jpeg", ".png",
    ".zip", ".tar", ".gz", ".doc", ".docx", ".xlsx",
}


def _is_downloadable(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DOWNLOADABLE_EXTS)


def _is_wargov(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("war.gov")


def _normalize(base: str, href: str) -> str | None:
    if not href or href.startswith(("mailto:", "javascript:", "#", "tel:")):
        return None
    full, _ = urldefrag(urljoin(base, href))
    return full


def _extract_links(html: str, base_url: str) -> tuple[set[str], set[str]]:
    """Return (sub_pages, file_urls) — both within war.gov and absolute."""
    tree = HTMLParser(html)
    sub_pages: set[str] = set()
    files: set[str] = set()
    for node in tree.css("a[href]"):
        href = node.attributes.get("href")
        url = _normalize(base_url, href or "")
        if not url or not _is_wargov(url):
            continue
        if _is_downloadable(url):
            files.add(url)
        else:
            sub_pages.add(url)
    # Also catch <source>/<video> tags
    for node in tree.css("source[src], video[src], embed[src]"):
        src = node.attributes.get("src")
        url = _normalize(base_url, src or "")
        if url and _is_wargov(url) and _is_downloadable(url):
            files.add(url)
    return sub_pages, files


async def _head_metadata(client: RateLimitedClient, url: str) -> dict:
    """Try HEAD; on method not allowed fall back to a 0-byte ranged GET."""
    try:
        r = await client.head(url)
    except Exception as e:
        log.debug("HEAD failed for %s: %s", url, e)
        return {}
    out: dict = {}
    if "content-length" in r.headers:
        with contextlib.suppress(ValueError):
            out["size_bytes"] = int(r.headers["content-length"])
    if "etag" in r.headers:
        out["etag"] = r.headers["etag"]
    if "last-modified" in r.headers:
        out["last_modified"] = r.headers["last-modified"]
    if "content-type" in r.headers:
        out["media_type"] = r.headers["content-type"].split(";", 1)[0].strip()
    return out


async def discover_wargov(
    client: RateLimitedClient,
    landing_url: str = WARGOV_URL,
    max_depth: int = 1,
    snapshot_html_to: str | None = None,
) -> list[DigitalObject]:
    """
    BFS from the landing page, descend at most `max_depth` non-file pages.
    For every downloadable URL found, build a DigitalObject (size/etag via HEAD).
    """
    visited_pages: set[str] = set()
    queue: list[tuple[str, int]] = [(landing_url, 0)]
    found_files: dict[str, str] = {}  # url -> page_url

    while queue:
        page_url, depth = queue.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        try:
            r = await client.get(page_url)
        except Exception as e:
            log.warning("could not fetch %s: %s", page_url, e)
            continue
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            continue

        if snapshot_html_to and page_url == landing_url:
            try:
                from pathlib import Path as _P
                _P(snapshot_html_to).write_text(r.text, encoding="utf-8")
            except OSError:
                pass

        sub_pages, files = _extract_links(r.text, page_url)
        for f in files:
            found_files.setdefault(f, page_url)
        if depth < max_depth:
            for sp in sub_pages:
                if sp not in visited_pages:
                    queue.append((sp, depth + 1))

    objects: list[DigitalObject] = []
    for url, page_url in sorted(found_files.items()):
        meta = await _head_metadata(client, url)
        filename = urlparse(url).path.rsplit("/", 1)[-1] or "index"
        objects.append(DigitalObject(
            object_id=wargov_object_id(page_url, url),
            agency="WARGOV",
            title=None,
            object_url=url,
            object_filename=filename,
            media_type=meta.get("media_type"),
            size_bytes=meta.get("size_bytes"),
            etag=meta.get("etag"),
            last_modified=meta.get("last_modified"),
            captured_at=now_iso(),
            source="war.gov",
        ))
    return objects
