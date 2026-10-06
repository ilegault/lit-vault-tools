"""Explore's neighbor model, ranking and stub filenames: pure functions.

WHY THIS EXISTS
---------------
Semantic Scholar cannot sort citations server-side, so Explore pages through
the whole lean list and ranks locally; only the top slice then gets abstracts.

* `rank_neighbors` is a total order (influential first, citation count
  descending, `s2_id` ascending), so the same neighbors in any input order give
  the same top-N and the same files (invariant 4). A missing count ranks as 0.
* `stub_filename` makes the readable graph label (`Jones 2019 - Dislocation
  loops in irradiated…`). Identity is the `s2_id`/`doi` in frontmatter, never
  this name (invariant 3), so it only has to be unique. Collisions are judged
  case-insensitively because Windows filesystems are; `taken` is never mutated
  so the caller decides when a name is claimed. Forbidden characters are
  handled by `people.sanitize_filename`, the single owner of that rule.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from lit_vault_tools.config import STUB_TITLE_MAX_CHARS
from lit_vault_tools.domain.people import sanitize_filename

_NO_YEAR = "n.d."
_NO_AUTHOR = "Unknown"
_ELLIPSIS = "…"


@dataclass(frozen=True)
class Neighbor:
    """A reference or citation of the focus paper. `relation` is "reference" or "citation".

    The lean list fetch fills only id, title, year, citation count,
    influential and DOI; the rest arrive for the ranked top slice.
    """

    s2_id: str
    doi: str | None
    title: str | None
    authors: tuple[str, ...]
    year: int | None
    venue: str | None
    citation_count: int | None
    is_influential: bool
    tldr: str | None
    abstract: str | None
    relation: str


def rank_neighbors(neighbors: Sequence[Neighbor]) -> list[Neighbor]:
    """Influential first, then citation count descending, then `s2_id` ascending."""
    return sorted(
        neighbors,
        key=lambda n: (not n.is_influential, -(n.citation_count or 0), n.s2_id),
    )


def stub_filename(neighbor: Neighbor, taken: Collection[str]) -> str:
    """Readable, unique stub filename stem; never in `taken` (case-insensitive)."""
    words = neighbor.authors[0].split() if neighbor.authors else []
    surname = words[-1] if words else _NO_AUTHOR
    year = str(neighbor.year) if neighbor.year is not None else _NO_YEAR
    title = (neighbor.title or "").strip()
    if len(title) > STUB_TITLE_MAX_CHARS:
        title = title[:STUB_TITLE_MAX_CHARS].rstrip() + _ELLIPSIS
    base = sanitize_filename(f"{surname} {year} - {title}")
    used = {name.casefold() for name in taken}
    candidate = base
    counter = 2
    while candidate.casefold() in used:
        candidate = f"{base} ({counter})"
        counter += 1
    return candidate
