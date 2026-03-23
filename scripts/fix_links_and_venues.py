#!/usr/bin/env python3
"""
Re-parse scholarly debate links and invited talk venues from original LaTeX.
Also fix preprints missing DOIs and conference presentation links.
"""

import re
import yaml


def clean_tex(s):
    """Remove LaTeX commands, keeping content."""
    if not s:
        return ""
    # Remove \textbf{\textit{...}} (author self-references)
    s = re.sub(r"\\textbf\{\\textit\{([^{}]*)\}\}", r"\1", s)
    # Remove \textbf{...}
    s = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", s)
    # Remove \emph{...} and \textit{...}
    s = re.sub(r"\\(?:emph|textit)\{([^{}]*)\}", r"\1", s)
    # Remove remaining simple commands
    for _ in range(3):
        s = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", s)
    # Remove \\ line breaks
    s = s.replace("\\\\", " ")
    # Clean up whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_links(text):
    """Extract \href{url}{label} pairs from LaTeX text."""
    links = {}
    for m in re.finditer(r"\\href\{([^}]+)\}\{([^}]+)\}", text):
        url = m.group(1).replace(r"\%", "%")
        label = clean_tex(m.group(2)).lower()
        if "pdf" in label or "full text" in label:
            links.setdefault("pdf", url)
        elif "diva" in label:
            links.setdefault("diva", url)
        elif "slide" in label or "osf.io" in label:
            links.setdefault("slides", url)
        elif "video" in label or "youtube" in label:
            links.setdefault("video", url)
        elif "program" in label or "kb.se" in label:
            links.setdefault("program", url)
        elif "web" in label or "blog" in label or "lakartidningen" in label or \
             "svd.se" in label or "curie" in label or "coalition" in label or \
             "humtank" in label or "deevybee" in label or "anpdm" in label or \
             "unt.se" in label or "kth.se" in label or "neuro.uu.se" in label or \
             "vof.se" in label or "skolaochsamhalle" in label or \
             "universitetslararen" in label or "stockholmuniversitypress" in label or \
             "tidningencurie" in label or "biblioteksbladet" in label or \
             "su.se" in label or "sverigesungaakademi" in label:
            links.setdefault("web", url)
        else:
            links.setdefault("web", url)
    # Also extract bare doi: references
    for m in re.finditer(r"\bdoi:\s*\\href\{([^}]+)\}\{([^}]+)\}", text):
        pass  # Already captured above
    for m in re.finditer(r"\bdoi:\s*(?:\\href\{[^}]+\}\{)?([0-9][^}\s,]+)", text):
        doi = m.group(1).strip().rstrip(".")
        links["doi"] = doi
    # Extract Zenodo DOI
    for m in re.finditer(r"Zenodo,\s*doi:\s*\\href\{[^}]+\}\{([^}]+)\}", text):
        links["doi"] = m.group(1).strip()
    return links


def normalize_title(t):
    if not t:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t.lower())).strip()


