#!/usr/bin/env python3
"""
Add missing publications and preprints from RIMS, link preprints to papers,
and remove duplicate preprints.
"""

import csv
import re
import yaml
from difflib import SequenceMatcher


def normalize_doi(doi):
    if not doi: return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = doi.replace(r"\_", "_").replace(r"\&", "&")
    return doi


def normalize_title(t):
    if not t: return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t.lower())).strip()


def title_sim(t1, t2):
    n1, n2 = normalize_title(t1), normalize_title(t2)
    if not n1 or not n2: return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def rims_to_pub(row):
    """Convert a RIMS row to a publication dict."""
    pub = {}
    title = row.get("Title OR Title (English)", "").strip().rstrip(".")
    # Remove [...] brackets (Swedish translation indicator)
    title = re.sub(r"^\[(.+)\]$", r"\1", title)
    pub["title"] = title
    
    authors = row.get("Authors OR Creators / Principal investigators OR Author", "").strip()
    if authors:
        pub["authors"] = authors
    
    journal = row.get("Canonical journal title", "").strip()
    if not journal:
        journal = row.get("Journal OR Published proceedings", "").strip()
    if journal:
        pub["journal"] = journal
    
    doi = row.get("DOI", "").strip()
    if doi:
        pub["doi"] = doi
    
    # Year from publication date or reporting date
    pub_date = row.get("Publication date", "").strip()
    rep_date = row.get("Reporting date 1", "").strip()
    if pub_date and len(pub_date) >= 4:
        year_str = pub_date[:4]
    elif rep_date and len(rep_date) >= 4:
        year_str = rep_date[-4:]
    else:
        year_str = ""
    if year_str.isdigit():
        pub["year"] = int(year_str)
    
    vol = row.get("Volume", "").strip()
    if vol: pub["volume"] = vol
    
    issue = row.get("Issue", "").strip()
    if issue: pub["issue"] = issue
    
    start = row.get("Pagination (start page)", "").strip()
    end = row.get("Pagination (end page)", "").strip()
    if start:
        pub["pages"] = f"{start}-{end}" if end else start
    
    article_num = row.get("Article number OR Chapter number", "").strip()
    if article_num and not start:
        pub["article_number"] = article_num
    
    pub["links"] = {}
    pub["rims_id"] = row.get("ID", "").strip()
    
    return pub


