"""Crossref client: a work's cited DOIs, used as the reference fallback.

WHY THIS EXISTS
---------------
When Semantic Scholar hides a paper's reference list (`ReferencesHidden`), the
publisher still deposits the cited DOIs with Crossref. This returns them as
`reference_dois` on a `PaperRecord`; every graph field OpenAlex fills stays empty
(`openalex_id=None`) because Crossref does not know them.

* Request per `tests/fixtures/README.md`: `GET /works/<doi>?mailto=<MAILTO>`
  (the polite pool). With an empty `mailto` no parameter is sent at all, so
  Explore works when `CROSSREF_MAILTO` is unset.
* The mailto is personal; `ClientError` redacts it from its message.
* Reference entries without a DOI are skipped, not guessed from their text.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.paper_record import PaperRecord

_BASE = "https://api.crossref.org"


def fetch_work(doi: str, mailto: str, transport: Transport) -> PaperRecord | None:
    """Fetch one work by DOI; `None` when Crossref answers 404."""
    bare = normalize_doi(doi)
    if bare is None:
        return None
    url = f"{_BASE}/works/{quote(bare, safe='/:()')}"
    if mailto:
        url += f"?mailto={quote(mailto, safe='@')}"
    response = transport("GET", url, {}, None)
    if response.status == 404:
        return None
    if not 200 <= response.status < 300:
        raise ClientError(response.status, url)
    message = json.loads(response.body)["message"]
    reference_dois = [
        normalized
        for reference in message.get("reference") or []
        if (normalized := normalize_doi(reference.get("DOI"))) is not None
    ]
    return PaperRecord(
        openalex_id=None,
        doi=normalize_doi(message.get("DOI")),
        oa_status=None,
        authors=[],
        institutions=[],
        countries=[],
        subfield=None,
        references=[],
        reference_dois=reference_dois,
    )
