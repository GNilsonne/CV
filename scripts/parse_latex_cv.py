#!/usr/bin/env python3
"""
Parse CV_GN.tex into cv_data.yaml. V2 — improved title/author/link extraction.
"""

import re
import yaml
from pathlib import Path


def clean_latex(text: str) -> str:
    """Remove LaTeX formatting."""
    text = re.sub(r'(?<!\\)%.*$', '', text, flags=re.MULTILINE)
    text = text.replace(r'\\', ' ')
    # Remove commands but keep content
    for cmd in [r'\textbf', r'\textit', r'\emph', r'\bf', r'\it']:
        text = text.replace(cmd, '')
    text = re.sub(r'(?<!\\)\{', '', text)
    text = re.sub(r'(?<!\\)\}', '', text)
    text = text.replace(r'\&', '&').replace(r'\%', '%').replace(r'\$', '$')
    text = text.replace(r'\#', '#').replace(r'\_', '_')
    text = text.replace(r'bioR$\chi$iv', 'bioRxiv').replace(r'MedR$\chi$iv', 'MedRxiv')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_hrefs(text):
    return re.findall(r'\\href\{([^}]*)\}\{([^}]*)\}', text)


def extract_links(text):
    """Extract links using keyword context."""
    links = {}
    hrefs = extract_hrefs(text)
    
    for url, label in hrefs:
        idx = text.find(f'\\href{{{url}}}{{{label}}}')
        if idx < 0:
            continue
        context = text[max(0, idx-200):idx].lower()
        url_lower = url.lower()
        
        # Skip plain DOI links (the paper's own DOI)
        if ('doi.org' in url_lower or 'dx.doi.org' in url_lower):
            # But keep ancillary DOIs (zenodo, dryad, figshare, osf)
            if not any(x in url_lower for x in ['zenodo', 'dryad', 'figshare', 'osf.io']):
                # Unless it's a preprint doi
                if not any(x in context for x in ['preprint', 'postprint']):
                    continue
        
        # Preprint / postprint
        if any(x in context for x in ['preprint:', 'preprint.', 'preprint,', 'postprint:', "authors' postprint"]):
            links.setdefault('preprint', url)
        elif any(x in url_lower for x in ['psyarxiv', 'biorxiv', 'medrxiv', 'arxiv.org/abs', 'ecoevorxiv', 'socarxiv', 'metaarxiv']):
            links.setdefault('preprint', url)
        elif any(x in url_lower for x in ['hdl.handle.net/10616', 'openarchive.ki.se']):
            links.setdefault('preprint', url)
        elif 'repository.essex' in url_lower:
            links.setdefault('preprint', url)
        # Preregistration
        elif any(x in context for x in ['preregistration', 'pre-registration']) or 'clinicaltrials.gov' in url_lower:
            links.setdefault('preregistration', url)
        # Data and code combined
        elif 'data and code' in context:
            links.setdefault('data', url)
            links.setdefault('code', url)
        # Data
        elif any(x in context for x in ['associated data', 'data publication', 'data:']):
            links.setdefault('data', url)
        elif any(x in url_lower for x in ['openneuro.org', 'dryad', 'ncbi.nlm.nih.gov/geo']):
            links.setdefault('data', url)
        # Code
        elif 'github.com' in url_lower and 'code' not in links:
            links.setdefault('code', url)
        elif 'zenodo' in url_lower and 'data' not in links:
            links.setdefault('code', url)
        # Materials
        elif 'stimulus material' in context or 'course material' in context:
            links.setdefault('materials', url)
        # Slides
        elif 'slide' in context:
            links.setdefault('slides', url)
        # Video
        elif any(x in context for x in ['video', 'recording']) or any(x in url_lower for x in ['youtube.com', 'vimeo.com']):
            links.setdefault('video', url)
        # Poster
        elif 'poster' in context:
            links.setdefault('poster', url)
        # Web
        elif any(x in context for x in ['web:', 'url:', 'web,', '\nurl:']):
            links.setdefault('web', url)
        # OSF in data context
        elif 'osf.io' in url_lower and 'associated' in context:
            links.setdefault('data', url)
    
    return links


