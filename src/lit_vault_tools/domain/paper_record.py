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
    openalex_id: str | None
    doi: str | None
    oa_status: str | None
    authors: list[tuple[AuthorRef, list[str]]]
    institutions: list[InstitutionRef]
    countries: list[str]
    subfield: str | None
    references: list[str]
    reference_dois: list[str] = field(default_factory=list)
    # OpenAlex subfield id (`2505`), so the subfield note can be matched by id, not name.
    subfield_id: str | None = None
    # author OpenAlex id -> the name as printed on the paper, kept as an alias when it differs.
    author_raw_names: dict[str, str] = field(default_factory=dict)
