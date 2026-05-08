# Runbook — using this archive on a slow link

## What this gives you

- A complete, deduplicated index of every public digital object in:
  - `https://www.war.gov/UFO/`
  - NARA RG-615 series for FAA, NRC, ODNI, NSA, DoS
- A resumable downloader so you can pull as much as you have bandwidth for.
- Every line in the manifests has the original government URL plus a
  sha256 (after you run `verify`), so you can hand a file to a friend on
  USB and they can confirm it wasn't tampered with.

## Day-zero (5 minutes)

```bash
git clone https://github.com/mrc0000/PlaySpace.git
cd PlaySpace
uv venv && source .venv/bin/activate
uv pip install -e .
git config user.email you@example.com   # so government servers can reach you
```

Now you have the manifests in `manifests/by-agency/*.jsonl`. Open one in
any text editor — these are the canonical artifact. You can browse the
data without ever hitting the network again:

```bash
jq -s 'group_by(.agency)|map({agency:.[0].agency,n:length,bytes:(map(.size_bytes//0)|add)})' \
  manifests/by-agency/*.jsonl
```

## Pull a slice — bandwidth-bounded

```bash
# 500 MB cap, 1 req/sec (gentle on gov servers)
python -m uap_archive fetch --agency FAA --max-bytes 500000000 --rps 1
```

The downloader:

- Writes to `staging/<agency>/<naid>/<filename>.part` while in flight.
- Resumes on restart via HTTP `Range` requests — kill it any time.
- Verifies sha256 once a file completes.

## Verify what you have

```bash
python -m uap_archive verify --agency FAA
```

This re-hashes everything in `staging/`, fills in `sha256` in the manifest
for files you have locally, and writes a JSON report under
`manifests/verify-report-*.json`.

## Sneakernet handoff

```bash
# producer (good internet):
python -m uap_archive fetch --agency FAA
python -m uap_archive verify --agency FAA
rsync -av staging/ /media/usb/uap-staging/
cp manifests/by-agency/faa.jsonl /media/usb/

# consumer (no internet):
rsync -av /media/usb/uap-staging/ ~/PlaySpace/staging/
cp /media/usb/faa.jsonl ~/PlaySpace/manifests/by-agency/faa.jsonl
python -m uap_archive verify --agency FAA   # confirms integrity
```

## When discovery becomes stale

Re-run `discover` against the same source. The merge is idempotent on
`object_id`. Records whose ETag is unchanged just get a refreshed
`captured_at`. New records appear; sha256 of already-verified records is
preserved.

```bash
python -m uap_archive discover --source FAA
python -m uap_archive siptest        # refresh size projection
```
