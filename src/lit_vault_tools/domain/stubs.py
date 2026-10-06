"""Stub note text and stub id reading: pure functions.

WHY THIS EXISTS
---------------
A stub is a temporary preview in `_explore/` (CONTEXT.md, Stub lifecycle).
Identity lives in frontmatter (`s2_id`, `doi`), never in the filename
(invariant 3), so `read_stub_ids` is how retirement and trail logic find out
which paper a stub file is.

* Authors are plain text so exploring never adds author nodes to the graph. A
  stub's text must therefore never contain a wikilink: `[[` / `]]` in API text
  are broken apart with a space rather than rendered as a link.
* Missing data is omitted, never printed as `None`, and an unknown DOI has no
  `doi:` line.
* Output is deterministic (invariant 4): same neighbor, same bytes.
"""

from __future__ import annotations

import json

from lit_vault_tools.domain.doi import PaperIds, normalize_doi
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.neighbors import Neighbor

_UNTITLED = "Untitled"


def _plain(text: str) -> str:
    """Text with wikilink brackets defused, so API content can never become a link."""
    return text.replace("[[", "[ [").replace("]]", "] ]")


def _line(text: str) -> str:
    return " ".join(_plain(text).split())


def render_stub(neighbor: Neighbor) -> str:
    """Full text of the stub note for `neighbor`."""
    doi = normalize_doi(neighbor.doi)
    head = ["---", "type: stub", f"s2_id: {neighbor.s2_id}"]
    if doi:
        head.append(f"doi: {json.dumps(doi)}")
    head += [f"relation: {neighbor.relation}", "---"]

    facts: list[str] = []
    authors = [_line(a) for a in neighbor.authors if a.strip()]
    if authors:
        facts.append(f"**Authors:** {', '.join(authors)}")
    if neighbor.year is not None:
        facts.append(f"**Year:** {neighbor.year}")
    if neighbor.venue:
        facts.append(f"**Venue:** {_line(neighbor.venue)}")
    if neighbor.citation_count is not None:
        facts.append(f"**Citations:** {neighbor.citation_count}")
    facts.append(f"**Influential:** {'yes' if neighbor.is_influential else 'no'}")

    blocks = [f"# {_line(neighbor.title or '') or _UNTITLED}", "\n".join(facts)]
    if neighbor.tldr:
        blocks.append(f"**TL;DR:** {_line(neighbor.tldr)}")
    if neighbor.abstract:
        blocks.append(f"## Abstract\n\n{_plain(neighbor.abstract.strip())}")
    if doi:
        blocks.append(f"**DOI:** [{doi}](https://doi.org/{doi})")
    return "\n".join(head) + "\n" + "\n".join(f"{block}\n" for block in blocks)


def read_stub_ids(text: str) -> PaperIds:
    """The DOI (normalized) and `s2_id` a stub's frontmatter declares."""
    parts = split_note(text)
    return PaperIds(doi=normalize_doi(read_scalar(parts, "doi")), s2_id=read_scalar(parts, "s2_id"))
