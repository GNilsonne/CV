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
import re
import sys
import time
import unicodedata
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
    month = int((pub_date.get("month") or {}).get("value", 0))
    day = int((pub_date.get("day") or {}).get("value", 0))

    # Build YYYY-MM-DD date string from available components
    date_str = ""
    if year:
        date_str = f"{year:04d}"
        if month:
            date_str += f"-{month:02d}"
            if day:
                date_str += f"-{day:02d}"
            else:
                date_str += "-01"  # default to 1st of month
        else:
            date_str += "-01-01"  # default to Jan 1st

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
        "date": date_str,
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


# ---------- ID generation ----------

def _slugify(text: str) -> str:
    """Convert text to a slug: lowercase, ascii-safe, underscores."""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')


def _first_surname(authors: str) -> str:
    """Extract the first author's surname."""
    if not authors:
        return 'unknown'
    first = authors.split(',')[0].strip()
    parts = first.split()
    if not parts:
        return 'unknown'
    last = parts[-1].rstrip('.')
    if len(last) <= 3 and last.replace('-', '').replace('.', '').isalpha():
        surname = parts[0]  # "Nilsonne G" format
    else:
        surname = parts[-1]  # "Gustav Nilsonne" format
    return _slugify(surname.rstrip('*'))


_STOP = {'a','an','the','of','in','on','for','and','to','is','are','was',
         'were','be','been','with','from','by','at','or','not','but','its',
         'as','do','does','did','can','how','what','when','where','why',
         'no','vs','between'}

def _title_keyword(title: str) -> str:
    """Extract a distinctive keyword from the title."""
    t = re.sub(r'^\[|\]$', '', title.strip())
    words = re.findall(r'[a-zA-Z\u00C0-\u024F]+', t)
    for w in words:
        if len(w) > 3 and w.lower() not in _STOP:
            return _slugify(w)
    return _slugify(words[0]) if words else 'untitled'


def generate_id(entry: dict, existing_ids: set) -> str:
    """Generate a unique id for a CV entry."""
    surname = _first_surname(entry.get('authors', ''))
    year = entry.get('year', '')
    keyword = _title_keyword(entry.get('title', ''))
    base = f"{surname}_{year}_{keyword}" if year else f"{surname}_{keyword}"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    existing_ids.add(candidate)
    return candidate


def work_to_entry(parsed: dict) -> dict:
    """Convert a parsed work to a YAML entry."""
    entry = {
        "title": parsed["title"],
        "authors": parsed["authors"] or "Nilsonne G, et al.",
    }
    if parsed["year"]:
        entry["year"] = parsed["year"]
    if parsed["date"]:
        entry["date"] = parsed["date"]
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


# All sections to scan for existing entries (avoid re-adding works that
# were manually moved to a different section, e.g. scholarly_debate).
ALL_ENTRY_SECTIONS = list(set(SECTION_MAP.values())) + [
    "scholarly_debate", "other_publications",
]


def _normalise_title(title: str) -> str:
    """Lower-case, strip brackets/punctuation for fuzzy title matching."""
    import re
    t = title.strip().lower()
    t = re.sub(r'^\[|\]$', '', t)   # remove surrounding brackets
    t = re.sub(r'[^a-z0-9 ]', '', t)  # keep only alphanumeric + space
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def existing_dois(data: dict) -> dict:
    """Build DOI → (section, index) map across all entry sections."""
    doi_map = {}
    for section in ALL_ENTRY_SECTIONS:
        for i, entry in enumerate(data.get(section, [])):
            if entry.get("doi"):
                doi_map[entry["doi"].lower()] = (section, i)
    return doi_map


def existing_titles(data: dict) -> set:
    """Build a set of normalised titles across all entry sections."""
    titles = set()
    for section in ALL_ENTRY_SECTIONS:
        for entry in data.get(section, []):
            if entry.get("title"):
                titles.add(_normalise_title(entry["title"]))
    return titles


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
    title_set = existing_titles(existing)

    # Collect all existing IDs for collision avoidance
    all_ids: set = set()
    for sec in existing:
        if isinstance(existing[sec], list):
            for e in existing[sec]:
                if isinstance(e, dict) and e.get('id'):
                    all_ids.add(e['id'])

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
            section, idx = doi_map[doi]
            # Always backfill date if missing
            if parsed["date"] and not existing[section][idx].get("date"):
                existing[section][idx]["date"] = parsed["date"]
                if parsed["year"] and not existing[section][idx].get("year"):
                    existing[section][idx]["year"] = parsed["year"]
                updated_count += 1
            if args.update_authors and parsed["authors"]:
                old_authors = existing[section][idx].get("authors", "")
                if old_authors != parsed["authors"]:
                    existing[section][idx]["authors"] = parsed["authors"]
                    updated_count += 1
            skipped_count += 1
            continue

        # Skip works whose title already exists in any section (catches
        # entries without DOI that were manually moved, e.g. to
        # scholarly_debate).
        norm = _normalise_title(parsed.get("title", ""))
        if norm and norm in title_set:
            skipped_count += 1
            continue

        section = SECTION_MAP.get(parsed["type"], "other_publications")
        entry = work_to_entry(parsed)
        entry['id'] = generate_id(entry, all_ids)
        existing[section].append(entry)
        if norm:
            title_set.add(norm)
        if doi:
            doi_map[doi] = (section, len(existing[section]) - 1)
        new_count += 1

    # Sort each section by date (ascending, oldest first); entries without a date go last
    for section in SECTION_MAP.values():
        if section in existing and existing[section]:
            existing[section].sort(key=lambda e: (0 if e.get("date") else 1, e.get("date") or "9999-99-99"))

    # Write YAML
    class CustomDumper(yaml.SafeDumper):
        pass

    def represent_dict(dumper, data):
        if not data:
            return dumper.represent_mapping("tag:yaml.org,2002:map", {})
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

    def represent_date(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))

    CustomDumper.add_representer(dict, represent_dict)

    import datetime
    CustomDumper.add_representer(datetime.date, represent_date)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, Dumper=CustomDumper, default_flow_style=False,
                  allow_unicode=True, sort_keys=False, width=120)

    print(f"Added {new_count} new entries, skipped {skipped_count} existing"
          + (f", updated {updated_count} author lists" if args.update_authors else "")
          + ".")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
