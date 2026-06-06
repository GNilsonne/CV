#!/usr/bin/env python3
"""
Match an external people list against CV co-authors exported by list_coauthors.py.

Input files:
  1) coauthors CSV from scripts/list_coauthors.py --format csv
     Expected columns: name, paper_count

  2) external CSV exported from Excel
     Expected columns: first_name,last_name
     Can be overridden with --first-col / --last-col

Outputs:
  - matched_exact.csv
  - matched_possible.csv
  - unmatched.csv

Typical usage:
  python3 scripts/list_coauthors.py --format csv
  python3 scripts/match_coauthors.py \
      --coauthors output/coauthors.csv \
      --people people.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable


SURNAME_PARTICLES = {
    "da", "de", "del", "della", "der", "di", "dos", "du", "la", "le",
    "van", "von", "den", "ten", "ter", "bin", "ibn", "al", "el"
}


def collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def strip_accents(s: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )


def normalize_text(s: str, *, remove_accents: bool = False) -> str:
    s = collapse_spaces(s)
    if remove_accents:
        s = strip_accents(s)
    s = s.casefold()
    return s


def normalize_name(name: str, *, remove_accents: bool = False) -> str:
    name = normalize_text(name, remove_accents=remove_accents)
    name = re.sub(r"[.,;:()\[\]{}]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def split_name_tokens(name: str) -> list[str]:
    return [t for t in normalize_name(name).split(" ") if t]


def coauthor_surname_key(name: str) -> str:
    """Best-effort surname extraction for mixed formats like 'First Last' and 'Surname I'."""
    tokens = split_name_tokens(name)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]

    last = tokens[-1]
    if len(last) <= 3 and last.isalpha():
        surname_tokens = tokens[:-1]
    else:
        surname_tokens = [last]
        idx = len(tokens) - 2
        while idx >= 0 and tokens[idx] in SURNAME_PARTICLES:
            surname_tokens.insert(0, tokens[idx])
            idx -= 1
    return " ".join(surname_tokens)


def external_surname_key(first_name: str, last_name: str) -> str:
    return normalize_name(last_name)


def first_initial(name: str) -> str:
    tokens = split_name_tokens(name)
    return tokens[0][0] if tokens and tokens[0] else ""


def external_first_initial(first_name: str) -> str:
    first_name = normalize_name(first_name)
    return first_name[0] if first_name else ""


def first_token(name: str) -> str:
    tokens = split_name_tokens(name)
    return tokens[0] if tokens else ""


def names_equivalent(full_name_a: str, full_name_b: str) -> bool:
    return normalize_name(full_name_a) == normalize_name(full_name_b)


def names_equivalent_no_accents(full_name_a: str, full_name_b: str) -> bool:
    return normalize_name(full_name_a, remove_accents=True) == normalize_name(full_name_b, remove_accents=True)


def row_full_name(first_name: str, last_name: str) -> str:
    return collapse_spaces(f"{first_name} {last_name}")


def load_coauthors(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)

    required = {"name"}
    missing = required - set(rows[0].keys()) if rows else required
    if missing:
        raise ValueError(f"Coauthors CSV missing required columns: {sorted(missing)}")

    out = []
    for row in rows:
        name = collapse_spaces(row.get("name", ""))
        if not name:
            continue
        out.append({
            "name": name,
            "paper_count": row.get("paper_count", ""),
            "norm": normalize_name(name),
            "norm_ascii": normalize_name(name, remove_accents=True),
            "surname": coauthor_surname_key(name),
            "first_initial": first_initial(name),
            "first_token": first_token(name),
        })
    return out


def load_people(path: Path, first_col: str, last_col: str) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return []

    missing = {first_col, last_col} - set(rows[0].keys())
    if missing:
        raise ValueError(f"People CSV missing required columns: {sorted(missing)}")

    out = []
    for i, row in enumerate(rows, start=2):
        first_name = collapse_spaces(row.get(first_col, ""))
        last_name = collapse_spaces(row.get(last_col, ""))
        full_name = row_full_name(first_name, last_name)
        if not full_name.strip():
            continue
        out.append({
            "source_row": i,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "norm": normalize_name(full_name),
            "norm_ascii": normalize_name(full_name, remove_accents=True),
            "surname": external_surname_key(first_name, last_name),
            "first_initial": external_first_initial(first_name),
            "first_token": first_token(first_name),
            "raw": row,
        })
    return out


def unique_by_name(candidates: Iterable[dict]) -> list[dict]:
    seen = set()
    out = []
    for c in candidates:
        key = c["name"]
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def build_indexes(coauthors: list[dict]):
    by_norm = defaultdict(list)
    by_norm_ascii = defaultdict(list)
    by_surname = defaultdict(list)
    by_surname_initial = defaultdict(list)

    for c in coauthors:
        by_norm[c["norm"]].append(c)
        by_norm_ascii[c["norm_ascii"]].append(c)
        by_surname[c["surname"]].append(c)
        by_surname_initial[(c["surname"], c["first_initial"])].append(c)

    return by_norm, by_norm_ascii, by_surname, by_surname_initial


def match_people(people: list[dict], coauthors: list[dict]):
    by_norm, by_norm_ascii, by_surname, by_surname_initial = build_indexes(coauthors)

    matched_exact = []
    matched_possible = []
    unmatched = []

    for person in people:
        exact = unique_by_name(by_norm.get(person["norm"], []))
        if exact:
            for c in exact:
                matched_exact.append({
                    **person,
                    "match_type": "exact_full_name",
                    "matched_coauthor": c["name"],
                    "paper_count": c["paper_count"],
                })
            continue

        exact_ascii = unique_by_name(by_norm_ascii.get(person["norm_ascii"], []))
        if exact_ascii:
            for c in exact_ascii:
                matched_exact.append({
                    **person,
                    "match_type": "exact_full_name_no_accents",
                    "matched_coauthor": c["name"],
                    "paper_count": c["paper_count"],
                })
            continue

        possible = []

        surname_initial = unique_by_name(by_surname_initial.get((person["surname"], person["first_initial"]), []))
        for c in surname_initial:
            possible.append(("same_surname_same_first_initial", c))

        same_surname = unique_by_name(by_surname.get(person["surname"], []))
        for c in same_surname:
            if c["first_token"] and person["first_token"] and c["first_token"] == person["first_token"]:
                possible.append(("same_surname_same_first_token", c))

        dedup = []
        seen = set()
        for reason, cand in possible:
            key = cand["name"]
            if key not in seen:
                seen.add(key)
                dedup.append((reason, cand))

        if dedup:
            matched_possible.append({
                **person,
                "possible_matches": " | ".join(c["name"] for _, c in dedup),
                "possible_match_types": " | ".join(r for r, _ in dedup),
                "possible_paper_counts": " | ".join(str(c["paper_count"]) for _, c in dedup),
            })
        else:
            unmatched.append(person)

    return matched_exact, matched_possible, unmatched


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(description="Match external people list against CV co-authors")
    parser.add_argument("--coauthors", required=True, help="CSV from scripts/list_coauthors.py --format csv")
    parser.add_argument("--people", required=True, help="CSV exported from Excel")
    parser.add_argument("--first-col", default="first_name", help="First-name column in people CSV")
    parser.add_argument("--last-col", default="last_name", help="Last-name column in people CSV")
    parser.add_argument("--outdir", default="output/coauthor_matches", help="Output directory")
    args = parser.parse_args()

    coauthors = load_coauthors(Path(args.coauthors))
    people = load_people(Path(args.people), args.first_col, args.last_col)

    matched_exact, matched_possible, unmatched = match_people(people, coauthors)

    outdir = Path(args.outdir)
    write_csv(
        outdir / "matched_exact.csv",
        matched_exact,
        ["source_row", "first_name", "last_name", "full_name", "match_type", "matched_coauthor", "paper_count"],
    )
    write_csv(
        outdir / "matched_possible.csv",
        matched_possible,
        ["source_row", "first_name", "last_name", "full_name", "possible_match_types", "possible_matches", "possible_paper_counts"],
    )
    write_csv(
        outdir / "unmatched.csv",
        unmatched,
        ["source_row", "first_name", "last_name", "full_name"],
    )

    print(f"Co-authors loaded: {len(coauthors)}")
    print(f"People loaded: {len(people)}")
    print(f"Exact matches: {len(matched_exact)}")
    print(f"Possible matches: {len(matched_possible)}")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Written: {outdir / 'matched_exact.csv'}")
    print(f"Written: {outdir / 'matched_possible.csv'}")
    print(f"Written: {outdir / 'unmatched.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
