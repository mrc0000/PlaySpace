# UAP Disclosure Archive

A manifest-first index of the **May 8, 2026** U.S. UAP disclosure data —
a directory of every public digital object on `war.gov/UFO/` and across the
U.S. National Archives **Record Group 615** agency series, with sha256
checksums and a resumable downloader so readers on slow or intermittent
connections can pull a usable subset.

## What's in this repo

- `manifests/by-agency/*.jsonl` — one digital object per line, with the
  original government URL, size, etag, and (after verification) sha256.
  This is the primary artifact.
- `src/uap_archive/` — Python tooling: discover, siptest, fetch, verify, index.
- `docs/` — runbook, etiquette policy, pipeline notes.

**This repo does not host the bulk files.** It is a *manifest-and-code* layer.
Readers run the included downloader to pull blobs from the original
government sources directly.

## Sources

| Surface | URL |
|---|---|
| War.gov UFO portal | <https://www.war.gov/UFO/> |
| NARA RG-615 collection | <https://www.archives.gov/research/topics/uaps/rg-615> |
| FAA series (NAID 493468575) | <https://catalog.archives.gov/id/493468575> |
| US NRC series (NAID 488808322) | <https://catalog.archives.gov/id/488808322> |
| ODNI series (NAID 493468579) | <https://catalog.archives.gov/id/493468579> |
| NSA series (NAID 580103959) | <https://catalog.archives.gov/id/580103959> |
| DoS series (NAID 608806625) | <https://catalog.archives.gov/id/608806625> |

License of the source data: U.S. federal government works, public domain
under 17 U.S.C. § 105. See [`ATTRIBUTION.md`](./ATTRIBUTION.md).

## Quick start

```bash
# clone + set up
git clone https://github.com/mrc0000/PlaySpace.git
cd PlaySpace
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 1) read what's there without downloading anything — Phase 1 manifest is
#    already committed at manifests/by-agency/wargov.jsonl (263 entries
#    seeded from a community mirror so we never had to re-hit war.gov)
jq -r '.title' manifests/by-agency/wargov.jsonl | head

# 2) regenerate the seeded manifest if you update the seed files
python -m uap_archive seed \
    --tsv manifests/seeds/wargov-release-1/pdf_manifest.tsv \
    --csv manifests/seeds/wargov-release-1/uap-csv.csv \
    --out manifests/by-agency/wargov.jsonl

# 3a) RECOMMENDED for NARA: download the per-collection ZIPs from
#     https://www.archives.gov/research/catalog/catalog-bulk-downloads/uap-bulk-download
#     and ingest the JSON metadata that comes alongside them. This avoids
#     the catalog API entirely (it has a 10,000-queries/month/key cap).
python -m uap_archive bulk --json /path/to/faa-metadata.json --agency FAA
python -m uap_archive bulk --json /path/to/nrc-metadata.json --agency NRC
python -m uap_archive bulk --json /path/to/odni-metadata.json --agency ODNI
python -m uap_archive bulk --json /path/to/nsa-metadata.json --agency NSA
python -m uap_archive bulk --json /path/to/dos-metadata.json --agency DOS

# Unsure about the JSON shape? Probe before writing:
python -m uap_archive bulk --json /path/to/file.json --agency FAA --inspect

# 3b) ALTERNATIVE — live catalog API (rate-limit-aware)
python -m uap_archive discover --source FAA --max-records 25
python -m uap_archive siptest --agency FAA --sample 5

# 4) pull a slice — capped at 500 MB at 1 req/s, resumable
python -m uap_archive fetch --agency FAA --max-bytes 500000000 --rps 1

# 5) verify checksums
python -m uap_archive verify --agency FAA
```

Set your contact email so government servers can reach you if they need to:

```bash
git config user.email you@example.com
```

## Why manifests-only

We do **not** rehost on Internet Archive, GitHub Releases, or torrents
ourselves. Every blob is pulled from the original government source by
each reader. Tradeoffs:

- ✅ Repo stays under 50 MB; clones are cheap on poor connections.
- ✅ No re-distribution legal risk; sources stay authoritative.
- ✅ Etiquette is centralized (rate limit, User-Agent, `robots.txt`) — see
  [`docs/etiquette.md`](./docs/etiquette.md).
- ⚠️ If many readers run `fetch` simultaneously they'll all hit gov servers.
  README asks for coordination: prefer copying via USB/sneakernet from a
  peer who already pulled.
- ⚠️ If a record is withdrawn after capture, only readers who already
  fetched it have a copy. The manifest preserves the URL and `captured_at`.

If you want a torrent or rehosted bundle, that's downstream of this repo —
build it from the manifest and please link back here.

## Status

- **Phase 1**: war.gov manifest. ✅ committed at `manifests/by-agency/wargov.jsonl`
  — 263 records (117 PDFs + 137 thumbnails + 8 modal images + 1 other),
  seeded from [`DenisSergeevitch/UFO-USA`](https://github.com/DenisSergeevitch/UFO-USA)
  to avoid re-loading war.gov. Live HTML scraper available too via
  `python -m uap_archive discover --source wargov`.
- **Phase 2**: NARA catalog walk for all five agency NAIDs. ✅ client + discover module ready;
  run live on your machine — this repo's CI does not hit gov servers.
- **Phase 3**: optional offline HTML browser of the manifest. Pending.

Run live discovery on your own machine — this repo's CI does not hit gov
servers.

## License

Code + manifests: [CC0-1.0](./LICENSE). Underlying data: public domain
(17 U.S.C. § 105).
