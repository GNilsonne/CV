#!/usr/bin/env python3
"""
Render cv_data.yaml into LaTeX PDF and generate output lists.

Usage:
    python3 scripts/render_cv.py [--data cv_data.yaml] [--template templates/cv.tex.j2] [--output output/]

Outputs:
    output/cv.tex          — Generated LaTeX source
    output/cv.pdf          — Compiled PDF (if pdflatex available)
    output/open_outputs.md — List of all open outputs by type
"""

import argparse
from pathlib import Path
from collections import defaultdict

import yaml

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 required. Install with: pip3 install jinja2")
    raise SystemExit(1)


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Use pure-Python loader to avoid C extension issues on Python 3.14+
    return yaml.load(content, Loader=yaml.SafeLoader)


def tex_escape(text) -> str:
    """Escape special LaTeX characters."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def format_authors_vancouver(authors_str, max_authors=6) -> str:
    """Format an author string in Vancouver style.
    
    Vancouver rules:
    - List up to max_authors authors, then 'et al.' if more
    - Format: Surname Initials (no periods), comma-separated
    
    Input is already in approximate Vancouver format from RIMS/LaTeX:
    'Nilsonne G, Sun X, Nyström C, ...'
    where each author is a single comma-separated element.
    
    Some inputs use "Surname Initials, Surname Initials" (one element per author),
    others use "Surname, Initials, Surname, Initials" (two elements per author).
    We detect which format by checking patterns.
    """
    if not authors_str:
        return ""
    authors_str = str(authors_str).strip()
    
    # If already contains "et al" with few listed, return as-is
    if "et al" in authors_str.lower() and authors_str.count(",") < 15:
        return authors_str
    
    # Split by comma
    parts = [p.strip() for p in authors_str.split(",")]
    
    # Detect format: check if parts alternate between names and initials
    # "Surname, I, Surname, I" format has short parts (1-3 chars) at odd positions
    # "Surname I, Surname I" format has each part containing both name and initials
    two_element_format = False
    if len(parts) >= 4:
        # Check if parts[1], parts[3], parts[5] etc. look like initials
        initials_count = 0
        check_positions = min(6, len(parts))
        for j in range(1, check_positions, 2):
            p = parts[j].strip()
            if (len(p) <= 4 and p.replace("-", "").replace(" ", "").replace(".", "").isalpha()
                    and p[0].isupper()):
                initials_count += 1
        if initials_count >= 2:
            two_element_format = True
    
    if two_element_format:
        # Group pairs: (Surname, Initials) -> "Surname Initials"
        authors = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts):
                name = parts[i].strip()
                initials = parts[i + 1].strip()
                # Verify initials look right
                if (len(initials) <= 4 and 
                    initials.replace("-", "").replace(" ", "").replace(".", "").isalpha()):
                    authors.append(f"{name} {initials}")
                    i += 2
                    continue
            authors.append(parts[i].strip())
            i += 1
    else:
        # Each comma-separated part is already a complete author
        authors = [p.strip() for p in parts if p.strip()]
    
    if len(authors) > max_authors:
        return ", ".join(authors[:6]) + ", et al"
    else:
        return ", ".join(authors)


def format_links_latex(links) -> str:
    """Format links dict as LaTeX inline list."""
    if not links or not isinstance(links, dict):
        return ""
    labels = {
        "preprint": "preprint",
        "data": "data",
        "code": "code",
        "materials": "materials",
        "preregistration": "prereg",
        "narrative": "narrative",
        "slides": "slides",
        "video": "video",
        "protocol": "protocol",
        "web": "web",
        "poster": "poster",
        "correction": "correction",
    }
    parts = []
    seen_urls = set()
    for key, url in links.items():
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        label = labels.get(key, key)
        # Don't escape URLs - they go inside \href
        parts.append(rf"\href{{{url}}}{{{label}}}")
    if parts:
        return " [" + " | ".join(parts) + "]"
    return ""


def render_latex(data: dict, template_dir: str, template_name: str) -> str:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
    )
    env.filters["tex"] = tex_escape
    env.filters["links"] = format_links_latex
    env.filters["notrailingdot"] = lambda s: str(s).rstrip(".") if s else ""
    env.filters["doi"] = lambda s: str(s).replace("_", r"\_") if s else ""
    env.filters["vancouver_authors"] = format_authors_vancouver

    template = env.get_template(template_name)
    return template.render(**data)


def generate_outputs_list(data: dict) -> str:
    """Generate a Markdown list of all open outputs grouped by link type."""
    outputs = defaultdict(list)

    all_sections = ["publications", "preprints", "book_chapters", "presentations", "other_publications"]

    for section in all_sections:
        for entry in data.get(section, []):
            links = entry.get("links", {})
            if not links:
                continue
            for link_type, url in links.items():
                if not url:
                    continue
                outputs[link_type].append({
                    "title": entry.get("title", "Untitled"),
                    "year": entry.get("year", ""),
                    "url": url,
                    "doi": entry.get("doi", ""),
                })

    if not outputs:
        return "# Open Research Outputs\n\nNo linked outputs found yet. Add links to entries in cv_data.yaml.\n"

    lines = ["# Open Research Outputs\n",
             f"Generated from cv_data.yaml\n"]

    type_labels = {
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

    # Summary
    lines.append("## Summary\n")
    for link_type in sorted(outputs.keys(), key=lambda k: type_labels.get(k, k)):
        label = type_labels.get(link_type, link_type.title())
        lines.append(f"- **{label}**: {len(outputs[link_type])}")
    lines.append("")

    # Detail
    for link_type in sorted(outputs.keys(), key=lambda k: type_labels.get(k, k)):
        label = type_labels.get(link_type, link_type.title())
        lines.append(f"## {label}\n")
        entries = sorted(outputs[link_type], key=lambda e: str(e["year"]), reverse=True)
        for e in entries:
            doi_link = f" (DOI: [{e['doi']}](https://doi.org/{e['doi']}))" if e["doi"] else ""
            lines.append(f"- [{e['title']}]({e['url']}) ({e['year']}){doi_link}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render CV from YAML data")
    parser.add_argument("--data", default="cv_data.yaml", help="YAML data file")
    parser.add_argument("--template-dir", default="templates", help="Template directory")
    parser.add_argument("--template", default="cv.tex.j2", help="LaTeX template name")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF compilation")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_data(args.data)

    # Render LaTeX
    latex = render_latex(data, args.template_dir, args.template)
    tex_path = output_dir / "cv.tex"
    tex_path.write_text(latex, encoding="utf-8")
    print(f"Written: {tex_path}")

    # Compile PDF
    if not args.no_pdf:
        import subprocess
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", str(output_dir), str(tex_path)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"Written: {output_dir / 'cv.pdf'}")
            else:
                print(f"pdflatex failed (exit {result.returncode}). Check {output_dir}/cv.log")
                print(result.stdout[-500:] if result.stdout else "")
        except FileNotFoundError:
            print("pdflatex not found — skipping PDF. Install texlive or run on a machine with LaTeX.")

    # Generate outputs list
    outputs_md = generate_outputs_list(data)
    outputs_path = output_dir / "open_outputs.md"
    outputs_path.write_text(outputs_md, encoding="utf-8")
    print(f"Written: {outputs_path}")


if __name__ == "__main__":
    main()
