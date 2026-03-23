#!/usr/bin/env python3
"""
Generate an alphabetical list of all co-authors from cv_data.yaml.

Usage:
    python3 scripts/list_coauthors.py [--data cv_data.yaml] [--format text|csv|md]
    python3 scripts/list_coauthors.py --with-papers        # show which papers each co-author is on
    python3 scripts/list_coauthors.py --exclude-self        # exclude Gustav Nilsonne (default: included)

Can also pull co-authors directly from ORCID:
    python3 scripts/list_coauthors.py --from-orcid 0000-0001-5273-0150
"""

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.request

# Force UTF-8 stdout on Windows (cp1252 can't handle ö, å, ń, etc.)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
from collections import defaultdict
from pathlib import Path

import yaml


SELF_PATTERNS = [
    r"^gustav\s+nilsonne$",
    r"^nilsonne\s*,?\s*g\.?$",
    r"^nilsonne\s+g$",
    r"^g\.?\s*nilsonne$",
]


def is_self(name: str) -> bool:
    """Check if a name matches Gustav Nilsonne."""
    clean = name.strip().lower()
    for pat in SELF_PATTERNS:
        if re.match(pat, clean):
            return True
    return False


def normalize_name(name: str) -> str:
    """Light normalization: strip whitespace, fix common issues."""
    name = name.strip()
    # Remove trailing periods from initials-only names
    name = re.sub(r"\s+", " ", name)
    return name


def parse_author_string(authors_str: str) -> list[str]:
    """Parse a comma/semicolon-separated author string into individual names."""
    if not authors_str:
        return []

    # Split on comma, semicolon, or " and "
    # But be careful: "LastName, FirstName" uses commas too
    # Heuristic: if there are semicolons, split on those
    if ";" in authors_str:
        names = [n.strip() for n in authors_str.split(";")]
    else:
        # Split on comma, but try to detect "Last, First" patterns
        parts = [p.strip() for p in authors_str.split(",")]

        # If most parts have spaces, they're individual names separated by commas
        # If few have spaces, it might be "Last, First, Last, First" format
        has_space = sum(1 for p in parts if " " in p.strip())

        if has_space > len(parts) * 0.5:
            # Most parts have spaces → each part is a full name
            names = parts
        else:
            # Try pairing: "Last, First, Last, First"
            # But this is unreliable, so just treat each as a name
            names = parts

    # Clean up "and" at the beginning of names
    cleaned = []
    for n in names:
        n = n.strip()
        n = re.sub(r"^and\s+", "", n, flags=re.IGNORECASE)
        n = re.sub(r"^\*+", "", n)  # Remove asterisks (shared authorship markers)
        n = n.strip()
        if n and len(n) > 1:  # Skip single characters
            cleaned.append(normalize_name(n))

    return cleaned


def coauthors_from_yaml(data: dict, exclude_self: bool = True) -> dict:
    """Extract co-authors from cv_data.yaml. Returns {name: [list of paper titles]}."""
    coauthors = defaultdict(list)

    all_sections = ["publications", "preprints", "book_chapters", "presentations", "other_publications"]

    for section in all_sections:
        for entry in data.get(section, []):
            authors_str = entry.get("authors", "")
            title = entry.get("title", "Untitled")
            year = entry.get("year", "")

            names = parse_author_string(authors_str)
            for name in names:
                if exclude_self and is_self(name):
                    continue
                coauthors[name].append(f"{title} ({year})")

    return dict(coauthors)


