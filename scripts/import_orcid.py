#!/usr/bin/env python3
"""
Fetch publications from ORCID and generate a skeleton cv_data.yaml.
Existing entries (matched by DOI) are preserved — only new works are appended.

Usage:
    python3 scripts/import_orcid.py [--orcid 0000-0001-5273-0150] [--output cv_data.yaml]
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import yaml


def fetch_orcid_works(orcid_id: str) -> list[dict]:
    """Fetch all works from ORCID public API."""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    works = []
    for group in data.get("group", []):
        summaries = group.get("work-summary", [])
        if not summaries:
            continue
        s = summaries[0]  # take first summary per group

        title = (s.get("title") or {}).get("title", {}).get("value", "")
        wtype = s.get("type", "")
        journal = (s.get("journal-title") or {}).get("value", "")

        pub_date = s.get("publication-date") or {}
        year = int((pub_date.get("year") or {}).get("value", 0))
        month = (pub_date.get("month") or {}).get("value", "")
        day = (pub_date.get("day") or {}).get("value", "")

        doi = ""
        for eid in (s.get("external-ids") or {}).get("external-id", []):
            if eid.get("external-id-type") == "doi":
                doi = eid.get("external-id-value", "")
                break

        works.append({
            "title": title,
            "type": wtype,
            "year": year,
            "month": month,
            "day": day,
            "journal": journal,
            "doi": doi,
        })

    return works


# Map ORCID types to our YAML sections
SECTION_MAP = {
    "journal-article": "publications",
    "preprint": "preprints",
    "book-chapter": "book_chapters",
    "conference-abstract": "other_publications",
    "other": "other_publications",
}


def orcid_to_entry(work: dict) -> dict:
    """Convert an ORCID work to a YAML entry skeleton."""
    entry = {
        "title": work["title"],
        "authors": "Nilsonne G, et al.",  # placeholder — fill in manually
        "year": work["year"],
    }
    if work["doi"]:
        entry["doi"] = work["doi"]
    if work["journal"]:
        entry["journal"] = work["journal"]
    entry["links"] = {}  # placeholder for manual curation
    return entry


def load_existing(path: Path) -> dict:
    """Load existing cv_data.yaml if it exists."""
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def existing_dois(data: dict) -> set:
    """Collect all DOIs already in the YAML."""
    dois = set()
    for section in SECTION_MAP.values():
        for entry in data.get(section, []):
            if entry.get("doi"):
                dois.add(entry["doi"].lower())
    return dois


def main():
    parser = argparse.ArgumentParser(description="Import ORCID works into cv_data.yaml")
    parser.add_argument("--orcid", default="0000-0001-5273-0150", help="ORCID iD")
    parser.add_argument("--output", default="cv_data.yaml", help="Output YAML file")
    args = parser.parse_args()

    output_path = Path(args.output)
    existing = load_existing(output_path)
    known_dois = existing_dois(existing)

    works = fetch_orcid_works(args.orcid)
    print(f"Fetched {len(works)} works from ORCID {args.orcid}")

    # Ensure all sections exist
    for section in set(SECTION_MAP.values()):
        if section not in existing:
            existing[section] = []

    # Ensure meta section
    if "meta" not in existing:
        existing["meta"] = {
            "name": "Gustav Nilsonne",
            "orcid": args.orcid,
            "affiliation": "Karolinska Institutet",
            "email": "",
        }

    # Ensure other sections
    for section in ["presentations", "other_publications"]:
        if section not in existing:
            existing[section] = []

    new_count = 0
    skipped_count = 0
    for work in works:
        doi = work.get("doi", "").lower()
        if doi and doi in known_dois:
            skipped_count += 1
            continue

        section = SECTION_MAP.get(work["type"], "other_publications")
        entry = orcid_to_entry(work)
        existing[section].append(entry)
        known_dois.add(doi)
        new_count += 1

    # Sort each section by year (descending)
    for section in SECTION_MAP.values():
        if section in existing and existing[section]:
            existing[section].sort(key=lambda e: e.get("year", 0), reverse=True)

    # Custom YAML representer to handle empty dicts nicely
    class CustomDumper(yaml.SafeDumper):
        pass

    def represent_dict(dumper, data):
        if not data:
            return dumper.represent_mapping("tag:yaml.org,2002:map", {})
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

    CustomDumper.add_representer(dict, represent_dict)

    with open(output_path, "w") as f:
        yaml.dump(existing, f, Dumper=CustomDumper, default_flow_style=False,
                  allow_unicode=True, sort_keys=False, width=120)

    print(f"Added {new_count} new entries, skipped {skipped_count} existing.")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
