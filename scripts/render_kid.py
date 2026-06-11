#!/usr/bin/env python3
"""
Render a KI-style publication list for the last 5 years from cv_data.yaml.

This mirrors the VR publication list layout/formatting but uses a rolling
5-year window based on the current UTC year.

Produces:
  - output/kid_publist.tex
  - output/kid_publist.pdf (if pdflatex is available)

Usage:
  python scripts/render_kid.py
  python scripts/render_kid.py --no-pdf
"""

import argparse
import os
import subprocess
from datetime import datetime, timezone

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

    parts = [part.strip() for part in authors_str.split(",")]
    two_element_format = False
    if len(parts) >= 4:
        initials_count = 0
        for idx in range(1, min(6, len(parts)), 2):
            part = parts[idx].strip()
            if (
                len(part) <= 4
                and part.replace("-", "").replace(" ", "").replace(".", "").isalpha()
                and part[:1].isupper()
            ):
                initials_count += 1
        if initials_count >= 2:
            two_element_format = True

    if two_element_format:
        authors = []
        index = 0
        while index < len(parts):
            if index + 1 < len(parts):
                surname = parts[index].strip()
                initials = parts[index + 1].strip()
                if (
                    len(initials) <= 4
                    and initials.replace("-", "").replace(" ", "").replace(".", "").isalpha()
                ):
                    authors.append(f"{surname} {initials}")
                    index += 2
                    continue
            authors.append(parts[index].strip())
            index += 1
    else:
        authors = [part.strip() for part in parts if part.strip()]

    if len(authors) > max_authors:
        return ", ".join(authors[:6]) + ", et al"
    return ", ".join(authors)


def vr_bold_name(text, name="Nilsonne G") -> str:
    if not text:
        return ""
    escaped_name = tex_escape(name)
    if escaped_name in text:
        return text.replace(escaped_name, r"\textbf{" + escaped_name + "}")
    return text


def classify_publication(pub, overrides=None):
    """Classify a publication as 'original', 'review', 'conference', 'book', or 'other'."""
    if overrides and pub.get("doi") in overrides:
        return overrides[pub["doi"]]

    pub_type = pub.get("pub_type")
    if pub_type in {"original", "review", "conference", "book", "other"}:
        return pub_type

    vr_type = pub.get("vr_type")
    if vr_type:
        return vr_type

    title = (pub.get("title", "") or "").lower()
    if any(marker in title for marker in ["systematic review", "meta-analy", "scoping review"]):
        return "review"
    return "original"


def in_year_range(pub, start_year, end_year):
    year = pub.get("year", 0) or 0
    return start_year <= year <= end_year


