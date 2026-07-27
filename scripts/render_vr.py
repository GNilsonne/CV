#!/usr/bin/env python3
"""
Render VR (Vetenskapsrådet) publication list from cv_data.yaml.

Usage:
    python scripts/render_vr.py [--no-pdf]

The script reads cv_data.yaml and vr_config.yaml (for the top-10 selection
and article type overrides) and produces output/vr_publist.tex.
"""

import argparse
import os
import re
import subprocess
import sys

import yaml
from jinja2 import Environment, FileSystemLoader


def tex_escape(text) -> str:
    if text is None:
        return ""
    text = str(text)
    replacements = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def format_authors_vancouver(authors_str, max_authors=6) -> str:
    """Vancouver-style author formatting."""
    if not authors_str:
        return ""
    authors_str = str(authors_str).strip()
    if "et al" in authors_str.lower() and authors_str.count(",") < 15:
        return authors_str

    parts = [p.strip() for p in authors_str.split(",")]
    two_element_format = False
    if len(parts) >= 4:
        initials_count = 0
        for j in range(1, min(6, len(parts)), 2):
            p = parts[j].strip()
            if (len(p) <= 4 and p.replace("-", "").replace(" ", "").replace(".", "").isalpha()
                    and p[0].isupper()):
                initials_count += 1
        if initials_count >= 2:
            two_element_format = True

    if two_element_format:
        authors = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts):
                name = parts[i].strip()
                initials = parts[i + 1].strip()
                if (len(initials) <= 4 and
                    initials.replace("-", "").replace(" ", "").replace(".", "").isalpha()):
                    authors.append(f"{name} {initials}")
                    i += 2
                    continue
            authors.append(parts[i].strip())
            i += 1
    else:
        authors = [p.strip() for p in parts if p.strip()]

    if len(authors) > max_authors:
        rendered = ", ".join(authors[:6]) + ", et al"
    else:
        rendered = ", ".join(authors)
    # The template appends its own period after the author list, so drop a
    # trailing one carried in from the data to avoid "Melin B..".
    if rendered.endswith(".") and not rendered.endswith("et al."):
        rendered = rendered[:-1]
    return rendered


def format_title_sentence(text) -> str:
    """Escape a title and terminate it with a single period.

    Titles end inconsistently in the data: some carry a trailing period, some
    none, and some end in ? or !. Appending a period unconditionally produced
    "...hur gor vi?.", so sentence-final punctuation is left alone. A dangling
    trailing colon introduces nothing once rendered and becomes a period.
    """
    raw = str(text).strip() if text else ""
    raw = raw.rstrip(".").strip()
    if not raw:
        return ""
    if raw.endswith(":"):
        raw = raw[:-1].rstrip()
    escaped = tex_escape(raw)
    if raw.endswith(("?", "!")):
        return escaped
    return escaped + "."


def vr_bold_name(text, name="Nilsonne G") -> str:
    """Bold the applicant's name in the author string (after tex_escape)."""
    if not text:
        return ""
    escaped_name = tex_escape(name)
    # Try to bold the name - handle both "Nilsonne G" and "Nilsonne G,"
    if escaped_name in text:
        return text.replace(escaped_name, r"\textbf{" + escaped_name + "}")
    return text


def in_year_range(pub, start=2017, end=2025):
    year = pub.get("year", 0) or 0
    return start <= year <= end


