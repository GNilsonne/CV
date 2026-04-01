#!/usr/bin/env python3
"""
Fetch publications from ORCID with full author lists and generate/update cv_data.yaml.
Existing entries (matched by DOI) are preserved — only new works are appended.
Use --update-authors to overwrite author lists from ORCID for existing entries.

Usage:
    python3 scripts/import_orcid.py [--orcid 0000-0001-5273-0150] [--output cv_data.yaml]
    python3 scripts/import_orcid.py --update-authors   # also refresh author lists
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import yaml


def fetch_orcid_works_summary(orcid_id: str) -> list[dict]:
    """Fetch work summaries to get put-codes."""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    put_codes = []
    for group in data.get("group", []):
        summaries = group.get("work-summary", [])
        if summaries:
            put_codes.append(str(summaries[0].get("put-code", "")))

    return put_codes


def fetch_works_bulk(orcid_id: str, put_codes: list[str]) -> list[dict]:
    """Fetch full work details in bulk (up to 100 at a time)."""
    works = []
    # Process in chunks of 50
    for i in range(0, len(put_codes), 50):
        chunk = put_codes[i:i+50]
        codes_str = ",".join(chunk)
        url = f"https://pub.orcid.org/v3.0/{orcid_id}/works/{codes_str}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        for item in data.get("bulk", []):
            work = item.get("work")
            if not work:
                continue
            works.append(work)

        if i + 50 < len(put_codes):
            time.sleep(0.5)  # Be nice to the API

    return works


def extract_authors(work: dict) -> str:
    """Extract author list from ORCID work detail."""
    contribs = (work.get("contributors") or {}).get("contributor", [])
    if not contribs:
        return ""

    # First try contributors with role=author
    authors = []
    for c in contribs:
        role = (c.get("contributor-attributes") or {}).get("contributor-role", "")
        name = (c.get("credit-name") or {}).get("value", "")
        if role == "author" and name:
            authors.append(name)

    # If no role-tagged authors, use all contributors with names (older entries)
    if not authors:
        for c in contribs:
            name = (c.get("credit-name") or {}).get("value", "")
            if name:
                authors.append(name)

    return ", ".join(authors) if authors else ""


def extract_authors_list(work: dict) -> list[str]:
    """Extract author list as a Python list."""
    contribs = (work.get("contributors") or {}).get("contributor", [])
    if not contribs:
        return []

    authors = []
    for c in contribs:
        role = (c.get("contributor-attributes") or {}).get("contributor-role", "")
        name = (c.get("credit-name") or {}).get("value", "")
        if role == "author" and name:
            authors.append(name)

    if not authors:
        for c in contribs:
            name = (c.get("credit-name") or {}).get("value", "")
            if name:
                authors.append(name)

    return authors


def parse_work(work: dict) -> dict:
    """Parse a full ORCID work into our schema."""
    title_obj = (work.get("title") or {}).get("title", {})
    title = title_obj.get("value", "") if title_obj else ""
    # Clean HTML tags from title
    if title.startswith("<p>"):
        import re
        title = re.sub(r"<[^>]+>", "", title)

    wtype = work.get("type", "")
    journal = (work.get("journal-title") or {}).get("value", "")

    pub_date = work.get("publication-date") or {}
    year = int((pub_date.get("year") or {}).get("value", 0))

    doi = ""
    for eid in (work.get("external-ids") or {}).get("external-id", []):
        if eid.get("external-id-type") == "doi":
            doi = eid.get("external-id-value", "")
            break

    authors = extract_authors(work)

    return {
        "title": title,
        "type": wtype,
        "year": year,
        "journal": journal,
        "doi": doi,
        "authors": authors,
    }


# Map ORCID types to our YAML sections
SECTION_MAP = {
    "journal-article": "publications",
    "preprint": "preprints",
    "book-chapter": "book_chapters",
    "conference-abstract": "other_publications",
    "other": "other_publications",
}


def work_to_entry(parsed: dict) -> dict:
    """Convert a parsed work to a YAML entry."""
    entry = {
        "title": parsed["title"],
        "authors": parsed["authors"] or "Nilsonne G, et al.",
        "year": parsed["year"],
    }
    if parsed["doi"]:
        entry["doi"] = parsed["doi"]
    if parsed["journal"]:
        entry["journal"] = parsed["journal"]
    entry["links"] = {}
    return entry


def load_existing(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return yaml.load(content, Loader=yaml.SafeLoader) or {}
    return {}


def existing_dois(data: dict) -> dict:
    """Build DOI → (section, index) map."""
    doi_map = {}
    for section in set(SECTION_MAP.values()):
        for i, entry in enumerate(data.get(section, [])):
            if entry.get("doi"):
                doi_map[entry["doi"].lower()] = (section, i)
    return doi_map


def main():
    parser = argparse.ArgumentParser(description="Import ORCID works into cv_data.yaml")
    parser.add_argument("--orcid", default="0000-0001-5273-0150", help="ORCID iD")
    parser.add_argument("--output", default="cv_data.yaml", help="Output YAML file")
    parser.add_argument("--update-authors", action="store_true",
                        help="Update author lists for existing entries from ORCID")
    args = parser.parse_args()

    output_path = Path(args.output)
    existing = load_existing(output_path)
    doi_map = existing_dois(existing)

    print(f"Fetching work summaries from ORCID {args.orcid}...")
    put_codes = fetch_orcid_works_summary(args.orcid)
    print(f"Found {len(put_codes)} works, fetching details...")

    works = fetch_works_bulk(args.orcid, put_codes)
    print(f"Fetched details for {len(works)} works")

    # Ensure all sections exist
    for section in set(SECTION_MAP.values()):
        if section not in existing:
            existing[section] = []

    if "meta" not in existing:
        existing["meta"] = {
            "name": "Gustav Nilsonne",
            "orcid": args.orcid,
            "affiliation": "Karolinska Institutet",
            "email": "",
        }

    for section in ["presentations", "other_publications"]:
        if section not in existing:
            existing[section] = []

    new_count = 0
    updated_count = 0
    skipped_count = 0

    for work in works:
        parsed = parse_work(work)
        doi = parsed.get("doi", "").lower()

        if doi and doi in doi_map:
            if args.update_authors and parsed["authors"]:
                section, idx = doi_map[doi]
                old_authors = existing[section][idx].get("authors", "")
                if old_authors != parsed["authors"]:
                    existing[section][idx]["authors"] = parsed["authors"]
                    updated_count += 1
            skipped_count += 1
            continue

        section = SECTION_MAP.get(parsed["type"], "other_publications")
        entry = work_to_entry(parsed)
        existing[section].append(entry)
        if doi:
            doi_map[doi] = (section, len(existing[section]) - 1)
        new_count += 1

    # Sort each section by year (descending)
    for section in SECTION_MAP.values():
        if section in existing and existing[section]:
            existing[section].sort(key=lambda e: e.get("year", 0), reverse=True)

    # Write YAML
    class CustomDumper(yaml.SafeDumper):
        pass

    def represent_dict(dumper, data):
        if not data:
            return dumper.represent_mapping("tag:yaml.org,2002:map", {})
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

    CustomDumper.add_representer(dict, represent_dict)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, Dumper=CustomDumper, default_flow_style=False,
                  allow_unicode=True, sort_keys=False, width=120)

    print(f"Added {new_count} new entries, skipped {skipped_count} existing"
          + (f", updated {updated_count} author lists" if args.update_authors else "")
          + ".")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
