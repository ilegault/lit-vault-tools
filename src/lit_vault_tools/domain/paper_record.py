"""The plain-data shape of one paper as OpenAlex describes it.

WHY THIS EXISTS
---------------
Clients return plain data and domain code consumes it, so neither needs to know
the other's wire format. `PaperRecord` is what `enrich` works from; every field
is already normalised (DOI lowercase and bare, ids without the
`https://openalex.org/` prefix).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lit_vault_tools.domain.people import AuthorRef, InstitutionRef


@dataclass(frozen=True)
class PaperRecord:
    openalex_id: str
    doi: str | None
    oa_status: str | None
    authors: list[tuple[AuthorRef, list[str]]]
    institutions: list[InstitutionRef]
    countries: list[str]
    subfield: str | None
    references: list[str]
    reference_dois: list[str] = field(default_factory=list)
