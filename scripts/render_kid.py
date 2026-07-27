#!/usr/bin/env python3
"""
Render a KI-style publication list for peer-reviewed research articles from the
last 5 years in a single list.

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


def bold_name(text, name="Nilsonne G") -> str:
    if not text:
        return ""
    escaped_name = tex_escape(name)
    if escaped_name in text:
        return text.replace(escaped_name, r"\textbf{" + escaped_name + "}")
    return text


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
        # pdflatex echoes source lines in its own 8-bit encoding, so decoding its
        # output strictly as UTF-8 crashes on Swedish characters. Replace rather
        # than fail: this text is only used for the error message below.
        result = subprocess.run(
            command, cwd=workdir, capture_output=True, text=True, errors="replace"
        )
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

    publications = data.get("publications", []) or []
    peer_reviewed_articles = sorted(
        [pub for pub in publications if in_year_range(pub, start_year, end_year)],
        key=lambda pub: ((pub.get("year", 0) or 0), pub.get("date", "")),
        reverse=True,
    )

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
    env.filters["vr_authors"] = lambda value: tex_escape(format_authors_vancouver(value))
    env.filters["vr_bold_name"] = bold_name

    template = env.from_string(r"""\documentclass[11pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage[margin=2.5cm]{geometry}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage[hyphens]{url}
\usepackage{xurl}
\usepackage[colorlinks,breaklinks=true]{hyperref}

\hypersetup{
    urlcolor=blue!70!black,
    linkcolor=blue!70!black,
}

\linespread{1.0}

\pagestyle{empty}

\setlist[enumerate]{leftmargin=2.5em, labelsep=0.5em, itemsep=0.5ex, parsep=0.3ex, topsep=0.5ex}
\sloppy

\begin{document}

\begin{center}
\textbf{<< meta.name|tex >> -- Publication List}
\end{center}

\section*{Peer-reviewed research articles << year_label >>}

\begin{enumerate}
<% for pub in peer_reviewed_articles %>
\item <% if pub.authors %><< pub.authors|vr_authors|vr_bold_name >>. <% endif %><< pub.title|notrailingdot|tex >>. <% if pub.journal %>\textit{<< pub.journal|notrailingdot|tex >>}<% endif %><% if pub.year %> << pub.year >><% endif %><% if pub.volume %>;<< pub.volume >><% endif %><% if pub.issue %>(<< pub.issue >>)<% endif %><% if pub.pages %>:<< pub.pages >><% elif pub.article_number %>:<< pub.article_number >><% endif %>.<% if pub.doi %> doi:~\href{https://doi.org/<< pub.doi >>}{<< pub.doi|doi >>}<% endif %>
<% endfor %>
\end{enumerate}

\end{document}
""")

    output = template.render(
        meta=data.get("meta", {}),
        year_label=f"{start_year}--{end_year}",
        peer_reviewed_articles=peer_reviewed_articles,
    )

    os.makedirs("output", exist_ok=True)
    tex_path = os.path.join("output", "kid_publist.tex")
    with open(tex_path, "w", encoding="utf-8") as handle:
        handle.write(output)
    print(f"Written: {tex_path}")
    print(f"Peer-reviewed research articles {start_year}-{end_year}: {len(peer_reviewed_articles)}")

    if not args.no_pdf:
        try:
            compile_pdf(tex_path)
            print(f"Written: {tex_path[:-4] + '.pdf'}")
        except FileNotFoundError:
            print("pdflatex not found — skipping PDF compilation")


if __name__ == "__main__":
    main()
