# CV Generator — User Guide

## Overview

Your CV data lives in one file: `cv_data.yaml`. Everything else is generated from it.

```
cv_data.yaml  ──→  scripts/render_cv.py     ──→  output/cv.tex + cv.pdf
              ──→  scripts/render_vr.py      ──→  output/vr_publist.tex
              ──→  scripts/list_outputs.py   ──→  output/open_outputs.md (or CSV)
              ──→  scripts/list_coauthors.py ──→  (printed to screen or file)
```

## Prerequisites

- Python 3.8+
- `pyyaml` and `jinja2` (`pip install pyyaml jinja2`)
- `pdflatex` for PDF output (install via MiKTeX on Windows or `texlive` on Linux/Mac)
- LaTeX packages: `libertinus`, `enumitem`, `titlesec`, `xurl`, `hyperref`, `fancyhdr`, `lastpage`

## Day-to-day workflow

### 1. Edit `cv_data.yaml`

This is the only file you edit regularly. It has these sections:

| Section | Description |
|---------|-------------|
| `meta` | Name, email, ORCID, affiliation |
| `degrees` | Academic degrees |
| `employment` | Employment and appointments |
| `phd_supervision` | Supervised PhD students (structured: name, institution, year, role, thesis) |
| `grants` | Research grants |
| `teaching` | Teaching activities (with nested sub-items for course roles and student theses) |
| `awards` | Awards and prizes |
| `phd_committee` | PhD committee memberships |
| `academic_commissions` | Academic commissions (with nested sub-items; peer review entries have `wos: true` flag) |
| `other_commissions` | Other commissions (with nested sub-items for organizations) |
| `publications` | Peer-reviewed journal articles |
| `preprints` | Preprints not yet published in a journal |
| `books` | Books and book chapters |
| `open_peer_reviews` | Open peer-review reports |
| `reports` | Reports |
| `study_materials` | Study materials |
| `digital_research_objects` | Datasets, software, etc. |
| `scholarly_debate` | Debate articles, opinion pieces |
| `invited_talks` | Invited talks (with `venue` field) |
| `conference_presentations` | Conference presentations |
| `conference_abstracts` | Indexed conference abstracts |
| `popular_science_talks` | Popular science talks |
| `popular_science_writings` | Popular science writings |
| `blogging` | Blog posts |

Each publication entry looks like this:

```yaml
- title: "Intrinsic brain connectivity after partial sleep deprivation"
  authors: "Nilsonne G, Tamm S, Schwarz J, ..."
  year: 2017
  doi: "10.1038/s41598-017-09744-7"
  journal: "Scientific Reports"
  volume: "7"
  issue: "1"
  pages: "9422"
  pmid: "28842596"
  links:
    preprint: "http://dx.doi.org/10.1101/073494"
    data: "https://openneuro.org/datasets/ds000201"
    code: "http://doi.org/10.5281/zenodo.581250"
    correction: "https://doi.org/10.xxxx/yyyy"  # if applicable
```

Supported link types: `preprint`, `data`, `code`, `materials`, `preregistration`,
`narrative`, `slides`, `video`, `poster`, `protocol`, `web`, `correction`, `pdf`,
`diva`, `program`. Custom keys are also displayed.

### 2. Generate the CV

```bash
# Generate LaTeX CV + PDF + open outputs list
python3 scripts/render_cv.py

# Generate LaTeX only (no PDF compilation)
python3 scripts/render_cv.py --no-pdf

# Outputs:
#   output/cv.tex          — LaTeX source
#   output/cv.pdf          — compiled PDF
#   output/open_outputs.md — list of all open outputs grouped by type
```

### 3. Generate VR publication list

For Vetenskapsrådet (Swedish Research Council) grant applications:

```bash
python3 scripts/render_vr.py

# Output: output/vr_publist.tex
```

**Before generating**, edit `vr_config.yaml` to configure:

1. **Top 10 selected outputs** — list DOIs of your most important papers:
   ```yaml
   selected_outputs:
     - "10.1016/j.jclinepi.2025.111710"
     - "10.1038/s41562-021-01173-x"
     # ... up to 10
   ```

2. **Contribution descriptions** — max 4 lines per selected paper:
   ```yaml
   selected_contributions:
     - doi: "10.1016/j.jclinepi.2025.111710"
       contribution: "I designed the study, led the data collection across Nordic countries, performed the analyses, and wrote the manuscript."
   ```

3. **Article type overrides** — correct auto-classification if needed:
   ```yaml
   type_overrides:
     - doi: "10.xxxx/yyyy"
       type: "review"   # original, review, conference, book, other
   ```

The VR template follows VR requirements:
- Arial 11pt, single-spaced, 2.5cm margins, max 5 pages
- Section 1: Top 10 with contribution descriptions
- Section 2: Peer-reviewed 2017–2025 (original articles, conference, reviews, books, other)
- Section 3: Non peer-reviewed 2017–2025 (popular science, preprints, other)
- Section 4: Publication counts
- Applicant name **bolded** in all author lists
- Reverse chronological order within each category