def main():
    # Read LaTeX source
    with open("CV_GN.tex", encoding="utf-8") as f:
        tex = f.read()
    
    # Read YAML
    with open("cv_data.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    # === 1. Fix Scholarly Debate links ===
    # Extract section from LaTeX
    m = re.search(r"\\subsection\*\{Scholarly debate\}(.*?)\\subsection\*\{", tex, re.DOTALL)
    if m:
        debate_tex = m.group(1)
        # Split into items
        items = re.split(r"\\item\s+", debate_tex)
        items = [i.strip() for i in items if i.strip() and not i.strip().startswith("\\begin")]
        
        print(f"=== SCHOLARLY DEBATE: {len(items)} items in LaTeX ===")
        
        # Match each LaTeX item to YAML entry by title
        matched = 0
        for item_tex in items:
            # Extract title: text inside \textbf{...} (not \textbf{\textit{...}})
            title_match = re.search(r"\\textbf\{(?!\\textit)([^}]+)\}", item_tex)
            if not title_match:
                continue
            title = clean_tex(title_match.group(1)).rstrip(".")
            nt = normalize_title(title)
            
            links = extract_links(item_tex)
            if not links:
                continue
            
            # Find matching YAML entry
            best_idx = None
            best_score = 0
            for i, entry in enumerate(data.get("scholarly_debate", [])):
                from difflib import SequenceMatcher
                s = SequenceMatcher(None, nt, normalize_title(entry.get("title", ""))).ratio()
                if s > best_score:
                    best_score = s
                    best_idx = i
            
            if best_score > 0.8 and best_idx is not None:
                entry = data["scholarly_debate"][best_idx]
                existing = entry.get("links", {})
                if not existing or not any(existing.values()):
                    entry["links"] = links
                    matched += 1
                    print(f"  + [{best_idx+1}] {title[:50]} → {list(links.keys())}")
        
        print(f"  Matched {matched} new link sets")
    
    # === 2. Fix Invited Talks: add venue ===
    m = re.search(r"\\subsection\*\{Invited talks\}(.*?)\\subsection\*\{", tex, re.DOTALL)
    if m:
        talks_tex = m.group(1)
        items = re.split(r"\\item\s+", talks_tex)
        items = [i.strip() for i in items if i.strip() and not i.strip().startswith("\\begin")]
        
        print(f"\n=== INVITED TALKS: {len(items)} items in LaTeX ===")
        
        matched = 0
        for item_tex in items:
            # Title is in \textbf{...}
            title_match = re.search(r"\\textbf\{([^}]+)\}", item_tex)
            if not title_match:
                continue
            raw_title = title_match.group(1)
            
            # Everything after the title closing brace is the venue/context
            after_title = item_tex[title_match.end():].strip()
            # Remove links from after_title to get venue
            venue_text = re.sub(r"\\href\{[^}]+\}\{[^}]+\}", "", after_title)
            venue_text = re.sub(r"(?:Program|Slides|Web|web|url|Video|DiVA|Abstracts):?\s*,?\s*", "", venue_text)
            venue_text = re.sub(r"%[^\n]*\n?", "", venue_text)  # Remove comments
            venue_text = clean_tex(venue_text).strip().rstrip(",").strip()
            
            # Extract links
            links = extract_links(item_tex)
            
            title = clean_tex(raw_title).rstrip(".")
            nt = normalize_title(title)
            
            # Find matching YAML entry
            from difflib import SequenceMatcher
            best_idx = None
            best_score = 0
            for i, entry in enumerate(data.get("invited_talks", [])):
                s = SequenceMatcher(None, nt, normalize_title(entry.get("title", ""))).ratio()
                if s > best_score:
                    best_score = s
                    best_idx = i
            
            if best_score > 0.8 and best_idx is not None:
                entry = data["invited_talks"][best_idx]
                if venue_text and not entry.get("venue"):
                    entry["venue"] = venue_text
                    matched += 1
                if links:
                    existing = entry.get("links", {})
                    if not existing or not any(existing.values()):
                        entry["links"] = links
        
        print(f"  Added venue to {matched} talks")
    
    # === 3. Fix Conference Presentations: add links ===
    m = re.search(r"\\subsection\*\{Conference presentations\}(.*?)\\subsection\*\{", tex, re.DOTALL)
    if m:
        conf_tex = m.group(1)
        items = re.split(r"\\item\s+", conf_tex)
        items = [i.strip() for i in items if i.strip() and not i.strip().startswith("\\begin")]
        
        print(f"\n=== CONFERENCE PRESENTATIONS: {len(items)} items in LaTeX ===")
        
        matched = 0
        for item_tex in items:
            links = extract_links(item_tex)
            if not links:
                continue
            
            title_match = re.search(r"\\textbf\{([^}]+)\}", item_tex)
            if not title_match:
                continue
            title = clean_tex(title_match.group(1)).rstrip(".")
            nt = normalize_title(title)
            
            from difflib import SequenceMatcher
            best_idx = None
            best_score = 0
            for i, entry in enumerate(data.get("conference_presentations", [])):
                s = SequenceMatcher(None, nt, normalize_title(entry.get("title", ""))).ratio()
                if s > best_score:
                    best_score = s
                    best_idx = i
            
            if best_score > 0.8 and best_idx is not None:
                entry = data["conference_presentations"][best_idx]
                existing = entry.get("links", {})
                if not existing or not any(existing.values()):
                    entry["links"] = links
                    matched += 1
                    print(f"  + [{best_idx+1}] {title[:50]} → {list(links.keys())}")
        
        print(f"  Matched {matched} link sets")
    
    # === 4. Remove preprint [26] (PSA Bylaws) ===
    preprints = data.get("preprints", [])
    for i, pp in enumerate(preprints):
        if "Psychological Science Accelerator Funding" in pp.get("title", ""):
            print(f"\n=== Removing preprint [{i+1}]: {pp['title'][:50]} ===")
            preprints.pop(i)
            break
    
    # === 5. Fix preprints missing DOIs ===
    print(f"\n=== PREPRINTS WITHOUT DOI ===")
    for i, pp in enumerate(preprints):
        if not pp.get("doi"):
            print(f"  [{i+1}] {pp.get('title','')[:60]}")
    
    # Save
    with open("cv_data.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=120)
    print("\nWritten to cv_data.yaml")


if __name__ == "__main__":
    main()
