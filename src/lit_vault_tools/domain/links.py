"""`refs` / `cited_by` between saved papers: pure functions.

WHY THIS EXISTS
---------------
`refs` and `cited_by` link saved papers to saved papers only; links to unsaved
papers exist only temporarily, in Explore (CONTEXT.md). Which saved note a
reference points at is decided by id (invariant 3): an OpenAlex id, or a DOI in
any spelling (`find_paper` normalises it). A filename is only what the link is
written with.

* `resolve_refs` never links a paper to itself and de-duplicates, and returns
  stems sorted case-insensitively so the output does not depend on file order
  (invariant 4).
* `cited_by` is never fetched: it is the inverse of `refs` across the vault, so
  it needs no network and stays consistent with `refs` by construction.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from lit_vault_tools.domain.doi import PaperIds, find_paper


def make_link(stem: str) -> str:
    return f"[[{stem}]]"


def link_stem(link: str) -> str:
    """`[[Note#Heading|alias]]` -> `Note`."""
    text = link.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    return text.split("|", 1)[0].split("#", 1)[0].strip()


def _sorted(stems: Iterable[str]) -> list[str]:
    return sorted(set(stems), key=lambda s: (s.casefold(), s))


def resolve_refs(
    openalex_ids: Sequence[str],
    dois: Sequence[str],
    candidates: Sequence[tuple[str, PaperIds]],
    own: str,
) -> list[str]:
    """Stems of the saved papers (other than `own`) that the given references point at."""
    others = [(stem, ids) for stem, ids in candidates if stem != own]
    pool = [ids for _, ids in others]
    found: set[str] = set()
    wanted = [PaperIds(openalex_id=w) for w in openalex_ids] + [PaperIds(doi=d) for d in dois]
    for ids in wanted:
        index = find_paper(ids, pool)
        if index is not None:
            found.add(others[index][0])
    return _sorted(found)


def cited_by_map(refs_by_stem: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """Invert `refs`: for each cited stem, the sorted stems whose refs include it."""
    inverted: dict[str, set[str]] = {}
    for citing, cited_stems in refs_by_stem.items():
        for cited in cited_stems:
            if cited != citing:
                inverted.setdefault(cited, set()).add(citing)
    return {cited: _sorted(citers) for cited, citers in inverted.items()}