def classify_publication(pub, overrides=None):
    """Classify a publication as 'original', 'review', 'conference', 'book', or 'other'.
    
    Uses vr_type override if present, otherwise heuristic.
    """
    if overrides and pub.get("doi") in overrides:
        return overrides[pub["doi"]]
    
    vr_type = pub.get("vr_type")
    if vr_type:
        return vr_type
    
    title = (pub.get("title", "") or "").lower()
    # Heuristic
    if any(x in title for x in ["systematic review", "meta-analy", "scoping review"]):
        return "review"
    return "original"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)

    # Load data
    with open("cv_data.yaml", encoding="utf-8") as f:
        content = f.read()
    data = yaml.load(content, Loader=yaml.SafeLoader)

    # Load VR config (top-10 selection, type overrides)
    vr_config_path = "vr_config.yaml"
    vr_config = {}
    if os.path.exists(vr_config_path):
        with open(vr_config_path, encoding="utf-8") as f:
            content = f.read()
        vr_config = yaml.load(content, Loader=yaml.SafeLoader) or {}

    # Type overrides: doi -> type
    type_overrides = {}
    for item in vr_config.get("type_overrides", []) or []:
        if "doi" in item and "type" in item:
            type_overrides[item["doi"]] = item["type"]

    publications = data.get("publications", [])
    preprints = data.get("preprints", [])
    books = data.get("books", [])
    scholarly_debate = data.get("scholarly_debate", [])
    conference_abstracts = data.get("conference_abstracts", [])
    popular_science_writings = data.get("popular_science_writings", [])
    reports = data.get("reports", [])
    digital_research_objects = data.get("digital_research_objects", [])

    # === Section 1: Selected outputs ===
    selected_dois = vr_config.get("selected_outputs", []) or []
    selected_outputs = []
    contributions = {item["doi"]: item.get("contribution", "")
                     for item in (vr_config.get("selected_contributions", []) or [])
                     if "doi" in item}

    for doi in selected_dois:
        for pub in publications + preprints + books:
            if pub.get("doi") == doi:
                pub_copy = dict(pub)
                pub_copy["vr_contribution"] = contributions.get(doi, "[Describe contribution here]")
                selected_outputs.append(pub_copy)
                break

    # === Section 2: Peer-reviewed 2017-2025 ===
    # Sort reverse chronological
    pubs_sorted = sorted(publications, key=lambda p: -(p.get("year", 0) or 0))

    peer_original_articles_2017 = []
    peer_reviews_2017 = []
    peer_conference_2017 = []
    peer_books_2017 = []
    peer_other_2017 = []

    for pub in pubs_sorted:
        if not in_year_range(pub):
            continue
        ptype = classify_publication(pub, type_overrides)
        if ptype == "review":
            peer_reviews_2017.append(pub)
        elif ptype == "conference":
            peer_conference_2017.append(pub)
        elif ptype == "book":
            peer_books_2017.append(pub)
        elif ptype == "other":
            peer_other_2017.append(pub)
        else:
            peer_original_articles_2017.append(pub)

    # Conference abstracts (2017-2025) as conference contributions
    for ca in sorted(conference_abstracts, key=lambda p: -(p.get("year", 0) or 0)):
        if in_year_range(ca):
            peer_conference_2017.append(ca)

    # Books 2017-2025
    for b in books:
        if in_year_range(b):
            peer_books_2017.append(b)

    # === Section 3: Non peer-reviewed 2017-2025 ===
    # Popular science
    popular_science_2017 = []
    for pw in sorted(popular_science_writings, key=lambda p: -(p.get("year", 0) or 0)):
        if in_year_range(pw):
            popular_science_2017.append(pw)
    # Also scholarly debate as popular science / non-peer-reviewed
    for sd in sorted(scholarly_debate, key=lambda p: -(p.get("year", 0) or 0)):
        if in_year_range(sd):
            popular_science_2017.append(sd)

    # Preprints 2017-2025
    preprints_2017 = sorted(
        [p for p in preprints if in_year_range(p)],
        key=lambda p: -(p.get("year", 0) or 0)
    )

    # Other non-peer-reviewed: reports, digital research objects
    nonpeer_other_2017 = []
    for r in sorted(reports, key=lambda p: -(p.get("year", 0) or 0)):
        if in_year_range(r):
            nonpeer_other_2017.append(r)
    for dro in sorted(digital_research_objects, key=lambda p: -(p.get("year", 0) or 0)):
        if in_year_range(dro):
            nonpeer_other_2017.append(dro)

    # === Section 4: Counts ===
    all_originals = [p for p in publications if classify_publication(p, type_overrides) == "original"]
    all_reviews = [p for p in publications if classify_publication(p, type_overrides) == "review"]
    all_other = len(books) + len(reports) + len(scholarly_debate) + len(popular_science_writings) + len(preprints)

    other_2017 = (
        len([b for b in books if in_year_range(b)]) +
        len([r for r in reports if in_year_range(r)]) +
        len([s for s in scholarly_debate if in_year_range(s)]) +
        len([p for p in popular_science_writings if in_year_range(p)]) +
        len(preprints_2017)
    )

    counts = {
        "total_originals": len(all_originals),
        "total_reviews": len(all_reviews),
        "total_other": all_other,
        "originals_2017": len([p for p in all_originals if in_year_range(p)]),
        "reviews_2017": len([p for p in all_reviews if in_year_range(p)]),
        "other_2017": other_2017,
    }

    # === Render ===
    env = Environment(
        loader=FileSystemLoader("templates"),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
    )

    env.filters["tex"] = tex_escape
    env.filters["notrailingdot"] = lambda s: str(s).rstrip(".") if s else ""
    env.filters["titledot"] = format_title_sentence
    env.filters["doi"] = lambda s: str(s).replace("_", r"\_") if s else ""
    env.filters["vr_authors"] = lambda s: tex_escape(format_authors_vancouver(s))
    env.filters["vr_bold_name"] = vr_bold_name

    template = env.get_template("vr_publist.tex.j2")
    output = template.render(
        meta=data.get("meta", {}),
        selected_outputs=selected_outputs,
        peer_original_articles_2017=peer_original_articles_2017,
        peer_conference_2017=peer_conference_2017,
        peer_reviews_2017=peer_reviews_2017,
        peer_books_2017=peer_books_2017,
        peer_other_2017=peer_other_2017,
        popular_science_2017=popular_science_2017,
        preprints_2017=preprints_2017,
        nonpeer_other_2017=nonpeer_other_2017,
        counts=counts,
    )

    os.makedirs("output", exist_ok=True)
    with open("output/vr_publist.tex", "w", encoding="utf-8") as f:
        f.write(output)
    print("Written: output/vr_publist.tex")

    # Print summary
    print(f"\n=== VR Publication List Summary ===")
    print(f"Section 1 - Selected outputs: {len(selected_outputs)}")
    print(f"Section 2 - Peer-reviewed 2017-2025:")
    print(f"  Original articles: {len(peer_original_articles_2017)}")
    print(f"  Conference contributions: {len(peer_conference_2017)}")
    print(f"  Research reviews: {len(peer_reviews_2017)}")
    print(f"  Books: {len(peer_books_2017)}")
    print(f"  Other: {len(peer_other_2017)}")
    print(f"Section 3 - Non peer-reviewed 2017-2025:")
    print(f"  Popular science: {len(popular_science_2017)}")
    print(f"  Preprints: {len(preprints_2017)}")
    print(f"  Other: {len(nonpeer_other_2017)}")
    print(f"Section 4 - Counts:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
