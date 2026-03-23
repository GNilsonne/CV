#!/usr/bin/env python3
"""
Enrich cv_data.yaml with metadata from KI RIMS CSV export.

Matches publications by DOI and fills in:
- volume, issue, pages
- pmid (PubMed ID)
- issn, eissn
- publication_date (exact date)
- canonical_journal (standardized journal name)
- keywords
- abstract
- open_access_status
- acceptance_date

Also matches RIMS preprints to existing publication entries via
title similarity, enriching the publication's links.preprint field.

Usage:
    python3 scripts/enrich_from_rims.py [--rims templates/csv20260323.csv] [--data cv_data.yaml]
"""

import argparse
import csv
import re
import yaml
from difflib import SequenceMatcher


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=120)


def load_rims(path):
    """Load RIMS CSV into list of dicts."""
    records = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records


def normalize_doi(doi):
    """Normalize a DOI for matching."""
    if not doi:
        return ""
    doi = doi.strip().lower()
    # Remove common prefixes
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    # Remove LaTeX escapes
    doi = doi.replace(r"\_", "_")
    doi = doi.replace(r"\&", "&")
    return doi


def normalize_title(title):
    """Normalize a title for fuzzy matching."""
    if not title:
        return ""
    t = title.lower()
    # Remove punctuation
    t = re.sub(r"[^\w\s]", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_similarity(t1, t2):
    """Calculate similarity between two titles."""
    n1 = normalize_title(t1)
    n2 = normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def enrich_publication(pub, rims_record):
    """Enrich a publication entry with RIMS data."""
    changes = []
    
    # Volume
    vol = rims_record.get("Volume", "").strip()
    if vol and not pub.get("volume"):
        pub["volume"] = vol
        changes.append(f"volume={vol}")
    
    # Issue
    issue = rims_record.get("Issue", "").strip()
    if issue and not pub.get("issue"):
        pub["issue"] = issue
        changes.append(f"issue={issue}")
    
    # Pages
    start = rims_record.get("Pagination (start page)", "").strip()
    end = rims_record.get("Pagination (end page)", "").strip()
    if start and not pub.get("pages"):
        if end:
            pub["pages"] = f"{start}-{end}"
        else:
            pub["pages"] = start
        changes.append(f"pages={pub['pages']}")
    
    # Article number (some journals use this instead of pages)
    article_num = rims_record.get("Article number OR Chapter number", "").strip()
    if article_num and not pub.get("pages") and not pub.get("article_number"):
        pub["article_number"] = article_num
        changes.append(f"article_number={article_num}")
    
    # PubMed ID (from merged sources)
    pmid = rims_record.get("_pmid", "").strip()
    if not pmid:
        # Fallback: check Proprietary ID if source is PubMed
        prop_id = rims_record.get("Proprietary ID", "").strip()
        source = rims_record.get("Source", "").strip()
        if source == "PubMed" and prop_id:
            pmid = prop_id
        # Also check External identifiers
        ext_ids = rims_record.get("External identifiers", "")
        pmid_match = re.search(r"pubmed:(\d+)", ext_ids)
        if pmid_match:
            pmid = pmid_match.group(1)
    if pmid and not pub.get("pmid"):
        pub["pmid"] = pmid
        changes.append(f"pmid={pmid}")
    
    # ISSN
    issn = rims_record.get("ISSN", "").strip()
    if issn and not pub.get("issn"):
        pub["issn"] = issn
        changes.append("issn")
    
    # eISSN
    eissn = rims_record.get("eISSN", "").strip()
    if eissn and not pub.get("eissn"):
        pub["eissn"] = eissn
        changes.append("eissn")
    
    # Publication date (exact)
    pub_date = rims_record.get("Publication date", "").strip()
    if pub_date and not pub.get("publication_date"):
        pub["publication_date"] = pub_date
        changes.append(f"publication_date={pub_date}")
    
    # Online publication date
    online_date = rims_record.get("Online publication date", "").strip()
    if online_date and not pub.get("online_date"):
        pub["online_date"] = online_date
        changes.append(f"online_date={online_date}")
    
    # Acceptance date
    accept_date = rims_record.get("Date of acceptance", "").strip()
    if accept_date and not pub.get("acceptance_date"):
        pub["acceptance_date"] = accept_date
        changes.append("acceptance_date")
    
    # Canonical journal title (use to verify/update journal name)
    canonical = rims_record.get("Canonical journal title", "").strip()
    if canonical:
        pub["canonical_journal"] = canonical
        changes.append(f"canonical_journal")
    
    # Keywords
    keywords = rims_record.get("Keywords", "").strip()
    if keywords and not pub.get("keywords"):
        pub["keywords"] = keywords
        changes.append("keywords")
    
    # Open access status
    oa = rims_record.get("Open access status", "").strip()
    if oa and not pub.get("open_access"):
        pub["open_access"] = oa
        changes.append(f"oa={oa}")
    
    # RIMS ID for cross-referencing
    rims_id = rims_record.get("ID", "").strip()
    if rims_id:
        pub["rims_id"] = rims_id
    
    return changes


def match_preprints_to_publications(pubs, rims_preprints):
    """Match RIMS preprint records to publication entries by title similarity.
    
    Returns list of (pub_index, preprint_doi, similarity_score) matches.
    """
    matches = []
    
    for pp in rims_preprints:
        pp_title = pp.get("Title OR Title (English)", "")
        pp_doi = pp.get("DOI", "").strip()
        if not pp_title:
            continue
        
        best_match = None
        best_score = 0
        
        for i, pub in enumerate(pubs):
            pub_title = pub.get("title", "")
            score = title_similarity(pp_title, pub_title)
            if score > best_score:
                best_score = score
                best_match = i
        
        if best_match is not None and best_score > 0.7:
            matches.append((best_match, pp_doi, best_score, pp_title[:60]))
    
    return matches


def main():
    parser = argparse.ArgumentParser(description="Enrich CV data from KI RIMS")
    parser.add_argument("--rims", default="templates/csv20260323.csv", help="RIMS CSV file")
    parser.add_argument("--data", default="cv_data.yaml", help="YAML data file")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()
    
    # Load data
    data = load_yaml(args.data)
    rims_records = load_rims(args.rims)
    
    # Separate RIMS records by type
    # Group by DOI so we can merge multiple sources
    rims_articles = {}  # DOI -> merged record (best fields from all sources)
    rims_preprints = []
    
    for r in rims_records:
        pub_type = r.get("Publication type", "")
        doi = normalize_doi(r.get("DOI", ""))
        
        if pub_type == "Journal article" and doi:
            if doi not in rims_articles:
                rims_articles[doi] = dict(r)
            else:
                # Merge: fill in empty fields from this source
                existing = rims_articles[doi]
                for k, v in r.items():
                    if v and v.strip() and (not existing.get(k) or not existing[k].strip()):
                        existing[k] = v
                # Also pick up PubMed ID specifically
                source = r.get("Source", "")
                prop_id = r.get("Proprietary ID", "").strip()
                if source == "PubMed" and prop_id:
                    existing["_pmid"] = prop_id
                # Check External identifiers for pubmed:NNNN
                ext_ids = r.get("External identifiers", "")
                pmid_match = re.search(r"pubmed:(\d+)", ext_ids)
                if pmid_match:
                    existing["_pmid"] = pmid_match.group(1)
        elif pub_type == "Preprint":
            rims_preprints.append(r)
    
    print(f"RIMS: {len(rims_articles)} journal articles, {len(rims_preprints)} preprints")
    print(f"YAML: {len(data['publications'])} publications, {len(data.get('preprints', []))} preprints")
    print()
    
    # === ENRICH PUBLICATIONS ===
    matched = 0
    enriched = 0
    total_changes = 0
    
    for i, pub in enumerate(data["publications"]):
        doi = normalize_doi(pub.get("doi", ""))
        if doi and doi in rims_articles:
            matched += 1
            changes = enrich_publication(pub, rims_articles[doi])
            if changes:
                enriched += 1
                total_changes += len(changes)
                if len(changes) <= 5:
                    print(f"  [{i+1}] +{len(changes)} fields: {', '.join(changes[:5])}")
                else:
                    print(f"  [{i+1}] +{len(changes)} fields: {', '.join(changes[:3])}...")
    
    print(f"\nPublications: {matched}/{len(data['publications'])} matched, "
          f"{enriched} enriched with {total_changes} total new fields")
    
    # === MATCH PREPRINTS ===
    print(f"\n--- Preprint matching ---")
    print(f"Checking {len(rims_preprints)} RIMS preprints against {len(data['publications'])} publications...")
    
    preprint_matches = match_preprints_to_publications(data["publications"], rims_preprints)
    new_preprint_links = 0
    
    for pub_idx, pp_doi, score, pp_title in preprint_matches:
        pub = data["publications"][pub_idx]
        existing_preprint = pub.get("links", {}).get("preprint", "")
        
        if pp_doi and not existing_preprint:
            if "links" not in pub:
                pub["links"] = {}
            pub["links"]["preprint"] = f"https://doi.org/{pp_doi}"
            new_preprint_links += 1
            print(f"  [{pub_idx+1}] linked preprint doi:{pp_doi} (score={score:.2f})")
        elif pp_doi and existing_preprint:
            # Already has preprint link — just note it
            pass
    
    print(f"New preprint links added: {new_preprint_links}")
    
    # === ALSO ENRICH YAML PREPRINTS SECTION ===
    rims_preprints_by_doi = {}
    for r in rims_preprints:
        doi = normalize_doi(r.get("DOI", ""))
        if doi:
            rims_preprints_by_doi[doi] = r
    
    preprint_enriched = 0
    for i, pp in enumerate(data.get("preprints", [])):
        doi = normalize_doi(pp.get("doi", ""))
        if doi and doi in rims_preprints_by_doi:
            changes = enrich_publication(pp, rims_preprints_by_doi[doi])
            if changes:
                preprint_enriched += 1
    
    print(f"Preprint entries enriched: {preprint_enriched}")
    
    # === SUMMARY ===
    print(f"\n=== Summary ===")
    print(f"Publications matched: {matched}/{len(data['publications'])}")
    print(f"Publications enriched: {enriched}")
    print(f"Total new fields: {total_changes}")
    print(f"New preprint links: {new_preprint_links}")
    print(f"Preprint entries enriched: {preprint_enriched}")
    
    # Save
    if not args.dry_run:
        save_yaml(data, args.data)
        print(f"\nWritten to {args.data}")
    else:
        print("\n[DRY RUN - no changes written]")


if __name__ == "__main__":
    main()
