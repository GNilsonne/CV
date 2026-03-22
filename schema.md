# CV Data Schema

This document describes the YAML schema used in `cv_data.yaml`.

## Top-level sections

- `meta` — Your personal/contact info
- `publications` — Peer-reviewed journal articles
- `preprints` — Preprints (not yet published in a journal)
- `book_chapters` — Book chapters and similar
- `presentations` — Talks, posters, invited lectures
- `other_publications` — Non-academic papers, reports, blog posts, etc.

## Entry fields

### Common fields (all entry types)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Title of the work |
| `year` | int | yes | Publication year |
| `doi` | string | no | DOI (without https://doi.org/ prefix) |
| `tags` | list[str] | no | Free-form tags for filtering |
| `links` | dict | no | See Links below |

### Publication-specific fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `authors` | string | yes | Author list as displayed |
| `journal` | string | yes | Journal name |
| `volume` | string | no | Volume number |
| `issue` | string | no | Issue number |
| `pages` | string | no | Page range |
| `type` | string | no | e.g., "article", "comment", "review", "letter" |

### Presentation-specific fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event` | string | yes | Conference/event name |
| `location` | string | no | City, country |
| `date` | string | no | ISO date (YYYY-MM-DD) |
| `type` | string | no | e.g., "invited", "contributed", "keynote", "poster" |

## Links

The `links` field is a dictionary. Keys are link types, values are URLs.

Supported link types:
- `preprint` — Link to openly accessible preprint
- `data` — Link to open dataset
- `code` — Link to code repository
- `materials` — Link to open materials (stimuli, questionnaires, etc.)
- `preregistration` — Link to preregistration (OSF, AsPredicted, etc.)
- `narrative` — Link to narrative description (blog post, thread, etc.)
- `slides` — Presentation slides
- `video` — Video recording
- `protocol` — Registered protocol

Any other keys are also allowed — the renderer will display them generically.
