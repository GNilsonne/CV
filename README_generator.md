# CV Generator

YAML-driven academic CV with structured links to open research outputs.

## Quick Start

```bash
cd cv-generator

# 1. Import/update from ORCID (adds new publications, preserves existing edits)
python3 scripts/import_orcid.py

# 2. Edit cv_data.yaml — add links, fix author lists, add presentations, etc.

# 3. Render CV to LaTeX/PDF
python3 scripts/render_cv.py              # generates output/cv.tex + output/cv.pdf
python3 scripts/render_cv.py --no-pdf     # LaTeX only (if no pdflatex installed)

# 4. List open outputs
python3 scripts/list_outputs.py --summary              # count summary
python3 scripts/list_outputs.py --type data             # all open datasets
python3 scripts/list_outputs.py --type code             # all code repos
python3 scripts/list_outputs.py --type preprint         # all preprints/OA versions
python3 scripts/list_outputs.py --type all              # everything
python3 scripts/list_outputs.py --type data --format csv # CSV export
```

## Files

```
cv-generator/
├── cv_data.yaml           ← Your data (the single source of truth)
├── schema.md              ← Field documentation
├── README.md              ← This file
├── templates/
│   └── cv.tex.j2          ← LaTeX template (customise to match your style)
├── scripts/
│   ├── import_orcid.py    ← Pulls publications from ORCID API
│   ├── render_cv.py       ← Renders YAML → LaTeX/PDF + open_outputs.md
│   └── list_outputs.py    ← Query/filter open outputs by type
└── output/
    ├── cv.tex             ← Generated LaTeX
    ├── cv.pdf             ← Generated PDF
    └── open_outputs.md    ← Generated list of all open outputs
```

## Workflow

1. **New paper published?** → Run `import_orcid.py` to pull it from ORCID, then add links
2. **New talk or non-academic paper?** → Add entry to `cv_data.yaml` manually
3. **Need updated CV?** → Run `render_cv.py`
4. **Funder asks about open data?** → Run `list_outputs.py --type data`

## Publication List Renderers

- `python3 scripts/render_vr.py` renders the VR publication list to `output/vr_publist.tex` and, if `pdflatex` is available, `output/vr_publist.pdf`.
- `python3 scripts/render_kid.py` renders a KI-style publication list for the rolling last 5 years using the same layout as the VR output, writing `output/kid_publist.tex` and, if `pdflatex` is available, `output/kid_publist.pdf`.
- Add `--no-pdf` to either command to skip PDF compilation and write only the LaTeX source.

## Customisation

- **LaTeX template**: Edit `templates/cv.tex.j2` to match your preferred CV style
- **Link types**: Add any key to the `links:` dict — the renderer handles arbitrary types
- **Sections**: Add new sections in `cv_data.yaml` and corresponding blocks in the template
- **Author lists**: The ORCID import uses "Nilsonne G, et al." as placeholder — fill in real author lists

## Dependencies

- Python 3.8+
- `pyyaml` and `jinja2` (Python packages)
- `pdflatex` (optional, for PDF output — install via `texlive`)
