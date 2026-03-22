# CV Generator — User Guide

## Overview

Your CV data lives in one file: `cv_data.yaml`. Everything else is generated from it.

```
cv_data.yaml  ──→  scripts/render_cv.py    ──→  output/cv.tex + cv.pdf
                   scripts/list_outputs.py  ──→  output/open_outputs.md (or CSV)
                   scripts/list_coauthors.py ──→  (printed to screen or file)
```

## Prerequisites

- Python 3.8+
- `pyyaml` and `jinja2` (`pip install pyyaml jinja2`)
- `pdflatex` for PDF output (install via `texlive-latex-base` or similar)

## Day-to-day workflow

### 1. Edit `cv_data.yaml`

This is the only file you edit regularly. It has these sections:

- `meta` — your name, email, ORCID, affiliation
- `publications` — peer-reviewed journal articles
- `preprints` — preprints not yet published in a journal
- `book_chapters` — books and book chapters
- `presentations` — invited talks, conference talks, popular science talks
- `other_publications` — reports, scholarly debate, blog posts, etc.

Each entry looks like this:

```yaml
- title: "Intrinsic brain connectivity after partial sleep deprivation"
  authors: "Nilsonne G, Tamm S, Schwarz J, ..."
  year: 2017
  doi: "10.1038/s41598-017-09744-7"
  journal: "Scientific Reports"
  links:
    preprint: "http://dx.doi.org/10.1101/073494"
    preregistration: "https://clinicaltrials.gov/ct2/show/NCT02000076"
    data: "https://openneuro.org/datasets/ds000201"
    code: "http://doi.org/10.5281/zenodo.581250"
```

To add a new paper, just add a new entry at the top of the `publications` list.
To add a new talk, add it to `presentations`. And so on.

Supported link types: `preprint`, `data`, `code`, `materials`, `preregistration`,
`narrative`, `slides`, `video`, `poster`, `protocol`, `web`. You can also add any
custom key — the renderer will display it.

### 2. Generate outputs

From the repo root directory:

```bash
# Generate LaTeX CV + PDF + open outputs list
python3 scripts/render_cv.py

# Generate LaTeX only (no PDF compilation)
python3 scripts/render_cv.py --no-pdf

# The outputs appear in the output/ directory:
#   output/cv.tex          — LaTeX source
#   output/cv.pdf          — compiled PDF
#   output/open_outputs.md — list of all open outputs grouped by type
```

### 3. List specific output types

```bash
# All open datasets
python3 scripts/list_outputs.py --type data

# All code repositories
python3 scripts/list_outputs.py --type code

# All preprints / open access versions
python3 scripts/list_outputs.py --type preprint

# All preregistrations
python3 scripts/list_outputs.py --type preregistration

# Everything
python3 scripts/list_outputs.py --type all

# Summary counts
python3 scripts/list_outputs.py --summary

# CSV export (e.g. for a spreadsheet or a funder report)
python3 scripts/list_outputs.py --type data --format csv > my_datasets.csv

# Plain text
python3 scripts/list_outputs.py --type all --format text
```

### 4. List co-authors

```bash
# Alphabetical list from YAML
python3 scripts/list_coauthors.py

# With papers per co-author
python3 scripts/list_coauthors.py --with-papers

# CSV export
python3 scripts/list_coauthors.py --format csv > coauthors.csv

# Markdown
python3 scripts/list_coauthors.py --format md > coauthors.md

# Pull directly from ORCID (doesn't require cv_data.yaml)
python3 scripts/list_coauthors.py --from-orcid 0000-0001-5273-0150

# Include yourself in the list
python3 scripts/list_coauthors.py --include-self
```

## Importing new publications from ORCID

When you publish a new paper and it appears on ORCID:

```bash
# Pull new works (existing entries are preserved)
python3 scripts/import_orcid.py

# Also update author lists from ORCID for existing entries
python3 scripts/import_orcid.py --update-authors
```

This adds skeleton entries with title, authors, year, DOI, and journal.
You then add the `links:` section manually (preprint, data, code, etc.).

## Customizing the LaTeX template

The template is at `templates/cv.tex.j2`. It uses Jinja2 syntax with
non-standard delimiters to avoid clashing with LaTeX:

- `<< variable >>` instead of `{{ variable }}`
- `<% block %>...<% endblock %>` instead of `{% block %}...{% endblock %}`

Edit this file to match your preferred CV formatting. The current template
is a starting point — you'll want to adjust fonts, margins, section order,
and formatting to match your style.

## Re-parsing from LaTeX (one-time migration)

If you've made changes to `CV_GN.tex` and want to re-import into the YAML:

```bash
python3 scripts/parse_latex_cv.py
```

**Warning:** This overwrites `cv_data.yaml`. It's meant as a one-time migration
tool, not part of the regular workflow. Once you're maintaining `cv_data.yaml`
directly, you won't need this anymore.

## File overview

```
CV/
├── cv_data.yaml              ← YOUR DATA (single source of truth)
├── CV_GN.tex                 ← Original LaTeX CV (kept for reference)
├── CV_GN.pdf                 ← Original compiled PDF
├── templates/
│   └── cv.tex.j2             ← LaTeX template (customize this)
├── scripts/
│   ├── render_cv.py          ← YAML → LaTeX/PDF + open outputs list
│   ├── list_outputs.py       ← Query open outputs by type
│   ├── list_coauthors.py     ← Alphabetical co-author list
│   ├── import_orcid.py       ← Pull new publications from ORCID
│   └── parse_latex_cv.py     ← One-time LaTeX → YAML migration
├── output/
│   ├── cv.tex                ← Generated LaTeX (don't edit)
│   ├── cv.pdf                ← Generated PDF
│   └── open_outputs.md       ← Generated output list
├── schema.md                 ← Field documentation
└── README_generator.md       ← This file
```

## Typical scenarios

**"A funder asks for a list of my open datasets"**
```bash
python3 scripts/list_outputs.py --type data --format csv > datasets_for_funder.csv
```

**"I need a complete alphabetical co-author list for a grant application"**
```bash
python3 scripts/list_coauthors.py --format text > coauthors.txt
```

**"I just published a new paper"**
1. Run `python3 scripts/import_orcid.py` (or add the entry manually to `cv_data.yaml`)
2. Add links (preprint, data, code) to the new entry in `cv_data.yaml`
3. Run `python3 scripts/render_cv.py`
4. Commit and push

**"I gave a talk and want to add it"**
1. Add an entry to the `presentations:` section in `cv_data.yaml`
2. Run `python3 scripts/render_cv.py`
3. Commit and push

**"How open is my research? What fraction of papers have open data?"**
```bash
python3 scripts/list_outputs.py --summary
```
