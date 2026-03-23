#!/usr/bin/env python3
"""
Generate a filtered list of outputs by link type.

Usage:
    python3 scripts/list_outputs.py [--data cv_data.yaml] [--type data] [--format md|csv|text]

Examples:
    python3 scripts/list_outputs.py --type data          # All open datasets
    python3 scripts/list_outputs.py --type code           # All code repos
    python3 scripts/list_outputs.py --type preprint       # All preprints
    python3 scripts/list_outputs.py --type all            # Everything
    python3 scripts/list_outputs.py --summary             # Count summary
"""

import argparse
import csv
import io
from pathlib import Path

import yaml


LINK_TYPE_LABELS = {
    "preprint": "Preprints / Open Access Versions",
    "data": "Open Datasets",
    "code": "Code Repositories",
    "materials": "Open Materials",
    "preregistration": "Preregistrations",
    "narrative": "Narrative Descriptions",
    "slides": "Presentation Slides",
    "video": "Video Recordings",
    "protocol": "Protocols",
}

ALL_SECTIONS = ["publications", "preprints", "book_chapters", "presentations", "other_publications"]


def collect_outputs(data: dict, link_type: str = "all") -> dict:
    """Collect outputs grouped by link type."""
    from collections import defaultdict
    outputs = defaultdict(list)

    for section in ALL_SECTIONS:
        for entry in data.get(section, []):
            links = entry.get("links", {})
            if not links:
                continue
            for lt, url in links.items():
                if not url:
                    continue
                if link_type != "all" and lt != link_type:
                    continue
                outputs[lt].append({
                    "title": entry.get("title", "Untitled"),
                    "year": entry.get("year", ""),
                    "url": url,
                    "doi": entry.get("doi", ""),
                    "section": section,
                })
    return dict(outputs)


def format_md(outputs: dict) -> str:
    lines = []
    for lt, entries in sorted(outputs.items()):
        label = LINK_TYPE_LABELS.get(lt, lt.title())
        lines.append(f"## {label}\n")
        for e in sorted(entries, key=lambda x: x["year"], reverse=True):
            doi_part = f" (DOI: [{e['doi']}](https://doi.org/{e['doi']}))" if e["doi"] else ""
            lines.append(f"- [{e['title']}]({e['url']}) ({e['year']}){doi_part}")
        lines.append("")
    return "\n".join(lines) if lines else "No outputs found.\n"


def format_csv(outputs: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["type", "title", "year", "url", "doi"])
    for lt, entries in sorted(outputs.items()):
        for e in sorted(entries, key=lambda x: x["year"], reverse=True):
            writer.writerow([lt, e["title"], e["year"], e["url"], e["doi"]])
    return buf.getvalue()


def format_text(outputs: dict) -> str:
    lines = []
    for lt, entries in sorted(outputs.items()):
        label = LINK_TYPE_LABELS.get(lt, lt.title())
        lines.append(f"=== {label} ===")
        for e in sorted(entries, key=lambda x: x["year"], reverse=True):
            lines.append(f"  {e['year']} | {e['title']}")
            lines.append(f"         {e['url']}")
        lines.append("")
    return "\n".join(lines) if lines else "No outputs found.\n"


def format_summary(data: dict) -> str:
    from collections import Counter
    counts = Counter()
    total_entries = 0
    entries_with_any_link = 0

    for section in ALL_SECTIONS:
        for entry in data.get(section, []):
            total_entries += 1
            links = entry.get("links", {})
            has_link = False
            for lt, url in links.items():
                if url:
                    counts[lt] += 1
                    has_link = True
            if has_link:
                entries_with_any_link += 1

    lines = [
        f"Total entries: {total_entries}",
        f"Entries with at least one link: {entries_with_any_link}",
        f"Entries with no links: {total_entries - entries_with_any_link}",
        "",
        "By link type:",
    ]
    for lt, count in sorted(counts.items(), key=lambda x: -x[1]):
        label = LINK_TYPE_LABELS.get(lt, lt)
        lines.append(f"  {label}: {count}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List open research outputs")
    parser.add_argument("--data", default="cv_data.yaml", help="YAML data file")
    parser.add_argument("--type", default="all", help="Link type to filter (data, code, preprint, etc.) or 'all'")
    parser.add_argument("--format", default="md", choices=["md", "csv", "text"], help="Output format")
    parser.add_argument("--summary", action="store_true", help="Show count summary only")
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as f:
        content = f.read()
    data = yaml.load(content, Loader=yaml.SafeLoader)

    if args.summary:
        print(format_summary(data))
        return

    outputs = collect_outputs(data, args.type)

    formatters = {"md": format_md, "csv": format_csv, "text": format_text}
    print(formatters[args.format](outputs))


if __name__ == "__main__":
    main()
