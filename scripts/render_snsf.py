#!/usr/bin/env python3
"""
Render an SNSF-compatible narrative CV from cv_data.yaml.

Usage:
    python3 scripts/render_snsf.py [--data cv_data.yaml] [--config snsf_config.yaml] [--output output/]

Outputs:
    output/snsf_cv.tex      — Generated LaTeX source
    output/snsf_cv.pdf      — Compiled PDF (if pdflatex available)
"""

import argparse
from datetime import date
from pathlib import Path

import yaml

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 required. Install with: pip3 install jinja2")
    raise SystemExit(1)


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return yaml.load(content, Loader=yaml.SafeLoader) or {}


def tex_escape(text) -> str:
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
    import re
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""

    segments = []

    for m in re.finditer(r'\bdoi(?:\s+of[^:]*)?:\s*(10\.\S+)', text):
        doi = m.group(1).rstrip('.,;)')
        url = f'https://doi.org/{doi}'
        full_match_text = m.group(0)
        if full_match_text.endswith(('.', ',', ';', ')')):
            full_match_text = full_match_text[:-1]
        segments.append((m.start(), m.start() + len(full_match_text), url, full_match_text))

    for m in re.finditer(r'\burl:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len('url: ') + len(raw), url, raw))

    for m in re.finditer(r'\bosf:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len('osf: ') + len(raw), url, raw))

    for m in re.finditer(r'\b[Ww]eb:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        segments.append((m.start(), m.start() + len(m.group(0).split(raw)[0]) + len(raw), url, raw))

    for m in re.finditer(r'Course materials:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        url = raw if raw.startswith('http') else f'https://{raw}'
        full_match = m.group(0)[:len('Course materials: ') + len(raw)]
        segments.append((m.start(), m.start() + len(full_match), url, f'Course materials: {raw}'))

    for m in re.finditer(r'Program:\s*(\S+)', text):
        raw = m.group(1).rstrip('.,;)')
        if '/' in raw or '.' in raw:
            url = raw if raw.startswith('http') else f'https://{raw}'
            segments.append((m.start(), m.start() + len(m.group(0).split(raw)[0]) + len(raw), url, raw))

    for m in re.finditer(r'archived:\s*figshare,\s*doi:\s*(10\.\S+)', text):
        doi = m.group(1).rstrip('.,;)')
        url = f'https://doi.org/{doi}'
        segments.append((m.start(), m.start() + len(m.group(0)), url, f'archived: figshare, doi: {doi}'))

    for m in re.finditer(r'https?://\S+', text):
        raw = m.group(0).rstrip('.,;)')
        already = False
        for s_start, s_end, _, _ in segments:
            if m.start() >= s_start and m.end() <= s_end + 5:
                already = True
                break
        if not already:
            segments.append((m.start(), m.start() + len(raw), raw, raw))

    if not segments:
        return tex_escape(text)

    segments.sort(key=lambda x: x[0])
    filtered = []
    last_end = 0
    for start, end, url, label in segments:
        if start >= last_end:
            filtered.append((start, end, url, label))
            last_end = end

    result = []
    pos = 0
    for start, end, url, label in filtered:
        if start > pos:
            result.append(tex_escape(text[pos:start]))
        display = tex_escape(label)
        result.append(f'\\href{{{url}}}{{{display}}}')
        pos = end
    if pos < len(text):
        result.append(tex_escape(text[pos:]))

    return ''.join(result)


def format_authors_vancouver(authors_str, max_authors=6) -> str:
    if not authors_str:
        return ""
    authors_str = str(authors_str).strip()
    if "et al" in authors_str.lower() and authors_str.count(",") < 15:
        return authors_str

    parts = [p.strip() for p in authors_str.split(",")]
    two_element_format = False
    if len(parts) >= 4:
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
        return ", ".join(authors[:max_authors]) + ", et al"
    return ", ".join(authors)


def _link_parts(links) -> list:
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
        "url": "link",
    }
    parts = []
    seen_urls = set()
    for key, url in links.items():
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        label = labels.get(key, key)
        parts.append(rf"\href{{{url}}}{{{label}}}")
    return parts


def format_links_with_doi(doi, links) -> str:
    parts = []
    if doi:
        parts.append(rf"\href{{https://doi.org/{doi}}}{{doi}}")
    parts.extend(_link_parts(links))
    if parts:
        return " [" + " | ".join(parts) + "]"
    return ""


def format_work_reference(work: dict) -> str:
    if not work:
        return ""

    title = tex_escape(str(work.get("title", "")).rstrip("."))
    year = tex_escape(work.get("year", ""))
    authors = format_authors_vancouver(work.get("authors", ""), max_authors=20)
    authors = tex_escape(authors)
    venue = work.get("journal") or work.get("publisher") or work.get("venue") or work.get("type") or ""
    venue = tex_escape(str(venue).rstrip(".")) if venue else ""

    parts = []
    if authors:
        parts.append(f"{authors}.")
    if title:
        parts.append(f"\\emph{{{title}}}.")
    if venue:
        parts.append(f"{venue}.")
    if year:
        parts.append(str(year))

    links = format_links_with_doi(work.get("doi", ""), work.get("links", {}))
    reference = " ".join(p for p in parts if p).strip()
    return reference + links


def parse_year_from_text(text: str):
    import re
    if not text:
        return None
    years = re.findall(r"(?:19|20)\d{2}", str(text))
    if not years:
        return None
    return int(years[-1])


def collect_all_works(data: dict) -> dict:
    sections = [
        "publications",
        "preprints",
        "books",
        "reports",
        "study_materials",
        "digital_research_objects",
        "scholarly_debate",
        "invited_talks",
        "conference_presentations",
        "conference_abstracts",
        "popular_science_writings",
        "popular_science_talks",
        "blogging",
    ]
    works = {}
    for section in sections:
        for item in data.get(section, []) or []:
            item_copy = dict(item)
            item_copy.setdefault("type", section[:-1] if section.endswith("s") else section)
            item_copy.setdefault("section", section)
            if item_copy.get("id"):
                works[item_copy["id"]] = item_copy
    return works


def compute_net_academic_age(snsf_config: dict) -> str:
    naa = snsf_config.get("net_academic_age", {}) or {}
    if naa.get("display"):
        return str(naa["display"])

    phd_year = naa.get("phd_year") or naa.get("degree_year")
    if not phd_year:
        return ""

    today = date.today()
    years = today.year - int(phd_year)
    months = today.month - int(naa.get("phd_month", 1))
    if months < 0:
        years -= 1
        months += 12

    deduction_months = int(naa.get("deduction_months", 0) or 0)
    total_months = max(0, years * 12 + months - deduction_months)
    out_years, out_months = divmod(total_months, 12)
    return f"{out_years} years, {out_months} months"


def build_context(data: dict, snsf_config: dict) -> dict:
    meta = data.get("meta", {})
    all_works = collect_all_works(data)

    education = sorted(
        data.get("degrees", []),
        key=lambda item: item.get("year") or parse_year_from_text(item.get("description", "")) or 0,
    )
    employment = sorted(
        data.get("employment", []),
        key=lambda item: parse_year_from_text(item.get("description", "")) or 0,
    )

    achievements = []
    missing_work_ids = []
    for achievement in snsf_config.get("achievements", []) or []:
        selected_works = []
        for work_id in achievement.get("selected_work_ids", []) or []:
            work = all_works.get(work_id)
            if work:
                selected_works.append(work)
            else:
                missing_work_ids.append(work_id)
        achievements.append({
            "title": achievement.get("title", ""),
            "category": achievement.get("category", ""),
            "description": achievement.get("description", ""),
            "selected_works": selected_works,
        })

    selected_works_count = sum(len(item["selected_works"]) for item in achievements)
    if selected_works_count > 10:
        raise ValueError(f"SNSF CV allows at most 10 selected works; found {selected_works_count}.")
    if missing_work_ids:
        raise ValueError("SNSF config references unknown work ids: " + ", ".join(missing_work_ids))

    return {
        "meta": meta,
        "education": education,
        "employment": employment,
        "achievements": achievements,
        "net_academic_age": compute_net_academic_age(snsf_config),
        "snsf_notes": snsf_config.get("notes", []),
    }


def render_latex(context: dict, template_dir: str, template_name: str) -> str:
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
    env.filters["workref"] = format_work_reference

    template = env.get_template(template_name)
    return template.render(**context)


def main():
    parser = argparse.ArgumentParser(description="Render SNSF narrative CV from YAML data")
    parser.add_argument("--data", default="cv_data.yaml", help="YAML data file")
    parser.add_argument("--config", default="snsf_config.yaml", help="SNSF configuration file")
    parser.add_argument("--template-dir", default="templates", help="Template directory")
    parser.add_argument("--template", default="snsf_cv.tex.j2", help="LaTeX template name")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF compilation")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_yaml(args.data)
    snsf_config = load_yaml(args.config)
    context = build_context(data, snsf_config)

    latex = render_latex(context, args.template_dir, args.template)
    tex_path = output_dir / "snsf_cv.tex"
    tex_path.write_text(latex, encoding="utf-8")
    print(f"Written: {tex_path}")

    if not args.no_pdf:
        import subprocess
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", str(output_dir), str(tex_path)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"Written: {output_dir / 'snsf_cv.pdf'}")
            else:
                print(f"pdflatex failed (exit {result.returncode}). Check {output_dir}/snsf_cv.log")
                print(result.stdout[-500:] if result.stdout else "")
        except FileNotFoundError:
            print("pdflatex not found — skipping PDF. Install texlive or run on a machine with LaTeX.")


if __name__ == "__main__":
    main()
