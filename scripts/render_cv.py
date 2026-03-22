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
    with open(path) as f:
        return yaml.safe_load(f)


def tex_escape(text: str) -> str:
    """Escape special LaTeX characters."""
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


def format_links_latex(links: dict) -> str:
    """Format links dict as LaTeX inline list."""
    if not links:
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
    }
    parts = []
    for key, url in links.items():
        if not url:
            continue
        label = labels.get(key, key)
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
        entries = sorted(outputs[link_type], key=lambda e: e["year"], reverse=True)
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
    tex_path.write_text(latex)
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
    outputs_path.write_text(outputs_md)
    print(f"Written: {outputs_path}")


if __name__ == "__main__":
    main()
