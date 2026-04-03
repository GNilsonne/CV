#!/usr/bin/env python3
"""
Download open-access PDFs for publications listed in cv_data.yaml.

For each publication that has a DOI and an id, queries the Unpaywall API
for the best available open-access PDF.  Downloaded files are saved to
``pdfs/<id>.pdf``.  Entries that already have a PDF on disk are skipped
(idempotent).

Usage:
    python3 scripts/fetch_pdfs.py [--input cv_data.yaml] [--output-dir pdfs]
                                  [--email gustav.nilsonne@ki.se]
                                  [--dry-run]         # list what would be fetched
                                  [--force]           # re-download even if file exists
                                  [--section publications]  # which YAML section(s)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml


# ── Unpaywall helpers ────────────────────────────────────────────────

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

def unpaywall_lookup(doi: str, email: str) -> dict | None:
    """Return the Unpaywall record for *doi*, or None on failure."""
    url = f"{UNPAYWALL_BASE}/{doi}?email={email}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": f"CVBuilder/1.0 (mailto:{email})",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    except Exception:
        return None


def best_pdf_url(record: dict) -> str | None:
    """Extract the best open-access PDF URL from an Unpaywall record.

    Priority:
      1. best_oa_location with pdf_url
      2. Any oa_location with pdf_url (prefer publisher over repository)
    """
    if not record:
        return None

    # 1. best_oa_location
    best = record.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]

    # 2. Scan all locations
    locations = record.get("oa_locations") or []
    # Sort: publisher > repository
    for loc in sorted(locations, key=lambda l: 0 if l.get("host_type") == "publisher" else 1):
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"]

    return None


# ── PDF download ─────────────────────────────────────────────────────

def download_pdf(url: str, dest: Path, doi: str) -> bool:
    """Download a PDF from *url* into *dest*.  Returns True on success."""
    headers = {
        "User-Agent": "CVBuilder/1.0 (mailto:gustav.nilsonne@ki.se)",
        "Accept": "application/pdf,*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()

            # Sanity check: should start with %PDF
            if data[:5] != b"%PDF-" and "pdf" not in content_type.lower():
                return False

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    except Exception:
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download open-access PDFs for CV publications")
    parser.add_argument("--input", default="cv_data.yaml",
                        help="Input YAML file (default: cv_data.yaml)")
    parser.add_argument("--output-dir", default="pdfs",
                        help="Directory for downloaded PDFs (default: pdfs)")
    parser.add_argument("--email", default="gustav.nilsonne@ki.se",
                        help="Email for Unpaywall API")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only list what would be fetched, don't download")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if file already exists")
    parser.add_argument("--section", nargs="+", default=["publications"],
                        help="YAML sections to process (default: publications)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    with open(input_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = []
    for section in args.section:
        for entry in data.get(section, []):
            if entry.get("doi") and entry.get("id"):
                entries.append(entry)

    print(f"Found {len(entries)} entries with DOI + id in {args.section}")

    # Counters
    already = 0
    downloaded = 0
    no_oa = 0
    failed = 0
    skipped_no_doi = 0

    no_oa_entries = []

    for i, entry in enumerate(entries, 1):
        doi = entry["doi"]
        eid = entry["id"]
        dest = output_dir / f"{eid}.pdf"
        title_short = entry.get("title", "")[:60]

        # Skip if already downloaded
        if dest.exists() and not args.force:
            already += 1
            continue

        print(f"[{i}/{len(entries)}] {eid}")
        print(f"  DOI: {doi}")

        if args.dry_run:
            print(f"  (dry run — would query Unpaywall)")
            continue

        # Query Unpaywall
        record = unpaywall_lookup(doi, args.email)
        pdf_url = best_pdf_url(record)

        if not pdf_url:
            # No OA PDF available
            is_oa = record.get("is_oa", False) if record else False
            no_oa += 1
            no_oa_entries.append((eid, doi, title_short, is_oa))
            print(f"  ✗ No OA PDF available (is_oa={is_oa})")
            time.sleep(0.2)
            continue

        print(f"  ↓ {pdf_url[:80]}")

        if download_pdf(pdf_url, dest, doi):
            size_kb = dest.stat().st_size / 1024
            downloaded += 1
            print(f"  ✓ Saved ({size_kb:.0f} KB)")
        else:
            failed += 1
            print(f"  ✗ Download failed or not a valid PDF")

        # Be polite to the API
        time.sleep(0.3)

    # Summary
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"Total entries:     {len(entries)}")
    print(f"Already on disk:   {already}")
    print(f"Downloaded:        {downloaded}")
    print(f"No OA PDF:         {no_oa}")
    print(f"Failed:            {failed}")

    if no_oa_entries:
        print(f"\nEntries without OA PDF ({len(no_oa_entries)}):")
        for eid, doi, title, is_oa in no_oa_entries:
            print(f"  - {eid} (doi:{doi})")


if __name__ == "__main__":
    main()
