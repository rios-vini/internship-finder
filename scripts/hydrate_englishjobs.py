#!/usr/bin/env python3
"""
Hydration script for englishjobs.de markdown cache.

Fetches all 4 categories via web_extract (Hermes browser backend) and saves
to data/cache/englishjobs_md/<category>_<timestamp>.md

Usage:
    python scripts/hydrate_englishjobs.py

This script is designed to be run by Hermes (orchestrator) weekly.
The cache serves as fallback for the VPS cron which gets Cloudflare 403.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# We'll use the web_extract tool via the hermes_tools module
# This requires running within a Hermes session with web_extract available


def hydrate_englishjobs():
    """Fetch all 4 englishjobs categories and save to cache."""
    # This function is meant to be called from within a Hermes session
    # where web_extract is available via hermes_tools
    from hermes_tools import web_extract

    cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache" / "englishjobs_md"
    cache_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d")

    categories = {
        "intern_internship": "https://englishjobs.de/jobs/intern_internship?format=markdown",
        "procurement": "https://englishjobs.de/jobs/procurement?format=markdown",
        "supply_chain": "https://englishjobs.de/jobs/supply_chain?format=markdown",
        "internship": "https://englishjobs.de/jobs/internship?format=markdown",
    }

    results = web_extract(urls=list(categories.values()), char_limit=100000)

    saved = 0
    for result in results.get("results", []):
        url = result.get("url", "")
        content = result.get("content", "")
        error = result.get("error")

        # Find category name from URL
        cat_name = None
        for name, cat_url in categories.items():
            if cat_url in url:
                cat_name = name
                break

        if not cat_name:
            print(f"WARNING: Unknown URL: {url}")
            continue

        if error:
            print(f"ERROR fetching {cat_name}: {error}")
            continue

        if not content:
            print(f"WARNING: Empty content for {cat_name}")
            continue

        # Save to cache
        cache_file = cache_dir / f"{cat_name}_{timestamp}.md"
        cache_file.write_text(content, encoding="utf-8")
        print(f"Saved {cat_name}: {len(content)} chars -> {cache_file}")
        saved += 1

    print(f"\nHydration complete: {saved}/4 categories saved to {cache_dir}")
    return saved == 4


if __name__ == "__main__":
    # Check if we're in a Hermes session with web_extract available
    try:
        from hermes_tools import web_extract
    except ImportError:
        print("ERROR: hermes_tools.web_extract not available.")
        print("This script must be run within a Hermes session (e.g., 'hermes chat -Q -q ...')")
        sys.exit(1)

    success = hydrate_englishjobs()
    sys.exit(0 if success else 1)