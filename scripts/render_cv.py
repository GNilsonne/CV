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
import datetime
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


def autolink(text) -> str:
    """Escape LaTeX special chars AND convert bare URLs/DOIs to \\href links.
    
    Recognises patterns like:
      doi: 10.xxx/yyy
      url: some.site/path
      osf: osf.io/xxx
      web: some.site/path
      Web: some.site/path
      archived: figshare, doi: 10.xxx
      Course materials: osf.io/xxx
      Program: ki.se/path  (but not just 'ki.se' without path)
      http://... or https://...
    """
    import re
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    
    # First, find all URL-like segments and protect them from tex_escape
    # We'll work with the raw text, find linkable patterns, and build output
    
    # Pattern: "label: url_text" where label is doi/url/osf/web/Web/archived/etc.
    # Also bare https?:// URLs
    
    # Collect segments: (start, end, raw_url, display_label)
    segments = []
    
    # Match "doi: 10.xxxx" patterns (including "doi of review report: 10.xxxx")
    for m in re.finditer(r'\bdoi(?:\s+of[^:]*)?:\s*(10\.\S+)', text):
        doi = m.group(1).rstrip('.,;)')
        url = f'https://doi.org/{doi}'
        full_match_text = m.group(0)
        if full_match_text.endswith(('.', ',', ';', ')')):
            full_match_text = full_match_text[:-1]
        segments.append((m.start(), m.start() + len(full_match_text), url, full_match_text))
    
    # Match "url: domain/path" patterns
    for m in re.finditer(r'\burl:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len('url: ') + len(raw), url, raw))
    
    # Match "osf: osf.io/xxx" patterns
    for m in re.finditer(r'\bosf:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len('osf: ') + len(raw), url, raw))
    
    # Match "web: domain/path" and "Web: domain/path" patterns
    for m in re.finditer(r'\b[Ww]eb:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len(m.group(0).split(raw)[0]) + len(raw), url, raw))
    
    # Match "Course materials: osf.io/xxx" patterns
    for m in re.finditer(r'Course materials:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        full_match = m.group(0)[:len('Course materials: ') + len(raw)]
        segments.append((m.start(), m.start() + len(full_match), url, f'Course materials: {raw}'))
    
    # Match "Program: domain/path" patterns
    for m in re.finditer(r'Program:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        if '/' in raw or '.' in raw:
            url = raw if raw.startswith('http') else f'https://{raw}'
            segments.append((m.start(), m.start() + len(m.group(0).split(raw)[0]) + len(raw), url, raw))
    
    # Match "archived: figshare, doi: 10.xxx" 
    for m in re.finditer(r'archived:\s*figshare,\s*doi:\s*(10\.\S+)', text):
        doi = m.group(1).rstrip('.,;)')
        url = f'https://doi.org/{doi}'
        segments.append((m.start(), m.start() + len(m.group(0)), url, f'archived: figshare, doi: {doi}'))
    
    # Match bare https?:// URLs not already inside \href
    for m in re.finditer(r'https?://\S+', text):
        raw = m.group(0).rstrip('.,;)')
        # Skip if already captured
        already = False
        for s_start, s_end, _, _ in segments:
            if m.start() >= s_start and m.end() <= s_end + 5:
                already = True
                break
        if not already:
            segments.append((m.start(), m.start() + len(raw), raw, raw))
    
    if not segments:
        return tex_escape(text)
    
    # Sort by start position, remove overlaps
    segments.sort(key=lambda x: x[0])
    filtered = []
    last_end = 0
    for start, end, url, label in segments:
        if start >= last_end:
            filtered.append((start, end, url, label))
            last_end = end
    
    # Build output
    result = []
    pos = 0
    for start, end, url, label in filtered:
        # Text before this segment: tex_escape
        if start > pos:
            result.append(tex_escape(text[pos:start]))
        # The link itself: don't tex_escape the URL inside \href
        display = tex_escape(label)
        result.append(f'\\href{{{url}}}{{{display}}}')
        pos = end
    # Remaining text
    if pos < len(text):
        result.append(tex_escape(text[pos:]))
    
    return ''.join(result)


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
        rendered = ", ".join(authors[:6]) + ", et al"
    else:
        rendered = ", ".join(authors)
    # Templates append their own period after the author list, so drop a
    # trailing one carried in from the source data to avoid "Melin B..".
    if rendered.endswith(".") and not rendered.endswith("et al."):
        rendered = rendered[:-1]
    return rendered


def profile_handle(url) -> str:
    """Derive a short display handle from a profile URL.

    The header previously hardcoded handles that duplicated cv_data.yaml, so a
    changed URL would leave a stale label behind. Prefer an explicit user id in
    the query string, else fall back to the last non-empty path segment.
    """
    raw = str(url).strip() if url else ""
    if not raw:
        return ""
    base, _, query = raw.partition("?")
    for pair in query.split("&"):
        key, _, value = pair.partition("=")
        if key in ("user", "id") and value:
            return tex_escape(value)
    segments = [s for s in base.rstrip("/").split("/") if s]
    if len(segments) <= 2:  # scheme + host only, no path to name
        return tex_escape(segments[-1]) if segments else ""
    return tex_escape(segments[-1])


def format_title_sentence(text) -> str:
    """Escape a title and terminate it with a single period.

    Titles in the data end inconsistently: some carry a trailing period, some
    none, and some end in ? or !. Appending a period unconditionally produced
    "...hur gor vi?." so sentence-final punctuation is left alone. A dangling
    trailing colon introduces nothing once rendered, so it is replaced by the
    normal period separator rather than preserved.
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


def _canonical_url(url) -> str:
    """Normalise a URL for duplicate detection only.

    Ignores scheme, host aliases used by DOI resolvers, and a trailing slash,
    so ``http://dx.doi.org/10.x`` and ``https://doi.org/10.x`` compare equal.
    The original URL is still what gets linked.
    """
    text = str(url).strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    for host in ("dx.doi.org/", "doi.org/", "www."):
        if text.startswith(host):
            text = text[len(host) :]
    return text.rstrip("/")


def _fallback_link_label(key: str) -> str:
    """Pick a short label for a links key missing from the known label map.

    Some entries use the link text itself as the key: a bare DOI, a domain, or
    even the whole description. Printing those verbatim gives an unreadable
    label, so collapse them to the generic label their shape implies. Short,
    word-like keys pass through so new descriptive keys still work.
    """
    key = str(key).strip()
    if not key:
        return "link"
    lowered = key.lower()
    if lowered.startswith("10.") or lowered.startswith("doi:"):
        return "doi"
    if lowered.startswith(("http://", "https://", "www.")) or "/" in key:
        return "link"
    if " " not in key and "." in key:
        return "web"
    if " " in key or len(key) > 24:
        return "link"
    return key


def _link_parts(links, seen_urls=None) -> list:
    """Return a list of \\href{url}{label} strings from a links dict.

    Pass ``seen_urls`` to suppress URLs already emitted by the caller, so an
    entry whose ``links`` repeats its own DOI renders one label, not two.
    """
    if not links or not isinstance(links, dict):
        return []
    labels = {
        "preprint": "preprint",
        "data": "data",
        "code": "code",
        "materials": "materials",
        "preregistration": "preregistration",
        "narrative": "narrative",
        "slides": "slides",
        "video": "video",
        "protocol": "protocol",
        "web": "web",
        "poster": "poster",
        "correction": "correction",
        "pdf": "pdf",
        "diva": "DiVA",
        "program": "program",
        "thesis": "thesis",
        "certificate": "certificate",
        "swecris": "SweCRIS",
        "cordis": "CORDIS",
        "doi": "doi",
        "osf": "OSF",
        "link": "link",
        "url": "link",
        "transcript": "transcript",
    }
    parts = []
    if seen_urls is None:
        seen_urls = set()
    for key, url in links.items():
        if not url or _canonical_url(url) in seen_urls:
            continue
        seen_urls.add(_canonical_url(url))
        label = labels.get(key, _fallback_link_label(key))
        parts.append(rf"\href{{{url}}}{{{tex_escape(label)}}}")
    return parts


def format_links_latex(links) -> str:
    """Format links dict as LaTeX inline bracketed list."""
    parts = _link_parts(links)
    if parts:
        return " [" + " | ".join(parts) + "]"
    return ""


def format_links_with_doi(doi, links) -> str:
    """Combine DOI and links into a single bracketed group separated by |."""
    parts = []
    seen_urls = set()
    if doi:
        doi_url = f"https://doi.org/{doi}"
        seen_urls.add(_canonical_url(doi_url))
        parts.append(rf"\href{{{doi_url}}}{{doi}}")
    parts.extend(_link_parts(links, seen_urls))
    if parts:
        return " [" + " | ".join(parts) + "]"
    return ""


def _is_url(value) -> bool:
    """True when a value looks like a link rather than free text."""
    if not value:
        return False
    text = str(value).strip()
    if not text or " " in text:
        return False
    return text.startswith(("http://", "https://", "doi:", "10.", "urn:", "www."))


def format_entry_date(entry) -> str:
    """Return an entry's date if present, otherwise its year.

    A full ``date`` (e.g. 2009-12-11) is more specific than ``year``, so it wins
    when both are given. YAML parses ISO dates into date objects, so format
    those back to ISO strings rather than relying on ``str()`` of a datetime.
    """
    if not entry or not isinstance(entry, dict):
        return ""
    date = entry.get("date")
    if date:
        if isinstance(date, (datetime.date, datetime.datetime)):
            return date.strftime("%Y-%m-%d")
        return str(date).strip()
    year = entry.get("year")
    if year:
        return str(year).strip()
    return ""


def format_entry_links(entry, keys) -> str:
    """Format an entry's top-level URL fields as a bracketed link group.

    Mirrors the bracketed ``[a | b]`` style used by the publication sections,
    with the brackets outside the hyperlink. Link fields sit at the top level of
    these entries rather than in a nested ``links`` dict, so they are collected
    explicitly to keep label order stable. Values that are not URLs are skipped
    so stale free-text entries never produce a broken \\href.
    """
    if not entry or not isinstance(entry, dict):
        return ""
    links = {}
    for key in keys:
        url = entry.get(key)
        if _is_url(url):
            links[key] = str(url).strip()
    return format_links_latex(links)


def format_degree_date(degree) -> str:
    """Date-or-year for a degree entry."""
    return format_entry_date(degree)


def format_degree_links(degree) -> str:
    """Thesis/certificate links for a degree entry."""
    return format_entry_links(degree, ("thesis", "certificate", "link"))


def format_supervision_title(entry) -> str:
    """Thesis title for a supervision entry.

    Prefers the ``title`` field. Older entries stored the title in ``thesis``
    with the URL in ``link``; when ``thesis`` holds free text rather than a URL
    it is used as the title so those entries still render.
    """
    if not entry or not isinstance(entry, dict):
        return ""
    title = entry.get("title")
    if title and str(title).strip():
        return str(title).strip()
    legacy = entry.get("thesis")
    if legacy and not _is_url(legacy):
        return str(legacy).strip()
    return ""


def format_supervision_links(entry) -> str:
    """Thesis link for a supervision entry.

    The URL normally sits in ``thesis``, but older entries put it in ``link``.
    Either way it points at the thesis, so it is labelled ``thesis``.
    """
    if not entry or not isinstance(entry, dict):
        return ""
    for key in ("thesis", "link"):
        url = entry.get(key)
        if _is_url(url):
            return format_links_latex({"thesis": str(url).strip()})
    return ""


def _normalise_url(key, value) -> str:
    """Expand a shorthand link value into a full URL.

    Data files store DOIs bare (``10.6084/...``) and other links as bare domains
    (``osf.io/xxx``, ``openarchive.ki.se/...``), so add the scheme and DOI
    resolver here rather than requiring fully-qualified URLs in the YAML.
    """
    text = str(value).strip().rstrip(".,;")
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    if key == "doi" or text.startswith("10."):
        return f"https://doi.org/{text}"
    if text.startswith("urn:"):
        return f"http://urn.kb.se/resolve?urn={text}"
    return f"https://{text}"


def format_student_links(entry) -> str:
    """Bracketed link group for a student thesis entry.

    Brackets sit outside the hyperlinks. Values may be bare DOIs or bare
    domains, so each is normalised to a full URL first.
    """
    if not entry or not isinstance(entry, dict):
        return ""
    links = {}
    for key in ("doi", "link", "osf"):
        url = _normalise_url(key, entry.get(key, ""))
        if url:
            links[key] = url
    return format_links_latex(links)


def format_award_links(entry) -> str:
    """Bracketed link group for an award entry, brackets outside the hyperlink."""
    return format_entry_links(entry, ("link",))


def format_grant_links(entry) -> str:
    """Link/SweCRIS/CORDIS links for a grant entry, in that order."""
    return format_entry_links(entry, ("link", "swecris", "cordis"))


def format_peer_review_links(review) -> str:
    """Combine paper DOI and report DOIs into a single bracketed group."""
    parts = []
    paper_doi = review.get('paper_doi', '')
    report_dois = review.get('report_dois', [])
    if paper_doi:
        parts.append(rf"\href{{https://doi.org/{paper_doi}}}{{doi for paper}}")
    for i, rd in enumerate(report_dois):
        if len(report_dois) > 1:
            parts.append(rf"\href{{https://doi.org/{rd}}}{{doi for report {i+1}}}")
        else:
            parts.append(rf"\href{{https://doi.org/{rd}}}{{doi for report}}")
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
    env.filters["autolink"] = autolink
    env.filters["links"] = format_links_latex
    env.filters["doilinks"] = lambda entry: format_links_with_doi(entry.get('doi', ''), entry.get('links', {}))
    env.filters["reviewlinks"] = format_peer_review_links
    env.filters["degreedate"] = format_degree_date
    env.filters["degreelinks"] = format_degree_links
    env.filters["entrydate"] = format_entry_date
    env.filters["supervisiontitle"] = format_supervision_title
    env.filters["supervisionlinks"] = format_supervision_links
    env.filters["grantlinks"] = format_grant_links
    env.filters["studentlinks"] = format_student_links
    env.filters["awardlinks"] = format_award_links
    env.filters["notrailingdot"] = lambda s: str(s).rstrip(".") if s else ""
    env.filters["titledot"] = format_title_sentence
    env.filters["handle"] = profile_handle
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