def main():
    # Load YAML
    with open("cv_data.yaml", encoding="utf-8") as f:
        content = f.read()
    data = yaml.load(content, Loader=yaml.SafeLoader)
    
    # Collect all known DOIs and titles across all sections
    known_dois = set()
    known_titles = set()
    for section in ["publications", "preprints", "scholarly_debate", 
                     "popular_science_writings", "reports"]:
        for p in data.get(section, []):
            doi = normalize_doi(p.get("doi", ""))
            if doi: known_dois.add(doi)
            t = normalize_title(p.get("title", ""))
            if t: known_titles.add(t)
    
    # Collect preprint DOIs linked from publications
    linked_preprint_dois = set()
    for pub in data["publications"]:
        url = pub.get("links", {}).get("preprint", "").lower()
        if url:
            m = re.search(r"doi\.org/(.+)", url)
            if m: linked_preprint_dois.add(m.group(1))
            linked_preprint_dois.add(url)
    
    # Load RIMS, deduplicate by DOI+title
    rims_articles = {}  # key -> row
    rims_preprints = {}
    with open("templates/csv20260323.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pub_type = row.get("Publication type", "")
            doi = normalize_doi(row.get("DOI", ""))
            title = row.get("Title OR Title (English)", "").strip()
            
            if not title or title in ("[Not Available].", ""):
                continue
            # Skip bracket-wrapped duplicates (Swedish translations listed separately)
            if title.startswith("[") and title.endswith("]."):
                # Check if the non-bracket version exists
                inner = title[1:-2]
                nt_inner = normalize_title(inner)
                # Keep it but deduplicate later
            
            key = doi if doi else normalize_title(title)
            if not key: continue
            
            if pub_type == "Journal article":
                if key not in rims_articles:
                    rims_articles[key] = row
            elif pub_type == "Preprint":
                if key not in rims_preprints:
                    rims_preprints[key] = row
    
    # === 1. Find new journal articles ===
    new_articles = []
    for key, row in rims_articles.items():
        doi = normalize_doi(row.get("DOI", ""))
        title = row.get("Title OR Title (English)", "").strip()
        nt = normalize_title(title)
        
        if doi and doi in known_dois: continue
        if nt in known_titles: continue
        
        # Fuzzy check
        best = 0
        for section in ["publications", "preprints", "scholarly_debate",
                        "popular_science_writings", "reports"]:
            for p in data.get(section, []):
                s = title_sim(title, p.get("title", ""))
                best = max(best, s)
        if best > 0.8: continue
        
        new_articles.append(rims_to_pub(row))
    
    # === 2. Find new preprints ===
    new_preprints = []
    preprints_to_link = []  # (preprint_doi, pub_index)
    
    for key, row in rims_preprints.items():
        doi = normalize_doi(row.get("DOI", ""))
        title = row.get("Title OR Title (English)", "").strip()
        nt = normalize_title(title)
        
        if doi and doi in known_dois: continue
        if doi and doi in linked_preprint_dois: continue
        if nt in known_titles: continue
        
        # Check if this preprint matches a publication (existing or newly added)
        best_score = 0
        best_pub_idx = None
        for i, pub in enumerate(data["publications"]):
            s = title_sim(title, pub.get("title", ""))
            if s > best_score:
                best_score = s
                best_pub_idx = i
        # Also check newly added articles
        for i, pub in enumerate(new_articles):
            s = title_sim(title, pub.get("title", ""))
            if s > best_score:
                best_score = s
                best_pub_idx = -(i + 1)  # negative = new article
        
        if best_score > 0.8 and best_pub_idx is not None:
            # Link to publication instead of adding as standalone
            preprints_to_link.append((doi, best_pub_idx, best_score, title[:60]))
        else:
            # Standalone preprint
            pp = rims_to_pub(row)
            new_preprints.append(pp)
    
    # === 3. Find YAML preprints duplicated with publications ===
    preprints_to_remove = []
    for i, pp in enumerate(data.get("preprints", [])):
        pp_doi = normalize_doi(pp.get("doi", ""))
        pp_title = pp.get("title", "")
        
        for j, pub in enumerate(data["publications"]):
            # Check DOI match via preprint link
            pub_pp_url = pub.get("links", {}).get("preprint", "").lower()
            if pp_doi and pp_doi in pub_pp_url:
                preprints_to_remove.append((i, pp_title[:60], j+1))
                break
            # Check title similarity
            s = title_sim(pp_title, pub.get("title", ""))
            if s > 0.85:
                preprints_to_remove.append((i, pp_title[:60], j+1))
                break
    
    # === APPLY CHANGES ===
    
    # Add new articles
    print(f"\n=== Adding {len(new_articles)} new journal articles ===")
    for pub in sorted(new_articles, key=lambda p: p.get("year", 0)):
        print(f"  + [{pub.get('year','')}] {pub.get('title','')[:70]}")
        data["publications"].append(pub)
        known_dois.add(normalize_doi(pub.get("doi", "")))
    
    # Sort publications by year (descending, newest first) — wait, original order was oldest first
    # Keep original order: sort by year ascending
    
    # Link preprints to publications
    print(f"\n=== Linking {len(preprints_to_link)} preprints to publications ===")
    for pp_doi, pub_idx, score, pp_title in preprints_to_link:
        if pub_idx >= 0:
            pub = data["publications"][pub_idx]
        else:
            pub = new_articles[-(pub_idx + 1)]
        
        existing = pub.get("links", {}).get("preprint", "")
        if not existing and pp_doi:
            if "links" not in pub:
                pub["links"] = {}
            pub["links"]["preprint"] = f"https://doi.org/{pp_doi}"
            print(f"  → [{pub.get('year','')}] {pub.get('title','')[:50]} ← {pp_doi}")
    
    # Add new standalone preprints
    print(f"\n=== Adding {len(new_preprints)} new standalone preprints ===")
    for pp in new_preprints:
        print(f"  + [{pp.get('year','')}] {pp.get('title','')[:70]}")
        data.setdefault("preprints", []).append(pp)
    
    # Remove duplicate preprints
    print(f"\n=== Removing {len(preprints_to_remove)} duplicate preprints ===")
    indices_to_remove = set()
    for pp_idx, pp_title, pub_num in preprints_to_remove:
        print(f"  - Preprint [{pp_idx}]: {pp_title}")
        print(f"    (already linked to Pub [{pub_num}])")
        indices_to_remove.add(pp_idx)
    
    if indices_to_remove:
        data["preprints"] = [pp for i, pp in enumerate(data["preprints"]) 
                            if i not in indices_to_remove]
    
    # Save
    with open("cv_data.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=120)
    
    print(f"\n=== Summary ===")
    print(f"New articles added: {len(new_articles)}")
    print(f"Preprints linked to publications: {len(preprints_to_link)}")
    print(f"New standalone preprints: {len(new_preprints)}")
    print(f"Duplicate preprints removed: {len(preprints_to_remove)}")
    print(f"Total publications: {len(data['publications'])}")
    print(f"Total preprints: {len(data.get('preprints', []))}")
    print(f"\nWritten to cv_data.yaml")


if __name__ == "__main__":
    main()