def compile_pdf(tex_path):
    workdir = os.path.dirname(tex_path)
    filename = os.path.basename(tex_path)
    commands = [
        ["pdflatex", "-interaction=nonstopmode", filename],
        ["pdflatex", "-interaction=nonstopmode", filename],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=workdir, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"pdflatex failed for {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pdf", action="store_true", help="Write the .tex file but skip PDF compilation")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)

    current_year = datetime.now(timezone.utc).year
    start_year = current_year - 4
    end_year = current_year

    with open("cv_data.yaml", encoding="utf-8") as handle:
        data = yaml.safe_load(handle.read()) or {}

    vr_config = {}
    if os.path.exists("vr_config.yaml"):
        with open("vr_config.yaml", encoding="utf-8") as handle:
            vr_config = yaml.safe_load(handle.read()) or {}

    type_overrides = {}
    for item in vr_config.get("type_overrides", []) or []:
        if "doi" in item and "type" in item:
            type_overrides[item["doi"]] = item["type"]

    publications = data.get("publications", []) or []
    preprints = data.get("preprints", []) or []
    books = data.get("books", []) or []
    scholarly_debate = data.get("scholarly_debate", []) or []
    conference_abstracts = data.get("conference_abstracts", []) or []
    popular_science_writings = data.get("popular_science_writings", []) or []
    reports = data.get("reports", []) or []
    digital_research_objects = data.get("digital_research_objects", []) or []

    selected_outputs = []
    peer_original_articles_2017 = []
    peer_reviews_2017 = []
    peer_conference_2017 = []
    peer_books_2017 = []
    peer_other_2017 = []
    popular_science_2017 = []
    preprints_2017 = []
    nonpeer_other_2017 = []

    pubs_sorted = sorted(publications, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True)

    for pub in pubs_sorted:
        if not in_year_range(pub, start_year, end_year):
            continue
        pub_type = classify_publication(pub, type_overrides)
        if pub_type == "review":
            peer_reviews_2017.append(pub)
        elif pub_type == "conference":
            peer_conference_2017.append(pub)
        elif pub_type == "book":
            peer_books_2017.append(pub)
        elif pub_type == "other":
            peer_other_2017.append(pub)
        else:
            peer_original_articles_2017.append(pub)

    for conference_abstract in sorted(conference_abstracts, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(conference_abstract, start_year, end_year):
            peer_conference_2017.append(conference_abstract)

    for book in sorted(books, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(book, start_year, end_year):
            peer_books_2017.append(book)

    for item in sorted(popular_science_writings, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(item, start_year, end_year):
            popular_science_2017.append(item)
    for item in sorted(scholarly_debate, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(item, start_year, end_year):
            popular_science_2017.append(item)

    preprints_2017 = sorted(
        [pub for pub in preprints if in_year_range(pub, start_year, end_year)],
        key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")),
        reverse=True,
    )

    for item in sorted(reports, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(item, start_year, end_year):
            nonpeer_other_2017.append(item)
    for item in sorted(digital_research_objects, key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")), reverse=True):
        if in_year_range(item, start_year, end_year):
            nonpeer_other_2017.append(item)

    all_originals = [pub for pub in publications if classify_publication(pub, type_overrides) == "original"]
    all_reviews = [pub for pub in publications if classify_publication(pub, type_overrides) == "review"]
    all_other = len(books) + len(reports) + len(scholarly_debate) + len(popular_science_writings) + len(preprints)

    other_2017 = (
        len([pub for pub in books if in_year_range(pub, start_year, end_year)])
        + len([pub for pub in reports if in_year_range(pub, start_year, end_year)])
        + len([pub for pub in scholarly_debate if in_year_range(pub, start_year, end_year)])
        + len([pub for pub in popular_science_writings if in_year_range(pub, start_year, end_year)])
        + len(preprints_2017)
    )

    counts = {
        "total_originals": len(all_originals),
        "total_reviews": len(all_reviews),
        "total_other": all_other,
        "originals_2017": len([pub for pub in all_originals if in_year_range(pub, start_year, end_year)]),
        "reviews_2017": len([pub for pub in all_reviews if in_year_range(pub, start_year, end_year)]),
        "other_2017": other_2017,
    }

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
    env.filters["notrailingdot"] = lambda value: str(value).rstrip(".") if value else ""
    env.filters["doi"] = lambda value: str(value).replace("_", r"\_") if value else ""
    env.filters["vr_authors"] = format_authors_vancouver
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

    year_label = f"{start_year}--{end_year}"
    output = output.replace("1. Selection of research outputs", "1. Publications")
    output = output.replace(
        "{\\small\\textit{The 10 publications most important for confirming competence as project leader and for the proposed research.}}\n\n",
        "",
    )
    output = output.replace(
        "\\section*{2. Relevant peer-reviewed research outputs 2017--2025}",
        f"\\section*{{2. Relevant peer-reviewed research outputs {year_label}}}",
    )
    output = output.replace(
        "\\section*{3. Relevant non peer-reviewed research outputs 2017--2025}",
        f"\\section*{{3. Relevant non peer-reviewed research outputs {year_label}}}",
    )
    output = output.replace(
        "2017--2025",
        year_label,
    )

    os.makedirs("output", exist_ok=True)
    tex_path = os.path.join("output", "kid_publist.tex")
    with open(tex_path, "w", encoding="utf-8") as handle:
        handle.write(output)
    print(f"Written: {tex_path}")

    print("\n=== KI publication list summary ===")
    print(f"Window: {start_year}-{end_year}")
    print(f"Peer-reviewed original articles: {len(peer_original_articles_2017)}")
    print(f"Peer-reviewed conference contributions: {len(peer_conference_2017)}")
    print(f"Peer-reviewed review articles: {len(peer_reviews_2017)}")
    print(f"Peer-reviewed books/book chapters: {len(peer_books_2017)}")
    print(f"Peer-reviewed other outputs: {len(peer_other_2017)}")
    print(f"Non peer-reviewed popular science/scholarly debate: {len(popular_science_2017)}")
    print(f"Non peer-reviewed preprints: {len(preprints_2017)}")
    print(f"Non peer-reviewed other outputs: {len(nonpeer_other_2017)}")

    if not args.no_pdf:
        try:
            compile_pdf(tex_path)
            print(f"Written: {tex_path[:-4] + '.pdf'}")
        except FileNotFoundError:
            print("pdflatex not found — skipping PDF compilation")


if __name__ == "__main__":
    main()
