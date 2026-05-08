# war.gov/UFO Release 01 — seed metadata

These three files are the upstream release inventory for the May 8, 2026
PURSUE Release 01 on `https://www.war.gov/UFO/`. They are *not* the
underlying records — they are pointer/metadata files that let our `seed`
command build a manifest without re-hitting war.gov.

| file | what it is | rows |
|---|---|---|
| `pdf_manifest.tsv` | filename + URL + title + agency for every PDF | 120 |
| `uap-csv.csv`      | full release inventory (PDFs + videos + images) | 162 |
| `download_summary.json` | upstream download verification report | — |

## Provenance

These files were fetched verbatim on 2026-05-08 from
[`DenisSergeevitch/UFO-USA`](https://github.com/DenisSergeevitch/UFO-USA),
a community archive that converted the war.gov PDFs to markdown.

The rows in those files are URL-and-title facts about a public-domain U.S.
government release (17 U.S.C. § 105) — they are not protected expression
on either end. We cite the upstream repo because **it spared us a few
gigabytes of redundant load on war.gov** during initial enumeration.
Attribution beats re-fetching.

## Building the manifest from these seeds

From the repo root:

```bash
python -m uap_archive seed \
  --tsv manifests/seeds/wargov-release-1/pdf_manifest.tsv \
  --csv manifests/seeds/wargov-release-1/uap-csv.csv \
  --out manifests/by-agency/wargov.jsonl
```

The output is `manifests/by-agency/wargov.jsonl` with one JSONL line per
unique URL (PDFs, video thumbnails, modal images), deduplicated on
`object_id`.

## Refreshing seeds

When future tranches drop (`release_2/`, `release_3/`, etc.), watch the
upstream repo or, once the war.gov scraper proves stable, run
`python -m uap_archive discover --source wargov` instead.
