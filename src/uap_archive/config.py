"""Project-wide constants. Single source of truth — never inline these elsewhere."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx

from uap_archive import __version__

REPO_URL = "https://github.com/mrc0000/PlaySpace"

# NARA Record Group 615 — agency series root NAIDs.
ROOT_NAIDS: dict[str, int] = {
    "FAA":  493468575,
    "NRC":  488808322,
    "ODNI": 493468579,
    "NSA":  580103959,
    "DOS":  608806625,
}

WARGOV_URL = "https://www.war.gov/UFO/"
NARA_API_BASE = "https://catalog.archives.gov/api/v2"

# Etiquette defaults. CLI flags only lower these, never raise.
DEFAULT_RPS = 1.0           # global requests/sec
PER_HOST_CONCURRENCY = 2    # max in-flight per host
MAX_RETRIES = 5
RETRY_BASE = 1.0            # seconds; exponential 1, 2, 4, 8, 16

# Filesystem layout. Relative to repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = REPO_ROOT / "manifests"
BY_AGENCY_DIR = MANIFESTS_DIR / "by-agency"
STAGING_DIR = REPO_ROOT / "staging"


def _git_email() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "--get", "user.email"],
            capture_output=True, text=True, check=False, timeout=2,
        )
        v = out.stdout.strip()
        return v or "unknown@example.invalid"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown@example.invalid"


def user_agent() -> str:
    """Build the UA used for every outbound request. Includes maintainer contact."""
    contact = os.environ.get("UAP_ARCHIVE_CONTACT") or _git_email()
    return (
        f"UAP-Archive/{__version__} "
        f"(+{REPO_URL}; mailto:{contact}) "
        f"httpx/{httpx.__version__}"
    )


# Hosts we will hit. robots.txt is consulted for each.
KNOWN_HOSTS = ("catalog.archives.gov", "www.war.gov")
