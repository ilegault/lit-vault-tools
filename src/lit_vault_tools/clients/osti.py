"""OSTI.gov client: find a DOE report's DOI by title.

WHY THIS EXISTS
---------------
Some saved papers are DOE technical reports with no DOI in the note. OSTI is
searched by title and the first record's DOI (when it has one) is returned on a
`PaperRecord`, so the other lookups can then run by DOI. Matching by title is a
last resort, which is why only the DOI is taken and every other field stays
empty.

Request per `tests/fixtures/README.md`: `GET /api/v1/records?title=<t>&rows=1`
with `Accept: application/json`. No key is involved.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.paper_record import PaperRecord

_BASE = "https://www.osti.gov/api/v1/records"


def fetch_by_title(title: str, transport: Transport) -> PaperRecord | None:
    """First OSTI record for `title`; `None` on 404 or an empty result list."""
    url = f"{_BASE}?title={quote(title, safe='')}&rows=1"
    response = transport("GET", url, {"Accept": "application/json"}, None)
    if response.status == 404:
        return None
    if not 200 <= response.status < 300:
        raise ClientError(response.status, url)
    records = json.loads(response.body)
    if not records:
        return None
    return PaperRecord(
        openalex_id=None,
        doi=normalize_doi(records[0].get("doi")),
        oa_status=None,
        authors=[],
        institutions=[],
        countries=[],
        subfield=None,
        references=[],
    )