def extract_doi(text):
    # Match doi: \href{...}{10.xxx} or \href{https://doi.org/10.xxx}{...}
    m = re.search(r'doi:\s*\\href\{[^}]*\}\{([^}]*)\}', text)
    if m:
        return re.sub(r'^doi:?\s*', '', m.group(1).strip(), flags=re.IGNORECASE)
    m = re.search(r'\\href\{https?://(?:dx\.)?doi\.org/([^}]*)\}', text)
    if m:
        return m.group(1).strip()
    return ""


def split_items(section_text):
    items = re.split(r'\\item\s+', section_text)
    return [i.strip() for i in items if i.strip() and len(i.strip()) > 20]


def find_section(tex, name):
    """Find section text between its header and the next section/subsection."""
    escaped = re.escape(name)
    pat = rf'\\(?:sub)?section\*\{{{escaped}\}}(.*?)(?=\\(?:sub)?section\*\{{|\\newpage\s*\\section|$)'
    m = re.search(pat, tex, re.DOTALL)
    return m.group(1) if m else ""


def parse_pub_item(item):
    """Parse a publication from the CV LaTeX format."""
    # The CV pattern is: 
    # \textbf{\textit{Nilsonne G}}, Author2, ... \textbf{Title.} \emph{Journal} Year ...
    # OR: Author1, \textbf{\textit{Nilsonne G}}, ... \textbf{Title.} \emph{Journal} Year ...
    
    # Find ALL \textbf{...} blocks
    bold_blocks = list(re.finditer(r'\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}', item))
    
    title = ""
    authors_end = 0
    
    if len(bold_blocks) >= 2:
        # Usually the last substantial \textbf is the title
        # The first one(s) are author names (e.g., \textbf{\textit{Nilsonne G}})
        for i, block in enumerate(bold_blocks):
            content = block.group(1).strip()
            # If it contains \textit{...Nilsonne...} or is just an author name, skip
            if 'Nilsonne' in content or 'Open Science Collaboration' in content or len(content) < 15:
                authors_end = block.end()
                continue
            # This is likely the title
            title = clean_latex(content).strip().rstrip('.')
            authors_end = block.start()
            break
    elif len(bold_blocks) == 1:
        content = bold_blocks[0].group(1).strip()
        if 'Nilsonne' not in content:
            title = clean_latex(content).strip().rstrip('.')
    
    if not title:
        # Fallback: look for the longest bold block that isn't an author
        for block in sorted(bold_blocks, key=lambda b: len(b.group(1)), reverse=True):
            content = block.group(1).strip()
            if 'Nilsonne' not in content and len(content) > 20:
                title = clean_latex(content).strip().rstrip('.')
                authors_end = block.start()
                break
    
    # Extract authors (everything before the title bold block)
    if authors_end > 0:
        authors_text = item[:authors_end]
    else:
        authors_text = ""
    authors = clean_latex(authors_text).strip().rstrip('.').rstrip(',')
    # Clean up leading/trailing artifacts
    authors = re.sub(r'^\s*,\s*', '', authors)
    authors = re.sub(r'\s*,\s*$', '', authors)
    if not authors or len(authors) < 3:
        authors = ""
    
    # Extract journal
    journal = ""
    journal_matches = re.findall(r'(?:\\emph|\\textit)\{([^}]+)\}', item)
    for jm in journal_matches:
        jm_clean = clean_latex(jm)
        # Skip if it's a preprint server name or too short
        if jm_clean in title or len(jm_clean) < 3:
            continue
        if any(x in jm_clean.lower() for x in ['biorxiv', 'psyarxiv', 'medrxiv', 'socarxiv', 'figshare']):
            continue
        journal = jm_clean
        break
    
    # Extract year
    year = 0
    # Look for year after journal name or in the main text
    year_match = re.search(r'\b(19\d{2}|20[0-2]\d)\b', item)
    if year_match:
        year = int(year_match.group(1))
    
    doi = extract_doi(item)
    links = extract_links(item)
    
    entry = {"title": title, "authors": authors, "year": year}
    if doi:
        entry["doi"] = doi
    if journal:
        entry["journal"] = journal
    entry["links"] = links if links else {}
    return entry


