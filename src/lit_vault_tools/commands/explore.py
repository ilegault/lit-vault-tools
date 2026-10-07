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

Once everything is written, `retire_stubs` removes the stub of any neighbour that
is already a saved paper and links the saved note instead.

Load more (`more=True`)
-----------------------
Re-fetches and re-ranks the same focus, then writes the next `STUB_CAP_PER_LIST`
ranked neighbours per list whose `s2_id` is not already a stub in `_explore/`, and
rewrites `_focus.md` with the longer lists. It never wipes and never rewrites an
existing stub or `_trail.md`. It only applies to the current focus (the `focus:`
line of `_focus.md`); anything else fails without touching the vault. A neighbour
in both lists gets one stub, linked from both.

The trail (CONTEXT.md, Stub lifecycle 5)
----------------------------------------
`_explore/_trail.md` lists the last `trail_length` foci, newest first, as an ordered
list of links, and that list is the only state: it is parsed at the start of the
next run. A focus is either a saved note (resolved by `doi`) or a stub inside
`_explore/` (resolved by its `s2_id`). Trail foci that are stubs survive the wipe
(only their neighbours are cleared), and a neighbour that is already a trail stub
is linked, not written twice. A focus that falls off the end is deleted only if it
is a stub: it is simply not kept by the wipe, whereas a saved note is outside
`_explore/` and is never touched. The trail is rewritten only after a fully
successful fetch, so a failed run leaves it as it was.
"""

from __future__ import annotations

import dataclasses
import logging
import re
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
from lit_vault_tools.config import STUB_CAP_PER_LIST, TRAIL_LENGTH
from lit_vault_tools.domain.doi import PaperIds, normalize_doi
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.neighbors import Neighbor, rank_neighbors, stub_filename
from lit_vault_tools.domain.stubs import read_stub_ids, render_stub
from lit_vault_tools.vault.explore_dir import explore_path, wipe_explore, write_stub
from lit_vault_tools.vault.retire import retire_stubs

logger = logging.getLogger(__name__)

_FOCUS_FILE = "_focus"
_TRAIL_FILE = "_trail"
_TRAIL_ITEM = re.compile(r"^\s*\d+\.\s*\[\[(.+?)\]\]\s*$")


@dataclass
class ExploreSummary:
    ok: bool
    message: str = ""
    references_total: int = 0
    references_shown: int = 0
    citations_total: int = 0
    citations_shown: int = 0
    references_hidden: bool = False
    trail: list[str] = dataclasses.field(default_factory=list)


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
    trail_length: int = TRAIL_LENGTH,
    more: bool = False,
) -> ExploreSummary:
    """Explore `focus_note`; on any failure nothing in the vault changes."""
    vault, focus_note = Path(vault), Path(focus_note)
    try:
        with open(focus_note, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as err:
        return _failed(f"cannot read the focus note {focus_note}: {err}")
    ref, problem = _paper_ref(vault, focus_note, text)
    if ref is None:
        return _failed(problem)

    if more and (problem := _not_current_focus(vault, focus_note)):
        return _failed(problem)

    pacer = pacer or _make_pacer(sleep, clock)
    trail = [focus_note.stem, *(s for s in _read_trail(vault) if s != focus_note.stem)][: max(1, trail_length)]
    kept = {} if more else _trail_stubs(vault, trail)
    existing = _stub_index(vault) if more else {ids.s2_id: stem for stem, ids in kept.items() if ids.s2_id}
    hidden = False
    try:
        try:
            references = fetch_neighbors(ref, "reference", api_key, transport, pacer=pacer)
        except ReferencesHidden:
            references, hidden = [], True
        citations = fetch_neighbors(ref, "citation", api_key, transport, pacer=pacer)
        shown_refs = _select(rank_neighbors(references), existing, more)
        shown_cits = _select(rank_neighbors(citations), existing, more)
        ids = list(dict.fromkeys(n.s2_id for n in (*shown_refs, *shown_cits) if n.s2_id not in existing))
        details = fetch_details(ids, api_key, transport, pacer=pacer)
    except ClientError as err:
        return _failed(f"Semantic Scholar request failed ({err}); _explore/ was left as it was")

    if not more:
        wipe_explore(vault, keep=kept)
    taken = {_FOCUS_FILE, _TRAIL_FILE, *kept, *existing.values()}
    ref_names = _write_stubs(vault, shown_refs, details, taken, existing)
    cit_names = _write_stubs(vault, shown_cits, details, taken, existing)
    summary = ExploreSummary(
        ok=True,
        references_total=len(references),
        references_shown=len(shown_refs),
        citations_total=len(citations),
        citations_shown=len(shown_cits),
        references_hidden=hidden,
        trail=trail,
    )
    write_stub(vault, _FOCUS_FILE, _render_focus(focus_note.stem, ref_names, cit_names, summary))
    if not more:
        write_stub(vault, _TRAIL_FILE, _render_trail(trail))
    retire_stubs(vault)
    verb = "loaded more for" if more else "explored"
    summary.message = (
        f"{verb} {focus_note.stem}: {summary.references_shown} of {summary.references_total} references, "
        f"{summary.citations_shown} of {summary.citations_total} citations"
        + (" (references hidden by the publisher)" if hidden else "")
    )
    return summary


def _select(ranked: Sequence[Neighbor], existing: dict[str, str], more: bool) -> list[Neighbor]:
    """The neighbours to list: the top slice, or (more) every existing stub plus the next slice, in rank order."""
    if not more:
        return list(ranked[:STUB_CAP_PER_LIST])
    new = {n.s2_id for n in [n for n in ranked if n.s2_id not in existing][:STUB_CAP_PER_LIST]}
    return [n for n in ranked if n.s2_id in existing or n.s2_id in new]


def _not_current_focus(vault: Path, focus_note: Path) -> str:
    """Why `--more` cannot apply to `focus_note` ("" when it can): it must be the focus in `_focus.md`."""
    try:
        text = (explore_path(vault) / f"{_FOCUS_FILE}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "there is no current focus yet; run explore on the note first"
    if read_scalar(split_note(text), "focus") != f"[[{focus_note.stem}]]":
        return f"{focus_note.stem} is not the current focus; run explore on it first, then --more"
    return ""


def _stub_index(vault: Path) -> dict[str, str]:
    """s2_id -> stem of every stub currently in `_explore/`."""
    index: dict[str, str] = {}
    root = explore_path(vault)
    for path in sorted(root.glob("*.md")) if root.is_dir() else []:
        if path.stem in (_FOCUS_FILE, _TRAIL_FILE):
            continue
        try:
            s2_id = read_stub_ids(path.read_text(encoding="utf-8")).s2_id
        except (OSError, UnicodeDecodeError):
            continue
        if s2_id:
            index[s2_id] = path.stem
    return index


def _paper_ref(vault: Path, focus_note: Path, text: str) -> tuple[str | None, str]:
    """(Semantic Scholar paper ref, "") for the focus, or (None, why not). A stub is resolved by `s2_id`."""
    if _inside_explore(vault, focus_note):
        ids = read_stub_ids(text)
        if ids.s2_id:
            return ids.s2_id, ""
        if ids.doi:
            return f"DOI:{ids.doi}", ""
        return None, f"the focus stub {focus_note.name} has neither an s2_id nor a doi"
    doi = normalize_doi(read_scalar(split_note(text), "doi"))
    if doi is None:
        return None, f"the focus note {focus_note.name} has no usable doi; explore needs one"
    return f"DOI:{doi}", ""


def _inside_explore(vault: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(explore_path(vault).resolve())
    except ValueError:
        return False
    return True


def _read_trail(vault: Path) -> list[str]:
    """Stems in `_trail.md`, newest first; missing or unreadable means an empty trail."""
    try:
        text = (explore_path(vault) / f"{_TRAIL_FILE}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [m.group(1) for line in text.splitlines() if (m := _TRAIL_ITEM.match(line))]


def _trail_stubs(vault: Path, trail: Sequence[str]) -> dict[str, PaperIds]:
    """Trail entries that are stub files in `_explore/` (stem -> their ids); saved notes are not stubs."""
    kept: dict[str, PaperIds] = {}
    for stem in trail:
        path = explore_path(vault) / f"{stem}.md"
        if stem in (_FOCUS_FILE, _TRAIL_FILE) or not path.is_file():
            continue
        try:
            kept[stem] = read_stub_ids(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return kept


def _render_trail(trail: Sequence[str]) -> str:
    items = [f"{number}. [[{stem}]]" for number, stem in enumerate(trail, start=1)]
    return "\n".join(["---", "type: trail", "---", "", *items, ""])


def _make_pacer(sleep, clock) -> Pacer:
    kwargs = {k: v for k, v in (("sleep", sleep), ("clock", clock)) if v is not None}
    return Pacer(**kwargs)


def _write_stubs(
    vault: Path,
    neighbors: Sequence[Neighbor],
    details: dict[str, Details],
    taken: set[str],
    existing: dict[str, str],
) -> list[str]:
    """Write one stub per neighbour in rank order; returns their filename stems in that order.

    A neighbour that is already a (kept) trail stub is linked by its existing name, not rewritten.
    """
    names = []
    for neighbor in neighbors:
        if neighbor.s2_id in existing:
            names.append(existing[neighbor.s2_id])
            continue
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
        existing[neighbor.s2_id] = stem
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
