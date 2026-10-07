"""`explore`: temporary stub previews of one focus paper's references and citations.

WHY THIS EXISTS
---------------
Wires clients -> domain -> vault for the temporary half of the design: for one
focus paper, fetch its current neighbours from Semantic Scholar and write them as
stubs in `_explore/`, plus `_explore/_focus.md` (the only place the temporary links
live, decision 14), so saved notes are never modified.

Order matters. Everything is fetched FIRST (lean lists for both relations, ranked
locally, then abstract/tldr details for just the top `STUB_CAP_PER_LIST` of each),
and only then is `_explore/` wiped and rewritten. A failed fetch therefore returns
a failed summary and leaves the previous session's files byte-for-byte intact.

Details are requested only for the selected stubs, never for all neighbours: a
heavily cited paper has thousands of citations and the batch endpoint has a 10 MB
response cap. `_focus.md` states how many were shown of how many exist, so it is
obvious when there is more.

References the publisher has hidden (`ReferencesHidden`) are reported as hidden,
never shown as an empty list. The Crossref fallback for that case is ticket 22.
The focus note is read before the wipe; keeping a focus that lives inside
`_explore/` (the trail) is ticket 17.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.clients.semantic_scholar import (
    Details,
    Pacer,
    ReferencesHidden,
    fetch_details,
    fetch_neighbors,
)
from lit_vault_tools.config import STUB_CAP_PER_LIST
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.neighbors import Neighbor, rank_neighbors, stub_filename
from lit_vault_tools.domain.stubs import render_stub
from lit_vault_tools.vault.explore_dir import wipe_explore, write_stub

logger = logging.getLogger(__name__)

_FOCUS_FILE = "_focus"


@dataclass
class ExploreSummary:
    ok: bool
    message: str = ""
    references_total: int = 0
    references_shown: int = 0
    citations_total: int = 0
    citations_shown: int = 0
    references_hidden: bool = False


def _failed(message: str) -> ExploreSummary:
    return ExploreSummary(ok=False, message=message)


def run_explore(
    vault: Path,
    focus_note: Path,
    api_key: str,
    transport: Transport,
    sleep=None,
    clock=None,
    pacer: Pacer | None = None,
) -> ExploreSummary:
    """Explore `focus_note`; on any failure nothing in the vault changes."""
    vault, focus_note = Path(vault), Path(focus_note)
    try:
        with open(focus_note, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as err:
        return _failed(f"cannot read the focus note {focus_note}: {err}")
    doi = normalize_doi(read_scalar(split_note(text), "doi"))
    if doi is None:
        return _failed(f"the focus note {focus_note.name} has no usable doi; explore needs one")

    pacer = pacer or _make_pacer(sleep, clock)
    ref = f"DOI:{doi}"
    hidden = False
    try:
        try:
            references = fetch_neighbors(ref, "reference", api_key, transport, pacer=pacer)
        except ReferencesHidden:
            references, hidden = [], True
        citations = fetch_neighbors(ref, "citation", api_key, transport, pacer=pacer)
        shown_refs = rank_neighbors(references)[:STUB_CAP_PER_LIST]
        shown_cits = rank_neighbors(citations)[:STUB_CAP_PER_LIST]
        ids = list(dict.fromkeys(n.s2_id for n in (*shown_refs, *shown_cits)))
        details = fetch_details(ids, api_key, transport, pacer=pacer)
    except ClientError as err:
        return _failed(f"Semantic Scholar request failed ({err}); _explore/ was left as it was")

    wipe_explore(vault)
    taken = {_FOCUS_FILE}
    ref_names = _write_stubs(vault, shown_refs, details, taken)
    cit_names = _write_stubs(vault, shown_cits, details, taken)
    summary = ExploreSummary(
        ok=True,
        references_total=len(references),
        references_shown=len(shown_refs),
        citations_total=len(citations),
        citations_shown=len(shown_cits),
        references_hidden=hidden,
    )
    write_stub(vault, _FOCUS_FILE, _render_focus(focus_note.stem, ref_names, cit_names, summary))
    summary.message = (
        f"explored {focus_note.stem}: {summary.references_shown} of {summary.references_total} references, "
        f"{summary.citations_shown} of {summary.citations_total} citations"
        + (" (references hidden by the publisher)" if hidden else "")
    )
    return summary


def _make_pacer(sleep, clock) -> Pacer:
    kwargs = {k: v for k, v in (("sleep", sleep), ("clock", clock)) if v is not None}
    return Pacer(**kwargs)


def _write_stubs(vault: Path, neighbors: Sequence[Neighbor], details: dict[str, Details], taken: set[str]) -> list[str]:
    """Write one stub per neighbour in rank order; returns their filename stems in that order."""
    names = []
    for neighbor in neighbors:
        extra = details.get(neighbor.s2_id)
        if extra is not None:
            neighbor = dataclasses.replace(
                neighbor,
                abstract=extra.abstract,
                tldr=extra.tldr,
                authors=extra.authors,
                venue=extra.venue,
            )
        stem = stub_filename(neighbor, taken)
        taken.add(stem)
        write_stub(vault, stem, render_stub(neighbor))
        names.append(stem)
    return names


def _showing(shown: int, total: int, noun: str) -> str:
    return f"showing {shown:,} of {total:,} {noun}"


def _render_focus(focus_stem: str, refs: Sequence[str], cits: Sequence[str], summary: ExploreSummary) -> str:
    """`_explore/_focus.md`: the temporary links to every stub, in rank order."""
    lines = ["---", "type: focus", f'focus: "[[{focus_stem}]]"', "---", "", "## References", ""]
    if summary.references_hidden:
        lines.append("The publisher has hidden this paper's reference list at Semantic Scholar.")
    else:
        lines.append(_showing(summary.references_shown, summary.references_total, "references"))
    lines += ["", *(f"- [[{name}]]" for name in refs), "", "## Citations", ""]
    lines.append(_showing(summary.citations_shown, summary.citations_total, "citations"))
    lines += ["", *(f"- [[{name}]]" for name in cits), ""]
    return "\n".join(lines)
