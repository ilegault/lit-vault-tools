# Test fixtures

Real, unmodified API responses captured by hand for ticket 05 (`scripts/capture_fixtures.py`).
Paper: DOI `10.1016/j.matdes.2024.112730`. Capture date for every file: 2026-10-06.

## How each API expects its credentials

- OpenAlex: API key as query parameter `api_key=<KEY>`.
- Semantic Scholar (Academic Graph API, `https://api.semanticscholar.org/graph/v1`): API key in request header `x-api-key: <KEY>`.
- Crossref: no key; contact address as query parameter `mailto=<MAILTO>` (polite pool).
- OSTI.gov: no key; ask for JSON with header `Accept: application/json`.

## Requests

### `openalex_work.json`

- Method: `GET`
- URL: `https://api.openalex.org/works/doi:10.1016/j.matdes.2024.112730?api_key=<KEY>`
- Headers: `(none)`
- Body: `(none)`
- Credentials: OpenAlex: query parameter `api_key=<KEY>`
- Captured: 2026-10-06

### `openalex_institution.json`

- Method: `GET`
- URL: `https://api.openalex.org/institutions/I123534392?api_key=<KEY>`
- Headers: `(none)`
- Body: `(none)`
- Credentials: OpenAlex: query parameter `api_key=<KEY>`
- Captured: 2026-10-06

### `s2_paper.json`

- Method: `GET`
- URL: `https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.matdes.2024.112730?fields=paperId`
- Headers: `{"x-api-key": "<KEY>"}`
- Body: `(none)`
- Credentials: Semantic Scholar: header `x-api-key: <KEY>`
- Captured: 2026-10-06

### `s2_references_page1.json`

- Method: `GET`
- URL: `https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.matdes.2024.112730/references?fields=title,year,citationCount,externalIds,isInfluential&limit=5&offset=0`
- Headers: `{"x-api-key": "<KEY>"}`
- Body: `(none)`
- Credentials: Semantic Scholar: header `x-api-key: <KEY>`
- Captured: 2026-10-06

### `s2_references_last.json`

- Method: `GET`
- URL: `https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.matdes.2024.112730/references?fields=title,year,citationCount,externalIds,isInfluential&limit=5&offset=57`
- Headers: `{"x-api-key": "<KEY>"}`
- Body: `(none)`
- Credentials: Semantic Scholar: header `x-api-key: <KEY>`
- Captured: 2026-10-06

### `s2_citations_page1.json`

- Method: `GET`
- URL: `https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.matdes.2024.112730/citations?fields=title,year,citationCount,externalIds,isInfluential&limit=5&offset=0`
- Headers: `{"x-api-key": "<KEY>"}`
- Body: `(none)`
- Credentials: Semantic Scholar: header `x-api-key: <KEY>`
- Captured: 2026-10-06

### `s2_batch.json`

- Method: `POST`
- URL: `https://api.semanticscholar.org/graph/v1/paper/batch?fields=abstract,tldr,authors,venue`
- Headers: `{"Content-Type": "application/json", "x-api-key": "<KEY>"}`
- Body: `{"ids": ["0cc8fffff5cc69081cce435709070e0687224aa3", "709638d7591074f3879df519c0fdd1144d2cfc03", "c31e7327bacee0a32c6a7dd2f61c84ec88ffab8a", "8b5957bc14f58a6d1b004f3be3197c919c2d524e", "c77d70c4f0cb52450cf401a26cdc18cd3dce3ae3", "0000000000000000000000000000000000000000"]}`
- Credentials: Semantic Scholar: header `x-api-key: <KEY>`
- Captured: 2026-10-06

### `crossref_work.json`

- Method: `GET`
- URL: `https://api.crossref.org/works/10.1016/j.matdes.2024.112730?mailto=<MAILTO>`
- Headers: `(none)`
- Body: `(none)`
- Credentials: Crossref: no key; `mailto=<MAILTO>` query parameter (polite pool)
- Captured: 2026-10-06

### `osti_record.json`

- Method: `GET`
- URL: `https://www.osti.gov/api/v1/records?title=Understanding%20bubble%20and%20void%20nucleation%20in%20dual%20ion%20irradiated%20T91%20steel%20using%20single%20parameter%20experiments&rows=1`
- Headers: `{"Accept": "application/json"}`
- Body: `(none)`
- Credentials: OSTI: no key; header `Accept: application/json`
- Captured: 2026-10-06

### `s2_references_elided.json`

- Method: `GET`
- URL: `https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.actamat.2020.07.060/references?fields=title,year,citationCount,externalIds,isInfluential&limit=5&offset=0`
- Headers: `(none)`
- Body: `(none)`
- Credentials: none (captured without a key)
- Captured: 2026-10-06
- Note: a paywalled Elsevier paper. Semantic Scholar returns `"data": null` with a disclaimer that the publisher has hidden its references. Kept for testing the reference fallback.