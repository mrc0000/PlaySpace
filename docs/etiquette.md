# Etiquette — being a good citizen of NARA & war.gov

These services host public-domain data, but every request still costs them
CPU, bandwidth, and wear. The point of this project is **manifest plus
checksums** so that, ideally, a single coordinated pull is enough for an
entire community.

## What's enforced in code

Everything in `src/uap_archive/nara_client.py`:

- **One User-Agent**, with our repo URL and a contact email pulled from
  `git config user.email` (or `UAP_ARCHIVE_CONTACT`). If they need to
  reach the maintainer, the UA tells them how.
- **Default 1 request per second**, globally. The CLI flag `--rps` can
  only lower the rate, never raise it.
- **At most 2 concurrent requests per host.**
- **Tenacity exponential backoff** (1, 2, 4, 8, 16 s, 5 attempts) on
  429 / 5xx / transport errors. `Retry-After` is honored.
- **Three consecutive 429s** triggers a 5-minute pause and halves the
  rate for the rest of the run.
- **`robots.txt` is consulted once per host** at startup. Disallowed paths
  raise `PermissionError` — the request never goes out.
- **Conditional GETs** (`If-None-Match` from the manifest's stored ETag)
  on rediscovery, so unchanged records don't re-stream.

## What we ask of operators

- Don't fork this repo and crank `--rps`. The default is the contract.
- If you maintain a mirror somewhere else (Internet Archive, a campus
  network share, a torrent), please link to it from the README so others
  can pull from you instead of the source.
- If you operate war.gov or NARA infrastructure and need this client to
  slow down or stop, please open an issue or email the contact in the
  User-Agent. We'll respect it.

## API rate cap (NARA)

NARA's Catalog API has a **default cap of 10,000 queries per month per
API key** (per their public docs). A naive recursive walk of a single
RG-615 series can spend hundreds of queries; doing all five agencies
back-to-back can exceed the monthly quota and lock you out.

For that reason this project recommends the *bulk-download* path:

- NARA publishes per-collection ZIPs + JSON metadata at
  <https://www.archives.gov/research/catalog/catalog-bulk-downloads/uap-bulk-download>,
  refreshed at least 3× a year.
- `python -m uap_archive bulk --json <metadata.json> --agency FAA`
  ingests that JSON without making a single live API call.
- The live catalog walk in `discover.py` is still available for cases
  where you need fresher data than the last bulk refresh — but it
  defaults to 1 rps and you should obtain an API key for any non-trivial
  walk so you don't share quota with anonymous users.

## Snapshot vs canonical

Manifests record `captured_at` per object. NARA may withdraw, redact, or
reorganize records after we capture them. Our policy:

- The original `object_url` and the source's current behavior remain
  authoritative — readers should treat the live source as canonical.
- We keep the manifest line and any locally fetched copy. On rediscovery
  if a record is gone, we surface a `withdrawn_at` field rather than
  silently deleting.
- We do not "preserve" or "leak" anything that was not already public on
  the day we fetched it.

## Public domain

NARA records and war.gov works are U.S. federal government works, public
domain under 17 U.S.C. § 105. This repo's code and manifests are CC0.
See [`../LICENSE`](../LICENSE) and [`../ATTRIBUTION.md`](../ATTRIBUTION.md).