def coauthors_from_orcid(orcid_id: str, exclude_self: bool = True) -> dict:
    """Fetch co-authors directly from ORCID API."""
    # Get put-codes
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    put_codes = []
    for group in data.get("group", []):
        for s in group.get("work-summary", []):
            put_codes.append(str(s.get("put-code", "")))
            break

    # Fetch details in bulk
    coauthors = defaultdict(list)
    for i in range(0, len(put_codes), 50):
        chunk = put_codes[i:i+50]
        codes_str = ",".join(chunk)
        url = f"https://pub.orcid.org/v3.0/{orcid_id}/works/{codes_str}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            bulk_data = json.loads(resp.read())

        for item in bulk_data.get("bulk", []):
            work = item.get("work")
            if not work:
                continue

            title = ((work.get("title") or {}).get("title") or {}).get("value", "Untitled")
            year = ((work.get("publication-date") or {}).get("year") or {}).get("value", "")
            contribs = (work.get("contributors") or {}).get("contributor", [])

            for c in contribs:
                name = (c.get("credit-name") or {}).get("value", "")
                if not name:
                    continue
                if exclude_self and is_self(name):
                    continue
                coauthors[normalize_name(name)].append(f"{title} ({year})")

        if i + 50 < len(put_codes):
            time.sleep(0.5)

    return dict(coauthors)


def sort_by_surname(name: str) -> str:
    """Extract likely surname for sorting. Handles 'Surname Initials' (Vancouver) and 'First Last'."""
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip().lower()
    parts = name.split()
    if len(parts) >= 2:
        # Vancouver format: "Surname I" or "Surname AB" — last part is short initials
        last = parts[-1]
        if len(last) <= 3 and last.replace("-", "").isalpha() and last[0].isupper():
            # Last part looks like initials, surname is everything before
            return " ".join(parts[:-1]).lower()
        # Otherwise assume "First Last"
        return parts[-1].lower()
    if parts:
        return parts[0].lower()
    return name.lower()


def format_text(coauthors: dict, with_papers: bool) -> str:
    lines = [f"Co-authors: {len(coauthors)} unique names\n"]
    for name in sorted(coauthors.keys(), key=sort_by_surname):
        if with_papers:
            papers = coauthors[name]
            lines.append(f"{name} ({len(papers)} papers)")
            for p in papers:
                lines.append(f"  - {p}")
        else:
            lines.append(name)
    return "\n".join(lines)


def format_csv(coauthors: dict, with_papers: bool) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    if with_papers:
        writer.writerow(["name", "paper_count", "papers"])
        for name in sorted(coauthors.keys(), key=sort_by_surname):
            papers = coauthors[name]
            writer.writerow([name, len(papers), "; ".join(papers)])
    else:
        writer.writerow(["name", "paper_count"])
        for name in sorted(coauthors.keys(), key=sort_by_surname):
            writer.writerow([name, len(coauthors[name])])
    return buf.getvalue()


def format_md(coauthors: dict, with_papers: bool) -> str:
    lines = [f"# Co-authors ({len(coauthors)} unique names)\n"]
    for name in sorted(coauthors.keys(), key=sort_by_surname):
        papers = coauthors[name]
        if with_papers:
            lines.append(f"- **{name}** ({len(papers)} papers)")
            for p in papers:
                lines.append(f"  - {p}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List all co-authors")
    parser.add_argument("--data", default="cv_data.yaml", help="YAML data file")
    parser.add_argument("--format", default="text", choices=["text", "csv", "md"])
    parser.add_argument("--with-papers", action="store_true", help="Show papers per co-author")
    parser.add_argument("--include-self", action="store_true", help="Include Gustav Nilsonne in the list")
    parser.add_argument("--from-orcid", type=str, default=None,
                        help="Pull co-authors directly from ORCID instead of YAML")
    args = parser.parse_args()

    exclude_self = not args.include_self

    if args.from_orcid:
        print(f"Fetching co-authors from ORCID {args.from_orcid}...", file=sys.stderr)
        coauthors = coauthors_from_orcid(args.from_orcid, exclude_self)
    else:
        with open(args.data, encoding="utf-8") as f:
            content = f.read()
        data = yaml.load(content, Loader=yaml.SafeLoader)
        coauthors = coauthors_from_yaml(data, exclude_self)

    formatters = {"text": format_text, "csv": format_csv, "md": format_md}
    print(formatters[args.format](coauthors, args.with_papers))


if __name__ == "__main__":
    main()
