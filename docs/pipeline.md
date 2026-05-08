# Pipeline overview

```
            ┌──────────────────┐
            │  config.py       │  ROOT_NAIDS, USER_AGENT, RATE_LIMIT
            └──────────────────┘
                     ▲
                     │
   ┌─────────────────┴────────────────┐
   │       nara_client.py             │  rate limit + retry + robots.txt
   │       (one HTTP client; etiquette│
   │        baked in)                 │
   └────┬─────────────────────┬───────┘
        │                     │
        ▼                     ▼
 ┌──────────────┐      ┌──────────────────┐
 │ wargov_client│      │ discover_nara_   │
 │   .py        │      │   agency()       │
 │  (HTML scrape│      │ (catalog v2 walk)│
 └──────┬───────┘      └────────┬─────────┘
        │                       │
        └──────────┬────────────┘
                   ▼
           ┌──────────────────┐       ┌──────────────────────────┐
           │ discover.py      │ ────▶ │ manifests/by-agency/*.jsonl
           │ merge_record()   │       │ manifests/root.json
           │ (idempotent)     │       └──────────────────────────┘
           └────────┬─────────┘
                    ▼
              ┌──────────────────┐
              │ siptest.py       │ ────▶ manifests/size-projection.md
              └──────────────────┘
                    ▼ (optional, for end-users)
              ┌──────────────────┐
              │ fetch.py         │ ────▶ staging/<agency>/<naid>/<file>
              │  (Range resume)  │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ verify.py        │ ────▶ manifests/verify-report-*.json
              │  (sha256 audit)  │       updates manifest sha256 in-place
              └──────────────────┘
```

## Stage outputs

| stage | input | output | network? |
|---|---|---|---|
| `discover --source wargov` | `https://www.war.gov/UFO/` | `manifests/by-agency/wargov.jsonl` | yes (HTML + HEAD) |
| `discover --source FAA` | `ROOT_NAIDS["FAA"]` | `manifests/by-agency/faa.jsonl` | yes (API + HEAD) |
| `siptest [--agency X]` | per-agency JSONL | `manifests/size-projection.md` | no |
| `fetch --agency X` | per-agency JSONL | `staging/X/.../`  | yes (GET, Range) |
| `verify --agency X` | manifest + staging | `manifests/verify-report-*.json` + sha256 in JSONL | no |

## Idempotency

`merge_record()` keys on `object_id`:

- `nara:<naid>:do:<sha1(url)[:8]>` for catalog records
- `wargov:<sha1(page)[:8]>:do:<sha1(url)[:8]>` for war.gov files

Re-running `discover` against the same source does not perturb unchanged
records (ETag match → only `captured_at` is updated). Manifest writes are
sorted by `object_id` so git diffs stay minimal across runs.
