"""`python -m uap_archive <subcommand>` entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from uap_archive import __version__
from uap_archive.config import DEFAULT_RPS


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rps", type=float, default=DEFAULT_RPS,
                   help="global requests/sec ceiling (default: %(default)s)")
    p.add_argument("-v", "--verbose", action="count", default=0)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="uap-archive",
                                 description="UAP Disclosure Archive — manifest tooling")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_bulk = sub.add_parser("bulk",
                            help="ingest NARA bulk-download JSON metadata into a manifest")
    p_bulk.add_argument("--json", dest="json_path", type=Path, required=True,
                        help="path to NARA-published JSON metadata file (from the bulk download)")
    p_bulk.add_argument("--agency", required=True,
                        help="agency code: FAA / NRC / ODNI / NSA / DOS / OSD")
    p_bulk.add_argument("--root-naid", type=int, default=None,
                        help="parent series NAID; auto-fills from config.ROOT_NAIDS if known")
    p_bulk.add_argument("--out", type=Path, default=None,
                        help="manifest path (default: manifests/by-agency/<agency>.jsonl)")
    p_bulk.add_argument("--inspect", action="store_true",
                        help="probe the JSON shape without writing a manifest")
    _add_common(p_bulk)

    p_seed = sub.add_parser("seed",
                            help="build wargov manifest from a curated TSV/CSV (offline)")
    p_seed.add_argument("--tsv", type=Path, default=None,
                        help="pdf_manifest.tsv path (DenisSergeevitch/UFO-USA layout)")
    p_seed.add_argument("--csv", type=Path, default=None,
                        help="uap-csv.csv path (full 162-row release inventory)")
    p_seed.add_argument("--out", type=Path,
                        default=Path("manifests/by-agency/wargov.jsonl"))
    _add_common(p_seed)

    p_disc = sub.add_parser("discover", help="enumerate digital objects (manifest only)")
    p_disc.add_argument("--source", default="wargov",
                        help="'wargov' or an agency code (FAA/NRC/ODNI/NSA/DOS)")
    p_disc.add_argument("--root", type=int, default=None,
                        help="override NAID (advanced)")
    p_disc.add_argument("--max-records", type=int, default=None,
                        help="hard cap for smoke tests")
    p_disc.add_argument("--out", type=Path, default=None,
                        help="manifest path (default: manifests/by-agency/<source>.jsonl)")
    p_disc.add_argument("--snapshot-html", type=Path, default=None,
                        help="dump landing page HTML to this file (war.gov only)")
    _add_common(p_disc)

    p_sip = sub.add_parser("siptest", help="project per-agency size from existing manifest")
    p_sip.add_argument("--agency", required=False, default=None)
    p_sip.add_argument("--sample", type=int, default=20)
    _add_common(p_sip)

    p_fet = sub.add_parser("fetch", help="resumable downloader for end-users")
    p_fet.add_argument("--agency", required=True)
    p_fet.add_argument("--max-bytes", type=int, default=None)
    _add_common(p_fet)

    p_ver = sub.add_parser("verify", help="re-hash staging/ and update manifest sha256")
    p_ver.add_argument("--agency", required=True)
    _add_common(p_ver)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose >= 2 else (logging.INFO if args.verbose else logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "bulk":
        from uap_archive import bulk_ingest
        from uap_archive.config import BY_AGENCY_DIR, ROOT_NAIDS
        if args.inspect:
            print(bulk_ingest.inspect(args.json_path))
            return 0
        agency = args.agency.upper()
        out = args.out or BY_AGENCY_DIR / f"{agency.lower()}.jsonl"
        root = args.root_naid or ROOT_NAIDS.get(agency)
        n = bulk_ingest.ingest(args.json_path, agency=agency, out=out, root_naid=root)
        print(f"manifest: {out} ({n} objects)")
        return 0

    if args.cmd == "seed":
        from uap_archive.seeds import seed_manifest
        n = seed_manifest(tsv=args.tsv, csv_path=args.csv, out=args.out)
        print(f"manifest: {args.out} ({n} objects)")
        return 0

    if args.cmd == "discover":
        from uap_archive.discover import discover_source
        path = asyncio.run(discover_source(
            args.source,
            rps=args.rps,
            out_path=args.out,
            max_records=args.max_records,
            root_override=args.root,
            snapshot_html_to=str(args.snapshot_html) if args.snapshot_html else None,
        ))
        print(f"manifest: {path}")
        return 0

    if args.cmd == "siptest":
        from uap_archive.config import MANIFESTS_DIR
        from uap_archive.siptest import run_all, siptest_agency, write_projection_md
        if args.agency:
            row = siptest_agency(args.agency, sample=args.sample)
            write_projection_md([row], MANIFESTS_DIR / "size-projection.md")
            print(row)
        else:
            print(f"projection: {run_all()}")
        return 0

    if args.cmd == "fetch":
        from uap_archive.fetch import fetch_agency
        result = asyncio.run(fetch_agency(
            args.agency, rps=args.rps, max_bytes=args.max_bytes,
        ))
        print(result)
        return 0 if result.get("fail", 0) == 0 else 2

    if args.cmd == "verify":
        from uap_archive.verify import verify_agency
        report = verify_agency(args.agency)
        print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})
        return 0 if not report["mismatch"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