### 4. List specific output types

```bash
python3 scripts/list_outputs.py --type data      # All open datasets
python3 scripts/list_outputs.py --type code       # All code repositories
python3 scripts/list_outputs.py --type preprint   # All preprints
python3 scripts/list_outputs.py --type all        # Everything
python3 scripts/list_outputs.py --summary         # Summary counts

# CSV export
python3 scripts/list_outputs.py --type data --format csv > my_datasets.csv
```

### 5. List co-authors

```bash
python3 scripts/list_coauthors.py                    # Alphabetical list
python3 scripts/list_coauthors.py --with-papers       # With papers per co-author
python3 scripts/list_coauthors.py --format csv > coauthors.csv
python3 scripts/list_coauthors.py --from-orcid 0000-0001-5273-0150
```

## Enrichment scripts

### Enrich from KI RIMS

If you have a RIMS CSV export (e.g. `templates/csv20260323.csv`):

```bash
# Adds volume, issue, pages, PMID, keywords, etc. from RIMS
python3 scripts/enrich_from_rims.py

# Add publications/preprints from RIMS not yet in YAML
python3 scripts/add_missing_from_rims.py
```

### Import from ORCID

```bash
python3 scripts/import_orcid.py                  # Pull new works
python3 scripts/import_orcid.py --update-authors  # Also update author lists
```

### Re-extract links and venues from original LaTeX

```bash
# One-time: re-parse scholarly debate links and invited talk venues
python3 scripts/fix_links_and_venues.py
```

## Customizing the LaTeX templates

Templates are in `templates/` and use Jinja2 with non-standard delimiters:

- `<< variable >>` for variables
- `<% block %>...<% endblock %>` for blocks
- Filters: `|tex` (escape LaTeX), `|autolink` (escape + hyperlink bare URLs/DOIs),
  `|vancouver_authors` (truncate to 6 + et al), `|notrailingdot`, `|doi`, `|links`

| Template | Purpose |
|----------|---------|
| `templates/cv.tex.j2` | Full academic CV (Libertinus font, 2cm margins) |
| `templates/vr_publist.tex.j2` | VR publication list (Arial 11pt, 2.5cm margins) |

## File overview

```
CV/
├── cv_data.yaml               ← YOUR DATA (single source of truth)
├── vr_config.yaml             ← VR publication list configuration
├── CV_GN.tex                  ← Original LaTeX CV (kept for reference)
├── templates/
│   ├── cv.tex.j2              ← CV template
│   ├── vr_publist.tex.j2      ← VR publication list template
│   └── csv20260323.csv        ← KI RIMS data export
├── scripts/
│   ├── render_cv.py           ← YAML → CV LaTeX/PDF
│   ├── render_vr.py           ← YAML → VR publication list
│   ├── list_outputs.py        ← Query open outputs by type
│   ├── list_coauthors.py      ← Alphabetical co-author list
│   ├── import_orcid.py        ← Pull from ORCID API
│   ├── enrich_from_rims.py    ← Enrich YAML from KI RIMS CSV
│   ├── add_missing_from_rims.py ← Add missing entries from RIMS
│   ├── fix_links_and_venues.py  ← Re-parse links/venues from LaTeX
│   ├── parse_full_cv.py       ← One-time LaTeX → YAML migration
│   └── parse_latex_cv.py      ← Earlier partial LaTeX parser
├── output/
│   ├── cv.tex                 ← Generated CV LaTeX
│   ├── cv.pdf                 ← Generated CV PDF
│   ├── vr_publist.tex         ← Generated VR publication list
│   └── open_outputs.md        ← Generated output list
├── schema.md                  ← YAML field documentation
├── WORKFLOW.md                ← This file
└── README_generator.md        ← Older readme (see this file instead)
```

## Typical scenarios

**"I just published a new paper"**
1. Add the entry to `publications:` in `cv_data.yaml` (or run `import_orcid.py`)
2. Add links (preprint, data, code) to the new entry
3. Run `python3 scripts/render_cv.py`
4. Commit and push

**"I need a VR publication list for a grant application"**
1. Edit `vr_config.yaml` — select your top 10, write contributions, check type overrides
2. Run `python3 scripts/render_vr.py`
3. Compile `output/vr_publist.tex` with pdflatex
4. Check it fits within 5 pages

**"A funder asks for a list of my open datasets"**
```bash
python3 scripts/list_outputs.py --type data --format csv > datasets_for_funder.csv
```

**"I got a new RIMS export and want to update"**
1. Put the CSV in `templates/`
2. Update the filename in `enrich_from_rims.py` and `add_missing_from_rims.py`
3. Run both scripts
4. Review and commit

**"How open is my research?"**
```bash
python3 scripts/list_outputs.py --summary
```
