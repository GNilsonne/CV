#!/usr/bin/env python3
"""
Parse CV_GN.tex into a comprehensive cv_data.yaml.
Extracts ALL sections from the LaTeX source.
"""

import re
import yaml
import sys


def read_tex(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_section(tex, heading):
    """Extract text between a subsection/section heading and the next one."""
    # Try subsection* first, then section*
    for cmd in [r"\\subsection\*", r"\\section\*"]:
        pattern = cmd + r"\{" + re.escape(heading) + r"\}(.*?)(?=\\(?:sub)?section\*\{|\\end\{document\})"
        m = re.search(pattern, tex, re.DOTALL)
        if m:
            return m.group(1)
    return ""


def clean_tex(s):
    """Remove common LaTeX markup from a string."""
    if not s:
        return ""
    s = s.strip()
    # Remove comments first (but not % in URLs)
    s = re.sub(r"(?<!\\)%[^\n]*", "", s)
    # Remove {\bf ...} pattern (old-style bold)
    s = re.sub(r"\{\\bf\s+([^}]*)\}", r"\1", s)
    # Remove nested \textbf{\textit{...}}
    s = re.sub(r"\\textbf\{\\textit\{([^}]*)\}\}", r"\1", s)
    # Remove \textbf{...}, \textit{...}, \emph{...}
    # Handle nested braces up to one level
    for cmd in ["textbf", "textit", "emph", "bf"]:
        s = re.sub(r"\\%s\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}" % cmd, r"\1", s)
    # Remove \href{url}{text} -> text
    s = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", s)
    # Remove \hyperref[...]{text} -> text
    s = re.sub(r"\\hyperref\[[^\]]*\]\{([^}]*)\}", r"\1", s)
    # Remove \label{...}
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    # Remove remaining simple commands
    s = s.replace(r"\&", "&")
    s = s.replace(r"\%", "%")
    s = s.replace(r"\_", "_")
    s = s.replace(r"\#", "#")
    s = s.replace(r"\$", "$")
    s = s.replace(r"\textasciitilde{}", "~")
    s = s.replace(r"\textasciicircum{}", "^")
    s = s.replace("\\\\", " ")
    s = s.replace(r"\newline", " ")
    # Remove \begin{...} and \end{...}
    s = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?", "", s)
    # Remove bioRxiv special: bioR$\chi$iv -> bioRxiv
    s = re.sub(r"bioR\$\\chi\$iv", "bioRxiv", s)
    s = re.sub(r"MedR\$\\chi\$iv", "MedRxiv", s)
    # Remove leftover LaTeX commands like \item
    s = re.sub(r"\\item\s*", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Final cleanup: remove any remaining \command{...} patterns
    # Do multiple passes to handle nesting
    for _ in range(3):
        s = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", s)
    # Remove any remaining bare \commands (no braces)
    s = re.sub(r"\\(?:newpage|noindent|vspace|hspace)\b\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_href(s):
    """Extract all \href{url}{text} from a string, return list of (url, text)."""
    return re.findall(r"\\href\{([^}]*)\}\{([^}]*)\}", s)


def extract_first_href_url(s):
    """Extract first href URL from string."""
    m = re.search(r"\\href\{([^}]*)\}", s)
    return m.group(1) if m else ""


def parse_itemize_items(text):
    """Parse \item entries from an itemize block."""
    items = re.split(r"\\item\s+", text)
    return [clean_tex(it) for it in items if it.strip() and not it.strip().startswith("\\begin")]


def parse_enumerate_entries(text):
    """Split enumerate into individual \\item blocks."""
    # Handle both \item{...} (no space) and \item ... (with space)
    items = re.split(r"\\item\s*", text)
    return [it.strip() for it in items if it.strip()]


def parse_contact(tex):
    """Parse the contact/meta section."""
    meta = {
        "name": "Gustav Nilsonne",
        "orcid": "0000-0001-5273-0150",
        "affiliation": "Karolinska Institutet",
        "email": "gustav.nilsonne@ki.se",
    }
    # Extract additional profile links
    profiles = {}
    hrefs = extract_href(tex[:3000])
    for url, text in hrefs:
        if "github.com" in url:
            profiles["github"] = url
        elif "scholar.google" in url:
            profiles["google_scholar"] = url
        elif "osf.io" in url and "nolrw" in url:
            profiles["osf"] = url
        elif "nilsonne.net" in url:
            profiles["website"] = url
        elif "ki.se/en/people" in url:
            profiles["ki_profile"] = url
        elif "su.se/profiles" in url:
            profiles["su_profile"] = url
        elif "metrics.stanford" in url:
            profiles["stanford_profile"] = url
    meta["profiles"] = profiles
    return meta


def parse_degrees(tex):
    """Parse degrees section."""
    section = extract_section(tex, "Degrees and qualifications")
    if not section:
        return []
    degrees = []
    items = re.split(r"\\item\s+", section)
    for item in items:
        item = item.strip()
        if not item or item.startswith("\\begin") or item.startswith("\\end"):
            continue
        # Clean out comments
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        if not text or len(text) < 5:
            continue
        link = extract_first_href_url(item)
        d = {"description": text}
        if link:
            d["link"] = link
        # Try to extract year
        m = re.search(r"(\d{4})", text)
        if m:
            d["year"] = int(m.group(1))
        degrees.append(d)
    return degrees


def parse_employment(tex):
    """Parse employment section."""
    section = extract_section(tex, "Employment and appointments")
    if not section:
        return []
    items = re.split(r"\\item\s+", section)
    positions = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        if text:
            positions.append({"description": text})
    return positions


def parse_simple_list_section(tex, heading):
    """Parse a section that's just a list of items."""
    section = extract_section(tex, heading)
    if not section:
        return []
    items = re.split(r"\\item\s+", section)
    result = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        item = re.sub(r"%[^\n]*", "", item)
        hrefs = extract_href(item)
        text = clean_tex(item)
        if not text:
            continue
        entry = {"description": text}
        links = {}
        for url, label in hrefs:
            links[label.strip() if label.strip() else "link"] = url
        if links:
            entry["links"] = links
        result.append(entry)
    return result


def parse_nested_list_section(tex, heading):
    """Parse a section with nested itemize lists (e.g., reviewer lists).
    
    Returns list of entries where each entry can have 'subitems' list.
    """
    section = extract_section(tex, heading)
    if not section:
        return []
    
    result = []
    # Split by top-level \item, but track nested \begin{itemize}/\end{itemize}
    # First, let's split smarter: find top-level items by tracking nesting depth
    lines = section.split("\n")
    
    current_item = []
    in_item = False
    
    items_raw = []
    depth = 0
    buf = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("\\begin{itemize}") or stripped.startswith("\\begin{enumerate}"):
            depth += 1
            if depth == 1:
                # This is the outermost list, skip the \begin
                continue
            buf.append(line)
        elif stripped.startswith("\\end{itemize}") or stripped.startswith("\\end{enumerate}"):
            depth -= 1
            if depth == 0:
                # End of outermost list
                continue
            buf.append(line)
        elif stripped.startswith("\\item") and depth == 1:
            # New top-level item
            if buf:
                items_raw.append("\n".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        items_raw.append("\n".join(buf))
    
    for raw in items_raw:
        # Check if this item has a nested \begin{itemize}
        if "\\begin{itemize}" in raw or "\\begin{enumerate}" in raw:
            # Split into parent text and sub-items
            parent_match = re.match(r"\\item\s+(.*?)\\begin\{(?:itemize|enumerate)\}", raw, re.DOTALL)
            if parent_match:
                parent_text = parent_match.group(1)
            else:
                parent_text = raw.split("\\begin{")[0]
                parent_text = re.sub(r"^\\item\s*", "", parent_text)
            
            parent_clean = clean_tex(parent_text)
            hrefs = extract_href(parent_text)
            
            # Extract sub-items
            subitems = []
            sub_raw = raw[raw.index("\\begin{"):]
            sub_entries = re.split(r"\\item\s+", sub_raw)
            for sub in sub_entries:
                sub = sub.strip()
                if not sub or sub.startswith("\\begin") or sub.startswith("\\end"):
                    continue
                # Remove \end{itemize} and everything after (including footnotes)
                sub = re.sub(r"\\end\{[^}]*\}.*", "", sub, flags=re.DOTALL)
                sub_text = clean_tex(sub)
                if sub_text:
                    subitems.append(sub_text)
            
            # Check for text after \end{itemize} (e.g., the Web of Science note)
            end_match = re.search(r"\\end\{(?:itemize|enumerate)\}(.*?)$", raw, re.DOTALL)
            footnote = ""
            if end_match:
                fn_text = clean_tex(end_match.group(1))
                fn_hrefs = extract_href(end_match.group(1))
                if fn_text:
                    footnote = fn_text
            
            entry = {"description": parent_clean}
            if subitems:
                entry["subitems"] = subitems
            if footnote:
                entry["footnote"] = footnote
            links = {}
            for url, label in hrefs:
                links[label.strip() if label.strip() else "link"] = url
            if links:
                entry["links"] = links
            if parent_clean or subitems:
                result.append(entry)
        else:
            # Simple item, no nesting
            raw = re.sub(r"^\\item\s*", "", raw)
            raw = re.sub(r"%[^\n]*", "", raw)
            hrefs = extract_href(raw)
            text = clean_tex(raw)
            if not text:
                continue
            entry = {"description": text}
            links = {}
            for url, label in hrefs:
                links[label.strip() if label.strip() else "link"] = url
            if links:
                entry["links"] = links
            result.append(entry)
    
    return result


def parse_publication(raw):
    """Parse a single publication entry from raw LaTeX."""
    entry = {}
    
    # The LaTeX pattern is typically:
    # Authors. \textbf{Title.} \emph{Journal} Year... doi:...
    # Where author names in bold/italic indicate "Nilsonne G" as self-reference
    
    # Extract title - look for \textbf{ that contains actual title text
    # Titles are in \textbf{...} but NOT the ones that are just author names like \textbf{\textit{Nilsonne G}}
    title_candidates = re.findall(r"\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}", raw)
    title = ""
    for tc in title_candidates:
        # Skip author self-references: \textit{...} inside \textbf{...}
        if re.match(r"^\s*\\textit\{", tc):
            continue
        cleaned = clean_tex(tc)
        # Skip if it's just a name or very short
        if cleaned and len(cleaned) > 20 and not re.match(r"^[A-Z][a-z]+ [A-Z]$", cleaned):
            title = cleaned
            break
    if not title and title_candidates:
        # Fall back to longest candidate that isn't an author reference
        non_author = [tc for tc in title_candidates if not re.match(r"^\s*\\textit\{", tc)]
        if non_author:
            title = clean_tex(max(non_author, key=lambda x: len(x)))
    entry["title"] = title.rstrip(".")
    
    # Extract journal - \emph{Journal Name} or \textit{Journal Name}
    # But skip author self-references and known non-journals
    journal_candidates = re.findall(r"\\(?:emph|textit)\{([^}]+)\}", raw)
    journal = ""
    known_not_journal = {"in vitro", "Docent", "co-supervisor", "amanuens", "studierektor",
                         "Kårfullmäktige", "PsyArXiv", "bioRxiv", "MedRxiv", "OSF Preprints",
                         "figshare", "Karolinska Open Archive", "SocArXiv", "MetaArXiv",
                         "arXiv", "KI Open Archive"}
    for jc in journal_candidates:
        jc_clean = clean_tex(jc)
        if (jc_clean and len(jc_clean) > 3 and 
            jc_clean not in known_not_journal and
            not jc_clean.startswith("bioR") and
            not jc_clean.startswith("MedR") and
            "preprint" not in jc_clean.lower() and
            # Skip person names (pattern: "Surname X" or "Surname XY" — single initial)
            not re.match(r"^[A-ZÅÄÖÜ][a-zåäöü]+\s+[A-ZÅÄÖÜ]{1,3}$", jc_clean) and
            # Skip if it's inside \textbf{\textit{...}} (author self-reference)
            "\\textbf{\\textit{%s}" % jc not in raw):
            journal = jc_clean
            break
    entry["journal"] = journal
    
    # Extract DOI - various patterns
    doi_match = re.search(r"doi:\s*\\href\{[^}]*\}\{([^}]+)\}", raw)
    if not doi_match:
        doi_match = re.search(r"doi:\s*(?:\\href\{)?(?:https?://(?:dx\.)?doi\.org/)?([^\s},\\]+)", raw)
    if doi_match:
        doi = doi_match.group(1).strip().rstrip(".")
        # Clean doi: prefix if accidentally included
        doi = re.sub(r"^doi:", "", doi)
        # Clean LaTeX escapes from DOI (e.g., \_ -> _)
        doi = doi.replace(r"\_", "_")
        doi = doi.replace(r"\&", "&")
        entry["doi"] = doi
    
    # Extract year
    year_match = re.search(r"(?:19|20)\d{2}", raw)
    if year_match:
        entry["year"] = int(year_match.group(0))
    
    # Extract authors
    # The pattern: "Author1, \textbf{\textit{Nilsonne G}}, Author2. \textbf{Title...}"
    # We need to find the REAL title \textbf{} (not the author self-reference ones)
    # Real title \textbf{} contains long text, author ones contain just \textit{Name}
    
    # Find position of the real title \textbf
    real_title_pos = -1
    for m in re.finditer(r"\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}", raw):
        content = m.group(1)
        # Skip if it contains \textit{ (author self-reference or group name)
        if re.match(r"^\s*\\textit\{", content):
            continue
        cleaned = clean_tex(content)
        if len(cleaned) > 20:  # Real titles are longer
            real_title_pos = m.start()
            break
    
    if real_title_pos > 0:
        authors_raw = raw[:real_title_pos]
        # Clean the author string
        authors = clean_tex(authors_raw).rstrip(".").strip()
        # Remove trailing year in parens
        authors = re.sub(r"\s*\(\d{4}\)\s*$", "", authors).strip().rstrip(".")
        if authors and len(authors) > 2:
            entry["authors"] = authors
    
    # Extract all links
    links = {}
    href_pairs = re.findall(r"\\href\{([^}]*)\}\{([^}]*)\}", raw)
    
    for url, text in href_pairs:
        text_lower = text.lower().strip()
        url_lower = url.lower()
        
        # Classify by context around the href
        context_start = max(0, raw.find(url) - 80)
        context = raw[context_start:raw.find(url) + len(url) + 20].lower()
        
        if any(x in context for x in ["preprint", "postprint", "preprint:", "authors'"]):
            if "preprint" not in links:
                links["preprint"] = url
        elif any(x in context for x in ["associated data and code", "data and code"]):
            links["data"] = url
            links["code"] = url
        elif any(x in context for x in ["associated data", "associated data:"]):
            if "data" not in links:
                links["data"] = url
        elif "preregistration" in context or "clinicaltrials" in url_lower:
            if "preregistration" not in links:
                links["preregistration"] = url
        elif "openneuro" in url_lower:
            if "data" not in links:
                links["data"] = url
        elif "zenodo" in url_lower and "data" not in links:
            links["data"] = url
        elif "dryad" in url_lower:
            links["data"] = url
        elif "github" in url_lower and "code" not in links and "doi.org" not in url:
            links["code"] = url
        elif "osf.io/ezcuj" in url_lower or "osf.io/by2kc" in url_lower:
            links["data"] = url
        # Skip DOI links (they're already in the doi field)
    
    entry["links"] = links
    return entry


def parse_publications_section(tex, heading):
    """Parse a publications enumerate section."""
    section = extract_section(tex, heading)
    if not section:
        return []
    
    entries = parse_enumerate_entries(section)
    pubs = []
    for raw in entries:
        pub = parse_publication(raw)
        if pub.get("title"):
            pubs.append(pub)
    return pubs


def parse_presentation(raw):
    """Parse a single presentation entry."""
    entry = {}
    
    # Extract title - skip \textbf{\textit{Name}} (author self-references)
    # and find the real title \textbf{...} which contains longer text
    title = ""
    for m in re.finditer(r"\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}", raw):
        content = m.group(1)
        # Skip author self-references like \textit{Nilsonne G}
        if re.match(r"^\s*\\textit\{[^}]+\}\s*$", content):
            continue
        cleaned = clean_tex(content)
        if len(cleaned) > 5:
            title = cleaned
            break
    
    # Try {\bf ...} pattern if no \textbf found
    if not title:
        bf_match = re.search(r"\{\\bf\s+([^}]+)\}", raw)
        if bf_match:
            title = clean_tex(bf_match.group(1))
    
    if not title:
        title = clean_tex(raw[:200])
    
    entry["title"] = title
    
    # Extract authors - everything before the real title \textbf{...}
    # Find position of the real title in raw
    real_title_pos = -1
    for m in re.finditer(r"\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}", raw):
        content = m.group(1)
        if re.match(r"^\s*\\textit\{[^}]+\}\s*$", content):
            continue
        cleaned = clean_tex(content)
        if len(cleaned) > 5:
            real_title_pos = m.start()
            break
    if not real_title_pos or real_title_pos < 0:
        # Try {\bf ...} position
        bf_m = re.search(r"\{\\bf\s+", raw)
        if bf_m:
            real_title_pos = bf_m.start()
    
    if real_title_pos and real_title_pos > 5:
        authors_raw = raw[:real_title_pos]
        authors = clean_tex(authors_raw).rstrip(".").strip()
        authors = re.sub(r"\s*\(\d{4}\)\s*$", "", authors).strip().rstrip(".")
        if authors and len(authors) > 2:
            entry["authors"] = authors

    # Extract year, strip URLs first to avoid matching digits in URLs
    raw_no_urls = re.sub(r"\\href\{[^}]*\}", "", raw)
    raw_no_urls = re.sub(r"https?://[^\s]+", "", raw_no_urls)
    year_match = re.search(r"((?:19|20)\d{2})", raw_no_urls)
    if year_match:
        entry["year"] = int(year_match.group(1))
    
    # Extract links
    links = {}
    href_pairs = extract_href(raw)
    for url, text in href_pairs:
        text_lower = text.lower().strip()
        if "slide" in text_lower or "osf" in text_lower:
            links["slides"] = url
        elif "video" in text_lower or "youtube" in text_lower or "vimeo" in text_lower:
            links["video"] = url
        elif "poster" in text_lower:
            links["poster"] = url
        elif "web" in text_lower or "program" in text_lower:
            links["web"] = url
    
    if links:
        entry["links"] = links
    else:
        entry["links"] = {}
    
    return entry


def parse_presentations_section(tex, heading):
    """Parse a presentations enumerate section."""
    section = extract_section(tex, heading)
    if not section:
        return []
    entries = parse_enumerate_entries(section)
    result = []
    for raw in entries:
        pres = parse_presentation(raw)
        if pres.get("title"):
            result.append(pres)
    return result


def parse_grants(tex):
    """Parse research grants section."""
    section = extract_section(tex, "Research grants")
    if not section:
        return []
    items = re.split(r"\\item\s+", section)
    grants = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        link = extract_first_href_url(item)
        if text:
            g = {"description": text}
            if link:
                g["link"] = link
            grants.append(g)
    return grants


def parse_teaching(tex):
    """Parse teaching section into structured data."""
    section = extract_section(tex, "Teaching")
    if not section:
        return []
    # This is complex with nested itemize, just store as list of descriptions
    items = re.split(r"\\item\s+", section)
    teaching = []
    for item in items:
        item = item.strip()
        if not item or item.startswith("\\begin"):
            continue
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        if text and len(text) > 5:
            hrefs = extract_href(item)
            entry = {"description": text}
            links = {}
            for url, label in hrefs:
                links[clean_tex(label) if label else "link"] = url
            if links:
                entry["links"] = links
            teaching.append(entry)
    return teaching


def parse_phd_supervision(tex):
    """Parse PhD supervision section."""
    section = extract_section(tex, "Supervision of PhD students")
    if not section:
        return []
    items = re.split(r"\\item\s+", section)
    students = []
    for item in items:
        item = item.strip()
        if not item or item.startswith("\\begin"):
            continue
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        link = extract_first_href_url(item)
        if text:
            entry = {"description": text}
            if link:
                entry["link"] = link
            students.append(entry)
    return students


def parse_awards(tex):
    """Parse awards section."""
    section = extract_section(tex, "Awards")
    if not section:
        return []
    items = re.split(r"\\item\s+", section)
    awards = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        item = re.sub(r"%[^\n]*", "", item)
        text = clean_tex(item)
        link = extract_first_href_url(item)
        if text:
            a = {"description": text}
            if link:
                a["link"] = link
            awards.append(a)
    return awards


def parse_peer_reviews(tex):
    """Parse open peer review section."""
    section = extract_section(tex, "Open peer-review reports")
    if not section:
        return []
    entries = parse_enumerate_entries(section)
    reviews = []
    for raw in entries:
        # Strip outer braces from \item{...} pattern
        raw = raw.strip()
        if raw.startswith("{"):
            # Find matching closing brace
            depth = 0
            end = -1
            for idx, ch in enumerate(raw):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx
                        break
            if end > 0:
                raw = raw[1:end]
        # Remove any trailing \end{...} and leftovers
        raw = re.sub(r"\\end\{[^}]*\}.*$", "", raw, flags=re.DOTALL)
        text = clean_tex(raw)
        if not text:
            continue
        hrefs = extract_href(raw)
        entry = {"description": text}
        links = {}
        for url, label in hrefs:
            links[clean_tex(label)] = url
        if links:
            entry["links"] = links
        reviews.append(entry)
    return reviews


def parse_scholarly_debate(tex):
    """Parse scholarly debate section."""
    section = extract_section(tex, "Scholarly debate")
    if not section:
        return []
    entries = parse_enumerate_entries(section)
    items = []
    for raw in entries:
        pub = parse_publication(raw)
        if not pub.get("title"):
            fallback = clean_tex(raw[:200])
            if not fallback:
                continue
            pub["title"] = fallback
        items.append(pub)
    return items


def parse_popular_science_writings(tex):
    """Parse popular science writings section."""
    section = extract_section(tex, "Popular science writings and general debate")
    if not section:
        return []
    entries = parse_enumerate_entries(section)
    items = []
    for raw in entries:
        entry = {}
        # Try \textbf{...} first, then {\bf ...}
        title_match = re.search(r"\\textbf\{([^}]+)\}", raw)
        if not title_match:
            title_match = re.search(r"\{\\bf\s+([^}]+)\}", raw)
        if title_match:
            entry["title"] = clean_tex(title_match.group(1))
        else:
            entry["title"] = clean_tex(raw[:150])
        
        # Extract year, but strip URLs first to avoid matching digits in URLs
        raw_no_urls = re.sub(r"\\href\{[^}]*\}", "", raw)
        raw_no_urls = re.sub(r"https?://[^\s]+", "", raw_no_urls)
        year_match = re.search(r"((?:19|20)\d{2})", raw_no_urls)
        if year_match:
            entry["year"] = int(year_match.group(1))
        
        links = {}
        hrefs = extract_href(raw)
        for url, text in hrefs:
            text_lower = text.lower()
            if "video" in text_lower or "youtube" in text_lower:
                links["video"] = url
            else:
                links["web"] = url
        entry["links"] = links
        if entry.get("title"):
            items.append(entry)
    return items


def main():
    tex = read_tex("/tmp/CV/CV_GN.tex")
    
    data = {}
    
    # Meta
    data["meta"] = parse_contact(tex)
    
    # Degrees
    data["degrees"] = parse_degrees(tex)
    
    # Employment
    data["employment"] = parse_employment(tex)
    
    # PhD supervision
    data["phd_supervision"] = parse_phd_supervision(tex)
    
    # Grants
    data["grants"] = parse_grants(tex)
    
    # Teaching
    data["teaching"] = parse_teaching(tex)
    
    # Awards
    data["awards"] = parse_awards(tex)
    
    # PhD committee
    data["phd_committee"] = parse_simple_list_section(tex, "PhD thesis committee member/faculty opponent")
    
    # Academic commissions
    data["academic_commissions"] = parse_nested_list_section(tex, "Academic commissions of trust")
    
    # Other commissions
    data["other_commissions"] = parse_simple_list_section(tex, "Other commissions of trust")
    
    # Publications
    data["publications"] = parse_publications_section(tex, "Publications in academic journals")
    
    # Preprints
    data["preprints"] = parse_publications_section(tex, "Preprints")
    
    # Books / Book chapters
    data["books"] = parse_publications_section(tex, "Books")
    
    # Open peer reviews
    data["open_peer_reviews"] = parse_peer_reviews(tex)
    
    # Reports
    data["reports"] = parse_publications_section(tex, "Reports")
    
    # Study materials
    data["study_materials"] = parse_publications_section(tex, "Study Materials")
    
    # Digital research objects
    data["digital_research_objects"] = parse_publications_section(tex, "Other digital research objects")
    
    # Scholarly debate
    data["scholarly_debate"] = parse_scholarly_debate(tex)
    
    # Invited talks
    data["invited_talks"] = parse_presentations_section(tex, "Invited talks")
    
    # Conference presentations
    data["conference_presentations"] = parse_presentations_section(tex, "Conference presentations")
    
    # Conference abstracts
    data["conference_abstracts"] = parse_presentations_section(tex, "Other indexed conference abstracts")
    
    # Popular science talks
    data["popular_science_talks"] = parse_presentations_section(tex, "Popular science talks")
    
    # Popular science writings
    data["popular_science_writings"] = parse_popular_science_writings(tex)
    
    # Blogging
    data["blogging"] = parse_simple_list_section(tex, "Blogging")
    
    # Print summary
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} entries")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} keys")
    
    # Write YAML
    out_path = "/tmp/CV/cv_data.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
    
    print(f"\nWritten to {out_path}")
    
    # Verify
    with open(out_path, encoding="utf-8") as f:
        verify = yaml.safe_load(f)
    print("YAML verification passed ✓")


if __name__ == "__main__":
    main()
