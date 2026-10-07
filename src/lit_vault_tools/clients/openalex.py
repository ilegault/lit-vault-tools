"""OpenAlex client: one work, looked up by DOI, returned as a `PaperRecord`.

WHY THIS EXISTS
---------------
Enrich identifies a paper by DOI and needs its authors, institutions, countries,
subfield and reference ids. The request is exactly the one recorded in
`tests/fixtures/README.md`: `GET /works/doi:<doi>?api_key=<KEY>`. OpenAlex takes
its key as a query parameter, so the URL is secret-bearing: it is never logged,
and `ClientError` redacts it.

404 means OpenAlex does not know the DOI and is `None`, not an error; any other
non-success status is a `ClientError`.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.paper_record import PaperRecord
from lit_vault_tools.domain.people import AuthorRef, InstitutionRef

_BASE = "https://api.openalex.org"
_PREFIX = "https://openalex.org/"


def _id(value: str) -> str:
    return value.removeprefix(_PREFIX)


def fetch_work(doi: str, api_key: str, transport: Transport) -> PaperRecord | None:
    """Fetch one work by DOI; `None` when OpenAlex answers 404."""
    bare = normalize_doi(doi)
    if bare is None:
        return None
    url = f"{_BASE}/works/doi:{quote(bare, safe='/:()')}?api_key={api_key}"
    response = transport("GET", url, {}, None)
    if response.status == 404:
        return None
    if not 200 <= response.status < 300:
        raise ClientError(response.status, url)
    return _parse(json.loads(response.body))


def fetch_institution_geo(institution_id: str, api_key: str, transport: Transport) -> tuple[float, float] | None:
    """(latitude, longitude) of one institution, or None when unknown (404 or null coordinates).

    Work responses carry only dehydrated institutions (no coordinates), hence this
    per-institution lookup. Invariant 6: unknown means None, never (0, 0).
    """
    url = f"{_BASE}/institutions/{_id(institution_id)}?api_key={api_key}"
    response = transport("GET", url, {}, None)
    if response.status == 404:
        return None
    if not 200 <= response.status < 300:
        raise ClientError(response.status, url)
    geo = json.loads(response.body).get("geo") or {}
    lat, lng = geo.get("latitude"), geo.get("longitude")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _parse(raw: dict) -> PaperRecord:
    authors: list[tuple[AuthorRef, list[str]]] = []
    institutions: dict[str, InstitutionRef] = {}
    countries: list[str] = []
    for authorship in raw.get("authorships") or []:
        author = authorship["author"]
        raw_institutions = authorship.get("institutions") or []
        names = [i.get("display_name") for i in raw_institutions]
        authors.append((AuthorRef(_id(author["id"]), author.get("display_name")), names))
        for institution in raw_institutions:
            institution_id = _id(institution["id"])
            institutions.setdefault(
                institution_id,
                InstitutionRef(
                    institution_id,
                    institution.get("display_name"),
                    institution.get("ror"),
                    institution.get("country_code"),
                    institution.get("type"),
                ),
            )
        for country in authorship.get("countries") or []:
            if country not in countries:
                countries.append(country)
    subfield = ((raw.get("primary_topic") or {}).get("subfield") or {}).get("display_name")
    return PaperRecord(
        openalex_id=_id(raw["id"]),
        doi=normalize_doi(raw.get("doi")),
        oa_status=(raw.get("open_access") or {}).get("oa_status"),
        authors=authors,
        institutions=list(institutions.values()),
        countries=countries,
        subfield=subfield,
        references=[_id(r) for r in raw.get("referenced_works") or []],
    )
