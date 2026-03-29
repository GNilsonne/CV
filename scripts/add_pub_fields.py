#!/usr/bin/env python3
"""
Add 'id' (bibtex-style key) and 'pub_type' fields to every publication in cv_data.yaml.

- id: firstauthorsurname_year_firstmeaningfulword  (e.g. nilsonne_2006_selenite)
- pub_type: 'original' or 'review' (auto-detected by heuristic, meant for manual correction)

Run once, then manually review/adjust pub_type values.
"""

import re
import yaml

SKIP_WORDS = {'a', 'an', 'the', 'on', 'of', 'in', 'to', 'for', 'and', 'is', 'are',
              'was', 'were', 'do', 'does', 'no', 'not', 'its', 'it', 'by', 'with',
              'from', 'at', 'as', 'or', 'but', 'be', 'has', 'had', 'have', 'this',
              'that', 'which', 'who', 'how', 'what', 'when', 'where', 'why'}


def make_bibkey(pub):
    authors = (pub.get('authors', '') or '').strip()
    year = pub.get('year', '') or ''
    title = (pub.get('title', '') or '').strip()

    # First author surname
    first_author = authors.split(',')[0].strip() if authors else 'unknown'
    surname = first_author.split()[0] if first_author else 'unknown'
    # Lowercase, keep accented chars, strip punctuation
    surname = re.sub(r'[^a-zåäöüéèêëàáâãñ0-9]', '', surname.lower())
    if not surname:
        surname = 'unknown'

    yr = str(year) if year else 'nd'

    words = re.findall(r'[a-zåäöüéèêëàáâãñ]+', title.lower())
    first_word = 'untitled'
    for w in words:
        if w not in SKIP_WORDS and len(w) > 1:
            first_word = w
            break

    return f'{surname}_{yr}_{first_word}'


def guess_pub_type(pub):
    """Heuristic: 'review' if title contains systematic review / meta-analysis / scoping review."""
    title = (pub.get('title', '') or '').lower()
    if any(x in title for x in ['systematic review', 'meta-analy', 'scoping review']):
        return 'review'
    return 'original'


def main():
    with open('cv_data.yaml', encoding='utf-8') as f:
        raw = f.read()
    data = yaml.load(raw, Loader=yaml.SafeLoader)

    pubs = data.get('publications', [])

    # Generate keys, disambiguate duplicates
    used_keys = {}
    for pub in pubs:
        key = make_bibkey(pub)
        if key in used_keys:
            suffix = 'b'
            while f'{key}{suffix}' in used_keys:
                suffix = chr(ord(suffix) + 1)
            key = f'{key}{suffix}'
        used_keys[key] = True

        # Only add if not already present
        if 'id' not in pub:
            pub['id'] = key
        if 'pub_type' not in pub:
            pub['pub_type'] = guess_pub_type(pub)

    # Write back
    # Use a custom dumper to preserve order and readability
    class OrderedDumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        if any(c in data for c in ':{}[]&*?|->!%@`'):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    OrderedDumper.add_representer(str, str_representer)

    with open('cv_data.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(data, f, Dumper=OrderedDumper, allow_unicode=True,
                  default_flow_style=False, sort_keys=False, width=120)

    print(f"Updated {len(pubs)} publications with id + pub_type fields.")

    # Summary
    originals = sum(1 for p in pubs if p.get('pub_type') == 'original')
    reviews = sum(1 for p in pubs if p.get('pub_type') == 'review')
    print(f"  original: {originals}")
    print(f"  review:   {reviews}")
    print()
    print("Review articles (verify these):")
    for p in pubs:
        if p.get('pub_type') == 'review':
            print(f"  {p['id']}: {p.get('title', '')[:80]}")


if __name__ == '__main__':
    main()