def parse_presentation_item(item, pres_type=""):
    """Parse a presentation item."""
    bold_blocks = list(re.finditer(r'\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}', item))
    
    title = ""
    for block in bold_blocks:
        content = block.group(1).strip()
        if 'Nilsonne' not in content and len(clean_latex(content)) > 10:
            title = clean_latex(content).strip().rstrip('.')
            break
    
    if not title:
        # Try {\bf ...} pattern
        bf_match = re.search(r'\{\\bf\s+([^}]+)\}', item)
        if bf_match:
            title = clean_latex(bf_match.group(1)).strip().rstrip('.')
    
    if not title:
        title = clean_latex(item[:100]).strip()
    
    year = 0
    year_match = re.search(r'((?:19|20)\d{2})', item)
    if year_match:
        year = int(year_match.group(1))
    
    event = ""
    event_matches = re.findall(r'(?:\\emph|\\textit)\{([^}]+)\}', item)
    for em in event_matches:
        em_clean = clean_latex(em)
        if em_clean != title and len(em_clean) > 3:
            event = em_clean
            break
    
    links = extract_links(item)
    
    # For presentations, OSF links without other context are usually slides
    if not links:
        hrefs = extract_hrefs(item)
        for url, label in hrefs:
            if 'osf.io' in url.lower() and 'doi.org' not in url.lower():
                links['slides'] = url
                break
    
    entry = {"title": title, "year": year, "type": pres_type}
    if event:
        entry["event"] = event
    entry["links"] = links if links else {}
    return entry


def parse_other_item(item, section_source=""):
    """Parse other publications (scholarly debate, reports, etc.)."""
    bold_blocks = list(re.finditer(r'\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}', item))
    
    title = ""
    authors_end = 0
    for block in bold_blocks:
        content = block.group(1).strip()
        if 'Nilsonne' not in content and len(clean_latex(content)) > 10:
            title = clean_latex(content).strip().rstrip('.')
            authors_end = block.start()
            break
    
    if not title:
        bf_match = re.search(r'\{\\bf\s+([^}]+)\}', item)
        if bf_match:
            title = clean_latex(bf_match.group(1)).strip().rstrip('.')
    
    authors = ""
    if authors_end > 0:
        authors = clean_latex(item[:authors_end]).strip().rstrip('.').rstrip(',')
    if not authors or len(authors) < 3:
        authors = "Nilsonne G"
    
    year = 0
    year_match = re.search(r'((?:19|20)\d{2})', item)
    if year_match:
        year = int(year_match.group(1))
    
    journal = ""
    journal_matches = re.findall(r'(?:\\emph|\\textit)\{([^}]+)\}', item)
    for jm in journal_matches:
        jm_clean = clean_latex(jm)
        if jm_clean != title and len(jm_clean) > 3:
            journal = jm_clean
            break
    
    doi = extract_doi(item)
    links = extract_links(item)
    
    # For other pubs, non-DOI hrefs without other classification are "web" links
    if not links:
        hrefs = extract_hrefs(item)
        for url, label in hrefs:
            if 'doi.org' not in url:
                links['web'] = url
                break
    
    entry = {"title": title, "authors": authors, "year": year}
    if doi:
        entry["doi"] = doi
    if journal:
        entry["journal"] = journal
    entry["links"] = links if links else {}
    if section_source:
        entry["section_source"] = section_source
    return entry


