"""DOI normalization and paper matching.

WHY THIS EXISTS
---------------
Invariant 3: papers are matched by ID (DOI / `openalex_id` / `s2_id`), never by
filename or title. DOIs arrive as URLs, `doi:` strings or upper-case text
depending on the source, so every comparison goes through `normalize_doi` first.
`find_paper` deliberately takes no filename, so it cannot match on one, and a
missing id never equals a missing id (two unidentified papers are not the same
paper).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(raw: str | None) -> str | None:
    """Return the lowercase bare DOI, or None when `raw` is empty or not a DOI."""
    if raw is None:
        return None
    text = _PREFIX.sub("", raw.strip()).strip().lower()
    return text if _DOI.match(text) else None


@dataclass(frozen=True)
class PaperIds:
    doi: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None


def find_paper(ids: PaperIds, candidates: Sequence[PaperIds]) -> int | None:
    """Index of the first candidate sharing any non-None id with `ids`, else None."""
    wanted = {
        "doi": normalize_doi(ids.doi),
        "openalex_id": ids.openalex_id,
        "s2_id": ids.s2_id,
    }
    wanted = {k: v for k, v in wanted.items() if v is not None}
    if not wanted:
        return None
    for index, candidate in enumerate(candidates):
        have = {
            "doi": normalize_doi(candidate.doi),
            "openalex_id": candidate.openalex_id,
            "s2_id": candidate.s2_id,
        }
        if any(have[key] == value for key, value in wanted.items()):
            return index
    return None