def main():
    tex = Path("/tmp/cv-repo/CV_GN.tex").read_text(encoding='utf-8')
    output = Path("/home/ubuntu/.openclaw/workspace/cv-generator/cv_data.yaml")
    
    data = {
        "meta": {
            "name": "Gustav Nilsonne",
            "orcid": "0000-0001-5273-0150",
            "affiliation": "Karolinska Institutet",
            "email": "gustav.nilsonne@ki.se",
        },
        "publications": [],
        "preprints": [],
        "book_chapters": [],
        "presentations": [],
        "other_publications": [],
    }
    
    # Publications
    section = find_section(tex, "Publications in academic journals")
    items = split_items(section)
    print(f"Publications: {len(items)} items")
    for item in items:
        e = parse_pub_item(item)
        if e["title"] and len(e["title"]) > 5:
            data["publications"].append(e)
        else:
            print(f"  SKIPPED (bad title): {e['title'][:50]}... doi={e.get('doi','')}")
    
    # Preprints
    section = find_section(tex, "Preprints")
    items = split_items(section)
    print(f"Preprints: {len(items)} items")
    for item in items:
        e = parse_pub_item(item)
        if e["title"] and len(e["title"]) > 5:
            data["preprints"].append(e)
    
    # Books
    section = find_section(tex, "Books")
    items = split_items(section)
    print(f"Books: {len(items)} items")
    for item in items:
        e = parse_other_item(item)
        if e["title"]:
            data["book_chapters"].append(e)
    
    # Presentations
    for sec_name, ptype in [
        ("Invited talks", "invited"),
        ("Conference presentations", "conference"),
        ("Popular science talks", "popular-science"),
        ("Other indexed conference abstracts", "conference-abstract"),
    ]:
        section = find_section(tex, sec_name)
        items = split_items(section)
        print(f"{sec_name}: {len(items)} items")
        for item in items:
            e = parse_presentation_item(item, ptype)
            if e["title"] and e["year"]:
                data["presentations"].append(e)
    
    # Other publications
    for sec_name in [
        "Open peer-review reports",
        "Reports",
        "Study Materials",
        "Other digital research objects",
        "Scholarly debate",
        "Popular science writings and general debate",
        "Blogging",
    ]:
        section = find_section(tex, sec_name)
        if not section:
            continue
        items = split_items(section)
        print(f"{sec_name}: {len(items)} items")
        for item in items:
            e = parse_other_item(item, sec_name)
            if e["title"]:
                data["other_publications"].append(e)
    
    # Sort
    for key in ["publications", "preprints", "presentations", "other_publications"]:
        data[key].sort(key=lambda e: e.get("year", 0), reverse=True)
    
    # Write
    class D(yaml.SafeDumper):
        pass
    def rd(dumper, d):
        if not d:
            return dumper.represent_mapping("tag:yaml.org,2002:map", {})
        return dumper.represent_mapping("tag:yaml.org,2002:map", d.items())
    D.add_representer(dict, rd)
    
    with open(output, "w") as f:
        yaml.dump(data, f, Dumper=D, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
    
    # Summary
    from collections import Counter
    print(f"\n=== Summary ===")
    for key in ["publications", "preprints", "book_chapters", "presentations", "other_publications"]:
        print(f"{key}: {len(data[key])}")
    
    link_types = Counter()
    total_with_links = 0
    for section in ["publications", "preprints", "presentations", "other_publications"]:
        for entry in data[section]:
            has_link = False
            for lt, url in entry.get("links", {}).items():
                if url:
                    link_types[lt] += 1
                    has_link = True
            if has_link:
                total_with_links += 1
    
    print(f"\nEntries with at least one link: {total_with_links}")
    print("Link types:")
    for lt, count in link_types.most_common():
        print(f"  {lt}: {count}")
    print(f"\nWritten to {output}")


if __name__ == "__main__":
    main()
